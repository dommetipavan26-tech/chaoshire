"""End-to-end tests for the main product workflows."""
from fastapi.testclient import TestClient

import backend

client = TestClient(backend.app)


def test_home_serves_the_dashboard():
    response = client.get("/")
    assert response.status_code == 200
    assert "ChaosHire" in response.text
    assert "Waking up the server" in response.text


def test_filtered_view_preserves_reviewed_human_cost_numbers():
    response = client.get("/api/filtered", params={"model": "legacy"})
    assert response.status_code == 200
    body = response.json()
    assert body["total_rejected"] == 441
    assert body["qualified_missed"] == 42
    assert body["top_reasons"][0]["label"] == "Age 50+ penalty"


def test_candidate_explanation_and_appeal_flow():
    explanation = client.get("/api/explain/C-1046", params={"model": "legacy"})
    assert explanation.status_code == 200
    assert explanation.json()["decision"] == "Rejected"
    assert explanation.json()["score"] == 0.4647

    candidate = client.get("/api/candidate/C-1046")
    assert candidate.status_code == 200
    assert candidate.json()["can_appeal"] is True

    appeal = client.post(
        "/api/appeals",
        json={"candidate_id": "C-1046", "message": "Please review my application."},
    )
    assert appeal.status_code == 200
    assert appeal.json()["priority"] == "HIGH — qualified candidate rejected"

    queue = client.get("/api/appeals")
    assert queue.status_code == 200
    assert queue.json()["appeals"][0]["candidate_id"] == "C-1046"


def test_request_validation_rejects_empty_appeal_message():
    response = client.post(
        "/api/appeals",
        json={"candidate_id": "C-1046", "message": ""},
    )
    assert response.status_code == 422


def test_mitigation_endpoint_preserves_reviewed_improvement():
    response = client.post(
        "/api/mitigate",
        json={"strategies": ["blind", "proxy", "calibrate"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["before"]["total"], body["before"]["grade"]) == (42, "F")
    assert (
        body["after"]["certificate"]["total"],
        body["after"]["certificate"]["grade"],
    ) == (83, "B")


def test_upload_validation_and_uploaded_audit():
    missing_decision = client.post("/api/upload", json={"csv": "gender,qualified\nF,1\n"})
    assert missing_decision.status_code == 200
    assert "error" in missing_decision.json()

    csv_text = "gender,decision,qualified\n" + "\n".join(
        ["F,1,1"] * 30 + ["M,1,1"] * 30
    )
    upload = client.post("/api/upload", json={"csv": csv_text})
    assert upload.status_code == 200
    upload_body = upload.json()
    assert upload_body["ok"] is True
    assert upload_body["rows"] == 60
    assert upload_body["attributes_found"] == ["gender"]
    assert upload_body["has_ground_truth"] is True
    assert upload_body["configuration"]["minimum_group_size"] == 30

    result = client.get("/api/audit", params={"dataset": "uploaded"})
    assert result.status_code == 200
    assert result.json()["stats"]["candidates"] == 60
    assert result.json()["certificate"]["grade"] == "A"


def test_chaos_suite_is_repeatable_across_calls():
    first = client.get("/api/chaos", params={"model": "legacy"}).json()
    second = client.get("/api/chaos", params={"model": "legacy"}).json()
    assert first == second
