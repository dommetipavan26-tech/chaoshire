"""Check a deployed ChaosHire site from the outside.

The Render service is hand-managed, so a merge or a green CI run does not prove
what visitors get. This script checks the running site itself:

* the deployed build matches this checkout (optionally waiting for a deploy);
* public routes, content types, robots.txt, sitemap.xml, and the social card;
* the HTTP -> HTTPS redirect, HSTS, and the other security headers;
* the analytics endpoints reject bad input and keep counts operator-only;
* every link on the public pages resolves;
* in Chromium: no horizontal overflow at 1440/390/320px, all three model
  choices visible, no analytics beacon before consent, Reject and Allow behave;
* warm server response times and real-browser page speed.

    python -m pip install -r requirements-browser.txt
    python -m playwright install chromium
    python scripts/check_live_site.py --base-url https://chaoshire.onrender.com

Everything is read-only apart from one deliberately invalid analytics POST,
which the server rejects with 422 without counting it. The browser consent
check intercepts the analytics beacon, so production counters are not touched.
Under GitHub Actions the results are also written as annotations and a job
summary. The exit status is 1 when any check fails; a site that is not yet
running this checkout's build is reported as a warning, not a failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "reports" / "generated" / "live"
CONSENT_KEY = "chaoshire-analytics-consent-v1"
BEACON_PATH = "/api/analytics/view"
USER_AGENT = "ChaosHire-live-check/1.0 (+https://github.com/dommetipavan26-tech/chaoshire)"
CSS_VERSION = re.compile(r"chaoshire\.css\?v=([0-9a-f]{12})")
REDIRECT_CODES = (301, 302, 307, 308)
ONE_YEAR = 31_536_000

#: (path, expected status, expected content-type prefix, request headers)
ROUTES: list[tuple[str, int, str, dict[str, str]]] = [
    ("/", 200, "text/html", {}),
    ("/privacy", 200, "text/html", {}),
    ("/terms", 200, "text/html", {}),
    ("/robots.txt", 200, "text/plain", {}),
    ("/sitemap.xml", 200, "application/xml", {}),
    ("/social-preview.png", 200, "image/png", {}),
    ("/favicon.ico", 200, "image/", {}),
    ("/icons/favicon-32.png", 200, "image/png", {}),
    ("/api/ready", 200, "application/json", {}),
    ("/this-page-does-not-exist", 404, "text/html", {"Accept": "text/html"}),
    ("/api/this-does-not-exist", 404, "application/json", {}),
]
LINK_PAGES = ("/", "/privacy", "/terms")


@dataclass
class Results:
    """Check results grouped by category, in the order they were recorded."""

    items: list[tuple[str, str, str]] = field(default_factory=list)

    def record(self, category: str, status: str, detail: str) -> None:
        self.items.append((category, status, detail))
        print(f"[{status}] {category}: {detail}", flush=True)

    def check(self, category: str, passed: bool, detail: str) -> bool:
        self.record(category, "PASS" if passed else "FAIL", detail)
        return passed

    def info(self, category: str, detail: str) -> None:
        self.record(category, "INFO", detail)

    def warn(self, category: str, detail: str) -> None:
        self.record(category, "WARN", detail)

    @property
    def failed(self) -> bool:
        return any(status == "FAIL" for _, status, _ in self.items)


def expected_build() -> dict[str, str]:
    """Build facts this checkout would advertise, read without importing the app."""
    build_info = (REPO_ROOT / "chaoshire" / "build_info.py").read_text(encoding="utf-8")
    package = (REPO_ROOT / "chaoshire" / "__init__.py").read_text(encoding="utf-8")
    patterns = {
        "version": (package, r'^__version__ = "([^"]+)"'),
        "automated_tests": (build_info, r"^AUTOMATED_TESTS = (\d+)"),
        "package_coverage": (build_info, r'^PACKAGE_COVERAGE = "([^"]+)"'),
    }
    facts: dict[str, str] = {}
    for key, (text, pattern) in patterns.items():
        match = re.search(pattern, text, re.MULTILINE)
        if not match:
            raise SystemExit(f"could not read {key} from this checkout")
        facts[key] = match.group(1)
    stylesheet = REPO_ROOT / "chaoshire" / "web" / "static" / "chaoshire.css"
    facts["stylesheet"] = hashlib.sha256(stylesheet.read_bytes()).hexdigest()[:12]
    return facts


def describe(build: dict[str, Any]) -> str:
    if not build:
        return "no build information"
    if "error" in build:
        return f"an error ({build['error']})"
    return (
        f"v{build.get('version')}, {build.get('automated_tests')} tests, "
        f"{build.get('package_coverage')}, stylesheet {build.get('stylesheet')}"
    )


def get(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    follow: bool = False,
    timeout: float = 30.0,
) -> httpx.Response:
    """GET with a bounded wait when the site's rate limiter answers 429."""
    response = client.get(url, headers=headers, follow_redirects=follow, timeout=timeout)
    for _ in range(2):
        if response.status_code != 429:
            break
        retry_after = response.headers.get("retry-after", "10")
        time.sleep(min(int(retry_after) if retry_after.isdigit() else 10, 60))
        response = client.get(url, headers=headers, follow_redirects=follow, timeout=timeout)
    return response


