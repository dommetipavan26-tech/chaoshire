"""Days 11-20: agent, adapters, security, evidence, PDF, operations, and demo."""

import json
import re

import pandas as pd
from conftest import operator_client

from chaoshire import __version__
from chaoshire.adapters import CallableDecisionAdapter, DecisionAdapter, ReferenceModelAdapter
from chaoshire.agent import review_audit
from chaoshire.build_info import SERVICE_WORKER_CACHE, VERSION
from chaoshire.cli import main
from chaoshire.evidence import build_evidence_bundle, verify_evidence_bundle
from chaoshire.metrics import audit
from chaoshire.models import LEGACY, build_decisions
from chaoshire.platform import SlidingWindowLimiter

client = operator_client()


def test_v020_contract_and_operational_endpoints():
    # Not a literal: build_info.VERSION is the single source of truth and
    # tests/infrastructure/test_build_info.py pins it to the package version.
    assert __version__ == VERSION
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    assert client.get("/api/live").json() == {"status": "alive"}
    assert client.get("/api/ready").json()["status"] == "ready"
    assert client.head("/api/health").status_code == 200
    assert client.head("/api/live").status_code == 200
    assert client.head("/api/ready").status_code == 200
    metrics = client.get("/api/metrics").json()
    assert metrics["requests"] >= 2
    assert metrics["uptime_seconds"] >= 0


def test_security_headers_and_request_id_are_present():
    response = client.get("/api/health", headers={"X-Request-ID": "portfolio-test"})
    assert response.headers["x-request-id"] == "portfolio-test"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "camera=()" in response.headers["permissions-policy"]


