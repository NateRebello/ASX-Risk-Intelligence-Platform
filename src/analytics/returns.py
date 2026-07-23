"""
Milestone 2 — Daily/log returns computation.

Pure functions operate on plain pandas DataFrames/Series so they're trivial
to unit test; `run()` wires them up to the database for the real pipeline.
"""

from __future__ import annotations

import logging
import sys

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.db.engine import get_engine
from src.processing.cleaning import clean_prices

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def compute_daily_returns(prices: pd.Series) -> pd.Series:
    """Simple percentage return: (P_t / P_{t-1}) - 1.

    >>> import pandas as pd
    >>> round(compute_daily_returns(pd.Series([100, 110])).iloc[-1], 4)
    0.1
    """
    return prices.pct_change()


def compute_log_returns(prices: pd.Series) -> pd.Series:
    """Log return: ln(P_t / P_{t-1})."""
    return np.log(prices / prices.shift(1))


def compute_returns_frame(df: pd.DataFrame, price_col: str = "adj_close") -> pd.DataFrame:
    """Given a long-format DataFrame with columns [date, ticker, <price_col>],
    return a DataFrame with columns [date, ticker, daily_return, log_return].
    """
    df = df.sort_values(["ticker", "date"]).copy()
    df["daily_return"] = df.groupby("ticker")[price_col].transform(compute_daily_returns)
    df["log_return"] = df.groupby("ticker")[price_col].transform(compute_log_returns)
    return df[["date", "ticker", "daily_return", "log_return"]]


def load_prices(engine: Engine, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    query = "SELECT date, ticker, open, high, low, close, adj_close, volume FROM daily_prices"
    conditions = []
    params: dict[str, str] = {}
    if start:
        conditions.append("date >= :start")
        params["start"] = start
    if end:
        conditions.append("date <= :end")
        params["end"] = end
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY ticker, date"
    return pd.read_sql(text(query), engine, params=params)


def upsert_returns(engine: Engine, returns_df: pd.DataFrame) -> int:
    returns_df = returns_df.dropna(subset=["daily_return"])
    if returns_df.empty:
        return 0
    records = returns_df.where(pd.notna(returns_df), None).to_dict("records")
    stmt = text("""
        INSERT INTO returns (date, ticker, daily_return, log_return)
        VALUES (:date, :ticker, :daily_return, :log_return)
        ON CONFLICT (date, ticker) DO UPDATE SET
            daily_return = EXCLUDED.daily_return,
            log_return = EXCLUDED.log_return
        """)
    with engine.begin() as conn:
        conn.execute(stmt, records)
    return len(records)


def run(start: str | None = None, end: str | None = None) -> int:
    engine = get_engine()
    raw = load_prices(engine, start=start, end=end)
    if raw.empty:
        logger.warning("No prices found for the requested window; nothing to compute")
        return 0
    cleaned = clean_prices(raw)
    returns_df = compute_returns_frame(cleaned)
    n = upsert_returns(engine, returns_df)
    logger.info("Upserted %d return rows", n)
    return n


def lambda_handler(event: dict, context) -> dict:  # noqa: ANN001
    start = (event or {}).get("start")
    end = (event or {}).get("end")
    n = run(start=start, end=end)
    return {"statusCode": 200, "rows_written": n}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Compute daily/log returns from daily_prices")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args(argv)
    run(start=args.start, end=args.end)
    return 0


if __name__ == "__main__":
    sys.exit(main())
