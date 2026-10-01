"""Limiter identities expire globally and flooding cannot reset an active budget."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import operator_client
from fastapi.testclient import TestClient

from chaoshire.app import app
from chaoshire.platform import SlidingWindowLimiter


def test_inactive_identities_expire_without_returning_or_restarting():
    now = [0.0]
    limiter = SlidingWindowLimiter(max_keys=2, clock=lambda: now[0])
    assert limiter.allow("one", 2)
    now[0] = 1
    assert limiter.allow("two", 2)
    now[0] = 61
    assert limiter.allow("fresh", 2)
    assert limiter.snapshot()["active_keys"] == 1
    assert set(limiter._events) == {"fresh"}


def test_capacity_fails_closed_instead_of_evicting_live_keys():
    now = [0.0]
    limiter = SlidingWindowLimiter(max_keys=2, clock=lambda: now[0])
    assert limiter.allow("victim", 1)
    assert limiter.allow("attacker-0", 1)
    for i in range(100):
        assert not limiter.allow(f"attacker-{i + 1}", 1)
    assert not limiter.allow("victim", 1)
    assert limiter.snapshot()["active_keys"] == limiter.max_keys
    assert limiter.snapshot()["capacity_denied"] == 100
    assert limiter.retry_after("unseen") == 60
    now[0] = 60
    assert limiter.allow("new", 1)
    assert limiter.snapshot()["active_keys"] == 1


def test_expired_entries_are_freed_at_capacity_between_periodic_sweeps():
    now = [0.0]
    limiter = SlidingWindowLimiter(max_keys=1, clock=lambda: now[0])
    assert limiter.allow("short", 1, window_seconds=1)
    now[0] = 0.9
    assert not limiter.allow("other", 1)
    now[0] = 1.01
    assert limiter.allow("other", 1)


def test_retry_after_rounds_up_so_clients_do_not_retry_before_expiration():
    now = [0.0]
    limiter = SlidingWindowLimiter(clock=lambda: now[0])
    assert limiter.allow("client", 1)
    now[0] = 0.2
    assert limiter.retry_after("client") == 60
    now[0] = 59.2
    assert limiter.retry_after("client") == 1
    assert not limiter.allow("client", 1)
    now[0] = 60
    assert limiter.allow("client", 1)


def test_different_window_lengths_do_not_expire_a_key_early():
    now = [0.0]
    limiter = SlidingWindowLimiter(clock=lambda: now[0])
    assert limiter.allow("one", 10, window_seconds=120)
    now[0] = 1
    assert limiter.allow("one", 10, window_seconds=60)
    now[0] = 62
    assert limiter.snapshot()["active_keys"] == 1
    now[0] = 120
    assert limiter.snapshot()["active_keys"] == 0


def test_concurrent_admission_obeys_both_bucket_and_identity_bounds():
    limiter = SlidingWindowLimiter(max_keys=4)
    with ThreadPoolExecutor(max_workers=16) as pool:
        allowed = list(pool.map(lambda _: limiter.allow("same", 5), range(100)))
        assert sum(allowed) == 5
        identities = list(pool.map(lambda i: limiter.allow(f"client-{i}", 5), range(100)))
        assert sum(identities) == 3
    assert limiter.snapshot()["active_keys"] == 4


def test_disabled_budgets_allocate_no_keys_and_reset_clears_telemetry():
    limiter = SlidingWindowLimiter(max_keys=1)
    for i in range(100):
        assert limiter.allow(str(i), 0)
    assert limiter.snapshot()["active_keys"] == 0
    limiter.allow("first", 1)
    limiter.allow("second", 1)
    limiter.reset()
    assert limiter.snapshot() == {
        "active_keys": 0,
        "max_keys": 1,
        "denied": 0,
        "capacity_denied": 0,
    }
    assert limiter.retry_after("unknown") == 60


@pytest.mark.parametrize("argument", ["capacity", "window"])
def test_nonpositive_configuration_fails(argument):
    with pytest.raises(ValueError):
        if argument == "capacity":
            SlidingWindowLimiter(max_keys=0)
        else:
            SlidingWindowLimiter().allow("one", 1, window_seconds=0)


def test_operator_metrics_expose_bounds_without_client_identifiers():
    anonymous = TestClient(app).get("/api/ops/metrics")
    assert anonymous.status_code == 401
    result = operator_client().get("/api/ops/metrics")
    assert result.status_code == 200
    data = result.json()["rate_limiter"]
    assert data["max_keys"] == 4096
    assert set(data) == {"active_keys", "max_keys", "denied", "capacity_denied"}
