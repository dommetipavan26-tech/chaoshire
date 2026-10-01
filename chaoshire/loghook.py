"""Best-effort aggregate log delivery with bounded workers, bytes, and outstanding jobs.

An optional server-only webhook receives five allowlisted event kinds. Payloads
contain aggregate metadata, never candidate rows or appeal message bodies.
The HMAC secret is captured at enqueue time; credential-bearing exception text
is never logged. Delivery outages drop work instead of blocking application
requests. No retry/durability guarantee is made.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)
_MAX_QUEUE = 256  # Pending PLUS in-flight, not a thread-per-request backlog.
_MAX_WORKERS = 4
_MAX_EVENT_BYTES = 65_536

SHIPPED_EVENTS = (
    "audit.completed",
    "appeal.created",
    "chaos.completed",
    "mitigation.completed",
    "upload.completed",
)


def webhook_url() -> str | None:
    return (os.getenv("CHAOSHIRE_LOG_WEBHOOK_URL") or "").strip() or None


def webhook_secret() -> str | None:
    return (os.getenv("CHAOSHIRE_LOG_WEBHOOK_SECRET") or "").strip() or None


def webhook_enabled() -> bool:
    return webhook_url() is not None


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _build_payload(event: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        "service": "chaoshire",
        "data": data,
    }


@dataclass(frozen=True)
class Delivery:
    url: str
    event: str
    body: bytes
    signature: str | None


def _deliver(job: Delivery) -> bool:
    """Perform real delivery; tests inject an HTTP transport rather than skip this path."""
    headers = {"Content-Type": "application/json"}
    if job.signature is not None:
        headers["X-ChaosHire-Signature"] = job.signature
    try:
        # Do not follow a redirect with credentials or buffer an arbitrary
        # receiver response body. Only the status is needed for observability.
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            with client.stream("POST", job.url, content=job.body, headers=headers) as response:
                succeeded = 200 <= response.status_code < 300
                if not succeeded:
                    logger.warning(
                        "log webhook rejected event %s (status %d)", job.event, response.status_code
                    )
                return succeeded
    except Exception as error:
        logger.warning("log webhook delivery failed for %s (%s)", job.event, type(error).__name__)
        return False


class WebhookDispatcher:
    """A fixed daemon-worker pool with a shared outstanding-job reservation.

    Taking a job off the pending deque does NOT free its capacity reservation;
    it stays reserved until completion. A stalled receiver therefore cannot
    cause more threads/jobs to be allocated than the configured bounds.
    """

    def __init__(
        self,
        *,
        workers: int = _MAX_WORKERS,
        capacity: int = _MAX_QUEUE,
        max_event_bytes: int = _MAX_EVENT_BYTES,
        deliver: Callable[[Delivery], bool] | None = None,
    ) -> None:
        if workers < 1 or capacity < workers or max_event_bytes < 1:
            raise ValueError("Webhook bounds must be positive and capacity must cover all workers.")
        self.workers = workers
        self.capacity = capacity
        self.max_event_bytes = max_event_bytes
        self.pid = os.getpid()
        self._deliver = deliver or _deliver
        self._condition = threading.Condition()
        self._pending: deque[Delivery] = deque()
        self._in_flight = 0
        self._sent = self._failed = self._dropped = 0
        self._accepting = True
        self._closing = False
        self._threads = [
            threading.Thread(target=self._work, name=f"chaoshire-webhook-{i}", daemon=True)
            for i in range(workers)
        ]
        for thread in self._threads:
            thread.start()

    def submit(self, url: str, event: str, data: dict[str, Any], secret: str | None = None) -> bool:
        try:
            if event not in SHIPPED_EVENTS:
                raise ValueError("Unsupported event")
            body = json.dumps(
                _build_payload(event, data), ensure_ascii=True, allow_nan=False
            ).encode("utf-8")
            if len(body) > self.max_event_bytes:
                raise ValueError("Oversized event")
            job = Delivery(url, event, body, _sign(body, secret) if secret else None)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            with self._condition:
                self._dropped += 1
            return False
        with self._condition:
            if not self._accepting or len(self._pending) + self._in_flight >= self.capacity:
                self._dropped += 1
                return False
            self._pending.append(job)
            self._condition.notify()
            return True

    def _work(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending or self._closing)
                if not self._pending:
                    return
                job = self._pending.popleft()
                self._in_flight += 1
            success = False
            try:
                success = self._deliver(job)
            except Exception as error:
                # A broken injected/embedded delivery callback must not kill a
                # worker and strand its reservation forever.
                logger.warning("log delivery callback failed (%s)", type(error).__name__)
            finally:
                with self._condition:
                    self._in_flight -= 1
                    self._sent += bool(success)
                    self._failed += not success
                    self._condition.notify_all()

    def flush(self, timeout: float = 5.0) -> bool:
        with self._condition:
            return self._condition.wait_for(
                lambda: not self._pending and not self._in_flight, timeout=timeout
            )

    def close(self, timeout: float = 5.0, *, drain: bool = True) -> bool:
        """Seal the queue and join within a bounded deadline; daemon jobs may be lost at exit."""
        with self._condition:
            self._accepting = False
            self._closing = True
            if not drain:
                self._dropped += len(self._pending)
                self._pending.clear()
            self._condition.notify_all()
        deadline = time.monotonic() + timeout
        for thread in self._threads:
            thread.join(max(0, deadline - time.monotonic()))
        return all(not thread.is_alive() for thread in self._threads)

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            return {
                "queue_depth": len(self._pending),
                "in_flight": self._in_flight,
                "outstanding": len(self._pending) + self._in_flight,
                "max_queue": self.capacity,
                "max_outstanding": self.capacity,
                "worker_limit": self.workers,
                "active_workers": sum(thread.is_alive() for thread in self._threads),
                "max_event_bytes": self.max_event_bytes,
                "delivered": self._sent,
                "failed": self._failed,
                "dropped": self._dropped,
                "accepting": self._accepting,
            }


_DISPATCHER: WebhookDispatcher | None = None
_DISPATCHER_LOCK = threading.Lock()


def _dispatcher() -> WebhookDispatcher | None:
    global _DISPATCHER
    with _DISPATCHER_LOCK:
        if _DISPATCHER is not None and _DISPATCHER.pid != os.getpid():
            # Forked processes cannot use a parent process's worker threads.
            _DISPATCHER = None
        if _DISPATCHER is not None and not _DISPATCHER.snapshot()["accepting"]:
            if _DISPATCHER.snapshot()["active_workers"]:
                return None  # Never start a second pool while a sealed pool is alive.
            _DISPATCHER = None
        if _DISPATCHER is None:
            _DISPATCHER = WebhookDispatcher()
        return _DISPATCHER


def ship(event: str, data: dict[str, Any]) -> None:
    """Non-blocking best-effort enqueue; an unconfigured hook allocates no threads."""
    url = webhook_url()
    if url is None:
        return
    dispatcher = _dispatcher()
    if dispatcher is not None:
        dispatcher.submit(url, event, data, webhook_secret())


def shutdown_log_shipping(timeout: float = 5.0) -> bool:
    """Called on application shutdown; no credentials or payloads in its result."""
    with _DISPATCHER_LOCK:
        dispatcher = _DISPATCHER
    return dispatcher.close(timeout) if dispatcher is not None else True


def queue_depth() -> int:
    with _DISPATCHER_LOCK:
        return _DISPATCHER.snapshot()["queue_depth"] if _DISPATCHER is not None else 0


def drain_all_sync() -> list[dict[str, Any]]:
    """Compatibility test helper: wait for bounded delivery, return only safe summary stats."""
    with _DISPATCHER_LOCK:
        dispatcher = _DISPATCHER
    if dispatcher is None:
        return []
    dispatcher.flush()
    return [dispatcher.snapshot()]


def log_shipping_status() -> dict[str, Any]:
    with _DISPATCHER_LOCK:
        dispatcher = _DISPATCHER
    stats = (
        dispatcher.snapshot()
        if dispatcher is not None
        else {
            "queue_depth": 0,
            "in_flight": 0,
            "outstanding": 0,
            "max_queue": _MAX_QUEUE,
            "max_outstanding": _MAX_QUEUE,
            "worker_limit": _MAX_WORKERS,
            "active_workers": 0,
            "max_event_bytes": _MAX_EVENT_BYTES,
            "delivered": 0,
            "failed": 0,
            "dropped": 0,
            "accepting": True,
        }
    )
    return {
        "configured": webhook_enabled(),
        "url_present": webhook_enabled(),
        "signed": webhook_secret() is not None,
        "events_shipped": list(SHIPPED_EVENTS),
        **stats,
    }
