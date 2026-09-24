"""Measure real-browser local load timings without inventing a Lighthouse score.

Run against a *running* app after installing requirements-browser.txt:
    python scripts/check_page_speed.py --base-url http://127.0.0.1:8000

Use --chromium-executable for a system/browser binary when the Playwright
browser download is unavailable. Results are local lab measurements, not
field Core Web Vitals or a promise about Render cold starts or other regions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("reports/generated/page-speed.json"))
    parser.add_argument("--chromium-executable", type=Path)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    viewports: dict[str, dict[str, object]] = {}
    report: dict[str, object] = {
        "source": "local Chromium navigation, fresh context per run, service workers blocked",
        "url": args.base_url,
        "runs_per_viewport": args.runs,
        "units": "milliseconds (timing); bytes (resource sizes)",
        "viewports": viewports,
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium_executable)
        for width in (1440, 390):
            samples: list[dict[str, int]] = []
            for _ in range(args.runs):
                context = browser.new_context(
                    viewport={"width": width, "height": 900}, service_workers="block"
                )
                page = context.new_page()
                page.add_init_script(
                    "window.__lcp=0;new PerformanceObserver(l=>{for(const e of l.getEntries())"
                    "window.__lcp=e.startTime}).observe({type:'largest-contentful-paint',buffered:true})"
                )
                response = page.goto(args.base_url, wait_until="networkidle", timeout=30000)
                if response is None or not response.ok:
                    raise RuntimeError(
                        f"Landing page failed: {response.status if response else 'no response'}"
                    )
                page.wait_for_function(
                    "() => document.querySelectorAll('#modelsel button').length >= 3 && "
                    "document.querySelector('#proof-tests')?.textContent !== '—' && "
                    "document.querySelector('#tab-overview .grade-ring b')"
                )
                sample = page.evaluate(
                    """() => {
                      const n=performance.getEntriesByType('navigation')[0];
                      const fcp=performance.getEntriesByType('paint').find(e=>e.name==='first-contentful-paint');
                      const bytes=performance.getEntriesByType('resource').reduce((sum,e)=>sum+e.encodedBodySize,0);
                      return {ttfb_ms:Math.round(n.responseStart),load_ms:Math.round(n.loadEventEnd),
                        fcp_ms:Math.round(fcp?.startTime||0),lcp_ms:Math.round(window.__lcp),
                        html_wire_bytes:n.encodedBodySize,assets_wire_bytes:bytes,
                        scroll_width:document.documentElement.scrollWidth};
                    }"""
                )
                sample["html_bytes"] = len(response.body())
                if sample["scroll_width"] > width:
                    raise RuntimeError(
                        f"Horizontal overflow at {width}px: {sample['scroll_width']}px"
                    )
                samples.append(sample)
                context.close()
            viewports[str(width)] = {
                "samples": samples,
                "median": {key: median(sample[key] for sample in samples) for key in samples[0]},
            }
        browser.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {args.output}")
    for width, data in viewports.items():
        print(f"{width}px median: {data['median']}")


if __name__ == "__main__":
    main()
