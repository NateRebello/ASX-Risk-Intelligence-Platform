"""
Milestone 2 — Covariance / correlation estimation with Ledoit-Wolf shrinkage.
"""

from __future__ import annotations

import logging

import pandas as pd
from sklearn.covariance import LedoitWolf
from sqlalchemy import text
from sqlalchemy.engine import Engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def pivot_returns(returns_df: pd.DataFrame, value_col: str = "daily_return") -> pd.DataFrame:
    """Long [date, ticker, daily_return] -> wide DataFrame indexed by date,
    one column per ticker."""
    wide = returns_df.pivot(index="date", columns="ticker", values=value_col)
    return wide.sort_index()


def compute_correlation_matrix(returns_wide: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation matrix across tickers (pairwise-complete)."""
    return returns_wide.corr()


def compute_covariance_matrix(
    returns_wide: pd.DataFrame, annualize: bool = False, trading_days: int = 252
) -> pd.DataFrame:
    """Sample covariance matrix across tickers (pairwise-complete)."""
    cov = returns_wide.cov()
    if annualize:
        cov = cov * trading_days
    return cov


def compute_shrunk_covariance(
    returns_wide: pd.DataFrame, annualize: bool = False, trading_days: int = 252
) -> tuple[pd.DataFrame, float]:
    """Ledoit-Wolf shrinkage covariance estimator.

    Rows with any NaN are dropped (LedoitWolf requires a complete matrix).
    Returns (covariance_dataframe, shrinkage_coefficient).
    """
    clean = returns_wide.dropna(axis=0, how="any")
    if clean.shape[0] < 2 or clean.shape[1] < 2:
        raise ValueError("Not enough overlapping observations to estimate covariance")

    lw = LedoitWolf().fit(clean.values)
    cov = lw.covariance_
    if annualize:
        cov = cov * trading_days
    cov_df = pd.DataFrame(cov, index=clean.columns, columns=clean.columns)
    return cov_df, float(lw.shrinkage_)


def load_returns_wide(engine: Engine, start: str | None = None, end: str | None = None) -> pd.DataFrame:
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
    df = pd.read_sql(text(query), engine, params=params)
    return pivot_returns(df)


def main(argv: list[str] | None = None) -> int:
    import argparse

    from src.db.engine import get_engine

    parser = argparse.ArgumentParser(description="Compute shrunk covariance/correlation matrices")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args(argv)

    engine = get_engine()
    wide = load_returns_wide(engine, start=args.start, end=args.end)
    corr = compute_correlation_matrix(wide)
    cov, shrinkage = compute_shrunk_covariance(wide, annualize=True)
    logger.info("Correlation matrix shape=%s, shrinkage=%.4f", corr.shape, shrinkage)
    print(cov)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
