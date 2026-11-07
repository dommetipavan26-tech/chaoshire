"""Per-audit access control for published audit records.

A published audit is no longer world-readable by identifier alone: reading
its full record requires the operator key or the random access token issued
once, in the upload response. Only the token's SHA-256 digest is stored.
"""

from pathlib import Path

from conftest import TEST_API_KEY, operator_client
from fastapi.testclient import TestClient

import backend
from chaoshire.repository import save_audit

client = operator_client()
CSV = "person,group,outcome\nP-1,A,advance\nP-2,A,reject\nP-3,B,advance\nP-4,B,reject\n"


def publish(name: str = "Access-controlled review") -> dict:
    response = client.post(
        "/api/upload",
        json={
            "audit_name": name,
            "csv": CSV,
            "decision_column": "outcome",
            "favorable_values": ["advance"],
            "protected_attributes": ["group"],
            "candidate_id_column": "person",
            "minimum_group_size": 2,
        },
    )
    assert response.status_code == 200
    return response.json()


def anonymous() -> TestClient:
    return TestClient(backend.app)


def test_published_upload_issues_a_token_exactly_once():
    body = publish()
    token = body["audit_access_token"]
    assert token and len(token) >= 32
    # The token is not part of the persisted audit record or the listing.
    assert token not in str(body["audit"])
    listing = client.get("/api/audits").json()
    assert listing["audits"][0]["access_required"] is True
    assert token not in str(listing)


def test_token_is_never_persisted_only_its_digest(monkeypatch, tmp_path):
    database = tmp_path / "token-storage.db"
    monkeypatch.setenv("CHAOSHIRE_DB_PATH", str(database))
    body = publish("Digest-only storage")
    raw = Path(database).read_bytes()
    assert body["audit_access_token"].encode() not in raw
    assert b"P-1" not in raw  # raw candidate rows stay unpersisted too


def test_detail_requires_operator_key_or_the_audit_token():
    body = publish()
    audit_id, token = body["audit_id"], body["audit_access_token"]
    public = anonymous()

    assert public.get(f"/api/audits/{audit_id}").status_code == 401
    assert (
        public.get(f"/api/audits/{audit_id}", headers={"X-Audit-Access-Token": "wrong"}).status_code
        == 401
    )
    via_header = public.get(f"/api/audits/{audit_id}", headers={"X-Audit-Access-Token": token})
    assert via_header.status_code == 200
    assert via_header.json()["audit_id"] == audit_id
    via_query = public.get(f"/api/audits/{audit_id}", params={"access_token": token})
    assert via_query.status_code == 200
    # The operator key still reads every audit.
    assert client.get(f"/api/audits/{audit_id}").status_code == 200


def test_a_token_only_opens_its_own_audit():
    first, second = publish("First"), publish("Second")
    public = anonymous()
    response = public.get(
        f"/api/audits/{first['audit_id']}",
        headers={"X-Audit-Access-Token": second["audit_access_token"]},
    )
    assert response.status_code == 401


def test_unknown_audit_is_masked_from_unauthenticated_probing():
    public = anonymous()
    assert public.get("/api/audits/AUD-DOES-NOT-EXIST").status_code == 401
    assert client.get("/api/audits/AUD-DOES-NOT-EXIST").status_code == 404


def test_shared_uploaded_slot_requires_the_same_access():
    body = publish()
    token = body["audit_access_token"]
    public = anonymous()
    assert public.get("/api/audit", params={"dataset": "uploaded"}).status_code == 401
    assert public.get("/api/audit/export").status_code == 401
    assert public.get("/api/report.html", params={"dataset": "uploaded"}).status_code == 401
    headers = {"X-Audit-Access-Token": token}
    assert (
        public.get("/api/audit", params={"dataset": "uploaded"}, headers=headers).status_code == 200
    )
    assert public.get("/api/audit/export", headers=headers).status_code == 200
    assert client.get("/api/audit", params={"dataset": "uploaded"}).status_code == 200


def test_audits_saved_without_a_token_are_operator_only():
    audit_id = save_audit(
        {
            "stats": {"candidates": 2, "accepted": 1},
            "certificate": {"total": 50, "grade": "D"},
        },
        "Legacy record",
        {"protected_attributes": ["group"]},
    )
    public = anonymous()
    assert public.get(f"/api/audits/{audit_id}").status_code == 401
    assert (
        public.get(
            f"/api/audits/{audit_id}", headers={"X-Audit-Access-Token": "anything"}
        ).status_code
        == 401
    )
    assert client.get(f"/api/audits/{audit_id}").status_code == 200
    assert TEST_API_KEY  # the operator client above authenticates with it
