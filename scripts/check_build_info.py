"""Fail the build when the committed build facts stop matching reality.

``chaoshire/build_info.py`` holds the numbers the landing page and README quote.
Two of them — the automated-test count and the package-coverage percentage — are
properties of a test run rather than of the package, so they can silently drift.
This script re-derives both and exits non-zero when they no longer match, which
is what keeps "121 automated tests · 97.9% coverage" from becoming the kind of
stale claim the repository used to ship.

Usage
-----
    python -m pytest --cov=chaoshire --cov-report=json -q
    python scripts/check_build_info.py --coverage-json coverage.json

Without ``--coverage-json`` only the collected-test count is verified.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from chaoshire.build_info import AUTOMATED_TESTS, PACKAGE_COVERAGE  # noqa: E402


def collected_test_count() -> int:
    """Count tests pytest would run, using the repository's own configuration."""
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--no-cov",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in (0, 1):
        raise SystemExit(f"pytest --collect-only failed:\n{completed.stdout}\n{completed.stderr}")
    collected = 0
    for line in completed.stdout.splitlines():
        # `-q --collect-only` prints one `path::test_name` line per test.
        if "::" in line and not line.startswith(" "):
            collected += 1
    if not collected:
        raise SystemExit(f"could not parse collected tests from:\n{completed.stdout}")
    return collected


def coverage_percent(coverage_json: Path) -> str:
    """Format coverage the way the README and landing page quote it.

    ``percent_covered_display`` is rounded to the precision in the coverage
    configuration (0 decimals by default, i.e. "97"), which would silently
    downgrade a committed "97.3%" to "97.0%" on every run. ``percent_covered``
    is the unrounded figure.
    """
    payload = json.loads(coverage_json.read_text(encoding="utf-8"))
    return f"{round(float(payload['totals']['percent_covered']), 1):.1f}%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-json", type=Path, default=None)
    parser.add_argument(
        "--write", action="store_true", help="update build_info.py instead of failing"
    )
    args = parser.parse_args(argv)

    problems: list[str] = []
    tests = collected_test_count()
    if tests != AUTOMATED_TESTS:
        problems.append(f"AUTOMATED_TESTS is {AUTOMATED_TESTS} but pytest collects {tests}")

    coverage = PACKAGE_COVERAGE
    if args.coverage_json is not None:
        if not args.coverage_json.exists():
            raise SystemExit(
                f"{args.coverage_json} does not exist; run pytest with --cov-report=json"
            )
        coverage = coverage_percent(args.coverage_json)
        # Allow ±0.1% tolerance for coverage differences between environments
        # (e.g., Python 3.11 vs 3.12, different package versions).
        committed_pct = float(PACKAGE_COVERAGE.rstrip("%"))
        actual_pct = float(coverage.rstrip("%"))
        if abs(committed_pct - actual_pct) > 0.1:
            problems.append(
                f"PACKAGE_COVERAGE is {PACKAGE_COVERAGE} but coverage reports {coverage}"
            )

    if not problems:
        print(
            f"build_info OK · {tests} tests · coverage {coverage} · (verified against a real run)"
        )
        return 0

    if args.write:
        target = REPO_ROOT / "chaoshire" / "build_info.py"
        text = target.read_text(encoding="utf-8")
        text = text.replace(f"AUTOMATED_TESTS = {AUTOMATED_TESTS}", f"AUTOMATED_TESTS = {tests}")
        text = text.replace(
            f'PACKAGE_COVERAGE = "{PACKAGE_COVERAGE}"', f'PACKAGE_COVERAGE = "{coverage}"'
        )
        target.write_text(text, encoding="utf-8")
        print(f"updated {target}: {tests} tests, coverage {coverage}")
        return 0

    print("build_info drift detected:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    print(
        "Fix chaoshire/build_info.py (or rerun with --write). The landing page and "
        "README quote these numbers, so they must match a real test run.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
