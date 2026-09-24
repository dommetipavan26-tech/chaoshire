"""Nonce-based CSP and the operator-configured remote decision connector."""

import json
import logging
import re

import httpx
import pytest
from conftest import operator_client
from fastapi.testclient import TestClient

import chaoshire.app as app_module
from chaoshire.adapters import (
    RemoteDecisionAdapter,
    find_remote_adapter,
    remote_adapters_from_env,
)
from chaoshire.app import app
from chaoshire.services import upload_decisions

client = operator_client()

# A URL of the shape httpx and urllib actually put in their error text: scheme,
# embedded credentials, host, path and query. If any fragment of it reaches a
# response body, the assertions below fail.
SECRET_URL = "https://operator:sk-live-SUPERSECRET@models.example/decisions?token=abc123"

NONCE_RE = re.compile(r"script-src 'self' 'nonce-([^']+)'")


def test_csp_uses_a_fresh_nonce_per_request():
    with TestClient(app) as client:
        first = client.get("/")
        second = client.get("/")

    csp = first.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "form-action 'self'" in csp
    script_src = csp.split("script-src")[1].split(";")[0]
    assert "'unsafe-inline'" not in script_src

    match = NONCE_RE.search(csp)
    assert match, f"no nonce in script-src: {script_src}"
    nonce = match.group(1)
    assert f'<script nonce="{nonce}">' in first.text
    assert "<script>" not in first.text

    second_nonce = NONCE_RE.search(second.headers["content-security-policy"])
    assert second_nonce and second_nonce.group(1) != nonce


def _handler(payload, status=200, require_auth=None):
    def handle(request: httpx.Request) -> httpx.Response:
        if (
            require_auth is not None
            and request.headers.get("Authorization") != f"Bearer {require_auth}"
        ):
            return httpx.Response(401, json={"error": "unauthorized"})
        return httpx.Response(status, json=payload)

    return handle


def test_remote_adapter_authenticates_and_normalises(monkeypatch):
    payload = {
        "decisions": [
            {"candidate_id": "R-1", "accepted": "yes", "gender": "F", "qualified": True},
            {"candidate_id": "R-2", "accepted": 0, "gender": "M", "qualified": False},
            {"candidate_id": "R-3", "accepted": True, "gender": "NB", "qualified": True},
        ]
    }
    adapter = RemoteDecisionAdapter(
        model_id="acme-v4",
        url="https://models.example/decisions",
        api_key_env="ACME_KEY",
        transport=httpx.MockTransport(_handler(payload, require_auth="secret-key")),
    )
    assert adapter.describe()["authenticated"] is True
    assert adapter.describe()["mode"] == "remote_http"

    monkeypatch.setenv("ACME_KEY", "secret-key")
    frame = adapter.decisions()
    assert frame["accepted"].tolist() == [True, False, True]

    monkeypatch.delenv("ACME_KEY")
    with pytest.raises(ValueError, match="missing API key"):
        adapter.decisions()


def test_remote_adapter_rejects_bad_payloads_and_upstream_errors():
    adapter = RemoteDecisionAdapter(
        model_id="x",
        url="https://e.example/d",
        transport=httpx.MockTransport(_handler({"nope": []})),
    )
    with pytest.raises(ValueError, match="no decision rows"):
        adapter.decisions()

    adapter = RemoteDecisionAdapter(
        model_id="x",
        url="https://e.example/d",
        transport=httpx.MockTransport(_handler([{"candidate_id": "R-1"}])),
    )
    with pytest.raises(ValueError, match="missing the 'accepted' field"):
        adapter.decisions()

    adapter = RemoteDecisionAdapter(
        model_id="x",
        url="https://e.example/d",
        transport=httpx.MockTransport(_handler({}, status=500)),
    )
    with pytest.raises(httpx.HTTPStatusError):
        adapter.decisions()

    adapter = RemoteDecisionAdapter(model_id="x", url="ftp://e.example/d")
    with pytest.raises(ValueError, match="http\\(s\\)"):
        adapter.decisions()


