"""Capture deterministic portfolio screenshots from a running ChaosHire app."""
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="docs/assets")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        desktop = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        desktop.goto(args.base_url, wait_until="networkidle")
        desktop.screenshot(path=output / "landing-desktop.png", full_page=True)
        desktop.get_by_role("button", name="Explore dashboard").click()
        desktop.get_by_text("Fairness Risk Score", exact=True).wait_for()
        desktop.screenshot(path=output / "dashboard-desktop.png", full_page=True)

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        mobile.goto(args.base_url, wait_until="networkidle")
        mobile.screenshot(path=output / "landing-mobile.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
