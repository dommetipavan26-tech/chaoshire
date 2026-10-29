"""Command-line tools for CI/CD fairness gates and report generation."""

import argparse
import json
from pathlib import Path

from .agent import review_audit
from .chaos import run_chaos_suite
from .config import (
    GATE_MAX_HOLDOUT_MEAN_FALSE_POSITIVE_RATE,
    GATE_MAX_HOLDOUT_P90_FALSE_POSITIVE_RATE,
    GATE_MIN_HOLDOUT_FOUR_FIFTHS_PASS_RATE,
    GATE_MIN_HOLDOUT_MEAN_ACCURACY,
    GATE_MIN_HOLDOUT_MEAN_RECALL,
    GATE_MIN_HOLDOUT_P10_ACCURACY,
    GATE_MIN_HOLDOUT_P10_RECALL,
    GATE_MIN_HOLDOUT_P10_WORST_DI,
)
from .evidence import build_evidence_bundle
from .metrics import audit, worst_disparate_impact
from .models import build_decisions, get_model
from .pdf_reporting import render_pdf_report
from .quality import evaluate_fairness_gate
from .reporting import render_html_report

#: Default destination for the protected-attribute contrast report. Under
#: ``reports/generated/``, which .gitignore already excludes: the fit is a
#: disposable diagnostic, not an artifact to pin or commit.
CONTRAST_REPORT_PATH = Path("reports/generated/protected-contrast.json")


