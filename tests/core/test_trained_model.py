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
    POLICY_COST_CANDIDATES,
    POLICY_HOLDOUT_SEEDS,
    POLICY_MINIMUM_MEAN_ACCURACY,
    POLICY_TUNING_SEEDS,
    PREVIOUS_TALENTFIT_V3_COEFFICIENTS,
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
    policy_digest,
    policy_study,
    probability_cutoff,
    train_coefficients,
)


def test_artifact_is_pinned_wellformed_and_blind():
    assert ARTIFACT_PATH.exists(), "run `python -m chaoshire train --write`"
    artifact = load_artifact()
    coefficients = artifact["coefficients"]
    assert artifact["model_id"] == "trained"
    assert artifact["model_version"] == 4
    assert artifact["label"] == "qualified"
    assert artifact["train_features"] == list(TRAIN_FEATURES)
    assert artifact["coefficient_digest"] == coefficient_digest(coefficients)
    assert artifact["decision_policy_digest"] == policy_digest(artifact["decision_policy"])
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
    """Pin the fairness-prioritised v4 demo output."""
    from chaoshire.metrics import audit

    result = audit(build_decisions(get_model("trained")))
    assert (result["certificate"]["total"], result["certificate"]["grade"]) == (85, "B")
    gender = next(a for a in result["attributes"] if a["attribute"] == "gender")
    assert gender["disparate_impact"] == pytest.approx(0.8735, abs=1e-4)
    # The score uses the *worst* attribute, which is gender on v4.
    worst = worst_disparate_impact(result)
    assert worst["attribute"] == "gender"
    assert worst["disparate_impact"] == pytest.approx(0.8735, abs=1e-4)
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

    bad_policy_digest = tmp_path / "policy-digest.json"
    payload = json.loads(json.dumps(artifact))
    payload["decision_policy"]["false_rejection_cost"] = 2.0
    bad_policy_digest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="policy digest"):
        load_artifact(bad_policy_digest)

    stale_policy = tmp_path / "stale-policy.json"
    payload["decision_policy_digest"] = policy_digest(payload["decision_policy"])
    stale_policy.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="outdated decision policy"):
        load_artifact(stale_policy)

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
    # gender for the contrast fit vs 0.874 on gender for the blind v4 fit.
    blind_worst = report["blind_worst_disparate_impact"]["disparate_impact"]
    assert blind_worst == pytest.approx(0.8735, abs=1e-4)
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


# --- The TalentFit fairness-prioritised operating point --------------------
#
# The first trained v3 already dropped protected and proxy features, but its
# 2:1 cutoff left a poorer fairness score and missed more qualified candidates
# than the new fairness-prioritised operating point. The policy study evaluates
# one global-cutoff grid on a fixed synthetic tuning set, applies an accuracy
# guardrail, then validates once on a disjoint holdout. These tests pin the
# complete selection protocol and its trade-offs, not just the fixture score.


def _summary(coefficients):
    decisions = build_decisions(coefficients)
    return decision_summary(audit(decisions), decisions)


def test_fairness_policy_selection_is_global_bounded_and_reproducible():
    pytest.importorskip("sklearn")
    artifact = load_artifact()
    policy = artifact["decision_policy"]
    assert policy["false_rejection_cost"] == FALSE_REJECTION_COST == 3.0
    assert policy["probability_cutoff"] == pytest.approx(0.25, abs=1e-6)
    assert policy["probability_cutoff"] == pytest.approx(probability_cutoff(3.0), abs=1e-6)
    assert "never per group" in policy["cutoff_scope"]
    assert policy["candidate_false_rejection_costs"] == list(POLICY_COST_CANDIDATES)
    assert policy["minimum_tuning_mean_accuracy"] == POLICY_MINIMUM_MEAN_ACCURACY == 0.80
    assert policy["tuning_seeds"] == list(POLICY_TUNING_SEEDS)
    assert policy["holdout_seeds"] == list(POLICY_HOLDOUT_SEEDS)
    assert set(POLICY_TUNING_SEEDS).isdisjoint(POLICY_HOLDOUT_SEEDS)
    assert DEMO_SEED not in POLICY_TUNING_SEEDS
    assert "synthetic tuning populations" in policy["selection_method"]
    assert "not a real-world cost estimate" in policy["rationale"]
    assert artifact["train_features"] == list(MERIT_FEATURES)
    assert artifact["excluded_proxy_features"] == list(PROXY_FEATURES)
    for feature in PROXY_FEATURES + PROTECTED_FEATURES:
        assert artifact["coefficients"][feature] == 0.0, feature
    assert probability_cutoff(1.0) == 0.5
    with pytest.raises(ValueError):
        probability_cutoff(0)

    study = policy_study()
    assert study["selected_false_rejection_cost"] == 3.0
    assert study["selected_probability_cutoff"] == 0.25
    candidate = next(row for row in study["candidates"] if row["false_rejection_cost"] == 3.0)
    too_liberal = next(row for row in study["candidates"] if row["false_rejection_cost"] == 3.5)
    assert candidate["eligible"] is True
    assert candidate["mean_fairness_risk_score"] == pytest.approx(78.63, abs=0.01)
    assert candidate["mean_accuracy"] == pytest.approx(0.8091, abs=1e-4)
    assert too_liberal["eligible"] is False
    assert too_liberal["mean_fairness_risk_score"] > candidate["mean_fairness_risk_score"]
    held = study["independent_holdout"]["models"]
    assert held["candidate"]["mean_total"] == pytest.approx(78.40, abs=0.01)
    assert held["candidate"]["mean_accuracy"] == pytest.approx(0.8099, abs=1e-4)
    assert held["previous_talentfit_v3"]["mean_total"] == pytest.approx(74.62, abs=0.01)


