"""Fix #3 — per-group threshold calibration is a research contrast, not a fix.

``mitigate(["calibrate"])`` used to set per-group decision cutoffs on gender,
ethnicity and age and report the result as an *applied mitigation*, with a soft
doc caveat that it "may create legal or operational concerns and requires expert
review". In the jurisdiction the project's four-fifths rule comes from, it is not
a concern — it is prohibited:

    42 U.S.C. § 2000e-2(l) (Civil Rights Act of 1991):
    "... it shall be an unlawful employment practice ... to adjust the scores of,
    use different cutoff scores for, or otherwise alter the results of,
    employment related tests on the basis of race, color, religion, sex, or
    national origin."

So: removed from the one-click mitigation set, refused unless explicitly
acknowledged, cited in every response that mentions it, and reported under its
own key so it can never be mistaken for the mitigation result.
"""

from typing import get_args

import pytest
from conftest import operator_client
from pydantic import ValidationError

import backend
from chaoshire.schemas import MitigationRequest, MitigationStrategy
from chaoshire.services import (
    MITIGATION_STRATEGIES,
    THRESHOLD_CONTRAST_NOTICE,
    THRESHOLD_CONTRAST_STATUTE,
    mitigate,
    threshold_contrast_disclosure,
)

client = operator_client()


def test_calibration_is_not_an_available_mitigation():
    assert "calibrate" not in MITIGATION_STRATEGIES
    assert MITIGATION_STRATEGIES == ("blind", "proxy")
    assert set(get_args(MitigationStrategy)) == set(MITIGATION_STRATEGIES)


def test_requesting_calibration_is_refused_with_the_statute():
    result = mitigate(["calibrate"])
    assert "error" in result
    assert THRESHOLD_CONTRAST_STATUTE in result["error"]
    assert "unlawful" in result["error"]
    assert result["available_strategies"] == ["blind", "proxy"]
    disclosure = result["threshold_contrast"]
    assert disclosure["research_only"] is True
    assert disclosure["is_mitigation"] is False
    assert disclosure["prohibited_in_us_employment_testing"] is True
    assert disclosure["statute"] == "42 U.S.C. § 2000e-2(l)"
    assert "different cutoff scores" in disclosure["statutory_text"]
    assert disclosure["statute_url"].startswith("https://")


def test_the_endpoint_returns_422_not_a_silent_success():
    response = client.post("/api/mitigate", json={"strategies": ["calibrate"]})
    assert response.status_code == 422
    body = response.json()
    # pydantic rejects it at the schema level: 'calibrate' is not in the Literal.
    assert body["detail"][0]["type"] == "literal_error"


def test_the_contrast_needs_an_explicit_acknowledgement():
    refused = mitigate(["proxy"], threshold_contrast_acknowledged=False)
    assert refused["error"] == THRESHOLD_CONTRAST_NOTICE
    assert "never be applied to a real hiring process" in refused["error"]
    assert "not legal advice" in refused["error"]
    assert "threshold_contrast_acknowledged=true" in refused["how_to_run_as_research"]
    assert "research_contrast" not in refused


def test_the_acknowledged_contrast_is_reported_separately_and_never_merged():
    result = mitigate(["proxy"], threshold_contrast_acknowledged=True)
    assert "research_contrast" in result
    contrast = result["research_contrast"]
    assert contrast["research_only"] is True
    assert contrast["statute"] == THRESHOLD_CONTRAST_STATUTE
    assert contrast["notice"] == THRESHOLD_CONTRAST_NOTICE

    # The mitigation result itself contains no per-group cutoffs.
    assert result["after"]["certificate"]["total"] < contrast["after"]["certificate"]["total"]
    # "applied" lists only lawful controls, so nothing in the top-level payload
    # suggests calibration was used.
    assert not any("threshold" in item.lower() for item in result["applied"])
    assert "cutoff" in contrast["applied"]

    # Every mitigation response names the excluded control, acknowledged or not.
    excluded = result["excluded_controls"]["threshold_calibration"]
    assert excluded["prohibited_in_us_employment_testing"] is True
    plain = mitigate(["blind", "proxy"])
    assert "research_contrast" not in plain
    assert plain["excluded_controls"]["threshold_calibration"]["statute"] == (
        THRESHOLD_CONTRAST_STATUTE
    )


def test_contrast_alone_is_a_valid_request_but_a_mitigation_is_not_implied():
    result = mitigate([], threshold_contrast_acknowledged=True)
    assert "research_contrast" in result
    assert result["applied"] == []
    assert result["before"]["certificate"]["total"] == result["after"]["certificate"]["total"]


def test_schema_requires_at_least_one_thing_to_do():
    # An empty request that also skips the contrast asks the server to do nothing.
    with pytest.raises(ValidationError):
        MitigationRequest(strategies=[])
    assert MitigationRequest(strategies=["blind"]).threshold_contrast_acknowledged is None
    # The contrast on its own is a legitimate request.
    assert MitigationRequest(threshold_contrast_acknowledged=True).strategies == []
    # 'calibrate' is gone from the catalogue, so it fails schema validation.
    with pytest.raises(ValidationError):
        MitigationRequest(strategies=["calibrate"])
    with pytest.raises(ValidationError):
        MitigationRequest(strategies=["blind", "proxy", "blind"])


def test_every_disclosure_carries_the_citation():
    disclosure = threshold_contrast_disclosure()
    for key in ("statute", "statute_name", "statute_url", "statutory_text", "notice"):
        assert disclosure[key]
    assert "2000e-2(l)" in disclosure["statute"]
    assert "Civil Rights Act of 1991" in disclosure["statute_name"]
    assert disclosure["not_legal_advice"] is True


def test_the_guided_demo_leads_with_the_refusal():
    steps = client.get("/api/demo").json()["steps"]
    refusal = next(step for step in steps if "2000e-2(l)" in step["title"])
    assert THRESHOLD_CONTRAST_STATUTE in refusal["title"]
    assert "unlawful employment practice" in refusal["message"]
    assert refusal["evidence"]["statute_url"].startswith("https://")
    # The refusal is not buried at the end of the walkthrough.
    assert refusal["id"] <= len(steps) - 2


def test_backend_shim_still_exposes_the_mitigation_entrypoint():
    result = backend.api_mitigate(backend.MitigateReq(strategies=["blind"]))
    assert result["after"]["certificate"]["total"] > result["before"]["certificate"]["total"]
