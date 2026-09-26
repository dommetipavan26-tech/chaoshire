"""Fix #5 — the fairness score is measured, and its denominator is disclosed.

Two problems with the old ``certificate()``:

* it added an unconditional ``TRANSPARENCY_POINTS = 15`` for disclosure, release
  gates, CI and appeal routes. None of that is a property of the model under
  audit and none of it was ever measured — it was 15 free points that pushed a
  perfect group-fairness result to 85/B and a genuinely bad one to 47/D instead
  of F;
* the denominator switched between 85 (ground truth available) and 60 (not) with
  nothing in the payload saying so, so two scores printed side by side were not
  measuring the same thing.

Now: ``total = measured / available * 100`` over a single scale, with the
arithmetic, the basis and the missing components stated explicitly, and the
platform-disclosure text carried as a string rather than as points.
"""

from typing import Any

import pytest

from chaoshire.metrics import (
    DI_POINTS,
    FULL_BASIS_POINTS,
    OPPORTUNITY_POINTS,
    PARITY_POINTS,
    PLATFORM_DISCLOSURE,
    SCORE_SCALE,
    SELECTION_ONLY_BASIS_POINTS,
    audit,
)
from chaoshire.models import build_decisions, get_model
from chaoshire.reporting import render_html_report
from chaoshire.services import mitigate

LEGACY = audit(build_decisions(get_model("legacy")))
FAIR = audit(build_decisions(get_model("fair")))
TRAINED = audit(build_decisions(get_model("trained")))


def cert(result: dict[str, Any]) -> dict[str, Any]:
    return result["certificate"]


def test_the_free_fifteen_points_are_gone():
    import chaoshire.metrics as metrics

    assert not hasattr(metrics, "TRANSPARENCY_POINTS")
    source = open(metrics.__file__, encoding="utf-8").read()
    assert "TRANSPARENCY_POINTS" not in source
    assert "+ 15" not in source


def test_the_scale_is_arithmetic_not_a_bonus():
    assert SCORE_SCALE == 100
    assert DI_POINTS + PARITY_POINTS + OPPORTUNITY_POINTS == FULL_BASIS_POINTS == 85
    assert DI_POINTS + PARITY_POINTS == SELECTION_ONLY_BASIS_POINTS == 60

    for result in (LEGACY, FAIR, TRAINED):
        c = cert(result)
        assert c["available_points"] == FULL_BASIS_POINTS
        assert c["scale"] == SCORE_SCALE
        assert c["basis"] == "full"
        assert c["comparable_with_full_basis"] is True
        # total is exactly measured/available*100, rounded and clamped.
        assert c["total"] == int(max(0, min(100, round(c["measured_points"] / 85 * 100))))
        assert sum(component["pts"] for component in c["components"]) == pytest.approx(
            c["measured_points"], abs=0.15
        )
        assert c["unmeasured_components"] == []


def test_a_perfect_group_fairness_result_scores_100_not_85():
    """The ceiling is now reachable on merit."""
    from chaoshire.metrics import certificate

    perfect = certificate(
        [
            {
                "attribute": "gender",
                "disparate_impact": 1.0,
                "parity_gap": 0.0,
                "eq_opp_gap": 0.0,
            }
        ]
    )
    assert perfect["measured_points"] == pytest.approx(85.0)
    assert perfect["total"] == 100
    assert perfect["grade"] == "A"


def test_canonical_model_scores_are_unchanged_by_the_rescale():
    assert (cert(LEGACY)["total"], cert(LEGACY)["grade"]) == (32, "F")
    assert (cert(FAIR)["total"], cert(FAIR)["grade"]) == (84, "B")
    # TalentFit was 66/C under this scale; the v3 upgrade (proxy-free inputs and a
    # cost-sensitive cutoff, tests/core/test_trained_model.py) moved it to 80/B.
    assert (cert(TRAINED)["total"], cert(TRAINED)["grade"]) == (80, "B")
    # ...but each is now 15 points lower than the inflated figure it replaced.
    assert cert(FAIR)["total"] < 99


