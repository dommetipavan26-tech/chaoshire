"""SHAP-compatible explanation adapter for linear decision models.

Produces feature-attribution vectors in the format consumed by the SHAP
library (``base_value`` + per-feature ``values``), so downstream tooling —
force plots, summary plots, dependence plots — works without a custom
parser. The adapter is model-agnostic within the ChaosHire reference-model
contract: it reads the coefficient dictionary and the per-candidate feature
matrix and emits the same structure a ``shap.LinearExplainer`` would.

Why this matters for a fairness auditor
---------------------------------------
SHAP is the de facto standard for model-agnostic feature attribution. An
auditor who wants to compare ChaosHire's native contribution breakdown
with a SHAP force plot, or who wants to pipe ChaosHire explanations into
a fairness dashboard built around SHAP, should not have to write a
translation layer. This adapter ships that translation as a first-class
contract.

The adapter does NOT depend on the ``shap`` package itself — it produces
the same JSON shape that ``shap.Explanation`` serialises to.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .data import DEMO_DATA
from .models import FEATURE_LABELS, Coefficients, feature_components, get_model, score


def shap_explanation(candidate_id: str, model: str = "legacy") -> dict[str, Any]:
    """Return a SHAP-compatible explanation for one candidate.

    The output matches the shape of ``shap.Explanation`` as serialised by
    ``shap`` version 0.43+:

    ``base_value``
        The model intercept (expected value when every feature is zero).
    ``values``
        Per-feature attribution: ``coefficient × feature_value`` for each
        active feature, in the same order as ``feature_names``.
    ``feature_names``
        Human-readable labels matching ChaosHire's dashboard vocabulary.
    ``data``
        The raw feature values used for the attribution, normalised to the
        same [0, 1] / integer scale the model sees.
    ``output``
        The model's raw score (before the decision threshold).
    ``candidate_id``
        Echo of the input identifier so the caller can link back.
    """
    rows = DEMO_DATA[DEMO_DATA["candidate_id"] == candidate_id]
    if rows.empty:
        return {"error": f"Candidate {candidate_id} not found."}
    coefficients = get_model(model)
    return _explain_row(rows, coefficients, candidate_id, model)


def shap_batch(candidate_ids: list[str], model: str = "legacy") -> dict[str, Any]:
    """Return SHAP-compatible explanations for a list of candidates.

    Errors are included inline (``{"error": "...", "candidate_id": "..."}``)
    so the caller can render a partial result without a second round trip.
    """
    coefficients = get_model(model)
    explanations: list[dict[str, Any]] = []
    for candidate_id in candidate_ids:
        rows = DEMO_DATA[DEMO_DATA["candidate_id"] == candidate_id]
        if rows.empty:
            explanations.append(
                {"error": f"Candidate {candidate_id} not found.", "candidate_id": candidate_id}
            )
            continue
        explanations.append(_explain_row(rows, coefficients, candidate_id, model))
    return {
        "model": model,
        "count": len(explanations),
        "explanations": explanations,
        "adapter": "shap-compatible",
        "format_version": "1.0",
    }


def _explain_row(
    rows: pd.DataFrame,
    coefficients: Coefficients,
    candidate_id: str,
    model: str,
) -> dict[str, Any]:
    """Build the SHAP-compatible dict for one row."""
    components = feature_components(rows)
    base_value = float(coefficients.get("intercept", 0.0))
    feature_names: list[str] = []
    values: list[float] = []
    data: list[float] = []
    for feature, weight in coefficients.items():
        if feature == "intercept" or weight == 0:
            continue
        component_value = float(components[feature].iloc[0])
        feature_names.append(FEATURE_LABELS.get(feature, feature))
        values.append(round(weight * component_value, 6))
        data.append(round(component_value, 6))
    output_score = float(score(rows, coefficients)[0])
    return {
        "candidate_id": candidate_id,
        "model": model,
        "adapter": "shap-compatible",
        "format_version": "1.0",
        "base_value": round(base_value, 6),
        "values": values,
        "feature_names": feature_names,
        "data": data,
        "output": round(output_score, 6),
        "expected_value": round(base_value + sum(values), 6),
    }


def adapter_catalog_entry() -> dict[str, Any]:
    """Document the SHAP adapter for ``/api/adapters``."""
    return {
        "id": "shap-compatible",
        "status": "available",
        "use": (
            "SHAP-compatible feature-attribution vectors for any reference model. "
            "GET /api/explain/shap/{candidate_id}?model=... or POST "
            "/api/explain/shap/batch with {candidate_ids: [...], model: ...}."
        ),
        "format": "shap.Explanation-compatible JSON (base_value + values + feature_names)",
        "depends_on": "shap (optional — the adapter produces the same JSON shape without importing shap)",
    }
