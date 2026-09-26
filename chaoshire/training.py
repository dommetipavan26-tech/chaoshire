"""Build-time trainer for the bundled ``trained`` reference model.

ChaosHire ships three reference models: the hand-written ``legacy`` and
``fair`` coefficient sets, and ``trained`` — a logistic regression actually
fitted to the deterministic demo fixture with scikit-learn.

Design rules that keep the platform honest and reproducible:

* Protected attributes (gender, ethnicity, age band) are **excluded** from the
  training features. Two real-world "neutral" résumé signals — college
  prestige and career gap — are offered to the fit as candidate proxies. On
  this fixture they carry almost no signal: the ``qualified`` label is generated
  from skills, experience, education and certifications only, so the fit gives
  them near-zero weight and they do **not** explain the model's group
  disparity. Retraining without them makes the audit slightly *worse*
  (``tests/core/test_trained_model.py`` pins this).
* The trained model's disparity comes from the label it learns. By sampling
  chance the fixture's ``qualified`` rate differs between groups (e.g. 45% of
  women vs 30% of non-binary candidates), so a model that predicts the label
  well reproduces those gaps. Accepting exactly the qualified candidates — a
  perfect predictor — itself fails the four-fifths rule.
  :func:`disparity_diagnostics` reports this at runtime without scikit-learn.
* Training is a **build-time tool**. The fitted coefficients are affinely
  calibrated onto the platform's [0, 1] score convention (the logistic 0.5
  probability boundary lands exactly on ``DECISION_THRESHOLD``) and pinned to
  ``chaoshire/artifacts/trained_model.json`` with a SHA-256 digest.
* Runtime code only ever loads the pinned artifact, so production keeps its
  lightweight dependency set and the published numbers cannot drift when
  scikit-learn is upgraded. ``python -m chaoshire train --check`` re-fits the
  model and fails when fresh training drifts from the artifact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import DECISION_THRESHOLD
from .data import DEMO_DATA
from .models import Coefficients, feature_components

LABEL_COLUMN = "qualified"
MERIT_FEATURES: tuple[str, ...] = ("skills", "experience", "education", "certs")
PROXY_FEATURES: tuple[str, ...] = ("prestige", "gap")
TRAIN_FEATURES: tuple[str, ...] = MERIT_FEATURES + PROXY_FEATURES
PROTECTED_FEATURES: tuple[str, ...] = (
    "gender_M",
    "gender_NB",
    "eth_G2",
    "eth_G3",
    "age_36-50",
    "age_50+",
)
ALGORITHM = "LogisticRegression(C=1.0, solver='lbfgs', max_iter=1000)"
CALIBRATION = (
    "affine; the logistic decision boundary (probability 0.5) is mapped onto the "
    f"platform decision threshold {DECISION_THRESHOLD} and the observed score "
    "range is scaled to fit inside [0, 1]"
)
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
    data: pd.DataFrame | None = None, include_protected: bool = False
) -> Coefficients:
    """Fit the trained model and return platform-shaped coefficients.

    Requires scikit-learn (a development/example dependency). The fit is fully
    deterministic: fixed data, fixed hyper-parameters, and the quasi-Newton
    ``lbfgs`` solver has no random component.

    ``include_protected=True`` is an experimental contrast fit that leaks the
    protected attributes into training; it is never pinned to the artifact.
    """
    from sklearn.linear_model import LogisticRegression

    features = TRAIN_FEATURES + (PROTECTED_FEATURES if include_protected else ())
    frame = DEMO_DATA if data is None else data
    matrix = build_design_matrix(frame, features)
    labels = frame[LABEL_COLUMN].to_numpy(dtype=int)

    classifier = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    classifier.fit(matrix.to_numpy(), labels)

    weights = classifier.coef_[0]
    bias = float(classifier.intercept_[0])
    decision = matrix.to_numpy() @ weights + bias
    low, high = float(decision.min()), float(decision.max())

    # Scale so the probability-0.5 boundary lands on DECISION_THRESHOLD and the
    # observed extremes stay inside the platform's [0, 1] score range.
    bounds = []
    if low < 0:
        bounds.append(DECISION_THRESHOLD / -low)
    if high > 0:
        bounds.append((1.0 - DECISION_THRESHOLD) / high)
    scale = min(bounds) if bounds else 1.0

    coefficients: Coefficients = {
        feature: _round6(scale * weight) for feature, weight in zip(features, weights, strict=True)
    }
    coefficients["intercept"] = _round6(DECISION_THRESHOLD + scale * bias)
    if not include_protected:
        for feature in PROTECTED_FEATURES:
            coefficients[feature] = 0.0
    return coefficients


def coefficient_digest(coefficients: Coefficients) -> str:
    """Return a stable SHA-256 digest over the coefficient mapping."""
    canonical = json.dumps(coefficients, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_artifact(coefficients: Coefficients | None = None) -> dict[str, Any]:
    """Assemble the pinned artifact payload (metadata + digest + coefficients)."""
    import sklearn

    fitted = train_coefficients() if coefficients is None else coefficients
    return {
        "model_id": "trained",
        "label": LABEL_COLUMN,
        "algorithm": ALGORITHM,
        "train_features": list(TRAIN_FEATURES),
        "excluded_protected_features": list(PROTECTED_FEATURES),
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
    coefficients: Coefficients = {
        key: float(value) for key, value in artifact["coefficients"].items()
    }
    if artifact.get("coefficient_digest") != coefficient_digest(coefficients):
        raise ValueError(f"Trained-model artifact at {target} failed its digest check.")
    if any(coefficients.get(feature, 0.0) != 0.0 for feature in PROTECTED_FEATURES):
        raise ValueError(f"Trained-model artifact at {target} carries protected-attribute weight.")
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
    from .metrics import audit, worst_disparate_impact
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
        return {
            "total": result["certificate"]["total"],
            "grade": result["certificate"]["grade"],
            "worst_disparate_impact": worst_disparate_impact(result),
            "accuracy": round(_accuracy(decisions), 4),
            "selected": int(decisions["accepted"].sum()),
        }

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
            + "A model fitted to that label tends to reproduce its group gaps the "
            "more closely it predicts it; the proxy features change "
            f"{changed} of {len(frame)} decisions and do not account for the gap."
        ),
    }
