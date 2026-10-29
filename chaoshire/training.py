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
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import DECISION_THRESHOLD, DEMO_SEED, MIN_CELL_SIZE
from .data import (
    DEMO_DATA,
    STRESS_SCENARIO_DESCRIPTIONS,
    STRESS_SCENARIOS,
    generate_demo_data,
    generate_stress_population,
)
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
#: Additional synthetic stress populations. These seeds and scenarios are held
#: out from both fitting and policy selection; they are evaluation only.
STRESS_HOLDOUT_SEEDS: tuple[int, ...] = tuple(range(101, 111))
ROBUST_HOLDOUT_POPULATION_COUNT = len(POLICY_HOLDOUT_SEEDS) + len(STRESS_SCENARIOS) * len(
    STRESS_HOLDOUT_SEEDS
)
BOOTSTRAP_RESAMPLES = 1_000
THRESHOLD_SENSITIVITY_VALUES: tuple[float, ...] = (0.45, 0.475, 0.5, 0.525, 0.55)
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


def _robust_holdout_population_templates() -> tuple[tuple[str, int, pd.DataFrame], ...]:
    """Build the frozen baseline and stress populations once per process."""
    populations: list[tuple[str, int, pd.DataFrame]] = [
        ("baseline", seed, generate_demo_data(seed=seed)) for seed in POLICY_HOLDOUT_SEEDS
    ]
    populations.extend(
        (scenario, seed, generate_stress_population(seed=seed, scenario=scenario))
        for scenario in STRESS_SCENARIOS
        for seed in STRESS_HOLDOUT_SEEDS
    )
    return tuple(populations)


@lru_cache(maxsize=1)
def _cached_robust_holdout_population_templates() -> tuple[tuple[str, int, pd.DataFrame], ...]:
    return _robust_holdout_population_templates()


def _policy_metrics(
    coefficients: Coefficients,
    population: pd.DataFrame,
    threshold: float | None = None,
) -> dict[str, float | bool | int]:
    """Measure a frozen policy without fitting or using intersections as gate inputs."""
    from .metrics import attribute_metrics
    from .models import build_decisions

    decisions = build_decisions(coefficients, threshold=threshold, data=population)
    qualified = decisions[LABEL_COLUMN].astype(bool).to_numpy()
    accepted = decisions["accepted"].astype(bool).to_numpy()
    unqualified = ~qualified
    attributes = [
        attribute_metrics(decisions, name) for name in ("gender", "ethnicity", "age_band")
    ]
    impacts = [float(result["disparate_impact"]) for result in attributes]
    return {
        "accuracy": float(np.mean(accepted == qualified)) if len(qualified) else 0.0,
        "recall": float(np.mean(accepted[qualified])) if qualified.any() else 0.0,
        "false_positive_rate": (
            float(np.mean(accepted[unqualified])) if unqualified.any() else 0.0
        ),
        "worst_disparate_impact": min(impacts) if impacts else 0.0,
        "four_fifths_pass": all(bool(result["di_pass"]) for result in attributes),
        "acceptance_rate": float(np.mean(accepted)) if len(accepted) else 0.0,
        "qualified_rejected": int(np.sum(qualified & ~accepted)),
    }


def _bootstrap_seed(namespace: str) -> int:
    return int.from_bytes(hashlib.sha256(namespace.encode("utf-8")).digest()[:8], "big")


def _population_metric_summary(values: Iterable[float], namespace: str) -> dict[str, Any]:
    """Summarise population-level values with a deterministic bootstrap CI for the mean."""
    observations = np.asarray(list(values), dtype=float)
    if not len(observations):
        raise ValueError("Cannot summarize an empty population metric.")
    rng = np.random.default_rng(_bootstrap_seed(namespace))
    samples = rng.integers(
        0,
        len(observations),
        size=(BOOTSTRAP_RESAMPLES, len(observations)),
    )
    bootstrap_means = observations[samples].mean(axis=1)
    lower, upper = np.quantile(bootstrap_means, [0.025, 0.975])
    return {
        "population_count": int(len(observations)),
        "mean": round(float(observations.mean()), 4),
        "p10": round(float(np.quantile(observations, 0.10)), 4),
        "p90": round(float(np.quantile(observations, 0.90)), 4),
        "mean_ci95": {"low": round(float(lower), 4), "high": round(float(upper), 4)},
    }


