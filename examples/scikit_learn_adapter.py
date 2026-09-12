"""Audit a real scikit-learn screening model with ChaosHire — no hard-coded demo data.

Run:
    python -m examples.scikit_learn_adapter
    python examples/scikit_learn_adapter.py

What happens, in order:

1. A synthetic applicant population is generated from a documented process
   (no real people, no real employer, no personal data).
2. Two scikit-learn pipelines are trained to predict hidden ground-truth
   qualification: a naive resume model that also reads a prestige proxy and a
   career-gap penalty, and a blind model that keeps only assessed merit signals.
3. Each model's decisions are normalised through ``SklearnDecisionAdapter``, which
   satisfies ChaosHire's ``DecisionAdapter`` contract — the only interface an
   external model has to implement.
4. The decisions are audited with the same fairness metrics the web app serves.
5. A tamper-evident evidence bundle is produced and verified.
6. A release policy is evaluated, and the run exits non-zero when a model must
   be blocked — the same shape as the ``python -m chaoshire gate`` CI check.

The example is deterministic: a fixed seed produces the same decisions, the same
audit numbers, and the same evidence digest on every run.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from chaoshire.adapters import DecisionAdapter
from chaoshire.config import FAIRNESS_THRESHOLDS
from chaoshire.evidence import build_evidence_bundle, verify_evidence_bundle
from chaoshire.metrics import audit

SEED = 1046
POPULATION = 800
PROTECTED_ATTRIBUTES = ["gender", "ethnicity", "age_band"]
NAIVE_FEATURES = ["skills", "experience", "education", "certs", "prestige", "gap"]
BLIND_FEATURES = ["skills", "experience", "education", "certs"]
MINIMUM_RISK_SCORE = 75
MINIMUM_ACCURACY = 0.70


def synthetic_population(seed: int = SEED, size: int = POPULATION) -> pd.DataFrame:
    """Generate a fictional applicant pool from a documented generative process.

    ``ability`` is the hidden ground-truth merit signal and the only thing the
    label depends on. Two *observed* signals are contaminated: measured skills
    absorb coaching money (``prestige``) and a career gap depresses the measured
    test score even when ability is unchanged. That contamination is exactly the
    failure mode a fairness audit has to catch.
    """
    rng = np.random.default_rng(seed)
    gender = rng.choice(["M", "F", "NB"], size=size, p=[0.47, 0.47, 0.06])
    ethnicity = rng.choice(["G1", "G2", "G3"], size=size, p=[0.62, 0.23, 0.15])
    age_band = rng.choice(["18-35", "36-50", "50+"], size=size, p=[0.42, 0.38, 0.20])
    ability = rng.normal(size=size)

    coaching = rng.normal(size=size) + 1.1 * (ethnicity == "G1")
    prestige = np.clip(50 + 9 * coaching + rng.normal(scale=6, size=size), 0, 100)
    gap = rng.random(size=size) < (
        0.08
        + 0.20 * (gender != "M")
        + 0.12 * (age_band == "36-50")
        + 0.06 * (age_band == "50+")
    )
    skills = np.clip(
        70 + 12 * ability + 0.30 * (prestige - 50) - 6.0 * gap + rng.normal(scale=4.5, size=size),
        0,
        100,
    )
    experience = np.clip(np.round(6 + 3.2 * ability + rng.normal(scale=2.4, size=size)), 0, 30)
    education = np.clip(
        np.round(3 + 0.8 * ability + 0.35 * coaching + rng.normal(scale=0.6, size=size)), 1, 5
    )
    certs = np.maximum(0, np.round(1.4 + 0.9 * ability + rng.normal(scale=0.8, size=size)))
    qualified = ability >= np.quantile(ability, 0.55)

    return pd.DataFrame(
        {
            "candidate_id": [f"S-{index:04d}" for index in range(1, size + 1)],
            "gender": gender,
            "ethnicity": ethnicity,
            "age_band": age_band,
            "skills": skills,
            "experience": experience,
            "education": education,
            "certs": certs,
            "prestige": prestige,
            "gap": gap.astype(int),
            "qualified": qualified.astype(int),
        }
    )


def screening_pipeline(features: list[str], seed: int = SEED) -> Pipeline:
    """Scale then fit logistic regression: small, auditable, reproducible."""
    return Pipeline(
        [
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(C=1.0, solver="lbfgs", max_iter=1_000, random_state=seed)),
        ]
    )


def train_and_decide(
    population: pd.DataFrame, features: list[str], seed: int = SEED
) -> tuple[Pipeline, pd.DataFrame]:
    """Fit the screening model and return its decision frame in audit shape."""
    model = screening_pipeline(features, seed)
    model.fit(population[features], population["qualified"])
    probability = model.predict_proba(population[features])[:, 1]
    decisions = population.copy()
    decisions["accepted"] = (probability >= 0.5).astype(int)
    decisions["probability"] = np.round(probability, 6)
    return model, decisions


@dataclass(frozen=True)
class SklearnDecisionAdapter:
    """Adapts a fitted scikit-learn pipeline to ChaosHire's decision contract.

    ChaosHire consumes *decisions*; it never needs model weights and never executes
    uploaded code. Any object with ``adapter_id``, ``describe()`` and ``decisions()``
    satisfies the contract, so an integration can stay this small.
    """

    model_id: str
    provider: Callable[[], pd.DataFrame]
    features: tuple[str, ...]
    adapter_id: str = "sklearn-decisions"

    def describe(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter_id,
            "model_id": self.model_id,
            "mode": "provided_decisions",
            "deterministic": True,
            "library": "scikit-learn",
            "pipeline": "StandardScaler + LogisticRegression",
            "features": list(self.features),
            "seed": SEED,
            "data": "synthetic - generated by examples/scikit_learn_adapter.py",
        }

    def decisions(self) -> pd.DataFrame:
        frame = self.provider()
        missing = {"accepted"} - set(frame.columns)
        if missing:
            raise ValueError(f"Adapter output is missing required columns: {', '.join(sorted(missing))}.")
        return frame.copy()


def to_adapter(model_id: str, decisions: pd.DataFrame, features: list[str]) -> SklearnDecisionAdapter:
    """Build the adapter and prove it satisfies the documented contract."""
    adapter = SklearnDecisionAdapter(
        model_id=model_id,
        provider=lambda: decisions,
        features=tuple(features),
    )
    if not isinstance(adapter, DecisionAdapter):
        raise TypeError("External integration must satisfy the DecisionAdapter contract.")
    return adapter


def utility_metrics(model: Pipeline, features: list[str], decisions: pd.DataFrame) -> dict[str, Any]:
    """Utility numbers, reported beside the fairness numbers on purpose."""
    predicted = model.predict(decisions[features])
    qualified = decisions["qualified"].to_numpy()
    accepted = decisions["accepted"].to_numpy().astype(bool)
    return {
        "accuracy": round(float((predicted == qualified).mean()), 4),
        "accept_rate": round(float(accepted.mean()), 4),
        "qualified_missed": int(((~accepted) & qualified.astype(bool)).sum()),
    }


def release_policy(audited: dict[str, Any], utility: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a model-release policy for an external model."""
    certificate = audited["certificate"]
    worst_di = min(attribute["disparate_impact"] for attribute in audited["attributes"])
    worst_parity = max(attribute["parity_gap"] for attribute in audited["attributes"])
    opportunity_gaps = [
        attribute["eq_opp_gap"]
        for attribute in audited["attributes"]
        if attribute["eq_opp_gap"] is not None
    ]
    worst_eq_opp = max(opportunity_gaps) if opportunity_gaps else 0.0
    checks = [
        {
            "id": "minimum_risk_score",
            "label": f"Fairness Risk Score >= {MINIMUM_RISK_SCORE}",
            "actual": certificate["total"],
            "passed": certificate["total"] >= MINIMUM_RISK_SCORE,
        },
        {
            "id": "disparate_impact",
            "label": f"Worst disparate impact >= {FAIRNESS_THRESHOLDS['disparate_impact']}",
            "actual": worst_di,
            "passed": worst_di >= FAIRNESS_THRESHOLDS["disparate_impact"],
        },
        {
            "id": "parity_gap",
            "label": f"Demographic parity gap <= {FAIRNESS_THRESHOLDS['parity_gap']}",
            "actual": worst_parity,
            "passed": worst_parity <= FAIRNESS_THRESHOLDS["parity_gap"],
        },
        {
            "id": "equal_opportunity_gap",
            "label": f"Equal-opportunity gap <= {FAIRNESS_THRESHOLDS['eq_opp_gap']}",
            "actual": worst_eq_opp,
            "passed": worst_eq_opp <= FAIRNESS_THRESHOLDS["eq_opp_gap"],
        },
        {
            "id": "utility_floor",
            "label": f"Accuracy >= {MINIMUM_ACCURACY}",
            "actual": utility["accuracy"],
            "passed": utility["accuracy"] >= MINIMUM_ACCURACY,
        },
    ]
    return {
        "status": "PASS" if all(check["passed"] for check in checks) else "FAIL",
        "risk_score": {"total": certificate["total"], "grade": certificate["grade"]},
        "worst_disparate_impact": worst_di,
        "worst_parity_gap": worst_parity,
        "worst_equal_opportunity_gap": round(worst_eq_opp, 4),
        "checks": checks,
        "blocking_checks": [check["id"] for check in checks if not check["passed"]],
    }


