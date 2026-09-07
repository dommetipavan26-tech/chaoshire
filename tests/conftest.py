"""Shared test isolation for in-memory application state and SQLite history."""
import pytest

from chaoshire.state import APPEALS, UPLOADED


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOSHIRE_DB_PATH", str(tmp_path / "chaoshire-test.db"))
    APPEALS.clear()
    UPLOADED.update({"df": None, "metadata": None, "audit": None})
    yield
    APPEALS.clear()
    UPLOADED.update({"df": None, "metadata": None, "audit": None})
