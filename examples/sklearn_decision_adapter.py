"""Audit deterministic scikit-learn predictions through ChaosHire's adapter contract.

This is an educational integration example, not a hiring model or legal assessment.
It trains only on synthetic data and keeps protected attributes out of model features.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from chaoshire.adapters import CallableDecisionAdapter, DecisionAdapter
from chaoshire.metrics import audit

SEED = 1046
ROWS = 800


def synthetic_candidates() -> tuple[pd.DataFrame, np.ndarray]:
    """Return synthetic candidate features and a synthetic training label."""
    rng = np.random.default_rng(SEED)
    frame = pd.DataFrame(
        {
            "candidate_id": [f"SK-{i:04d}" for i in range(ROWS)],
            "gender": rng.choice(["Woman", "Man"], ROWS),
            "community": rng.choice(["A", "B", "C"], ROWS, p=[0.45, 0.35, 0.20]),
            "skills_score": rng.normal(70, 12, ROWS).clip(0, 100),
            "experience_years": rng.gamma(2.5, 2.0, ROWS).clip(0, 20),
            "assessment_score": rng.normal(68, 14, ROWS).clip(0, 100),
        }
    )
    signal = (
        0.055 * frame["skills_score"]
        + 0.11 * frame["experience_years"]
        + 0.045 * frame["assessment_score"]
        + rng.normal(0, 0.55, ROWS)
    )
    labels = (signal >= np.quantile(signal, 0.58)).astype(int).to_numpy()
    return frame, labels


def build_adapter() -> CallableDecisionAdapter:
    """Train a model, normalize its outcomes, and expose a DecisionAdapter."""
    candidates, labels = synthetic_candidates()
    features = ["skills_score", "experience_years", "assessment_score"]
    model = make_pipeline(StandardScaler(), LogisticRegression(random_state=SEED))
    model.fit(candidates[features], labels)

    def provide_decisions() -> pd.DataFrame:
        decisions = candidates[["candidate_id", "gender", "community"]].copy()
        decisions["qualified"] = labels.astype(bool)
        decisions["accepted"] = model.predict(candidates[features]).astype(bool)
        return decisions

    return CallableDecisionAdapter(model_id="synthetic-logistic-v1", provider=provide_decisions)


def main() -> None:
    adapter = build_adapter()
    assert isinstance(adapter, DecisionAdapter)
    decisions = adapter.decisions()
    result = audit(decisions, attributes=["gender", "community"])

    print("Adapter:", adapter.describe())
    print("Rows audited:", len(decisions))
    print(
        "Fairness risk score:",
        f"{result['certificate']['total']}/{result['certificate']['grade']}",
    )
    for attribute in result["attributes"]:
        print(
            f"{attribute['attribute']}: DI={attribute['disparate_impact']:.3f}, "
            f"DP gap={attribute['parity_gap']:.3f}"
        )
    print("Interpretation: screening evidence for human review, not legal certification.")


if __name__ == "__main__":
    main()
