"""Chaos evidence, model comparison, release-gate, and report tests."""

from conftest import operator_client

import backend
from chaoshire.cli import main
from chaoshire.reporting import render_html_report

client = operator_client()


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
    assert result["delta"]["certificate"] == 52
    assert result["delta"]["chaos_resilience"] == 70
    assert result["candidate"]["certificate"]["grade"] == "B"


def test_unknown_comparison_model_returns_400():
    response = client.get("/api/compare", params={"candidate": "unknown"})
    assert response.status_code == 400


def test_release_gate_passes_improvement_blocks_regression_and_guards_utility():
    passed = client.post(
        "/api/gate", json={"baseline_model": "legacy", "candidate_model": "fair"}
    ).json()
    assert passed["status"] == "PASS"
    assert passed["passed"] is True
    assert all(check["passed"] for check in passed["checks"])

    trained = client.post(
        "/api/gate", json={"baseline_model": "legacy", "candidate_model": "trained"}
    ).json()
    accuracy = next(check for check in trained["checks"] if check["id"] == "minimum_accuracy")
    assert trained["status"] == "PASS"
    assert accuracy["actual"] == 0.831
    assert accuracy["passed"] is True
    holdout = trained["holdout"]
    assert holdout["evaluation_design"]["population_count"] == 100
    assert holdout["evaluation_design"]["holdout_disjoint_from_policy_selection"] is True
    assert set(holdout["evaluation_design"]["scenario_design"]["stress"]) == {
        "group_imbalance",
        "label_base_rate_shift",
        "label_noise",
        "proxy_correlation_shift",
        "merit_distribution_shift",
    }
    candidate_holdout = holdout["models"]["candidate"]
    assert candidate_holdout["metrics"]["accuracy"]["mean"] == 0.8129
    assert candidate_holdout["metrics"]["accuracy"]["p10"] == 0.782
    assert candidate_holdout["metrics"]["accuracy"]["mean_ci95"]["low"] < 0.8129
    assert candidate_holdout["metrics"]["recall"]["mean"] == 0.9621
    assert candidate_holdout["metrics"]["false_positive_rate"]["p90"] == 0.3383
    assert candidate_holdout["metrics"]["worst_disparate_impact"]["p10"] == 0.6497
    assert candidate_holdout["four_fifths_pass_rate"]["rate"] == 0.63
    assert len(holdout["threshold_sensitivity"]["thresholds"]) == 5

    accuracy_block = client.post(
        "/api/gate",
        json={
            "baseline_model": "legacy",
            "candidate_model": "trained",
            "minimum_accuracy": 0.84,
        },
    ).json()
    assert accuracy_block["status"] == "BLOCK"
    assert [check["id"] for check in accuracy_block["checks"] if not check["passed"]] == [
        "minimum_accuracy"
    ]

    fpr_block = client.post(
        "/api/gate",
        json={
            "baseline_model": "legacy",
            "candidate_model": "trained",
            "maximum_holdout_p90_false_positive_rate": 0.30,
        },
    ).json()
    assert fpr_block["status"] == "BLOCK"
    assert [check["id"] for check in fpr_block["checks"] if not check["passed"]] == [
        "maximum_holdout_p90_false_positive_rate"
    ]

    blocked = client.post(
        "/api/gate", json={"baseline_model": "fair", "candidate_model": "legacy"}
    ).json()
    assert blocked["status"] == "BLOCK"
    assert blocked["passed"] is False
    assert any(not check["passed"] for check in blocked["checks"])


def test_release_gate_rejects_holdout_limits_outside_probability_range():
    response = client.post(
        "/api/gate",
        json={
            "baseline_model": "legacy",
            "candidate_model": "trained",
            "maximum_holdout_p90_false_positive_rate": 1.01,
        },
    )
    assert response.status_code == 422


def test_reference_html_report_is_self_contained():
    response = client.get("/api/report.html", params={"model": "legacy"})
    assert response.status_code == 200
    assert response.headers["content-disposition"] == ("attachment; filename=chaoshire-report.html")
    assert "ChaosHire Audit Report" in response.text
    assert "32 / F" in response.text
    assert "EXP-" in response.text
    assert "<script" not in response.text
    assert "https://" not in response.text


def test_uploaded_report_requires_an_upload():
    response = client.get("/api/report.html", params={"dataset": "uploaded"})
    assert response.status_code == 404


def test_cli_gate_exit_codes(capsys):
    assert main(["gate", "--baseline", "legacy", "--candidate", "fair"]) == 0
    assert '"status": "PASS"' in capsys.readouterr().out
    assert (
        main(["gate", "--baseline", "legacy", "--candidate", "trained", "--min-accuracy", "0.84"])
        == 1
    )
    blocked = capsys.readouterr().out
    assert '"status": "BLOCK"' in blocked
    assert '"id": "minimum_accuracy"' in blocked
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
