"""Capture deterministic before/after redesign screenshots from a running app.

The redesign review in ``docs/operations/WEBSITE-READINESS.md`` quotes four
images::

    docs/portfolio/assets/redesign-before-desktop.png
    docs/portfolio/assets/redesign-after-desktop.png
    docs/portfolio/assets/redesign-before-mobile.png
    docs/portfolio/assets/redesign-after-mobile.png

Both labels are produced by this one script so the pair differs only in the
markup and stylesheet, never in capture settings. Determinism comes from:

* the same readiness gate as ``capture_portfolio.py`` (reused, not copied), so
  a screenshot is never taken before ``/api/meta`` has rendered;
* a pre-seeded ``localStorage`` analytics choice, so the consent banner is
  already dismissed and cannot cover the masthead in one image but not the other;
* service workers blocked, reduced-motion emulation, and a fixed
  ``device_scale_factor`` so the pixels do not depend on capture order.

Usage
-----
    python -m uvicorn backend:app --port 8000 &
    python scripts/capture_redesign.py --label before
    # ... change the markup/stylesheet ...
    python scripts/capture_redesign.py --label after
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture_portfolio import wait_for_landing  # noqa: E402

#: (suffix, width, height) — the two widths the layout checks also use.
VIEWS = (("desktop", 1440, 1000), ("mobile", 390, 844))

#: Dismiss the optional-analytics banner before first paint so the masthead is
#: visible in both images. 'no' fires no beacon, matching the documented default.
CONSENT_INIT = "localStorage.setItem('chaoshire-analytics-consent-v1','no');"


def capture(
    base_url: str, output: Path, label: str, chromium_executable: Path | None
) -> list[Path]:
    written: list[Path] = []
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=chromium_executable)
        for suffix, width, height in VIEWS:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
                reduced_motion="reduce",
                service_workers="block",
            )
            context.add_init_script(CONSENT_INIT)
            page = context.new_page()
            page.goto(base_url, wait_until="networkidle")
            wait_for_landing(page, base_url)
            assert page.locator("#consent-banner").is_hidden(), "consent banner covers the masthead"
            target = output / f"redesign-{label}-{suffix}.png"
            page.screenshot(path=target, full_page=True)
            written.append(target)
            context.close()
        browser.close()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="docs/portfolio/assets")
    parser.add_argument("--label", required=True, choices=("before", "after"))
    parser.add_argument("--chromium-executable", type=Path, help="Use a locally installed Chromium")
    args = parser.parse_args()

    for path in capture(args.base_url, Path(args.output), args.label, args.chromium_executable):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
