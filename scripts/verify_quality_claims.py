"""Verify the public quality claims that the landing page and README repeat.

Recruiters should not have to trust a badge, and maintainers should not have to
remember to update a number. Every claim in docs/VERIFIED-QUALITY.json is re-derived
here from the repository and the running application:

    python scripts/verify_quality_claims.py
    python scripts/verify_quality_claims.py --coverage coverage.json

Exit code is non-zero with a readable report when any claim has drifted.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAIMS = ROOT / "docs" / "VERIFIED-QUALITY.json"
LANDING = ROOT / "index.html"

sys.path.insert(0, str(ROOT))


def collect_rows() -> list[tuple[str, str, str]]:
    """Return (claim, expected, actual) rows for the report."""
    claims = json.loads(CLAIMS.read_text(encoding="utf-8"))
    landing = LANDING.read_text(encoding="utf-8")
    rows: list[tuple[str, str, str]] = []

    def check(name: str, expected: object, actual: object) -> None:
        rows.append((name, str(expected), str(actual)))

    from chaoshire import __version__
    from chaoshire.metrics import audit
    from chaoshire.models import build_decisions, get_model
    from chaoshire.quality import compare_models
    from chaoshire.services import mitigate

    check("package version matches pyproject claim", claims["version"], __version__)
    check(
        "landing proof strip shows the release version",
        f'v{claims["version"]}',
        re.search(r"<b>(v[\d.]+)</b>", landing).group(1),
    )

    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    match = re.search(r"(\d+) tests? collected", collected.stdout)
    count = int(match.group(1)) if match else 0
    check("core tests collected", claims["core_tests"], count)
    check(
        "landing proof strip test count",
        str(claims["core_tests"]),
        re.search(r'data-verified-tests="([^"]+)"', landing).group(1),
    )
    check(
        "landing proof strip coverage",
        f'{claims["coverage_percent"]:.2f}',
        re.search(r'data-verified-coverage="([^"]+)"', landing).group(1),
    )

    legacy = audit(build_decisions(get_model("legacy")))["certificate"]
    fair = audit(build_decisions(get_model("fair")))["certificate"]
    check("LegacyCorp fixture risk score", f'{claims["demo"]["legacy_risk_score"]}', legacy["total"])
    check("LegacyCorp fixture grade", claims["demo"]["legacy_grade"], legacy["grade"])
    check("MeritFirst fixture risk score", claims["demo"]["fair_risk_score"], fair["total"])
    check("MeritFirst fixture grade", claims["demo"]["fair_grade"], fair["grade"])
    check(
        "synthetic population size",
        claims["demo"]["candidates"],
        audit(build_decisions(get_model("legacy")))["stats"]["candidates"],
    )
    mitigated = mitigate(["blind", "proxy", "calibrate"])["after"]["certificate"]
    check("mitigated fixture risk score", claims["demo"]["mitigated_risk_score"], mitigated["total"])

    from chaoshire.chaos import CHAOS_TESTS, run_chaos_suite

    suite = run_chaos_suite("legacy", evidence_limit=1)
    gender_swap = next(test for test in suite["tests"] if test["name"].startswith("Gender-Swap"))
    check(
        "gender-swap decision flips",
        claims["demo"]["gender_swap_decision_flips"],
        int(str(gender_swap["value"]).split()[0]),
    )
    check("chaos experiment count", claims["demo"]["chaos_experiments"], len(CHAOS_TESTS))
    check("chaos resilience of the biased fixture", claims["demo"]["legacy_resilience"], suite["resilience"])
    check("release gate improvement delta", claims["demo"]["risk_score_delta"], compare_models()["delta"]["certificate"])

    return rows


def coverage_row(path: Path) -> tuple[str, str, str]:
    claims = json.loads(CLAIMS.read_text(encoding="utf-8"))
    measured = json.loads(path.read_text(encoding="utf-8"))["totals"]["percent_covered"]
    return (
        "package coverage from coverage.json",
        f'{claims["coverage_percent"]:.2f}',
        f"{measured:.2f}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify published quality claims.")
    parser.add_argument(
        "--report",
        type=Path,
        help="write the full claim/expected/actual table to this file instead of stdout",
    )
    parser.add_argument(
        "--coverage",
        type=Path,
        help="coverage.json produced by: python -m pytest --cov=chaoshire --cov-report=json:coverage.json",
    )
    args = parser.parse_args(argv)

    rows = collect_rows()
    if args.coverage:
        if not args.coverage.exists():
            print(f"coverage report not found: {args.coverage}", file=sys.stderr)
            return 2
        rows.append(coverage_row(args.coverage))

    # Values are read from committed files, so only the claim name and a status word are
    # written to the console; the numeric detail goes to --report for CI artefacts.
    drift = [name for name, expected, actual in rows if expected != actual]
    stale = {name for name in drift}

    if args.report:
        args.report.write_text(
            "\n".join(
                f"{name}: expected {expected}, found {actual}" for name, expected, actual in rows
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"detailed claim report written to {args.report}")

    for name, _expected, _actual in rows:
        print(("STALE  " if name in stale else "verified") + f"  {name}")

    if drift:
        print(
            f"\n{len(drift)} published claim(s) are stale — re-measure and update "
            "docs/VERIFIED-QUALITY.json (details in --report).",
            file=sys.stderr,
        )
        return 1
    print(f"\nAll {len(rows)} published claims verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
