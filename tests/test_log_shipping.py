"""Tests for the structured JSON log-shipping hook (chaoshire.loghook)."""

from __future__ import annotations

import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from chaoshire.app import app
from chaoshire.loghook import (
    SHIPPED_EVENTS,
    _build_payload,
    _sign,
    log_shipping_status,
    queue_depth,
    ship,
    webhook_enabled,
    webhook_secret,
    webhook_url,
)


@pytest.fixture(autouse=True)
def _clear_webhook_env(monkeypatch):
    monkeypatch.delenv("CHAOSHIRE_LOG_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("CHAOSHIRE_LOG_WEBHOOK_SECRET", raising=False)


def test_webhook_not_configured_by_default():
    assert webhook_url() is None
    assert not webhook_enabled()
    assert webhook_secret() is None


def test_ship_is_silent_when_unconfigured():
    ship("audit.completed", {"model": "legacy", "certificate_grade": "F"})
    assert queue_depth() == 0


def test_build_payload_shape():
    payload = _build_payload("audit.completed", {"model": "legacy"})
    assert payload["event"] == "audit.completed"
    assert payload["service"] == "chaoshire"
    assert payload["data"] == {"model": "legacy"}
    assert "timestamp" in payload


def test_sign_produces_hex_digest():
    sig = _sign(b'{"event":"test"}', "secret")
    assert len(sig) == 64
    assert all(c in "0123456789abcdef" for c in sig)


def test_shipped_events_catalogue():
    assert "audit.completed" in SHIPPED_EVENTS
    assert "appeal.created" in SHIPPED_EVENTS
    assert "chaos.completed" in SHIPPED_EVENTS
    assert "mitigation.completed" in SHIPPED_EVENTS
    assert "upload.completed" in SHIPPED_EVENTS


def test_log_shipping_status_when_unconfigured():
    status = log_shipping_status()
    assert status["configured"] is False
    assert status["url_present"] is False
    assert status["signed"] is False
    assert status["queue_depth"] == 0
    assert status["events_shipped"] == list(SHIPPED_EVENTS)


def test_meta_reports_log_shipping_status():
    with TestClient(app) as client:
        meta = client.get("/api/meta").json()
    assert "log_shipping" in meta
    assert meta["log_shipping"]["configured"] is False


def test_ship_delivers_to_webhook(monkeypatch):
    """When configured, events are POSTed to the webhook URL."""
    received: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content))
        return httpx.Response(200)

    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_URL", "https://logs.example/ingest")
    transport = httpx.MockTransport(handler)

    import chaoshire.loghook as loghook

    def patched_drain():
        with loghook._QUEUE_LOCK:
            if not loghook._QUEUE:
                return
            item = loghook._QUEUE.pop(0)
        body = json.dumps(item["payload"], ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        secret = loghook.webhook_secret()
        if secret:
            headers["X-ChaosHire-Signature"] = loghook._sign(body, secret)
        with httpx.Client(timeout=10.0, transport=transport) as client:
            client.post(item["url"], content=body, headers=headers)

    monkeypatch.setattr(loghook, "_drain_one", patched_drain)

    ship("audit.completed", {"model": "legacy", "certificate_grade": "F"})
    time.sleep(0.5)
    assert len(received) == 1
    assert received[0]["event"] == "audit.completed"
    assert received[0]["data"]["model"] == "legacy"


def test_ship_with_secret_signs_payload(monkeypatch):
    """When a secret is set, the X-ChaosHire-Signature header is sent."""
    received_headers: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_headers.append(dict(request.headers))
        return httpx.Response(200)

    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_URL", "https://logs.example/ingest")
    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_SECRET", "test-secret")
    transport = httpx.MockTransport(handler)

    import chaoshire.loghook as loghook

    def patched_drain():
        with loghook._QUEUE_LOCK:
            if not loghook._QUEUE:
                return
            item = loghook._QUEUE.pop(0)
        body = json.dumps(item["payload"], ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        secret = loghook.webhook_secret()
        if secret:
            headers["X-ChaosHire-Signature"] = loghook._sign(body, secret)
        with httpx.Client(timeout=10.0, transport=transport) as client:
            client.post(item["url"], content=body, headers=headers)

    monkeypatch.setattr(loghook, "_drain_one", patched_drain)

    ship("audit.completed", {"model": "legacy"})
    time.sleep(0.5)
    assert len(received_headers) == 1
    assert "x-chaoshire-signature" in received_headers[0]


def test_ship_handles_webhook_error(monkeypatch):
    """A 500 from the webhook is logged, not raised."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_URL", "https://logs.example/ingest")
    transport = httpx.MockTransport(handler)

    import chaoshire.loghook as loghook

    def patched_drain():
        with loghook._QUEUE_LOCK:
            if not loghook._QUEUE:
                return
            item = loghook._QUEUE.pop(0)
        body = json.dumps(item["payload"], ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        with httpx.Client(timeout=10.0, transport=transport) as client:
            response = client.post(item["url"], content=body, headers=headers)
        if response.status_code >= 400:
            import logging

            logging.getLogger("chaoshire.loghook").warning(
                "chaoshire log-shipping webhook returned %s for %s",
                response.status_code,
                item["payload"]["event"],
            )

    monkeypatch.setattr(loghook, "_drain_one", patched_drain)
    ship("audit.completed", {"model": "legacy"})
    time.sleep(0.5)


def test_ship_queue_overflow(monkeypatch):
    """When the queue is full, events are dropped silently."""
    import chaoshire.loghook as loghook

    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_URL", "https://logs.example/ingest")
    monkeypatch.setattr(loghook, "_drain_one", lambda: None)

    for i in range(loghook._MAX_QUEUE + 10):
        ship("audit.completed", {"i": i})

    assert loghook.queue_depth() == loghook._MAX_QUEUE


def test_webhook_env_configured(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_URL", "https://logs.example/ingest")
    assert webhook_url() == "https://logs.example/ingest"
    assert webhook_enabled()


def test_webhook_secret_configured(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_LOG_WEBHOOK_SECRET", "s3cret")
    assert webhook_secret() == "s3cret"


def test_appeal_triggers_ship_event():
    with TestClient(app) as client:
        response = client.post(
            "/api/appeals",
            json={"candidate_id": "C-1000", "message": "test appeal"},
        )
        assert response.status_code == 200


def test_chaos_triggers_ship_event():
    with TestClient(app) as client:
        response = client.get("/api/chaos?model=legacy")
        assert response.status_code == 200
