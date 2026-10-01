"""Regression tests for request/evidence edge cases found in the repository audit."""

import asyncio
import json

import pytest
from conftest import operator_client
from fastapi.testclient import TestClient

from chaoshire.app import app
from chaoshire.evidence import build_evidence_bundle, verify_evidence_bundle
from chaoshire.platform import OPERATIONS, RequestBodyLimitMiddleware, api_key_matches


@pytest.mark.parametrize("length", ["nope", "-1", "1.5", "", "+5", "9" * 4400])
def test_invalid_content_length_is_a_client_error(length):
    response = operator_client().post(
        "/api/evidence/verify", content=b"{}", headers={"Content-Length": length}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Content-Length header."
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in response.headers


@pytest.mark.parametrize("declared", [None, "1"])
def test_actual_stream_size_is_limited_without_trusting_content_length(monkeypatch, declared):
    monkeypatch.setenv("CHAOSHIRE_MAX_BODY_BYTES", "64")
    headers = {"Content-Type": "application/json"}
    if declared is not None:
        headers["Content-Length"] = declared
    chunks = iter([b'{"bundle":{},"padding":"', b"x" * 1000, b'"}'])
    before = OPERATIONS.snapshot()
    response = operator_client().post("/api/evidence/verify", content=chunks, headers=headers)
    assert response.status_code == 413
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "x-request-id" in response.headers
    after = OPERATIONS.snapshot()
    assert after["statuses"].get(413, 0) == before["statuses"].get(413, 0) + 1


def test_request_at_exact_budget_is_replayed_to_the_endpoint(monkeypatch):
    payload = b'{"bundle":{"payload":{}}}'
    monkeypatch.setenv("CHAOSHIRE_MAX_BODY_BYTES", str(len(payload)))
    response = operator_client().post(
        "/api/evidence/verify", content=payload, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["reason"] == "Digest mismatch."


def test_rate_limit_refusals_get_security_headers_and_are_counted(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_RATE_LIMIT_PER_MINUTE", "1")
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    before = OPERATIONS.snapshot()
    response = client.get("/api/health")
    assert response.status_code == 429
    assert response.headers["retry-after"].isdigit()
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in response.headers
    after = OPERATIONS.snapshot()
    assert after["statuses"].get(429, 0) == before["statuses"].get(429, 0) + 1


@pytest.mark.parametrize("route", ["/api/ops/posture", "/api/appeals"])
def test_non_ascii_api_key_is_rejected_not_crashed(route):
    client = TestClient(app)
    headers = [(b"X-API-Key", b"\xe9")]
    if route.endswith("appeals"):
        response = client.post(
            route, headers=headers, json={"candidate_id": "C-1046", "message": "Please review."}
        )
    else:
        response = client.get(route, headers=headers)
    assert response.status_code == 401


def test_key_comparison_accepts_valid_unicode_without_type_error():
    assert api_key_matches("clé", "clé")
    assert not api_key_matches("clé", "other")


@pytest.mark.parametrize("digest", ["sha256:é", "\ud800", None, 1, {}])
def test_invalid_evidence_digest_returns_a_verdict_not_a_server_error(digest):
    bundle = build_evidence_bundle({})
    bundle["integrity"]["digest"] = digest
    response = operator_client().post(
        "/api/evidence/verify",
        content=json.dumps({"bundle": bundle}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is False


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "\ud800"])
def test_noncanonical_evidence_payload_is_rejected(value):
    bundle = {"payload": {"value": value}, "integrity": {}}
    direct = verify_evidence_bundle(bundle)
    assert direct == {"valid": False, "reason": "Bundle payload is not canonical JSON."}
    response = operator_client().post(
        "/api/evidence/verify",
        content=json.dumps({"bundle": bundle}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == direct


def test_asgi_limit_stops_reading_at_the_budget_and_never_calls_the_endpoint(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_MAX_BODY_BYTES", "5")
    calls = []
    sent = []
    events = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": True},
        ]
    )

    async def receive():
        return next(events)  # Fails if the middleware attempts to read past the refusal.

    async def send(message):
        sent.append(message)

    async def endpoint(scope, receive, send):
        calls.append(scope)

    middleware = RequestBodyLimitMiddleware(endpoint)
    asyncio.run(middleware({"type": "http", "headers": []}, receive, send))
    assert calls == []
    assert sent[0]["status"] == 413


@pytest.mark.parametrize("headers", [[(b"content-length", b"6")], [(b"content-length", b"1")] * 2])
def test_invalid_declared_size_is_refused_before_any_body_read(monkeypatch, headers):
    monkeypatch.setenv("CHAOSHIRE_MAX_BODY_BYTES", "5")
    sent = []

    async def receive():
        pytest.fail("Body must not be read for an invalid declared size")

    async def send(message):
        sent.append(message)

    async def endpoint(scope, receive, send):
        pytest.fail("Endpoint must not be called for an invalid declared size")

    asyncio.run(
        RequestBodyLimitMiddleware(endpoint)({"type": "http", "headers": headers}, receive, send)
    )
    assert sent[0]["status"] == (413 if len(headers) == 1 else 400)


def test_body_limit_handles_disconnects_and_non_http_scopes():
    calls = []

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        pytest.fail("Disconnected requests must not receive a response")

    async def endpoint(scope, receive, send):
        calls.append(scope["type"])

    middleware = RequestBodyLimitMiddleware(endpoint)
    asyncio.run(middleware({"type": "http", "headers": []}, receive, send))
    asyncio.run(middleware({"type": "lifespan"}, receive, send))
    assert calls == ["lifespan"]


def test_replayed_body_delegates_later_receives():
    received = []
    events = iter(
        [{"type": "http.request", "body": b"ok", "more_body": False}, {"type": "http.disconnect"}]
    )

    async def receive():
        return next(events)

    async def send(message):
        pass

    async def endpoint(scope, receive, send):
        received.append(await receive())
        received.append(await receive())

    asyncio.run(
        RequestBodyLimitMiddleware(endpoint)({"type": "http", "headers": []}, receive, send)
    )
    assert received == [
        {"type": "http.request", "body": b"ok", "more_body": False},
        {"type": "http.disconnect"},
    ]
