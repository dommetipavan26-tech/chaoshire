"""Intersectional gender × community swap: the sixth Chaos Lab experiment."""

from conftest import operator_client

from chaoshire.chaos import run_chaos_suite

client = operator_client()


def _test(suite: dict, test_id: str) -> dict:
    return next(item for item in suite["tests"] if item["id"] == test_id)


def test_intersectional_swap_flips_more_than_either_single_swap_for_legacy():
    suite = run_chaos_suite("legacy")
    result = _test(suite, "intersectional_swap")
    assert result["verdict"] == "FAIL"
    assert result["rate"] == 0.177
    assert result["evidence_count"] == 177
    # The combined swap exposes flips neither single-attribute swap observes
    # on its own count alone (169 gender, 111 community).
    assert result["evidence_count"] > _test(suite, "gender_swap")["evidence_count"]
    assert result["evidence_count"] > _test(suite, "ethnicity_swap")["evidence_count"]
    assert "Female + Community C" in result["detail"]
    assert suite["resilience"] == 25  # six-test mean: FAIL enters the average


def test_intersectional_swap_is_by_construction_for_models_without_those_inputs():
    for model in ("fair", "trained"):
        result = _test(run_chaos_suite(model), "intersectional_swap")
        assert result["verdict"] == "PASS"
        assert result["rate"] == 0.0
        assert "by construction" in result["by_construction"]


def test_intersectional_thresholds_are_configurable_through_the_api():
    response = client.post(
        "/api/chaos/run",
        json={
            "model": "legacy",
            "thresholds": {"intersectional_swap": {"warn": 0.20, "fail": 0.30}},
        },
    )
    assert response.status_code == 200
    result = _test(response.json(), "intersectional_swap")
    assert result["verdict"] == "PASS"  # 0.177 is under the raised warn bound
    assert result["threshold"] == {"warn": 0.20, "fail": 0.30}
