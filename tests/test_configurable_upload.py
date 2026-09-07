"""Tests for configurable bring-your-own-model audits."""
from fastapi.testclient import TestClient

import backend

client = TestClient(backend.app)


def test_custom_columns_values_and_protected_attributes():
    csv_text = "person_id,region,disability_status,outcome,job_ready\n" + "\n".join(
        [f"A{i},north,no,advance,qualified" for i in range(25)]
        + [f"B{i},south,yes,reject,qualified" for i in range(25)]
    )
    response = client.post(
        "/api/upload",
        json={
            "csv": csv_text,
            "decision_column": "outcome",
            "favorable_values": ["advance"],
            "qualification_column": "job_ready",
            "qualified_values": ["qualified"],
            "protected_attributes": ["region", "disability_status"],
            "candidate_id_column": "person_id",
            "minimum_group_size": 20,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["attributes_found"] == ["region", "disability_status"]
    assert body["configuration"]["decision_column"] == "outcome"
    assert body["configuration"]["minimum_group_size"] == 20

    audit = client.get("/api/audit", params={"dataset": "uploaded"}).json()
    assert audit["stats"]["candidates"] == 50
    assert audit["stats"]["accepted"] == 25
    assert audit["configuration"]["protected_attributes"] == [
        "region", "disability_status"
    ]
    assert {item["attribute"] for item in audit["attributes"]} == {
        "region", "disability_status"
    }


def test_missing_configured_column_returns_available_columns():
    response = client.post(
        "/api/upload",
        json={
            "csv": "group,result\nA,yes\nB,no\n",
            "decision_column": "decision",
            "protected_attributes": ["group"],
        },
    )
    body = response.json()
    assert "Decision column 'decision' was not found" in body["error"]
    assert body["available_columns"] == ["group", "result"]


def test_high_cardinality_identifier_is_rejected_as_attribute():
    rows = [f"C-{i},yes" for i in range(101)]
    response = client.post(
        "/api/upload",
        json={
            "csv": "candidate_id,decision\n" + "\n".join(rows),
            "protected_attributes": ["candidate_id"],
        },
    )
    assert "looks like an identifier" in response.json()["error"]


def test_missing_group_values_are_reported_separately():
    response = client.post(
        "/api/upload",
        json={
            "csv": "region,decision\nnorth,1\n,0\nsouth,1\n",
            "protected_attributes": ["region"],
            "minimum_group_size": 2,
        },
    )
    body = response.json()
    assert body["ok"] is True
    assert any("missing values" in warning for warning in body["warnings"])

    audit = client.get("/api/audit", params={"dataset": "uploaded"}).json()
    groups = audit["attributes"][0]["groups"]
    assert "(missing)" in {group["group"] for group in groups}


def test_downloadable_json_report_has_attachment_header():
    client.post(
        "/api/upload",
        json={
            "csv": "group,decision\nA,1\nA,0\nB,1\nB,0\n",
            "protected_attributes": ["group"],
            "minimum_group_size": 2,
        },
    )
    response = client.get("/api/audit/export")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        "attachment; filename=chaoshire-audit.json"
    )
    assert response.json()["configuration"]["protected_attributes"] == ["group"]


def test_upload_request_enforces_group_size_bounds():
    response = client.post(
        "/api/upload",
        json={
            "csv": "group,decision\nA,1\nB,0\n",
            "protected_attributes": ["group"],
            "minimum_group_size": 1,
        },
    )
    assert response.status_code == 422