def live_build(client: httpx.Client, base: str) -> dict[str, Any]:
    build: dict[str, Any] = dict(get(client, f"{base}/api/meta", timeout=120.0).json()["build"])
    match = CSS_VERSION.search(get(client, f"{base}/", timeout=60.0).text)
    build["stylesheet"] = match.group(1) if match else None
    return build


def wait_for_build(
    client: httpx.Client, base: str, expected: dict[str, str], wait_minutes: float, results: Results
) -> bool:
    """Poll until the live site advertises this checkout's build, or give up."""
    deadline = time.monotonic() + wait_minutes * 60
    first = True
    while True:
        started = time.perf_counter()
        try:
            build = live_build(client, base)
        except (httpx.HTTPError, ValueError, KeyError) as error:
            build = {"error": type(error).__name__}
        if first:
            elapsed = time.perf_counter() - started
            results.info(
                "Server speed",
                f"first responses this run took {elapsed:.1f}s (includes any cold start)",
            )
            first = False
        if all(str(build.get(key)) == value for key, value in expected.items()):
            results.check("Build", True, f"live site runs this commit's build: {describe(build)}")
            return True
        if time.monotonic() >= deadline:
            results.warn(
                "Build",
                f"live site reports {describe(build)}; this commit expects {describe(expected)}. "
                "Deploy it on Render, then run this check again.",
            )
            return False
        time.sleep(20)


def check_routes(
    client: httpx.Client, base: str, canonical: str, results: Results
) -> dict[str, httpx.Response]:
    responses: dict[str, httpx.Response] = {}
    problems: list[str] = []
    for path, status, content_type, headers in ROUTES:
        response = get(client, base + path, headers=headers)
        responses[path] = response
        actual = response.headers.get("content-type", "")
        if response.status_code != status or not actual.startswith(content_type):
            problems.append(
                f"{path} -> {response.status_code} {actual or 'no content-type'} "
                f"(expected {status} {content_type})"
            )
    for problem in problems:
        results.check("Routes", False, problem)
    if not problems:
        results.check("Routes", True, f"all {len(ROUTES)} routes return the expected status/type")

    def text(path: str) -> str:
        return responses[path].text if responses[path].status_code < 500 else ""

    titles = {
        "/privacy": "<title>Privacy Policy | ChaosHire</title>",
        "/terms": "<title>Terms &amp; Conditions | ChaosHire</title>",
        "/this-page-does-not-exist": "<title>Page not found | ChaosHire</title>",
    }
    missing = [path for path, title in titles.items() if title not in text(path)]
    results.check(
        "Routes",
        not missing,
        "privacy, terms and 404 pages carry their titles"
        if not missing
        else f"missing expected <title> on {', '.join(missing)}",
    )
    robots, sitemap, home = text("/robots.txt"), text("/sitemap.xml"), text("/")
    if canonical:
        sitemap_line = f"Sitemap: {canonical}/sitemap.xml"
        wanted = [f"<loc>{canonical}{path}</loc>" for path in ("/", "/privacy", "/terms")]
    else:
        results.info("Routes", "canonical origin unknown: robots/sitemap origin checks skipped")
        sitemap_line = "Sitemap: "
        wanted = ["/privacy</loc>", "/terms</loc>"]
    results.check(
        "Routes",
        "Disallow: /api/" in robots and sitemap_line in robots,
        f"robots.txt disallows /api/ and declares '{sitemap_line.strip()}'",
    )
    results.check(
        "Routes",
        all(item in sitemap for item in wanted),
        f"sitemap.xml lists the home, privacy and terms pages{' at ' + canonical if canonical else ''}",
    )
    card = responses["/social-preview.png"].content
    size = struct.unpack(">II", card[16:24]) if card[:8] == b"\x89PNG\r\n\x1a\n" else None
    results.check("Routes", size == (1200, 630), f"social-preview.png is a PNG of size {size}")
    results.check(
        "Routes",
        'property="og:image"' in home and "/social-preview.png" in home,
        "home page declares the social card as og:image",
    )
    return responses


