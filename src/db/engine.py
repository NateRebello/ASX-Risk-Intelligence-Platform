"""
Database connectivity helpers shared across ingestion/analytics/reporting.

Centralizes the SQLAlchemy engine construction and a small retry wrapper so
transient connection errors (e.g. RDS cold-starts, brief network blips) are
handled gracefully instead of crashing the whole pipeline.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

import boto3
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import URL
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

_engine: Engine | None = None


def _database_password() -> str:
    """Resolve the DB password locally or from Secrets Manager at runtime."""
    if not settings.DB_SECRET_ARN:
        return settings.DB_PASSWORD

    response = boto3.client("secretsmanager", region_name=settings.AWS_REGION).get_secret_value(
        SecretId=settings.DB_SECRET_ARN
    )
    secret = response["SecretString"]
    if secret.lstrip().startswith("{"):
        import json

        payload = json.loads(secret)
        return payload["password"]
    return secret


def database_url() -> URL:
    """Build a URL safely so special characters in passwords are escaped."""
    return URL.create(
        "postgresql+psycopg2",
        username=settings.DB_USER,
        password=_database_password(),
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=settings.DB_NAME,
    )


def get_engine(url: str | None = None) -> Engine:
    """Return a process-wide singleton SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(url or database_url(), pool_pre_ping=True, future=True)
    return _engine


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
)
def connect_with_retry(engine: Engine | None = None):
    """Open a connection, retrying with exponential backoff on failure."""
    engine = engine or get_engine()
    return engine.connect()


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    engine = engine or get_engine()
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Session rolled back due to an error")
        raise
    finally:
        session.close()


def run_migrations(sql_dir: str = "sql") -> None:
    """Apply schema.sql (and views.sql, if present) idempotently."""
    import pathlib

    engine = get_engine()
    base = pathlib.Path(sql_dir)
    for filename in ("schema.sql", "views.sql"):
        path = base / filename
        if not path.exists():
            continue
        sql_text = path.read_text(encoding="utf-8")
        with engine.begin() as conn:
            for statement in _split_statements(sql_text):
                if statement.strip():
                    conn.exec_driver_sql(statement)
        logger.info("Applied %s", path)


def _split_statements(sql_text: str) -> list[str]:
    """Naive statement splitter on semicolons (schema files have no
    semicolons inside string literals, so this is safe here)."""
    return [s.strip() for s in sql_text.split(";") if s.strip()]
