"""Real-browser checks for the recruiter landing experience.

Two things are deliberately asserted against the running server rather than
against literals in this file:

* the landing-page proof strip, which is served from ``/api/meta`` so it cannot
  drift from ``chaoshire.__version__`` (it used to hardcode ``v0.21.0`` while
  the package said ``0.22.0``, and this test asserted the stale string);
* the reference-model score card, which is served from ``/api/audit``.

The XSS check at the bottom is the regression test for the attribute-context
escape hole: an uploaded CSV group value containing ``"`` used to break out of
``title="${esc(g.group)}"`` on the intersections card.
"""

from __future__ import annotations

import csv
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

XSS_PAYLOAD = '"><img src=x onerror="window.__xss=1"><b>pwned</b>'


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def running_app():
    port = free_port()
    with tempfile.TemporaryDirectory() as temp_dir:
        env = {**os.environ, "CHAOSHIRE_DB_PATH": f"{temp_dir}/browser.db"}
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend:app", "--port", str(port)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(f"{url}/api/health", timeout=1)
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local ChaosHire server did not start")
            yield url
        finally:
            process.terminate()
            process.wait(timeout=10)


def api(url: str, path: str) -> dict:
    with urllib.request.urlopen(f"{url}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def test_landing_ctas_mobile_layout_and_keyboard_navigation() -> None:
    with running_app() as url, sync_playwright() as playwright:
        build = api(url, "/api/meta")["build"]
        models = {model["id"]: model for model in api(url, "/api/meta")["models"]}

        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        page.goto(url, wait_until="networkidle")

        page.get_by_role("heading", name="Stress-test hiring AI").wait_for()

        # Proof strip comes from the API, so compare against the API too.
        assert page.locator("#proof-version").inner_text() == f"v{build['version']}"
        assert page.locator("#proof-tests").inner_text() == str(build["automated_tests"])
        assert page.locator("#proof-coverage").inner_text() == build["package_coverage"]
        assert page.locator("#proof-experiments").inner_text() == str(build["chaos_experiments"])

        assert page.get_by_text("does not make hiring decisions", exact=False).is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert page.locator("#modelsel").is_visible()
        # Three reference models, including the one we actually trained.
        assert page.locator("#modelsel .mbtn").count() == len(models) == 3

        page.get_by_role("button", name=models["fair"]["title"]).click()
        assert page.locator("#tab-welcome").is_visible()
        page.locator("#home-score", has_text="84 / B").wait_for()
        assert page.locator("#home-gender").inner_text() == "0"
        assert page.locator("#home-community").inner_text() == "0"
        assert page.locator("#home-resilience").inner_text() == "100"

        page.get_by_role("button", name=models["trained"]["title"]).click()
        page.locator("#home-score", has_text="66 / C").wait_for()
        # The most interesting result in the project: perfect counterfactual
        # resilience alongside a failing disparate impact.
        assert page.locator("#home-resilience").inner_text() == "100"

        page.get_by_role("button", name=models["legacy"]["title"]).click()
        page.locator("#home-score", has_text="32 / F").wait_for()
        assert page.locator("#home-gender").inner_text() == "169"
        assert page.locator("#home-community").inner_text() == "111"
        assert page.locator("#home-resilience").inner_text() == "30"

        page.get_by_role("button", name="Explore dashboard").click()
        page.get_by_role("button", name=models["fair"]["title"]).click()
        page.locator("#tab-overview .grade-ring b", has_text="84").wait_for()
        assert page.locator("#tab-overview").is_visible()
        page.get_by_role("button", name="Home").click()
        assert page.locator("#modelsel").is_visible()
        assert page.locator("#home-score").inner_text() == "84 / B"

        demo = page.get_by_role("button", name="Start the 3-minute demo")
        demo.focus()
        page.keyboard.press("Enter")
        page.get_by_role("heading", name="From hidden hiring bias to a release decision").wait_for()
        assert page.locator("#tab-demo").is_visible()
        # Step 6 is the statutory refusal; it must name the statute.
        assert page.get_by_text("42 U.S.C. § 2000e-2(l)", exact=False).first.is_visible()

        home = page.get_by_role("button", name="Home")
        home.focus()
        page.keyboard.press("Enter")
        page.get_by_role("button", name="Explore dashboard").click()
        page.get_by_text("Fairness Risk Score", exact=True).wait_for()
        assert page.locator("#tab-overview").is_visible()
        browser.close()


def test_mitigation_tab_refuses_per_group_thresholds() -> None:
    with running_app() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")

        page.get_by_role("button", name="Mitigations").click()
        # The one-click set is exactly the two lawful controls.
        assert page.locator(".mit-check").count() == 2
        assert page.locator("#m_blind").is_visible()
        assert page.locator("#m_proxy").is_visible()
        assert page.locator("#m_calibrate").count() == 0

        card = page.locator("#contrastcard")
        assert card.is_visible()
        assert "42 U.S.C. § 2000e-2(l)" in card.inner_text()
        assert "unlawful employment practice" in card.inner_text()

        # Unacknowledged: the server refuses and quotes the statute back.
        page.locator("#runcontrast").click()
        page.locator("#contrastout .err").wait_for()
        assert "2000e-2(l)" in page.locator("#contrastout").inner_text()

        # Acknowledged: runs, and is labelled research-only rather than applied.
        page.locator("#m_contrast_ack").check()
        page.locator("#runcontrast").click()
        page.get_by_text("prohibited in US employment testing", exact=False).wait_for()
        assert "research only" in page.locator("#contrastout").inner_text()
        browser.close()


def test_uploaded_group_values_cannot_escape_the_attribute_context() -> None:
    """Regression test for the ``title="${esc(g.group)}"`` breakout."""
    with running_app() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")

        # The escaping helper itself must cover both markup and attribute quotes.
        assert page.evaluate("""esc('"><b>x</b>')""") == "&quot;&gt;&lt;b&gt;x&lt;/b&gt;"
        assert page.evaluate("""esc("it's")""") == "it&#39;s"
        assert page.evaluate("""esc('a`b')""") == "a&#96;b"

        # A nonce CSP means an injected inline handler cannot run even if the
        # escaping regressed; assert both layers.
        with urllib.request.urlopen(f"{url}/api/health", timeout=30) as response:
            csp = response.headers["content-security-policy"]
        assert "script-src 'self' 'nonce-" in csp
        assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]

        # Written through the csv module: the payload contains quote characters
        # that would otherwise be parsed as CSV quoting rather than as data.
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["gender", "ethnicity", "decision", "qualified"])
        for decision, qualified in [(1, 1)] * 20 + [(0, 0)] * 20:
            writer.writerow([XSS_PAYLOAD, "G2", decision, qualified])
        for decision, qualified in [(1, 1)] * 20 + [(0, 0)] * 20:
            writer.writerow(["M", "G1", decision, qualified])
        csv_path = Path(tempfile.gettempdir()) / "chaoshire-xss.csv"
        csv_path.write_text(buffer.getvalue(), encoding="utf-8")

        page.get_by_role("button", name="Upload Your Model").click()
        page.locator("#auditname").fill("XSS probe")
        page.locator("#csvfile").set_input_files(str(csv_path))
        page.locator("#attrs").fill("gender,ethnicity")
        page.locator("#upbtn").click()
        page.get_by_text("not published", exact=False).wait_for()
        page.locator("#viewup").click()
        page.locator("#tab-overview .grade-ring").wait_for()

        # Nothing executed, and no element was smuggled into the DOM.
        assert page.evaluate("window.__xss === undefined")
        assert page.locator("#tab-overview img").count() == 0
        assert page.locator("#tab-overview b", has_text="pwned").count() == 0
        # The payload survives as inert, visible text instead.
        assert "<b>pwned</b>" in page.locator("#tab-overview").inner_text()
        csv_path.unlink(missing_ok=True)
        browser.close()
