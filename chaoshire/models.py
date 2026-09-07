"""Reference scoring models and feature transformations."""
from typing import TypeAlias

import numpy as np
import pandas as pd

from .config import DECISION_THRESHOLD
from .data import DEMO_DATA

Coefficients: TypeAlias = dict[str, float]

FEATURE_LABELS = {
    "skills": "Skills assessment",
    "experience": "Years of experience",
    "education": "Education level",
    "prestige": "College prestige (proxy)",
    "certs": "Certifications",
    "gender_M": "Gender = Male bonus",
    "gender_NB": "Gender = Non-binary penalty",
    "eth_G2": "Ethnicity B penalty",
    "eth_G3": "Ethnicity C penalty",
    "age_36-50": "Age 36-50 penalty",
    "age_50+": "Age 50+ penalty",
    "gap": "Career-gap penalty",
}
FEATURE_DESCRIPTIONS = {
    "skills": "Score on the structured skills test",
    "experience": "Relevant years of experience",
    "education": "Highest completed education",
    "prestige": "Prestige rank of the college named on the résumé",
    "certs": "Number of relevant certifications",
    "gender_M": "Model boosts résumés it reads as male",
    "gender_NB": "Model penalizes non-binary markers",
    "eth_G2": "Model penalizes names from community B",
    "eth_G3": "Model penalizes names from community C",
    "age_36-50": "Model penalizes mid-career applicants",
    "age_50+": "Model penalizes applicants above 50",
    "gap": "Model penalizes career gaps (e.g. parental leave)",
}
BIAS_FEATURES = [
    "gender_M", "gender_NB", "eth_G2", "eth_G3", "age_36-50",
    "age_50+", "gap", "prestige",
]

LEGACY: Coefficients = {
    "intercept": 0.05,
    "skills": 0.40,
    "experience": 0.19,
    "education": 0.13,
    "prestige": 0.09,
    "gender_M": 0.045,
    "gender_NB": -0.035,
    "eth_G2": -0.015,
    "eth_G3": -0.04,
    "age_36-50": -0.015,
    "age_50+": -0.055,
    "gap": -0.05,
    "certs": 0.02,
}
FAIR: Coefficients = {
    "intercept": -0.08,
    "skills": 0.50,
    "experience": 0.25,
    "education": 0.15,
    "certs": 0.10,
}
MODEL_META = {
    "legacy": {
        "id": "legacy",
        "title": "LegacyCorp Screen v1",
        "blurb": "Vendor model in production. Accused of bias — you're auditing it.",
    },
    "fair": {
        "id": "fair",
        "title": "MeritFirst v2",
        "blurb": "Skills-only reference model. Your clean baseline.",
    },
}


def get_model(model: str) -> Coefficients:
    """Return a named reference model; preserve the original fair fallback."""
    return LEGACY if model == "legacy" else FAIR


def feature_components(data: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "skills": data["skills"] / 100.0,
        "experience": data["experience"] / 15.0,
        "education": data["edu_num"],
        "prestige": data["prestige"],
        "certs": data["certs"] / 4.0,
        "gender_M": (data["gender"] == "M").astype(float),
        "gender_NB": (data["gender"] == "NB").astype(float),
        "eth_G2": (data["ethnicity"] == "G2").astype(float),
        "eth_G3": (data["ethnicity"] == "G3").astype(float),
        "age_36-50": (data["age_band"] == "36-50").astype(float),
        "age_50+": (data["age_band"] == "50+").astype(float),
        "gap": data["gap"].astype(float),
    }


def score(data: pd.DataFrame, coefficients: Coefficients) -> np.ndarray:
    components = feature_components(data)
    result = np.full(len(data), float(coefficients.get("intercept", 0.0)))
    for feature, weight in coefficients.items():
        if feature == "intercept" or weight == 0 or feature not in components:
            continue
        result = result + weight * components[feature].to_numpy(dtype=float)
    return np.clip(result, 0, 1)


def build_decisions(
    coefficients: Coefficients,
    threshold: float | np.ndarray | None = None,
    data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    result = (DEMO_DATA if data is None else data).copy()
    scores = score(result, coefficients)
    result["score"] = scores
    cutoff = DECISION_THRESHOLD if threshold is None else threshold
    result["accepted"] = (scores >= cutoff).astype(int)
    return result