def _summarize_population_rows(
    rows: list[dict[str, Any]],
    namespace: str,
) -> dict[str, Any]:
    metrics = {
        metric: _population_metric_summary(
            (float(row[metric]) for row in rows), f"{namespace}:{metric}"
        )
        for metric in (
            "accuracy",
            "recall",
            "false_positive_rate",
            "worst_disparate_impact",
            "acceptance_rate",
        )
    }
    pass_rate = _population_metric_summary(
        (float(bool(row["four_fifths_pass"])) for row in rows),
        f"{namespace}:four_fifths_pass_rate",
    )
    return {
        "population_count": len(rows),
        "metrics": metrics,
        "four_fifths_pass_rate": {
            "rate": pass_rate["mean"],
            "mean_ci95": pass_rate["mean_ci95"],
        },
        "mean_qualified_rejected": round(
            float(np.mean([float(row["qualified_rejected"]) for row in rows])), 2
        ),
    }


@lru_cache(maxsize=3)
def _cached_robust_model_summary(model_name: str) -> dict[str, Any]:
    """Cached deterministic summary for a bundled reference model."""
    from .models import get_model

    coefficients = get_model(model_name)
    populations = _cached_robust_holdout_population_templates()
    rows = [
        {
            "scenario": scenario,
            "seed": seed,
            **_policy_metrics(coefficients, population),
        }
        for scenario, seed, population in populations
    ]
    by_scenario: dict[str, dict[str, Any]] = {}
    for scenario in ("baseline", *STRESS_SCENARIOS):
        scenario_rows = [row for row in rows if row["scenario"] == scenario]
        scenario_seeds = [int(row["seed"]) for row in scenario_rows]
        by_scenario[scenario] = {
            "seeds": scenario_seeds,
            **_summarize_population_rows(scenario_rows, f"{model_name}:{scenario}"),
        }
    return {
        "reference_model": model_name,
        **_summarize_population_rows(rows, f"{model_name}:all"),
        "scenarios": by_scenario,
    }


def _scenario_seed_design() -> dict[str, Any]:
    return {
        "baseline": {
            "generator": "generate_demo_data",
            "seeds": list(POLICY_HOLDOUT_SEEDS),
            "population_count": len(POLICY_HOLDOUT_SEEDS),
        },
        "stress": {
            scenario: {
                "description": description,
                "seeds": list(STRESS_HOLDOUT_SEEDS),
                "population_count": len(STRESS_HOLDOUT_SEEDS),
            }
            for scenario, description in STRESS_SCENARIO_DESCRIPTIONS.items()
        },
    }


def _threshold_sensitivity_for_model(model_name: str) -> dict[str, Any]:
    from .models import get_model

    coefficients = get_model(model_name)
    populations = _cached_robust_holdout_population_templates()
    thresholds = []
    for threshold in THRESHOLD_SENSITIVITY_VALUES:
        rows = [
            {
                "scenario": scenario,
                "seed": seed,
                **_policy_metrics(coefficients, population, threshold=threshold),
            }
            for scenario, seed, population in populations
        ]
        summary = _summarize_population_rows(rows, f"{model_name}:threshold:{threshold:.3f}")
        thresholds.append(
            {
                "score_threshold": threshold,
                "delta_from_default": round(threshold - DECISION_THRESHOLD, 3),
                **summary,
            }
        )
    return {
        "model": model_name,
        "scope": (
            "The same platform-score threshold is applied to every candidate and group. "
            "These are score-space perturbations around the one global 0.5 cutoff, not "
            "group-specific thresholds or probability recalibration."
        ),
        "thresholds": thresholds,
    }


@lru_cache(maxsize=3)
def _cached_threshold_sensitivity(model_name: str) -> dict[str, Any]:
    return _threshold_sensitivity_for_model(model_name)