def evaluate(name: str, population: pd.DataFrame, features: list[str], seed: int) -> dict[str, Any]:
    """Full pipeline for one external model: train, decide, audit, evidence, gate."""
    model, decisions = train_and_decide(population, features, seed)
    adapter = to_adapter(name, decisions, features)
    frame = adapter.decisions()
    audited = audit(frame, PROTECTED_ATTRIBUTES)
    bundle = build_evidence_bundle(audited)
    verified = verify_evidence_bundle(bundle)
    utility = utility_metrics(model, features, frame)
    return {
        "model": name,
        "adapter": adapter.describe(),
        "rows_audited": int(len(frame)),
        "audit": audited,
        "evidence": {
            "algorithm": bundle["integrity"]["algorithm"],
            "digest": bundle["integrity"]["digest"],
            "verified": bool(verified["valid"]),
        },
        "utility": utility,
        "policy": release_policy(audited, utility),
    }


def summarise(result: dict[str, Any]) -> dict[str, Any]:
    audited = result["audit"]
    return {
        "model": result["model"],
        "candidates": audited["stats"]["candidates"],
        "accept_rate": audited["stats"]["accept_rate"],
        "accuracy": result["utility"]["accuracy"],
        "qualified_missed": result["utility"]["qualified_missed"],
        "risk_score": result["policy"]["risk_score"],
        "worst_disparate_impact": result["policy"]["worst_disparate_impact"],
        "worst_parity_gap": result["policy"]["worst_parity_gap"],
        "worst_equal_opportunity_gap": result["policy"]["worst_equal_opportunity_gap"],
        "evidence_digest": result["evidence"]["digest"],
        "evidence_verified": result["evidence"]["verified"],
        "policy": result["policy"]["status"],
        "blocking_checks": result["policy"]["blocking_checks"],
        "checks": [
            {"label": check["label"], "actual": check["actual"], "passed": check["passed"]}
            for check in result["policy"]["checks"]
        ],
    }