def check_https(
    client: httpx.Client, base: str, http_url: str | None, canonical: str, results: Results
) -> None:
    if not base.startswith("https://"):
        results.info("HTTPS", "skipped: the base URL is not HTTPS")
        return
    target = (http_url or "http://" + urlsplit(base).netloc).rstrip("/") + "/privacy"
    response = get(client, target)
    location = response.headers.get("location", "")
    expected = f"{canonical}/privacy"
    results.check(
        "HTTPS",
        response.status_code in REDIRECT_CODES and location == expected,
        f"{target} -> {response.status_code} {location or '(no Location header)'}",
    )
    health = get(client, base + "/api/ready")
    results.check("HTTPS", health.status_code == 200, f"HTTPS /api/ready -> {health.status_code}")


def check_headers(response: httpx.Response, secure: bool, results: Results) -> None:
    headers = response.headers
    if secure:
        hsts = headers.get("strict-transport-security", "")
        match = re.search(r"max-age=(\d+)", hsts)
        results.check(
            "Headers",
            bool(match) and int(match.group(1) if match else 0) >= ONE_YEAR,
            f"Strict-Transport-Security: {hsts or 'missing'}",
        )
    csp = headers.get("content-security-policy", "")
    csp_ok = bool(csp) and "unsafe-inline" not in csp and "frame-ancestors 'none'" in csp
    results.check(
        "Headers",
        csp_ok,
        "Content-Security-Policy present, no unsafe-inline, frame-ancestors 'none'"
        if csp_ok
        else f"Content-Security-Policy: {csp[:160] or 'missing'}",
    )
    for name, value in (
        ("x-frame-options", "DENY"),
        ("x-content-type-options", "nosniff"),
        ("referrer-policy", "no-referrer"),
    ):
        actual = headers.get(name, "")
        results.check("Headers", actual.lower() == value.lower(), f"{name}: {actual or 'missing'}")


def check_analytics_gate(client: httpx.Client, base: str, results: Results) -> None:
    response = client.post(
        base + BEACON_PATH, json={"page": "?email=someone@example.com"}, timeout=30.0
    )
    results.check(
        "Analytics",
        response.status_code == 422,
        f"POST {BEACON_PATH} with a non-allowlisted page -> {response.status_code} "
        "(expected 422; nothing is counted)",
    )
    response = get(client, base + "/api/ops/analytics")
    detail = f"GET /api/ops/analytics without a key -> {response.status_code}"
    if response.status_code == 503:
        results.warn("Analytics", detail + ": no operator key is configured on this deployment")
    else:
        results.check("Analytics", response.status_code == 401, detail + " (expected 401)")


