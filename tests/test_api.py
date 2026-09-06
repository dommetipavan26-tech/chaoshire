"""Public API contract tests."""
from fastapi.testclient import TestClient

import backend

client = TestClient(backend.app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ChaosHire"}


def test_meta_describes_both_reference_models():
    response = client.get("/api/meta")
    assert response.status_code == 200
    body = response.json()
    assert [model["id"] for model in body["models"]] == ["legacy", "fair"]
    assert body["thresholds"]["disparate_impact"] == 0.8
    assert "C-1046" in body["sample_ids"]


def test_legacy_audit_contract():
    response = client.get("/api/audit", params={"model": "legacy"})
    assert response.status_code == 200
    body = response.json()
    assert body["stats"]["candidates"] == 1000
    assert body["certificate"]["total"] == 42
    assert len(body["attributes"]) == 3


def test_chaos_suite_has_five_tests_and_expected_resilience():
    response = client.get("/api/chaos", params={"model": "legacy"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["tests"]) == 5
    assert body["resilience"] == 30
    assert {test["id"] for test in body["tests"]} == {
        "gender_swap", "ethnicity_swap", "adversarial", "gap_stress", "age_stress"
    }


def test_fair_model_is_counterfactually_resilient():
    response = client.get("/api/chaos", params={"model": "fair"})
    assert response.status_code == 200
    body = response.json()
    assert body["resilience"] == 100
    assert all(test["verdict"] == "PASS" for test in body["tests"])


def test_unknown_candidate_returns_explanatory_error():
    response = client.get("/api/candidate/DOES-NOT-EXIST")
    assert response.status_code == 200
    assert "error" in response.json()


def test_sample_csv_is_downloadable():
    response = client.get("/api/sample.csv")
    assert response.status_code == 200
    assert response.text.startswith("candidate_id,gender,ethnicity,age_band,decision,qualified")
    assert len(response.text.splitlines()) == 201
