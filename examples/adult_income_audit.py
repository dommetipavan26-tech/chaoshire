"""Audit real-world predictions: the UCI Adult (Census Income) benchmark.

Every other ChaosHire result is computed on a synthetic fixture. This example
runs the same, unchanged audit engine (``chaoshire.metrics.audit``) on a real,
public dataset so the metrics can be seen on messy data they were not written
against.

What it does
------------
1. Loads the UCI Adult data (48,842 people from the 1994 US Census). The files
   are downloaded once from UCI into ``data/adult/`` (git-ignored) and checked
   against pinned SHA-256 digests. Pass ``--data-dir`` to use a local copy.
2. Trains two logistic-regression models on the official training split:

   * ``naive``  - uses every column, including sex and race.
   * ``blind``  - drops sex and race *and* their obvious proxies
     (relationship, which encodes "Husband"/"Wife"; marital status; native
     country). This is ChaosHire's blind-screening + proxy-removal mitigation.
   * ``blind_no_age`` - the blind model without the ``age`` input as well,
     because age band is one of the audited attributes.

   The true label is also audited as if it were a model (``true_label``): the
   result any perfect predictor would get.

3. Predicts on the official test split (16,281 people, never seen in
   training) and audits each model by sex, race and age band (under 40 / 40+,
   the US ADEA protected age boundary).

How to read it
--------------
Adult is an *income* dataset, not a hiring dataset. "Accepted" means the model
predicted income > $50K, standing in for a favourable screening decision, and
"qualified" is the true census label. The label itself reflects 1994 pay gaps,
so equal-opportunity numbers measure agreement with a historically unequal
outcome. This is educational screening evidence, not a legal finding.

Run::

    python -m pip install -r requirements-examples.txt
    python -m examples.adult_income_audit
    python -m examples.adult_income_audit --json adult-audit.json --csv adult-decisions.csv

The ``--csv`` export uses the configurable upload schema, so it can be loaded
in the dashboard's "Audit your own decisions" panel (decision column
``decision``, favourable value ``advance``, qualification column
``high_income``, qualified value ``yes``, protected attributes
``sex, race, age_band``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from chaoshire.metrics import audit

SEED = 1046
UCI_BASE = "https://archive.ics.uci.edu/ml/machine-learning-databases/adult"
FILES = {
    "adult.data": "5b00264637dbfec36bdeaab5676b0b309ff9eb788d63554ca0a249491c86603d",
    "adult.test": "a2a9044bc167a35b2361efbabec64e89d69ce82d9790d2980119aac5fd7e9c05",
}
DEFAULT_DATA_DIR = Path("data") / "adult"

COLUMNS = [
    "age",
    "workclass",
    "fnlwgt",
    "education",
    "education_num",
    "marital_status",
    "occupation",
    "relationship",
    "race",
    "sex",
    "capital_gain",
    "capital_loss",
    "hours_per_week",
    "native_country",
    "income",
]
NUMERIC = ["age", "education_num", "capital_gain", "capital_loss", "hours_per_week"]
CATEGORICAL_ALL = [
    "workclass",
    "education",
    "marital_status",
    "occupation",
    "relationship",
    "race",
    "sex",
    "native_country",
]
PROTECTED = ["sex", "race"]
PROXIES = ["relationship", "marital_status", "native_country"]
AUDITED_ATTRIBUTES = ["sex", "race", "age_band"]

MODELS: dict[str, dict[str, Any]] = {
    "naive": {
        "label": "Naive model (all columns, including sex and race)",
        "numeric": NUMERIC,
        "categorical": CATEGORICAL_ALL,
    },
    "blind": {
        "label": "Blind model (sex, race and proxies removed)",
        "numeric": NUMERIC,
        "categorical": [c for c in CATEGORICAL_ALL if c not in PROTECTED + PROXIES],
    },
    "blind_no_age": {
        "label": "Blind model without age (also drops the age input)",
        "numeric": [c for c in NUMERIC if c != "age"],
        "categorical": [c for c in CATEGORICAL_ALL if c not in PROTECTED + PROXIES],
    },
}
# The true label, audited as if it were a model: the fairness ceiling for any
# model that copies the label perfectly (see "label inequality" in the docs).
LABEL_REFERENCE = "true_label"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_data(data_dir: Path, download: bool = True) -> dict[str, str]:
    """Make sure both Adult files exist locally; return their verification status."""
    data_dir.mkdir(parents=True, exist_ok=True)
    status: dict[str, str] = {}
    for name, expected in FILES.items():
        path = data_dir / name
        if not path.exists():
            if not download:
                raise FileNotFoundError(f"{path} is missing and downloading is disabled.")
            print(f"Downloading {name} from UCI ...", file=sys.stderr)
            with urllib.request.urlopen(f"{UCI_BASE}/{name}", timeout=60) as response:
                path.write_bytes(response.read())
        status[name] = "verified" if _sha256(path) == expected else "digest-mismatch"
        if status[name] != "verified":
            print(
                f"WARNING: {name} does not match the pinned UCI SHA-256; "
                "results may differ from the documented ones.",
                file=sys.stderr,
            )
    return status


def load_split(path: Path) -> pd.DataFrame:
    """Parse one Adult file into a clean frame (drops rows with missing values)."""
    frame = pd.read_csv(
        path,
        header=None,
        names=COLUMNS,
        skipinitialspace=True,
        na_values="?",
        comment="|",  # adult.test starts with a "|1x3 Cross validator" line
    )
    frame = frame.dropna().reset_index(drop=True)
    # adult.test writes labels as "<=50K." / ">50K."
    frame["income"] = frame["income"].str.rstrip(".")
    frame["high_income"] = frame["income"] == ">50K"
    frame["age_band"] = np.where(frame["age"] >= 40, "40+", "Under 40")
    return frame


def train_and_predict(
    train: pd.DataFrame, test: pd.DataFrame, numeric: list[str], categorical: list[str]
) -> np.ndarray:
    """Fit a logistic regression on ``train`` and return boolean predictions for ``test``."""
    preprocess = ColumnTransformer(
        [
            ("num", StandardScaler(), numeric),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
        ]
    )
    model = Pipeline(
        [
            ("prep", preprocess),
            ("clf", LogisticRegression(max_iter=2000, random_state=SEED)),
        ]
    )
    model.fit(train[numeric + categorical], train["high_income"])
    return model.predict(test[numeric + categorical]).astype(bool)


def decisions_frame(test: pd.DataFrame, predictions: np.ndarray) -> pd.DataFrame:
    """Shape predictions into the columns ``chaoshire.metrics.audit`` expects."""
    return pd.DataFrame(
        {
            "candidate_id": [f"ADULT-{i:05d}" for i in range(len(test))],
            "sex": test["sex"].to_numpy(),
            "race": test["race"].to_numpy(),
            "age_band": test["age_band"].to_numpy(),
            "qualified": test["high_income"].to_numpy(),
            "accepted": predictions,
        }
    )


def summarise(name: str, decisions: pd.DataFrame, result: dict[str, Any]) -> dict[str, Any]:
    """Compact, JSON-friendly digest of one audit."""
    accuracy = float((decisions["accepted"] == decisions["qualified"]).mean())
    qualified = decisions["qualified"]
    return {
        "model": name,
        "label": MODELS[name]["label"]
        if name in MODELS
        else "Perfect predictor (the true label itself)",
        "rows": int(len(decisions)),
        "accuracy": round(accuracy, 4),
        "qualified_wrongly_rejected": int((qualified & ~decisions["accepted"]).sum()),
        "score": result["certificate"]["total"],
        "grade": result["certificate"]["grade"],
        "attributes": {
            item["attribute"]: {
                "disparate_impact": item["disparate_impact"],
                "four_fifths_pass": item["di_pass"],
                "parity_gap": item["parity_gap"],
                "equal_opportunity_gap": item["eq_opp_gap"],
                "groups": {
                    group["group"]: {
                        "n": group["n"],
                        "selection_rate": group["selection_rate"],
                        "selection_rate_ci": group["selection_rate_ci"],
                        "tpr": group["tpr"],
                        "low_n": group["low_n"],
                    }
                    for group in item["groups"]
                },
            }
            for item in result["attributes"]
        },
    }


def run(data_dir: Path, download: bool = True) -> dict[str, Any]:
    """Load data, train both models, audit them, and return the combined report."""
    integrity = ensure_data(data_dir, download=download)
    train = load_split(data_dir / "adult.data")
    test = load_split(data_dir / "adult.test")

    report: dict[str, Any] = {
        "dataset": {
            "name": "UCI Adult (Census Income), 1994 US Census extract",
            "source": UCI_BASE,
            "integrity": integrity,
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "high_income_share_test": round(float(test["high_income"].mean()), 4),
            "high_income_share_by_group": {
                attribute: {
                    str(group): round(float(share), 4)
                    for group, share in test.groupby(attribute)["high_income"].mean().items()
                }
                for attribute in AUDITED_ATTRIBUTES
            },
        },
        "models": {},
        "decisions": {},
    }
    runs: dict[str, np.ndarray] = {
        name: train_and_predict(train, test, spec["numeric"], spec["categorical"])
        for name, spec in MODELS.items()
    }
    runs[LABEL_REFERENCE] = test["high_income"].to_numpy(dtype=bool)
    for name, predictions in runs.items():
        decisions = decisions_frame(test, predictions)
        result = audit(decisions, attributes=AUDITED_ATTRIBUTES)
        report["models"][name] = summarise(name, decisions, result)
        report["decisions"][name] = decisions
    return report


def upload_csv(decisions: pd.DataFrame) -> str:
    """Render decisions in the dashboard's configurable-upload schema."""
    export = pd.DataFrame(
        {
            "candidate_id": decisions["candidate_id"],
            "sex": decisions["sex"],
            "race": decisions["race"],
            "age_band": decisions["age_band"],
            "decision": np.where(decisions["accepted"], "advance", "reject"),
            "high_income": np.where(decisions["qualified"], "yes", "no"),
        }
    )
    return export.to_csv(index=False)


