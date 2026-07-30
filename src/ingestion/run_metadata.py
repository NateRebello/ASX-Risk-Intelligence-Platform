"""Ingestion run metadata helpers (Milestone 1 / Step 10).

Captures universe identity, requested period, ticker success/failure counts,
row counts, observed date range, status, and wall-clock duration for each
ingestion run, and persists them to `ingestion_log`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.universe.loader import REPO_ROOT, UNIVERSE_DIR, resolve_active_filename


@dataclass
class IngestionRunMetadata:
    source: str
    status: str  # success | failed | partial
    rows_written: int = 0
    universe_name: str | None = None
    universe_version: str | None = None
    period: str | None = None
    tickers_attempted: int | None = None
    tickers_succeeded: int | None = None
    tickers_failed: int | None = None
    min_date: date | None = None
    max_date: date | None = None
    duration_ms: int | None = None
    detail: str = ""
    run_at: datetime | None = None

    def to_log_params(self) -> dict[str, Any]:
        """Flatten for SQLAlchemy named-parameter execute."""
        return {
            "source": self.source,
            "rows": self.rows_written,
            "status": self.status,
            "detail": (self.detail or "")[:500],
            "universe_name": self.universe_name,
            "universe_version": self.universe_version,
            "period": self.period,
            "tickers_attempted": self.tickers_attempted,
            "tickers_succeeded": self.tickers_succeeded,
            "tickers_failed": self.tickers_failed,
            "min_date": self.min_date,
            "max_date": self.max_date,
            "duration_ms": self.duration_ms,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.min_date is not None:
            payload["min_date"] = self.min_date.isoformat()
        if self.max_date is not None:
            payload["max_date"] = self.max_date.isoformat()
        if self.run_at is not None:
            payload["run_at"] = self.run_at.isoformat()
        return payload


def universe_identity(tickers_file: str = "", filename: str | None = None) -> tuple[str, str]:
    """Return (universe_name, universe_version) for the active config artifact.

    `universe_name` is the stem (e.g. ``asx50``). `universe_version` is the
    config filename (e.g. ``asx50.csv``), which is the versioned artifact id
    published under ``config/universes/``.
    """
    if tickers_file:
        path = Path(tickers_file)
        return path.stem, path.name

    active = filename or resolve_active_filename()
    return Path(active).stem, Path(active).name


def local_universe_path(filename: str) -> Path:
    """Path to a committed universe CSV (useful for tests / evidence)."""
    return UNIVERSE_DIR / filename if not Path(filename).is_absolute() else Path(filename)


def build_yahoo_metadata(
    *,
    results: list[Any],
    total_rows: int,
    period: str | None,
    start: str | None,
    end: str | None,
    tickers_file: str,
    duration_ms: int,
    min_date: date | None,
    max_date: date | None,
) -> IngestionRunMetadata:
    """Assemble Step 10 metadata from a yahoo_loader run."""
    attempted = len(results)
    succeeded = sum(1 for r in results if getattr(r, "status", None) == "success")
    failed = sum(1 for r in results if getattr(r, "status", None) == "error")
    empty = attempted - succeeded - failed

    if failed == 0:
        status = "success"
    elif succeeded == 0 and empty == 0:
        status = "failed"
    else:
        status = "partial"

    name, version = universe_identity(tickers_file)
    period_label = period
    if start or end:
        period_label = f"{start or ''}..{end or ''}"

    detail = {
        "empty_tickers": empty,
        "failed_tickers": [getattr(r, "ticker", "?") for r in results if getattr(r, "status", None) == "error"],
    }

    return IngestionRunMetadata(
        source="yahoo",
        status=status,
        rows_written=total_rows,
        universe_name=name,
        universe_version=version,
        period=period_label,
        tickers_attempted=attempted,
        tickers_succeeded=succeeded,
        tickers_failed=failed,
        min_date=min_date,
        max_date=max_date,
        duration_ms=duration_ms,
        detail=json.dumps(detail, default=str),
        run_at=datetime.now(timezone.utc),
    )


def build_macro_metadata(
    *,
    rows_written: int,
    period: str,
    duration_ms: int,
    min_date: date | None,
    max_date: date | None,
    sources_ok: list[str],
    sources_failed: list[str],
) -> IngestionRunMetadata:
    """Assemble Step 10 metadata from a macro (rba_loader) run."""
    if rows_written <= 0:
        status = "failed"
    elif sources_failed:
        status = "partial"
    else:
        status = "success"

    detail = {"sources_ok": sources_ok, "sources_failed": sources_failed}
    return IngestionRunMetadata(
        source="macro",
        status=status,
        rows_written=rows_written,
        period=period,
        min_date=min_date,
        max_date=max_date,
        duration_ms=duration_ms,
        detail=json.dumps(detail),
        run_at=datetime.now(timezone.utc),
    )


_INSERT_STMT = text("""
    INSERT INTO ingestion_log (
        source, rows_written, status, detail,
        universe_name, universe_version, period,
        tickers_attempted, tickers_succeeded, tickers_failed,
        min_date, max_date, duration_ms
    )
    VALUES (
        :source, :rows, :status, :detail,
        :universe_name, :universe_version, :period,
        :tickers_attempted, :tickers_succeeded, :tickers_failed,
        :min_date, :max_date, :duration_ms
    )
    RETURNING id
""")


def persist_run_metadata(engine: Engine, metadata: IngestionRunMetadata) -> int:
    """Insert one ingestion_log row; return the new id."""
    with engine.begin() as conn:
        row = conn.execute(_INSERT_STMT, metadata.to_log_params()).one()
    return int(row[0])


def project_root() -> Path:
    return REPO_ROOT
