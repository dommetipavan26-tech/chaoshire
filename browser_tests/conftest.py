"""Live-browser test fixtures: a real ChaosHire server plus Chromium.

Playwright is optional for the core suite. When it (or its Chromium build) is missing,
these tests skip with an actionable message instead of failing, so `python -m pytest`
stays usable on a minimal checkout.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

pytest.importorskip("playwright.sync_api", reason="python -m pip install -r requirements-browser.txt")

from playwright.sync_api import Error as PlaywrightError  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

HEALTH_PATH = "/api/health"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="session")
def base_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Use an already-running ChaosHire when told to, otherwise start a private one."""
    override = os.environ.get("CHAOSHIRE_BASE_URL")
    if override:
        yield override.rstrip("/")
        return

    port = _free_port()
    database = tmp_path_factory.mktemp("browser-state") / "chaoshire.db"
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "CHAOSHIRE_DB_PATH": str(database),
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 40
    try:
        while time.time() < deadline:
            if process.poll() is not None:
                pytest.fail(f"ChaosHire exited with {process.returncode} before becoming healthy.")
            try:
                with urllib.request.urlopen(url + HEALTH_PATH, timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                time.sleep(0.25)
        else:
            pytest.fail("ChaosHire did not report healthy within 40 seconds.")
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive cleanup
            process.kill()


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def browser(playwright_instance):
    executable = shutil.which("chromium") or shutil.which("chromium-browser")
    try:
        if executable:
            launched = playwright_instance.chromium.launch(executable_path=executable)
        else:
            launched = playwright_instance.chromium.launch(args=["--no-sandbox"])
    except PlaywrightError as error:
        pytest.skip(
            "Chromium is unavailable for Playwright. Run: python -m playwright install chromium "
            f"({str(error).splitlines()[0]})"
        )
    yield launched
    launched.close()


@pytest.fixture
def context(browser, request: pytest.FixtureRequest):
    viewport = getattr(request, "param", {"width": 1280, "height": 900})
    created = browser.new_context(viewport=viewport, device_scale_factor=1)
    created.set_default_timeout(15_000)
    yield created
    created.close()


@pytest.fixture
def page(context, base_url: str):
    opened = context.new_page()
    opened.goto(base_url, wait_until="domcontentloaded")
    return opened


@pytest.fixture
def dashboard(page, base_url: str):
    """Enter the application the same way a visitor does: click, then wait for data."""
    page.get_by_role("button", name="Explore dashboard").click()
    page.wait_for_url(f"{base_url}#overview")
    page.locator("#tab-overview .grade-ring").wait_for()
    return page