def print_report(report: dict[str, Any]) -> None:
    dataset = report["dataset"]
    print(f"Dataset: {dataset['name']}")
    print(f"  integrity: {dataset['integrity']}")
    print(
        f"  train rows: {dataset['train_rows']:,}  test rows: {dataset['test_rows']:,}  "
        f"high-income share (test): {dataset['high_income_share_test']:.1%}"
    )
    for summary in report["models"].values():
        print()
        print(f"{summary['label']}")
        print(
            f"  accuracy {summary['accuracy']:.1%} | fairness risk score "
            f"{summary['score']}/{summary['grade']} | high earners missed "
            f"{summary['qualified_wrongly_rejected']:,}"
        )
        for attribute, values in summary["attributes"].items():
            verdict = "PASS" if values["four_fifths_pass"] else "FAIL"
            rates = ", ".join(
                f"{group} {data['selection_rate']:.1%}" + (" (low n)" if data["low_n"] else "")
                for group, data in values["groups"].items()
            )
            eq_gap = values["equal_opportunity_gap"]
            print(
                f"  {attribute:<8} DI {values['disparate_impact']:.3f} {verdict}  "
                f"parity gap {values['parity_gap']:.3f}  "
                f"eq-opp gap {eq_gap if eq_gap is None else f'{eq_gap:.3f}'}"
            )
            print(f"           selection rates: {rates}")
    print()
    print("Interpretation: screening evidence on a public income benchmark, not a hiring")
    print("model and not a legal finding. See docs/engineering/REAL-DATA-AUDIT.md.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--no-download", action="store_true", help="fail instead of downloading")
    parser.add_argument("--json", type=Path, help="write the audit summary as JSON")
    parser.add_argument(
        "--csv", type=Path, help="write blind-model decisions in the dashboard upload format"
    )
    args = parser.parse_args(argv)

    report = run(args.data_dir, download=not args.no_download)
    print_report(report)
    if args.json:
        payload = {key: value for key, value in report.items() if key != "decisions"}
        args.json.write_text(json.dumps(payload, indent=2))
        print(f"Wrote {args.json}")
    if args.csv:
        args.csv.write_text(upload_csv(report["decisions"]["blind"]))
        print(f"Wrote {args.csv}")


if __name__ == "__main__":
    main()
