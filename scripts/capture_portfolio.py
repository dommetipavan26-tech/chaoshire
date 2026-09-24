"""Capture deterministic portfolio screenshots from a running ChaosHire app."""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright


def wait_for_landing(page: Page, base_url: str) -> None:
    """Fail rather than save a screenshot before the live model data has rendered."""
    response = page.request.get(f"{base_url.rstrip('/')}/api/meta")
    if not response.ok:
        raise RuntimeError(f"Could not load model metadata: HTTP {response.status}")
    meta = response.json()
    models = meta["models"]
    expected_ids = [model["id"] for model in models]
    if not {"legacy", "fair", "trained"}.issubset(expected_ids):
        raise RuntimeError(f"Expected all three reference models, got {expected_ids}")

    selector = page.locator("#modelsel button[data-m]")
    expect(selector).to_have_count(len(expected_ids))
    actual_ids = selector.evaluate_all("buttons => buttons.map(button => button.dataset.m)")
    if actual_ids != expected_ids:
        raise RuntimeError(
            f"Model selector does not match /api/meta: {actual_ids} != {expected_ids}"
        )
    for model in models:
        expect(page.locator(f'#modelsel button[data-m="{model["id"]}"]')).to_contain_text(
            model["title"]
        )

    build = meta["build"]
    expect(page.locator("#proof-version")).to_have_text(f"v{build['version']}")
    expect(page.locator("#proof-tests")).to_have_text(str(build["automated_tests"]))
    expect(page.locator("#proof-coverage")).to_have_text(build["package_coverage"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="docs/portfolio/assets")
    parser.add_argument("--chromium-executable", type=Path, help="Use a locally installed Chromium")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium_executable)
        desktop = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        desktop.goto(args.base_url, wait_until="networkidle")
        wait_for_landing(desktop, args.base_url)
        desktop.screenshot(path=output / "landing-desktop.png", full_page=True)
        desktop.get_by_role("button", name="Fairness Dashboard").click()
        expect(desktop.locator("#tab-overview")).to_contain_text("Fairness Risk Score")
        expect(desktop.locator("#tab-overview .grade-ring b")).to_have_text("32")
        desktop.screenshot(path=output / "dashboard-desktop.png", full_page=True)

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        mobile.goto(args.base_url, wait_until="networkidle")
        wait_for_landing(mobile, args.base_url)
        mobile.screenshot(path=output / "landing-mobile.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
