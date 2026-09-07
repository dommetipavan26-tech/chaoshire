"""Deterministic synthetic data used by the public demonstration."""
import numpy as np
import pandas as pd

from .config import DEMO_SEED, DEMO_SIZE

MALE_NAMES = [
    "Arjun", "Ravi", "John", "David", "Wei", "Omar", "Carlos", "Daniel",
    "Sanjay", "Peter", "Ahmed", "Vikram",
]
FEMALE_NAMES = [
    "Priya", "Aisha", "Maria", "Chen", "Fatima", "Lakshmi", "Sarah", "Divya",
    "Emma", "Anita", "Zara", "Meera",
]
NON_BINARY_NAMES = ["Alex", "Sam", "Riya", "Noor", "Kai", "Dev"]
SURNAMES = [
    "Sharma", "Patel", "Khan", "Smith", "Chen", "Garcia", "Reddy", "Iyer",
    "Ali", "Kumar", "Brown", "Das", "Nair", "Singh", "Lopez", "Kim",
]


def generate_demo_data(seed: int = DEMO_SEED, size: int = DEMO_SIZE) -> pd.DataFrame:
    """Generate the reproducible, synthetic candidate fixture.

    The data is intentionally synthetic and must never be represented as a
    finding about a real employer or candidate population.
    """
    rng = np.random.default_rng(seed)
    genders = rng.choice(["M", "F", "NB"], size, p=[0.53, 0.42, 0.05])
    communities = rng.choice(["G1", "G2", "G3"], size, p=[0.45, 0.35, 0.20])
    ages = rng.choice(["18-25", "26-35", "36-50", "50+"], size, p=[0.28, 0.36, 0.22, 0.14])
    skills = np.clip(rng.normal(60, 18, size), 5, 100).round(0)
    experience = rng.integers(0, 16, size)
    education = rng.choice([1, 2, 3], size, p=[0.30, 0.45, 0.25])
    certifications = rng.integers(0, 5, size)
    prestige = np.clip(
        rng.normal(0.55, 0.18, size)
        + np.where(communities == "G1", 0.07, 0)
        - np.where(communities == "G3", 0.10, 0),
        0,
        1,
    ).round(3)
    career_gap = rng.random(size) < 0.18
    education_numeric = np.array([{1: 1.0, 2: 0.66, 3: 0.33}[x] for x in education])
    merit = (
        0.45 * skills / 100
        + 0.25 * experience / 15
        + 0.18 * education_numeric
        + 0.12 * certifications / 4
        + rng.normal(0, 0.05, size)
    )
    qualified = merit >= np.quantile(merit, 0.6)

    names = []
    for index in range(size):
        pool = (
            MALE_NAMES
            if genders[index] == "M"
            else FEMALE_NAMES
            if genders[index] == "F"
            else NON_BINARY_NAMES
        )
        names.append(f"{rng.choice(pool)} {rng.choice(SURNAMES)}")

    return pd.DataFrame(
        {
            "candidate_id": [f"C-{1000 + index}" for index in range(size)],
            "name": names,
            "gender": genders,
            "ethnicity": communities,
            "age_band": ages,
            "skills": skills,
            "experience": experience,
            "edu_tier": education,
            "edu_num": education_numeric,
            "certs": certifications,
            "prestige": prestige,
            "gap": career_gap,
            "merit": merit,
            "qualified": qualified,
        }
    )


DEMO_DATA = generate_demo_data()
