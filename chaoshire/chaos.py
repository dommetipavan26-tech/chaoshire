"""Controlled counterfactual and stress experiments for reference models."""
from typing import Any

import numpy as np
import pandas as pd

from .config import DECISION_THRESHOLD
from .data import DEMO_DATA
from .metrics import round4
from .models import MODEL_META, get_model, score


def _verdict(value: float, warning_threshold: float, failure_threshold: float) -> str:
    if value <= warning_threshold:
        return "PASS"
    return "WARN" if value <= failure_threshold else "FAIL"


def run_chaos_suite(model: str = "legacy") -> dict[str, Any]:
    coefficients = get_model(model)
    baseline_scores = score(DEMO_DATA, coefficients)
    baseline_decisions = baseline_scores >= DECISION_THRESHOLD
    tests = []

    gender_swap = DEMO_DATA.copy()
    gender_swap["gender"] = gender_swap["gender"].replace({"M": "F", "F": "M", "NB": "M"})
    gender_scores = score(gender_swap, coefficients)
    gender_flips = int(((gender_scores >= DECISION_THRESHOLD) != baseline_decisions).sum())
    gender_rate = gender_flips / len(DEMO_DATA)
    female_mask = (DEMO_DATA["gender"] == "F").to_numpy()
    gender_delta = round4((gender_scores - baseline_scores)[female_mask].mean())
    tests.append(
        {
            "id": "gender_swap",
            "name": "Gender-Swap Counterfactual",
            "story": "Every candidate's gender marker is flipped and the model re-scores them. A fair model must not change a single decision.",
            "metric": "Decisions flipped",
            "value": f"{gender_flips} ({gender_rate:.1%})",
            "detail": f"Avg score change when Female→Male: {gender_delta:+.4f}",
            "verdict": _verdict(gender_rate, 0.01, 0.05),
        }
    )

    community_swap = DEMO_DATA.copy()
    community_swap["ethnicity"] = community_swap["ethnicity"].replace(
        {"G1": "G3", "G3": "G1", "G2": "G1"}
    )
    community_scores = score(community_swap, coefficients)
    community_flips = int(
        ((community_scores >= DECISION_THRESHOLD) != baseline_decisions).sum()
    )
    community_rate = community_flips / len(DEMO_DATA)
    minority_mask = (DEMO_DATA["ethnicity"] == "G3").to_numpy()
    community_delta = round4(
        (community_scores - baseline_scores)[minority_mask].mean()
    )
    tests.append(
        {
            "id": "ethnicity_swap",
            "name": "Name/Community-Swap Counterfactual",
            "story": "The community signal (name, school cluster) is swapped between majority and minority groups — same résumé, different identity.",
            "metric": "Decisions flipped",
            "value": f"{community_flips} ({community_rate:.1%})",
            "detail": f"Minority→Majority avg score change: {community_delta:+.4f}",
            "verdict": _verdict(community_rate, 0.01, 0.05),
        }
    )

    # A local seed makes repeated API calls identical and prevents test order
    # from affecting the experiment.
    rng = np.random.default_rng(2903)
    injected_count = 50
    injected = pd.DataFrame(
        {
            "gender": ["M"] * injected_count,
            "ethnicity": ["G1"] * injected_count,
            "age_band": ["26-35"] * injected_count,
            "skills": rng.uniform(20, 40, injected_count),
            "experience": rng.integers(0, 3, injected_count),
            "edu_tier": [3] * injected_count,
            "edu_num": [0.33] * injected_count,
            "certs": [0] * injected_count,
            "prestige": rng.uniform(0.85, 1.0, injected_count),
            "gap": [False] * injected_count,
        }
    )
    injected_acceptance = float(
        (score(injected, coefficients) >= DECISION_THRESHOLD).mean()
    )
    tests.append(
        {
            "id": "adversarial",
            "name": "Privilege-Keyword Injection",
            "story": "50 fake résumés with low skills but elite-college branding and majority markers are injected. Does the model get gamed?",
            "metric": "Fake candidates accepted",
            "value": f"{injected_acceptance:.0%}",
            "detail": f"Overall accept rate for comparison: {float(baseline_decisions.mean()):.0%}",
            "verdict": _verdict(injected_acceptance, 0.05, 0.20),
        }
    )

    qualified_hires = (baseline_decisions & DEMO_DATA["qualified"].astype(bool)).to_numpy()
    gap_stress = DEMO_DATA[qualified_hires].copy()
    gap_stress["gap"] = True
    gap_rejection = (
        float((score(gap_stress, coefficients) < DECISION_THRESHOLD).mean())
        if len(gap_stress)
        else 0.0
    )
    tests.append(
        {
            "id": "gap_stress",
            "name": "Career-Gap Stress Test",
            "story": "Every accepted, genuinely-qualified candidate gets a career gap added (parental leave, illness). Who survives?",
            "metric": "Qualified hires newly rejected",
            "value": f"{gap_rejection:.1%} of {len(gap_stress)}",
            "detail": "Disproportionately impacts returning parents and caregivers.",
            "verdict": _verdict(gap_rejection, 0.05, 0.15),
        }
    )

    young_hires = (
        baseline_decisions & DEMO_DATA["age_band"].isin(["18-25", "26-35"])
    ).to_numpy()
    age_stress = DEMO_DATA[young_hires].copy()
    age_stress["age_band"] = "50+"
    age_rejection = (
        float((score(age_stress, coefficients) < DECISION_THRESHOLD).mean())
        if len(age_stress)
        else 0.0
    )
    tests.append(
        {
            "id": "age_stress",
            "name": "Ageing Stress Test",
            "story": "Accepted young candidates are re-submitted as 50+. Same skills, same experience — only the birth year changes.",
            "metric": "Hires newly rejected",
            "value": f"{age_rejection:.1%} of {len(age_stress)}",
            "detail": "Detects hidden ageism in ranking features.",
            "verdict": _verdict(age_rejection, 0.05, 0.15),
        }
    )

    score_map = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}
    resilience = int(round(100 * np.mean([score_map[test["verdict"]] for test in tests])))
    return {"tests": tests, "resilience": resilience, "model": MODEL_META[model]}