def test_env_config_parsing(monkeypatch):
    monkeypatch.delenv("CHAOSHIRE_REMOTE_MODELS", raising=False)
    assert remote_adapters_from_env() == []
    assert find_remote_adapter("anything") is None

    monkeypatch.setenv(
        "CHAOSHIRE_REMOTE_MODELS",
        json.dumps(
            [
                {
                    "model_id": "acme-v4",
                    "url": "https://models.example/decisions",
                    "api_key_env": "ACME_KEY",
                }
            ]
        ),
    )
    adapters = remote_adapters_from_env()
    assert [adapter.model_id for adapter in adapters] == ["acme-v4"]
    assert find_remote_adapter("acme-v4") is not None
    assert find_remote_adapter("ghost") is None

    monkeypatch.setenv("CHAOSHIRE_REMOTE_MODELS", "not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        remote_adapters_from_env()

    monkeypatch.setenv(
        "CHAOSHIRE_REMOTE_MODELS", json.dumps({"model_id": "x", "url": "https://e.example"})
    )
    with pytest.raises(ValueError, match="JSON list"):
        remote_adapters_from_env()

    monkeypatch.setenv(
        "CHAOSHIRE_REMOTE_MODELS", json.dumps([{"model_id": "x", "url": "ftp://bad"}])
    )
    with pytest.raises(ValueError, match="http\\(s\\)"):
        remote_adapters_from_env()


def _remote_rows():
    return [
        {
            "candidate_id": f"R-{i}",
            "accepted": i % 2 == 0,
            "gender": "F" if i % 2 == 0 else "M",
            "ethnicity": "G1" if i % 3 else "G2",
            "age_band": "18-35" if i % 4 else "36-50",
            "qualified": i % 2 == 0,
        }
        for i in range(120)
    ]


def test_connector_audit_endpoint(monkeypatch):
    adapter = RemoteDecisionAdapter(
        model_id="acme-v4",
        url="https://models.example/decisions",
        transport=httpx.MockTransport(_handler(_remote_rows())),
    )
    monkeypatch.setenv(
        "CHAOSHIRE_REMOTE_MODELS",
        json.dumps([{"model_id": "acme-v4", "url": "https://models.example/decisions"}]),
    )
    # The endpoint resolves connectors through the app namespace; the transport-
    # backed adapter keeps the test offline while the catalog reads real config.
    monkeypatch.setattr(
        app_module,
        "find_remote_adapter",
        lambda model_id: adapter if model_id == "acme-v4" else None,
    )

    with TestClient(app) as client:
        response = client.post("/api/connectors/audit", json={"model_id": "acme-v4"})
        assert response.status_code == 200
        body = response.json()
        assert body["model_id"] == "acme-v4"
        assert body["adapter"]["mode"] == "remote_http"
        assert body["audit"]["stats"]["candidates"] == 120
        assert "certificate" in body["audit"]

        missing = client.post("/api/connectors/audit", json={"model_id": "ghost"})
        assert missing.status_code == 404
        assert missing.json()["configured"] == ["acme-v4"]

        catalog = client.get("/api/adapters").json()
        remote_entry = next(a for a in catalog["adapters"] if a["id"] == "remote-http")
        assert remote_entry["status"] == "configured"
        assert remote_entry["configured_models"] == ["acme-v4"]
        assert "ACME_KEY" not in json.dumps(catalog)

        # Upstream failure is a bad gateway, not a ChaosHire 500.
        broken = RemoteDecisionAdapter(
            model_id="acme-v4",
            url="https://models.example/decisions",
            transport=httpx.MockTransport(_handler({}, status=503)),
        )
        monkeypatch.setattr(app_module, "find_remote_adapter", lambda model_id: broken)
        failure = client.post("/api/connectors/audit", json={"model_id": "acme-v4"})
        assert failure.status_code == 502
        assert "could not be audited" in failure.json()["error"]


def test_upstream_failure_never_echoes_the_exception(monkeypatch, caplog):
    """CodeQL `py/stack-trace-exposure`: the 502 body must not carry the detail.

    Remote-connector exceptions are exactly the kind that embed the request URL,
    proxy configuration or a credential fragment, so the client receives the
    failure category and the exception class, and the operator gets the full text
    in the server log.
    """

    class ExplodingAdapter:
        def describe(self) -> dict:
            return {"id": "remote-http", "model_id": "acme-v4"}

        def decisions(self):
            raise RuntimeError(f"connect timeout while requesting {SECRET_URL}")

    monkeypatch.setattr(app_module, "find_remote_adapter", lambda model_id: ExplodingAdapter())
    with caplog.at_level(logging.WARNING, logger="chaoshire.app"):
        response = client.post("/api/connectors/audit", json={"model_id": "acme-v4"})

    assert response.status_code == 502
    body = response.text
    assert "SUPERSECRET" not in body
    assert "abc123" not in body
    assert "models.example" not in body
    payload = response.json()
    assert payload["error"] == "Remote model 'acme-v4' could not be audited."
    assert payload["reason"] == "RuntimeError"
    # The detail is not lost, it is just not sent to the caller.
    assert "SUPERSECRET" in caplog.text


def test_csv_parse_failure_never_echoes_parser_internals(caplog):
    """Same rule for the upload path, which is reachable anonymously."""
    malformed = "gender,ethnicity,decision\nM,G1,1\nF,G2,0,EXTRA\n"
    with caplog.at_level(logging.WARNING, logger="chaoshire.services"):
        response = client.post("/api/upload", json={"csv": malformed, "audit_name": "Bad CSV"})

    assert response.status_code == 422
    body = response.text
    assert "EXTRA" not in body
    assert "Error tokenizing data" not in body
    assert "C error" not in body
    error = response.json()["error"]
    assert error.startswith("Could not parse the uploaded CSV (ParserError).")
    assert "UTF-8" in error
    # And the parser's own text is still available to whoever operates the box.
    assert "Error tokenizing data" in caplog.text

    direct = upload_decisions(csv_text=malformed, audit_name="Bad CSV", publish=False)
    assert direct["error"] == error


def test_callable_adapter_still_validates_its_contract():
    import pandas as pd

    from chaoshire.adapters import CallableDecisionAdapter

    adapter = CallableDecisionAdapter(model_id="m", provider=lambda: pd.DataFrame({"nope": [1]}))
    with pytest.raises(ValueError, match="missing required columns"):
        adapter.decisions()


def test_config_entries_need_model_id_and_url(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_REMOTE_MODELS", json.dumps([{"model_id": "x"}]))
    with pytest.raises(ValueError, match="needs 'model_id' and 'url'"):
        remote_adapters_from_env()
    monkeypatch.setenv("CHAOSHIRE_REMOTE_MODELS", json.dumps(["nonsense"]))
    with pytest.raises(ValueError, match="needs 'model_id' and 'url'"):
        remote_adapters_from_env()


def test_catalog_reports_misconfigured_connectors(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_REMOTE_MODELS", "broken{json")
    with TestClient(app) as client:
        catalog = client.get("/api/adapters").json()
    entry = next(a for a in catalog["adapters"] if a["id"] == "remote-http")
    assert entry["status"] == "misconfigured"
    assert entry["configured_models"] == []
