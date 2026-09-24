"""Shared test isolation for in-memory application state and SQLite history.

Tests run as an **authenticated operator**: ``isolated_state`` configures
``CHAOSHIRE_API_KEY`` and :func:`operator_client` sends it on every request.
That keeps the publish path (persistent audit history + the shared
``dataset=uploaded`` slot) under test. Tests that need the anonymous path build
a plain ``TestClient`` and omit the header — see
``tests/api/test_write_access.py``.

The per-minute rate-limit budgets are disabled here so a fast suite does not
trip them; the limiters are exercised directly in ``tests/api/test_write_access.py``.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

import backend
from chaoshire.platform import LIMITER
from chaoshire.site import SITE_ANALYTICS
from chaoshire.state import APPEALS, UPLOADED, UPLOADED_LOCK, appeals_capacity

TEST_API_KEY = "test-operator-key-not-a-secret"


def operator_client(**kwargs: Any) -> TestClient:
    """A ``TestClient`` that authenticates with :data:`TEST_API_KEY`."""
    client = TestClient(backend.app, **kwargs)
    client.headers.update({"X-API-Key": TEST_API_KEY})
    return client


def _clear_shared_state() -> None:
    APPEALS.set_capacity(appeals_capacity())
    APPEALS.clear()
    with UPLOADED_LOCK:
        UPLOADED.update({"df": None, "metadata": None, "audit": None})


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_DB_PATH", str(tmp_path / "chaoshire-test.db"))
    monkeypatch.setenv("CHAOSHIRE_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("CHAOSHIRE_RATE_LIMIT_PER_MINUTE", "0")
    monkeypatch.setenv("CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE", "0")
    monkeypatch.setenv("CHAOSHIRE_ANONYMOUS_APPEALS_PER_MINUTE", "0")
    monkeypatch.delenv("CHAOSHIRE_ALLOW_ANONYMOUS_WRITES", raising=False)
    monkeypatch.delenv("CHAOSHIRE_DISCLOSE_WRITE_POSTURE", raising=False)
    monkeypatch.delenv("CHAOSHIRE_AUDIT_HISTORY_DURABLE", raising=False)
    monkeypatch.delenv("CHAOSHIRE_TRUST_FORWARDED_FOR", raising=False)
    monkeypatch.delenv("CHAOSHIRE_MAX_APPEALS", raising=False)
    monkeypatch.delenv("CHAOSHIRE_REMOTE_MODELS", raising=False)
    monkeypatch.delenv("CHAOSHIRE_FORCE_HTTPS", raising=False)
    monkeypatch.delenv("CHAOSHIRE_TRUST_FORWARDED_PROTO", raising=False)
    monkeypatch.delenv("CHAOSHIRE_PUBLIC_ORIGIN", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    LIMITER.reset()
    SITE_ANALYTICS.reset()
    _clear_shared_state()
    yield
    LIMITER.reset()
    SITE_ANALYTICS.reset()
    _clear_shared_state()
