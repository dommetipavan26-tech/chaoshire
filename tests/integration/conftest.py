"""Opt-in database tests touch only a random schema on an explicit local test service."""

import os
from uuid import uuid4

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--require-postgres",
        action="store_true",
        help="fail rather than skip without a test service",
    )


@pytest.fixture
def postgres_schema(monkeypatch, request):
    url = os.getenv("CHAOSHIRE_TEST_POSTGRES_URL")
    if not url:
        if request.config.getoption("--require-postgres"):
            pytest.fail("Set CHAOSHIRE_TEST_POSTGRES_URL to a disposable local service.")
        pytest.skip("Optional PostgreSQL integration service is not configured")
    try:
        import psycopg2
        from psycopg2 import sql
        from psycopg2.extensions import make_dsn, parse_dsn
    except ImportError:
        pytest.fail("Install requirements-postgres.txt before integration tests.")
    params = parse_dsn(url)
    host = params.get("host", "")
    # Never fall back to the application's production DSN. CI maps its service
    # to loopback; the local audit uses a private Unix socket.
    if host not in {"localhost", "127.0.0.1", "::1"} and not host.startswith("/"):
        pytest.fail("Integration tests refuse nonlocal PostgreSQL hosts.")
    schema = "chaoshire_test_" + uuid4().hex
    connection = psycopg2.connect(url, connect_timeout=5)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        isolated = make_dsn(url, options=f"-c search_path={schema}")
        monkeypatch.setenv("CHAOSHIRE_DB_BACKEND", "postgres")
        monkeypatch.setenv("CHAOSHIRE_DATABASE_URL", isolated)
        yield schema, isolated
    finally:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        connection.close()
