"""Deterministic synthetic data used by the public demonstration."""

import numpy as np
import pandas as pd

from .config import DEMO_SEED, DEMO_SIZE

MALE_NAMES = [
    "Arjun",
    "Ravi",
    "John",
    "David",
    "Wei",
    "Omar",
    "Carlos",
    "Daniel",
    "Sanjay",
    "Peter",
    "Ahmed",
    "Vikram",
]
FEMALE_NAMES = [
    "Priya",
    "Aisha",
    "Maria",
    "Chen",
    "Fatima",
    "Lakshmi",
    "Sarah",
    "Divya",
    "Emma",
    "Anita",
    "Zara",
    "Meera",
]
NON_BINARY_NAMES = ["Alex", "Sam", "Riya", "Noor", "Kai", "Dev"]
SURNAMES = [
    "Sharma",
    "Patel",
    "Khan",
    "Smith",
    "Chen",
    "Garcia",
    "Reddy",
    "Iyer",
    "Ali",
    "Kumar",
    "Brown",
    "Das",
    "Nair",
    "Singh",
    "Lopez",
    "Kim",
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

#: Stress populations are reserved for evaluation. They must never be added to
#: policy tuning or used to select/refit the frozen reference models.
STRESS_SCENARIO_DESCRIPTIONS = {
    "group_imbalance": (
        "Skew gender, community, and age-band group sizes while leaving merit and labels fixed."
    ),
    "label_base_rate_shift": (
        "Vary synthetic qualification base rates by protected group without exposing those "
        "groups to the predictor."
    ),
    "label_noise": "Flip 8% of synthetic qualification labels to model noisy outcomes.",
    "proxy_correlation_shift": (
        "Strengthen correlations between protected groups and excluded prestige/career-gap "
        "proxy columns."
    ),
    "merit_distribution_shift": (
        "Shift skills and experience distributions in selected communities, then regenerate "
        "the merit-only synthetic label."
    ),
}
STRESS_SCENARIOS = tuple(STRESS_SCENARIO_DESCRIPTIONS)


def _stress_names(rng: np.random.Generator, genders: np.ndarray) -> list[str]:
    names = []
    for gender in genders:
        pool = MALE_NAMES if gender == "M" else FEMALE_NAMES if gender == "F" else NON_BINARY_NAMES
        names.append(f"{rng.choice(pool)} {rng.choice(SURNAMES)}")
    return names


def generate_stress_population(
    seed: int,
    scenario: str,
    size: int = DEMO_SIZE,
) -> pd.DataFrame:
    """Generate a deterministic, evaluation-only shift from the demo process.

    The ordinary demo generator remains unchanged. Stress data is kept separate
    from both model fitting and policy selection; only frozen coefficients are
    evaluated on it. Protected and proxy columns are altered solely to test
    audit behavior and remain excluded from TalentFit's prediction features.
    """
    if scenario not in STRESS_SCENARIO_DESCRIPTIONS:
        raise ValueError(
            f"Unknown stress scenario '{scenario}'. Available scenarios: "
            f"{', '.join(STRESS_SCENARIOS)}."
        )
    salts = {name: (index + 1) * 100_003 for index, name in enumerate(STRESS_SCENARIOS)}
    rng = np.random.default_rng(seed + salts[scenario])
    frame = generate_demo_data(seed=seed, size=size)

    if scenario == "group_imbalance":
        frame["gender"] = rng.choice(["M", "F", "NB"], size, p=[0.74, 0.22, 0.04])
        frame["ethnicity"] = rng.choice(["G1", "G2", "G3"], size, p=[0.68, 0.22, 0.10])
        frame["age_band"] = rng.choice(
            ["18-25", "26-35", "36-50", "50+"], size, p=[0.12, 0.30, 0.35, 0.23]
        )
        frame["name"] = _stress_names(rng, frame["gender"].to_numpy())
    elif scenario == "label_base_rate_shift":
        genders = frame["gender"].to_numpy()
        communities = frame["ethnicity"].to_numpy()
        group_shift = np.select(
            [genders == "F", genders == "NB"], [-0.035, -0.10], default=0.02
        ) + np.select([communities == "G2", communities == "G3"], [-0.015, -0.045], default=0.01)
        latent_merit = frame["merit"].to_numpy(dtype=float) + group_shift
        frame["qualified"] = latent_merit >= np.quantile(latent_merit, 0.60)
    elif scenario == "label_noise":
        labels = frame["qualified"].to_numpy(dtype=bool)
        frame["qualified"] = np.logical_xor(labels, rng.random(size) < 0.08)
    elif scenario == "proxy_correlation_shift":
        communities = frame["ethnicity"].to_numpy()
        genders = frame["gender"].to_numpy()
        ages = frame["age_band"].to_numpy()
        proxy_shift = np.select(
            [communities == "G1", communities == "G3"], [0.34, -0.30], default=0.0
        )
        frame["prestige"] = np.clip(
            0.52 + proxy_shift + rng.normal(0.0, 0.10, size), 0.0, 1.0
        ).round(3)
        gap_probability = (
            0.08
            + np.where(genders == "F", 0.18, 0.0)
            + np.where(genders == "NB", 0.08, 0.0)
            + np.where(ages == "50+", 0.08, 0.0)
        )
        frame["gap"] = rng.random(size) < gap_probability
    else:  # merit_distribution_shift
        communities = frame["ethnicity"].to_numpy()
        frame["skills"] = np.clip(
            frame["skills"].to_numpy(dtype=float)
            + np.select([communities == "G2", communities == "G3"], [-8.0, -15.0], default=0.0),
            5,
            100,
        ).round(0)
        frame["experience"] = (
            np.clip(
                frame["experience"].to_numpy(dtype=float)
                + np.select([communities == "G2", communities == "G3"], [-1.0, -2.0], default=0.0),
                0,
                15,
            )
            .round(0)
            .astype(int)
        )
        merit = (
            0.45 * frame["skills"].to_numpy(dtype=float) / 100
            + 0.25 * frame["experience"].to_numpy(dtype=float) / 15
            + 0.18 * frame["edu_num"].to_numpy(dtype=float)
            + 0.12 * frame["certs"].to_numpy(dtype=float) / 4
            + rng.normal(0.0, 0.05, size)
        )
        frame["merit"] = merit
        frame["qualified"] = merit >= np.quantile(merit, 0.60)

    return frame
