"""Shared pytest fixtures.

Integration tests that need Postgres use the `db_engine` fixture. CI provides
a service container (see `.github/workflows/ci.yml`); local docker-compose
Postgres also works when `DB_*` / `DB_SSLMODE=disable` are set.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import URL

from config import settings
from src.db.engine import get_engine, reset_engine, run_migrations

# Tables touched by ingestion integration tests — truncated between tests.
_INGESTION_TABLES = (
    "ingestion_log",
    "daily_prices",
    "stocks",
    "macro",
)

_TEST_DB_NAME = "asx_risk_test"


def pytest_configure(config):  # noqa: ARG001
    config.addinivalue_line("markers", "integration: requires a reachable PostgreSQL instance")


def _ensure_test_database() -> None:
    """Create `asx_risk_test` on the local server if it does not already exist.

    CI creates it via the Postgres service env; local docker-compose only
    provisions `asx_risk`, so integration tests would otherwise hit the
    developer database and TRUNCATE real rows.
    """
    admin_url = URL.create(
        "postgresql+psycopg2",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database="postgres",
    )
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", connect_args={"sslmode": "disable"})
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": _TEST_DB_NAME},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{_TEST_DB_NAME}"'))
    finally:
        admin.dispose()


@pytest.fixture
def db_engine(monkeypatch) -> Engine:
    """Ephemeral-feeling Postgres: migrate schema, truncate tables, yield engine.

    Skips cleanly when Postgres is unreachable so unit-only runs still pass
    without Docker. Forces `sslmode=disable` and database `asx_risk_test`
    because CI/local containers do not present TLS certificates and so that
    local demo data in `asx_risk` is never truncated.
    """
    monkeypatch.setattr(settings, "DB_SSLMODE", "disable")
    monkeypatch.setattr(settings, "DB_SECRET_ARN", "")
    monkeypatch.setattr(settings, "DB_NAME", _TEST_DB_NAME)
    reset_engine()

    try:
        _ensure_test_database()
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        reset_engine()
        pytest.skip(f"PostgreSQL unavailable for integration tests: {exc}")

    run_migrations(sql_dir="sql")

    with engine.begin() as conn:
        for table in _INGESTION_TABLES:
            conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))

    yield engine

    reset_engine()
