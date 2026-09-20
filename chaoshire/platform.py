"""Security, access-control, and lightweight operational primitives.

Write access model
------------------
Mutating routes (``POST /api/upload``, ``POST /api/appeals``,
``POST /api/connectors/audit``) are gated by :func:`require_write_access`,
which returns a :class:`WriteAccess` describing *how* the caller was admitted:

``authenticated=True``
    The caller presented the configured ``CHAOSHIRE_API_KEY``. Authenticated
    uploads are published: they are written to the persistent audit history and
    become the shared ``dataset=uploaded`` artifact every visitor can read.

``authenticated=False``
    Anonymous writes are permitted only while
    ``CHAOSHIRE_ALLOW_ANONYMOUS_WRITES`` is truthy (the default, so a local run
    and the public portfolio demo stay interactive). Anonymous uploads are
    computed and returned to the caller but are **never** published, so an
    unauthenticated visitor cannot write an attacker-chosen name into the
    shared audit history that everyone else sees.

Either way a per-client write budget (``CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE``)
applies, and setting ``CHAOSHIRE_ALLOW_ANONYMOUS_WRITES=0`` makes the gateway
fail closed: with no key configured it returns 503, with a key configured it
returns 401.
"""

import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from secrets import compare_digest, token_urlsafe
from typing import Any
from uuid import uuid4

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse

