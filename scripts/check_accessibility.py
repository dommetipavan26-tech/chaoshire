"""Audit rendered pages with locally supplied axe-core and Playwright Chromium.

Download axe-core separately (not served to visitors or checked into Git), then:
  python scripts/check_accessibility.py --axe-path /tmp/axe.min.js

Axe catches many contrast, name, label, and semantic problems. Manual keyboard,
screen-reader, and physical-device checks are still required.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]
PAGES = {
    "Home": ("/", None),
    "Dashboard": ("/", "Fairness Dashboard"),
    "Upload": ("/", "Upload Your Model"),
    "Appeals": ("/", "Appeals Portal"),
    "Privacy": ("/privacy", None),
    "Terms": ("/terms", None),
    "404": ("/page-that-does-not-exist", None),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--axe-path", type=Path, required=True)
    parser.add_argument("--chromium-executable", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/generated/accessibility.json"))
    args = parser.parse_args()
    source = args.axe_path.read_text(encoding="utf-8")
    checks: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium_executable)
        for width in (1440, 390, 320):
            context = browser.new_context(
                viewport={"width": width, "height": 900}, service_workers="block"
            )
            for name, (route, tab) in PAGES.items():
                page = context.new_page()
                page.goto(f"{args.base_url.rstrip('/')}{route}", wait_until="networkidle")
                if tab:
                    page.get_by_role("button", name=tab).click()
                # Script tags are correctly blocked by the site's CSP. DevTools
                # evaluation runs the local audit without weakening that policy.
                page.evaluate(source)
                result = page.evaluate(
                    """async tags => {
                        const audit=await axe.run(document,{runOnly:{type:'tag',values:tags}});
                        return {violations:audit.violations.map(v=>({id:v.id,impact:v.impact,
                          targets:v.nodes.map(n=>n.target)})),
                          incomplete:audit.incomplete.map(v=>({id:v.id,
                            targets:v.nodes.map(n=>n.target)}))};
                    }""",
                    TAGS,
                )
                checks.append({"width": width, "page": name, **result})
                page.close()
            context.close()
        browser.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    violations = [check for check in checks if check["violations"]]
    for check in checks:
        print(f"{check['width']}px {check['page']}: {len(check['violations'])} violations")
    unresolved = [check for check in checks if check["incomplete"]]
    print(
        f"Saved {args.output} ({len(checks)} audits, {len(violations)} failing pages, "
        f"{len(unresolved)} pages with untestable elements for manual review)"
    )
    if violations:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
