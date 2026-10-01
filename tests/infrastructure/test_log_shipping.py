"""Real delivery paths and deterministic load tests for the bounded webhook pool."""

from __future__ import annotations

import json
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

import chaoshire.loghook as loghook
from chaoshire.app import app
from chaoshire.loghook import (
    SHIPPED_EVENTS,
    Delivery,
    WebhookDispatcher,
    _build_payload,
    _sign,
    drain_all_sync,
    log_shipping_status,
    queue_depth,
    ship,
    shutdown_log_shipping,
    webhook_enabled,
    webhook_secret,
    webhook_url,
)


@pytest.fixture(autouse=True)
def isolated_dispatcher(monkeypatch):
    monkeypatch.delenv("CHAOSHIRE_LOG_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("CHAOSHIRE_LOG_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(loghook, "_DISPATCHER", None)
    yield
    if loghook._DISPATCHER is not None:
        assert loghook._DISPATCHER.close(timeout=3, drain=False)


@pytest.fixture
def transport(monkeypatch):
    received = []
    native = httpx.Client

    def install(status=200, error=None):
        def handle(request):
            received.append(request)
            if error is not None:
                raise error
            return httpx.Response(status, json={"ignored": "body"})

        mock = httpx.MockTransport(handle)
        monkeypatch.setattr(
            loghook.httpx, "Client", lambda **kwargs: native(transport=mock, **kwargs)
        )
        return received

    return install


def test_webhook_not_configured_by_default():
    assert webhook_url() is None
    assert not webhook_enabled()
    assert webhook_secret() is None


def test_ship_is_silent_when_unconfigured():
    ship("audit.completed", {"model": "legacy"})
    assert queue_depth() == 0
    assert loghook._DISPATCHER is None
    assert shutdown_log_shipping()
    assert drain_all_sync() == []


def test_build_payload_shape():
    payload = _build_payload("audit.completed", {"model": "legacy"})
    assert payload["event"] == "audit.completed"
    assert payload["service"] == "chaoshire"
    assert payload["data"] == {"model": "legacy"}
    assert "timestamp" in payload


def test_sign_produces_hex_digest():
    sig = _sign(b'{"event":"test"}', "test-secret")
    assert len(sig) == 64
    assert all(c in "0123456789abcdef" for c in sig)


def test_shipped_events_catalogue():
    assert set(SHIPPED_EVENTS) == {
        "audit.completed",
        "appeal.created",
        "chaos.completed",
        "mitigation.completed",
        "upload.completed",
    }


def test_log_shipping_status_when_unconfigured():
    status = log_shipping_status()
    assert status["configured"] is False
    assert status["signed"] is False
    assert status["queue_depth"] == status["in_flight"] == status["active_workers"] == 0
    assert status["worker_limit"] == 4 and status["max_outstanding"] == 256
    assert status["events_shipped"] == list(SHIPPED_EVENTS)


def test_meta_reports_log_shipping_status():
    with TestClient(app) as client:
        meta = client.get("/api/meta").json()
    assert meta["log_shipping"]["configured"] is False
    assert meta["log_shipping"]["outstanding"] == 0


def test_ship_delivers_to_webhook(monkeypatch, transport):
    received = transport()
    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_URL", "https://logs.example/ingest")
    ship("audit.completed", {"model": "legacy", "certificate_grade": "F"})
    assert loghook._DISPATCHER.flush(timeout=3)
    assert len(received) == 1
    assert json.loads(received[0].content)["data"]["model"] == "legacy"
    assert log_shipping_status()["delivered"] == 1


def test_secret_is_captured_at_enqueue_and_signs_exact_bytes(transport):
    received = transport()
    release = threading.Event()

    def deliver(job):
        assert release.wait(3)
        return loghook._deliver(job)

    dispatcher = WebhookDispatcher(workers=1, capacity=2, deliver=deliver)
    try:
        assert dispatcher.submit(
            "https://logs.example/ingest", "audit.completed", {"model": "é"}, "first-secret"
        )
        release.set()
        assert dispatcher.flush(3)
        request = received[0]
        assert request.headers["X-ChaosHire-Signature"] == _sign(request.content, "first-secret")
        assert json.loads(request.content)["data"]["model"] == "é"
    finally:
        release.set()
        assert dispatcher.close()


@pytest.mark.parametrize("status", [301, 401, 500])
def test_http_refusals_are_counted_without_retry_or_redirect(
    status, monkeypatch, transport, caplog
):
    received = transport(status=status)
    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_URL", "https://logs.example/ingest")
    ship("audit.completed", {"model": "legacy"})
    assert loghook._DISPATCHER.flush(3)
    assert log_shipping_status()["failed"] == 1
    assert len(received) == 1
    assert str(status) in caplog.text


def test_delivery_exception_never_logs_credential_bearing_text(monkeypatch, transport, caplog):
    transport(error=RuntimeError("https://secret:user-password@private.example/?token=hidden"))
    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_URL", "https://logs.example/ingest")
    ship("audit.completed", {"model": "legacy"})
    assert loghook._DISPATCHER.flush(3)
    assert log_shipping_status()["failed"] == 1
    assert "RuntimeError" in caplog.text
    assert "user-password" not in caplog.text and "hidden" not in caplog.text


def test_pending_and_in_flight_share_capacity_and_worker_count_is_fixed():
    release = threading.Event()
    started = threading.Event()
    lock = threading.Lock()
    active = maximum = count = 0

    def stalled(job):
        nonlocal active, maximum, count
        with lock:
            active += 1
            count += 1
            maximum = max(maximum, active)
            if active == 2:
                started.set()
        assert release.wait(4)
        with lock:
            active -= 1
        return True

    dispatcher = WebhookDispatcher(workers=2, capacity=5, deliver=stalled)
    try:
        for _ in range(2):
            assert dispatcher.submit("https://logs.example", "audit.completed", {})
        assert started.wait(3)
        for _ in range(20):
            dispatcher.submit("https://logs.example", "audit.completed", {})
        stats = dispatcher.snapshot()
        assert stats["in_flight"] == 2
        assert stats["queue_depth"] == 3
        assert stats["outstanding"] == stats["max_outstanding"] == 5
        assert stats["active_workers"] == stats["worker_limit"] == 2
        assert stats["dropped"] == 17
        assert not dispatcher.flush(timeout=0.01)
        release.set()
        assert dispatcher.flush(3)
        assert maximum == 2 and count == 5
        assert dispatcher.snapshot()["delivered"] == 5
    finally:
        release.set()
        assert dispatcher.close()


@pytest.mark.parametrize("data", [{"bad": float("nan")}, {"bad": object()}, {"long": "x" * 1000}])
def test_invalid_or_oversized_events_are_dropped(data):
    dispatcher = WebhookDispatcher(
        workers=1, capacity=1, max_event_bytes=256, deliver=lambda job: True
    )
    try:
        assert not dispatcher.submit("https://logs.example", "audit.completed", data)
        assert dispatcher.snapshot()["dropped"] == 1
        assert dispatcher.snapshot()["outstanding"] == 0
        assert not dispatcher.submit("https://logs.example", "unknown.event", {})
    finally:
        assert dispatcher.close()


def test_callback_failure_releases_its_reservation_and_keeps_worker_alive(caplog):
    def broken(job):
        raise RuntimeError("private-payload-not-for-logs")

    dispatcher = WebhookDispatcher(workers=1, capacity=1, deliver=broken)
    try:
        for _ in range(2):
            assert dispatcher.submit("https://logs.example", "audit.completed", {})
            assert dispatcher.flush(3)
        assert dispatcher.snapshot()["failed"] == 2
        assert dispatcher.snapshot()["outstanding"] == 0
        assert "private-payload-not-for-logs" not in caplog.text
    finally:
        assert dispatcher.close()


def test_shutdown_is_bounded_seals_queue_and_discards_waiting_jobs():
    release, started = threading.Event(), threading.Event()

    def stalled(job):
        started.set()
        assert release.wait(3)
        return True

    dispatcher = WebhookDispatcher(workers=1, capacity=2, deliver=stalled)
    try:
        assert dispatcher.submit("https://logs.example", "audit.completed", {})
        assert started.wait(2)
        assert dispatcher.submit("https://logs.example", "audit.completed", {})
        assert not dispatcher.close(timeout=0.01, drain=False)
        assert dispatcher.snapshot()["dropped"] == 1
        assert not dispatcher.submit("https://logs.example", "audit.completed", {})
        release.set()
        assert dispatcher.close()
        assert dispatcher.snapshot()["active_workers"] == 0
    finally:
        release.set()
        dispatcher.close()


def test_closed_pool_is_not_replaced_until_its_workers_exit(monkeypatch):
    release, started = threading.Event(), threading.Event()

    def stalled(job):
        started.set()
        assert release.wait(3)
        return True

    dispatcher = WebhookDispatcher(workers=1, capacity=1, deliver=stalled)
    monkeypatch.setattr(loghook, "_DISPATCHER", dispatcher)
    try:
        dispatcher.submit("https://logs.example", "audit.completed", {})
        assert started.wait(2)
        assert not shutdown_log_shipping(timeout=0.01)
        assert loghook._dispatcher() is None
        release.set()
        assert dispatcher.close()
        replacement = loghook._dispatcher()
        assert replacement is not dispatcher
        assert len(drain_all_sync()) == 1
    finally:
        release.set()
        dispatcher.close()


def test_forked_dispatcher_is_not_reused(monkeypatch):
    dispatcher = WebhookDispatcher(workers=1, capacity=1, deliver=lambda job: True)
    try:
        dispatcher.pid = -1
        monkeypatch.setattr(loghook, "_DISPATCHER", dispatcher)
        assert loghook._dispatcher() is not dispatcher
    finally:
        assert dispatcher.close()


@pytest.mark.parametrize(
    "bounds", [{"workers": 0}, {"workers": 2, "capacity": 1}, {"max_event_bytes": 0}]
)
def test_invalid_pool_bounds_fail(bounds):
    with pytest.raises(ValueError):
        WebhookDispatcher(**bounds)


def test_webhook_env_configured(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_URL", "https://logs.example/ingest")
    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_SECRET", "test-secret")
    assert webhook_url() == "https://logs.example/ingest"
    assert webhook_enabled()
    assert webhook_secret() == "test-secret"


def test_app_lifespan_closes_the_delivery_pool(monkeypatch, transport):
    transport()
    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_URL", "https://logs.example/ingest")
    with TestClient(app) as client:
        assert client.get("/api/chaos?model=legacy").status_code == 200
        assert (
            client.post(
                "/api/appeals", json={"candidate_id": "C-1000", "message": "synthetic test"}
            ).status_code
            == 200
        )
        # Embedded callers use the same hook, even if a route emits no event.
        ship("audit.completed", {"model": "legacy"})
    assert log_shipping_status()["active_workers"] == 0
    assert log_shipping_status()["outstanding"] == 0
    assert not log_shipping_status()["accepting"]


def test_delivery_record_has_no_mutable_payload():
    job = Delivery("https://logs.example", "audit.completed", b"{}", None)
    assert job.body == b"{}"
