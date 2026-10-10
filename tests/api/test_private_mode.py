"""Opt-in single-operator protection for shared applicant-related data.

Private mode is a single shared API-key boundary, not tenant isolation. The
public synthetic demo remains available, while published history, appeals,
and uploaded-data outputs require the operator key.
"""

from conftest import operator_client
from fastapi.testclient import TestClient

import backend


def _sample_csv() -> str:
    return "gender,decision\n" + "\n".join(["F,1"] * 30 + ["M,0"] * 30)


def test_private_mode_protects_all_shared_data_paths(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_PRIVATE_MODE", "1")
    monkeypatch.setenv("CHAOSHIRE_ALLOW_ANONYMOUS_WRITES", "1")
    operator = operator_client()
    public = TestClient(backend.app)

    uploaded = operator.post(
        "/api/upload",
        json={
            "csv": _sample_csv(),
            "audit_name": "private-test",
            "protected_attributes": ["gender"],
        },
    )
    assert uploaded.status_code == 200
    audit_id = uploaded.json()["audit_id"]
    appeal = operator.post(
        "/api/appeals",
        json={"candidate_id": "C-1046", "message": "synthetic private-mode test"},
    )
    assert appeal.status_code == 200

    # The existing operator key can read every shared/history surface.
    assert operator.get("/api/appeals").status_code == 200
    assert operator.get("/api/audits").status_code == 200
    assert operator.get(f"/api/audits/{audit_id}").status_code == 200
    assert operator.get("/api/audit", params={"dataset": "uploaded"}).status_code == 200
    assert operator.get("/api/audit/export").status_code == 200
    assert operator.get("/api/evidence", params={"dataset": "uploaded"}).status_code == 200
    assert operator.get("/api/report.html", params={"dataset": "uploaded"}).status_code == 200
    assert operator.get("/api/report.pdf", params={"dataset": "uploaded"}).status_code == 200
    assert (
        operator.post(
            "/api/agent/review", json={"model": "legacy", "dataset": "uploaded"}
        ).status_code
        == 200
    )

    protected_reads = [
        ("get", "/api/appeals", {}),
        ("get", "/api/audits", {}),
        ("get", f"/api/audits/{audit_id}", {}),
        ("get", "/api/audit", {"params": {"dataset": "uploaded"}}),
        ("get", "/api/audit/export", {}),
        ("get", "/api/evidence", {"params": {"dataset": "uploaded"}}),
        ("get", "/api/report.html", {"params": {"dataset": "uploaded"}}),
        ("get", "/api/report.pdf", {"params": {"dataset": "uploaded"}}),
        (
            "post",
            "/api/agent/review",
            {"json": {"model": "legacy", "dataset": "uploaded"}},
        ),
    ]
    for method, path, kwargs in protected_reads:
        response = getattr(public, method)(path, **kwargs)
        assert response.status_code == 401, (method, path, response.text)

    # Anonymous mutation settings cannot weaken private mode, and reference
    # fixtures remain public because they contain only synthetic demo data.
    assert (
        public.post("/api/appeals", json={"candidate_id": "C-1046", "message": "x"}).status_code
        == 401
    )
    assert (
        public.post(
            "/api/upload",
            json={"csv": _sample_csv(), "protected_attributes": ["gender"]},
        ).status_code
        == 401
    )
    assert public.get("/api/audit", params={"dataset": "demo"}).status_code == 200


def test_private_mode_hides_public_posture_even_if_disclosure_is_requested(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_PRIVATE_MODE", "1")
    monkeypatch.setenv("CHAOSHIRE_DISCLOSE_WRITE_POSTURE", "1")

    public = TestClient(backend.app)
    posture = public.get("/api/meta").json()["platform"]
    assert posture["disclosed"] is False
    assert "private_mode" not in posture
    assert "api_key_configured" not in posture

    operator = operator_client()
    full_posture = operator.get("/api/ops/posture").json()
    assert full_posture["private_mode"] is True
    assert full_posture["anonymous_writes_allowed"] is False
    assert "not tenant isolation" in full_posture["note"]


def test_private_mode_without_a_configured_key_fails_closed(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_PRIVATE_MODE", "1")
    monkeypatch.setenv("CHAOSHIRE_ALLOW_ANONYMOUS_WRITES", "1")
    monkeypatch.delenv("CHAOSHIRE_API_KEY", raising=False)

    client = TestClient(backend.app)
    assert client.get("/api/audits").status_code == 503
    assert client.get("/api/appeals").status_code == 503
    assert (
        client.post("/api/appeals", json={"candidate_id": "C-1046", "message": "x"}).status_code
        == 503
    )