def robust_holdout_comparison(
    models: dict[str, str] | None = None,
    threshold_sensitivity_model: str | None = "trained",
) -> dict[str, Any]:
    """Evaluate frozen reference policies over baseline and stress holdouts.

    The 50 baseline seeds are the original disjoint holdout. Five additional
    stress scenarios contribute ten populations each (50 total); all use seeds
    101–110 and are excluded from fitting and policy selection. The uncertainty
    intervals describe resampling across these synthetic populations only.
    """
    from .models import MODEL_META

    selected = {name: name for name in MODEL_META} if models is None else models
    if not selected:
        raise ValueError("At least one reference model is required for robust holdout evaluation.")
    unknown = sorted(set(selected.values()) - set(MODEL_META))
    if unknown:
        raise ValueError(f"Unknown reference model(s): {', '.join(unknown)}.")
    result: dict[str, Any] = {
        "evaluation_design": {
            "synthetic_only": True,
            "training_seed": DEMO_SEED,
            "tuning_seeds": list(POLICY_TUNING_SEEDS),
            "baseline_holdout_seeds": list(POLICY_HOLDOUT_SEEDS),
            "stress_holdout_seeds_per_scenario": list(STRESS_HOLDOUT_SEEDS),
            "scenario_design": _scenario_seed_design(),
            "population_count": ROBUST_HOLDOUT_POPULATION_COUNT,
            "holdout_disjoint_from_policy_selection": True,
            "uncertainty_method": (
                f"95% percentile bootstrap interval for the mean across independent "
                f"synthetic population seeds ({BOOTSTRAP_RESAMPLES} resamples); not a "
                "real-world confidence interval."
            ),
            "threshold_scope": "one global platform-score cutoff; never per group",
        },
        "models": {
            label: _cached_robust_model_summary(model_name)
            for label, model_name in selected.items()
        },
    }
    if threshold_sensitivity_model is not None:
        sensitivity_label = next(
            (
                label
                for label, model_name in selected.items()
                if model_name == threshold_sensitivity_model
            ),
            None,
        )
        if sensitivity_label is not None:
            result["threshold_sensitivity"] = {
                "label": sensitivity_label,
                **_cached_threshold_sensitivity(threshold_sensitivity_model),
            }
    return result