def render(rows: list[dict[str, Any]], seed: int, size: int) -> str:
    lines = [f"Synthetic population: {size} applicants · seed {seed} · no real applicant data", ""]
    for row in rows:
        verdict = "release approved" if row["policy"] == "PASS" else "release blocked"
        lines += [
            f"  {row['model']}",
            f"    Fairness Risk Score     {row['risk_score']['total']} / {row['risk_score']['grade']}",
            f"    accept rate / accuracy  {row['accept_rate']:.1%} / {row['accuracy']:.1%}",
            f"    qualified rejected      {row['qualified_missed']}",
            f"    worst DI / parity / TPR {row['worst_disparate_impact']:.4f} / "
            f"{row['worst_parity_gap']:.4f} / {row['worst_equal_opportunity_gap']:.4f}",
            f"    evidence                {row['evidence_digest'][:23]}… verified={row['evidence_verified']}",
            f"    release policy          {row['policy']} → {verdict}",
        ]
        for check in row["checks"]:
            mark = "pass" if check["passed"] else "FAIL"
            lines.append(f"      [{mark}] {check['label']} (actual {check['actual']})")
        lines.append("")
    lines.append(
        "A Fairness Risk Score prioritises engineering review. It is not a legal certification "
        "and\ndoes not by itself prove or disprove unlawful discrimination."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit scikit-learn decisions with ChaosHire.")
    parser.add_argument("--size", type=int, default=POPULATION, help="synthetic applicants")
    parser.add_argument("--seed", type=int, default=SEED, help="deterministic seed")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if any model fails its release policy (CI mode)",
    )
    args = parser.parse_args(argv)

    population = synthetic_population(args.seed, args.size)
    rows = [
        summarise(evaluate("sklearn-resume-naive", population, NAIVE_FEATURES, args.seed)),
        summarise(evaluate("sklearn-blind-merit", population, BLIND_FEATURES, args.seed)),
    ]

    if args.json:
        print(json.dumps({"seed": args.seed, "population": args.size, "models": rows}))
    else:
        print(render(rows, args.seed, args.size))

    return 1 if args.strict and any(row["policy"] != "PASS" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
