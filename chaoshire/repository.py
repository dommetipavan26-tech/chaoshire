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
from threading import Lock
from typing import Any
from uuid import uuid4

_SQLITE_WAL_LOCK = Lock()


def _ensure_wal(connection: sqlite3.Connection, path: str) -> None:
    """Set persistent WAL mode without racing concurrent connection opens.

    Reissuing ``PRAGMA journal_mode=WAL`` on every connection races when
    concurrent uploads open the same SQLite file. The mode persists in the DB
    file, so serialize the check and only change it when needed. Rechecking the
    file also handles an operator replacing a local database at the same path.
    """
    if path == ":memory:":
        return
    with _SQLITE_WAL_LOCK:
        mode = connection.execute("PRAGMA journal_mode").fetchone()
        if mode is None or str(mode[0]).lower() != "wal":
            connection.execute("PRAGMA journal_mode=WAL")


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
        _ensure_wal(connection, path)
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
                result_json TEXT NOT NULL,
                access_token_hash TEXT
            )
            """
        )
        # Databases created before per-audit access tokens existed have no
        # digest column; add it in place. Rows predating the feature keep a
        # NULL digest and are readable by the operator only.
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(audit_runs)").fetchall()
        }
        if "access_token_hash" not in columns:
            connection.execute("ALTER TABLE audit_runs ADD COLUMN access_token_hash TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_runs_created_at ON audit_runs(created_at DESC)"
        )


def save_audit(
    result: dict[str, Any],
    name: str,
    configuration: dict[str, Any],
    source: str = "uploaded_csv",
    access_token_hash: str | None = None,
) -> str:
    """Persist aggregate results and return a stable public audit ID.

    ``access_token_hash`` is the SHA-256 digest of the audit's per-record
    access token (see :mod:`chaoshire.audit_access`); the token itself is
    never stored. ``None`` leaves the record operator-only.
    """
    if _postgres_active():
        from .repository_postgres import save_audit as _pg_save

        return _pg_save(result, name, configuration, source, access_token_hash=access_token_hash)
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
                configuration_json, result_json, access_token_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                access_token_hash,
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
            # Metadata only: the detail record requires the operator key or
            # this audit's access token (see chaoshire.audit_access).
            "access_required": True,
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


def audit_access_digest(audit_id: str) -> str | None:
    """Stored token digest for one audit, or ``None`` when unset/missing."""
    if _postgres_active():
        from .repository_postgres import audit_access_digest as _pg_digest

        return _pg_digest(audit_id)
    initialise_database()
    with connect() as connection:
        row = connection.execute(
            "SELECT access_token_hash FROM audit_runs WHERE id = ?", (audit_id,)
        ).fetchone()
    return str(row["access_token_hash"]) if row and row["access_token_hash"] else None


def verify_audit_access(audit_id: str, token: str | None) -> bool:
    """Whether ``token`` is the access token issued for ``audit_id``."""
    from .audit_access import audit_access_token_matches

    return audit_access_token_matches(audit_access_digest(audit_id), token)