def test_original_v3_is_reproducible_as_the_baseline():
    pytest.importorskip("sklearn")
    assert original_v3_coefficients() == ORIGINAL_V3_COEFFICIENTS


def test_before_and_after_on_the_fixture():
    original = _summary(ORIGINAL_V3_COEFFICIENTS)
    previous = _summary(PREVIOUS_TALENTFIT_V3_COEFFICIENTS)
    after = _summary(get_model("trained"))
    fair = _summary(FAIR)
    assert (original["total"], original["grade"]) == (66, "C")
    assert original["worst_disparate_impact"]["disparate_impact"] == pytest.approx(0.727, abs=1e-4)
    assert (previous["total"], previous["grade"]) == (80, "B")
    assert previous["qualified_rejected"] == 21
    assert previous["worst_disparate_impact"]["disparate_impact"] == pytest.approx(0.8137, abs=1e-4)
    assert (after["total"], after["grade"]) == (85, "B")
    assert after["worst_disparate_impact"]["attribute"] == "gender"
    assert after["worst_disparate_impact"]["disparate_impact"] == pytest.approx(0.8735, abs=1e-4)
    assert after["worst_disparate_impact"]["di_pass"] is True
    assert (
        original["qualified_rejected"],
        previous["qualified_rejected"],
        after["qualified_rejected"],
    ) == (65, 21, 11)
    assert fair["qualified_rejected"] == 34
    assert after["recall"] == pytest.approx(0.9725, abs=1e-4)
    assert after["recall"] > previous["recall"] > fair["recall"] > original["recall"]
    assert after["accuracy"] == pytest.approx(0.831, abs=1e-3)
    assert after["accuracy"] < fair["accuracy"] < previous["accuracy"] < original["accuracy"]
    assert fair["total"] == 84


def test_the_upgrade_generalises_to_unseen_populations():
    """Frozen coefficients improve mean fairness on 50 disjoint synthetic holdouts."""
    report = holdout_comparison()
    assert report["populations"] == 50
    assert report["seeds"] == list(POLICY_HOLDOUT_SEEDS)
    assert DEMO_SEED not in report["seeds"]
    models = report["models"]
    trained = models["trained"]
    previous = models["previous_talentfit_v3"]
    original = models["original_v3"]
    fair = models["fair"]
    assert trained["mean_total"] == pytest.approx(78.40, abs=0.01)
    assert previous["mean_total"] == pytest.approx(74.62, abs=0.01)
    assert fair["mean_total"] == pytest.approx(74.04, abs=0.01)
    assert original["mean_total"] == pytest.approx(71.88, abs=0.01)
    assert trained["mean_total"] > previous["mean_total"] > fair["mean_total"]
    assert trained["mean_qualified_rejected"] == pytest.approx(9.02, abs=0.01)
    assert previous["mean_qualified_rejected"] == pytest.approx(19.84, abs=0.01)
    assert trained["mean_recall"] == pytest.approx(0.9775, abs=1e-4)
    assert trained["mean_recall"] > previous["mean_recall"] > fair["mean_recall"]
    assert trained["mean_worst_disparate_impact"] == pytest.approx(0.8343, abs=1e-4)
    assert trained["mean_worst_disparate_impact"] > previous["mean_worst_disparate_impact"]
    assert trained["worst_disparate_impact_pass_rate"] == pytest.approx(0.74, abs=1e-4)
    assert (
        trained["worst_disparate_impact_pass_rate"] > previous["worst_disparate_impact_pass_rate"]
    )
    assert trained["mean_accuracy"] == pytest.approx(0.8099, abs=1e-4)
    assert trained["mean_accuracy"] < previous["mean_accuracy"] < fair["mean_accuracy"]
    # Explicitly retain the cost: fairer selection rates come with more false
    # positives sent for human review and lower accuracy against the synthetic label.
    assert trained["mean_false_positive_rate"] == pytest.approx(0.3018, abs=1e-4)
    assert trained["mean_false_positive_rate"] > previous["mean_false_positive_rate"]


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
    assert diagnostics["model"]["qualified_rejected"] == 11


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


def test_re_adding_the_proxies_does_not_improve_the_fairness_score():
    pytest.importorskip("sklearn")
    with_proxies = train_coefficients(features=MERIT_FEATURES + PROXY_FEATURES)
    assert with_proxies["prestige"] != 0.0
    # It can nudge fixture accuracy through a chance correlation, not fairness.
    assert _summary(with_proxies)["total"] <= _summary(get_model("trained"))["total"]


def test_label_is_generated_without_proxies_or_protected_attributes():
    """The fixture's merit formula never reads prestige, gap or identity."""
    import inspect

    from chaoshire import data

    source = inspect.getsource(data.generate_demo_data)
    merit_block = source[source.index("merit = (") : source.index("qualified =")]
    for column in ("prestige", "career_gap", "genders", "communities", "ages"):
        assert column not in merit_block, column


def test_cli_holdout_and_policy_study_print_their_reports(capsys, monkeypatch):
    import json

    import chaoshire.training as training
    from chaoshire.cli import main

    # Full 50-population results are pinned above; this checks CLI wiring.
    real = training.holdout_comparison
    monkeypatch.setattr(training, "holdout_comparison", lambda: real(seeds=[1, 2, 29]))
    assert main(["train", "--holdout"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["populations"] == 2  # the fixture seed is always skipped
    assert set(report["models"]) == {
        "fair",
        "original_v3",
        "previous_talentfit_v3",
        "trained",
    }

    monkeypatch.setattr(training, "policy_study", lambda: {"selected_cost": 3.0})
    assert main(["train", "--policy-study"]) == 0
    assert json.loads(capsys.readouterr().out) == {"selected_cost": 3.0}


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
