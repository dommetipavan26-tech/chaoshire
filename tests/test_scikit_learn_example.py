"""The scikit-learn integration example must stay real, deterministic, and gated."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("sklearn", reason="install requirements-examples.txt to run the example")

from chaoshire.adapters import DecisionAdapter  # noqa: E402
from examples import scikit_learn_adapter as example  # noqa: E402


@pytest.fixture(scope="module")
def population():
    return example.synthetic_population(example.SEED, example.POPULATION)


def test_synthetic_population_is_deterministic_and_labelled():
    first = example.synthetic_population(seed=1046, size=250)
    second = example.synthetic_population(seed=1046, size=250)
    assert first.equals(second)
    assert len(first) == 250
    assert set(first["gender"]) <= {"M", "F", "NB"}
    assert set(first["qualified"]) == {0, 1}
    # A useful fixture must contain both decisions and both labels.
    assert first["qualified"].mean() == pytest.approx(0.45, abs=0.08)


def test_adapter_contract_and_decision_shape(population):
    model, decisions = example.train_and_decide(population, example.NAIVE_FEATURES)
    adapter = example.to_adapter("sklearn-test", decisions, example.NAIVE_FEATURES)
    assert isinstance(adapter, DecisionAdapter)
    frame = adapter.decisions()
    assert {"accepted", "candidate_id", "qualified", "gender"} <= set(frame.columns)
    assert set(frame["accepted"].unique()) == {0, 1}
    assert frame["accepted"].sum() > 0
    assert len(frame) == len(population)
    described = adapter.describe()
    assert described["mode"] == "provided_decisions"
    assert described["library"] == "scikit-learn"
    assert described["features"] == example.NAIVE_FEATURES
    assert described["pipeline"] == "StandardScaler + LogisticRegression"
    assert len(model.named_steps) == 2


def test_same_seed_reproduces_identical_evidence(population):
    first = example.evaluate("gate-run", population, example.NAIVE_FEATURES, example.SEED)
    second = example.evaluate("gate-run", population, example.NAIVE_FEATURES, example.SEED)
    assert first["evidence"]["digest"] == second["evidence"]["digest"]
    assert first["policy"] == second["policy"]
    assert first["evidence"]["verified"] is True
    assert first["evidence"]["algorithm"] == "SHA-256"


def test_tampered_evidence_bundle_fails_verification(population):
    from chaoshire.evidence import build_evidence_bundle, verify_evidence_bundle

    result = example.evaluate("tamper", population, example.NAIVE_FEATURES, example.SEED)
    bundle = build_evidence_bundle(result["audit"])
    bundle["payload"]["audit"]["certificate"]["total"] = 100
    assert verify_evidence_bundle(bundle)["valid"] is False


def test_naive_resume_model_is_blocked_and_blind_model_releases(population):
    naive = example.evaluate("naive", population, example.NAIVE_FEATURES, example.SEED)
    blind = example.evaluate("blind", population, example.BLIND_FEATURES, example.SEED)
    assert naive["policy"]["status"] == "FAIL"
    assert "equal_opportunity_gap" in naive["policy"]["blocking_checks"]
    assert blind["policy"]["status"] == "PASS"
    # Utility is reported, not hidden: the fairer fixture is not better at everything.
    assert blind["utility"]["accuracy"] <= naive["utility"]["accuracy"]
    assert blind["utility"]["qualified_missed"] >= naive["utility"]["qualified_missed"]


def test_release_policy_checks_are_transparent(population):
    result = example.evaluate("checks", population, example.BLIND_FEATURES, example.SEED)
    policy = example.release_policy(result["audit"], result["utility"])
    labels = {check["id"] for check in policy["checks"]}
    assert labels == {
        "minimum_risk_score",
        "disparate_impact",
        "parity_gap",
        "equal_opportunity_gap",
        "utility_floor",
    }
    assert all(isinstance(check["passed"], bool) for check in policy["checks"])
    assert policy["status"] == ("PASS" if not policy["blocking_checks"] else "FAIL")


def test_cli_run_and_json_output_are_deterministic(tmp_path, capsys):
    assert example.main(["--size", "400", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["population"] == 400
    assert [model["candidates"] for model in payload["models"]] == [400, 400]

    assert example.main(["--size", "400", "--json"]) == 0
    again = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert again == payload
    assert example.main(["--size", "400", "--json", "--strict"]) == 1
