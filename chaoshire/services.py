"""Application services shared by the HTTP route layer."""
import io
from typing import Any

import numpy as np
import pandas as pd

from .config import DECISION_THRESHOLD
from .data import DEMO_DATA
from .metrics import audit, round4
from .models import (
    BIAS_FEATURES,
    FEATURE_DESCRIPTIONS,
    FEATURE_LABELS,
    LEGACY,
    MODEL_META,
    build_decisions,
    feature_components,
    get_model,
    score,
)
from .repository import save_audit
from .state import APPEALS, UPLOADED


def filtered_candidates(model: str = "legacy") -> dict[str, Any]:
    coefficients = get_model(model)
    decisions = build_decisions(coefficients)
    rejected = decisions[decisions["accepted"] == 0]
    components = feature_components(rejected)
    keys = [
        key for key, value in coefficients.items()
        if key != "intercept" and value != 0
    ]
    contribution_matrix = np.column_stack(
        [coefficients[key] * components[key].to_numpy(dtype=float) for key in keys]
    )
    reason_indexes = contribution_matrix.argmin(axis=1)
    reasons = [keys[index] for index in reason_indexes]
    reason_counts: dict[str, int] = {}
    for reason in reasons:
        label = FEATURE_LABELS[reason]
        reason_counts[label] = reason_counts.get(label, 0) + 1
    top_reasons = sorted(reason_counts.items(), key=lambda item: -item[1])[:8]

    by_gender = []
    for gender in sorted(rejected["gender"].unique()):
        subset = rejected[rejected["gender"] == gender]
        by_gender.append(
            {
                "group": str(gender),
                "rejected": int(len(subset)),
                "share": round4(
                    len(subset) / max(1, len(decisions[decisions["gender"] == gender]))
                ),
            }
        )

    sample = []
    for (_, row), reason in list(zip(rejected.iterrows(), reasons, strict=False))[:40]:
        sample.append(
            {
                "id": row["candidate_id"],
                "name": row["name"],
                "gender": row["gender"],
                "ethnicity": row["ethnicity"],
                "age_band": row["age_band"],
                "score": round4(row["score"]),
                "qualified": bool(row["qualified"]),
                "reason": reason,
                "reason_label": FEATURE_LABELS[reason],
                "bias_related": reason in BIAS_FEATURES,
            }
        )
    return {
        "total_rejected": int(len(rejected)),
        "qualified_missed": int(rejected["qualified"].astype(bool).sum()),
        "top_reasons": [
            {"label": label, "count": count} for label, count in top_reasons
        ],
        "by_gender": by_gender,
        "sample": sample,
    }


def explain_candidate(candidate_id: str, model: str = "legacy") -> dict[str, Any]:
    rows = DEMO_DATA[DEMO_DATA["candidate_id"] == candidate_id]
    if rows.empty:
        return {"error": f"Candidate {candidate_id} not found."}
    coefficients = get_model(model)
    components = feature_components(rows)
    contributions = []
    for feature, weight in coefficients.items():
        if feature == "intercept" or weight == 0:
            continue
        contributions.append(
            {
                "feature": feature,
                "label": FEATURE_LABELS[feature],
                "desc": FEATURE_DESCRIPTIONS[feature],
                "impact": round4(weight * float(components[feature].iloc[0])),
            }
        )
    candidate_score = round4(score(rows, coefficients)[0])
    accepted = bool(candidate_score >= DECISION_THRESHOLD)
    helped = sorted(
        [item for item in contributions if item["impact"] > 0],
        key=lambda item: -item["impact"],
    )[:3]
    hurt = sorted(
        [item for item in contributions if item["impact"] < 0],
        key=lambda item: item["impact"],
    )[:3]
    return {
        "candidate_id": candidate_id,
        "name": rows.iloc[0]["name"],
        "score": candidate_score,
        "decision": "Accepted" if accepted else "Rejected",
        "threshold": DECISION_THRESHOLD,
        "helped": helped,
        "hurt": hurt,
    }


def candidate_decision(candidate_id: str) -> dict[str, Any]:
    rows = DEMO_DATA[DEMO_DATA["candidate_id"] == candidate_id]
    if rows.empty:
        return {"error": f"Application {candidate_id} not found. Check the ID on your decision letter."}
    candidate_score = round4(score(rows, LEGACY)[0])
    accepted = candidate_score >= DECISION_THRESHOLD
    components = feature_components(rows)
    contributions = sorted(
        [
            {
                "label": FEATURE_LABELS[feature],
                "desc": FEATURE_DESCRIPTIONS[feature],
                "impact": round4(weight * float(components[feature].iloc[0])),
            }
            for feature, weight in LEGACY.items()
            if feature != "intercept" and weight != 0
        ],
        key=lambda item: item["impact"],
    )
    reasons = (
        [item for item in contributions if item["impact"] < 0][:3]
        if not accepted
        else [item for item in reversed(contributions) if item["impact"] > 0][:3]
    )
    return {
        "candidate_id": candidate_id,
        "name": rows.iloc[0]["name"],
        "status": "Accepted" if accepted else "Rejected",
        "score": candidate_score,
        "model": MODEL_META["legacy"]["title"],
        "reasons": reasons,
        "can_appeal": not accepted,
    }


