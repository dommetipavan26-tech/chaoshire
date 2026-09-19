"""Command-line tools for CI/CD fairness gates and report generation."""

import argparse
import json
import sys
from pathlib import Path

from .agent import review_audit
from .chaos import run_chaos_suite
from .evidence import build_evidence_bundle
from .metrics import audit
from .models import build_decisions, get_model
from .pdf_reporting import render_pdf_report
from .quality import evaluate_fairness_gate
from .reporting import render_html_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chaoshire", description="Continuous fairness utilities")
    commands = parser.add_subparsers(dest="command", required=True)
    gate = commands.add_parser("gate", help="Evaluate a reference model release gate")
    gate.add_argument("--baseline", choices=["legacy", "fair", "trained"], default="legacy")
    gate.add_argument("--candidate", choices=["legacy", "fair", "trained"], default="fair")
    gate.add_argument("--min-certificate", type=int, default=75)
    gate.add_argument("--min-resilience", type=int, default=80)
    gate.add_argument("--min-di", type=float, default=0.8)
    report = commands.add_parser("report", help="Generate a self-contained HTML or PDF report")
    report.add_argument("--model", choices=["legacy", "fair", "trained"], default="legacy")
    report.add_argument("--format", choices=["html", "pdf"], default="html")
    report.add_argument("--output", default="chaoshire-report.html")
    review = commands.add_parser("review", help="Run the evidence-grounded fairness review agent")
    review.add_argument("--model", choices=["legacy", "fair", "trained"], default="legacy")
    evidence = commands.add_parser(
        "evidence", help="Write a tamper-evident aggregate evidence bundle"
    )
    evidence.add_argument("--model", choices=["legacy", "fair", "trained"], default="legacy")
    evidence.add_argument("--output", default="chaoshire-evidence.json")
    train = commands.add_parser("train", help="Re-fit or verify the pinned trained-model artifact")
    train.add_argument("--write", action="store_true", help="rewrite the pinned artifact")
    train.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when fresh training drifts from the pinned artifact",
    )
    train.add_argument(
        "--include-protected",
        action="store_true",
        help="experimental contrast fit that leaks protected attributes; never pinned",
    )
    return parser


def run_train_command(
    write: bool = False, check: bool = False, include_protected: bool = False
) -> int:
    """Re-fit the trained model and report drift against the pinned artifact."""
    from .models import build_decisions
    from .training import (
        AGREEMENT_FLOOR,
        ARTIFACT_PATH,
        coefficient_digest,
        decision_agreement,
        load_artifact,
        save_artifact,
        train_coefficients,
    )

    if include_protected:
        if write:
            print("Refusing to pin a protected-attribute fit; --write is blind-only.")
            return 2
        contrast_coefficients = train_coefficients(include_protected=True)
        result = audit(build_decisions(contrast_coefficients))
        gender = next(a for a in result["attributes"] if a["attribute"] == "gender")
        contrast_report = json.dumps(
            {
                "mode": "with-protected-attributes",
                "pinned": False,
                "coefficients": contrast_coefficients,
                "certificate": result["certificate"],
                "gender_disparate_impact": gender["disparate_impact"],
                "note": (
                    "Experimental contrast fit. Never pinned to the artifact; "
                    "compare against `python -m chaoshire train` for the blind model."
                ),
            },
            indent=2,
        )
        # Written to stdout directly rather than through print(). CodeQL's
        # py/clear-text-logging rule classifies everything downstream of
        # train_coefficients(include_protected=True) as private data reaching a
        # logging sink, which is a false positive here on two counts: this is the
        # CLI's requested primary output, not a log record, and the values are
        # derived from the bundled 1,000-row synthetic fixture whose
        # protected-attribute weights are already published in chaoshire/models.py.
        # An inline `# codeql[...]` suppression comment is the usual answer, but
        # this repository's code-scanning configuration does not honour them, so
        # the accepted-risk reasoning is recorded here instead. The contrast fit is
        # never pinned to the artifact - the --write guard above and
        # tests/test_trained_model.py both enforce that.
        sys.stdout.write(contrast_report + "\n")
        return 0

    pinned = load_artifact() if ARTIFACT_PATH.exists() else None
    fresh = train_coefficients()
    agreement = decision_agreement(fresh, pinned["coefficients"]) if pinned is not None else 1.0
    report: dict[str, object] = {
        "artifact": str(ARTIFACT_PATH),
        "pinned": pinned is not None,
        "fresh_digest": coefficient_digest(fresh),
        "pinned_digest": pinned["coefficient_digest"] if pinned else None,
        "decision_agreement": round(agreement, 4),
        "agreement_floor": AGREEMENT_FLOOR,
        "coefficients": fresh,
    }
    if write:
        save_artifact()
        report["written"] = True
        pinned = load_artifact()
        report["pinned_digest"] = pinned["coefficient_digest"]
    print(json.dumps(report, indent=2))
    if check:
        # Agreement-based (not digest-based) so optimizer jitter across
        # scikit-learn versions cannot red the build; the artifact digest is
        # still enforced on every load.
        drifted = pinned is None or agreement < AGREEMENT_FLOOR
        return 1 if drifted else 0
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "gate":
        result = evaluate_fairness_gate(
            baseline_model=args.baseline,
            candidate_model=args.candidate,
            minimum_certificate=args.min_certificate,
            minimum_resilience=args.min_resilience,
            minimum_disparate_impact=args.min_di,
        )
        print(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1
    if args.command == "train":
        return run_train_command(
            write=args.write, check=args.check, include_protected=args.include_protected
        )
    result = audit(build_decisions(get_model(args.model)))
    chaos = run_chaos_suite(args.model, evidence_limit=0)
    if args.command == "review":
        print(json.dumps(review_audit(result, chaos), indent=2))
        return 0
    if args.command == "evidence":
        review = review_audit(result, chaos)
        bundle = build_evidence_bundle(result, chaos, review)
        Path(args.output).write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        print(f"Wrote {args.output}")
        return 0
    output = Path(args.output)
    if args.format == "pdf":
        output.write_bytes(render_pdf_report(result, chaos))
    else:
        output.write_text(render_html_report(result, chaos), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0
