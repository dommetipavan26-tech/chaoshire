"""Real-browser checks for the recruiter landing experience."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager

from playwright.sync_api import sync_playwright


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


def test_landing_ctas_mobile_layout_and_keyboard_navigation() -> None:
    with running_app() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        page.goto(url, wait_until="networkidle")

        page.get_by_role("heading", name="Stress-test hiring AI").wait_for()
        for proof in ("65", "96.83%", "5", "v0.21.0"):
            assert page.get_by_text(proof, exact=True).is_visible()
        assert page.get_by_text("does not make hiring decisions", exact=False).is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert page.locator("#modelsel").is_visible()

        page.get_by_role("button", name="MeritFirst v2").click()
        assert page.locator("#tab-welcome").is_visible()
        page.locator("#home-score", has_text="86 / B").wait_for()
        assert page.locator("#home-gender").inner_text() == "0"
        assert page.locator("#home-community").inner_text() == "0"
        assert page.locator("#home-resilience").inner_text() == "100"

        page.get_by_role("button", name="LegacyCorp Screen v1").click()
        page.locator("#home-score", has_text="42 / F").wait_for()
        assert page.locator("#home-gender").inner_text() == "169"
        assert page.locator("#home-community").inner_text() == "111"
        assert page.locator("#home-resilience").inner_text() == "30"

        page.get_by_role("button", name="Explore dashboard").click()
        page.get_by_role("button", name="MeritFirst v2").click()
        page.locator("#tab-overview .grade-ring b", has_text="86").wait_for()
        assert page.locator("#tab-overview").is_visible()
        page.get_by_role("button", name="Home").click()
        assert page.locator("#modelsel").is_visible()
        assert page.locator("#home-score").inner_text() == "86 / B"

        demo = page.get_by_role("button", name="Start the 3-minute demo")
        demo.focus()
        page.keyboard.press("Enter")
        page.get_by_role("heading", name="From hidden hiring bias to a release decision").wait_for()
        assert page.locator("#tab-demo").is_visible()

        home = page.get_by_role("button", name="Home")
        home.focus()
        page.keyboard.press("Enter")
        page.get_by_role("button", name="Explore dashboard").click()
        page.get_by_text("Fairness Risk Score", exact=True).wait_for()
        assert page.locator("#tab-overview").is_visible()
        browser.close()
