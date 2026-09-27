"""The equal-opportunity gap must rest on enough *qualified* people, not rows.

``low_n`` bounds a group's size, but a true-positive rate's denominator is the
qualified people *inside* the group. The UCI Adult audit
(`docs/engineering/REAL-DATA-AUDIT.md`) exposed the gap: the
**Amer-Indian-Eskimo** cell has 149 rows — comfortably above the minimum group
size of 30 — but only **19** truly high-income people. Its true-positive rate
was therefore estimated from 19 observations (Wilson 95% interval 0.15-0.54 on
the naive model) and it dominated the race equal-opportunity gap for every model
audited. ChaosHire's own 1,000-candidate fixture has the same shape: 57
non-binary candidates of whom 17 are qualified.

These tests lock the fix: a group is excluded from the equal-opportunity gap
when it has fewer than ``minimum_group_size`` **qualified** people, the
exclusion is reported in the payload rather than silently applied, the
selection-rate metrics are untouched, and a score that loses the component says
*why* — with wording that distinguishes "no labels supplied" from "labels too
thin to use".
"""

from typing import Any

import pandas as pd

from chaoshire.metrics import attribute_metrics, audit, certificate
from chaoshire.models import build_decisions, get_model
from chaoshire.pdf_reporting import _report_lines
from chaoshire.reporting import render_html_report

#: The UCI Adult test split's race cells under the naive model: rows, qualified
#: rows, and qualified rows that were accepted. ``tpr`` = accepted/qualified, so
#: these reproduce the true-positive rates quoted in REAL-DATA-AUDIT.md exactly.
ADULT_LIKE_RACE = {
    "Amer-Indian-Eskimo": (149, 19, 6),  # 149 rows clears n>=30; 19 qualified does not
    "Other": (122, 24, 10),  # the second thin cell the old check also missed
    "Asian-Pac-Islander": (408, 121, 80),
    "Black": (1411, 168, 84),
    "White": (12970, 3368, 2042),
}

#: The race equal-opportunity gap before and after the qualified-count check.
ADULT_RACE_GAP_PRE_FIX = 0.3454
ADULT_RACE_GAP_POST_FIX = 0.1612


def frame(cells: dict[str, tuple[int, int, int]], attribute: str = "race") -> pd.DataFrame:
    """Build a decision frame from ``group -> (rows, qualified, qualified_accepted)``.

    Unqualified rows are never accepted, so the only variation is in the
    true-positive rates under test.
    """
    rows: list[dict[str, Any]] = []
    for group, (count, qualified, accepted) in cells.items():
        for index in range(count):
            is_qualified = index < qualified
            rows.append(
                {
                    attribute: group,
                    "qualified": is_qualified,
                    "accepted": bool(is_qualified and index < accepted),
                }
            )
    return pd.DataFrame(rows)


def adult_race_result(minimum_group_size: int = 30) -> dict[str, Any]:
    return attribute_metrics(frame(ADULT_LIKE_RACE), "race", minimum_group_size)


def group_of(result: dict[str, Any], name: str) -> dict[str, Any]:
    return next(group for group in result["groups"] if group["group"] == name)


def test_row_count_and_qualified_count_are_reported_and_checked_separately():
    """A group can clear one check and fail the other, so both are exposed."""
    result = adult_race_result()
    thin = group_of(result, "Amer-Indian-Eskimo")

    assert thin["n"] == 149
    assert thin["qualified_count"] == 19
    assert thin["low_n"] is False, "the group-size check still passes"
    assert thin["low_qualified_n"] is True, "the qualified-count check now fails"
    assert thin["tpr"] == 0.3158
    # The interval is what made the exclusion necessary: 19 observations cannot
    # pin a proportion down, and the width is reported rather than hidden.
    assert thin["tpr_ci"]["low"] == 0.1536
    assert thin["tpr_ci"]["high"] == 0.5399

    white = group_of(result, "White")
    assert (white["low_n"], white["low_qualified_n"]) == (False, False)
    assert white["qualified_count"] == 3368


