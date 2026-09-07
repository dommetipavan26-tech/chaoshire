"""Persistent aggregate audit-history tests."""
from pathlib import Path

from fastapi.testclient import TestClient

import backend
from chaoshire.state import UPLOADED

client = TestClient(backend.app)


def upload_named_audit(name: str = "Quarterly screening review") -> dict:
    response = client.post(
        "/api/upload",
        json={
            "audit_name": name,
            "csv": "person,group,outcome\nSecret-001,A,advance\nSecret-002,A,reject\nSecret-003,B,advance\nSecret-004,B,reject\n",
            "decision_column": "outcome",
            "favorable_values": ["advance"],
            "protected_attributes": ["group"],
            "candidate_id_column": "person",
            "minimum_group_size": 2,
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    return response.json()


def test_upload_creates_a_named_audit_record():
    uploaded = upload_named_audit()
    assert uploaded["audit_id"].startswith("AUD-")
    assert uploaded["audit_name"] == "Quarterly screening review"
    assert uploaded["created_at"].endswith("+00:00")

    history = client.get("/api/audits").json()["audits"]
    assert len(history) == 1
    assert history[0]["audit_id"] == uploaded["audit_id"]
    assert history[0]["candidates"] == 4
    assert history[0]["protected_attributes"] == ["group"]


def test_audit_detail_survives_loss_of_in_memory_upload():
    uploaded = upload_named_audit()
    UPLOADED.update({"df": None, "metadata": None, "audit": None})

    detail = client.get(f"/api/audits/{uploaded['audit_id']}")
    assert detail.status_code == 200
    assert detail.json()["audit_name"] == "Quarterly screening review"
    assert detail.json()["stats"]["candidates"] == 4


def test_unknown_audit_returns_404():
    response = client.get("/api/audits/AUD-DOES-NOT-EXIST")
    assert response.status_code == 404
    assert response.json()["detail"] == "Audit record not found."


def test_raw_candidate_rows_are_not_persisted(monkeypatch, tmp_path):
    database = tmp_path / "privacy-test.db"
    monkeypatch.setenv("CHAOSHIRE_DB_PATH", str(database))
    upload_named_audit("Privacy check")

    raw_database = Path(database).read_bytes()
    assert b"Secret-001" not in raw_database
    assert b"Secret-004" not in raw_database


def test_history_limit_is_bounded_and_newest_first():
    first = upload_named_audit("First audit")
    second = upload_named_audit("Second audit")
    response = client.get("/api/audits", params={"limit": 1})
    assert response.status_code == 200
    audits = response.json()["audits"]
    assert len(audits) == 1
    assert audits[0]["audit_id"] == second["audit_id"]
    assert audits[0]["audit_id"] != first["audit_id"]


def test_audit_name_validation():
    response = client.post(
        "/api/upload",
        json={
            "audit_name": "",
            "csv": "group,decision\nA,1\nB,0\n",
            "protected_attributes": ["group"],
        },
    )
    assert response.status_code == 422
