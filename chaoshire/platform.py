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

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from secrets import compare_digest, token_urlsafe
from typing import Any
from uuid import uuid4

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .site import public_origin

# A zero value disables the corresponding limiter. The defaults are non-zero so
# a deployment that forgets to configure anything is still bounded.
DEFAULT_RATE_LIMIT_PER_MINUTE = 120
DEFAULT_WRITE_RATE_LIMIT_PER_MINUTE = 6
DEFAULT_ANONYMOUS_APPEALS_PER_MINUTE = 2
TRUTHY = {"1", "true", "yes", "on"}

# Anonymous uploads are never published. A function, not a stray ``False``
# literal in ``write_posture()``, so the public note and the JSON field cannot
# drift from each other.
ANONYMOUS_UPLOADS_PUBLISHED = False

# The in-memory limiter is per-process. Naming that in the posture is how a
# reviewer learns that scaling replicas silently doubles the budget.
LIMITER_SCOPE = "process-local-memory"

# Committed contract with ``render.yaml``. ``tests/api/test_write_access.py``
# parses the Blueprint and fails if these diverge. Live drift (dashboard env
# vs this file) is reported at boot and on ``GET /api/ops/posture``.
BLUEPRINT_CONTRACT: dict[str, str] = {
    "CHAOSHIRE_ALLOW_ANONYMOUS_WRITES": "1",
    "CHAOSHIRE_RATE_LIMIT_PER_MINUTE": "120",
    "CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE": "6",
    "CHAOSHIRE_TRUST_FORWARDED_FOR": "1",
    "CHAOSHIRE_MAX_APPEALS": "200",
    "CHAOSHIRE_MAX_BODY_BYTES": "5500000",
    "CHAOSHIRE_DB_PATH": "/app/data/chaoshire.db",
    "CHAOSHIRE_ANONYMOUS_APPEALS_PER_MINUTE": "2",
    "CHAOSHIRE_AUDIT_HISTORY_DURABLE": "0",
    "CHAOSHIRE_FORCE_HTTPS": "1",
    "CHAOSHIRE_TRUST_FORWARDED_PROTO": "1",
    "CHAOSHIRE_PUBLIC_ORIGIN": "https://chaoshire.onrender.com",
}

# Keys that describe budgets, key presence, and bucketing. Public ``/api/meta``
# omits them when disclosure is off so a private deployment is not a recon
# surface. The boot log and ``GET /api/ops/posture`` always carry the full set.
_RECON_POSTURE_KEYS = (
    "api_key_configured",
    "rate_limit_per_minute",
    "write_rate_limit_per_minute",
    "instance_write_rate_limit_per_minute",
    "anonymous_appeals_per_minute",
    "appeals_capacity",
    "trusted_proxy_headers",
    "rate_limit_bucketing",
    "client_ip_selection",
    "limiter_scope",
    "audit_history_durable",
    "blueprint_drift",
    "worker_count",
)


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


def running_on_render() -> bool:
    return bool(os.getenv("RENDER_SERVICE_ID") or os.getenv("RENDER_EXTERNAL_URL"))


def force_https() -> bool:
    """Require TLS on Render; leave local HTTP usable unless explicitly enabled."""
    return _bool_env("CHAOSHIRE_FORCE_HTTPS", running_on_render())


def trusted_forwarded_proto() -> bool:
    """Only trust proxy scheme headers behind an operator-declared TLS terminator."""
    return _bool_env("CHAOSHIRE_TRUST_FORWARDED_PROTO", running_on_render())


