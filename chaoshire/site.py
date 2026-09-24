"""Public site metadata and small, first-party, consent-based traffic counters.

No visitor identifiers, IP addresses, user agents, referrers, or event payloads
are stored here. Counters are process-local and expire after 30 UTC days.
"""

from __future__ import annotations

import os
import re
import threading
from collections import Counter
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_PUBLIC_ORIGIN = "https://chaoshire.onrender.com"
WEB_DIR = Path(__file__).resolve().parent / "web"


def css_version() -> str:
    """Cache-bust the stylesheet when its content changes without a new release tag."""
    return sha256((WEB_DIR / "static" / "chaoshire.css").read_bytes()).hexdigest()[:12]


ANALYTICS_PAGES = frozenset(
    {
        "welcome",
        "overview",
        "chaos",
        "filtered",
        "mitigations",
        "appeals",
        "upload",
        "history",
        "compare",
        "agent",
        "demo",
    }
)


def public_origin() -> str:
    """Return an operator-configured HTTPS origin, never the untrusted Host header."""
    origin = (os.getenv("CHAOSHIRE_PUBLIC_ORIGIN") or DEFAULT_PUBLIC_ORIGIN).strip().rstrip("/")
    try:
        parts = urlsplit(origin)
        if (
            parts.scheme == "https"
            and parts.hostname
            and parts.port != 0
            and not parts.username
            and not parts.password
            and not parts.path
            and not parts.query
            and not parts.fragment
            and re.fullmatch(r"[A-Za-z0-9.:[\]-]+", parts.netloc)
            and not any(char in origin for char in "\r\n\t\\")
        ):
            return origin
    except ValueError:  # invalid IPv6 literal or port
        pass
    return DEFAULT_PUBLIC_ORIGIN


def site_html(filename: str, nonce: str = "") -> str:
    """Fill safe server-owned SEO values into one of the packaged HTML pages."""
    if filename not in {"index.html", "privacy.html", "terms.html", "404.html"}:
        raise ValueError("Unknown site page")
    html = (WEB_DIR / filename).read_text(encoding="utf-8")
    html = html.replace("__PUBLIC_ORIGIN__", escape(public_origin(), quote=True))
    html = html.replace("__CSS_VERSION__", css_version())
    if nonce:
        html = html.replace("<script>", f'<script nonce="{nonce}">', 1)
    return html


class SiteAnalytics:
    """Bounded per-page, per-day counts; no visitor records or persistent state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._days: dict[str, Counter[str]] = {}

    def record(self, page: str) -> None:
        if page not in ANALYTICS_PAGES:
            raise ValueError("Unknown analytics page")
        now = datetime.now(UTC).date()
        cutoff = (now - timedelta(days=29)).isoformat()
        with self._lock:
            self._days = {day: counts for day, counts in self._days.items() if day >= cutoff}
            self._days.setdefault(now.isoformat(), Counter())[page] += 1

    def snapshot(self) -> dict[str, object]:
        cutoff = (datetime.now(UTC).date() - timedelta(days=29)).isoformat()
        with self._lock:
            self._days = {day: counts for day, counts in self._days.items() if day >= cutoff}
            return {
                "retention_days": 30,
                "storage": "process-local aggregate counts (reset on restart)",
                "views": {
                    day: dict(sorted(counts.items())) for day, counts in sorted(self._days.items())
                },
                "total_views": sum(sum(counts.values()) for counts in self._days.values()),
            }

    def reset(self) -> None:
        """Clear counters between isolated test cases."""
        with self._lock:
            self._days.clear()


SITE_ANALYTICS = SiteAnalytics()