def create_appeal(candidate_id: str, message: str) -> dict[str, Any]:
    rows = DEMO_DATA[DEMO_DATA["candidate_id"] == candidate_id]
    if rows.empty:
        return {"error": "Unknown candidate ID."}
    row = rows.iloc[0]
    rejected = score(rows, LEGACY)[0] < DECISION_THRESHOLD
    priority = (
        "HIGH — qualified candidate rejected"
        if bool(row["qualified"]) and rejected
        else "NORMAL"
    )
    record = {
        "id": len(APPEALS) + 1,
        "candidate_id": candidate_id,
        "name": row["name"],
        "gender": row["gender"],
        "message": message,
        "priority": priority,
        "status": "PENDING",
    }
    APPEALS.append(record)
    return {"ok": True, "appeal_id": record["id"], "priority": priority}


def list_appeals() -> dict[str, list[dict[str, Any]]]:
    return {"appeals": list(reversed(APPEALS))}


def mitigate(strategies: list[str]) -> dict[str, Any]:
    if not strategies:
        return {"error": "Select at least one strategy."}
    coefficients = dict(LEGACY)
    applied = []
    if "blind" in strategies:
        for feature in [
            "gender_M", "gender_NB", "eth_G2", "eth_G3", "age_36-50", "age_50+"
        ]:
            coefficients[feature] = 0.0
        applied.append("Blind screening — every protected-attribute weight forced to zero")
    if "proxy" in strategies:
        coefficients["prestige"] = 0.0
        coefficients["gap"] = round(coefficients["gap"] * 0.25, 4)
        applied.append("Proxy removal — college-prestige feature dropped; career-gap weight cut by 75%")

    scores = score(DEMO_DATA, coefficients)
    thresholds = np.full(len(DEMO_DATA), DECISION_THRESHOLD)
    if "calibrate" in strategies:
        for attribute in ["gender", "ethnicity", "age_band"]:
            selection_rates = {
                group: float((scores[DEMO_DATA[attribute] == group] >= DECISION_THRESHOLD).mean())
                for group in DEMO_DATA[attribute].unique()
            }
            target = max(selection_rates.values())
            for group in selection_rates:
                mask = (DEMO_DATA[attribute] == group).to_numpy()
                if target > 0 and mask.sum():
                    quantile = float(
                        np.quantile(scores[mask], max(0.0, min(1.0, 1 - target)))
                    )
                    thresholds[mask] = np.minimum(thresholds[mask], quantile)
        applied.append("Threshold calibration — per-group cutoffs aligned to the highest selection rate")

    before = audit(build_decisions(LEGACY))["certificate"]
    after = audit(build_decisions(coefficients, thresholds))
    return {"applied": applied, "before": before, "after": after}


