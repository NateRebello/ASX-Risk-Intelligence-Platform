"""Controlled database-schema migration Lambda entry point.

The daily Step Functions execution skips this task by default. Operators can
start an execution with ``{"runMigrations": true}`` during deployment, after
reviewing the idempotent SQL files packaged into the image.
"""

from __future__ import annotations

from src.db.engine import run_migrations


def lambda_handler(event: dict, context) -> dict:  # noqa: ANN001
    run_migrations()
    return {"statusCode": 200, "message": "schema and views applied"}
