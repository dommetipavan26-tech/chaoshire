"""Capture deterministic portfolio screenshots from a running (or freshly started) ChaosHire.

Usage:
    python scripts/capture_portfolio.py                      # starts a private server
    python scripts/capture_portfolio.py --base-url https://chaoshire.onrender.com

The demonstration is seeded, so the same build always produces the same numbers.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SHOTS = [
    ("landing-desktop.png", {"width": 1440, "height": 1000}),
    ("landing-mobile.png", {"width": 390, "height": 844}),
    ("dashboard-desktop.png", {"width": 1440, "height": 1000}),
    ("chaos-lab-desktop.png", {"width": 1440, "height": 1000}),
    ("release-gate-desktop.png", {"width": 1440, "height": 1000}),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def wait_for_health(url: str, seconds: int = 40) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    raise RuntimeError(f"ChaosHire did not become healthy at {url}")


def start_server(port: int) -> subprocess.Popen:
    database = Path(tempfile.mkdtemp(prefix="chaoshire-shots-")) / "chaoshire.db"
    environment = {**os.environ, "PYTHONPATH": str(ROOT), "CHAOSHIRE_DB_PATH": str(database)}
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
    wait_for_health(f"http://127.0.0.1:{port}")
    return process


def capture(base_url: str, output: Path, full_page: bool) -> list[str]:
    from playwright.sync_api import sync_playwright

    written: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        for name, viewport in SHOTS:
            context = browser.new_context(viewport=viewport, device_scale_factor=2)
            page = context.new_page()
            page.goto(base_url, wait_until="domcontentloaded")

            if name.startswith("landing"):
                page.wait_for_selector("#landing-main")
            elif name == "dashboard-desktop.png":
                page.get_by_role("button", name="Explore dashboard").click()
                page.locator("#tab-overview .grade-ring").wait_for()
            elif name == "chaos-lab-desktop.png":
                page.get_by_role("button", name="Explore dashboard").click()
                page.locator("#tab-overview .grade-ring").wait_for()
                page.locator('#tabs button[data-t="chaos"]').click()
                page.locator("#runchaos").click()
                page.locator("#chaosout .card").first.wait_for()
            elif name == "release-gate-desktop.png":
                page.get_by_role("button", name="Explore dashboard").click()
                page.locator("#tab-overview .grade-ring").wait_for()
                page.locator('#tabs button[data-t="compare"]').click()
                page.locator("#tab-compare .stat-num").first.wait_for()
                page.locator("#rungate").click()
                page.locator("#gateout .chip").first.wait_for()

            page.wait_for_timeout(250)  # let fonts and bars settle
            target = output / name
            page.screenshot(path=str(target), full_page=full_page)
            written.append(str(target))
            context.close()
        browser.close()
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="", help="existing deployment to photograph")
    parser.add_argument("--output", default="docs/assets", help="where to write PNG files")
    parser.add_argument(
        "--viewport-only",
        action="store_true",
        help="capture the visible viewport instead of the full page",
    )
    args = parser.parse_args(argv)

    output = ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)

    if args.base_url:
        base_url = args.base_url.rstrip("/")
        process = None
    else:
        port = free_port()
        process = start_server(port)
        base_url = f"http://127.0.0.1:{port}"

    try:
        for path in capture(base_url, output, full_page=not args.viewport_only):
            print(f"wrote {path}")
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
