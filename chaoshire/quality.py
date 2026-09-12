"""Model comparison and automated fairness release gates."""
from typing import Any

from .chaos import run_chaos_suite
from .metrics import audit
from .models import MODEL_META, build_decisions, get_model


def model_snapshot(model: str) -> dict[str, Any]:
    audited = audit(build_decisions(get_model(model)))
    chaos = run_chaos_suite(model, evidence_limit=0)
    worst_di = min(attribute["disparate_impact"] for attribute in audited["attributes"])
    return {
        "model": MODEL_META[model],
        "certificate": audited["certificate"],
        "chaos_resilience": chaos["resilience"],
        "worst_disparate_impact": worst_di,
        "accept_rate": audited["stats"]["accept_rate"],
        "attributes": audited["attributes"],
        "experiment_id": chaos["experiment_id"],
    }


def compare_models(baseline_model: str = "legacy", candidate_model: str = "fair") -> dict:
    baseline = model_snapshot(baseline_model)
    candidate = model_snapshot(candidate_model)
    return {
        "baseline": baseline,
        "candidate": candidate,
        "delta": {
            "certificate": candidate["certificate"]["total"] - baseline["certificate"]["total"],
            "chaos_resilience": candidate["chaos_resilience"] - baseline["chaos_resilience"],
            "worst_disparate_impact": round(
                candidate["worst_disparate_impact"] - baseline["worst_disparate_impact"], 4
            ),
            "accept_rate": round(candidate["accept_rate"] - baseline["accept_rate"], 4),
        },
    }


def evaluate_fairness_gate(
    baseline_model: str = "legacy",
    candidate_model: str = "fair",
    minimum_certificate: int = 75,
    minimum_resilience: int = 80,
    minimum_disparate_impact: float = 0.8,
    maximum_certificate_regression: int = 0,
    maximum_resilience_regression: int = 0,
) -> dict:
    comparison = compare_models(baseline_model, candidate_model)
    baseline = comparison["baseline"]
    candidate = comparison["candidate"]
    checks = [
        {
            "id": "minimum_certificate",
            "label": f"Risk score ≥ {minimum_certificate}",
            "actual": candidate["certificate"]["total"],
            "passed": candidate["certificate"]["total"] >= minimum_certificate,
        },
        {
            "id": "minimum_resilience",
            "label": f"Chaos resilience ≥ {minimum_resilience}",
            "actual": candidate["chaos_resilience"],
            "passed": candidate["chaos_resilience"] >= minimum_resilience,
        },
        {
            "id": "minimum_disparate_impact",
            "label": f"Worst disparate impact ≥ {minimum_disparate_impact}",
            "actual": candidate["worst_disparate_impact"],
            "passed": candidate["worst_disparate_impact"] >= minimum_disparate_impact,
        },
        {
            "id": "certificate_regression",
            "label": f"Risk score regression ≤ {maximum_certificate_regression}",
            "actual": baseline["certificate"]["total"] - candidate["certificate"]["total"],
            "passed": (
                candidate["certificate"]["total"]
                >= baseline["certificate"]["total"] - maximum_certificate_regression
            ),
        },
        {
            "id": "resilience_regression",
            "label": f"Resilience regression ≤ {maximum_resilience_regression}",
            "actual": baseline["chaos_resilience"] - candidate["chaos_resilience"],
            "passed": (
                candidate["chaos_resilience"]
                >= baseline["chaos_resilience"] - maximum_resilience_regression
            ),
        },
    ]
    passed = all(check["passed"] for check in checks)
    return {
        "status": "PASS" if passed else "BLOCK",
        "passed": passed,
        "baseline_model": baseline_model,
        "candidate_model": candidate_model,
        "checks": checks,
        "comparison": comparison,
        "policy": {
            "minimum_certificate": minimum_certificate,
            "minimum_resilience": minimum_resilience,
            "minimum_disparate_impact": minimum_disparate_impact,
            "maximum_certificate_regression": maximum_certificate_regression,
            "maximum_resilience_regression": maximum_resilience_regression,
        },
    }