def test_thin_qualified_groups_are_excluded_from_the_equal_opportunity_gap():
    """The headline number no longer rests on a 19-person estimate."""
    result = adult_race_result()

    assert result["eq_opp_gap"] == ADULT_RACE_GAP_POST_FIX
    assert result["eq_opp_groups"] == ["Asian-Pac-Islander", "Black", "White"]
    assert [item["group"] for item in result["eq_opp_excluded"]] == [
        "Amer-Indian-Eskimo",
        "Other",
    ]
    assert result["eq_opp_excluded"][0]["qualified_count"] == 19
    assert result["eq_opp_excluded"][0]["minimum_group_size"] == 30
    assert "too unreliable to compare" in result["eq_opp_excluded"][0]["reason"]
    assert result["eq_opp_note"] is not None
    assert "Amer-Indian-Eskimo (19 qualified)" in result["eq_opp_note"]
    assert "Other (24 qualified)" in result["eq_opp_note"]
    assert result["eq_pass"] is (ADULT_RACE_GAP_POST_FIX <= 0.1)

    # The documented pre-fix figure was the spread over all five groups, i.e. it
    # was set by the thinnest cell rather than by a real difference between them.
    rates = [group["tpr"] for group in result["groups"]]
    assert round(max(rates) - min(rates), 4) == ADULT_RACE_GAP_PRE_FIX


def test_the_qualified_count_rule_uses_the_configured_minimum():
    """The threshold is the configured one, and it is a strict comparison."""
    # 19 qualified < 20 <= 24 qualified: only the first cell drops out.
    at_twenty = adult_race_result(minimum_group_size=20)
    assert [item["group"] for item in at_twenty["eq_opp_excluded"]] == ["Amer-Indian-Eskimo"]
    assert at_twenty["eq_opp_groups"] == ["Asian-Pac-Islander", "Black", "Other", "White"]
    assert at_twenty["eq_opp_gap"] == round(0.6612 - 0.4167, 4)

    # At 19 the same cell is exactly at the threshold and is kept, so the gap is
    # the pre-fix spread over all five groups again.
    at_nineteen = adult_race_result(minimum_group_size=19)
    assert at_nineteen["eq_opp_excluded"] == []
    assert at_nineteen["eq_opp_note"] is None
    assert at_nineteen["eq_opp_groups"] == [
        "Amer-Indian-Eskimo",
        "Asian-Pac-Islander",
        "Black",
        "Other",
        "White",
    ]
    assert at_nineteen["eq_opp_gap"] == ADULT_RACE_GAP_PRE_FIX


def test_selection_rate_metrics_are_untouched_by_the_qualified_count_check():
    """Excluding a cell from the TPR comparison must not change DI or parity."""
    data = frame(ADULT_LIKE_RACE)
    strict = attribute_metrics(data, "race", 30)
    lenient = attribute_metrics(data, "race", 20)

    assert strict["disparate_impact"] == lenient["disparate_impact"]
    assert strict["parity_gap"] == lenient["parity_gap"]
    assert strict["statistical_test"] == lenient["statistical_test"]
    assert [group["low_n"] for group in strict["groups"]] == [
        group["low_n"] for group in lenient["groups"]
    ]
    # The two runs differ only in the equal-opportunity view.
    assert strict["eq_opp_gap"] != lenient["eq_opp_gap"]


def test_the_gap_is_none_when_no_two_groups_have_enough_qualified_people():
    """Nothing is invented: an unmeasurable gap is reported as unmeasured."""
    data = frame({"small-a": (60, 12, 6), "small-b": (80, 20, 4)})
    result = attribute_metrics(data, "race")

    assert result["eq_opp_gap"] is None
    assert result["eq_pass"] is None
    assert result["eq_opp_groups"] == []
    assert result["eq_opp_note"] is not None
    assert "No equal-opportunity gap" in result["eq_opp_note"]
    assert "fewer than two groups" in result["eq_opp_note"]
    # Every group still reports its own rate, with the reason visible.
    assert all(group["low_qualified_n"] for group in result["groups"])


def test_the_certificate_says_which_kind_of_missing_evidence_it_is():
    """No labels and unusable labels must not read alike in the payload."""
    data = frame({"small-a": (60, 12, 6), "small-b": (80, 20, 4)})
    thin = certificate(audit(data, attributes=["race"])["attributes"])
    missing = certificate(
        audit(data.drop(columns=["qualified"]), attributes=["race"])["attributes"]
    )

    for c in (thin, missing):
        assert c["basis"] == "selection-rate-only"
        assert c["available_points"] == 60
        assert c["comparable_with_full_basis"] is False
        assert [item["label"] for item in c["unmeasured_components"]] == ["Equal opportunity gap"]
        assert "must not be ranked against each other" in c["basis_note"]

    assert "no group has enough qualified people" in thin["basis_note"]
    assert "no ground-truth qualification labels" in missing["basis_note"]
    assert "no group has enough qualified people" not in missing["basis_note"]
    assert "no ground-truth qualification labels" not in thin["basis_note"]

    thin_reason = thin["unmeasured_components"][0]["reason"]
    missing_reason = missing["unmeasured_components"][0]["reason"]
    assert thin_reason != missing_reason
    assert "labels exist" in thin_reason
    assert "No ground-truth qualification column" in missing_reason


