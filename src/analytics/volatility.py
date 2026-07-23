"""
Milestone 2 — Rolling volatility, Sharpe ratio, and max drawdown.
"""

from __future__ import annotations

import logging
import sys

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from config import settings
from src.db.engine import get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def compute_rolling_vol(
    returns: pd.Series,
    window: int = settings.ROLLING_VOL_WINDOW,
    annualize: bool = True,
    trading_days: int = settings.TRADING_DAYS_PER_YEAR,
) -> pd.Series:
    """Rolling standard deviation of returns, optionally annualized.

    >>> import numpy as np, pandas as pd
    >>> r = pd.Series(np.zeros(40))
    >>> compute_rolling_vol(r, window=10).iloc[-1]
    0.0
    """
    vol = returns.rolling(window=window, min_periods=window).std()
    if annualize:
        vol = vol * np.sqrt(trading_days)
    return vol


def compute_sharpe(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    trading_days: int = settings.TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualized Sharpe ratio for a return series (risk_free_rate is annualized)."""
    excess = returns - (risk_free_rate / trading_days)
    std = excess.std()
    if std == 0 or np.isnan(std):
        return float("nan")
    return float(excess.mean() / std * np.sqrt(trading_days))


def compute_max_drawdown(prices_or_cumret: pd.Series) -> float:
    """Maximum peak-to-trough drawdown (negative fraction, e.g. -0.35 = -35%)."""
    running_max = prices_or_cumret.cummax()
    drawdown = prices_or_cumret / running_max - 1.0
    return float(drawdown.min())


def compute_cumulative_returns(returns: pd.Series) -> pd.Series:
    return (1.0 + returns.fillna(0)).cumprod()


def compute_volatility_frame(
    returns_df: pd.DataFrame,
    window: int = settings.ROLLING_VOL_WINDOW,
) -> pd.DataFrame:
    """Given [date, ticker, daily_return], return [date, ticker, rolling_vol]."""
    df = returns_df.sort_values(["ticker", "date"]).copy()
    df["rolling_vol"] = df.groupby("ticker")["daily_return"].transform(lambda s: compute_rolling_vol(s, window=window))
    return df[["date", "ticker", "rolling_vol"]]


def load_returns(engine: Engine, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    query = "SELECT date, ticker, daily_return FROM returns"
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


def upsert_volatility(engine: Engine, vol_df: pd.DataFrame) -> int:
    vol_df = vol_df.dropna(subset=["rolling_vol"])
    if vol_df.empty:
        return 0
    records = vol_df.where(pd.notna(vol_df), None).to_dict("records")
    stmt = text("""
        INSERT INTO volatility (date, ticker, rolling_vol)
        VALUES (:date, :ticker, :rolling_vol)
        ON CONFLICT (date, ticker) DO UPDATE SET
            rolling_vol = EXCLUDED.rolling_vol
        """)
    with engine.begin() as conn:
        conn.execute(stmt, records)
    return len(records)


def run(window: int = settings.ROLLING_VOL_WINDOW, start: str | None = None, end: str | None = None) -> int:
    engine = get_engine()
    returns_df = load_returns(engine, start=start, end=end)
    if returns_df.empty:
        logger.warning("No returns found; nothing to compute")
        return 0
    vol_df = compute_volatility_frame(returns_df, window=window)
    n = upsert_volatility(engine, vol_df)
    logger.info("Upserted %d volatility rows", n)
    return n


def lambda_handler(event: dict, context) -> dict:  # noqa: ANN001
    n = run()
    return {"statusCode": 200, "rows_written": n}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Compute rolling volatility from returns")
    parser.add_argument("--window", type=int, default=settings.ROLLING_VOL_WINDOW)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args(argv)
    run(window=args.window, start=args.start, end=args.end)
    return 0


if __name__ == "__main__":
    sys.exit(main())
