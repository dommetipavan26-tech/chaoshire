"""Model comparison and automated fairness release gates."""

from typing import Any

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
from .metrics import audit
from .models import MODEL_META, build_decisions, get_model


def model_snapshot(model: str) -> dict[str, Any]:
    decisions = build_decisions(get_model(model))
    audited = audit(decisions)
    chaos = run_chaos_suite(model, evidence_limit=0)
    worst_di = min(attribute["disparate_impact"] for attribute in audited["attributes"])
    accuracy = (
        float((decisions["accepted"].astype(bool) == decisions["qualified"].astype(bool)).mean())
        if "qualified" in decisions.columns and len(decisions)
        else None
    )
    return {
        "model": MODEL_META[model],
        "certificate": audited["certificate"],
        "chaos_resilience": chaos["resilience"],
        "worst_disparate_impact": worst_di,
        "accept_rate": audited["stats"]["accept_rate"],
        "accuracy": round(accuracy, 4) if accuracy is not None else None,
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
            "accuracy": round(candidate["accuracy"] - baseline["accuracy"], 4),
        },
    }


def evaluate_fairness_gate(
    baseline_model: str = "legacy",
    candidate_model: str = "trained",
    minimum_certificate: int = 75,
    minimum_resilience: int = 80,
    minimum_disparate_impact: float = 0.8,
    maximum_certificate_regression: int = 0,
    maximum_resilience_regression: int = 0,
    minimum_accuracy: float = 0.80,
    minimum_holdout_mean_accuracy: float = GATE_MIN_HOLDOUT_MEAN_ACCURACY,
    minimum_holdout_p10_accuracy: float = GATE_MIN_HOLDOUT_P10_ACCURACY,
    minimum_holdout_mean_recall: float = GATE_MIN_HOLDOUT_MEAN_RECALL,
    minimum_holdout_p10_recall: float = GATE_MIN_HOLDOUT_P10_RECALL,
    maximum_holdout_mean_false_positive_rate: float = (GATE_MAX_HOLDOUT_MEAN_FALSE_POSITIVE_RATE),
    maximum_holdout_p90_false_positive_rate: float = (GATE_MAX_HOLDOUT_P90_FALSE_POSITIVE_RATE),
    minimum_holdout_p10_worst_disparate_impact: float = GATE_MIN_HOLDOUT_P10_WORST_DI,
    minimum_holdout_four_fifths_pass_rate: float = GATE_MIN_HOLDOUT_FOUR_FIFTHS_PASS_RATE,
) -> dict:
    from .training import robust_holdout_comparison

    probability_limits = {
        "minimum_disparate_impact": minimum_disparate_impact,
        "minimum_accuracy": minimum_accuracy,
        "minimum_holdout_mean_accuracy": minimum_holdout_mean_accuracy,
        "minimum_holdout_p10_accuracy": minimum_holdout_p10_accuracy,
        "minimum_holdout_mean_recall": minimum_holdout_mean_recall,
        "minimum_holdout_p10_recall": minimum_holdout_p10_recall,
        "maximum_holdout_mean_false_positive_rate": (maximum_holdout_mean_false_positive_rate),
        "maximum_holdout_p90_false_positive_rate": (maximum_holdout_p90_false_positive_rate),
        "minimum_holdout_p10_worst_disparate_impact": (minimum_holdout_p10_worst_disparate_impact),
        "minimum_holdout_four_fifths_pass_rate": (minimum_holdout_four_fifths_pass_rate),
    }
    for name, value in probability_limits.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1.")

    comparison = compare_models(baseline_model, candidate_model)
    baseline = comparison["baseline"]
    candidate = comparison["candidate"]
    holdout = robust_holdout_comparison(
        models={"baseline": baseline_model, "candidate": candidate_model},
        threshold_sensitivity_model=candidate_model,
    )
    candidate_holdout = holdout["models"]["candidate"]
    holdout_metrics = candidate_holdout["metrics"]
    population_count = candidate_holdout["population_count"]
    accuracy = holdout_metrics["accuracy"]
    recall = holdout_metrics["recall"]
    false_positive_rate = holdout_metrics["false_positive_rate"]
    worst_di = holdout_metrics["worst_disparate_impact"]
    pass_rate = candidate_holdout["four_fifths_pass_rate"]["rate"]
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
            "label": f"Demo-fixture worst DI ≥ {minimum_disparate_impact}",
            "actual": candidate["worst_disparate_impact"],
            "passed": candidate["worst_disparate_impact"] >= minimum_disparate_impact,
        },
        {
            "id": "minimum_accuracy",
            "label": f"Accuracy against synthetic label ≥ {minimum_accuracy}",
            "actual": candidate["accuracy"],
            "passed": candidate["accuracy"] is not None
            and candidate["accuracy"] >= minimum_accuracy,
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
        {
            "id": "minimum_holdout_mean_accuracy",
            "label": (
                f"Holdout mean accuracy ≥ {minimum_holdout_mean_accuracy} "
                f"({population_count} synthetic populations)"
            ),
            "actual": accuracy["mean"],
            "passed": accuracy["mean"] >= minimum_holdout_mean_accuracy,
        },
        {
            "id": "minimum_holdout_p10_accuracy",
            "label": f"Holdout p10 accuracy ≥ {minimum_holdout_p10_accuracy}",
            "actual": accuracy["p10"],
            "passed": accuracy["p10"] >= minimum_holdout_p10_accuracy,
        },
        {
            "id": "minimum_holdout_mean_recall",
            "label": f"Holdout mean recall ≥ {minimum_holdout_mean_recall}",
            "actual": recall["mean"],
            "passed": recall["mean"] >= minimum_holdout_mean_recall,
        },
        {
            "id": "minimum_holdout_p10_recall",
            "label": f"Holdout p10 recall ≥ {minimum_holdout_p10_recall}",
            "actual": recall["p10"],
            "passed": recall["p10"] >= minimum_holdout_p10_recall,
        },
        {
            "id": "maximum_holdout_mean_false_positive_rate",
            "label": (
                f"Holdout mean false-positive rate ≤ {maximum_holdout_mean_false_positive_rate}"
            ),
            "actual": false_positive_rate["mean"],
            "passed": false_positive_rate["mean"] <= maximum_holdout_mean_false_positive_rate,
        },
        {
            "id": "maximum_holdout_p90_false_positive_rate",
            "label": (
                f"Holdout p90 false-positive rate ≤ {maximum_holdout_p90_false_positive_rate}"
            ),
            "actual": false_positive_rate["p90"],
            "passed": false_positive_rate["p90"] <= maximum_holdout_p90_false_positive_rate,
        },
        {
            "id": "minimum_holdout_p10_worst_disparate_impact",
            "label": (
                f"Holdout p10 worst disparate impact ≥ {minimum_holdout_p10_worst_disparate_impact}"
            ),
            "actual": worst_di["p10"],
            "passed": worst_di["p10"] >= minimum_holdout_p10_worst_disparate_impact,
        },
        {
            "id": "minimum_holdout_four_fifths_pass_rate",
            "label": (f"Holdout four-fifths pass rate ≥ {minimum_holdout_four_fifths_pass_rate}"),
            "actual": pass_rate,
            "passed": pass_rate >= minimum_holdout_four_fifths_pass_rate,
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
        "holdout": holdout,
        "policy": {
            "minimum_certificate": minimum_certificate,
            "minimum_resilience": minimum_resilience,
            "minimum_disparate_impact": minimum_disparate_impact,
            "minimum_accuracy": minimum_accuracy,
            "minimum_holdout_mean_accuracy": minimum_holdout_mean_accuracy,
            "minimum_holdout_p10_accuracy": minimum_holdout_p10_accuracy,
            "minimum_holdout_mean_recall": minimum_holdout_mean_recall,
            "minimum_holdout_p10_recall": minimum_holdout_p10_recall,
            "maximum_holdout_mean_false_positive_rate": (maximum_holdout_mean_false_positive_rate),
            "maximum_holdout_p90_false_positive_rate": (maximum_holdout_p90_false_positive_rate),
            "minimum_holdout_p10_worst_disparate_impact": (
                minimum_holdout_p10_worst_disparate_impact
            ),
            "minimum_holdout_four_fifths_pass_rate": (minimum_holdout_four_fifths_pass_rate),
            "maximum_certificate_regression": maximum_certificate_regression,
            "maximum_resilience_regression": maximum_resilience_regression,
        },
    }
