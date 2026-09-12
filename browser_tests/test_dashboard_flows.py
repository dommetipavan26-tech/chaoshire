"""End-to-end coverage of the four dashboard journeys a reviewer would try."""
from __future__ import annotations

import json
import re

import pytest

pytestmark = pytest.mark.browser


def open_section(page, label: str):
    page.locator(f'#tabs button[data-t="{label}"]').click()


def test_model_switching_reaudits_without_a_page_reload(dashboard):
    assert dashboard.locator(".grade-ring b").inner_text() == "42"
    assert dashboard.locator(".grade-ring small").inner_text() == "Grade F"

    dashboard.locator('#modelsel button[data-m="fair"]').click()
    dashboard.wait_for_function("() => document.querySelector('.grade-ring b').textContent === '86'")
    assert dashboard.locator(".grade-ring small").inner_text() == "Grade B"
    assert dashboard.locator('#modelsel button[data-m="fair"].on').count() == 1
    assert "MeritFirst v2" in dashboard.locator("#modelsel").inner_text()


def test_chaos_lab_reports_five_deterministic_experiments(dashboard):
    open_section(dashboard, "chaos")
    assert "Chaos Engineering for Fairness" in dashboard.locator("#tab-chaos").inner_text()

    dashboard.locator("#runchaos").click()
    board = dashboard.locator("#chaosout")
    board.wait_for()
    assert "Chaos Resilience Score" in board.inner_text()
    assert "30/100" in board.inner_text()
    assert board.locator("article, .card").count() >= 5

    verdicts = " ".join(board.locator(".chip").all_inner_texts())
    for verdict in ("FAIL", "WARN", "PASS"):
        assert verdict in verdicts
    assert "LegacyCorp Screen v1" in dashboard.locator("#chaosout").inner_text()


def test_gender_swap_experiment_exposes_candidate_flips(dashboard):
    open_section(dashboard, "chaos")
    dashboard.locator("#runchaos").click()
    cards = dashboard.locator("#chaosout .card")
    gender_card = cards.filter(has_text="Gender").first
    gender_card.locator("summary").click()
    rows = gender_card.locator("table tr")
    assert rows.count() >= 2
    assert "Before" in rows.first.inner_text()


def test_filtered_view_names_the_qualified_candidates_who_were_lost(dashboard):
    open_section(dashboard, "filtered")
    summary = dashboard.locator("#tab-filtered")
    summary.wait_for()
    assert "Qualified but rejected" in summary.inner_text()
    assert summary.locator(".stat-num").nth(1).inner_text() == "42"
    assert "Rejection share by gender" in summary.inner_text()


def test_candidate_c1046_story_and_appeal_round_trip(dashboard):
    open_section(dashboard, "appeals")
    dashboard.locator("#cid").fill("C-1046")
    dashboard.locator("#lookup").click()

    card = dashboard.locator("#cout .card")
    card.wait_for()
    assert "Zara Lopez" in card.inner_text()
    assert "C-1046" in card.inner_text()
    assert "Rejected" in card.inner_text()
    assert card.locator(".chip.bad").count() >= 1

    card.get_by_role("button", name="Appeal this decision").click()
    assert dashboard.locator("#acid").input_value() == "C-1046"
    dashboard.locator("#amsg").fill("Skills test score omits my freelance work.")
    dashboard.locator("#sendappeal").click()

    filed = dashboard.locator("#aout .chip.ok")
    filed.wait_for()
    assert re.search(r"Appeal #\d+ filed", filed.inner_text())
    assert "Zara Lopez" in dashboard.locator("#queue").inner_text()


def test_mitigation_simulation_improves_the_risk_score(dashboard):
    open_section(dashboard, "mitigations")
    for box in dashboard.locator(".mit-check").all():
        box.check()
    dashboard.locator("#applymit").click()

    result = dashboard.locator("#mitout")
    result.wait_for()
    text = result.inner_text()
    assert "42 (F)" in text
    assert "83 (B)" in text
    assert "Fairness Risk Score" in text


def test_release_gate_can_block_and_release(dashboard):
    open_section(dashboard, "compare")
    gate = dashboard.locator("#tab-compare")
    gate.locator(".stat-num").first.wait_for()
    assert "BASELINE" in gate.inner_text()
    assert "42 / F" in gate.inner_text()
    assert "86 / B" in gate.inner_text()

    dashboard.locator("#gatecert").fill("99")
    dashboard.locator("#rungate").click()
    blocked = dashboard.locator("#gateout .chip")
    blocked.wait_for()
    assert blocked.first.inner_text().startswith("BLOCK")
    assert "release blocked" in blocked.first.inner_text()

    dashboard.locator("#gatecert").fill("75")
    dashboard.locator("#rungate").click()
    dashboard.wait_for_function(
        "() => document.querySelector('#gateout .chip').textContent.includes('release approved')"
    )
    assert "Risk score ≥ 75" in dashboard.locator("#gateout").inner_text()


def test_review_agent_returns_evidence_linked_findings(dashboard):
    open_section(dashboard, "agent")
    panel = dashboard.locator("#tab-agent")
    panel.wait_for()
    assert "BLOCK_AND_REVIEW" in panel.inner_text()
    assert "Prioritized findings" in panel.inner_text()
    assert panel.locator("article.card").count() >= 5
    assert "/certificate/total" in panel.inner_text()
    assert "Human action plan" in panel.inner_text()


def test_guided_demo_walkthrough_is_stable(dashboard):
    open_section(dashboard, "demo")
    panel = dashboard.locator("#tab-demo")
    panel.wait_for()
    assert panel.locator("article.card").count() == 6
    assert "From hidden hiring bias to a release decision" in panel.inner_text()
    assert "STEP 6" in panel.inner_text()


def test_report_and_evidence_downloads_are_served(dashboard):
    with dashboard.expect_download() as pdf_info:
        dashboard.locator('a[href*="/api/report.pdf"]').click()
    pdf = pdf_info.value
    assert pdf.suggested_filename == "chaoshire-report.pdf"
    body = pdf.path().read_bytes()
    assert body.startswith(b"%PDF-1.4")
    assert b"Fairness Risk Score" in body

    with dashboard.expect_download() as html_info:
        dashboard.locator('a[href*="/api/report.html"]').click()
    report = html_info.value
    assert report.suggested_filename == "chaoshire-report.html"
    exported = report.path().read_text(encoding="utf-8")
    assert "ChaosHire Audit Report" in exported
    assert "Fairness Risk Score" in exported

    with dashboard.expect_download() as evidence_info:
        dashboard.locator('a[href*="/api/evidence"]').click()
    bundle = json.loads(evidence_info.value.path().read_text(encoding="utf-8"))
    assert bundle["payload"]["schema"] == "chaoshire.evidence.v1"
    assert bundle["integrity"]["algorithm"] == "SHA-256"
    assert bundle["payload"]["audit"]["certificate"]["grade"] == "F"


def test_upload_tab_ships_a_sample_csv_for_byo_model_runs(dashboard):
    open_section(dashboard, "upload")
    with dashboard.expect_download() as sample_info:
        dashboard.locator('a[href="/api/sample.csv"]').click()
    header = sample_info.value.path().read_text(encoding="utf-8").splitlines()[0]
    assert "decision" in header and "gender" in header
    assert "Privacy" in dashboard.locator("#tab-upload").inner_text()
