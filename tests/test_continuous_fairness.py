"""Chaos evidence, model comparison, release-gate, and report tests."""

from fastapi.testclient import TestClient

import backend
from chaoshire.cli import main
from chaoshire.reporting import render_html_report

client = TestClient(backend.app)


def test_default_chaos_run_has_deterministic_id_and_evidence():
    first = client.get("/api/chaos").json()
    second = client.get("/api/chaos").json()
    assert first["experiment_id"].startswith("EXP-")
    assert first["experiment_id"] == second["experiment_id"]
    gender = first["tests"][0]
    assert gender["evidence_count"] == 169
    assert len(gender["evidence"]) == 10
    assert gender["evidence"][0]["candidate_id"].startswith("C-")
    assert gender["evidence"][0]["before_decision"] != gender["evidence"][0]["after_decision"]


def test_custom_thresholds_and_evidence_limit():
    response = client.post(
        "/api/chaos/run",
        json={
            "model": "legacy",
            "evidence_limit": 3,
            "thresholds": {"gender_swap": {"warn": 0.20, "fail": 0.30}},
        },
    )
    assert response.status_code == 200
    result = response.json()
    gender = next(test for test in result["tests"] if test["id"] == "gender_swap")
    assert gender["verdict"] == "PASS"
    assert len(gender["evidence"]) == 3
    assert result["experiment_id"] != client.get("/api/chaos").json()["experiment_id"]


def test_invalid_custom_threshold_order_returns_400():
    response = client.post(
        "/api/chaos/run",
        json={"thresholds": {"gender_swap": {"warn": 0.5, "fail": 0.1}}},
    )
    assert response.status_code == 400
    assert "warn must not exceed fail" in response.json()["detail"]


def test_model_comparison_reports_reviewed_deltas():
    response = client.get("/api/compare", params={"baseline": "legacy", "candidate": "fair"})
    assert response.status_code == 200
    result = response.json()
    assert result["delta"]["certificate"] == 44
    assert result["delta"]["chaos_resilience"] == 70
    assert result["candidate"]["certificate"]["grade"] == "B"


def test_unknown_comparison_model_returns_400():
    response = client.get("/api/compare", params={"candidate": "unknown"})
    assert response.status_code == 400


def test_release_gate_passes_improvement_and_blocks_regression():
    passed = client.post(
        "/api/gate", json={"baseline_model": "legacy", "candidate_model": "fair"}
    ).json()
    assert passed["status"] == "PASS"
    assert passed["passed"] is True
    assert all(check["passed"] for check in passed["checks"])

    blocked = client.post(
        "/api/gate", json={"baseline_model": "fair", "candidate_model": "legacy"}
    ).json()
    assert blocked["status"] == "BLOCK"
    assert blocked["passed"] is False
    assert any(not check["passed"] for check in blocked["checks"])


def test_reference_html_report_is_self_contained():
    response = client.get("/api/report.html", params={"model": "legacy"})
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        "attachment; filename=chaoshire-report.html"
    )
    assert "ChaosHire Audit Report" in response.text
    assert "42 / F" in response.text
    assert "EXP-" in response.text
    assert "<script" not in response.text
    assert "https://" not in response.text


def test_uploaded_report_requires_an_upload():
    response = client.get("/api/report.html", params={"dataset": "uploaded"})
    assert response.status_code == 404


def test_cli_gate_exit_codes(capsys):
    assert main(["gate", "--baseline", "legacy", "--candidate", "fair"]) == 0
    assert '"status": "PASS"' in capsys.readouterr().out
    assert main(["gate", "--baseline", "fair", "--candidate", "legacy"]) == 1
    assert '"status": "BLOCK"' in capsys.readouterr().out


def test_cli_writes_html_report(tmp_path, capsys):
    output = tmp_path / "report.html"
    assert main(["report", "--model", "legacy", "--output", str(output)]) == 0
    assert output.exists()
    assert "ChaosHire Audit Report" in output.read_text(encoding="utf-8")
    assert "Wrote" in capsys.readouterr().out


def test_report_renderer_escapes_audit_name():
    result = backend.audit(backend.build_decisions(backend.LEGACY))
    result["audit_name"] = "<script>alert(1)</script>"
    html = render_html_report(result)
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html