def test_the_platform_fixture_non_binary_group_is_flagged():
    """ChaosHire's own demo fixture has the same shape as the Adult race cell."""
    result = audit(build_decisions(get_model("legacy")))
    gender = next(item for item in result["attributes"] if item["attribute"] == "gender")
    non_binary = group_of(gender, "NB")

    assert non_binary["n"] == 57
    assert non_binary["qualified_count"] == 17
    assert non_binary["low_n"] is False
    assert non_binary["low_qualified_n"] is True
    assert gender["eq_opp_groups"] == ["F", "M"]
    assert gender["eq_opp_gap"] == 0.1273  # was 0.1959 while NB's 17 qualified counted
    # The score is unchanged because the age-band gap dominates on this fixture.
    assert (result["certificate"]["total"], result["certificate"]["grade"]) == (32, "F")
    assert result["certificate"]["basis"] == "full"


def test_intersectional_audits_apply_the_same_rule():
    """Crossed cells are audited by the same code, so the same check applies."""
    rows: list[dict[str, Any]] = []
    for index in range(200):
        # One crossed cell is large enough but holds only five qualified people.
        thin = index < 40
        rows.append(
            {
                "gender": "F" if index % 2 else "M",
                "age_band": "40+" if thin else "Under 40",
                "qualified": (index < 5) if thin else index % 3 == 0,
                "accepted": index % 4 == 0,
            }
        )
    data = pd.DataFrame(rows)
    cross = attribute_metrics(data, "age_band", 30)

    assert group_of(cross, "40+")["qualified_count"] == 5
    assert group_of(cross, "40+")["low_qualified_n"] is True
    assert cross["eq_opp_groups"] == ["Under 40"]
    assert cross["eq_opp_gap"] is None
    assert "No equal-opportunity gap" in cross["eq_opp_note"]


def test_the_html_report_shows_the_qualified_column_and_the_exclusion():
    result = audit(frame(ADULT_LIKE_RACE), attributes=["race"])
    html = render_html_report(result)

    assert "<th>Qualified</th>" in html
    assert "Equal-opportunity reliability:" in html
    assert "Amer-Indian-Eskimo" in html
    assert "Only 19 qualified people" in html
    assert "excluded from the equal-opportunity gap" in html
    # The excluded rate is still printed, flagged, never silently dropped.
    assert "31.6% ⚠" in html


def test_the_pdf_report_prints_the_note_instead_of_a_bare_none():
    measurable = audit(frame(ADULT_LIKE_RACE), attributes=["race"])
    lines = _report_lines(measurable, None)
    assert "equal opportunity 0.1612" in " ".join(lines)
    assert any("Equal-opportunity gap excludes" in line for line in lines)

    unmeasurable = audit(
        frame({"small-a": (60, 12, 6), "small-b": (80, 20, 4)}), attributes=["race"]
    )
    text = " ".join(_report_lines(unmeasurable, None))
    assert "equal opportunity n/a" in text
    assert "None" not in text.split("Primary attributes")[1]


def test_the_dashboard_marks_thin_true_positive_rates():
    """The exclusion is visible in the product, not only in the JSON."""
    from pathlib import Path

    html = (Path(__file__).resolve().parents[2] / "chaoshire" / "web" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "g.low_qualified_n" in html
    assert "g.qualified_count" in html
    assert "excluded from ΔEqOpp" in html
    assert "at.eq_opp_note" in html
    # The tooltip text goes through esc(), like every other attribute value.
    assert 'title="${esc(' in html


def test_the_real_data_audit_documents_the_qualified_count_rule():
    """The page that motivated the fix must describe the fix, not the old gap."""
    from pathlib import Path

    document = (
        Path(__file__).resolve().parents[2] / "docs" / "engineering" / "REAL-DATA-AUDIT.md"
    ).read_text(encoding="utf-8")

    assert "19 qualified" in document and "24 qualified" in document
    for gap in ("0.161", "0.089", "0.074"):
        assert gap in document, f"post-fix race gap {gap} is not documented"
    assert "qualified count" in document.lower()
    assert "isn't\nflagged as unreliable" not in document
