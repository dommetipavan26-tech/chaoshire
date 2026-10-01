"""All metric entry points share a strict, non-truthiness decision contract."""

import numpy as np
import pandas as pd
import pytest

from chaoshire.adapters import CallableDecisionAdapter, normalise_remote_decisions
from chaoshire.decisions import boolean_label, normalise_decisions
from chaoshire.metrics import attribute_metrics, audit, intersectional_metrics


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        (np.bool_(False), False),
        (1, True),
        (0, False),
        (1.0, True),
        (0.0, False),
        (" yes ", True),
        ("FALSE", False),
        ("0", False),
        ("rejected", False),
        ("accepted", True),
    ],
)
def test_explicit_binary_labels_are_supported(value, expected):
    assert boolean_label(value, "qualified") is expected


@pytest.mark.parametrize(
    "value",
    [None, pd.NA, float("nan"), float("inf"), float("-inf"), 2, -1, 0.5, "unknown", "", [], {}],
)
def test_missing_unknown_nonfinite_and_nonbinary_labels_are_rejected(value):
    with pytest.raises(ValueError, match="explicit boolean"):
        boolean_label(value, "qualified")


def test_remote_false_string_does_not_become_a_qualified_person():
    rows = [{"accepted": "yes", "qualified": "false", "gender": "F"}] * 30
    rows += [{"accepted": "no", "qualified": "true", "gender": "M"}] * 30
    result = audit(normalise_remote_decisions(rows, "vendor"))
    gender = result["attributes"][0]
    assert gender["groups"][0]["qualified_count"] == 0
    assert gender["groups"][1]["qualified_count"] == 30
    assert result["stats"]["qualified_share"] == 0.5


def test_callable_and_direct_metrics_normalise_without_mutating_the_provider():
    frame = pd.DataFrame(
        {"accepted": ["true", "false"], "qualified": ["false", "true"], "gender": ["F", "M"]}
    )
    before = frame.copy(deep=True)
    normal = CallableDecisionAdapter("m", lambda: frame).decisions()
    assert normal["qualified"].tolist() == [False, True]
    assert audit(frame)["stats"]["qualified_share"] == 0.5
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("entry", ["audit", "attribute", "intersection"])
def test_bad_labels_cannot_bypass_validation_through_a_lower_level_metric(entry):
    frame = pd.DataFrame(
        {
            "accepted": [1, 0],
            "qualified": ["invalid", "false"],
            "gender": ["F", "M"],
            "region": ["a", "b"],
        }
    )
    with pytest.raises(ValueError):
        if entry == "audit":
            audit(frame)
        elif entry == "attribute":
            attribute_metrics(frame, "gender")
        else:
            intersectional_metrics(frame, ["gender", "region"])


@pytest.mark.parametrize("score", [float("nan"), float("inf"), None, "0.4", True])
def test_scores_must_be_finite_numeric_values(score):
    frame = pd.DataFrame({"accepted": [True], "gender": ["F"], "score": [score]})
    with pytest.raises(ValueError, match="finite numeric"):
        normalise_decisions(frame)


def test_missing_group_values_remain_a_visible_category():
    frame = pd.DataFrame({"accepted": [1, 0, 1], "gender": [None, " M ", np.nan]})
    assert normalise_decisions(frame)["gender"].tolist() == ["(missing)", "M", "(missing)"]


@pytest.mark.parametrize(
    "attributes", [["missing"], ["gender", "gender"], ["accepted"], ["qualified"], ["score"]]
)
def test_requested_groups_are_validated(attributes):
    frame = pd.DataFrame({"accepted": [True], "gender": ["F"]})
    with pytest.raises(ValueError):
        normalise_decisions(frame, attributes)


def test_no_groups_is_explicitly_not_assessable_or_refused_when_required():
    frame = pd.DataFrame({"accepted": [True, False]})
    assert audit(frame)["certificate"]["assessable"] is False
    with pytest.raises(ValueError, match="protected attribute"):
        normalise_decisions(frame, require_groups=True)


def test_empty_frames_remain_honestly_not_assessable():
    frame = pd.DataFrame(columns=["accepted", "gender"])
    result = audit(frame)
    assert result["stats"]["candidates"] == 0
    assert result["certificate"]["assessable"] is False


def test_invalid_frame_shape_fails_without_echoing_rows():
    with pytest.raises(ValueError, match="DataFrame"):
        normalise_decisions([{"accepted": True}])
    with pytest.raises(ValueError, match="unique"):
        normalise_decisions(pd.DataFrame([[1, 0]], columns=["accepted", "accepted"]))
    with pytest.raises(ValueError, match="scalar"):
        normalise_decisions(pd.DataFrame({"accepted": [1], "gender": [{"private": "payload"}]}))
    with pytest.raises(ValueError, match="UTF-8"):
        normalise_decisions(pd.DataFrame({"accepted": [1], "gender": ["\ud800"]}))
    with pytest.raises(ValueError, match="infinite"):
        normalise_decisions(pd.DataFrame({"accepted": [1], "gender": [float("inf")]}))
