"""Regression tests for the 2026-09-13 verification findings.

Each test pins one defect that the verification pass found, so the fixes cannot
silently regress: unknown-model handling, operational metrics on unhandled
exceptions, non-assessable audits, mitigation contract hardening, injection
test discriminating power, evidence-verification robustness, upload-slot
locking, and PWA installability assets.
"""
import concurrent.futures
from typing import get_args

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import backend
from chaoshire import models
from chaoshire.agent import review_audit
from chaoshire.chaos import CHAOS_TESTS, DEFAULT_THRESHOLDS, injection_experiment, run_chaos_suite
from chaoshire.evidence import build_evidence_bundle, verify_evidence_bundle
from chaoshire.metrics import assessability, audit
from chaoshire.models import FAIR, LEGACY, build_decisions
from chaoshire.pdf_reporting import render_pdf_report
from chaoshire.platform import OPERATIONS
from chaoshire.reporting import render_html_report
from chaoshire.schemas import MitigationStrategy
from chaoshire.services import MITIGATION_STRATEGIES, mitigate, uploaded_audit
from chaoshire.state import UPLOADED, UPLOADED_LOCK

client = TestClient(backend.app)

UNKNOWN_MODEL_ROUTES = [
    ("/api/audit", {"model": "nope"}),
    ("/api/chaos", {"model": "nope"}),
    ("/api/filtered", {"model": "nope"}),
    ("/api/explain/C-1046", {"model": "nope"}),
    ("/api/evidence", {"model": "nope"}),
    ("/api/report.html", {"model": "nope"}),
    ("/api/report.pdf", {"model": "nope"}),
]


@pytest.mark.parametrize("route,params", UNKNOWN_MODEL_ROUTES)
def test_unknown_reference_model_is_rejected_not_crashed(route, params):
    response = client.get(route, params=params)
    assert response.status_code == 400
    assert "Unknown reference model" in response.json()["detail"]


def test_unknown_dataset_is_rejected():
    response = client.get("/api/audit", params={"dataset": "nope"})
    assert response.status_code == 400
    assert "Unknown dataset" in response.json()["detail"]


def test_unknown_model_raises_in_library_code():
    with pytest.raises(ValueError, match="Unknown reference model"):
        models.get_model("nope")
    with pytest.raises(ValueError, match="Unknown reference model"):
        run_chaos_suite("nope")


def test_audit_payload_self_describes_its_model():
    legacy = client.get("/api/audit", params={"model": "legacy"}).json()
    fair = client.get("/api/audit", params={"model": "fair"}).json()
    assert legacy["model"]["id"] == "legacy"
    assert legacy["model"]["title"] == "LegacyCorp Screen v1"
    assert fair["model"]["id"] == "fair"


def test_unhandled_exception_is_counted_in_operational_metrics():
    def boom() -> None:
        raise RuntimeError("deliberate verification failure")

    backend.app.router.add_api_route("/api/__verification-boom", boom, methods=["GET"])
    try:
        failing = TestClient(backend.app, raise_server_exceptions=False)
        before = OPERATIONS.snapshot()
        response = failing.get("/api/__verification-boom")
        assert response.status_code == 500
        after = OPERATIONS.snapshot()
        assert after["server_errors"] == before["server_errors"] + 1
        assert after["statuses"].get(500, 0) >= 1
    finally:
        backend.app.router.routes[:] = [
            route
            for route in backend.app.router.routes
            if getattr(route, "path", None) != "/api/__verification-boom"
        ]


def degenerate_frame(decision: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "accepted": [decision] * 60,
            "gender": ["F"] * 30 + ["M"] * 30,
            "qualified": [True, False] * 30,
        }
    )


@pytest.mark.parametrize("decision", [0, 1])
def test_decision_sets_without_variation_are_not_scored(decision):
    certificate = audit(degenerate_frame(decision))["certificate"]
    assert certificate["grade"] == "N/A"
    assert certificate["assessable"] is False
    assert certificate["total"] == 0
    assert certificate["reasons"]


def test_dataset_without_protected_attributes_is_not_scored_not_crashed():
    frame = pd.DataFrame({"accepted": [1, 0, 1], "region": ["a", "b", "a"]})
    result = audit(frame)
    assert result["certificate"]["assessable"] is False
    assert any("protected attribute" in reason for reason in result["certificate"]["reasons"])
    assert result["attributes"] == []


def test_single_group_attribute_is_not_scored():
    frame = pd.DataFrame({"accepted": [1, 0, 1], "gender": ["F"] * 3})
    assert audit(frame, attributes=["gender"])["certificate"]["assessable"] is False


def test_reference_audits_remain_assessable():
    for coefficients in (LEGACY, FAIR):
        certificate = audit(build_decisions(coefficients))["certificate"]
        assert certificate["assessable"] is True
        assert certificate["reasons"] == []


def test_assessability_helper_reports_reasons():
    assessable, reasons = assessability(degenerate_frame(1), [])
    assert assessable is False
    assert len(reasons) == 2


def test_agent_flags_non_assessable_audits():
    review = review_audit(audit(degenerate_frame(0)))
    assert review["disposition"] == "BLOCK_AND_REVIEW"
    finding = next(item for item in review["findings"] if item["id"] == "audit-not-assessable")
    assert finding["severity"] == "HIGH"
    assert review["recommended_actions"][0].startswith("Repair the audit input")


