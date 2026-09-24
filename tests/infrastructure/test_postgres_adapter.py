"""Tests for the optional PostgreSQL repository adapter.

These tests verify the dispatch logic and configuration surface without
requiring an actual PostgreSQL instance. The SQLite backend remains the
default and is covered by the broader test suite.
"""

from __future__ import annotations

import pytest

from chaoshire.repository import _postgres_active
from chaoshire.repository_postgres import (
    database_url,
    postgres_enabled,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("CHAOSHIRE_DB_BACKEND", raising=False)
    monkeypatch.delenv("CHAOSHIRE_DATABASE_URL", raising=False)


def test_postgres_not_enabled_by_default():
    assert not postgres_enabled()
    assert not _postgres_active()
    assert database_url() is None


def test_postgres_enabled_when_configured(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_DB_BACKEND", "postgres")
    assert postgres_enabled()
    assert _postgres_active()


def test_postgres_case_insensitive(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_DB_BACKEND", "PostgreSQL")
    # Only 'postgres' matches
    assert not postgres_enabled()
    monkeypatch.setenv("CHAOSHIRE_DB_BACKEND", "POSTGRES")
    assert postgres_enabled()


def test_database_url_from_env(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_DATABASE_URL", "postgresql://user:pass@host/db")
    assert database_url() == "postgresql://user:pass@host/db"


def test_database_url_strips_whitespace(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_DATABASE_URL", "  postgresql://host/db  ")
    assert database_url() == "postgresql://host/db"


def test_sqlite_default_when_backend_unset():
    """Without CHAOSHIRE_DB_BACKEND, the repository uses SQLite."""
    from chaoshire.repository import initialise_database, list_audits

    # Must not raise even though postgres is not configured
    initialise_database()
    audits = list_audits()
    assert isinstance(audits, list)


def test_build_info_reports_sqlite_by_default():
    from chaoshire.build_info import build_info

    info = build_info()
    assert info["repository_backend"] == "sqlite"


def test_build_info_reports_postgres_when_configured(monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_DB_BACKEND", "postgres")
    from chaoshire.build_info import build_info

    info = build_info()
    assert info["repository_backend"] == "postgres"


def test_postgres_connect_requires_url(monkeypatch):
    """connect() raises when CHAOSHIRE_DATABASE_URL is unset."""
    import sys
    from unittest.mock import MagicMock

    # Fake psycopg2 so the import check passes even when the real package
    # is not installed.
    fake_psycopg2 = MagicMock()
    fake_psycopg2.extras = MagicMock()
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", fake_psycopg2.extras)

    from chaoshire.repository_postgres import connect

    with pytest.raises(RuntimeError, match="CHAOSHIRE_DATABASE_URL"):
        with connect():
            pass


def test_postgres_dispatch_save_audit(monkeypatch):
    """When postgres is active, save_audit delegates to the postgres module."""
    import chaoshire.repository as repo

    monkeypatch.setenv("CHAOSHIRE_DB_BACKEND", "postgres")
    assert repo._postgres_active()

    # Mock the postgres save_audit to avoid needing a real DB
    called = {}

    def fake_save(result, name, config, source="uploaded_csv"):
        called["args"] = (result, name, config, source)
        return "AUD-MOCK123456"

    monkeypatch.setattr("chaoshire.repository_postgres.save_audit", fake_save)
    result = repo.save_audit(
        {"stats": {"candidates": 100, "accepted": 50}, "certificate": {"total": 80, "grade": "B"}},
        "test audit",
        {"protected_attributes": ["gender"]},
    )
    assert result == "AUD-MOCK123456"
    assert "args" in called


def test_postgres_dispatch_list_audits(monkeypatch):
    import chaoshire.repository as repo

    monkeypatch.setenv("CHAOSHIRE_DB_BACKEND", "postgres")

    def fake_list(limit=50):
        return [{"audit_id": "AUD-TEST", "name": "test"}]

    monkeypatch.setattr("chaoshire.repository_postgres.list_audits", fake_list)
    result = repo.list_audits(10)
    assert result == [{"audit_id": "AUD-TEST", "name": "test"}]


def test_postgres_dispatch_get_audit(monkeypatch):
    import chaoshire.repository as repo

    monkeypatch.setenv("CHAOSHIRE_DB_BACKEND", "postgres")

    def fake_get(audit_id):
        return {"audit_id": audit_id, "stats": {}} if audit_id == "AUD-FOUND" else None

    monkeypatch.setattr("chaoshire.repository_postgres.get_audit", fake_get)
    assert repo.get_audit("AUD-FOUND") == {"audit_id": "AUD-FOUND", "stats": {}}
    assert repo.get_audit("AUD-MISSING") is None


def test_postgres_dispatch_initialise_database(monkeypatch):
    import chaoshire.repository as repo

    monkeypatch.setenv("CHAOSHIRE_DB_BACKEND", "postgres")
    called = {"init": False}

    def fake_init():
        called["init"] = True

    monkeypatch.setattr("chaoshire.repository_postgres.initialise_database", fake_init)
    repo.initialise_database()
    assert called["init"] is True