def test_a_different_denominator_is_flagged_as_not_comparable():
    frame = build_decisions(get_model("legacy")).drop(columns=["qualified"])
    c = cert(audit(frame))
    assert c["basis"] == "selection-rate-only"
    assert c["available_points"] == SELECTION_ONLY_BASIS_POINTS
    assert c["comparable_with_full_basis"] is False
    assert [item["label"] for item in c["unmeasured_components"]] == ["Equal opportunity gap"]
    assert c["unmeasured_components"][0]["max"] == OPPORTUNITY_POINTS
    assert "must not be ranked against each other" in c["basis_note"]
    assert c["total"] == int(max(0, min(100, round(c["measured_points"] / 60 * 100))))


def test_an_unassessable_audit_does_not_invent_a_basis():
    from chaoshire.metrics import certificate

    c = certificate([], assessable=False, reasons=["No protected attribute supplied."])
    assert c["grade"] == "N/A"
    assert c["total"] == 0
    assert c["basis"] == "none"
    assert c["available_points"] == 0
    assert c["measured_points"] == 0.0
    assert c["comparable_with_full_basis"] is False
    assert c["reasons"] == ["No protected attribute supplied."]


def test_platform_disclosure_is_text_not_points():
    assert PLATFORM_DISCLOSURE["scored"] is False
    assert PLATFORM_DISCLOSURE["included_in_total"] is False
    assert "not the model under audit" in PLATFORM_DISCLOSURE["why_unscored"]
    assert len(PLATFORM_DISCLOSURE["capabilities"]) == 4
    for result in (LEGACY, FAIR, TRAINED):
        assert cert(result)["platform_disclosure"] == PLATFORM_DISCLOSURE


def test_mitigation_deltas_are_on_the_measured_scale():
    outcome = mitigate(["blind", "proxy"])
    before, after = cert(outcome["before"]), cert(outcome["after"])
    assert before["available_points"] == after["available_points"] == FULL_BASIS_POINTS
    assert after["total"] - before["total"] == 48
    assert before["total"] == 32 and after["total"] == 80


def test_the_html_report_states_the_basis():
    html = render_html_report(LEGACY)
    assert "Scoring basis:" in html
    assert "27.1 of 85 available points measured" in html
    assert "Platform disclosure (not scored, excluded from the total):" in html
    assert "Per-candidate contribution explanations (XAI)" in html
    assert "directly comparable" in html
    assert "32 / F" in html
    # The disclosure dict must never leak as a Python repr.
    assert "{'scored'" not in html
    assert '"scored"' not in html

    frame = build_decisions(get_model("legacy")).drop(columns=["qualified"])
    partial = render_html_report(audit(frame))
    assert "of 60 available points measured" in partial
    assert "Equal opportunity gap (25 points)" in partial
    assert "<b>not comparable</b>" in partial
    assert "no ground-truth qualification labels" in partial


def test_the_pdf_report_states_the_basis():
    from chaoshire.pdf_reporting import _report_lines, render_pdf_report

    lines = _report_lines(LEGACY, None)
    assert all(len(line) <= 92 for line in lines)  # nothing is silently truncated
    assert "Scoring basis: 27.1 of 85 available points measured (full)." in lines
    assert "Comparable with other full-basis scores." in lines
    assert "Transparency points are no longer added to the model score." in lines

    pdf = render_pdf_report(LEGACY)
    assert b"Scoring basis: 27.1 of 85 available points measured" in pdf
    assert b"Transparency points are no longer added" in pdf

    frame = build_decisions(get_model("legacy")).drop(columns=["qualified"])
    partial = _report_lines(audit(frame), None)
    assert "Scoring basis: 27.1 of 60 available points measured (selection-rate-only)." in partial
    assert any(line.startswith("Not comparable with a full-basis score") for line in partial)


def test_the_api_payload_carries_the_basis_through():
    from fastapi.testclient import TestClient

    from chaoshire.app import app

    with TestClient(app) as client:
        body = client.get("/api/audit", params={"model": "legacy", "dataset": "demo"}).json()
        c = body["certificate"]
        assert c["available_points"] == 85
        assert c["scale"] == 100
        assert c["basis"] == "full"
        assert c["comparable_with_full_basis"] is True
        assert "measured_points" in c
        assert c["platform_disclosure"] == PLATFORM_DISCLOSURE
