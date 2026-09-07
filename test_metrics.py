"""Regression tests for ChaosHire's fairness calculations.

These tests intentionally lock in the curated demo seed. If model weights or
the synthetic population change, update expected values only after reviewing
and documenting the effect on the product story.
"""
import backend


def attribute(result: dict, name: str) -> dict:
    return next(item for item in result["attributes"] if item["attribute"] == name)


def test_legacy_reference_audit_is_reproducible():
    result = backend.audit(backend.build_decisions(backend.LEGACY))

    assert result["stats"]["candidates"] == 1000
    assert result["stats"]["accepted"] == 559
    assert result["certificate"]["total"] == 42
    assert result["certificate"]["grade"] == "F"
    assert attribute(result, "gender")["disparate_impact"] == 0.5491
    assert attribute(result, "ethnicity")["disparate_impact"] == 0.6557
    assert attribute(result, "age_band")["disparate_impact"] == 0.5412


def test_fair_reference_model_passes_disparate_impact_checks():
    result = backend.audit(backend.build_decisions(backend.FAIR))

    assert result["stats"]["candidates"] == 1000
    assert result["certificate"]["total"] == 86
    assert result["certificate"]["grade"] == "B"
    assert all(item["di_pass"] for item in result["attributes"])


def test_disparate_impact_uses_four_fifths_threshold():
    result = backend.audit(backend.build_decisions(backend.LEGACY))
    gender = attribute(result, "gender")

    rates = [group["selection_rate"] for group in gender["groups"] if not group["low_n"]]
    expected = round(min(rates) / max(rates), 4)
    assert gender["disparate_impact"] == expected
    assert gender["di_pass"] is False


def test_small_groups_are_flagged_and_excluded_from_worst_case():
    import pandas as pd

    data = pd.DataFrame({
        "gender": ["large"] * 40 + ["tiny"] * 5,
        "accepted": [1] * 32 + [0] * 8 + [0] * 5,
        "qualified": [True] * 45,
    })
    result = backend.attr_metrics(data, "gender")
    tiny = next(group for group in result["groups"] if group["group"] == "tiny")

    assert tiny["low_n"] is True
    assert result["disparate_impact"] == 1.0
    assert result["di_pass"] is True


def test_all_mitigations_improve_but_do_not_overstate_grade():
    # Mirrors the endpoint's three-strategy algorithm while checking that the
    # public result remains the reviewed 42/F -> 83/B demonstration.
    response = backend.api_mitigate(
        backend.MitigateReq(strategies=["blind", "proxy", "calibrate"])
    )
    assert response["before"]["total"] == 42
    assert response["before"]["grade"] == "F"
    assert response["after"]["certificate"]["total"] == 83
    assert response["after"]["certificate"]["grade"] == "B"
