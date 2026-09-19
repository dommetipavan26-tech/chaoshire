"""The bundled trained model: pinned artifact integrity and end-to-end auditability."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chaoshire.app import app
from chaoshire.models import FEATURE_LABELS, build_decisions, get_model
from chaoshire.training import (
    AGREEMENT_FLOOR,
    ARTIFACT_PATH,
    PROTECTED_FEATURES,
    TRAIN_FEATURES,
    coefficient_digest,
    decision_agreement,
    load_artifact,
    train_coefficients,
)


def test_artifact_is_pinned_wellformed_and_blind():
    assert ARTIFACT_PATH.exists(), "run `python -m chaoshire train --write`"
    artifact = load_artifact()
    coefficients = artifact["coefficients"]
    assert artifact["model_id"] == "trained"
    assert artifact["label"] == "qualified"
    assert artifact["train_features"] == list(TRAIN_FEATURES)
    assert artifact["coefficient_digest"] == coefficient_digest(coefficients)
    assert set(coefficients) == set(FEATURE_LABELS) | {"intercept"}
    for feature in PROTECTED_FEATURES:
        assert coefficients[feature] == 0.0, f"protected feature leaked: {feature}"
    assert coefficients["skills"] > 0
    assert coefficients["experience"] > 0


def test_get_model_trained_matches_the_artifact_deterministically():
    pinned = load_artifact()["coefficients"]
    assert get_model("trained") == pinned
    assert get_model("trained") == get_model("trained")


def test_trained_model_is_auditable_end_to_end():
    with TestClient(app) as client:
        response = client.get("/api/audit", params={"model": "trained", "dataset": "demo"})
        assert response.status_code == 200
        body = response.json()
        assert body["model"]["id"] == "trained"
        assert body["certificate"]["assessable"] is True
        assert body["certificate"]["grade"] in {"A", "B", "C", "D", "F"}

        chaos = client.get("/api/chaos", params={"model": "trained"})
        assert chaos.status_code == 200
        assert 0 <= chaos.json()["resilience"] <= 100

        compare = client.get("/api/compare", params={"baseline": "legacy", "candidate": "trained"})
        assert compare.status_code == 200

        explain = client.get("/api/explain/C-1046", params={"model": "trained"})
        assert explain.status_code == 200
        assert explain.json()["candidate_id"] == "C-1046"

        first = client.get("/api/evidence", params={"model": "trained", "dataset": "demo"}).json()
        second = client.get("/api/evidence", params={"model": "trained", "dataset": "demo"}).json()
        assert first["integrity"]["digest"] == second["integrity"]["digest"]

        run = client.post("/api/chaos/run", json={"model": "trained"})
        assert run.status_code == 200

        review = client.post("/api/agent/review", json={"model": "trained", "dataset": "demo"})
        assert review.status_code == 200

        # Unknown identifiers are still rejected exactly as before.
        assert (
            client.get("/api/audit", params={"model": "bogus", "dataset": "demo"}).status_code
            == 400
        )


def test_trained_model_keeps_its_published_numbers():
    """Pin the trained model's deterministic demo output (like legacy 32/F and fair 84/B)."""
    from chaoshire.metrics import audit

    result = audit(build_decisions(get_model("trained")))
    assert (result["certificate"]["total"], result["certificate"]["grade"]) == (66, "C")
    gender = next(a for a in result["attributes"] if a["attribute"] == "gender")
    assert gender["disparate_impact"] == pytest.approx(0.7798, abs=1e-4)


def test_retraining_stays_close_to_the_pinned_artifact():
    pytest.importorskip("sklearn")
    fresh = train_coefficients()
    pinned = load_artifact()["coefficients"]
    for feature in PROTECTED_FEATURES:
        assert fresh[feature] == 0.0
    assert fresh["skills"] > 0
    assert fresh["experience"] > 0
    assert decision_agreement(fresh, pinned) >= AGREEMENT_FLOOR


def test_legacy_and_fair_outputs_are_untouched_by_the_new_model():
    from chaoshire.metrics import audit

    legacy = audit(build_decisions(get_model("legacy")))["certificate"]
    fair = audit(build_decisions(get_model("fair")))["certificate"]
    assert (legacy["total"], legacy["grade"]) == (32, "F")
    assert (fair["total"], fair["grade"]) == (84, "B")


