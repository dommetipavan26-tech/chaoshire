"""Build-time trainer for the bundled ``trained`` reference model.

ChaosHire ships three reference models: the hand-written ``legacy`` and
``fair`` coefficient sets, and ``trained`` — a logistic regression actually
fitted to the deterministic demo fixture with scikit-learn.

Design rules that keep the platform honest and reproducible:

* Protected attributes (gender, ethnicity, age band) are **excluded** from the
  training features. Two real-world "neutral" résumé signals — college
  prestige and career gap — are kept, so the model demonstrates proxy leakage
  instead of pretending feature selection alone removes bias.
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
