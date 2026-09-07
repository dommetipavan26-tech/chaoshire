"""Group-fairness metrics and the transparent certificate calculation."""
from typing import Any

import pandas as pd

from .config import MIN_CELL_SIZE


def round4(value: float) -> float:
    return float(round(float(value), 4))


def attribute_metrics(
    data: pd.DataFrame,
    attribute: str,
    minimum_group_size: int = MIN_CELL_SIZE,
) -> dict[str, Any]:
    groups = []
    has_truth = "qualified" in data.columns
    for group_value in sorted(data[attribute].unique()):
        subset = data[data[attribute] == group_value]
        count = int(len(subset))
        selected = int(subset["accepted"].sum())
        row = {
            "group": str(group_value),
            "n": count,
            "selected": selected,
            "low_n": count < minimum_group_size,
            "selection_rate": round4(selected / max(1, count)),
            "tpr": None,
            "fpr": None,
        }
        if has_truth:
            qualified = subset["qualified"].astype(bool)
            qualified_count = int(qualified.sum())
            row["tpr"] = (
                round4(int(subset.loc[qualified, "accepted"].sum()) / qualified_count)
                if qualified_count
                else None
            )
            not_qualified_count = count - qualified_count
            row["fpr"] = (
                round4(int(subset.loc[~qualified, "accepted"].sum()) / not_qualified_count)
                if not_qualified_count
                else None
            )
        groups.append(row)

    reliable_groups = [group for group in groups if not group["low_n"]] or groups
    rates = [group["selection_rate"] for group in reliable_groups]
    highest_rate = max(rates) if rates else 0.0
    disparate_impact = min(rates) / highest_rate if highest_rate > 0 else 1.0
    true_positive_rates = [
        group["tpr"] for group in reliable_groups if group["tpr"] is not None
    ]
    parity_gap = max(rates) - min(rates) if rates else 0.0
    opportunity_gap = (
        max(true_positive_rates) - min(true_positive_rates)
        if len(true_positive_rates) > 1
        else None
    )
    return {
        "attribute": attribute,
        "groups": groups,
        "disparate_impact": round4(disparate_impact),
        "parity_gap": round4(parity_gap),
        "eq_opp_gap": round4(opportunity_gap) if opportunity_gap is not None else None,
        "di_pass": bool(disparate_impact >= 0.8),
        "parity_pass": bool(parity_gap <= 0.1),
        "eq_pass": bool(opportunity_gap <= 0.1) if opportunity_gap is not None else None,
    }


def certificate(attribute_results: list[dict[str, Any]]) -> dict[str, Any]:
    impacts = [result["disparate_impact"] for result in attribute_results]
    parity_gaps = [result["parity_gap"] for result in attribute_results]
    opportunity_gaps = [
        result["eq_opp_gap"]
        for result in attribute_results
        if result["eq_opp_gap"] is not None
    ]
    impact_points = 40 * min(min(impacts) / 0.8, 1.0)
    parity_points = 20 * max(0.0, 1 - max(parity_gaps) / 0.15)
    if opportunity_gaps:
        opportunity_points = 25 * max(0.0, 1 - max(opportunity_gaps) / 0.2)
        base, denominator = impact_points + parity_points + opportunity_points, 85
    else:
        opportunity_points = None
        base, denominator = impact_points + parity_points, 60

    total = int(max(0, min(100, round(base / denominator * 85 + 15))))
    grade = (
        "A" if total >= 90 else
        "B" if total >= 75 else
        "C" if total >= 60 else
        "D" if total >= 45 else "F"
    )
    components = [
        {"label": "Disparate impact (4/5ths rule)", "pts": round(impact_points, 1), "max": 40},
        {"label": "Demographic parity gap", "pts": round(parity_points, 1), "max": 20},
    ]
    if opportunity_points is not None:
        components.append(
            {"label": "Equal opportunity gap", "pts": round(opportunity_points, 1), "max": 25}
        )
    components.append(
        {"label": "Transparency (XAI + appeals)", "pts": 15, "max": 15}
    )
    return {"total": total, "grade": grade, "components": components}


def audit(
    data: pd.DataFrame,
    attributes: list[str] | None = None,
    minimum_group_size: int = MIN_CELL_SIZE,
) -> dict[str, Any]:
    selected_attributes = attributes or [
        attribute for attribute in ["gender", "ethnicity", "age_band"]
        if attribute in data.columns
    ]
    results = [
        attribute_metrics(data, attribute, minimum_group_size)
        for attribute in selected_attributes
    ]
    count = int(len(data))
    accepted = int(data["accepted"].sum())
    return {
        "stats": {
            "candidates": count,
            "accepted": accepted,
            "accept_rate": round4(accepted / max(1, count)),
            "qualified_share": (
                round4(float(data["qualified"].mean())) if "qualified" in data.columns else None
            ),
        },
        "attributes": results,
        "configuration": {
            "protected_attributes": selected_attributes,
            "minimum_group_size": minimum_group_size,
            "has_ground_truth": "qualified" in data.columns,
        },
        "certificate": certificate(results),
    }
