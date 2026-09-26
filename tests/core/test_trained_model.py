"""The bundled trained model: pinned artifact integrity and end-to-end auditability."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chaoshire.app import app
from chaoshire.config import DEMO_SEED
from chaoshire.metrics import audit, worst_disparate_impact
from chaoshire.models import FAIR, FEATURE_LABELS, build_decisions, get_model
from chaoshire.training import (
    AGREEMENT_FLOOR,
    ARTIFACT_PATH,
    FALSE_REJECTION_COST,
    MERIT_FEATURES,
    ORIGINAL_V3_COEFFICIENTS,
    PROTECTED_FEATURES,
    PROXY_FEATURES,
    TRAIN_FEATURES,
    coefficient_digest,
    decision_agreement,
    decision_summary,
    disparity_diagnostics,
    holdout_comparison,
    load_artifact,
    original_v3_coefficients,
    probability_cutoff,
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
    assert (result["certificate"]["total"], result["certificate"]["grade"]) == (80, "B")
    gender = next(a for a in result["attributes"] if a["attribute"] == "gender")
    assert gender["disparate_impact"] == pytest.approx(0.9032, abs=1e-4)
    # The score uses the *worst* attribute, which is age band.
    worst = worst_disparate_impact(result)
    assert worst["attribute"] == "age_band"
    assert worst["disparate_impact"] == pytest.approx(0.8137, abs=1e-4)
    assert worst["di_pass"] is True
    assert all(attribute["di_pass"] for attribute in result["attributes"])


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

    proxied = tmp_path / "proxied.json"
    coefficients = dict(artifact["coefficients"])
    coefficients["prestige"] = 0.05
    payload = dict(artifact)
    payload["coefficients"] = coefficients
    payload["coefficient_digest"] = coefficient_digest(coefficients)
    proxied.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="proxy-feature"):
        load_artifact(proxied)

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
    # scores *worse* on disparate impact than the blind fit, which is the
    # argument for blinding rather than an excuse to skip it. Compare worst
    # attribute with worst attribute (the figure the score uses): 0.641 on
    # gender for the contrast fit vs 0.814 on age band for the blind fit.
    blind_worst = report["blind_worst_disparate_impact"]["disparate_impact"]
    assert blind_worst == pytest.approx(0.8137, abs=1e-4)
    assert 0 < report["worst_disparate_impact"]["disparate_impact"] < blind_worst
    assert report["worst_disparate_impact"]["di_pass"] is False
    assert 0 < report["gender_disparate_impact"] < 0.9032

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


# --- The v3 upgrade ---------------------------------------------------------
#
# The original v3 (proxies kept, error-rate cutoff 0.5) was the most accurate
# model and still failed the four-fifths rule, because it reproduced group gaps
# already present in its label. The upgrade drops the proxy features and uses a
# cost-sensitive cutoff fixed on product grounds (a false rejection costs 2x a
# false acceptance). These tests pin both the diagnosis and the result, and
# check that the result generalises beyond the audited fixture.


def _summary(coefficients):
    decisions = build_decisions(coefficients)
    return decision_summary(audit(decisions), decisions)


def test_the_upgrade_is_a_fixed_policy_not_a_tuned_threshold():
    artifact = load_artifact()
    policy = artifact["decision_policy"]
    assert policy["false_rejection_cost"] == FALSE_REJECTION_COST == 2.0
    assert policy["probability_cutoff"] == pytest.approx(1 / 3, abs=1e-6)
    assert policy["probability_cutoff"] == pytest.approx(probability_cutoff(2.0), abs=1e-6)
    assert "never per group" in policy["cutoff_scope"]
    assert "not tuned to the score" in policy["rationale"]
    assert artifact["train_features"] == list(MERIT_FEATURES)
    assert artifact["excluded_proxy_features"] == list(PROXY_FEATURES)
    for feature in PROXY_FEATURES + PROTECTED_FEATURES:
        assert artifact["coefficients"][feature] == 0.0, feature
    assert probability_cutoff(1.0) == 0.5
    with pytest.raises(ValueError):
        probability_cutoff(0)


def test_original_v3_is_reproducible_as_the_baseline():
    pytest.importorskip("sklearn")
    assert original_v3_coefficients() == ORIGINAL_V3_COEFFICIENTS


def test_before_and_after_on_the_fixture():
    before = _summary(ORIGINAL_V3_COEFFICIENTS)
    after = _summary(get_model("trained"))
    fair = _summary(FAIR)
    assert (before["total"], before["grade"]) == (66, "C")
    assert before["worst_disparate_impact"]["disparate_impact"] == pytest.approx(0.727, abs=1e-4)
    assert (after["total"], after["grade"]) == (80, "B")
    assert after["worst_disparate_impact"]["di_pass"] is True
    # Fewer qualified candidates wrongly rejected than either earlier model.
    assert (before["qualified_rejected"], after["qualified_rejected"]) == (65, 21)
    assert fair["qualified_rejected"] == 34
    assert after["recall"] == pytest.approx(0.9475, abs=1e-4)
    assert after["recall"] > fair["recall"] > before["recall"]
    # Accuracy: still above MeritFirst, a little below the error-rate cutoff,
    # which is the price of rejecting fewer qualified candidates.
    assert after["accuracy"] == pytest.approx(0.876, abs=1e-3)
    assert fair["accuracy"] < after["accuracy"] < before["accuracy"]
    # MeritFirst keeps a higher fixture score (84 vs 80): the policy was fixed
    # in advance and not tuned until v3 won on the audited sample.
    assert fair["total"] == 84


def test_the_upgrade_generalises_to_unseen_populations():
    """Fixed coefficients audited on 49 synthetic populations the model never saw."""
    report = holdout_comparison()
    assert report["populations"] == 49
    assert DEMO_SEED not in report["seeds"]
    models = report["models"]
    trained, original, fair = models["trained"], models["original_v3"], models["fair"]
    assert trained["mean_total"] == pytest.approx(74.06, abs=0.01)
    assert original["mean_total"] == pytest.approx(66.18, abs=0.01)
    assert fair["mean_total"] == pytest.approx(72.06, abs=0.01)
    assert trained["mean_total"] > fair["mean_total"] > original["mean_total"]
    assert trained["mean_qualified_rejected"] < fair["mean_qualified_rejected"]
    assert trained["mean_recall"] > fair["mean_recall"] > original["mean_recall"]
    # Stated plainly: out of sample the upgrade is slightly less accurate than
    # MeritFirst (0.850 vs 0.857). It trades precision for recall by design.
    assert trained["mean_accuracy"] == pytest.approx(0.8504, abs=1e-4)
    assert trained["mean_accuracy"] < fair["mean_accuracy"]


def test_the_label_itself_fails_the_four_fifths_rule():
    """Why the upgrade was needed: a perfect predictor of `qualified` is not fair here."""
    diagnostics = disparity_diagnostics()
    ceiling = diagnostics["label_ceiling"]
    assert ceiling["accuracy"] == 1.0
    assert (ceiling["total"], ceiling["grade"]) == (68, "C")
    assert ceiling["worst_disparate_impact"]["di_pass"] is False
    assert ceiling["worst_disparate_impact"]["disparate_impact"] == pytest.approx(0.6627, abs=1e-4)
    # The label's gender base rates differ by sampling chance alone.
    rates = diagnostics["label_base_rates"]["gender"]
    assert rates["F"] > rates["M"] > rates["NB"]
    assert rates["NB"] / rates["F"] < 0.8
    assert "label itself fails the four-fifths rule" in diagnostics["finding"]
    assert "cost-sensitive cutoff" in diagnostics["finding"]
    assert diagnostics["model"]["qualified_rejected"] == 21


def test_the_dropped_proxies_carried_no_signal():
    """The original v3 weighted them near zero; re-adding them does not help."""
    original = disparity_diagnostics(ORIGINAL_V3_COEFFICIENTS)["proxy_contribution"]
    assert abs(original["weights"]["prestige"]) < 0.02
    # Positive, i.e. the old model *rewarded* career gaps: a chance correlation.
    assert 0 < original["weights"]["gap"] < 0.05
    assert original["decisions_changed_when_zeroed"] == 23
    shipped = disparity_diagnostics()["proxy_contribution"]
    assert shipped["weights"] == {"prestige": 0.0, "gap": 0.0}
    assert shipped["decisions_changed_when_zeroed"] == 0


def test_re_adding_the_proxies_does_not_improve_the_upgrade():
    pytest.importorskip("sklearn")
    with_proxies = train_coefficients(features=MERIT_FEATURES + PROXY_FEATURES)
    assert with_proxies["prestige"] != 0.0
    assert _summary(with_proxies)["total"] <= _summary(get_model("trained"))["total"]


def test_label_is_generated_without_proxies_or_protected_attributes():
    """The fixture's merit formula never reads prestige, gap or identity."""
    import inspect

    from chaoshire import data

    source = inspect.getsource(data.generate_demo_data)
    merit_block = source[source.index("merit = (") : source.index("qualified =")]
    for column in ("prestige", "career_gap", "genders", "communities", "ages"):
        assert column not in merit_block, column