def test_cli_train_check_passes_and_reports(capsys):
    pytest.importorskip("sklearn")
    import json

    from chaoshire.cli import main

    assert main(["train", "--check"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["pinned"] is True
    assert "written" not in report
    assert report["fresh_digest"]
    assert report["pinned_digest"]
    assert report["decision_agreement"] >= AGREEMENT_FLOOR


def test_cli_train_write_roundtrip_into_tmp(tmp_path, monkeypatch, capsys):
    pytest.importorskip("sklearn")
    import json

    import chaoshire.training as training
    from chaoshire.cli import main

    target = tmp_path / "trained_model.json"
    monkeypatch.setattr(training, "ARTIFACT_PATH", target)
    assert main(["train", "--write"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["written"] is True
    assert target.exists()
    assert load_artifact(target)["coefficients"] == get_model("trained")


def test_load_artifact_rejects_missing_and_tampered_files(tmp_path):
    import json

    with pytest.raises(FileNotFoundError, match="chaoshire train --write"):
        load_artifact(tmp_path / "missing.json")

    artifact = load_artifact()

    bad_digest = tmp_path / "digest.json"
    payload = dict(artifact)
    payload["coefficient_digest"] = "sha256:" + "0" * 64
    bad_digest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        load_artifact(bad_digest)

    leaked = tmp_path / "leaked.json"
    coefficients = dict(artifact["coefficients"])
    coefficients["gender_M"] = 0.5
    payload = dict(artifact)
    payload["coefficients"] = coefficients
    payload["coefficient_digest"] = coefficient_digest(coefficients)
    leaked.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="protected-attribute"):
        load_artifact(leaked)


def test_decision_agreement_handles_empty_frames():
    from chaoshire.data import DEMO_DATA

    empty = DEMO_DATA.iloc[0:0]
    pinned = load_artifact()["coefficients"]
    assert decision_agreement(pinned, pinned, data=empty) == 1.0


def test_include_protected_contrast_fit_leaks_and_differs():
    pytest.importorskip("sklearn")
    leaked = train_coefficients(include_protected=True)
    assert any(leaked[feature] != 0.0 for feature in PROTECTED_FEATURES)
    # The pinned artifact itself stays blind no matter what experiments run.
    pinned = load_artifact()["coefficients"]
    assert all(pinned[feature] == 0.0 for feature in PROTECTED_FEATURES)


def test_cli_include_protected_reports_but_refuses_to_pin(capsys, tmp_path, monkeypatch):
    pytest.importorskip("sklearn")
    import json

    import chaoshire.cli as cli
    import chaoshire.training as training
    from chaoshire.cli import main
    from chaoshire.training import PROTECTED_FEATURES

    # The default destination lives under reports/generated/, which .gitignore
    # already excludes: the contrast fit is a disposable diagnostic, never an
    # artifact to pin or commit.
    assert cli.CONTRAST_REPORT_PATH == Path("reports/generated/protected-contrast.json")

    target = tmp_path / "nested" / "contrast.json"
    assert main(["train", "--include-protected", "--out", str(target)]) == 0
    stdout = capsys.readouterr().out

    # stdout carries only a static acknowledgement. Every value derived from a
    # protected-attribute fit goes to the file, because CodeQL's
    # py/clear-text-logging rule treats those values as private data reaching an
    # output sink, and inline suppression comments are not honoured by this
    # repository's code-scanning configuration.
    assert str(target) in stdout
    assert "Never pinned" in stdout
    assert not stdout.strip().startswith("{")
    for feature in PROTECTED_FEATURES:
        assert feature not in stdout

    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["mode"] == "with-protected-attributes"
    assert report["pinned"] is False
    assert "Never pinned" in report["note"]
    # The file keeps everything the flag exists to show, coefficients included.
    assert set(report["coefficients"]) >= set(PROTECTED_FEATURES)
    assert any(report["coefficients"][feature] != 0.0 for feature in PROTECTED_FEATURES)
    assert report["certificate"]["total"] >= 0
    # The contrast is the point: a fit allowed to see gender, ethnicity and age
    # scores *worse* on disparate impact than the blind fit's 0.78, which is the
    # argument for blinding rather than an excuse to skip it.
    assert 0 < report["gender_disparate_impact"] < 0.78

    # Without --out the report lands at the documented default, created if needed.
    default_target = tmp_path / "generated" / "protected-contrast.json"
    monkeypatch.setattr(cli, "CONTRAST_REPORT_PATH", default_target)
    assert main(["train", "--include-protected"]) == 0
    assert default_target.exists()
    assert "protected-contrast.json" in capsys.readouterr().out

    monkeypatch.setattr(training, "ARTIFACT_PATH", tmp_path / "never.json")
    assert main(["train", "--include-protected", "--write"]) == 2
    assert "Refusing" in capsys.readouterr().out
    assert not (tmp_path / "never.json").exists()
