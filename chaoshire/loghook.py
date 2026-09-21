"""Structured JSON log-shipping hook for external observability pipelines.

When ``CHAOSHIRE_LOG_WEBHOOK_URL`` is set, key application events are POSTed
as JSON to that endpoint on a background thread. Failures are logged locally
but never block the request that triggered them — a dead webhook must not
take the application down.

Events shipped
--------------
``audit.completed``
    An aggregate audit finished (demo or uploaded CSV). Carries the audit ID
    (if published), model, certificate grade and candidate count.
``appeal.created``
    A candidate appeal was accepted into the queue. Carries the appeal ID
    and priority only — the message body is never shipped.
``chaos.completed``
    A chaos suite run finished. Carries the experiment ID, model, resilience
    score and per-test verdicts.
``mitigation.completed``
    A mitigation simulation finished. Carries the before/after grades and
    the strategies applied.
``upload.completed``
    A CSV upload was validated and audited. Carries the audit ID (if
    published), row count, attributes and whether the result was published.

The webhook receives ``application/json`` with a top-level ``event`` key and
a ``timestamp`` in ISO-8601 UTC. A ``CHAOSHIRE_LOG_WEBHOOK_SECRET`` may be
set to sign each payload with an ``X-ChaosHire-Signature`` header
(HMAC-SHA256 hex digest of the body), so the receiver can authenticate the
source without a shared bearer token.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_QUEUE_LOCK = threading.Lock()
_QUEUE: list[dict[str, Any]] = []
_MAX_QUEUE = 256


def webhook_url() -> str | None:
    """Return the configured webhook URL, or ``None`` when unset."""
    raw = (os.getenv("CHAOSHIRE_LOG_WEBHOOK_URL") or "").strip()
    return raw or None


def webhook_secret() -> str | None:
    """Return the configured HMAC secret, or ``None`` when unset."""
    raw = (os.getenv("CHAOSHIRE_LOG_WEBHOOK_SECRET") or "").strip()
    return raw or None


def webhook_enabled() -> bool:
    """Whether log shipping is configured."""
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


def ship(event: str, data: dict[str, Any]) -> None:
    """Enqueue a structured event for delivery on a background thread.

    Silently drops the event when the queue is full — a webhook outage must
    never exert backpressure on the request path. The queue is bounded so a
    dead webhook cannot accumulate unbounded memory.
    """
    url = webhook_url()
    if not url:
        return
    payload = _build_payload(event, data)
    with _QUEUE_LOCK:
        if len(_QUEUE) >= _MAX_QUEUE:
            logger.warning("chaoshire log-shipping queue full; dropping event %r", event)
            return
        _QUEUE.append({"url": url, "payload": payload})
    thread = threading.Thread(target=_drain_one, daemon=True)
    thread.start()


def _drain_one() -> None:
    """Deliver one queued event. Failures are logged and swallowed."""
    with _QUEUE_LOCK:
        if not _QUEUE:
            return
        item = _QUEUE.pop(0)
    url = item["url"]
    body = json.dumps(item["payload"], ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    secret = webhook_secret()
    if secret:
        headers["X-ChaosHire-Signature"] = _sign(body, secret)
    try:
        import httpx

        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, content=body, headers=headers)
        if response.status_code >= 400:
            logger.warning(
                "chaoshire log-shipping webhook returned %s for %s",
                response.status_code,
                item["payload"]["event"],
            )
    except ImportError:  # pragma: no cover - httpx is a declared runtime dep
        logger.warning("chaoshire log-shipping unavailable (httpx not installed)")
    except Exception as error:
        logger.warning("chaoshire log-shipping delivery failed: %r", error)


def drain_all_sync() -> list[dict[str, Any]]:
    """Deliver every queued event synchronously. Used by tests only."""
    results: list[dict[str, Any]] = []
    while True:
        with _QUEUE_LOCK:
            if not _QUEUE:
                break
            item = _QUEUE.pop(0)
        url = item["url"]
        body = json.dumps(item["payload"], ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        secret = webhook_secret()
        if secret:
            headers["X-ChaosHire-Signature"] = _sign(body, secret)
        import httpx

        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, content=body, headers=headers)
        results.append(
            {
                "event": item["payload"]["event"],
                "status_code": response.status_code,
                "body": response.text,
            }
        )
    return results


def queue_depth() -> int:
    """Number of events waiting for delivery. Used by operational endpoints."""
    with _QUEUE_LOCK:
        return len(_QUEUE)


def log_shipping_status() -> dict[str, Any]:
    """Status snapshot for ``/api/meta`` and operator posture endpoints."""
    url = webhook_url()
    return {
        "configured": url is not None,
        "url_present": url is not None,
        "signed": webhook_secret() is not None,
        "queue_depth": queue_depth(),
        "max_queue": _MAX_QUEUE,
        "events_shipped": list(SHIPPED_EVENTS),
    }


#: Event names the hook recognises. Documented for operators and tests.
SHIPPED_EVENTS = (
    "audit.completed",
    "appeal.created",
    "chaos.completed",
    "mitigation.completed",
    "upload.completed",
)
