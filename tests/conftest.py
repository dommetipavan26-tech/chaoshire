"""Shared test isolation for in-memory application state and SQLite history.

Tests run as an **authenticated operator**: ``isolated_state`` configures
``CHAOSHIRE_API_KEY`` and :func:`operator_client` sends it on every request.
That keeps the publish path (persistent audit history + the shared
``dataset=uploaded`` slot) under test. Tests that need the anonymous path build
a plain ``TestClient`` and omit the header — see
``tests/test_write_access.py``.

The per-minute rate-limit budgets are disabled here so a fast suite does not
trip them; the limiters are exercised directly in ``tests/test_write_access.py``.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

import backend
from chaoshire.platform import LIMITER
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
    monkeypatch.delenv("CHAOSHIRE_ALLOW_ANONYMOUS_WRITES", raising=False)
    monkeypatch.delenv("CHAOSHIRE_MAX_APPEALS", raising=False)
    monkeypatch.delenv("CHAOSHIRE_REMOTE_MODELS", raising=False)
    LIMITER.reset()
    _clear_shared_state()
    yield
    LIMITER.reset()
    _clear_shared_state()