def test_optional_api_key_protects_mutations(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_API_KEY", "correct-secret")
    payload = {"candidate_id": "C-1046", "message": "Please review this decision."}
    assert client.post("/api/appeals", json=payload).status_code == 401
    response = client.post("/api/appeals", json=payload, headers={"X-API-Key": "correct-secret"})
    assert response.status_code == 200


def test_request_size_limit(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_MAX_BODY_BYTES", "10")
    response = client.post("/api/gate", content=b"{}", headers={"content-length": "11"})
    assert response.status_code == 413


def test_sliding_window_limiter():
    limiter = SlidingWindowLimiter()
    assert limiter.allow("client", 2)
    assert limiter.allow("client", 2)
    assert not limiter.allow("client", 2)


def test_reference_and_callable_adapter_contracts():
    reference = ReferenceModelAdapter("legacy")
    assert isinstance(reference, DecisionAdapter)
    assert reference.describe()["deterministic"] is True
    assert len(reference.decisions()) == 1000

    custom = CallableDecisionAdapter("candidate-v3", lambda: pd.DataFrame({"accepted": [1, 0]}))
    assert custom.decisions()["accepted"].tolist() == [1, 0]


def test_callable_adapter_rejects_invalid_output():
    adapter = CallableDecisionAdapter("broken", lambda: pd.DataFrame({"score": [0.2]}))
    try:
        adapter.decisions()
    except ValueError as error:
        assert "accepted" in str(error)
    else:
        raise AssertionError("Invalid adapter output should be rejected")


def test_adapter_catalog_endpoint():
    result = client.get("/api/adapters").json()
    assert result["required_normalized_columns"] == ["accepted"]
    assert {item["id"] for item in result["adapters"]} == {
        "reference-model",
        "csv-decisions",
        "callable-decisions",
        "remote-http",
        "shap-compatible",
    }


def test_agent_review_is_deterministic_and_evidence_linked():
    first = client.post("/api/agent/review", json={"model": "legacy"}).json()
    second = client.post("/api/agent/review", json={"model": "legacy"}).json()
    assert first == second
    assert first["disposition"] == "BLOCK_AND_REVIEW"
    assert first["agent"]["external_ai"] is False
    assert all(item["evidence_path"].startswith("/") for item in first["findings"])


def test_agent_can_review_audit_without_chaos():
    result = review_audit(audit(build_decisions(LEGACY)))
    assert result["findings"]
    assert result["risk_summary"]["high"] > 0


def test_evidence_digest_detects_tampering():
    result = audit(build_decisions(LEGACY))
    bundle = build_evidence_bundle(result)
    assert verify_evidence_bundle(bundle)["valid"] is True
    bundle["payload"]["audit"]["certificate"]["total"] = 100
    assert verify_evidence_bundle(bundle)["valid"] is False


def test_evidence_api_round_trip_and_tamper_detection():
    bundle = client.get("/api/evidence?model=legacy").json()
    verified = client.post("/api/evidence/verify", json={"bundle": bundle}).json()
    assert verified["valid"] is True
    altered = json.loads(json.dumps(bundle))
    altered["payload"]["audit"]["stats"]["accepted"] += 1
    rejected = client.post("/api/evidence/verify", json={"bundle": altered}).json()
    assert rejected["valid"] is False


def test_native_pdf_is_downloadable_and_valid():
    response = client.get("/api/report.pdf?model=legacy")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == "attachment; filename=chaoshire-report.pdf"
    assert response.content.startswith(b"%PDF-1.4")
    assert response.content.endswith(b"%%EOF\n")


def test_guided_demo_preserves_reviewed_story():
    result = client.get("/api/demo").json()
    assert result["duration_minutes"] == 3
    assert len(result["steps"]) == 8
    assert result["steps"][0]["evidence"]["certificate"]["total"] == 32
    assert result["steps"][-1]["evidence"]["status"] == "PASS"


def test_portfolio_cli_commands(tmp_path, capsys):
    assert main(["review", "--model", "legacy"]) == 0
    assert '"disposition": "BLOCK_AND_REVIEW"' in capsys.readouterr().out
    evidence = tmp_path / "evidence.json"
    assert main(["evidence", "--output", str(evidence)]) == 0
    assert json.loads(evidence.read_text())["integrity"]["algorithm"] == "SHA-256"
    pdf = tmp_path / "report.pdf"
    assert main(["report", "--format", "pdf", "--output", str(pdf)]) == 0
    assert pdf.read_bytes().startswith(b"%PDF-1.4")


def test_pwa_and_mobile_accessibility_markers():
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    body = manifest.json()
    assert body["display"] == "standalone"
    purposes = {icon["purpose"] for icon in body["icons"]}
    assert {"any", "maskable"} <= purposes
    sizes = {icon["sizes"] for icon in body["icons"]}
    assert "192x192" in sizes and "512x512" in sizes
    for icon in body["icons"]:
        icon_response = client.get(icon["src"])
        assert icon_response.status_code == 200
        assert icon_response.headers["content-type"] == "image/png"
        assert icon_response.content.startswith(b"\x89PNG")
    service_worker = client.get("/service-worker.js")
    assert SERVICE_WORKER_CACHE in service_worker.text
    assert "__CACHE_NAME__" not in service_worker.text
    assert "/icons/icon-192.png" in service_worker.text
    assert "skipWaiting" in service_worker.text
    assert "clients.claim" in service_worker.text
    assert "no-cache" in service_worker.headers["cache-control"]
    home = client.get("/")
    assert home.headers["cache-control"] == "no-cache"
    page = home.text
    assert page.count("</body>") == 1
    assert page.count("</html>") == 1
    assert page.rstrip().endswith("</html>")
    assert 'href="#main"' in page
    # External stylesheet carries the responsive and reduced-motion rules; the
    # page only links to it (style-src 'unsafe-inline' was dropped in v0.24.0).
    css = client.get("/static/chaoshire.css")
    assert css.status_code == 200
    assert "@media(max-width:600px)" in css.text
    assert "prefers-reduced-motion" in css.text
    assert 'href="/static/chaoshire.css"' in page
    # The tab was renamed from "Review Agent" — the reviewer flagged the name as
    # an AI overclaim for a deterministic rules engine (v0.23.4 red-flag pass).
    assert "Fairness Review" in page and "Guided Demo" in page