def test_cli_holdout_prints_the_comparison(capsys, monkeypatch):
    import json

    import chaoshire.training as training
    from chaoshire.cli import main

    # The full 49-population figures are pinned above; this checks the wiring.
    real = training.holdout_comparison
    monkeypatch.setattr(training, "holdout_comparison", lambda: real(seeds=[1, 2, 29]))
    assert main(["train", "--holdout"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["populations"] == 2  # the fixture seed is always skipped
    assert set(report["models"]) == {"fair", "original_v3", "trained"}


def test_train_write_replaces_an_artifact_that_fails_current_rules(tmp_path, monkeypatch, capsys):
    pytest.importorskip("sklearn")
    import json

    import chaoshire.training as training
    from chaoshire.cli import main

    stale = tmp_path / "trained_model.json"
    payload = dict(load_artifact())
    payload["coefficients"] = dict(ORIGINAL_V3_COEFFICIENTS)
    payload["coefficient_digest"] = coefficient_digest(ORIGINAL_V3_COEFFICIENTS)
    stale.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(training, "ARTIFACT_PATH", stale)
    # --check must still fail loudly on an artifact that breaks the rules ...
    with pytest.raises(ValueError, match="proxy-feature"):
        main(["train", "--check"])
    # ... while --write is allowed to replace it.
    assert main(["train", "--write"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["written"] is True
    assert "proxy-feature" in report["replaced_invalid_artifact"]
    assert load_artifact(stale)["coefficients"] == get_model("trained")
