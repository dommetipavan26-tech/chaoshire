"""Reusable controlled-experiment framework for hiring-model chaos tests."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .config import DECISION_THRESHOLD
from .data import DEMO_DATA
from .metrics import round4
from .models import MODEL_META, Coefficients, get_model, score

DEFAULT_THRESHOLDS = {
    "gender_swap": {"warn": 0.01, "fail": 0.05},
    "ethnicity_swap": {"warn": 0.01, "fail": 0.05},
    "adversarial": {"warn": 0.05, "fail": 0.20},
    "gap_stress": {"warn": 0.05, "fail": 0.15},
    "age_stress": {"warn": 0.05, "fail": 0.15},
}


@dataclass(frozen=True)
class Observation:
    rate: float
    value: str
    detail: str
    evidence: list[dict[str, Any]]


Experiment = Callable[[Coefficients, int], Observation]


@dataclass(frozen=True)
class ChaosTest:
    id: str
    name: str
    story: str
    metric: str
    experiment: Experiment

    def execute(self, coefficients: Coefficients, threshold: dict[str, float], limit: int) -> dict:
        observation = self.experiment(coefficients, limit)
        verdict = (
            "PASS"
            if observation.rate <= threshold["warn"]
            else "WARN"
            if observation.rate <= threshold["fail"]
            else "FAIL"
        )
        return {
            "id": self.id,
            "name": self.name,
            "story": self.story,
            "metric": self.metric,
            "value": observation.value,
            "rate": round4(observation.rate),
            "detail": observation.detail,
            "verdict": verdict,
            "threshold": threshold,
            "evidence": observation.evidence[:limit],
            "evidence_count": len(observation.evidence),
        }


def _decision_evidence(
    data: pd.DataFrame,
    before_scores: np.ndarray,
    after_scores: np.ndarray,
    changed: np.ndarray,
) -> list[dict[str, Any]]:
    ordered = sorted(
        np.flatnonzero(changed),
        key=lambda index: abs(after_scores[index] - before_scores[index]),
        reverse=True,
    )
    return [
        {
            "candidate_id": str(data.iloc[index]["candidate_id"]),
            "before_score": round4(before_scores[index]),
            "after_score": round4(after_scores[index]),
            "score_delta": round4(after_scores[index] - before_scores[index]),
            "before_decision": "Accepted"
            if before_scores[index] >= DECISION_THRESHOLD
            else "Rejected",
            "after_decision": "Accepted"
            if after_scores[index] >= DECISION_THRESHOLD
            else "Rejected",
        }
        for index in ordered
    ]


def gender_swap_experiment(coefficients: Coefficients, _limit: int) -> Observation:
    baseline = score(DEMO_DATA, coefficients)
    transformed = DEMO_DATA.copy()
    transformed["gender"] = transformed["gender"].replace({"M": "F", "F": "M", "NB": "M"})
    changed_scores = score(transformed, coefficients)
    changed = (changed_scores >= DECISION_THRESHOLD) != (baseline >= DECISION_THRESHOLD)
    flips = int(changed.sum())
    female_mask = (DEMO_DATA["gender"] == "F").to_numpy()
    delta = round4((changed_scores - baseline)[female_mask].mean())
    return Observation(
        flips / len(DEMO_DATA),
        f"{flips} ({flips / len(DEMO_DATA):.1%})",
        f"Avg score change when Female→Male: {delta:+.4f}",
        _decision_evidence(DEMO_DATA, baseline, changed_scores, changed),
    )


def community_swap_experiment(coefficients: Coefficients, _limit: int) -> Observation:
    baseline = score(DEMO_DATA, coefficients)
    transformed = DEMO_DATA.copy()
    transformed["ethnicity"] = transformed["ethnicity"].replace(
        {"G1": "G3", "G3": "G1", "G2": "G1"}
    )
    changed_scores = score(transformed, coefficients)
    changed = (changed_scores >= DECISION_THRESHOLD) != (baseline >= DECISION_THRESHOLD)
    flips = int(changed.sum())
    minority_mask = (DEMO_DATA["ethnicity"] == "G3").to_numpy()
    delta = round4((changed_scores - baseline)[minority_mask].mean())
    return Observation(
        flips / len(DEMO_DATA),
        f"{flips} ({flips / len(DEMO_DATA):.1%})",
        f"Minority→Majority avg score change: {delta:+.4f}",
        _decision_evidence(DEMO_DATA, baseline, changed_scores, changed),
    )


def injection_experiment(coefficients: Coefficients, _limit: int) -> Observation:
    baseline = score(DEMO_DATA, coefficients)
    rng = np.random.default_rng(2903)
    count = 50
    injected = pd.DataFrame(
        {
            "candidate_id": [f"ADV-{index + 1:03d}" for index in range(count)],
            "gender": ["M"] * count,
            "ethnicity": ["G1"] * count,
            "age_band": ["26-35"] * count,
            "skills": rng.uniform(20, 40, count),
            "experience": rng.integers(0, 3, count),
            "edu_tier": [3] * count,
            "edu_num": [0.33] * count,
            "certs": [0] * count,
            "prestige": rng.uniform(0.85, 1.0, count),
            "gap": [False] * count,
        }
    )
    injected_scores = score(injected, coefficients)
    accepted = injected_scores >= DECISION_THRESHOLD
    rate = float(accepted.mean())
    highest = float(injected_scores.max())
    evidence = [
        {
            "candidate_id": str(injected.iloc[index]["candidate_id"]),
            "score": round4(injected_scores[index]),
            "decision": "Accepted",
            "scenario": "Low-skill, prestige-heavy synthetic résumé",
        }
        for index in np.flatnonzero(accepted)
    ]
    return Observation(
        rate,
        f"{rate:.0%}",
        (
            f"Overall accept rate for comparison: "
            f"{float((baseline >= DECISION_THRESHOLD).mean()):.0%}. "
            f"{_injection_headroom(injected, coefficients, injected_scores, highest)}"
        ),
        evidence,
    )


def _injection_headroom(
    injected: pd.DataFrame,
    coefficients: Coefficients,
    injected_scores: np.ndarray,
    highest: float,
) -> str:
    """State how much margin separates this fixture from a FAIL verdict.

    A PASS here is only meaningful if reviewers can see how close the injected
    résumés came to the decision threshold, and how strongly the model would
    have to weight prestige before the test could fail.
    """
    without_prestige = {key: value for key, value in coefficients.items() if key != "prestige"}
    base_scores = score(injected, without_prestige)
    prestige_component = np.maximum(injected["prestige"].to_numpy(dtype=float), 1e-9)
    required_weight = float(((DECISION_THRESHOLD - base_scores) / prestige_component).min())
    current_weight = float(coefficients.get("prestige", 0.0))
    margin = (
        f"no prestige weight is applied; {round4(required_weight)} would be needed"
        if current_weight <= 0
        else f"{round4(required_weight / current_weight)}x more prestige weight would be needed"
    )
    return (
        f"Highest injected score {round4(highest)} vs the {DECISION_THRESHOLD} threshold "
        f"({round4(DECISION_THRESHOLD - highest):+.4f} headroom); {margin} "
        f"(>= {round4(required_weight)}) before this test could fail."
    )


def gap_stress_experiment(coefficients: Coefficients, _limit: int) -> Observation:
    baseline = score(DEMO_DATA, coefficients)
    baseline_decisions = baseline >= DECISION_THRESHOLD
    mask = (baseline_decisions & DEMO_DATA["qualified"].astype(bool)).to_numpy()
    selected = DEMO_DATA[mask].copy()
    before = baseline[mask]
    selected["gap"] = True
    after = score(selected, coefficients)
    changed = after < DECISION_THRESHOLD
    rate = float(changed.mean()) if len(selected) else 0.0
    return Observation(
        rate,
        f"{rate:.1%} of {len(selected)}",
        "Disproportionately impacts returning parents and caregivers.",
        _decision_evidence(selected.reset_index(drop=True), before, after, changed),
    )


def age_stress_experiment(coefficients: Coefficients, _limit: int) -> Observation:
    baseline = score(DEMO_DATA, coefficients)
    baseline_decisions = baseline >= DECISION_THRESHOLD
    mask = (baseline_decisions & DEMO_DATA["age_band"].isin(["18-25", "26-35"])).to_numpy()
    selected = DEMO_DATA[mask].copy()
    before = baseline[mask]
    selected["age_band"] = "50+"
    after = score(selected, coefficients)
    changed = after < DECISION_THRESHOLD
    rate = float(changed.mean()) if len(selected) else 0.0
    return Observation(
        rate,
        f"{rate:.1%} of {len(selected)}",
        "Detects hidden ageism in ranking features.",
        _decision_evidence(selected.reset_index(drop=True), before, after, changed),
    )


CHAOS_TESTS = [
    ChaosTest(
        "gender_swap",
        "Gender-Swap Counterfactual",
        "Every candidate's gender marker is flipped and the model re-scores them. A fair model must not change a single decision.",
        "Decisions flipped",
        gender_swap_experiment,
    ),
    ChaosTest(
        "ethnicity_swap",
        "Name/Community-Swap Counterfactual",
        "The community signal (name, school cluster) is swapped between majority and minority groups — same résumé, different identity.",
        "Decisions flipped",
        community_swap_experiment,
    ),
    ChaosTest(
        "adversarial",
        "Privilege-Keyword Injection",
        "50 fake résumés with low skills but elite-college branding and majority markers are injected. Does the model get gamed?",
        "Fake candidates accepted",
        injection_experiment,
    ),
    ChaosTest(
        "gap_stress",
        "Career-Gap Stress Test",
        "Every accepted, genuinely-qualified candidate gets a career gap added (parental leave, illness). Who survives?",
        "Qualified hires newly rejected",
        gap_stress_experiment,
    ),
    ChaosTest(
        "age_stress",
        "Ageing Stress Test",
        "Accepted young candidates are re-submitted as 50+. Same skills, same experience — only the birth year changes.",
        "Hires newly rejected",
        age_stress_experiment,
    ),
]


def run_chaos_suite(
    model: str = "legacy",
    thresholds: dict[str, dict[str, float]] | None = None,
    evidence_limit: int = 10,
) -> dict[str, Any]:
    if model not in MODEL_META:
        raise ValueError(
            f"Unknown reference model '{model}'. Available models: {', '.join(MODEL_META)}."
        )
    coefficients = get_model(model)
    configured = {key: dict(value) for key, value in DEFAULT_THRESHOLDS.items()}
    for test_id, values in (thresholds or {}).items():
        if test_id not in configured:
            raise ValueError(f"Unknown chaos test threshold: {test_id}")
        if values["warn"] > values["fail"]:
            raise ValueError(f"Threshold warn must not exceed fail for {test_id}")
        configured[test_id] = {"warn": float(values["warn"]), "fail": float(values["fail"])}

    tests = [
        test.execute(coefficients, configured[test.id], evidence_limit) for test in CHAOS_TESTS
    ]
    score_map = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}
    resilience = int(round(100 * np.mean([score_map[test["verdict"]] for test in tests])))
    fingerprint = json.dumps(
        {
            "model": model,
            "thresholds": configured,
            "results": [(t["id"], t["rate"]) for t in tests],
        },
        sort_keys=True,
    ).encode()
    experiment_id = f"EXP-{hashlib.sha256(fingerprint).hexdigest()[:12].upper()}"
    return {
        "experiment_id": experiment_id,
        "tests": tests,
        "resilience": resilience,
        "model": MODEL_META[model],
        "configuration": {"thresholds": configured, "evidence_limit": evidence_limit},
    }
