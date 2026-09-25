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

from playwright.sync_api import expect, sync_playwright

XSS_PAYLOAD = '"><img src=x onerror="window.__xss=1"><b>pwned</b>'


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def launch_chromium(playwright):
    """Use CHAOSHIRE_CHROMIUM when Playwright's own browser download is unavailable."""
    path = os.environ.get("CHAOSHIRE_CHROMIUM")
    if path:
        return playwright.chromium.launch(executable_path=path)
    return playwright.chromium.launch()


@contextmanager
def running_app():
    port = free_port()
    with tempfile.TemporaryDirectory() as temp_dir:
        env = {**os.environ, "CHAOSHIRE_DB_PATH": f"{temp_dir}/browser.db"}
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend:app", "--port", str(port)],
            cwd=Path(__file__).resolve().parents[2],
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

        browser = launch_chromium(playwright)
        page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        page.goto(url, wait_until="networkidle")

        page.get_by_role("heading", name="Stress-test hiring AI").wait_for()

        # Proof strip comes from the API, so compare against the API too. Every
        # one of these uses expect() rather than inner_text(): the strip is filled
        # by an async /api/meta fetch, and a bare inner_text() read does not retry,
        # so it races the fetch and reads the em-dash placeholder.
        expect(page.locator("#proof-version")).to_have_text(f"v{build['version']}")
        expect(page.locator("#proof-tests")).to_have_text(str(build["automated_tests"]))
        expect(page.locator("#proof-coverage")).to_have_text(build["package_coverage"])
        expect(page.locator("#proof-experiments")).to_have_text(str(build["chaos_experiments"]))

        expect(page.get_by_text("does not make hiring decisions", exact=False)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        expect(page.get_by_role("group", name="Audit model selector")).to_be_visible()
        # Three reference models, including the one we actually trained.
        assert len(models) == 3
        expect(page.locator("#modelsel .mbtn")).to_have_count(len(models))

        page.get_by_role("button", name=models["fair"]["title"]).click()
        expect(page.locator("#tab-welcome")).to_be_visible()
        expect(page.locator("#home-score")).to_have_text("84 / B")
        expect(page.locator("#home-gender")).to_have_text("0")
        expect(page.locator("#home-community")).to_have_text("0")
        expect(page.locator("#home-resilience")).to_have_text("100")

        page.get_by_role("button", name=models["trained"]["title"]).click()
        expect(page.locator("#home-score")).to_have_text("66 / C")
        # The most interesting result in the project: perfect counterfactual
        # resilience alongside a failing disparate impact.
        expect(page.locator("#home-resilience")).to_have_text("100")

        page.get_by_role("button", name=models["legacy"]["title"]).click()
        expect(page.locator("#home-score")).to_have_text("32 / F")
        expect(page.locator("#home-gender")).to_have_text("169")
        expect(page.locator("#home-community")).to_have_text("111")
        expect(page.locator("#home-resilience")).to_have_text("30")

        page.get_by_role("button", name="Measure", exact=True).click()
        page.get_by_role("button", name="Fairness Dashboard", exact=True).click()
        expect(page.get_by_role("heading", name="Fairness Dashboard", level=2)).to_be_visible()
        page.get_by_role("button", name=models["fair"]["title"]).click()
        expect(page.locator("#tab-overview .grade-ring b", has_text="84")).to_be_visible()
        expect(page.locator("#tab-overview")).to_be_visible()
        page.get_by_role("button", name="Home").click()
        expect(page.locator("#modelsel")).to_be_visible()
        expect(page.locator("#home-score")).to_have_text("84 / B")

        demo = page.get_by_role("button", name="Start the 3-minute demo")
        demo.focus()
        page.keyboard.press("Enter")
        page.get_by_role("heading", name="From hidden hiring bias to a release decision").wait_for()
        expect(page.locator("#tab-demo")).to_be_visible()
        # Step 6 is the statutory refusal; it must name the statute. Scoped to the
        # demo tab: the phrase also appears in the hidden Mitigations tab, and an
        # unscoped .first resolves to that one and never becomes visible.
        expect(page.locator("#tab-demo")).to_contain_text("42 U.S.C. § 2000e-2(l)")

        home = page.get_by_role("button", name="Home")
        home.focus()
        page.keyboard.press("Enter")
        page.get_by_role("button", name="Measure", exact=True).click()
        page.get_by_role("button", name="Fairness Dashboard", exact=True).click()
        # Scoped to the overview tab and matched as a substring: the score line now
        # reads "Fairness Risk Score · 71.3 of 85 measurable points, normalised to
        # 100", so there is no element whose entire text is the bare label. Asserting
        # the basis text here also proves the denominator disclosure reached the UI
        # rather than only the JSON payload.
        expect(page.locator("#tab-overview")).to_be_visible()
        expect(page.locator("#tab-overview")).to_contain_text("Fairness Risk Score")
        expect(page.locator("#tab-overview")).to_contain_text(
            "measurable points, normalised to 100"
        )
        browser.close()


def test_mitigation_tab_refuses_per_group_thresholds() -> None:
    with running_app() as url, sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")

        page.get_by_role("button", name="Review", exact=True).click()
        page.get_by_role("button", name="Mitigations", exact=True).click()
        # The one-click set is exactly the two lawful controls.
        expect(page.locator(".mit-check")).to_have_count(2)
        expect(page.locator("#m_blind")).to_be_visible()
        expect(page.locator("#m_proxy")).to_be_visible()
        expect(page.locator("#m_calibrate")).to_have_count(0)

        card = page.locator("#contrastcard")
        expect(card).to_be_visible()
        assert "42 U.S.C. § 2000e-2(l)" in card.inner_text()
        assert "unlawful employment practice" in card.inner_text()

        # Unacknowledged: the server refuses and quotes the statute back.
        page.locator("#runcontrast").click()
        expect(page.locator("#contrastout .err")).to_be_visible()
        assert "2000e-2(l)" in page.locator("#contrastout").inner_text()

        # Acknowledged: runs, and is labelled research-only rather than applied.
        page.locator("#m_contrast_ack").check()
        page.locator("#runcontrast").click()
        # Two chips render here ("research only" and "prohibited in US employment
        # testing"), and the acknowledgement label above repeats the phrase, so
        # wait on the container and assert on its text instead of a bare locator.
        page.locator("#contrastout .chip").first.wait_for()
        contrast_out = page.locator("#contrastout").inner_text()
        assert "research only" in contrast_out
        assert "prohibited in US employment testing" in contrast_out
        assert "42 U.S.C. § 2000e-2(l)" in contrast_out
        browser.close()


def test_uploaded_group_values_cannot_escape_the_attribute_context() -> None:
    """Regression test for the ``title="${esc(g.group)}"`` breakout."""
    with running_app() as url, sync_playwright() as playwright:
        browser = launch_chromium(playwright)
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

        page.get_by_role("button", name="Your data", exact=True).click()
        page.get_by_role("button", name="Upload Your Model", exact=True).click()
        page.locator("#auditname").fill("XSS probe")
        page.locator("#csvfile").set_input_files(str(csv_path))
        page.locator("#attrs").fill("gender,ethnicity")
        page.locator("#upbtn").click()
        # Scoped to the result container: the upload tab's static privacy notice
        # and the platform note both say "not published" too, so an unscoped
        # get_by_text() resolves to several elements and trips strict mode.
        page.locator("#upout .chip").wait_for()
        upload_out = page.locator("#upout").inner_text()
        assert "not published" in upload_out
        assert "XSS probe" in upload_out
        page.locator("#viewup").click()
        expect(page.locator("#tab-overview .grade-ring").first).to_be_visible()

        # Nothing executed, and no element was smuggled into the DOM.
        assert page.evaluate("window.__xss === undefined")
        assert page.locator("#tab-overview img").count() == 0
        assert page.locator("#tab-overview b", has_text="pwned").count() == 0
        # The payload survives as inert, visible text instead.
        assert "<b>pwned</b>" in page.locator("#tab-overview").inner_text()
        csv_path.unlink(missing_ok=True)
        browser.close()


def test_mobile_consent_and_form_validation() -> None:
    """No analytics before opt-in; mobile choices and form errors stay accessible."""
    with running_app() as url, sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        page = browser.new_page(viewport={"width": 320, "height": 700})
        tracking: list[str] = []
        submissions: list[str] = []
        page.on(
            "request",
            lambda request: (
                tracking.append(request.url)
                if request.url.endswith("/api/analytics/view")
                else submissions.append(request.url)
                if request.url.endswith(("/api/appeals", "/api/upload"))
                else None
            ),
        )
        page.goto(url, wait_until="networkidle")

        expect(page.locator("#consent-banner")).to_be_visible()
        assert not tracking
        trained = page.locator('#modelsel button[data-m="trained"]').bounding_box()
        assert trained is not None
        assert trained["x"] >= 0 and trained["x"] + trained["width"] <= 320
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        expect(page.locator("#startdemo")).to_be_visible()
        page.locator("#startdemo").scroll_into_view_if_needed()
        assert page.locator("#startdemo").evaluate(
            "button => {const r=button.getBoundingClientRect();"
            "return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2) === button}"
        )  # The banner must never overlay the CTA, even on a 320px phone.
        page.get_by_role("button", name="Reject optional").click()
        expect(page.locator("#consent-banner")).to_be_hidden()
        assert page.evaluate("localStorage.getItem('chaoshire-analytics-consent-v1')") == "no"
        page.reload(wait_until="networkidle")
        expect(page.locator("#consent-banner")).to_be_hidden()
        assert not tracking

        page.get_by_role("button", name="Privacy settings").click()
        expect(page.locator("#consent-banner")).to_be_visible()
        with page.expect_response(
            lambda response: response.url.endswith("/api/analytics/view")
        ) as event:
            page.get_by_role("button", name="Allow analytics").click()
        assert event.value.status == 204
        assert page.evaluate("localStorage.getItem('chaoshire-analytics-consent-v1')") == "yes"
        expect(page.locator("#consent-banner")).to_be_hidden()

        page.get_by_role("button", name="Review", exact=True).click()
        page.get_by_role("button", name="Appeals Portal", exact=True).click()
        page.get_by_role("button", name="Submit appeal").click()
        expect(page.locator("#aout")).to_contain_text("Enter an application ID")
        page.locator("#acid").fill("C-1046")
        page.locator("#amsg").fill("   ")
        page.get_by_role("button", name="Submit appeal").click()
        expect(page.locator("#aout")).to_contain_text("Explain why this decision needs review")
        assert not submissions
        page.locator("#amsg").fill("Please review the synthetic decision")
        page.locator("#appeal-website").evaluate("node => node.value = 'https://bot.example'")
        with page.expect_response(lambda response: response.url.endswith("/api/appeals")) as event:
            page.get_by_role("button", name="Submit appeal").click()
        assert event.value.status == 422

        page.get_by_role("button", name="Your data", exact=True).click()
        page.get_by_role("button", name="Upload Your Model", exact=True).click()
        page.get_by_role("button", name="Validate & audit").click()
        expect(page.locator("#upout")).to_contain_text("Choose a CSV file first")
        page.locator("#csvfile").set_input_files(
            {"name": "not-csv.txt", "mimeType": "text/plain", "buffer": b"decision\n1"}
        )
        page.get_by_role("button", name="Validate & audit").click()
        expect(page.locator("#upout")).to_contain_text("Choose a .csv file")
        assert not any(url.endswith("/api/upload") for url in submissions)
        browser.close()
