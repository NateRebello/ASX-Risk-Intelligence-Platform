"""Step 10 — ingestion run metadata builders and persistence."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from src.ingestion.run_metadata import (
    build_macro_metadata,
    build_yahoo_metadata,
    persist_run_metadata,
    universe_identity,
)
from src.ingestion.yahoo_loader import LoadResult


def test_universe_identity_from_explicit_path(tmp_path):
    path = tmp_path / "custom_universe.csv"
    path.write_text("ticker,name,sector,industry\nCBA,CBA,Financials,Banks\n", encoding="utf-8")
    name, version = universe_identity(str(path))
    assert name == "custom_universe"
    assert version == "custom_universe.csv"


def test_universe_identity_default_filename(monkeypatch):
    from src.ingestion import run_metadata as meta

    monkeypatch.setattr(meta, "resolve_active_filename", lambda: "asx50.csv")
    name, version = universe_identity("")
    assert name == "asx50"
    assert version == "asx50.csv"


def test_build_yahoo_metadata_counts_and_status():
    results = [
        LoadResult("CBA", 10, "success"),
        LoadResult("BHP", 0, "empty"),
        LoadResult("RIO", 0, "error", "timeout"),
    ]
    meta = build_yahoo_metadata(
        results=results,
        total_rows=10,
        period="5y",
        start=None,
        end=None,
        tickers_file="",
        duration_ms=1234,
        min_date=date(2025, 1, 1),
        max_date=date(2026, 1, 1),
    )
    assert meta.source == "yahoo"
    assert meta.status == "partial"
    assert meta.tickers_attempted == 3
    assert meta.tickers_succeeded == 1
    assert meta.tickers_failed == 1
    assert meta.rows_written == 10
    assert meta.duration_ms == 1234
    assert meta.min_date == date(2025, 1, 1)
    assert meta.max_date == date(2026, 1, 1)
    assert "RIO" in meta.detail


def test_build_yahoo_metadata_date_range_period_label():
    results = [LoadResult("CBA", 5, "success")]
    meta = build_yahoo_metadata(
        results=results,
        total_rows=5,
        period="5y",
        start="2024-01-01",
        end="2024-06-30",
        tickers_file="",
        duration_ms=10,
        min_date=None,
        max_date=None,
    )
    assert meta.period == "2024-01-01..2024-06-30"
    assert meta.status == "success"


def test_build_macro_metadata_failed_when_zero_rows():
    meta = build_macro_metadata(
        rows_written=0,
        period="1mo",
        duration_ms=50,
        min_date=None,
        max_date=None,
        sources_ok=[],
        sources_failed=["cash_rate", "cpi"],
    )
    assert meta.source == "macro"
    assert meta.status == "failed"


@pytest.mark.integration
def test_persist_run_metadata_round_trip(db_engine, monkeypatch):
    from src.ingestion import run_metadata as meta_mod

    monkeypatch.setattr(meta_mod, "resolve_active_filename", lambda: "asx50.csv")
    metadata = build_yahoo_metadata(
        results=[SimpleNamespace(ticker="CBA", status="success", rows=2)],
        total_rows=2,
        period="5d",
        start=None,
        end=None,
        tickers_file="",
        duration_ms=42,
        min_date=date(2026, 7, 1),
        max_date=date(2026, 7, 5),
    )
    row_id = persist_run_metadata(db_engine, metadata)
    assert row_id > 0

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT source, status, rows_written, universe_name, universe_version,
                       period, tickers_attempted, tickers_succeeded, tickers_failed,
                       min_date, max_date, duration_ms
                FROM ingestion_log WHERE id = :id
                """
            ),
            {"id": row_id},
        ).one()

    assert row.source == "yahoo"
    assert row.status == "success"
    assert row.rows_written == 2
    assert row.universe_name == "asx50"
    assert row.universe_version == "asx50.csv"
    assert row.period == "5d"
    assert row.tickers_attempted == 1
    assert row.tickers_succeeded == 1
    assert row.tickers_failed == 0
    assert row.min_date == date(2026, 7, 1)
    assert row.max_date == date(2026, 7, 5)
    assert row.duration_ms == 42
