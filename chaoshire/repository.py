"""Repository dispatcher and SQLite backend for aggregate audit evidence.

Raw uploaded candidate rows are deliberately never written to this database.
The default local path can be overridden with ``CHAOSHIRE_DB_PATH``.

Set ``CHAOSHIRE_DB_BACKEND=postgres`` and ``CHAOSHIRE_DATABASE_URL`` to use
the optional PostgreSQL adapter in :mod:`chaoshire.repository_postgres`.
SQLite remains the zero-config default for local runs, tests, and the
free-tier deployment.
"""

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def _postgres_active() -> bool:
    """Whether the operator opted into the PostgreSQL backend."""
    return (os.getenv("CHAOSHIRE_DB_BACKEND") or "").strip().lower() == "postgres"


def database_path() -> str:
    return os.getenv("CHAOSHIRE_DB_PATH", "data/chaoshire.db")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = database_path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialise_database() -> None:
    if _postgres_active():
        from .repository_postgres import initialise_database as _pg_init

        _pg_init()
        return
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_runs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                accepted_count INTEGER NOT NULL,
                certificate_score INTEGER NOT NULL,
                certificate_grade TEXT NOT NULL,
                protected_attributes TEXT NOT NULL,
                configuration_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_runs_created_at ON audit_runs(created_at DESC)"
        )


def save_audit(
    result: dict[str, Any],
    name: str,
    configuration: dict[str, Any],
    source: str = "uploaded_csv",
) -> str:
    """Persist aggregate results and return a stable public audit ID."""
    if _postgres_active():
        from .repository_postgres import save_audit as _pg_save

        return _pg_save(result, name, configuration, source)
    initialise_database()
    audit_id = f"AUD-{uuid4().hex[:12].upper()}"
    created_at = datetime.now(UTC).isoformat()
    result["audit_id"] = audit_id
    result["audit_name"] = name
    result["created_at"] = created_at
    result["source"] = source
    stats = result["stats"]
    certificate = result["certificate"]
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO audit_runs (
                id, name, created_at, source, row_count, accepted_count,
                certificate_score, certificate_grade, protected_attributes,
                configuration_json, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                name,
                created_at,
                source,
                stats["candidates"],
                stats["accepted"],
                certificate["total"],
                certificate["grade"],
                json.dumps(configuration["protected_attributes"]),
                json.dumps(configuration, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
            ),
        )
    return audit_id


def list_audits(limit: int = 50) -> list[dict[str, Any]]:
    if _postgres_active():
        from .repository_postgres import list_audits as _pg_list

        return _pg_list(limit)
    initialise_database()
    safe_limit = max(1, min(limit, 100))
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, name, created_at, source, row_count, accepted_count,
                   certificate_score, certificate_grade, protected_attributes
            FROM audit_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [
        {
            "audit_id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "source": row["source"],
            "candidates": row["row_count"],
            "accepted": row["accepted_count"],
            "certificate": {
                "total": row["certificate_score"],
                "grade": row["certificate_grade"],
            },
            "protected_attributes": json.loads(row["protected_attributes"]),
        }
        for row in rows
    ]


def get_audit(audit_id: str) -> dict[str, Any] | None:
    if _postgres_active():
        from .repository_postgres import get_audit as _pg_get

        return _pg_get(audit_id)
    initialise_database()
    with connect() as connection:
        row = connection.execute(
            "SELECT result_json FROM audit_runs WHERE id = ?", (audit_id,)
        ).fetchone()
    return json.loads(row["result_json"]) if row else None