def _calibration_metrics(probabilities: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    clipped = np.clip(np.asarray(probabilities, dtype=float), 0.0, 1.0)
    truth = np.asarray(labels, dtype=int)
    if not len(truth):
        return {"brier_score": 0.0, "expected_calibration_error": 0.0}
    bin_ids = np.minimum((clipped * 10).astype(int), 9)
    error = 0.0
    for bin_index in range(10):
        mask = bin_ids == bin_index
        if mask.any():
            error += float(mask.mean()) * abs(
                float(clipped[mask].mean()) - float(truth[mask].mean())
            )
    return {
        "brier_score": float(np.mean((clipped - truth) ** 2)),
        "expected_calibration_error": error,
    }


def _reliability_bins(probabilities: np.ndarray, labels: np.ndarray) -> list[dict[str, Any]]:
    from .metrics import wilson_interval

    clipped = np.clip(np.asarray(probabilities, dtype=float), 0.0, 1.0)
    truth = np.asarray(labels, dtype=int)
    bin_ids = np.minimum((clipped * 10).astype(int), 9)
    bins = []
    for bin_index in range(10):
        mask = bin_ids == bin_index
        count = int(mask.sum())
        if not count:
            continue
        positives = int(truth[mask].sum())
        bins.append(
            {
                "lower_probability": round(bin_index / 10, 1),
                "upper_probability": round((bin_index + 1) / 10, 1),
                "count": count,
                "mean_predicted_probability": round(float(clipped[mask].mean()), 4),
                "observed_rate": round(float(truth[mask].mean()), 4),
                "observed_rate_wilson_ci95": wilson_interval(positives, count),
            }
        )
    return bins


def calibration_study() -> dict[str, Any]:
    """Evaluate raw logistic probabilities and subgroup calibration diagnostics.

    The classifier is fitted once to the seed-29 synthetic fixture and frozen
    before the same 100 baseline/stress holdout populations are evaluated. This
    build-time diagnostic requires scikit-learn; runtime scoring remains
    sklearn-free. Subgroup summaries are uncertainty diagnostics only and never
    set or adjust a decision threshold.
    """
    from sklearn.linear_model import LogisticRegression

    classifier = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    classifier.fit(
        build_design_matrix(DEMO_DATA).to_numpy(),
        DEMO_DATA[LABEL_COLUMN].to_numpy(dtype=int),
    )
    populations = _cached_robust_holdout_population_templates()
    overall_rows: list[dict[str, Any]] = []
    scenario_values: dict[str, tuple[list[np.ndarray], list[np.ndarray]]] = {}
    subgroup_values: dict[str, dict[str, list[dict[str, float]]]] = {
        attribute: {} for attribute in ("gender", "ethnicity", "age_band")
    }
    subgroup_supported: dict[str, dict[str, int]] = {
        attribute: {} for attribute in ("gender", "ethnicity", "age_band")
    }

    for scenario, _seed, population in populations:
        probabilities = classifier.predict_proba(build_design_matrix(population).to_numpy())[:, 1]
        labels = population[LABEL_COLUMN].to_numpy(dtype=int)
        overall_rows.append({"scenario": scenario, **_calibration_metrics(probabilities, labels)})
        scenario_probabilities, scenario_labels = scenario_values.setdefault(scenario, ([], []))
        scenario_probabilities.append(probabilities)
        scenario_labels.append(labels)

        for attribute in subgroup_values:
            for group in sorted(population[attribute].astype(str).unique()):
                group_mask = population[attribute].astype(str).to_numpy() == group
                count = int(group_mask.sum())
                subgroup_supported[attribute][group] = subgroup_supported[attribute].get(
                    group, 0
                ) + int(count >= MIN_CELL_SIZE)
                if count < MIN_CELL_SIZE:
                    continue
                subgroup_values[attribute].setdefault(group, []).append(
                    {
                        "n": float(count),
                        **_calibration_metrics(probabilities[group_mask], labels[group_mask]),
                    }
                )

    metric_names = ("brier_score", "expected_calibration_error")
    overall = {
        metric: _population_metric_summary(
            (float(row[metric]) for row in overall_rows), f"calibration:all:{metric}"
        )
        for metric in metric_names
    }
    scenario_metrics = {}
    reliability = {}
    for scenario, (probability_rows, label_rows) in scenario_values.items():
        scenario_rows = [row for row in overall_rows if row["scenario"] == scenario]
        scenario_metrics[scenario] = {
            "population_count": len(scenario_rows),
            "metrics": {
                metric: _population_metric_summary(
                    (float(row[metric]) for row in scenario_rows),
                    f"calibration:{scenario}:{metric}",
                )
                for metric in metric_names
            },
        }
        reliability[scenario] = _reliability_bins(
            np.concatenate(probability_rows), np.concatenate(label_rows)
        )

    subgroup_diagnostics: dict[str, Any] = {}
    for attribute, groups in subgroup_values.items():
        subgroup_diagnostics[attribute] = {}
        for group, rows in sorted(groups.items()):
            subgroup_diagnostics[attribute][group] = {
                "population_count": len(rows),
                "supported_population_rate": round(
                    subgroup_supported[attribute].get(group, 0) / max(1, len(populations)), 4
                ),
                "mean_candidates": round(float(np.mean([row["n"] for row in rows])), 2),
                "metrics": {
                    metric: _population_metric_summary(
                        (float(row[metric]) for row in rows),
                        f"calibration:subgroup:{attribute}:{group}:{metric}",
                    )
                    for metric in metric_names
                },
            }
    return {
        "model": "trained",
        "fit": {
            "training_seed": DEMO_SEED,
            "training_rows": len(DEMO_DATA),
            "training_features": list(TRAIN_FEATURES),
            "frozen_before_holdout": True,
        },
        "probability_source": (
            "Raw LogisticRegression.predict_proba output from the seed-29 fit, before the "
            "affine transformation used by the runtime platform score. The runtime score "
            "is not itself a calibrated probability."
        ),
        "evaluation_design": {
            "baseline_holdout_seeds": list(POLICY_HOLDOUT_SEEDS),
            "stress_holdout_seeds_per_scenario": list(STRESS_HOLDOUT_SEEDS),
            "stress_scenarios": _scenario_seed_design()["stress"],
            "population_count": len(overall_rows),
            "subgroup_minimum_rows_per_population": MIN_CELL_SIZE,
            "training_and_tuning_data_excluded": True,
        },
        "population_count": len(overall_rows),
        "overall_metrics": overall,
        "scenario_metrics": scenario_metrics,
        "reliability_bins_by_scenario": reliability,
        "subgroup_diagnostics": subgroup_diagnostics,
        "subgroup_interpretation": (
            "Diagnostic only: intervals are bootstrapped across synthetic holdout populations. "
            "No subgroup-specific cutoff is selected, calibrated, or recommended."
        ),
        "limitations": (
            "These are synthetic calibration diagnostics, not validation of probability "
            "calibration for real applicants, employers, job families, or future data."
        ),
    }


def _pareto_frontier(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return candidates not dominated on DI, accuracy, recall, and false-positive rate."""
    objective_names = (
        "mean_worst_disparate_impact",
        "mean_accuracy",
        "mean_recall",
        "mean_false_positive_rate",
    )

    def vector(candidate: dict[str, Any]) -> tuple[float, ...]:
        values = [float(candidate[name]) for name in objective_names]
        values[-1] *= -1.0  # lower false-positive rate is better
        return tuple(values)

    frontier = []
    for candidate in candidates:
        current = vector(candidate)
        dominated = False
        for other in candidates:
            if other is candidate:
                continue
            comparison = vector(other)
            if all(left >= right for left, right in zip(comparison, current, strict=True)) and any(
                left > right for left, right in zip(comparison, current, strict=True)
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    return frontier


def _policy_candidate_eligible(
    mean_accuracy: float,
    mean_false_positive_rate: float,
    mean_recall: float,
    maximum_mean_false_positive_rate: float | None,
    minimum_mean_recall: float | None,
) -> bool:
    """Apply explicit utility bounds before any Pareto or score-based selection."""
    return (
        mean_accuracy >= POLICY_MINIMUM_MEAN_ACCURACY
        and (
            maximum_mean_false_positive_rate is None
            or mean_false_positive_rate <= maximum_mean_false_positive_rate
        )
        and (minimum_mean_recall is None or mean_recall >= minimum_mean_recall)
    )


def policy_study(
    maximum_mean_false_positive_rate: float | None = None,
    minimum_mean_recall: float | None = None,
) -> dict[str, Any]:
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

    for name, value in (
        ("maximum_mean_false_positive_rate", maximum_mean_false_positive_rate),
        ("minimum_mean_recall", minimum_mean_recall),
    ):
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1.")

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
        mean_recall = float(np.mean([row["recall"] for row in rows]))
        mean_false_positive_rate = float(np.mean([row["false_positive_rate"] for row in rows]))
        eligible_for_constraints = _policy_candidate_eligible(
            mean_accuracy,
            mean_false_positive_rate,
            mean_recall,
            maximum_mean_false_positive_rate,
            minimum_mean_recall,
        )
        result = {
            "false_rejection_cost": cost,
            "probability_cutoff": round(probability_cutoff(cost), 6),
            "mean_fairness_risk_score": round(float(np.mean([row["total"] for row in rows])), 2),
            "mean_accuracy": round(mean_accuracy, 4),
            "mean_recall": round(mean_recall, 4),
            "mean_false_positive_rate": round(mean_false_positive_rate, 4),
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
            "eligible_under_constraints": eligible_for_constraints,
            "eligible": eligible_for_constraints,
        }
        candidate_results.append(result)

    pareto_frontier = _pareto_frontier(candidate_results)
    pareto_costs = {candidate["false_rejection_cost"] for candidate in pareto_frontier}
    for candidate in candidate_results:
        candidate["pareto_efficient"] = candidate["false_rejection_cost"] in pareto_costs

    eligible = [candidate for candidate in candidate_results if candidate["eligible"]]
    if not eligible:
        raise ValueError("No global-cost policy candidate met the requested utility constraints.")
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
    selection_rule = POLICY_SELECTION_RULE
    constraint_notes = []
    if maximum_mean_false_positive_rate is not None:
        constraint_notes.append(f"mean false-positive rate <= {maximum_mean_false_positive_rate}")
    if minimum_mean_recall is not None:
        constraint_notes.append(f"mean recall >= {minimum_mean_recall}")
    if constraint_notes:
        selection_rule += (
            " Explicit analyst constraints also apply: "
            + " and ".join(constraint_notes)
            + "; candidates outside any bound are ineligible before selection."
        )
    return {
        "training_seed": DEMO_SEED,
        "tuning_seeds": list(POLICY_TUNING_SEEDS),
        "holdout_seeds": list(POLICY_HOLDOUT_SEEDS),
        "candidate_false_rejection_costs": list(POLICY_COST_CANDIDATES),
        "minimum_tuning_mean_accuracy": POLICY_MINIMUM_MEAN_ACCURACY,
        "selection_constraints": {
            "minimum_mean_accuracy": POLICY_MINIMUM_MEAN_ACCURACY,
            "maximum_mean_false_positive_rate": maximum_mean_false_positive_rate,
            "minimum_mean_recall": minimum_mean_recall,
        },
        "selection_rule": selection_rule,
        "pareto_objectives": {
            "maximize": [
                "mean_worst_disparate_impact",
                "mean_accuracy",
                "mean_recall",
            ],
            "minimize": ["mean_false_positive_rate"],
        },
        "pareto_frontier": pareto_frontier,
        "candidates": candidate_results,
        "selected_false_rejection_cost": selected_cost,
        "selected_probability_cutoff": round(probability_cutoff(selected_cost), 6),
        "selected_coefficients_digest": coefficient_digest(candidate_models[selected_cost]),
        "independent_holdout": holdout,
    }
