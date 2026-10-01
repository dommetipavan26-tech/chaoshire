"""Offline tests for the UCI Adult real-data example.

The real files are ~6 MB and downloaded on demand, so these tests write small
synthetic files in the exact Adult format (including the quirks of
``adult.test``) and run the example end to end without network access.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture()
def adult():
    """Import the example lazily so the tests are always collected.

    ``tests/infrastructure/test_build_info.py`` pins the collected-test count,
    and CI does not install scikit-learn, so a module-level skip would make the
    count differ between environments. Each test skips individually instead,
    matching ``test_trained_model.py``.
    """
    pytest.importorskip("sklearn")
    from examples import adult_income_audit

    return adult_income_audit


def _write_fake_adult(directory: Path, rows: int = 400, seed: int = 7) -> None:
    rng = np.random.default_rng(seed)

    def lines(count: int, test_file: bool) -> list[str]:
        out = []
        for _ in range(count):
            sex = rng.choice(["Male", "Female"])
            age = int(rng.integers(18, 70))
            education_num = int(rng.integers(5, 16))
            hours = int(rng.integers(20, 60))
            high = education_num + hours / 10 + rng.normal(0, 2) > 17
            label = (">50K" if high else "<=50K") + ("." if test_file else "")
            workclass = "?" if rng.random() < 0.02 else "Private"  # missing values
            fields = [
                age,
                workclass,
                100000,
                "Bachelors",
                education_num,
                "Married-civ-spouse" if rng.random() < 0.5 else "Never-married",
                rng.choice(["Exec-managerial", "Sales", "Craft-repair"]),
                "Husband" if sex == "Male" else "Wife",
                rng.choice(["White", "Black"]),
                sex,
                0,
                0,
                hours,
                "United-States",
                label,
            ]
            out.append(", ".join(str(field) for field in fields))
        return out

    (directory / "adult.data").write_text("\n".join(lines(rows, False)) + "\n")
    (directory / "adult.test").write_text(
        "|1x3 Cross validator\n" + "\n".join(lines(rows // 2, True)) + "\n"
    )


@pytest.fixture()
def fake_dir(tmp_path: Path) -> Path:
    _write_fake_adult(tmp_path)
    return tmp_path


def test_load_split_handles_test_file_quirks(adult, fake_dir: Path) -> None:
    frame = adult.load_split(fake_dir / "adult.test")
    assert not frame["income"].str.endswith(".").any()
    assert set(frame["income"]) <= {">50K", "<=50K"}
    assert frame.notna().all().all()  # "?" rows dropped
    assert set(frame["age_band"]) <= {"40+", "Under 40"}


def test_blind_models_exclude_protected_and_proxy_columns(adult) -> None:
    for name in ("blind", "blind_no_age"):
        used = set(adult.MODELS[name]["categorical"]) | set(adult.MODELS[name]["numeric"])
        assert used.isdisjoint(adult.PROTECTED + adult.PROXIES)
    assert "age" not in adult.MODELS["blind_no_age"]["numeric"]


def test_run_end_to_end_offline(adult, fake_dir: Path) -> None:
    report = adult.run(fake_dir, download=False, allow_unverified=True)
    # Synthetic files only run with explicit unverified-data opt-in.
    assert set(report["dataset"]["integrity"].values()) == {"digest-mismatch"}
    assert set(report["models"]) == {"naive", "blind", "blind_no_age", "true_label"}
    label = report["models"]["true_label"]
    assert label["accuracy"] == 1.0
    assert label["qualified_wrongly_rejected"] == 0
    for summary in report["models"].values():
        assert set(summary["attributes"]) == set(adult.AUDITED_ATTRIBUTES)
        assert 0 <= summary["score"] <= 100


def test_missing_files_without_download_fail_clearly(adult, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        adult.ensure_data(tmp_path, download=False)


def test_csv_export_is_accepted_by_upload_workflow(adult, fake_dir: Path) -> None:
    from chaoshire.services import upload_decisions

    report = adult.run(fake_dir, download=False, allow_unverified=True)
    csv_text = adult.upload_csv(report["decisions"]["blind"])
    assert set(pd.read_csv(io.StringIO(csv_text))["decision"]) <= {"advance", "reject"}
    result = upload_decisions(
        csv_text,
        "Adult example",
        decision_column="decision",
        favorable_values=["advance"],
        qualification_column="high_income",
        qualified_values=["yes"],
        protected_attributes=["sex", "race", "age_band"],
        minimum_group_size=10,
        publish=False,
    )
    assert result.get("ok") is True, result


def test_cli_writes_json_and_csv(adult, fake_dir: Path, tmp_path: Path) -> None:
    json_path, csv_path = tmp_path / "out.json", tmp_path / "out.csv"
    adult.main(
        [
            "--data-dir",
            str(fake_dir),
            "--no-download",
            "--allow-unverified",
            "--json",
            str(json_path),
            "--csv",
            str(csv_path),
        ]
    )
    payload = json.loads(json_path.read_text())
    assert "decisions" not in payload and "models" in payload
    assert csv_path.read_text().startswith("candidate_id,sex,race,age_band,decision")
