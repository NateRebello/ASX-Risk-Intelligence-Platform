"""Step 8 — database integration tests for price and macro upserts.

Requires PostgreSQL (CI service container or local docker-compose). Marked
`integration` and skipped automatically when the DB is unreachable.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text

from src.ingestion.rba_loader import upsert_macro
from src.ingestion.yahoo_loader import upsert_prices, upsert_stocks

pytestmark = pytest.mark.integration


def _price_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": date(2026, 1, 2),
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 104.0,
                "adj_close": 104.0,
                "volume": 1_000_000,
            },
            {
                "date": date(2026, 1, 3),
                "open": 104.0,
                "high": 106.0,
                "low": 103.0,
                "close": 105.5,
                "adj_close": 105.5,
                "volume": 1_100_000,
            },
            {
                "date": date(2026, 1, 6),
                "open": 105.0,
                "high": 107.0,
                "low": 104.0,
                "close": 106.0,
                "adj_close": 106.0,
                "volume": 900_000,
            },
        ]
    )


def test_price_upsert_idempotent_and_ohlcv_non_null(db_engine):
    universe = [
        {"ticker": "CBA", "name": "Commonwealth Bank", "sector": "Financials", "industry": "Banks"},
        {"ticker": "BHP", "name": "BHP Group", "sector": "Materials", "industry": "Metals & Mining"},
    ]
    upsert_stocks(db_engine, universe)

    cba = _price_frame()
    bhp = _price_frame().assign(
        open=lambda d: d["open"] + 10,
        high=lambda d: d["high"] + 10,
        low=lambda d: d["low"] + 10,
        close=lambda d: d["close"] + 10,
        adj_close=lambda d: d["adj_close"] + 10,
    )

    assert upsert_prices(db_engine, "CBA", cba) == 3
    assert upsert_prices(db_engine, "BHP", bhp) == 3
    # Re-upsert identical rows — primary key conflict path must not duplicate.
    assert upsert_prices(db_engine, "CBA", cba) == 3

    with db_engine.connect() as conn:
        price_count = conn.execute(text("SELECT COUNT(*) FROM daily_prices")).scalar_one()
        cba_count = conn.execute(
            text("SELECT COUNT(*) FROM daily_prices WHERE ticker = 'CBA'")
        ).scalar_one()
        null_ohlcv = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM daily_prices
                WHERE open IS NULL OR high IS NULL OR low IS NULL
                   OR close IS NULL OR adj_close IS NULL OR volume IS NULL
                """
            )
        ).scalar_one()
        date_min, date_max = conn.execute(
            text("SELECT MIN(date), MAX(date) FROM daily_prices WHERE ticker = 'CBA'")
        ).one()

    assert price_count == 6
    assert cba_count == 3
    assert null_ohlcv == 0
    assert date_min == date(2026, 1, 2)
    assert date_max == date(2026, 1, 6)


def test_price_upsert_known_ticker_date_range_row_counts(db_engine):
    upsert_stocks(
        db_engine,
        [{"ticker": "WES", "name": "Wesfarmers", "sector": "Consumer Discretionary", "industry": "Retailing"}],
    )
    df = _price_frame().iloc[:2].copy()
    assert upsert_prices(db_engine, "WES", df) == 2

    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM daily_prices
                WHERE ticker = 'WES'
                  AND date BETWEEN DATE '2026-01-02' AND DATE '2026-01-03'
                """
            )
        ).scalar_one()
        outside = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM daily_prices
                WHERE ticker = 'WES' AND date = DATE '2026-01-06'
                """
            )
        ).scalar_one()

    assert rows == 2
    assert outside == 0


def test_macro_upsert_idempotent_and_coalesce(db_engine):
    first = pd.DataFrame(
        [
            {
                "date": date(2026, 1, 31),
                "cash_rate": 4.35,
                "cpi": None,
                "unemployment": None,
                "aud_usd": 0.66,
                "iron_ore_price": 110.0,
            },
            {
                "date": date(2026, 2, 28),
                "cash_rate": 4.35,
                "cpi": 3.2,
                "unemployment": None,
                "aud_usd": 0.65,
                "iron_ore_price": 112.0,
            },
        ]
    )
    assert upsert_macro(db_engine, first) == 2

    # Second pass fills previously-NULL CPI via COALESCE and must not duplicate rows.
    second = pd.DataFrame(
        [
            {
                "date": date(2026, 1, 31),
                "cash_rate": None,
                "cpi": 3.1,
                "unemployment": None,
                "aud_usd": None,
                "iron_ore_price": None,
            }
        ]
    )
    assert upsert_macro(db_engine, second) == 1

    with db_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM macro")).scalar_one()
        jan = conn.execute(
            text("SELECT cash_rate, cpi, aud_usd FROM macro WHERE date = DATE '2026-01-31'")
        ).one()

    assert count == 2
    assert float(jan.cash_rate) == pytest.approx(4.35)
    assert float(jan.cpi) == pytest.approx(3.1)
    assert float(jan.aud_usd) == pytest.approx(0.66)
