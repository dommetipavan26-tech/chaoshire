"""Build-time trainer for the bundled ``trained`` reference model.

ChaosHire ships three reference models: the hand-written ``legacy`` and
``fair`` coefficient sets, and ``trained`` — a logistic regression actually
fitted to the deterministic demo fixture with scikit-learn.

Design rules that keep the platform honest and reproducible:

* **Blind and proxy-free inputs.** Protected attributes (gender, ethnicity, age
  band) are excluded from the training features, and so are the two
  "neutral" résumé signals that are known proxy risks — college prestige (a
  socioeconomic proxy correlated with community) and career gap (a caregiver
  proxy). The fixture's ``qualified`` label never uses them, so they carry no
  predictive signal; the original v3 fit gave them near-zero weight, including
  a meaningless *positive* weight on career gaps. Dropping them follows the
  platform's own proxy-removal mitigation. The artifact loader rejects any
  weight on either group of features.
* **One global cost-sensitive cutoff, selected transparently for the synthetic
  fairness demo.** A wrongly rejected qualified candidate is lost at the first
  screen, while a wrongly advanced candidate receives human review. The model
  uses the Bayes-optimal cutoff ``P(qualified) >= 1 / (1 + cost)`` for one
  global cost ratio, never a per-group threshold (42 U.S.C. § 2000e-2(l)). The
  current 3:1 operating point was selected from a fixed grid on 49 deterministic
  synthetic tuning populations, subject to a minimum 0.80 mean-accuracy guardrail,
  then validated on a disjoint 50-population holdout. It is not a real-world cost
  estimate or evidence of fair hiring outcomes.
* **Why the upgrade was needed.** A model fitted to the label reproduces the
  label's group gaps: by sampling chance the fixture's ``qualified`` rate
  differs between groups, and a perfect predictor of it scores 68/C.
  :func:`disparity_diagnostics` reports this at runtime without scikit-learn;
  :func:`policy_study` reproduces the threshold selection, and
  :func:`holdout_comparison` evaluates the frozen choice on synthetic populations
  the policy study did not use.
* Training is a **build-time tool**. The fitted coefficients are affinely
  calibrated onto the platform's [0, 1] score convention (the cost-sensitive
  probability cutoff lands exactly on ``DECISION_THRESHOLD``) and pinned to
  ``chaoshire/artifacts/trained_model.json`` with a SHA-256 digest.
* Runtime code only ever loads the pinned artifact, so production keeps its
  lightweight dependency set and the published numbers cannot drift when
  scikit-learn is upgraded. ``python -m chaoshire train --check`` re-fits the
  model and fails when fresh training drifts from the artifact.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import DECISION_THRESHOLD, DEMO_SEED
from .data import DEMO_DATA
from .models import Coefficients, feature_components

LABEL_COLUMN = "qualified"
MERIT_FEATURES: tuple[str, ...] = ("skills", "experience", "education", "certs")
PROXY_FEATURES: tuple[str, ...] = ("prestige", "gap")
TRAIN_FEATURES: tuple[str, ...] = MERIT_FEATURES
PROTECTED_FEATURES: tuple[str, ...] = (
    "gender_M",
    "gender_NB",
    "eth_G2",
    "eth_G3",
    "age_36-50",
    "age_50+",
)
#: Operating point for the fairness-prioritised synthetic reference model.
#: One global cost-sensitive cutoff is selected from a fixed candidate grid on
#: deterministic synthetic tuning populations, subject to a minimum mean
#: accuracy guardrail. This is not a real-world cost estimate or approval to use
#: the model for employment decisions.
FALSE_REJECTION_COST = 3.0
POLICY_COST_CANDIDATES: tuple[float, ...] = (2.0, 2.5, 3.0, 3.5, 4.0)
POLICY_MINIMUM_MEAN_ACCURACY = 0.80
POLICY_TUNING_SEEDS: tuple[int, ...] = tuple(seed for seed in range(1, 51) if seed != DEMO_SEED)
POLICY_HOLDOUT_SEEDS: tuple[int, ...] = tuple(range(51, 101))
POLICY_SELECTION_RULE = (
    "Select the candidate with the highest mean fairness risk score among fixed "
    "global cost ratios whose mean accuracy is at least 0.80 on the 49 synthetic "
    "tuning populations; validate once on the disjoint 50-population holdout."
)
MODEL_VERSION = 4
ALGORITHM = "LogisticRegression(C=1.0, solver='lbfgs', max_iter=1000)"


def probability_cutoff(false_rejection_cost: float = FALSE_REJECTION_COST) -> float:
    """Bayes-optimal acceptance cutoff on P(qualified) for the given cost ratio."""
    if false_rejection_cost <= 0:
        raise ValueError("false_rejection_cost must be positive")
    return 1.0 / (1.0 + false_rejection_cost)


PROBABILITY_CUTOFF = probability_cutoff()
CALIBRATION = (
    f"affine; the cost-sensitive cutoff P(qualified) >= {PROBABILITY_CUTOFF:.4f} "
    f"(false rejection cost {FALSE_REJECTION_COST:g}x a false acceptance) is mapped "
    f"onto the platform decision threshold {DECISION_THRESHOLD} and the observed "
    "score range is scaled to fit inside [0, 1]"
)
DECISION_POLICY = {
    "false_rejection_cost": FALSE_REJECTION_COST,
    "probability_cutoff": round(PROBABILITY_CUTOFF, 6),
    "cutoff_scope": "one global cutoff for every candidate; never per group",
    "rationale": (
        "First-round screen: a wrongly rejected qualified candidate is lost, while a "
        "wrongly advanced candidate receives human review. The 3:1 operating point was "
        "selected on synthetic tuning populations to prioritise group fairness while "
        "keeping mean accuracy at or above 0.80; this is not a real-world cost estimate."
    ),
    "selection_method": POLICY_SELECTION_RULE,
    "candidate_false_rejection_costs": list(POLICY_COST_CANDIDATES),
    "minimum_tuning_mean_accuracy": POLICY_MINIMUM_MEAN_ACCURACY,
    "tuning_seeds": list(POLICY_TUNING_SEEDS),
    "holdout_seeds": list(POLICY_HOLDOUT_SEEDS),
}
#: The original v3 configuration (proxies kept, error-rate cutoff 0.5), kept
#: reproducible as the before/after baseline. See :func:`original_v3_coefficients`.
ORIGINAL_V3_FEATURES: tuple[str, ...] = MERIT_FEATURES + PROXY_FEATURES
ORIGINAL_V3_FALSE_REJECTION_COST = 1.0
#: The original v3 coefficients as pinned before the upgrade (sklearn 1.9.1).
#: Stored so the before/after comparison runs at runtime without scikit-learn.
ORIGINAL_V3_COEFFICIENTS: Coefficients = {
    "skills": 0.550258,
    "experience": 0.343499,
    "education": 0.245529,
    "certs": 0.161015,
    "prestige": 0.011506,
    "gap": 0.029778,
    "intercept": -0.304035,
    "gender_M": 0.0,
    "gender_NB": 0.0,
    "eth_G2": 0.0,
    "eth_G3": 0.0,
    "age_36-50": 0.0,
    "age_50+": 0.0,
}
#: Last pinned TalentFit v3 coefficients (merit-only, 2:1 global cost cutoff).
#: Retained as a frozen comparator for the v4 operating-point change.
PREVIOUS_TALENTFIT_V3_COEFFICIENTS: Coefficients = {
    "skills": 0.560542,
    "experience": 0.345054,
    "education": 0.248977,
    "certs": 0.165299,
    "intercept": -0.257049,
    "prestige": 0.0,
    "gap": 0.0,
    "gender_M": 0.0,
    "gender_NB": 0.0,
    "eth_G2": 0.0,
    "eth_G3": 0.0,
    "age_36-50": 0.0,
    "age_50+": 0.0,
}
# Fresh training must reproduce at least this share of the pinned decisions,
# otherwise `train --check` reports drift. Loose enough to tolerate optimizer
# jitter across scikit-learn versions, tight enough to catch data changes.
AGREEMENT_FLOOR = 0.90

ARTIFACT_PATH = Path(__file__).resolve().parent / "artifacts" / "trained_model.json"


def build_design_matrix(
    data: pd.DataFrame, features: tuple[str, ...] = TRAIN_FEATURES
) -> pd.DataFrame:
    """Return the training design matrix for the requested feature subset."""
    components = feature_components(data)
    return pd.DataFrame(
        {feature: components[feature].to_numpy(dtype=float) for feature in features}
    )


def _round6(value: float) -> float:
    return round(float(value), 6)


def train_coefficients(
    data: pd.DataFrame | None = None,
    include_protected: bool = False,
    features: tuple[str, ...] | None = None,
    false_rejection_cost: float = FALSE_REJECTION_COST,
) -> Coefficients:
    """Fit the trained model and return platform-shaped coefficients.

    Requires scikit-learn (a development/example dependency). The fit is fully
    deterministic: fixed data, fixed hyper-parameters, and the quasi-Newton
    ``lbfgs`` solver has no random component.

    ``features`` and ``false_rejection_cost`` default to the shipped model;
    :func:`original_v3_coefficients` re-fits the original v3 for comparison. ``include_protected=True`` is an experimental contrast fit that
    leaks the protected attributes into training; it is never pinned.
    """
    from sklearn.linear_model import LogisticRegression

    chosen = TRAIN_FEATURES if features is None else tuple(features)
    fitted_features = chosen + (PROTECTED_FEATURES if include_protected else ())
    frame = DEMO_DATA if data is None else data
    matrix = build_design_matrix(frame, fitted_features)
    labels = frame[LABEL_COLUMN].to_numpy(dtype=int)

    classifier = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    classifier.fit(matrix.to_numpy(), labels)

    weights = classifier.coef_[0]
    # Accept when P(qualified) >= cutoff  <=>  logit >= log(cutoff / (1 - cutoff)).
    # Shifting the bias by that log-odds puts the cutoff at decision value 0.
    cutoff = probability_cutoff(false_rejection_cost)
    bias = float(classifier.intercept_[0]) - float(np.log(cutoff / (1.0 - cutoff)))
    decision = matrix.to_numpy() @ weights + bias
    low, high = float(decision.min()), float(decision.max())

    # Scale so the cutoff lands on DECISION_THRESHOLD and the observed extremes
    # stay inside the platform's [0, 1] score range.
    bounds = []
    if low < 0:
        bounds.append(DECISION_THRESHOLD / -low)
    if high > 0:
        bounds.append((1.0 - DECISION_THRESHOLD) / high)
    scale = min(bounds) if bounds else 1.0

    coefficients: Coefficients = {
        feature: _round6(scale * weight)
        for feature, weight in zip(fitted_features, weights, strict=True)
    }
    coefficients["intercept"] = _round6(DECISION_THRESHOLD + scale * bias)
    # Every platform feature is present in the mapping; unused ones weigh 0.
    for feature in PROXY_FEATURES + PROTECTED_FEATURES:
        coefficients.setdefault(feature, 0.0)
    return coefficients


def original_v3_coefficients(data: pd.DataFrame | None = None) -> Coefficients:
    """Re-fit the pre-upgrade v3 (proxies kept, probability-0.5 cutoff)."""
    return train_coefficients(
        data,
        features=ORIGINAL_V3_FEATURES,
        false_rejection_cost=ORIGINAL_V3_FALSE_REJECTION_COST,
    )


def _payload_digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def coefficient_digest(coefficients: Coefficients) -> str:
    """Return a stable SHA-256 digest over the coefficient mapping."""
    return _payload_digest(coefficients)


def policy_digest(policy: dict[str, Any]) -> str:
    """Return a stable SHA-256 digest over the decision-policy metadata."""
    return _payload_digest(policy)


def build_artifact(coefficients: Coefficients | None = None) -> dict[str, Any]:
    """Assemble the pinned artifact payload (metadata + digest + coefficients)."""
    import sklearn

    fitted = train_coefficients() if coefficients is None else coefficients
    return {
        "model_id": "trained",
        "model_version": MODEL_VERSION,
        "label": LABEL_COLUMN,
        "algorithm": ALGORITHM,
        "train_features": list(TRAIN_FEATURES),
        "excluded_protected_features": list(PROTECTED_FEATURES),
        "excluded_proxy_features": list(PROXY_FEATURES),
        "decision_policy": DECISION_POLICY,
        "decision_policy_digest": policy_digest(DECISION_POLICY),
        "calibration": CALIBRATION,
        "rows": int(len(DEMO_DATA)),
        "sklearn_version": sklearn.__version__,
        "coefficient_digest": coefficient_digest(fitted),
        "coefficients": fitted,
    }


def save_artifact(path: Path | None = None) -> Path:
    """Fit the model and write (or refresh) the pinned artifact."""
    target = ARTIFACT_PATH if path is None else path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_artifact(), indent=2) + "\n", encoding="utf-8")
    return target


def load_artifact(path: Path | None = None) -> dict[str, Any]:
    """Load the pinned artifact and verify its integrity invariants."""
    target = ARTIFACT_PATH if path is None else path
    if not target.exists():
        raise FileNotFoundError(
            f"Trained-model artifact missing at {target}. Run `python -m chaoshire train --write`."
        )
    artifact = json.loads(target.read_text(encoding="utf-8"))
    if artifact.get("model_version") != MODEL_VERSION:
        raise ValueError(f"Trained-model artifact at {target} has an outdated model version.")
    policy = artifact.get("decision_policy")
    if not isinstance(policy, dict):
        raise ValueError(f"Trained-model artifact at {target} has no valid decision policy.")
    if artifact.get("decision_policy_digest") != policy_digest(policy):
        raise ValueError(f"Trained-model artifact at {target} failed its policy digest check.")
    if policy != DECISION_POLICY:
        raise ValueError(f"Trained-model artifact at {target} has an outdated decision policy.")
    coefficients: Coefficients = {
        key: float(value) for key, value in artifact["coefficients"].items()
    }
    if artifact.get("coefficient_digest") != coefficient_digest(coefficients):
        raise ValueError(f"Trained-model artifact at {target} failed its digest check.")
    if any(coefficients.get(feature, 0.0) != 0.0 for feature in PROTECTED_FEATURES):
        raise ValueError(f"Trained-model artifact at {target} carries protected-attribute weight.")
    if any(coefficients.get(feature, 0.0) != 0.0 for feature in PROXY_FEATURES):
        raise ValueError(f"Trained-model artifact at {target} carries proxy-feature weight.")
    artifact["coefficients"] = coefficients
    return artifact


def trained_coefficients() -> Coefficients:
    """Return the pinned coefficients for the ``trained`` reference model."""
    return dict(load_artifact()["coefficients"])


def decision_agreement(
    left: Coefficients, right: Coefficients, data: pd.DataFrame | None = None
) -> float:
    """Share of demo candidates whose accept/reject decision is identical under both models."""
    from .models import build_decisions

    frame = DEMO_DATA if data is None else data
    first = build_decisions(left, data=frame)["accepted"].to_numpy()
    second = build_decisions(right, data=frame)["accepted"].to_numpy()
    if not len(first):
        return 1.0
    return float(np.mean(first == second))


def _accuracy(decisions: pd.DataFrame) -> float:
    return float(np.mean(decisions["accepted"].to_numpy() == decisions[LABEL_COLUMN].astype(int)))


def decision_summary(result: dict[str, Any], decisions: pd.DataFrame) -> dict[str, Any]:
    from .metrics import worst_disparate_impact

    qualified = decisions[LABEL_COLUMN].astype(bool).to_numpy()
    accepted = decisions["accepted"].to_numpy().astype(bool)
    unqualified = ~qualified
    return {
        "total": result["certificate"]["total"],
        "grade": result["certificate"]["grade"],
        "worst_disparate_impact": worst_disparate_impact(result),
        "accuracy": round(_accuracy(decisions), 4),
        "recall": round(float(accepted[qualified].mean()), 4) if qualified.any() else None,
        "false_positive_rate": (
            round(float(accepted[unqualified].mean()), 4) if unqualified.any() else None
        ),
        "acceptance_rate": round(float(accepted.mean()), 4) if len(accepted) else None,
        "qualified_rejected": int((qualified & ~accepted).sum()),
        "selected": int(accepted.sum()),
    }


def disparity_diagnostics(
    coefficients: Coefficients | None = None, data: pd.DataFrame | None = None
) -> dict[str, Any]:
    """Explain where the trained model's group disparity comes from.

    Runtime-safe (no scikit-learn). It answers the question a reader naturally
    asks — *"the trained model should be the best one, so why does it score
    below the hand-written merit model?"* — with three measurements:

    * ``label_ceiling``: the audit of a perfect predictor that accepts exactly
      the candidates labelled qualified. If that already fails the four-fifths
      rule, any model that learns the label well inherits the gap.
    * ``label_base_rates``: the qualified rate per protected group, i.e. the
      gap the model is being trained to reproduce.
    * ``proxy_contribution``: the proxy weights and how many decisions change
      when they are zeroed, bounding what proxy leakage could explain.

    A fitted model optimises agreement with its label, not a fairness metric, so
    "more accurate" and "fairer" are different claims and can move in opposite
    directions when the label's base rates differ between groups.
    """
    from .metrics import audit
    from .models import build_decisions

    frame = DEMO_DATA if data is None else data
    fitted = trained_coefficients() if coefficients is None else dict(coefficients)

    model_decisions = build_decisions(fitted, data=frame)
    model_audit = audit(model_decisions)

    oracle = frame.copy()
    oracle["accepted"] = oracle[LABEL_COLUMN].astype(int)
    oracle_audit = audit(oracle)

    without_proxies = dict(fitted)
    for feature in PROXY_FEATURES:
        without_proxies[feature] = 0.0
    no_proxy_decisions = build_decisions(without_proxies, data=frame)
    no_proxy_audit = audit(no_proxy_decisions)
    changed = int((no_proxy_decisions["accepted"] != model_decisions["accepted"]).sum())

    base_rates = {
        attribute: {
            str(group): round(float(rate), 4)
            for group, rate in frame.groupby(attribute)[LABEL_COLUMN].mean().items()
        }
        for attribute in model_audit["configuration"]["protected_attributes"]
    }

    def summary(result: dict[str, Any], decisions: pd.DataFrame) -> dict[str, Any]:
        return decision_summary(result, decisions)

    model_summary = summary(model_audit, model_decisions)
    ceiling = summary(oracle_audit, oracle)
    ceiling_fails = ceiling["worst_disparate_impact"]["di_pass"] is False
    return {
        "model": model_summary,
        "label_ceiling": {
            "decisions": "accept exactly the candidates labelled qualified (a perfect predictor)",
            **ceiling,
        },
        "label_base_rates": base_rates,
        "qualified": int(frame[LABEL_COLUMN].sum()),
        "proxy_contribution": {
            "weights": {feature: float(fitted.get(feature, 0.0)) for feature in PROXY_FEATURES},
            "decisions_changed_when_zeroed": changed,
            "without_proxies": summary(no_proxy_audit, no_proxy_decisions),
        },
        "finding": (
            (
                "The qualified label itself fails the four-fifths rule "
                f"(perfect predictor: {ceiling['total']}/{ceiling['grade']}, worst "
                f"disparate impact {ceiling['worst_disparate_impact']['disparate_impact']} "
                f"on {ceiling['worst_disparate_impact']['attribute']}). "
                if ceiling_fails
                else "The qualified label passes the four-fifths rule. "
            )
            + "A model fitted to that label at the error-rate cutoff reproduces its "
            "group gaps; the shipped model instead applies a cost-sensitive cutoff "
            f"(P(qualified) >= {PROBABILITY_CUTOFF:.3f}) that rejects fewer qualified "
            f"candidates ({model_summary['qualified_rejected']} of {int(frame[LABEL_COLUMN].sum())}). "
            f"Proxy features change {changed} of {len(frame)} decisions."
        ),
    }


def holdout_comparison(
    seeds: Iterable[int] = POLICY_HOLDOUT_SEEDS,
    coefficients: dict[str, Coefficients] | None = None,
) -> dict[str, Any]:
    """Audit fixed coefficients on synthetic populations not used for tuning.

    By default this uses the disjoint policy holdout (seeds 51–100). Every
    model is fitted or specified against the seed-29 fixture; none is refitted
    on the holdout populations. The fixture seed is always skipped. Runtime-safe
    (no scikit-learn).
    """
    from .data import generate_demo_data
    from .metrics import audit
    from .models import FAIR, build_decisions

    models = (
        coefficients
        if coefficients is not None
        else {
            "fair": FAIR,
            "original_v3": ORIGINAL_V3_COEFFICIENTS,
            "previous_talentfit_v3": PREVIOUS_TALENTFIT_V3_COEFFICIENTS,
            "trained": trained_coefficients(),
        }
    )
    used = [seed for seed in seeds if seed != DEMO_SEED]
    rows: dict[str, list[dict[str, Any]]] = {name: [] for name in models}
    for seed in used:
        population = generate_demo_data(seed=seed)
        for name, model in models.items():
            decisions = build_decisions(model, data=population)
            rows[name].append(decision_summary(audit(decisions), decisions))

    def mean(name: str, key: str) -> float:
        return round(float(np.mean([row[key] for row in rows[name]])), 4)

    summary = {
        name: {
            "mean_total": round(float(np.mean([row["total"] for row in rows[name]])), 2),
            "mean_accuracy": mean(name, "accuracy"),
            "mean_recall": mean(name, "recall"),
            "mean_false_positive_rate": mean(name, "false_positive_rate"),
            "mean_acceptance_rate": mean(name, "acceptance_rate"),
            "mean_qualified_rejected": mean(name, "qualified_rejected"),
            "mean_selected": mean(name, "selected"),
            "mean_worst_disparate_impact": round(
                float(
                    np.mean(
                        [row["worst_disparate_impact"]["disparate_impact"] for row in rows[name]]
                    )
                ),
                4,
            ),
            "p10_worst_disparate_impact": round(
                float(
                    np.quantile(
                        [row["worst_disparate_impact"]["disparate_impact"] for row in rows[name]],
                        0.10,
                    )
                ),
                4,
            ),
            "worst_disparate_impact_pass_rate": round(
                float(np.mean([row["worst_disparate_impact"]["di_pass"] for row in rows[name]])),
                4,
            ),
        }
        for name in models
    }
    return {"populations": len(used), "seeds": used, "models": summary}


def policy_study() -> dict[str, Any]:
    """Reproduce the fairness-prioritised global-cost policy selection.

    The model is fitted once to the seed-29 fixture. Candidate global cost
    ratios are compared on 49 independent synthetic tuning populations, subject
    to a minimum mean-accuracy guardrail; the chosen model is then evaluated on
    the separate 50-seed holdout. No protected attributes are model inputs and
    no group-specific thresholds are considered.
    """
    from .data import generate_demo_data
    from .metrics import audit
    from .models import build_decisions

    populations = {seed: generate_demo_data(seed=seed) for seed in POLICY_TUNING_SEEDS}
    candidate_models: dict[float, Coefficients] = {}
    candidate_results: list[dict[str, Any]] = []
    for cost in POLICY_COST_CANDIDATES:
        coefficients = train_coefficients(false_rejection_cost=cost)
        candidate_models[cost] = coefficients
        rows = []
        for population in populations.values():
            decisions = build_decisions(coefficients, data=population)
            rows.append(decision_summary(audit(decisions), decisions))
        worst_di = [row["worst_disparate_impact"]["disparate_impact"] for row in rows]
        mean_accuracy = float(np.mean([row["accuracy"] for row in rows]))
        result = {
            "false_rejection_cost": cost,
            "probability_cutoff": round(probability_cutoff(cost), 6),
            "mean_fairness_risk_score": round(float(np.mean([row["total"] for row in rows])), 2),
            "mean_accuracy": round(mean_accuracy, 4),
            "mean_recall": round(float(np.mean([row["recall"] for row in rows])), 4),
            "mean_false_positive_rate": round(
                float(np.mean([row["false_positive_rate"] for row in rows])), 4
            ),
            "mean_acceptance_rate": round(
                float(np.mean([row["acceptance_rate"] for row in rows])), 4
            ),
            "mean_qualified_rejected": round(
                float(np.mean([row["qualified_rejected"] for row in rows])), 2
            ),
            "mean_worst_disparate_impact": round(float(np.mean(worst_di)), 4),
            "worst_disparate_impact_pass_rate": round(
                float(np.mean([row["worst_disparate_impact"]["di_pass"] for row in rows])),
                4,
            ),
            "eligible": mean_accuracy >= POLICY_MINIMUM_MEAN_ACCURACY,
        }
        candidate_results.append(result)

    eligible = [candidate for candidate in candidate_results if candidate["eligible"]]
    if not eligible:
        raise ValueError("No global-cost policy candidate met the mean-accuracy guardrail.")
    selected = max(
        eligible,
        key=lambda candidate: (
            candidate["mean_fairness_risk_score"],
            -candidate["false_rejection_cost"],
        ),
    )
    selected_cost = float(selected["false_rejection_cost"])
    holdout = holdout_comparison(
        seeds=POLICY_HOLDOUT_SEEDS,
        coefficients={
            "previous_talentfit_v3": PREVIOUS_TALENTFIT_V3_COEFFICIENTS,
            "candidate": candidate_models[selected_cost],
        },
    )
    return {
        "training_seed": DEMO_SEED,
        "tuning_seeds": list(POLICY_TUNING_SEEDS),
        "holdout_seeds": list(POLICY_HOLDOUT_SEEDS),
        "candidate_false_rejection_costs": list(POLICY_COST_CANDIDATES),
        "minimum_tuning_mean_accuracy": POLICY_MINIMUM_MEAN_ACCURACY,
        "selection_rule": POLICY_SELECTION_RULE,
        "candidates": candidate_results,
        "selected_false_rejection_cost": selected_cost,
        "selected_probability_cutoff": round(probability_cutoff(selected_cost), 6),
        "selected_coefficients_digest": coefficient_digest(candidate_models[selected_cost]),
        "independent_holdout": holdout,
    }
