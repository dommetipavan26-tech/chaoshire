"""SQLite repository for aggregate audit evidence.

Raw uploaded candidate rows are deliberately never written to this database.
The default local path can be overridden with ``CHAOSHIRE_DB_PATH``.
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
            "CREATE INDEX IF NOT EXISTS idx_audit_runs_created_at "
            "ON audit_runs(created_at DESC)"
        )


def save_audit(
    result: dict[str, Any],
    name: str,
    configuration: dict[str, Any],
    source: str = "uploaded_csv",
) -> str:
    """Persist aggregate results and return a stable public audit ID."""
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
    initialise_database()
    with connect() as connection:
        row = connection.execute(
            "SELECT result_json FROM audit_runs WHERE id = ?", (audit_id,)
        ).fetchone()
    return json.loads(row["result_json"]) if row else None