# A zero value disables the corresponding limiter. The defaults are non-zero so
# a deployment that forgets to configure anything is still bounded.
DEFAULT_RATE_LIMIT_PER_MINUTE = 120
DEFAULT_WRITE_RATE_LIMIT_PER_MINUTE = 6
TRUTHY = {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    return raw.lower() in TRUTHY


def configured_api_key() -> str | None:
    """Return the trimmed ``CHAOSHIRE_API_KEY``, or ``None`` when unset."""
    return (os.getenv("CHAOSHIRE_API_KEY") or "").strip() or None


def anonymous_writes_allowed() -> bool:
    return _bool_env("CHAOSHIRE_ALLOW_ANONYMOUS_WRITES", True)


def rate_limit_per_minute() -> int:
    return _int_env("CHAOSHIRE_RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE)


def write_rate_limit_per_minute() -> int:
    return _int_env("CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE", DEFAULT_WRITE_RATE_LIMIT_PER_MINUTE)


def trust_forwarded_for() -> bool:
    """Only honour ``X-Forwarded-For`` when the operator says a proxy sets it."""
    return _bool_env("CHAOSHIRE_TRUST_FORWARDED_FOR", False)


def write_posture() -> dict[str, Any]:
    """Describe the deployment's write posture; surfaced through ``/api/meta``."""
    from .state import appeals_capacity

    trusted = trust_forwarded_for()
    return {
        "api_key_configured": configured_api_key() is not None,
        "anonymous_writes_allowed": anonymous_writes_allowed(),
        "anonymous_uploads_published": False,
        "rate_limit_per_minute": rate_limit_per_minute(),
        "write_rate_limit_per_minute": write_rate_limit_per_minute(),
        "appeals_capacity": appeals_capacity(),
        "trusted_proxy_headers": trusted,
        "rate_limit_bucketing": "per-client-ip" if trusted else "shared-per-instance",
        "note": (
            "Only uploads authenticated with CHAOSHIRE_API_KEY are published to the "
            "shared audit history. Anonymous uploads are returned to the caller and "
            "discarded, so the public demo cannot be defaced through the audit name. "
            "Rate limits bucket per client IP only when CHAOSHIRE_TRUST_FORWARDED_FOR=1 "
            "declares a trusted proxy; with the variable unset every visitor shares "
            "one per-instance bucket."
        ),
    }


class Operations:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started = time.time()
        self.requests = 0
        self.errors = 0
        self.duration_ms = 0.0
        self.statuses: dict[int, int] = defaultdict(int)

    def record(self, status: int, duration_ms: float) -> None:
        with self._lock:
            self.requests += 1
            self.errors += status >= 500
            self.duration_ms += duration_ms
            self.statuses[status] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "uptime_seconds": round(time.time() - self.started, 1),
                "requests": self.requests,
                "server_errors": self.errors,
                "average_duration_ms": round(self.duration_ms / max(1, self.requests), 2),
                "statuses": dict(sorted(self.statuses.items())),
            }


OPERATIONS = Operations()


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - window_seconds:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True

    def retry_after(self, key: str, window_seconds: int = 60) -> int:
        """Seconds until the oldest event in ``key``'s window expires."""
        now = time.monotonic()
        with self._lock:
            events = self._events.get(key)
            if not events:
                return window_seconds
            return max(1, int(window_seconds - (now - events[0])) + 1)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


LIMITER = SlidingWindowLimiter()


@dataclass(frozen=True)
class WriteAccess:
    """How a mutating request was admitted."""

    authenticated: bool
    client: str


def client_key(request: Request) -> str:
    """Best-effort per-client identifier used as the rate-limit bucket key.

    ``X-Forwarded-For`` is only consulted when the operator has declared a
    trusted proxy, and then only its **right-most** entry — the address the
    proxy itself observed — so a client cannot rotate the header to escape the
    budget.
    """
    if trust_forwarded_for():
        forwarded = request.headers.get("x-forwarded-for", "")
        candidates = [part.strip() for part in forwarded.split(",") if part.strip()]
        if candidates:
            return candidates[-1]
    return request.client.host if request.client else "unknown"


def require_write_access(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> WriteAccess:
    """Admit a mutating request, or fail closed with a status code that says why.

    This is a FastAPI dependency: routes declare
    ``dependencies=[Depends(require_write_access)]`` when they only need the
    gate, or ``access: WriteAccess = Depends(require_write_access)`` when the
    handler also needs to know whether the caller was authenticated.
    """
    configured = configured_api_key()
    client = client_key(request)

    if configured and x_api_key and compare_digest(configured, x_api_key):
        access = WriteAccess(authenticated=True, client=client)
    elif configured and x_api_key:
        # A key was offered and rejected: never silently downgrade to anonymous.
        raise HTTPException(status_code=401, detail="The supplied X-API-Key was rejected.")
    elif anonymous_writes_allowed():
        access = WriteAccess(authenticated=False, client=client)
    elif configured:
        raise HTTPException(status_code=401, detail="A valid X-API-Key header is required.")
    else:
        raise HTTPException(
            status_code=503,
            detail=(
                "Writes are disabled on this deployment: CHAOSHIRE_API_KEY is not "
                "configured and CHAOSHIRE_ALLOW_ANONYMOUS_WRITES is off."
            ),
        )

    limit = write_rate_limit_per_minute()
    bucket = f"write:{client}"
    if limit and not LIMITER.allow(bucket, limit):
        raise HTTPException(
            status_code=429,
            detail=f"Write budget exhausted ({limit} mutating requests per minute). Retry later.",
            headers={"Retry-After": str(LIMITER.retry_after(bucket))},
        )
    return access


async def platform_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex[:16]
    # A fresh nonce per request; the nonce-based CSP below forbids 'unsafe-inline'.
    request.state.csp_nonce = token_urlsafe(16)
    content_length = request.headers.get("content-length")
    maximum = _int_env("CHAOSHIRE_MAX_BODY_BYTES", 5_500_000)
    if content_length and int(content_length) > maximum:
        return JSONResponse(
            {"detail": "Request body exceeds the configured size limit."},
            status_code=413,
            headers={"X-Request-ID": request_id},
        )
    client = client_key(request)
    limit = rate_limit_per_minute()
    if limit and not LIMITER.allow(client, limit):
        return JSONResponse(
            {"detail": "Rate limit exceeded. Retry later."},
            status_code=429,
            headers={
                "Retry-After": str(LIMITER.retry_after(client)),
                "X-Request-ID": request_id,
            },
        )
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Unhandled endpoint exceptions are converted to a 500 further up the
        # stack, so record them here or operational metrics would never see them.
        OPERATIONS.record(500, (time.perf_counter() - started) * 1000)
        raise
    duration = (time.perf_counter() - started) * 1000
    OPERATIONS.record(response.status_code, duration)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        f"script-src 'self' 'nonce-{request.state.csp_nonce}'; "
        "img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response
