"""Tests for the SHAP-compatible explanation adapter (chaoshire.explain)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from chaoshire.app import app
from chaoshire.explain import adapter_catalog_entry, shap_batch, shap_explanation
from chaoshire.models import FEATURE_LABELS


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_shap_explanation_shape():
    result = shap_explanation("C-1000")
    assert "error" not in result
    assert result["candidate_id"] == "C-1000"
    assert result["adapter"] == "shap-compatible"
    assert result["format_version"] == "1.0"
    assert isinstance(result["base_value"], float)
    assert isinstance(result["values"], list)
    assert isinstance(result["feature_names"], list)
    assert isinstance(result["data"], list)
    assert len(result["values"]) == len(result["feature_names"])
    assert len(result["values"]) == len(result["data"])
    assert isinstance(result["output"], float)
    assert isinstance(result["expected_value"], float)


def test_shap_expected_value_equals_base_plus_values():
    """The expected_value should equal base_value + sum(values)."""
    result = shap_explanation("C-1000")
    expected = round(result["base_value"] + sum(result["values"]), 6)
    assert abs(result["expected_value"] - expected) < 1e-4


def test_shap_feature_names_are_human_readable():
    result = shap_explanation("C-1000")
    # All feature names should be from the FEATURE_LABELS vocabulary
    known_labels = set(FEATURE_LABELS.values())
    for name in result["feature_names"]:
        assert name in known_labels, f"Unknown feature label: {name}"


def test_shap_unknown_candidate():
    result = shap_explanation("DOES-NOT-EXIST")
    assert "error" in result


def test_shap_batch():
    result = shap_batch(["C-1000", "C-1001"])
    assert result["count"] == 2
    assert len(result["explanations"]) == 2
    assert result["adapter"] == "shap-compatible"
    for explanation in result["explanations"]:
        assert "error" not in explanation
        assert explanation["adapter"] == "shap-compatible"


def test_shap_batch_partial_error():
    result = shap_batch(["C-1000", "DOES-NOT-EXIST"])
    assert result["count"] == 2
    assert "error" not in result["explanations"][0]
    assert "error" in result["explanations"][1]


def test_shap_adapter_catalog_entry():
    entry = adapter_catalog_entry()
    assert entry["id"] == "shap-compatible"
    assert entry["status"] == "available"


def test_shap_route_single(client):
    response = client.get("/api/explain/shap/C-1000?model=legacy")
    assert response.status_code == 200
    data = response.json()
    assert data["candidate_id"] == "C-1000"
    assert data["adapter"] == "shap-compatible"


def test_shap_route_unknown_candidate(client):
    response = client.get("/api/explain/shap/NOPE?model=legacy")
    assert response.status_code == 404


def test_shap_route_batch(client):
    response = client.post(
        "/api/explain/shap/batch",
        json={"candidate_ids": ["C-1000", "C-1001"], "model": "legacy"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2


def test_shap_route_batch_validates_model(client):
    response = client.post(
        "/api/explain/shap/batch",
        json={"candidate_ids": ["C-1000"], "model": "nope"},
    )
    assert response.status_code == 422


def test_shap_route_batch_validates_empty(client):
    response = client.post(
        "/api/explain/shap/batch",
        json={"candidate_ids": [], "model": "legacy"},
    )
    assert response.status_code == 422


def test_shap_model_selection(client):
    """SHAP explanations respect the model parameter."""
    legacy = client.get("/api/explain/shap/C-1000?model=legacy").json()
    fair = client.get("/api/explain/shap/C-1000?model=fair").json()
    # Different models should produce different outputs
    assert legacy["output"] != fair["output"]


def test_shap_in_adapter_catalog(client):
    catalog = client.get("/api/adapters").json()
    ids = {a["id"] for a in catalog["adapters"]}
    assert "shap-compatible" in ids