def test_reports_render_non_assessable_audits_honestly():
    result = audit(degenerate_frame(0))
    html = render_html_report(result)
    assert "Not assessable" in html
    assert "No candidate was selected" in html
    assert "<script" not in html
    assert b"Fairness risk score: not assessable" in render_pdf_report(result)


def test_mitigate_rejects_unknown_strategies():
    assert client.post("/api/mitigate", json={"strategies": ["magic"]}).status_code == 422
    direct = mitigate(["magic"])
    assert "Unknown mitigation strategies" in direct["error"]
    assert direct["available_strategies"] == list(MITIGATION_STRATEGIES)


def test_mitigate_payload_is_symmetric_and_self_describing():
    response = client.post(
        "/api/mitigate", json={"strategies": ["blind", "proxy", "calibrate"]}
    ).json()
    assert response["model"]["id"] == "legacy"
    assert set(response["before"]) == set(response["after"])
    assert response["before"]["certificate"]["total"] == 42
    assert response["after"]["certificate"]["total"] == 83
    assert response["before"]["stats"]["candidates"] == 1000


def test_mitigation_schema_and_service_agree_on_strategies():
    assert set(get_args(MitigationStrategy)) == set(MITIGATION_STRATEGIES)


def test_privilege_injection_report_includes_headroom():
    observation = injection_experiment(LEGACY, 0)
    assert "headroom" in observation.detail
    assert "before this test could fail" in observation.detail
    assert "0.4043" in observation.detail


def test_privilege_injection_can_fail_a_prestige_heavy_model():
    gamed = dict(LEGACY)
    gamed["prestige"] = 0.35
    test = next(item for item in CHAOS_TESTS if item.id == "adversarial")
    assert test.execute(gamed, DEFAULT_THRESHOLDS["adversarial"], 0)["verdict"] == "FAIL"
    assert test.execute(FAIR, DEFAULT_THRESHOLDS["adversarial"], 0)["verdict"] == "PASS"


def test_evidence_verification_rejects_non_string_digests():
    bundle = build_evidence_bundle(audit(build_decisions(LEGACY)))
    bundle["integrity"]["digest"] = None
    assert verify_evidence_bundle(bundle)["valid"] is False
    bundle["integrity"] = "not-a-dict"
    assert verify_evidence_bundle(bundle)["valid"] is False


def test_upload_slot_swap_is_thread_safe():
    def upload(index: int) -> int:
        rows = ["F,1"] * 30 + (["M,0"] * 30 if index % 2 else ["M,1"] * 30)
        response = client.post(
            "/api/upload",
            json={
                "csv": "gender,decision\n" + "\n".join(rows),
                "audit_name": f"thread-{index}",
                "protected_attributes": ["gender"],
            },
        )
        return response.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(upload, range(16)))
    assert codes == [200] * 16
    with UPLOADED_LOCK:
        assert UPLOADED["audit"]["audit_name"].startswith("thread-")
    assert uploaded_audit()["audit_name"].startswith("thread-")


def test_write_protection_still_blocks_appeals(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_API_KEY", "guarded")
    payload = {"candidate_id": "C-1046", "message": "Please review this decision."}
    assert client.post("/api/appeals", json=payload).status_code == 401


def test_missing_icon_returns_404():
    assert client.get("/icons/does-not-exist.png").status_code == 404
    # Path-traversal attempts resolve to a dict miss, never a filesystem lookup.
    assert client.get("/icons/..%2Fapp.py").status_code == 404
    assert client.get("/icons/..%2f..%2fbackend.py").status_code == 404


def test_uploaded_dataset_feeds_reports_and_evidence():
    csv_text = "gender,decision\n" + "\n".join(["F,1"] * 30 + ["M,0"] * 30)
    assert client.post(
        "/api/upload", json={"csv": csv_text, "protected_attributes": ["gender"]}
    ).status_code == 200
    html = client.get("/api/report.html", params={"dataset": "uploaded"})
    assert html.status_code == 200
    assert "ChaosHire Audit Report" in html.text
    assert client.get("/api/report.pdf", params={"dataset": "uploaded"}).status_code == 200
    assert client.get("/api/evidence", params={"dataset": "uploaded"}).status_code == 200


def test_readiness_reports_unavailable_repository(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_DB_PATH", "/proc/chaoshire-readonly/nope.db")
    response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "Audit repository is unavailable."


def test_empty_dataset_is_not_assessable():
    frame = pd.DataFrame({"accepted": pd.Series(dtype=int), "gender": pd.Series(dtype=str)})
    certificate = audit(frame)["certificate"]
    assert certificate["assessable"] is False
    assert certificate["reasons"] == ["The audit contains no candidate rows."]


def test_unknown_chaos_threshold_id_is_rejected():
    with pytest.raises(ValueError, match="Unknown chaos test threshold"):
        run_chaos_suite("legacy", {"nope": {"warn": 0.1, "fail": 0.2}})
    response = client.post("/api/chaos/run", json={"thresholds": {"nope": {"warn": 0.1, "fail": 0.2}}})
    assert response.status_code == 400


def test_evidence_verification_rejects_missing_payload():
    assert verify_evidence_bundle({"integrity": {"digest": "sha256:x"}})["valid"] is False