def is_secure_request(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    forwarded = request.headers.get("x-forwarded-proto", "").split(",", maxsplit=1)[0]
    return trusted_forwarded_proto() and forwarded.strip().lower() == "https"


def configured_api_key() -> str | None:
    """Return the trimmed ``CHAOSHIRE_API_KEY``, or ``None`` when unset."""
    return (os.getenv("CHAOSHIRE_API_KEY") or "").strip() or None


def anonymous_writes_allowed() -> bool:
    return _bool_env("CHAOSHIRE_ALLOW_ANONYMOUS_WRITES", True)


def anonymous_uploads_published() -> bool:
    """Anonymous uploads are never published. Single source of that fact."""
    return ANONYMOUS_UPLOADS_PUBLISHED


def rate_limit_per_minute() -> int:
    return _int_env("CHAOSHIRE_RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE)


def write_rate_limit_per_minute() -> int:
    return _int_env("CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE", DEFAULT_WRITE_RATE_LIMIT_PER_MINUTE)


def instance_write_rate_limit_per_minute() -> int:
    """Process-wide write cap. Defaults to the per-client write budget.

    A live probe of chaoshire.onrender.com (2026-09-20) sent 7 anonymous
    ``POST /api/appeals`` with no spoofed headers and got 200 seven times,
    while ``/api/meta`` advertised ``write_rate_limit_per_minute: 6`` and
    ``/api/metrics`` showed zero 429s. Per-client keys were therefore not
    collapsing to one bucket (dual-stack IPv4/IPv6, ``ip:port`` tokens, or
    a unique XFF hop per connection). This backstop is the same number, on
    a single ``write:_instance`` key, so the advertised budget is enforced
    even when identity fails.
    """
    return _int_env(
        "CHAOSHIRE_INSTANCE_WRITE_RATE_LIMIT_PER_MINUTE",
        write_rate_limit_per_minute(),
    )


def anonymous_appeals_per_minute() -> int:
    """Extra budget on anonymous ``POST /api/appeals``, on top of the write budget.

    Zero disables the extra limiter (the write budget still applies).
    """
    return _int_env("CHAOSHIRE_ANONYMOUS_APPEALS_PER_MINUTE", DEFAULT_ANONYMOUS_APPEALS_PER_MINUTE)


def trust_forwarded_for() -> bool:
    """Only honour ``X-Forwarded-For`` when the operator says a proxy sets it."""
    return _bool_env("CHAOSHIRE_TRUST_FORWARDED_FOR", False)


def audit_history_durable() -> bool:
    """Operator declaration that ``CHAOSHIRE_DB_PATH`` survives a redeploy.

    Defaults to false — honest for Render's free plan, whose filesystem is
    wiped on redeploy. Set ``CHAOSHIRE_AUDIT_HISTORY_DURABLE=1`` only when a
    persistent disk or managed database is actually attached. The process
    cannot detect that from inside the container.
    """
    return _bool_env("CHAOSHIRE_AUDIT_HISTORY_DURABLE", False)


def disclose_write_posture() -> bool:
    """Whether ``/api/meta`` includes budgets, key presence, and bucketing.

    Defaults to the same value as anonymous writes: the public demo stays
    verifiable from outside, a private deployment does not advertise its
    gates. Override with ``CHAOSHIRE_DISCLOSE_WRITE_POSTURE``.
    """
    return _bool_env("CHAOSHIRE_DISCLOSE_WRITE_POSTURE", anonymous_writes_allowed())


def process_worker_count() -> int:
    for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        raw = (os.getenv(name) or "").strip()
        if raw.isdigit():
            return max(1, int(raw))
    return 1


def blueprint_drift() -> list[dict[str, str]]:
    """Live env vs the committed ``render.yaml`` contract.

    Unset variables are not drift — local runs and the test suite use code
    defaults. A variable that *is* set to something other than the Blueprint
    value is an operator override (or a stale dashboard) and is reported.
    ``CHAOSHIRE_API_KEY`` is ``generateValue`` and is only checked for presence
    on operator endpoints, never compared.
    """
    drift: list[dict[str, str]] = []
    for name, expected in BLUEPRINT_CONTRACT.items():
        actual = (os.getenv(name) or "").strip()
        if not actual:
            continue
        if actual != expected:
            drift.append({"name": name, "expected": expected, "actual": actual})
    return drift


def write_posture_note() -> str:
    published = anonymous_uploads_published()
    return (
        "Only uploads authenticated with CHAOSHIRE_API_KEY are published to the "
        "shared audit history. Anonymous uploads are "
        + ("also published." if published else "returned to the caller and discarded.")
        + " Behind a trusted proxy, set CHAOSHIRE_TRUST_FORWARDED_FOR=1 so rate "
        "limits bucket per client; unset, every visitor shares one bucket. "
        "Rate limits are process-local memory and reset on restart. "
        "Set CHAOSHIRE_DISCLOSE_WRITE_POSTURE=0 to hide budgets from /api/meta."
    )


def write_posture() -> dict[str, Any]:
    """Full deployment write posture; boot log and operator endpoints use this."""
    from .state import appeals_capacity

    trusted = trust_forwarded_for()
    return {
        "api_key_configured": configured_api_key() is not None,
        "anonymous_writes_allowed": anonymous_writes_allowed(),
        "anonymous_uploads_published": anonymous_uploads_published(),
        "rate_limit_per_minute": rate_limit_per_minute(),
        "write_rate_limit_per_minute": write_rate_limit_per_minute(),
        "instance_write_rate_limit_per_minute": instance_write_rate_limit_per_minute(),
        "anonymous_appeals_per_minute": anonymous_appeals_per_minute(),
        "trusted_proxy_headers": trusted,
        "rate_limit_bucketing": "per-client-ip" if trusted else "shared-per-instance",
        "client_ip_selection": ("left-most-x-forwarded-for" if trusted else "socket-peer"),
        "limiter_scope": LIMITER_SCOPE,
        "appeals_capacity": appeals_capacity(),
        "audit_history_durable": audit_history_durable(),
        "disclose_write_posture": disclose_write_posture(),
        "blueprint_drift": blueprint_drift(),
        "worker_count": process_worker_count(),
        "note": write_posture_note(),
    }


def public_write_posture() -> dict[str, Any]:
    """Posture safe to put on the unauthenticated ``/api/meta`` surface."""
    posture = write_posture()
    if disclose_write_posture():
        return {**posture, "disclosed": True}
    redacted = {key: value for key, value in posture.items() if key not in _RECON_POSTURE_KEYS}
    redacted["disclosed"] = False
    redacted["note"] = (
        "Write-posture details are withheld on this deployment. "
        "Authenticate to GET /api/ops/posture."
    )
    return redacted


def describe_client(request: Request) -> dict[str, Any]:
    """Behavioural view of how this request would be rate-limited.

    Lets an operator prove the left-most-XFF rule against a live proxy:
    send a spoofed left-most entry and read back ``client_key``. Config
    disclosure (``/api/meta``) cannot prove that.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    candidates = [part.strip() for part in forwarded.split(",") if part.strip()]
    trusted = trust_forwarded_for()
    using_xff = bool(trusted and candidates)
    return {
        "client_key": client_key(request),
        "source": "x-forwarded-for-leftmost" if using_xff else "socket-peer",
        "xff_present": bool(candidates),
        "xff_entry_count": len(candidates),
        "trust_forwarded_for": trusted,
        "assumption": (
            "The left-most X-Forwarded-For entry is treated as the client IP "
            "Render documents. A process-wide write backstop still applies, so "
            "a unique key per connection cannot bypass the advertised budget."
        ),
    }


def ensure_package_logging(log: logging.Logger) -> None:
    """Attach a stderr handler to ``log`` only if nothing would emit INFO.

    Does not call ``logging.basicConfig`` and does not touch the root logger, so
    embedding hosts keep their configuration. Walks the logger hierarchy: if
    any ancestor already has a handler (pytest caplog, uvicorn ``dictConfig``,
    a container entrypoint) this is a no-op.
    """
    probe: logging.Logger | None = log
    while probe is not None:
        if probe.handlers:
            return
        if not probe.propagate:
            break
        parent = probe.parent
        probe = parent if parent is not probe else None
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


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


def canonical_ip(value: str) -> str:
    """Strip a ``host:port`` suffix so ephemeral ports cannot mint buckets."""
    value = value.strip()
    if value.startswith("[") and "]" in value:
        return value[1 : value.index("]")]
    if value.count(":") == 1:
        host, _, port = value.rpartition(":")
        if port.isdigit() and host:
            return host
    return value or "unknown"


def client_key(request: Request) -> str:
    """Best-effort per-client identifier used as the rate-limit bucket key.

    ``X-Forwarded-For`` is only consulted when the operator has declared a
    trusted proxy. Render documents the **left-most** entry as the client IP
    it observed; a 2026-09-20 live probe showed that using only the right-most
    hop (or a raw ``ip:port`` token) does not collapse to one bucket. We take
    the left-most hop, strip a port suffix, and still enforce a process-wide
    write backstop in :func:`require_write_access` so a unique key per
    connection cannot bypass the advertised budget.
    """
    if trust_forwarded_for():
        forwarded = request.headers.get("x-forwarded-for", "")
        candidates = [canonical_ip(part) for part in forwarded.split(",") if part.strip()]
        if candidates:
            return candidates[0]
    host = request.client.host if request.client else "unknown"
    return canonical_ip(host)


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
    instance_limit = instance_write_rate_limit_per_minute()
    instance_bucket = "write:_instance"
    if instance_limit and not LIMITER.allow(instance_bucket, instance_limit):
        raise HTTPException(
            status_code=429,
            detail=(
                f"Instance write budget exhausted ({instance_limit} mutating "
                "requests per minute). Retry later."
            ),
            headers={"Retry-After": str(LIMITER.retry_after(instance_bucket))},
        )
    return access


def require_operator(
    x_api_key: str | None = Header(default=None),
) -> None:
    """Admit an operator-only read. Anonymous is never enough.

    Used by ``/api/ops/*`` so the public demo can hide recon from ``/api/meta``
    without losing a verification surface.
    """
    configured = configured_api_key()
    if not configured:
        raise HTTPException(
            status_code=503,
            detail="Operator endpoints require CHAOSHIRE_API_KEY to be configured.",
        )
    if not x_api_key or not compare_digest(configured, x_api_key):
        raise HTTPException(status_code=401, detail="A valid X-API-Key header is required.")


async def platform_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex[:16]
    # Health probes run inside the Render network and need not be redirected.
    health_probes = {"/api/health", "/api/live", "/api/ready"}
    if force_https() and not is_secure_request(request) and request.url.path not in health_probes:
        target = public_origin() + request.url.path
        if request.url.query:
            target += "?" + request.url.query
        return RedirectResponse(
            target,
            status_code=308,
            headers={"Cache-Control": "no-store", "X-Request-ID": request_id},
        )
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
    if is_secure_request(request):
        # Do not include subdomains: Render controls other *.onrender.com hosts.
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; "
        f"script-src 'self' 'nonce-{request.state.csp_nonce}'; "
        "img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response
