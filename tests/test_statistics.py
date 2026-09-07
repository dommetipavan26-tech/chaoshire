"""Statistical-rigor and intersectional-audit tests."""
import pandas as pd

import backend
from chaoshire.metrics import audit, two_proportion_test, wilson_interval


def test_wilson_interval_for_balanced_sample():
    interval = wilson_interval(50, 100)
    assert interval == {"low": 0.4038, "high": 0.5962, "level": 0.95}


def test_two_proportion_test_detects_large_difference():
    result = two_proportion_test(20, 100, 50, 100)
    assert result["p_value"] < 0.001
    assert result["z_score"] < 0


def test_zero_variance_proportions_are_handled_safely():
    assert two_proportion_test(0, 10, 0, 10) == {"z_score": 0.0, "p_value": 1.0}


def test_group_rows_include_selection_and_tpr_intervals():
    result = audit(backend.build_decisions(backend.LEGACY))
    female = next(
        group
        for group in next(item for item in result["attributes"] if item["attribute"] == "gender")["groups"]
        if group["group"] == "F"
    )
    assert female["selection_rate_ci"]["low"] < female["selection_rate"]
    assert female["selection_rate_ci"]["high"] > female["selection_rate"]
    assert female["tpr_ci"]["low"] < female["tpr"] < female["tpr_ci"]["high"]


def test_legacy_audit_reports_exploratory_significance():
    result = audit(backend.build_decisions(backend.LEGACY))
    gender = next(item for item in result["attributes"] if item["attribute"] == "gender")
    test = gender["statistical_test"]
    assert test["lowest_group"] == "NB"
    assert test["highest_group"] == "M"
    assert test["significant_at_0_05"] is True
    assert test["p_value"] < 0.001


def test_pairwise_intersections_do_not_change_certificate():
    data = backend.build_decisions(backend.LEGACY)
    result = audit(data)
    assert result["certificate"]["total"] == 42
    assert len(result["intersections"]) == 3
    assert {tuple(item["source_attributes"]) for item in result["intersections"]} == {
        ("gender", "ethnicity"),
        ("gender", "age_band"),
        ("ethnicity", "age_band"),
    }


def test_custom_intersection_uses_requested_attributes():
    data = pd.DataFrame(
        {
            "region": ["north"] * 30 + ["south"] * 30,
            "contract": (["full-time"] * 15 + ["part-time"] * 15) * 2,
            "accepted": [1] * 15 + [0] * 15 + [1] * 10 + [0] * 20,
        }
    )
    result = audit(data, attributes=["region", "contract"], minimum_group_size=10)
    assert len(result["intersections"]) == 1
    intersection = result["intersections"][0]
    assert intersection["attribute"] == "region × contract"
    assert len(intersection["groups"]) == 4
