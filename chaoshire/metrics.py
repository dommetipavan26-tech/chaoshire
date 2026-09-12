"""Group-fairness metrics and the transparent fairness risk-score calculation."""
from itertools import combinations
from math import erfc, sqrt
from typing import Any

import pandas as pd

from .config import MIN_CELL_SIZE


def round4(value: float) -> float:
    return float(round(float(value), 4))


def wilson_interval(successes: int, total: int, z_value: float = 1.959964) -> dict[str, float]:
    """Return a two-sided Wilson score interval for a binomial proportion."""
    if total <= 0:
        return {"low": 0.0, "high": 1.0, "level": 0.95}
    proportion = successes / total
    z_squared = z_value**2
    denominator = 1 + z_squared / total
    centre = (proportion + z_squared / (2 * total)) / denominator
    margin = (
        z_value
        * sqrt(proportion * (1 - proportion) / total + z_squared / (4 * total**2))
        / denominator
    )
    return {
        "low": round4(max(0.0, centre - margin)),
        "high": round4(min(1.0, centre + margin)),
        "level": 0.95,
    }


def two_proportion_test(
    selected_a: int,
    total_a: int,
    selected_b: int,
    total_b: int,
) -> dict[str, float]:
    """Two-sided pooled z-test for equality of two independent proportions."""
    if total_a <= 0 or total_b <= 0:
        return {"z_score": 0.0, "p_value": 1.0}
    proportion_a = selected_a / total_a
    proportion_b = selected_b / total_b
    pooled = (selected_a + selected_b) / (total_a + total_b)
    standard_error = sqrt(pooled * (1 - pooled) * (1 / total_a + 1 / total_b))
    if standard_error == 0:
        return {"z_score": 0.0, "p_value": 1.0}
    z_score = (proportion_a - proportion_b) / standard_error
    return {
        "z_score": round4(z_score),
        "p_value": float(round(erfc(abs(z_score) / sqrt(2)), 8)),
    }


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
            "selection_rate_ci": wilson_interval(selected, count),
            "tpr": None,
            "tpr_ci": None,
            "fpr": None,
        }
        if has_truth:
            qualified = subset["qualified"].astype(bool)
            qualified_count = int(qualified.sum())
            qualified_selected = int(subset.loc[qualified, "accepted"].sum())
            row["tpr"] = (
                round4(qualified_selected / qualified_count) if qualified_count else None
            )
            row["tpr_ci"] = (
                wilson_interval(qualified_selected, qualified_count) if qualified_count else None
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

    statistical_test = None
    if len(reliable_groups) >= 2:
        ordered = sorted(reliable_groups, key=lambda group: group["selection_rate"])
        lowest, highest = ordered[0], ordered[-1]
        test = two_proportion_test(
            lowest["selected"], lowest["n"], highest["selected"], highest["n"]
        )
        comparison_reliable = not lowest["low_n"] and not highest["low_n"]
        statistical_test = {
            "method": "two-sided pooled two-proportion z-test",
            "lowest_group": lowest["group"],
            "highest_group": highest["group"],
            "p_value": test["p_value"],
            "z_score": test["z_score"],
            "comparison_reliable": comparison_reliable,
            "significant_at_0_05": bool(
                test["p_value"] < 0.05 and comparison_reliable
            ),
            "note": "Exploratory indicator; correct for multiple comparisons in formal studies.",
        }
    return {
        "attribute": attribute,
        "groups": groups,
        "disparate_impact": round4(disparate_impact),
        "parity_gap": round4(parity_gap),
        "eq_opp_gap": round4(opportunity_gap) if opportunity_gap is not None else None,
        "di_pass": bool(disparate_impact >= 0.8),
        "parity_pass": bool(parity_gap <= 0.1),
        "eq_pass": bool(opportunity_gap <= 0.1) if opportunity_gap is not None else None,
        "statistical_test": statistical_test,
    }


def intersectional_metrics(
    data: pd.DataFrame,
    attributes: list[str],
    minimum_group_size: int = MIN_CELL_SIZE,
) -> list[dict[str, Any]]:
    """Audit every pair of protected attributes without affecting the primary risk score."""
    results = []
    for first, second in combinations(attributes, 2):
        temporary = data.copy()
        temporary["_intersection"] = (
            temporary[first].astype(str) + " × " + temporary[second].astype(str)
        )
        result = attribute_metrics(temporary, "_intersection", minimum_group_size)
        result["attribute"] = f"{first} × {second}"
        result["source_attributes"] = [first, second]
        results.append(result)
    return results


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
        "intersections": intersectional_metrics(
            data, selected_attributes, minimum_group_size
        ),
        "configuration": {
            "protected_attributes": selected_attributes,
            "minimum_group_size": minimum_group_size,
            "has_ground_truth": "qualified" in data.columns,
        },
        "certificate": certificate(results),
    }
