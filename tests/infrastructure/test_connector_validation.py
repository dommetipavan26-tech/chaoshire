"""Safe remote configuration and 502 verdicts for invalid external decision contracts."""

import json

import httpx
import pytest
from conftest import operator_client

import chaoshire.app as app_module
from chaoshire.adapters import RemoteDecisionAdapter, remote_adapters_from_env


@pytest.mark.parametrize(
    "url",
    [
        "ftp://vendor.example/data",
        "https://user:private-password@vendor.example/data",
        "https://vendor.example/data?token=private-token",
        "https://vendor.example/data#fragment",
        "https://vendor.example:bad/data",
        "https://vendor.example:0/data",
        "http://vendor.example/data",
        "https://vendor.example/white space",
        "https://vendor.example\\bad",
    ],
)
def test_bad_urls_are_rejected_without_echoing_credentials(url):
    adapter = RemoteDecisionAdapter("vendor", url)
    with pytest.raises(ValueError) as error:
        adapter.describe()
    assert "private-password" not in str(error.value)
    assert "private-token" not in str(error.value)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), 121, "30", True])
def test_timeouts_are_positive_finite_and_bounded(timeout):
    adapter = RemoteDecisionAdapter(
        "vendor", "https://vendor.example/data", timeout_seconds=timeout
    )
    with pytest.raises(ValueError, match="timeout_seconds"):
        adapter.describe()


def test_private_http_requires_an_explicit_operator_opt_in():
    adapter = RemoteDecisionAdapter("local", "http://127.0.0.1:8001/decisions", allow_http=True)
    assert adapter.describe()["url"].startswith("http:")


@pytest.mark.parametrize("key_env", ["", "API KEY", "KEY=VALUE", 123])
def test_credential_variable_names_are_validated(key_env):
    adapter = RemoteDecisionAdapter("vendor", "https://vendor.example/data", api_key_env=key_env)
    with pytest.raises(ValueError, match="environment-variable"):
        adapter.describe()


def test_response_bytes_are_bounded_before_json_parsing():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 65))
    adapter = RemoteDecisionAdapter(
        "vendor", "https://vendor.example/data", transport=transport, max_response_bytes=64
    )
    with pytest.raises(ValueError, match="byte limit"):
        adapter.decisions()


def test_redirects_are_not_followed_with_bearer_credentials(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://different.example/data"})

    monkeypatch.setenv("TEST_VENDOR_KEY", "test-only-bearer")
    adapter = RemoteDecisionAdapter(
        "vendor",
        "https://vendor.example/data",
        "TEST_VENDOR_KEY",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(httpx.HTTPStatusError):
        adapter.decisions()
    assert len(requests) == 1


@pytest.mark.parametrize(
    "rows",
    [
        [{"accepted": "maybe", "gender": "F"}],
        [{"accepted": 1, "qualified": None, "gender": "F"}],
        [{"accepted": 1}],
        [{"accepted": 1, "gender": "F", "score": float("inf")}],
        ["not a row"],
    ],
)
def test_invalid_upstream_data_returns_sanitized_502_not_a_misleading_score(
    monkeypatch, rows, caplog
):
    adapter = RemoteDecisionAdapter(
        "vendor",
        "https://vendor.example/data",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=json.dumps(rows))),
    )
    monkeypatch.setattr(app_module, "find_remote_adapter", lambda model: adapter)
    response = operator_client().post("/api/connectors/audit", json={"model_id": "vendor"})
    assert response.status_code == 502
    assert "certificate" not in response.json()
    assert "vendor.example" not in response.text + caplog.text


def test_lower_level_adapter_cannot_bypass_missing_attribute_or_truth_validation(monkeypatch):
    import pandas as pd

    class BypassingAdapter:
        def decisions(self):
            return pd.DataFrame({"accepted": [True], "qualified": ["nonsense"], "gender": ["F"]})

        def describe(self):
            return {}

    monkeypatch.setattr(app_module, "find_remote_adapter", lambda model: BypassingAdapter())
    assert (
        operator_client().post("/api/connectors/audit", json={"model_id": "vendor"}).status_code
        == 502
    )


def test_custom_attribute_contract_is_supported_and_missing_columns_are_refused(monkeypatch):
    rows = [
        {"accepted": i % 2 == 0, "qualified": "false", "region": "east" if i < 30 else "west"}
        for i in range(60)
    ]
    adapter = RemoteDecisionAdapter(
        "vendor",
        "https://vendor.example/data",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=rows)),
    )
    monkeypatch.setattr(app_module, "find_remote_adapter", lambda model: adapter)
    client = operator_client()
    valid = client.post(
        "/api/connectors/audit", json={"model_id": "vendor", "protected_attributes": ["region"]}
    )
    assert valid.status_code == 200
    assert valid.json()["audit"]["stats"]["qualified_share"] == 0
    assert valid.json()["audit"]["attributes"][0]["attribute"] == "region"
    assert (
        client.post(
            "/api/connectors/audit",
            json={"model_id": "vendor", "protected_attributes": ["missing"]},
        ).status_code
        == 502
    )


def test_malformed_configuration_is_a_safe_503_and_catalog_misconfigured(monkeypatch):
    monkeypatch.setenv(
        "CHAOSHIRE_REMOTE_MODELS",
        '[{"model_id":"vendor","url":"https://secret:private-password@vendor.example/data"}]',
    )
    client = operator_client()
    response = client.post("/api/connectors/audit", json={"model_id": "vendor"})
    assert response.status_code == 503
    assert "private-password" not in response.text
    entry = next(
        a for a in client.get("/api/adapters").json()["adapters"] if a["id"] == "remote-http"
    )
    assert entry["status"] == "misconfigured"


@pytest.mark.parametrize(
    "entries",
    [
        [{"model_id": "same", "url": "https://a.example"}] * 2,
        [{"model_id": "newline\n", "url": "https://a.example"}],
        [{"model_id": 123, "url": "https://a.example"}],
        [{"model_id": "one", "url": "http://a.example", "allow_http": "true"}],
    ],
)
def test_invalid_or_duplicate_configuration_identifiers_fail(entries, monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_REMOTE_MODELS", json.dumps(entries))
    with pytest.raises(ValueError):
        remote_adapters_from_env()


def test_compressed_response_is_refused_before_decompression():
    import gzip

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, content=gzip.compress(b"x" * 1_000_000), headers={"Content-Encoding": "gzip"}
        )
    )
    adapter = RemoteDecisionAdapter("vendor", "https://vendor.example/data", transport=transport)
    with pytest.raises(ValueError, match="identity encoding"):
        adapter.decisions()