def _unit_interval(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number between 0 and 1") from error
    if not 0.0 <= number <= 1.0:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chaoshire", description="Continuous fairness utilities")
    commands = parser.add_subparsers(dest="command", required=True)
    gate = commands.add_parser("gate", help="Evaluate a reference model release gate")
    gate.add_argument("--baseline", choices=["legacy", "fair", "trained"], default="legacy")
    gate.add_argument("--candidate", choices=["legacy", "fair", "trained"], default="trained")
    gate.add_argument("--min-certificate", type=int, default=75)
    gate.add_argument("--min-resilience", type=int, default=80)
    gate.add_argument("--min-di", type=_unit_interval, default=0.8)
    gate.add_argument("--min-accuracy", type=_unit_interval, default=0.8)
    gate.add_argument(
        "--min-holdout-mean-accuracy", type=_unit_interval, default=GATE_MIN_HOLDOUT_MEAN_ACCURACY
    )
    gate.add_argument(
        "--min-holdout-p10-accuracy", type=_unit_interval, default=GATE_MIN_HOLDOUT_P10_ACCURACY
    )
    gate.add_argument(
        "--min-holdout-mean-recall", type=_unit_interval, default=GATE_MIN_HOLDOUT_MEAN_RECALL
    )
    gate.add_argument(
        "--min-holdout-p10-recall", type=_unit_interval, default=GATE_MIN_HOLDOUT_P10_RECALL
    )
    gate.add_argument(
        "--max-holdout-mean-fpr",
        type=_unit_interval,
        default=GATE_MAX_HOLDOUT_MEAN_FALSE_POSITIVE_RATE,
    )
    gate.add_argument(
        "--max-holdout-p90-fpr",
        type=_unit_interval,
        default=GATE_MAX_HOLDOUT_P90_FALSE_POSITIVE_RATE,
    )
    gate.add_argument(
        "--min-holdout-p10-di", type=_unit_interval, default=GATE_MIN_HOLDOUT_P10_WORST_DI
    )
    gate.add_argument(
        "--min-holdout-di-pass-rate",
        type=_unit_interval,
        default=GATE_MIN_HOLDOUT_FOUR_FIFTHS_PASS_RATE,
    )
    report = commands.add_parser("report", help="Generate a self-contained HTML or PDF report")
    report.add_argument("--model", choices=["legacy", "fair", "trained"], default="legacy")
    report.add_argument("--format", choices=["html", "pdf"], default="html")
    report.add_argument("--output", default="chaoshire-report.html")
    review = commands.add_parser(
        "review", help="Run the evidence-grounded fairness review (deterministic rules)"
    )
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
    train.add_argument(
        "--holdout",
        action="store_true",
        help=(
            "audit pinned models on the disjoint synthetic holdout populations, "
            "seeds 51–100 (no scikit-learn needed)"
        ),
    )
    train.add_argument(
        "--policy-study",
        action="store_true",
        help=(
            "reproduce global-cutoff selection on synthetic tuning seeds and report "
            "the separate holdout; never reads real applicant data"
        ),
    )
    train.add_argument(
        "--max-mean-fpr",
        type=_unit_interval,
        help="optional policy-study constraint: reject candidates above this mean FPR",
    )
    train.add_argument(
        "--min-mean-recall",
        type=_unit_interval,
        help="optional policy-study constraint: reject candidates below this mean recall",
    )
    train.add_argument(
        "--robust-holdout",
        action="store_true",
        help=(
            "evaluate frozen models on baseline seeds 51–100 and five separate "
            "stress scenarios (seeds 101–110); no model fitting"
        ),
    )
    train.add_argument(
        "--calibration-study",
        action="store_true",
        help=(
            "run build-time raw-probability calibration diagnostics on the frozen "
            "synthetic holdout (requires scikit-learn)"
        ),
    )
    train.add_argument(
        "--out",
        default=str(CONTRAST_REPORT_PATH),
        help="where --include-protected writes its JSON report",
    )
    return parser


def run_train_command(
    write: bool = False,
    check: bool = False,
    include_protected: bool = False,
    out: str | None = None,
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
        blind = audit(build_decisions(load_artifact()["coefficients"]))
        contrast_report = {
            "mode": "with-protected-attributes",
            "pinned": False,
            "coefficients": contrast_coefficients,
            "certificate": result["certificate"],
            "gender_disparate_impact": gender["disparate_impact"],
            # The score uses the worst attribute, so compare like with like.
            "worst_disparate_impact": worst_disparate_impact(result),
            "blind_worst_disparate_impact": worst_disparate_impact(blind),
            "note": (
                "Experimental contrast fit. Never pinned to the artifact; "
                "compare against `python -m chaoshire train` for the blind model."
            ),
        }
        # Written to a file rather than printed. Everything downstream of a
        # protected-attribute fit - the coefficients *and* the certificate and
        # disparate impact computed from them - is classified by CodeQL's
        # py/clear-text-logging rule as private data reaching an output sink. The
        # verdict is a false positive (the fixture is synthetic and its
        # protected-attribute weights are already published in
        # chaoshire/models.py), but inline suppression comments are not honoured by
        # this repository's code-scanning configuration, and excluding the query
        # repo-wide would stop it catching a genuine credential in a log line
        # elsewhere. A file the operator asked for is also simply the better
        # channel for a machine-readable report; stdout gets a static
        # acknowledgement. See SECURITY.md, "Static analysis".
        target = Path(out) if out else CONTRAST_REPORT_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(contrast_report, indent=2) + "\n", encoding="utf-8")
        print(
            f"Wrote the protected-attribute contrast fit to {target}. "
            "Never pinned to the artifact; --write is blind-only."
        )
        return 0

    pinned = None
    replaced_invalid: str | None = None
    if ARTIFACT_PATH.exists():
        try:
            pinned = load_artifact()
        except ValueError as error:
            # --write exists to replace an artifact that no longer satisfies the
            # loader's rules (e.g. after a training-policy change); anything else
            # must still fail loudly.
            if not write:
                raise
            replaced_invalid = str(error)
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
        if replaced_invalid:
            report["replaced_invalid_artifact"] = replaced_invalid
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
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "gate":
        result = evaluate_fairness_gate(
            baseline_model=args.baseline,
            candidate_model=args.candidate,
            minimum_certificate=args.min_certificate,
            minimum_resilience=args.min_resilience,
            minimum_disparate_impact=args.min_di,
            minimum_accuracy=args.min_accuracy,
            minimum_holdout_mean_accuracy=args.min_holdout_mean_accuracy,
            minimum_holdout_p10_accuracy=args.min_holdout_p10_accuracy,
            minimum_holdout_mean_recall=args.min_holdout_mean_recall,
            minimum_holdout_p10_recall=args.min_holdout_p10_recall,
            maximum_holdout_mean_false_positive_rate=args.max_holdout_mean_fpr,
            maximum_holdout_p90_false_positive_rate=args.max_holdout_p90_fpr,
            minimum_holdout_p10_worst_disparate_impact=args.min_holdout_p10_di,
            minimum_holdout_four_fifths_pass_rate=args.min_holdout_di_pass_rate,
        )
        print(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1
    if args.command == "train":
        study_modes = sum(
            bool(value)
            for value in (
                args.policy_study,
                args.holdout,
                args.robust_holdout,
                args.calibration_study,
            )
        )
        if study_modes > 1:
            parser.error(
                "--policy-study, --holdout, --robust-holdout, and --calibration-study "
                "are mutually exclusive"
            )
        if (
            args.max_mean_fpr is not None or args.min_mean_recall is not None
        ) and not args.policy_study:
            parser.error("--max-mean-fpr and --min-mean-recall require --policy-study")
        if args.policy_study:
            if args.write or args.check or args.include_protected:
                parser.error(
                    "--policy-study cannot be combined with --write, --check, or "
                    "--include-protected"
                )
            from .training import policy_study

            print(
                json.dumps(
                    policy_study(
                        maximum_mean_false_positive_rate=args.max_mean_fpr,
                        minimum_mean_recall=args.min_mean_recall,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.holdout:
            if args.write or args.check or args.include_protected:
                parser.error(
                    "--holdout cannot be combined with --write, --check, or --include-protected"
                )
            from .training import holdout_comparison

            print(json.dumps(holdout_comparison(), indent=2))
            return 0
        if args.robust_holdout:
            if args.write or args.check or args.include_protected:
                parser.error(
                    "--robust-holdout cannot be combined with --write, --check, or "
                    "--include-protected"
                )
            from .training import robust_holdout_comparison

            print(json.dumps(robust_holdout_comparison(), indent=2))
            return 0
        if args.calibration_study:
            if args.write or args.check or args.include_protected:
                parser.error(
                    "--calibration-study cannot be combined with --write, --check, or "
                    "--include-protected"
                )
            from .training import calibration_study

            print(json.dumps(calibration_study(), indent=2))
            return 0
        return run_train_command(
            write=args.write,
            check=args.check,
            include_protected=args.include_protected,
            out=args.out,
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
