"""Red-flag review: what the product says about itself must match what it is.

Four self-presentational claims are pinned here because each one shipped as an
overclaim at least once:

1. the Chaos Lab story blurbs read as marketing narrative ("Does the model get
   gamed? Who survives?") instead of describing the experiment;
2. the privilege-injection experiment's PASS badge hid that the fixture itself
   bounds what the test can falsify (docs/engineering/CONTINUOUS-FAIRNESS.md);
3. the deterministic rules engine was branded a "Fairness Review Agent";
4. the TalentFit blurb ended on a teaser question instead of the measured
   result.

A fifth finding, the unredacted `GET /api/appeals` queue, has its own module:
`tests/api/test_appeals_redaction.py`.
"""

from pathlib import Path

from conftest import operator_client

from chaoshire.agent import review_audit
from chaoshire.chaos import CHAOS_TESTS, run_chaos_suite
from chaoshire.demo import guided_demo
from chaoshire.metrics import audit
from chaoshire.models import LEGACY, MODEL_META, build_decisions

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_HTML = (PROJECT_ROOT / "chaoshire" / "web" / "index.html").read_text(encoding="utf-8")

client = operator_client()

BANNED_STORY_CLAIMS = (
    "Does the model get gamed",
    "Who survives",
    "must not change a single decision",
    "Detects hidden ageism",
    "Disproportionately impacts",
)


def test_chaos_stories_describe_the_method_not_a_narrative():
    for test in CHAOS_TESTS:
        assert test.story.strip(), test.id
        for banned in BANNED_STORY_CLAIMS:
            assert banned not in test.story, f"{test.id} story: {banned}"
        # Every story states the mechanical procedure: a transformation is
        # applied and the same rows are (re-)scored against a threshold.
        assert "scored" in test.story and "threshold" in test.story, test.id


def test_chaos_observation_details_do_not_claim_detection_or_disproportion():
    suite = run_chaos_suite("legacy", evidence_limit=0)
    for result in suite["tests"]:
        for banned in BANNED_STORY_CLAIMS:
            assert banned not in result["detail"], f"{result['id']} detail: {banned}"


def test_privilege_injection_pass_is_labelled_fixture_limited():
    # Asserted against the served payload — the label must reach the HTTP API,
    # not just the in-process result.
    suite = client.get("/api/chaos", params={"model": "legacy"}).json()
    injection = next(result for result in suite["tests"] if result["id"] == "adversarial")
    assert injection["verdict"] == "PASS"
    assert injection["fixture_limit"]
    assert "Fixture-limited" in injection["fixture_limit"]
    assert "résumé-gaming" in injection["fixture_limit"]
    # Every other experiment carries no scope note.
    for result in suite["tests"]:
        if result["id"] != "adversarial":
            assert result["fixture_limit"] == "", result["id"]
    # The label is rendered next to the verdict and as a visible scope note —
    # an unlabelled PASS is exactly what the review flagged.
    assert "fixture-limited" in INDEX_HTML
    assert "Scope note:" in INDEX_HTML
    assert "t.fixture_limit" in INDEX_HTML


def test_the_fixture_label_changes_no_verdict_and_no_resilience_score():
    suite = run_chaos_suite("legacy", evidence_limit=0)
    # Published demo constants — preserved (LegacyCorp resilience 30/100).
    assert suite["resilience"] == 30
    verdicts = {result["id"]: result["verdict"] for result in suite["tests"]}
    assert verdicts["adversarial"] == "PASS"
    scores = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}
    expected = round(100 * sum(scores[value] for value in verdicts.values()) / len(verdicts))
    assert suite["resilience"] == expected


def test_the_fairness_review_is_not_marketed_as_an_ai_agent():
    review = review_audit(audit(build_decisions(LEGACY)))
    assert review["agent"]["external_ai"] is False
    assert "agent" not in review["agent"]["name"].lower()
    assert "deterministic" in review["agent"]["name"].lower()
    limitations = " ".join(review["limitations"])
    assert "not an AI agent or language model" in limitations
    # The HTTP payload carries the same honest identity.
    served = client.post("/api/agent/review", json={"model": "legacy", "dataset": "demo"}).json()
    assert served["agent"] == review["agent"]
    assert "not an AI agent or language model" in served["limitations"][0]
    # Current-facing surfaces: no "Fairness Review Agent" branding survives.
    assert "Fairness Review Agent" not in INDEX_HTML
    assert "Review Agent" not in INDEX_HTML
    assert "Fairness Review" in INDEX_HTML
    assert "no AI agent or language model is involved" in INDEX_HTML
    assert "not an AI agent" in INDEX_HTML
    # The guided demo step no longer says "Ask the review agent".
    demo = guided_demo()
    step_four = next(step for step in demo["steps"] if step["id"] == 4)
    assert "agent" not in step_four["title"].lower()


def test_the_talentfit_blurb_reports_the_measured_outcome():
    blurb = MODEL_META["trained"]["blurb"]
    # Pinned fixture results (tests/core/test_trained_model.py): 66/C, DI 0.78, 100/100.
    assert "66/C" in blurb
    assert "0.78" in blurb
    assert "100/100" in blurb
    assert not blurb.rstrip().endswith("?"), "the blurb must state results, not tease them"
    served = {model["id"]: model for model in client.get("/api/meta").json()["models"]}
    assert served["trained"]["blurb"] == blurb


def test_published_demo_scores_are_preserved():
    """LegacyCorp stays 32/F and Chaos stays 30/100 — nothing was tuned to look better."""
    certificate = audit(build_decisions(LEGACY))["certificate"]
    assert (certificate["total"], certificate["grade"]) == (32, "F")
    suite = run_chaos_suite("legacy", evidence_limit=50)
    assert suite["resilience"] == 30
    flips = {result["id"]: result["evidence_count"] for result in suite["tests"]}
    assert flips["gender_swap"] == 169
    assert flips["ethnicity_swap"] == 111