class LinkParser(HTMLParser):
    """Collect link-like URLs from anchors, assets, and social metadata."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in ("a", "link", "img", "script"):
            for attribute in ("href", "src"):
                if values.get(attribute):
                    self.links.append(str(values[attribute]))
        meta_name = values.get("property") or values.get("name") or ""
        if tag == "meta" and meta_name in ("og:image", "og:url", "twitter:image"):
            if values.get("content"):
                self.links.append(str(values["content"]))


def check_links(
    client: httpx.Client, base: str, canonical: str, pages: dict[str, str], results: Results
) -> None:
    base_parts = urlsplit(base)
    canonical_host = urlsplit(canonical).netloc if canonical else base_parts.netloc
    sources: dict[str, str] = {}
    for page_path, html in pages.items():
        parser = LinkParser()
        parser.feed(html)
        for raw in parser.links:
            if raw.startswith(("#", "mailto:", "javascript:", "data:")):
                continue
            url = urljoin(base + page_path, raw).split("#", 1)[0]
            parts = urlsplit(url)
            if parts.netloc == canonical_host != base_parts.netloc:
                # Canonical links must resolve on the site under test.
                parts = parts._replace(scheme=base_parts.scheme, netloc=base_parts.netloc)
                url = urlunsplit(parts)
            sources.setdefault(url, page_path)
    broken: list[str] = []
    blocked: list[str] = []
    for url, source in sorted(sources.items()):
        internal = urlsplit(url).netloc == base_parts.netloc
        try:
            status: int | str = get(client, url, follow=True).status_code
        except httpx.HTTPError as error:
            status = type(error).__name__
        if isinstance(status, int) and status < 400:
            continue
        if not internal and status in (403, 429):
            blocked.append(f"{url} ({status})")
        else:
            broken.append(f"{url} ({status}, linked from {source})")
    for item in broken:
        results.check("Links", False, f"broken: {item}")
    if blocked:
        results.warn("Links", "external site refused an automated check: " + ", ".join(blocked))
    if not broken:
        internal_count = sum(1 for url in sources if urlsplit(url).netloc == base_parts.netloc)
        results.check(
            "Links",
            True,
            f"all {len(sources) - len(blocked)} checked links resolve "
            f"({internal_count} on this site, the rest external) across {', '.join(pages)}",
        )


def check_server_speed(client: httpx.Client, base: str, results: Results) -> None:
    for path in ("/", "/api/ready"):
        first_byte: list[float] = []
        complete: list[float] = []
        for _ in range(5):
            started = time.perf_counter()
            with client.stream("GET", base + path, timeout=30.0) as response:
                headers_at = time.perf_counter()
                response.read()
            finished = time.perf_counter()
            first_byte.append((headers_at - started) * 1000)
            complete.append((finished - started) * 1000)
        results.info(
            "Server speed",
            f"{path}: median {median(first_byte):.0f} ms to first byte, "
            f"{median(complete):.0f} ms complete (5 warm requests)",
        )


def check_browser(base: str, insecure: bool, results: Results) -> None:
    """Layout and consent checks in Chromium. Imported lazily: HTTP-only runs need no browser."""
    from playwright.sync_api import Browser, Page, Route, sync_playwright

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    def open_page(browser: Browser, width: int, height: int) -> tuple[Page, list[str]]:
        context = browser.new_context(
            viewport={"width": width, "height": height},
            service_workers="block",
            ignore_https_errors=insecure,
        )
        page = context.new_page()
        beacons: list[str] = []

        def intercept(route: Route) -> None:
            # Answer the beacon locally so production analytics are never incremented.
            beacons.append(route.request.method)
            route.fulfill(status=204, body="")

        page.route(f"**{BEACON_PATH}", intercept)
        return page, beacons

    def load(page: Page, path: str) -> None:
        page.goto(base + path, wait_until="networkidle", timeout=90_000)

    def overflow(page: Page) -> int:
        return int(page.evaluate("document.documentElement.scrollWidth - window.innerWidth"))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for width, height in ((1440, 1000), (390, 844), (320, 700)):
                page, beacons = open_page(browser, width, height)
                load(page, "/")
                page.wait_for_function(
                    "() => document.querySelectorAll('#modelsel button[data-m]').length >= 3",
                    timeout=30_000,
                )
                home_overflow = overflow(page)
                choices = page.locator("#modelsel button[data-m]")
                visible = sum(1 for i in range(choices.count()) if choices.nth(i).is_visible())
                banner = page.get_by_role("button", name="Allow analytics").is_visible()
                page.screenshot(path=str(EVIDENCE_DIR / f"home-{width}.png"), full_page=True)
                load(page, "/privacy")
                legal_overflow = overflow(page)
                page.screenshot(path=str(EVIDENCE_DIR / f"privacy-{width}.png"), full_page=True)
                page.context.close()
                results.check(
                    "Layout",
                    home_overflow <= 0 and legal_overflow <= 0 and visible == 3,
                    f"{width}px: horizontal overflow {max(home_overflow, 0)}px on home, "
                    f"{max(legal_overflow, 0)}px on privacy; {visible}/3 model choices visible",
                )
                results.check(
                    "Consent",
                    banner and not beacons,
                    f"{width}px: consent banner shown; {len(beacons)} analytics beacons "
                    "before a choice",
                )
            for choice, stored_value in (("Reject optional", "no"), ("Allow analytics", "yes")):
                page, beacons = open_page(browser, 390, 844)
                load(page, "/")
                before = len(beacons)
                page.get_by_role("button", name=choice).click()
                page.wait_for_timeout(2_000)
                stored = page.evaluate(f"localStorage.getItem('{CONSENT_KEY}')")
                page.reload(wait_until="networkidle", timeout=90_000)
                page.wait_for_timeout(2_000)
                banner_again = page.get_by_role("button", name="Allow analytics").is_visible()
                page.context.close()
                sent = len(beacons) - before
                expected_sent = sent == 0 if stored_value == "no" else sent >= 1
                results.check(
                    "Consent",
                    before == 0 and stored == stored_value and expected_sent and not banner_again,
                    f"'{choice}': stored {stored!r}, {sent} beacon(s) afterwards "
                    f"({'none expected' if stored_value == 'no' else 'at least one expected'}), "
                    f"banner {'reappeared' if banner_again else 'stayed hidden'} after reload",
                )
        finally:
            browser.close()


def check_browser_speed(base: str, results: Results) -> None:
    output = EVIDENCE_DIR / "page-speed.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "check_page_speed.py"),
            "--base-url",
            base,
            "--runs",
            "3",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout).strip().splitlines()[-1:]
        results.check("Browser speed", False, f"page-speed run failed: {' '.join(tail)}")
        return
    report = json.loads(output.read_text(encoding="utf-8"))
    for width, data in report["viewports"].items():
        m = data["median"]
        results.info(
            "Browser speed",
            f"{width}px median of 3 fresh visits: TTFB {m['ttfb_ms']:.0f} ms, "
            f"FCP {m['fcp_ms']:.0f} ms, LCP {m['lcp_ms']:.0f} ms, load {m['load_ms']:.0f} ms, "
            f"HTML {m['html_wire_bytes'] / 1024:.1f} KB on the wire",
        )


def pause(seconds: int) -> None:
    """Space the phases out so the site's per-client rate limit is never the result."""
    print(f"... pausing {seconds}s between phases", flush=True)
    time.sleep(seconds)


