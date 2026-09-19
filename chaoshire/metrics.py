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
    groups: list[dict[str, Any]] = []
    has_truth = "qualified" in data.columns
    for group_value in sorted(data[attribute].unique()):
        subset = data[data[attribute] == group_value]
        count = int(len(subset))
        selected = int(subset["accepted"].sum())
        row: dict[str, Any] = {
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
            row["tpr"] = round4(qualified_selected / qualified_count) if qualified_count else None
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
    true_positive_rates = [group["tpr"] for group in reliable_groups if group["tpr"] is not None]
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
            "significant_at_0_05": bool(test["p_value"] < 0.05 and comparison_reliable),
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


def assessability(
    data: pd.DataFrame,
    attribute_results: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Report whether group-disparity metrics can carry any meaning.

    A model that selects everybody or nobody has no decision variation to
    compare, and an attribute without two reliable groups has no between-group
    comparison. In both cases the risk score would otherwise report a perfect
    grade for evidence that does not exist, so the audit is marked
    "not assessable" instead.
    """
    reasons: list[str] = []
    count = int(len(data))
    if count == 0:
        reasons.append("The audit contains no candidate rows.")
        return False, reasons
    accepted = int(data["accepted"].sum())
    if accepted == 0:
        reasons.append(
            "No candidate was selected, so selection-rate comparisons carry no information."
        )
    elif accepted == count:
        reasons.append(
            "Every candidate was selected, so selection-rate comparisons carry no information."
        )
    if not attribute_results:
        reasons.append("No protected attribute was supplied or detected in the dataset.")
    else:
        comparable = [
            result
            for result in attribute_results
            if len([group for group in result["groups"] if not group["low_n"]]) >= 2
        ]
        if not comparable:
            reasons.append(
                "No protected attribute has at least two reliable groups, so no "
                "between-group comparison is possible."
            )
    return (not reasons), reasons


# Fairness risk-score component weights. These are the *only* things the score
# measures. An earlier revision added a flat 15-point "Transparency (XAI +
# appeals)" component that every audited model received automatically because
# the ChaosHire platform happens to have an appeals tab; that scored the tool
# instead of the model under audit, so it is reported below as an explicitly
# unscored disclosure instead.
DI_POINTS = 40
PARITY_POINTS = 20
OPPORTUNITY_POINTS = 25
FULL_BASIS_POINTS = DI_POINTS + PARITY_POINTS + OPPORTUNITY_POINTS
SELECTION_ONLY_BASIS_POINTS = DI_POINTS + PARITY_POINTS
SCORE_SCALE = 100

GRADE_BANDS = ((90, "A"), (75, "B"), (60, "C"), (45, "D"))

PLATFORM_DISCLOSURE = {
    "scored": False,
    "included_in_total": False,
    "why_unscored": (
        "These describe the ChaosHire platform, not the model under audit. Awarding "
        "points for them would give every audited model the same credit for a feature "
        "it does not own, and would let a transparent but badly biased model score "
        "higher on a fairness scale. They are disclosed, not scored."
    ),
    "capabilities": [
        {
            "label": "Per-candidate contribution explanations (XAI)",
            "available_for": (
                "Bundled reference models, whose coefficients ChaosHire holds. An "
                "uploaded decision CSV carries no model internals, so no explanation "
                "of an individual decision is possible."
            ),
        },
        {"label": "Candidate appeal workflow", "available_for": "All audits"},
        {"label": "Downloadable aggregate evidence bundle", "available_for": "All audits"},
        {"label": "Automated release gate", "available_for": "Bundled reference models"},
    ],
}


def _grade(total: int) -> str:
    for floor, grade in GRADE_BANDS:
        if total >= floor:
            return grade
    return "F"


def certificate(
    attribute_results: list[dict[str, Any]],
    assessable: bool = True,
    reasons: list[str] | None = None,
) -> dict[str, Any]:
    """Score group-fairness outcomes on a 0-100 scale over measured components.

    The total is ``measured / available * 100``. ``available`` is 85 when ground
    truth exists (disparate impact + parity + equal opportunity) and 60 when it
    does not (disparate impact + parity only), so a score computed without
    qualification labels rests on strictly less evidence. That is reported
    explicitly through ``basis`` and ``comparable_with_full_basis`` rather than
    being hidden behind an identical-looking number.
    """
    if not assessable or not attribute_results:
        return {
            "total": 0,
            "grade": "N/A",
            "assessable": False,
            "reasons": list(reasons or ["No protected attribute was supplied or detected."]),
            "measured_points": 0.0,
            "available_points": 0,
            "scale": SCORE_SCALE,
            "basis": "none",
            "basis_note": "No group-fairness component could be measured.",
            "comparable_with_full_basis": False,
            "components": [
                {"label": "Disparate impact (4/5ths rule)", "pts": 0.0, "max": DI_POINTS},
                {"label": "Demographic parity gap", "pts": 0.0, "max": PARITY_POINTS},
                {"label": "Equal opportunity gap", "pts": 0.0, "max": OPPORTUNITY_POINTS},
            ],
            "unmeasured_components": [],
            "platform_disclosure": PLATFORM_DISCLOSURE,
        }

    impacts = [result["disparate_impact"] for result in attribute_results]
    parity_gaps = [result["parity_gap"] for result in attribute_results]
    opportunity_gaps = [
        result["eq_opp_gap"] for result in attribute_results if result["eq_opp_gap"] is not None
    ]
    impact_points = DI_POINTS * min(min(impacts) / 0.8, 1.0)
    parity_points = PARITY_POINTS * max(0.0, 1 - max(parity_gaps) / 0.15)

    components = [
        {
            "label": "Disparate impact (4/5ths rule)",
            "pts": round(impact_points, 1),
            "max": DI_POINTS,
        },
        {"label": "Demographic parity gap", "pts": round(parity_points, 1), "max": PARITY_POINTS},
    ]
    unmeasured: list[dict[str, Any]] = []
    if opportunity_gaps:
        opportunity_points = OPPORTUNITY_POINTS * max(0.0, 1 - max(opportunity_gaps) / 0.2)
        components.append(
            {
                "label": "Equal opportunity gap",
                "pts": round(opportunity_points, 1),
                "max": OPPORTUNITY_POINTS,
            }
        )
        measured = impact_points + parity_points + opportunity_points
        available = FULL_BASIS_POINTS
        basis = "full"
        basis_note = (
            "Disparate impact, demographic parity and equal opportunity were all "
            "measurable: the dataset carries ground-truth qualification labels."
        )
    else:
        unmeasured.append(
            {
                "label": "Equal opportunity gap",
                "max": OPPORTUNITY_POINTS,
                "reason": "No ground-truth qualification column, so true-positive rates are unknown.",
            }
        )
        measured = impact_points + parity_points
        available = SELECTION_ONLY_BASIS_POINTS
        basis = "selection-rate-only"
        basis_note = (
            "Only selection-rate components were measurable; equal opportunity was "
            "excluded because the dataset has no ground-truth qualification labels. "
            "This score rests on less evidence than a full-basis score and the two "
            "must not be ranked against each other."
        )

    total = int(max(0, min(SCORE_SCALE, round(measured / available * SCORE_SCALE))))
    return {
        "total": total,
        "grade": _grade(total),
        "assessable": True,
        "reasons": [],
        "measured_points": round(measured, 1),
        "available_points": available,
        "scale": SCORE_SCALE,
        "basis": basis,
        "basis_note": basis_note,
        "comparable_with_full_basis": basis == "full",
        "components": components,
        "unmeasured_components": unmeasured,
        "platform_disclosure": PLATFORM_DISCLOSURE,
    }


def audit(
    data: pd.DataFrame,
    attributes: list[str] | None = None,
    minimum_group_size: int = MIN_CELL_SIZE,
) -> dict[str, Any]:
    selected_attributes = attributes or [
        attribute for attribute in ["gender", "ethnicity", "age_band"] if attribute in data.columns
    ]
    results = [
        attribute_metrics(data, attribute, minimum_group_size) for attribute in selected_attributes
    ]
    count = int(len(data))
    accepted = int(data["accepted"].sum())
    assessable, reasons = assessability(data, results)
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
        "intersections": intersectional_metrics(data, selected_attributes, minimum_group_size),
        "configuration": {
            "protected_attributes": selected_attributes,
            "minimum_group_size": minimum_group_size,
            "has_ground_truth": "qualified" in data.columns,
        },
        "certificate": certificate(results, assessable, reasons),
    }
