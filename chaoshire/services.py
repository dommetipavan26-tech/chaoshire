"""Application services shared by the HTTP route layer."""

import io
import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime
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
    Coefficients,
    build_decisions,
    feature_components,
    get_model,
    score,
)
from .redaction import redact_appeal, redaction_notice
from .repository import save_audit
from .state import UPLOADED, UPLOADED_LOCK, appeals_snapshot, append_appeal

#: Failure detail that must never reach a response body stays here instead.
logger = logging.getLogger(__name__)


def filtered_candidates(model: str = "legacy") -> dict[str, Any]:
    coefficients = get_model(model)
    decisions = build_decisions(coefficients)
    rejected = decisions[decisions["accepted"] == 0]
    components = feature_components(rejected)
    keys = [key for key, value in coefficients.items() if key != "intercept" and value != 0]
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
        "top_reasons": [{"label": label, "count": count} for label, count in top_reasons],
        "by_gender": by_gender,
        "sample": sample,
    }


def explain_candidate(candidate_id: str, model: str = "legacy") -> dict[str, Any]:
    rows = DEMO_DATA[DEMO_DATA["candidate_id"] == candidate_id]
    if rows.empty:
        return {"error": f"Candidate {candidate_id} not found."}
    coefficients = get_model(model)
    components = feature_components(rows)
    contributions: list[dict[str, Any]] = []
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
        return {
            "error": f"Application {candidate_id} not found. Check the ID on your decision letter."
        }
    candidate_score = round4(score(rows, LEGACY)[0])
    accepted = candidate_score >= DECISION_THRESHOLD
    components = feature_components(rows)
    contributions: list[dict[str, Any]] = sorted(
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


def create_appeal(
    candidate_id: str,
    message: str,
    *,
    protected: bool = False,
) -> dict[str, Any]:
    rows = DEMO_DATA[DEMO_DATA["candidate_id"] == candidate_id]
    if rows.empty:
        return {"error": "Unknown candidate ID."}
    row = rows.iloc[0]
    rejected = score(rows, LEGACY)[0] < DECISION_THRESHOLD
    priority = (
        "HIGH — qualified candidate rejected" if bool(row["qualified"]) and rejected else "NORMAL"
    )
    record = append_appeal(
        {
            "candidate_id": candidate_id,
            "name": row["name"],
            "gender": row["gender"],
            "message": message,
            "priority": priority,
            "status": "PENDING",
            "protected": bool(protected),
            "source": "operator" if protected else "anonymous",
        }
    )
    return {"ok": True, "appeal_id": record["id"], "priority": priority}


def list_appeals() -> dict[str, Any]:
    """Redacted, newest-first view of the appeal queue.

    The public listing is read by every visitor (it feeds the demo's HR review
    queue), so it serves redacted copies of each record and discloses the
    redaction rules in the same payload — see :mod:`chaoshire.redaction`.
    """
    snapshot = appeals_snapshot()
    snapshot["appeals"] = [redact_appeal(record) for record in snapshot["appeals"]]
    snapshot["redaction"] = redaction_notice()
    return snapshot


# ---------------------------------------------------------------------------
# Mitigation strategies
# ---------------------------------------------------------------------------
# Only controls a United States employer may actually apply are offered as
# mitigations. Per-group decision cutoffs are deliberately *not* one of them:
# 42 U.S.C. § 2000e-2(l), added by the Civil Rights Act of 1991, makes it an
# unlawful employment practice to "adjust the scores of, use different cutoff
# scores for, or otherwise alter the results of, employment related tests on the
# basis of race, color, religion, sex, or national origin."
#
# The technique is still implemented (``_per_group_thresholds``) because seeing
# how much of an apparent fairness gain is manufactured by moving the bar per
# group is genuinely instructive — but only as an opt-in research contrast that
# is reported separately and never folded into the mitigation result.
MITIGATION_STRATEGIES = ("blind", "proxy")

THRESHOLD_CONTRAST_STATUTE = "42 U.S.C. § 2000e-2(l)"
THRESHOLD_CONTRAST_URL = "https://www.law.cornell.edu/uscode/text/42/2000e-2"
THRESHOLD_CONTRAST_TEXT = (
    "it shall be an unlawful employment practice for a respondent, in the context of "
    "admission to, or employment in, a program of education or training, to adjust the "
    "scores of, use different cutoff scores for, or otherwise alter the results of, "
    "employment related tests on the basis of race, color, religion, sex, or national "
    "origin."
)
THRESHOLD_CONTRAST_NOTICE = (
    "Per-group decision cutoffs are NOT an available remediation. In United States "
    f"employment testing, {THRESHOLD_CONTRAST_STATUTE} (Civil Rights Act of 1991) makes "
    "it unlawful to use different cutoff scores for, or otherwise alter the results of, "
    "employment-related tests on the basis of race, color, religion, sex, or national "
    "origin — the same protected characteristics this contrast adjusts for. ChaosHire "
    "implements it only so a reviewer can see how much of an apparent fairness "
    "improvement is manufactured by moving the bar per group instead of fixing the "
    "model. The parity it produces is arithmetic, not lawful, and it must never be "
    "applied to a real hiring process. ChaosHire is not legal advice; jurisdiction "
    "matters and qualified counsel must review any remediation."
)


def threshold_contrast_disclosure() -> dict[str, Any]:
    """The statutory warning that always accompanies the threshold contrast."""
    return {
        "id": "threshold_contrast",
        "label": "Per-group threshold contrast (research only — not a remediation)",
        "research_only": True,
        "is_mitigation": False,
        "prohibited_in_us_employment_testing": True,
        "statute": THRESHOLD_CONTRAST_STATUTE,
        "statute_name": "Civil Rights Act of 1991, § 106",
        "statute_url": THRESHOLD_CONTRAST_URL,
        "statutory_text": THRESHOLD_CONTRAST_TEXT,
        "notice": THRESHOLD_CONTRAST_NOTICE,
        "not_legal_advice": True,
    }


def _per_group_thresholds(coefficients: Coefficients) -> np.ndarray:
    """Cutoffs that equalise selection rates across gender, ethnicity and age."""
    scores = score(DEMO_DATA, coefficients)
    thresholds = np.full(len(DEMO_DATA), DECISION_THRESHOLD)
    for attribute in ["gender", "ethnicity", "age_band"]:
        selection_rates = {
            group: float((scores[DEMO_DATA[attribute] == group] >= DECISION_THRESHOLD).mean())
            for group in DEMO_DATA[attribute].unique()
        }
        target = max(selection_rates.values())
        for group in selection_rates:
            mask = (DEMO_DATA[attribute] == group).to_numpy()
            if target > 0 and mask.sum():
                quantile = float(np.quantile(scores[mask], max(0.0, min(1.0, 1 - target))))
                thresholds[mask] = np.minimum(thresholds[mask], quantile)
    return thresholds


def mitigate(
    strategies: Sequence[str],
    threshold_contrast_acknowledged: bool | None = None,
) -> dict[str, Any]:
    """Simulate lawful post-processing controls and re-audit the fixture.

    ``threshold_contrast_acknowledged`` is tri-state: ``None`` skips the
    research-only per-group cutoff contrast, ``False`` requests it without the
    required acknowledgement (refused, with the statute quoted back), and
    ``True`` runs it. Its result is returned under a separate
    ``research_contrast`` key and is never folded into ``after``.
    """
    if not strategies and threshold_contrast_acknowledged is None:
        return {"error": "Select at least one strategy."}
    unknown = [strategy for strategy in strategies if strategy not in MITIGATION_STRATEGIES]
    if unknown:
        names = ", ".join(sorted(set(unknown)))
        message = f"Unknown mitigation strategies: {names}."
        if "calibrate" in unknown:
            message += (
                " 'calibrate' was removed from the one-click mitigation set: using "
                "different cutoff scores by protected group is unlawful in United "
                f"States employment testing under {THRESHOLD_CONTRAST_STATUTE}. It "
                "remains available as an opt-in research contrast by sending "
                "threshold_contrast_acknowledged=true."
            )
        return {
            "error": message,
            "available_strategies": list(MITIGATION_STRATEGIES),
            "threshold_contrast": threshold_contrast_disclosure(),
        }
    if threshold_contrast_acknowledged is False:
        return {
            "error": THRESHOLD_CONTRAST_NOTICE,
            "how_to_run_as_research": (
                "Resend with threshold_contrast_acknowledged=true. The result is "
                "returned under 'research_contrast' and is excluded from 'after'."
            ),
            "threshold_contrast": threshold_contrast_disclosure(),
        }

    coefficients = dict(LEGACY)
    applied = []
    if "blind" in strategies:
        for feature in ["gender_M", "gender_NB", "eth_G2", "eth_G3", "age_36-50", "age_50+"]:
            coefficients[feature] = 0.0
        applied.append("Blind screening — every protected-attribute weight forced to zero")
    if "proxy" in strategies:
        coefficients["prestige"] = 0.0
        coefficients["gap"] = round(coefficients["gap"] * 0.25, 4)
        applied.append(
            "Proxy removal — college-prestige feature dropped; career-gap weight cut by 75%"
        )

    payload: dict[str, Any] = {
        "applied": applied,
        "model": MODEL_META["legacy"],
        "before": audit(build_decisions(LEGACY)),
        "after": audit(build_decisions(coefficients)),
        "available_strategies": list(MITIGATION_STRATEGIES),
        "excluded_controls": {"threshold_calibration": threshold_contrast_disclosure()},
    }
    if threshold_contrast_acknowledged:
        thresholds = _per_group_thresholds(coefficients)
        payload["research_contrast"] = {
            **threshold_contrast_disclosure(),
            "applied": "Per-group decision cutoffs aligned to the highest group selection rate",
            "after": audit(build_decisions(coefficients, thresholds)),
        }
    return payload


AUDIT_NAME_MAX_LENGTH = 60
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


def sanitise_audit_name(value: str | None) -> str:
    """Reduce an operator-supplied audit label to safe, displayable text.

    The name is persisted and shown to every visitor of the audit history, so
    control characters are dropped, whitespace is collapsed, and the length is
    capped independently of the request schema. An empty result falls back to a
    neutral label rather than an empty string.
    """
    # Control characters become spaces first, then whitespace runs collapse, so
    # a newline inside a name separates words instead of silently deleting them.
    cleaned = _WHITESPACE.sub(" ", _CONTROL_CHARS.sub(" ", str(value or ""))).strip()
    return cleaned[:AUDIT_NAME_MAX_LENGTH].strip() or "Untitled CSV audit"


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
    publish: bool = True,
) -> dict[str, Any]:
    """Validate and audit a configurable model-decision export.

    ``publish=True`` (authenticated callers only) writes the aggregate result to
    the persistent audit history and makes it the shared ``dataset=uploaded``
    artifact. ``publish=False`` computes exactly the same audit and returns it
    inline without persisting anything or touching the shared slot, so an
    anonymous visitor to a public deployment cannot push an attacker-chosen
    audit name into the history that every other visitor reads.
    """
    try:
        uploaded = pd.read_csv(io.StringIO(csv_text))
    except Exception as error:
        # A pandas/CSV parser message can quote buffer contents, dialect guesses
        # and file positions, so the raw text stays server-side. The caller gets
        # the failure category and the exception class, which is enough to tell a
        # malformed upload from an unsupported encoding.
        logger.warning("CSV parse failed for upload: %r", error)
        return {
            "error": (
                f"Could not parse the uploaded CSV ({type(error).__name__}). "
                "Expected UTF-8 text with a header row and at least one decision column."
            )
        }

    if uploaded.empty:
        return {"error": "The CSV has headers but no data rows."}
    if len(uploaded) > 100_000:
        return {"error": "The public prototype accepts at most 100,000 rows per audit."}
    if len(uploaded.columns) > 100:
        return {"error": "The CSV has more than 100 columns; remove unused fields and retry."}

    normalised_columns = [str(column).strip().lower() for column in uploaded.columns]
    duplicates = sorted(
        {column for column in normalised_columns if normalised_columns.count(column) > 1}
    )
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
            attribute
            for attribute in ["gender", "ethnicity", "age_band"]
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
    missing_attributes = [
        attribute for attribute in attributes if attribute not in uploaded.columns
    ]
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
            warnings.append(
                f"'{attribute}' contains only one group; no between-group comparison is possible."
            )
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
    safe_name = sanitise_audit_name(audit_name)
    if safe_name != str(audit_name or "").strip():
        warnings.append(
            f"Audit name was normalised to '{safe_name}' (control characters removed, "
            f"whitespace collapsed, {AUDIT_NAME_MAX_LENGTH}-character cap)."
        )

    audit_id: str | None
    if publish:
        audit_id = save_audit(result, safe_name, metadata)
        with UPLOADED_LOCK:
            UPLOADED["df"] = uploaded
            UPLOADED["metadata"] = metadata
            UPLOADED["audit"] = result
    else:
        audit_id = None
        result["audit_id"] = None
        result["audit_name"] = safe_name
        result["created_at"] = datetime.now(UTC).isoformat()
        result["source"] = "uploaded_csv_unpublished"

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
        "published": publish,
        "publishing_note": (
            "Saved to the shared audit history."
            if publish
            else "Returned to you only. Unauthenticated uploads are not published to the "
            "shared audit history; send the deployment's X-API-Key to publish."
        ),
        "audit": result,
    }


def uploaded_audit() -> dict[str, Any]:
    """Return the most recently uploaded aggregate audit.

    The prototype keeps a single shared slot, so on a public deployment this is
    the latest upload made by *any* visitor. Only aggregate metrics are exposed;
    raw rows never leave the uploading process's memory.
    """
    with UPLOADED_LOCK:
        result = UPLOADED["audit"]
    if result is None:
        return {
            "error": (
                "No published dataset is available. Only uploads authenticated with the "
                "deployment's CHAOSHIRE_API_KEY are published to this shared slot; an "
                "anonymous upload is returned directly to the uploader instead."
            )
        }
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