def publish(results: Results, deployed: bool) -> None:
    """Annotations (one per category, <= 10 per type), a job summary, and a step output."""
    if os.getenv("GITHUB_ACTIONS") != "true":
        return
    by_category: dict[str, list[tuple[str, str]]] = {}
    for category, status, detail in results.items:
        by_category.setdefault(category, []).append((status, detail))
    for category, entries in by_category.items():
        statuses = {status for status, _ in entries}
        level = "error" if "FAIL" in statuses else "warning" if "WARN" in statuses else "notice"
        shown = [detail for status, detail in entries if status in ("FAIL", "WARN")]
        message = " | ".join(shown or [detail for _, detail in entries])
        message = message if len(message) <= 1500 else message[:1497] + "..."
        escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::{level} title=Live {category}::{escaped}", flush=True)
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        lines = ["## Live site checks", "", "| Check | Result | Detail |", "|---|---|---|"]
        for category, status, detail in results.items:
            cell = detail.replace("|", "\\|")
            lines.append(f"| {category} | {status} | {cell} |")
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"deployed={'true' if deployed else 'false'}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url", default="https://chaoshire.onrender.com")
    parser.add_argument(
        "--canonical-origin",
        help="origin the site should redirect and link to (default: the base URL if HTTPS)",
    )
    parser.add_argument(
        "--http-url", help="plain-HTTP origin for the redirect check (default: base with http://)"
    )
    parser.add_argument(
        "--wait-minutes",
        type=float,
        default=0,
        help="wait up to this long for the live build to match this checkout",
    )
    parser.add_argument("--skip-browser", action="store_true", help="HTTP checks only")
    parser.add_argument(
        "--insecure", action="store_true", help="skip TLS verification (local self-signed only)"
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    canonical = (args.canonical_origin or (base if base.startswith("https://") else "")).rstrip("/")
    results = Results()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, verify=not args.insecure) as client:
        deployed = wait_for_build(client, base, expected_build(), args.wait_minutes, results)
        if deployed:
            responses = check_routes(client, base, canonical, results)
            check_https(client, base, args.http_url, canonical, results)
            check_headers(responses["/privacy"], base.startswith("https://"), results)
            check_analytics_gate(client, base, results)
            pages = {p: responses[p].text for p in LINK_PAGES if responses[p].status_code == 200}
            check_links(client, base, canonical, pages, results)
            check_server_speed(client, base, results)
    if deployed and not args.skip_browser:
        pause(30)
        check_browser(base, args.insecure, results)
        if not args.insecure:
            pause(30)
            check_browser_speed(base, results)
    publish(results, deployed)
    return 1 if results.failed else 0


if __name__ == "__main__":
    sys.exit(main())
