"""Command-line tools for CI/CD fairness gates and report generation."""
import argparse
import json
from pathlib import Path

from .chaos import run_chaos_suite
from .metrics import audit
from .models import build_decisions, get_model
from .quality import evaluate_fairness_gate
from .reporting import render_html_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chaoshire", description="Continuous fairness utilities")
    commands = parser.add_subparsers(dest="command", required=True)
    gate = commands.add_parser("gate", help="Evaluate a reference model release gate")
    gate.add_argument("--baseline", choices=["legacy", "fair"], default="legacy")
    gate.add_argument("--candidate", choices=["legacy", "fair"], default="fair")
    gate.add_argument("--min-certificate", type=int, default=75)
    gate.add_argument("--min-resilience", type=int, default=80)
    gate.add_argument("--min-di", type=float, default=0.8)
    report = commands.add_parser("report", help="Generate a self-contained reference HTML report")
    report.add_argument("--model", choices=["legacy", "fair"], default="legacy")
    report.add_argument("--output", default="chaoshire-report.html")
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
    Path(args.output).write_text(render_html_report(result, chaos), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0
