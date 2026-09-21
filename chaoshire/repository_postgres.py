"""Optional PostgreSQL repository adapter for durable cloud history.

Activated by setting ``CHAOSHIRE_DB_BACKEND=postgres`` together with
``CHAOSHIRE_DATABASE_URL`` (a psycopg-style connection string). When these
are absent, the default SQLite repository in :mod:`chaoshire.repository` is
used — SQLite stays the zero-config default for local runs, tests, and the
free-tier Render deployment.

The adapter implements the same interface as :mod:`chaoshire.repository`
(``initialise_database``, ``save_audit``, ``list_audits``, ``get_audit``),
so the route layer is backend-agnostic. ``psycopg2`` is imported lazily so
the dependency is only required on deployments that opt in.

Schema compatibility
--------------------
The PostgreSQL table mirrors the SQLite schema exactly: same columns, same
types (text for timestamps, JSON stored as ``TEXT``), same index. Aggregate
evidence produced by either backend is byte-identical.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def database_url() -> str | None:
    """Return the configured connection string, or ``None`` when unset."""
    raw = (os.getenv("CHAOSHIRE_DATABASE_URL") or "").strip()
    return raw or None


def postgres_enabled() -> bool:
    """Whether the operator opted into the PostgreSQL adapter."""
    return (os.getenv("CHAOSHIRE_DB_BACKEND") or "").strip().lower() == "postgres"


def _require_psycopg2():
    """Lazy import so SQLite-only deployments never need psycopg2."""
    try:
        import psycopg2  # type: ignore[import-untyped]
        import psycopg2.extras  # type: ignore[import-untyped]

        return psycopg2, psycopg2.extras
    except ImportError as error:  # pragma: no cover - exercised only with postgres backend
        raise RuntimeError(
            "CHAOSHIRE_DB_BACKEND=postgres requires psycopg2; install psycopg2-binary."
        ) from error


@contextmanager
def connect() -> Iterator[Any]:
    """Yield a psycopg2 connection with autocommit off; roll back on error."""
    psycopg2, _ = _require_psycopg2()
    url = database_url()
    if not url:
        raise RuntimeError(
            "CHAOSHIRE_DB_BACKEND=postgres requires CHAOSHIRE_DATABASE_URL to be set."
        )
    connection = psycopg2.connect(url)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialise_database() -> None:
    """Create the audit_runs table if it does not exist."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
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
            cursor.execute(
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
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_runs (
                    id, name, created_at, source, row_count, accepted_count,
                    certificate_score, certificate_grade, protected_attributes,
                    configuration_json, result_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, created_at, source, row_count, accepted_count,
                       certificate_score, certificate_grade, protected_attributes
                FROM audit_runs
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            rows = cursor.fetchall()
    return [
        {
            "audit_id": row[0],
            "name": row[1],
            "created_at": row[2],
            "source": row[3],
            "candidates": row[4],
            "accepted": row[5],
            "certificate": {"total": row[6], "grade": row[7]},
            "protected_attributes": json.loads(row[8]),
        }
        for row in rows
    ]


def get_audit(audit_id: str) -> dict[str, Any] | None:
    initialise_database()
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT result_json FROM audit_runs WHERE id = %s", (audit_id,))
            row = cursor.fetchone()
    return json.loads(row[0]) if row else None
