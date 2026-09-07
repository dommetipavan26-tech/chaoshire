"""Security, access-control, and lightweight operational primitives."""
import os
import threading
import time
from collections import defaultdict, deque
from secrets import compare_digest
from typing import Any
from uuid import uuid4

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse


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
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - window_seconds:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True


LIMITER = SlidingWindowLimiter()


def require_write_access(x_api_key: str | None = Header(default=None)) -> None:
    """Protect mutation routes only when CHAOSHIRE_API_KEY is configured."""
    configured = os.getenv("CHAOSHIRE_API_KEY")
    if configured and (not x_api_key or not compare_digest(configured, x_api_key)):
        raise HTTPException(status_code=401, detail="A valid X-API-Key header is required.")


async def platform_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex[:16]
    content_length = request.headers.get("content-length")
    maximum = int(os.getenv("CHAOSHIRE_MAX_BODY_BYTES", "5500000"))
    if content_length and int(content_length) > maximum:
        return JSONResponse(
            {"detail": "Request body exceeds the configured size limit."},
            status_code=413,
            headers={"X-Request-ID": request_id},
        )
    rate_limit = int(os.getenv("CHAOSHIRE_RATE_LIMIT_PER_MINUTE", "0"))
    client = request.client.host if request.client else "unknown"
    if rate_limit and not LIMITER.allow(client, rate_limit):
        return JSONResponse(
            {"detail": "Rate limit exceeded. Retry later."},
            status_code=429,
            headers={"Retry-After": "60", "X-Request-ID": request_id},
        )
    started = time.perf_counter()
    response = await call_next(request)
    duration = (time.perf_counter() - started) * 1000
    OPERATIONS.record(response.status_code, duration)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
    )
    return response
