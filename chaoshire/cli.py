"""Command-line tools for CI/CD fairness gates and report generation."""
import argparse
import json
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
    gate.add_argument("--baseline", choices=["legacy", "fair"], default="legacy")
    gate.add_argument("--candidate", choices=["legacy", "fair"], default="fair")
    gate.add_argument(
        "--min-certificate",
        type=int,
        default=75,
        help="Minimum fairness risk score (0-100). The flag name is kept for API compatibility.",
    )
    gate.add_argument("--min-resilience", type=int, default=80)
    gate.add_argument("--min-di", type=float, default=0.8)
    report = commands.add_parser("report", help="Generate a self-contained HTML or PDF report")
    report.add_argument("--model", choices=["legacy", "fair"], default="legacy")
    report.add_argument("--format", choices=["html", "pdf"], default="html")
    report.add_argument("--output", default="chaoshire-report.html")
    review = commands.add_parser("review", help="Run the evidence-grounded fairness review agent")
    review.add_argument("--model", choices=["legacy", "fair"], default="legacy")
    evidence = commands.add_parser("evidence", help="Write a tamper-evident aggregate evidence bundle")
    evidence.add_argument("--model", choices=["legacy", "fair"], default="legacy")
    evidence.add_argument("--output", default="chaoshire-evidence.json")
    return parser


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