def _normalise_name(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip().lower()


def _normalise_values(values: list[str]) -> set[str]:
    return {str(value).strip().lower() for value in values if str(value).strip()}


def upload_decisions(
    csv_text: str,
    audit_name: str = "Untitled CSV audit",
    decision_column: str = "decision",
    favorable_values: list[str] | None = None,
    qualification_column: str | None = None,
    qualified_values: list[str] | None = None,
    protected_attributes: list[str] | None = None,
    candidate_id_column: str | None = "candidate_id",
    minimum_group_size: int = 30,
) -> dict[str, Any]:
    """Validate and store a configurable model-decision export."""
    try:
        uploaded = pd.read_csv(io.StringIO(csv_text))
    except Exception as error:
        return {"error": f"Could not parse CSV: {error}"}

    if uploaded.empty:
        return {"error": "The CSV has headers but no data rows."}
    if len(uploaded) > 100_000:
        return {"error": "The public prototype accepts at most 100,000 rows per audit."}
    if len(uploaded.columns) > 100:
        return {"error": "The CSV has more than 100 columns; remove unused fields and retry."}

    normalised_columns = [str(column).strip().lower() for column in uploaded.columns]
    duplicates = sorted({column for column in normalised_columns if normalised_columns.count(column) > 1})
    if duplicates:
        return {"error": f"Duplicate columns after normalisation: {', '.join(duplicates)}."}
    uploaded.columns = normalised_columns

    decision = _normalise_name(decision_column)
    if decision not in uploaded.columns:
        return {
            "error": f"Decision column '{decision_column}' was not found.",
            "available_columns": normalised_columns,
        }
    favorable = _normalise_values(
        favorable_values or ["1", "true", "yes", "y", "accept", "accepted"]
    )
    if not favorable:
        return {"error": "Provide at least one favorable decision value."}

    warnings = []
    raw_decisions = uploaded[decision]
    if raw_decisions.isna().any():
        warnings.append(
            f"{int(raw_decisions.isna().sum())} rows have a missing decision and were treated as unfavorable."
        )
    uploaded["accepted"] = (
        raw_decisions.astype(str).str.strip().str.lower().isin(favorable).astype(int)
    )
    if uploaded["accepted"].nunique() < 2:
        warnings.append(
            "Only one decision class was found; disparity metrics may be uninformative."
        )

    qualification = _normalise_name(qualification_column)
    if qualification is None and "qualified" in uploaded.columns:
        qualification = "qualified"
    if qualification is not None:
        if qualification not in uploaded.columns:
            return {
                "error": f"Qualification column '{qualification_column}' was not found.",
                "available_columns": normalised_columns,
            }
        qualified = _normalise_values(qualified_values or ["1", "true", "yes", "y"])
        uploaded["qualified"] = (
            uploaded[qualification].astype(str).str.strip().str.lower().isin(qualified)
        )

    if protected_attributes is None:
        attributes = [
            attribute for attribute in ["gender", "ethnicity", "age_band"]
            if attribute in uploaded.columns
        ]
    else:
        attributes = list(
            dict.fromkeys(
                attribute
                for value in protected_attributes
                if (attribute := _normalise_name(value)) is not None
            )
        )
    if not attributes:
        return {
            "error": "Choose at least one protected attribute column.",
            "available_columns": normalised_columns,
        }
    missing_attributes = [attribute for attribute in attributes if attribute not in uploaded.columns]
    if missing_attributes:
        return {
            "error": f"Protected attribute columns not found: {', '.join(missing_attributes)}.",
            "available_columns": normalised_columns,
        }

    for attribute in attributes:
        missing_count = int(uploaded[attribute].isna().sum())
        values = uploaded[attribute].astype("string").str.strip().fillna("(missing)")
        values = values.mask(values == "", "(missing)")
        uploaded[attribute] = values.astype(str)
        group_count = int(uploaded[attribute].nunique())
        if group_count > 100:
            return {
                "error": f"'{attribute}' has {group_count} groups and looks like an identifier, not a protected attribute."
            }
        if group_count < 2:
            warnings.append(f"'{attribute}' contains only one group; no between-group comparison is possible.")
        if missing_count:
            warnings.append(
                f"'{attribute}' has {missing_count} missing values, reported as a separate '(missing)' group."
            )

    candidate_id = _normalise_name(candidate_id_column)
    if candidate_id and candidate_id not in uploaded.columns:
        candidate_id = None
        warnings.append("Candidate ID column was not found; row numbers will identify records.")

    metadata = {
        "decision_column": decision,
        "favorable_values": sorted(favorable),
        "qualification_column": qualification,
        "protected_attributes": attributes,
        "candidate_id_column": candidate_id,
        "minimum_group_size": minimum_group_size,
        "warnings": warnings,
    }
    result = audit(
        uploaded.copy(),
        attributes=attributes,
        minimum_group_size=minimum_group_size,
    )
    result["upload"] = metadata
    safe_name = audit_name.strip() or "Untitled CSV audit"
    audit_id = save_audit(result, safe_name, metadata)

    UPLOADED["df"] = uploaded
    UPLOADED["metadata"] = metadata
    UPLOADED["audit"] = result
    return {
        "ok": True,
        "audit_id": audit_id,
        "audit_name": safe_name,
        "created_at": result["created_at"],
        "rows": int(len(uploaded)),
        "columns": normalised_columns,
        "attributes_found": attributes,
        "has_ground_truth": "qualified" in uploaded.columns,
        "configuration": metadata,
        "warnings": warnings,
    }


def uploaded_audit() -> dict[str, Any]:
    result = UPLOADED["audit"]
    if result is None:
        return {"error": "No dataset uploaded yet."}
    return result


def sample_csv() -> str:
    return (
        build_decisions(LEGACY)[
            ["candidate_id", "gender", "ethnicity", "age_band", "accepted", "qualified"]
        ]
        .rename(columns={"accepted": "decision"})
        .head(200)
        .to_csv(index=False)
    )
