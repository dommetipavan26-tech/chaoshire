"""The recruiter landing view is a public contract, not decoration."""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

import backend
from chaoshire import __version__

ROOT = Path(__file__).resolve().parent.parent
LANDING = (ROOT / "index.html").read_text(encoding="utf-8")
CLAIMS = json.loads((ROOT / "docs" / "VERIFIED-QUALITY.json").read_text(encoding="utf-8"))
client = TestClient(backend.app)

GITHUB = "https://github.com/dommetipavan26-tech/chaoshire"


def test_landing_is_the_first_view_and_the_app_waits_behind_it():
    assert LANDING.count('<div id="landing">') == 1
    assert '<div id="app" hidden>' in LANDING
    assert "Skip to main content" in LANDING
    assert 'href="#landing-main"' in LANDING and 'href="#main"' in LANDING


def test_landing_states_the_problem_and_offers_both_entry_points():
    assert "identity" in re.search(r"<h2>(.*?)</h2>", LANDING, re.S).group(1)
    assert 'id="cta-demo"' in LANDING and 'data-goto="demo"' in LANDING
    assert 'id="cta-dash"' in LANDING and 'data-goto="overview"' in LANDING
    assert "Start the guided demo" in LANDING
    assert "Explore dashboard" in LANDING
    for capability in ("Measure the group outcome gap", "Break the decision on purpose", "Gate the next release"):
        assert capability in LANDING


def test_landing_links_to_public_evidence():
    assert f'href="{GITHUB}"' in LANDING
    assert 'href="/docs"' in LANDING
    assert f'href="{GITHUB}/releases/latest"' in LANDING
    assert 'href="docs/METHODOLOGY.md"' in LANDING


def test_verified_statistics_match_the_claims_file_and_the_package():
    tests = re.search(r'data-verified-tests="(\d+)"', LANDING).group(1)
    coverage = re.search(r'data-verified-coverage="([\d.]+)"', LANDING).group(1)
    release = re.search(r'data-verified-release="([\d.]+)"', LANDING).group(1)
    assert int(tests) == CLAIMS["core_tests"]
    assert float(coverage) == CLAIMS["coverage_percent"]
    assert release == CLAIMS["version"] == __version__
    assert f"<b>{tests}</b>" in LANDING
    assert f"<b>{coverage}%</b>" in LANDING
    assert f"<b>v{release}</b>" in LANDING
    assert str(CLAIMS["demo"]["chaos_experiments"]) in LANDING


def test_landing_never_claims_legal_certification():
    assert "Certificate" not in LANDING
    assert "™" not in LANDING
    assert "Fairness Risk Score" in LANDING
    assert "not</b> a legal certification" in LANDING or "not a legal certification" in LANDING
    assert "does not by itself prove or disprove" in LANDING
    assert "Every person, employer and outcome here is synthetic" in LANDING


def test_public_api_field_names_stay_compatible():
    """The label changed; the JSON contract did not."""
    audited = client.get("/api/audit?model=legacy").json()
    assert audited["certificate"]["grade"] == CLAIMS["demo"]["legacy_grade"]
    assert audited["certificate"]["total"] == CLAIMS["demo"]["legacy_risk_score"]
    assert "certificate" in audited


def test_mobile_navigation_is_a_disclosure_with_touch_targets():
    assert 'id="navtoggle"' in LANDING
    assert 'aria-controls="tabs"' in LANDING
    assert 'aria-expanded="false"' in LANDING
    assert ".navbar nav.open" in LANDING
    assert "@media(max-width:600px)" in LANDING
    assert "min-height:46px" in LANDING or "min-height:44px" in LANDING


def test_landing_does_not_wait_on_the_free_tier_server():
    assert "/* No deep link: stay on the landing view and let the visitor choose. */" in LANDING
    assert "openApp" in LANDING and "bootOnce" in LANDING


def test_demo_call_to_action_targets_a_real_tab():
    tab_ids = set(re.findall(r"\['(\w+)','", LANDING))
    for target in re.findall(r'data-goto="(\w+)"', LANDING):
        assert target in tab_ids, f"{target} is not a navigation tab"


def test_home_page_serves_the_landing_markup():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == LANDING
