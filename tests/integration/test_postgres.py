"""Service-backed schema, transactional, dispatcher, and HTTP readiness verification."""

import copy
import os

import pytest
from fastapi.testclient import TestClient

from chaoshire import repository as repo
from chaoshire import repository_postgres as pg
from chaoshire.app import app

pytestmark = pytest.mark.postgres

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # Fixture fails/skips explicitly before any test accesses it.


def sample_result():
    return {
        "stats": {"candidates": 80, "accepted": 40},
        "certificate": {"total": 80, "grade": "B"},
        "attributes": [{"attribute": "gender", "groups": [{"group": "Équipe"}]}],
    }


CONFIG = {"protected_attributes": ["gender"], "minimum_group_size": 30}


def operator_client():
    client = TestClient(app)
    client.headers["X-API-Key"] = os.environ["CHAOSHIRE_API_KEY"]
    return client


def test_schema_and_index_are_idempotent_and_isolated(postgres_schema):
    schema, url = postgres_schema
    repo.initialise_database()
    repo.initialise_database()
    with psycopg2.connect(url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name='audit_runs'",
            (schema,),
        )
        columns = {row[0] for row in cursor.fetchall()}
        assert columns == {
            "id",
            "name",
            "created_at",
            "source",
            "row_count",
            "accepted_count",
            "certificate_score",
            "certificate_grade",
            "protected_attributes",
            "configuration_json",
            "result_json",
        }
        cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname=%s", (schema,))
        assert "idx_audit_runs_created_at" in {row[0] for row in cursor.fetchall()}


def test_aggregate_unicode_round_trip_uses_actual_driver_and_dispatcher(postgres_schema):
    result = sample_result()
    identifier = repo.save_audit(result, "Audit Équipe", CONFIG)
    stored = repo.get_audit(identifier)
    assert stored == result
    assert stored["audit_name"] == "Audit Équipe"
    listing = repo.list_audits()
    assert listing[0]["audit_id"] == identifier
    assert listing[0]["protected_attributes"] == ["gender"]
    assert "candidate_id" not in listing[0]
    assert repo.get_audit("not-found") is None


def test_listing_limits_order_and_parameterized_identifier(postgres_schema):
    ids = [pg.save_audit(sample_result(), f"Synthetic {i}", CONFIG) for i in range(3)]
    assert [row["audit_id"] for row in pg.list_audits(3)] == ids[::-1]
    assert len(pg.list_audits(0)) == 1
    assert len(pg.list_audits(1000)) == 3
    assert pg.get_audit("'; DROP TABLE audit_runs; --") is None
    assert len(pg.list_audits()) == 3


def test_connection_commits_closes_and_changes_are_visible_to_a_new_connection(postgres_schema):
    repo.initialise_database()
    with pg.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE commit_probe (value INTEGER)")
            cursor.execute("INSERT INTO commit_probe VALUES (%s)", (7,))
    assert connection.closed
    with pg.connect() as another, another.cursor() as cursor:
        cursor.execute("SELECT value FROM commit_probe")
        assert cursor.fetchone() == (7,)


def test_connection_rolls_back_and_closes_on_application_exception(postgres_schema):
    with pg.connect() as connection, connection.cursor() as cursor:
        cursor.execute("CREATE TABLE rollback_probe (value INTEGER)")
    with pytest.raises(RuntimeError):
        with pg.connect() as failed, failed.cursor() as cursor:
            cursor.execute("INSERT INTO rollback_probe VALUES (%s)", (9,))
            raise RuntimeError("synthetic rollback")
    assert failed.closed
    with pg.connect() as another, another.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM rollback_probe")
        assert cursor.fetchone() == (0,)


def test_constraint_failure_leaves_repository_usable(postgres_schema):
    malformed = copy.deepcopy(sample_result())
    malformed["stats"]["candidates"] = None
    with pytest.raises(psycopg2.IntegrityError):
        pg.save_audit(malformed, "Synthetic invalid", CONFIG)
    identifier = pg.save_audit(sample_result(), "Synthetic valid", CONFIG)
    assert pg.get_audit(identifier)["stats"]["candidates"] == 80
    assert len(pg.list_audits()) == 1


def test_new_connection_sees_published_history_and_api_readiness(postgres_schema):
    identifier = repo.save_audit(sample_result(), "Service-backed synthetic", CONFIG)
    with TestClient(app) as client:
        assert client.get("/api/ready").status_code == 200
        assert client.get("/api/meta").json()["build"]["repository_backend"] == "postgres"
        assert client.get(f"/api/audits/{identifier}").json()["audit_id"] == identifier
        assert client.get("/api/audits").json()["audits"][0]["audit_id"] == identifier
    assert repo.get_audit(identifier) is not None


def test_authenticated_upload_publishes_only_aggregates_to_postgres(postgres_schema):
    text = "candidate_id,gender,decision,qualified\n" + "\n".join(
        f"FAKE-{i},{'F' if i < 40 else 'M'},{i % 2},true" for i in range(80)
    )
    response = operator_client().post(
        "/api/upload",
        json={
            "csv": text,
            "audit_name": "Synthetic PG integration",
            "protected_attributes": ["gender"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["published"] is True
    stored = repo.get_audit(payload["audit_id"])
    assert stored["stats"]["candidates"] == 80
    assert "FAKE-" not in str(stored)


def test_anonymous_upload_never_creates_database_history(postgres_schema):
    text = "gender,decision\nF,1\nM,0\n"
    response = TestClient(app).post(
        "/api/upload",
        json={
            "csv": text,
            "audit_name": "Synthetic unpublished",
            "protected_attributes": ["gender"],
        },
    )
    assert response.status_code == 200
    assert response.json()["published"] is False
    assert repo.list_audits() == []
