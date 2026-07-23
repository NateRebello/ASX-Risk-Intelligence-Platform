"""
Milestone 4 — Risk attribution: decompose portfolio risk into per-asset and
per-sector contributions.

Uses the standard Euler decomposition of portfolio volatility, which is
exact (not an approximation) for a homogeneous risk measure like variance:

    sigma_p = w' Sigma w  ==>  MCTR_i = w_i * (Sigma w)_i / sigma_p
    sum_i MCTR_i = sigma_p   (by Euler's theorem, since variance is
                              homogeneous of degree 1 in weights via vol)

VaR/CVaR contributions are then allocated *proportionally* to each asset's
share of total variance risk — an approximation that is exact under the
parametric (Gaussian) VaR model and a reasonable, widely-used
linear-attribution approximation otherwise.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.portfolio.optimizer import Portfolio, portfolio_volatility


def asset_risk_contributions(portfolio: Portfolio, cov_matrix: pd.DataFrame) -> pd.DataFrame:
    """Per-asset contribution to portfolio volatility.

    Returns columns: ticker, weight, marginal_contribution, pct_contribution.
    `marginal_contribution` values sum to the portfolio's total volatility.
    """
    tickers = [t for t in portfolio.tickers if t in cov_matrix.columns]
    sigma = cov_matrix.loc[tickers, tickers].values
    w = np.array([portfolio.weights[t] for t in tickers])

    port_vol = portfolio_volatility(w, sigma)
    if port_vol == 0:
        contributions = np.zeros_like(w)
    else:
        sigma_w = sigma @ w
        contributions = w * sigma_w / port_vol

    df = pd.DataFrame(
        {
            "ticker": tickers,
            "weight": w,
            "marginal_contribution": contributions,
        }
    )
    df["pct_contribution"] = (
        df["marginal_contribution"] / df["marginal_contribution"].sum()
        if df["marginal_contribution"].sum() != 0
        else 0.0
    )
    return df


def sector_risk_contributions(asset_contrib: pd.DataFrame, sector_map: dict[str, str]) -> pd.DataFrame:
    """Aggregate per-asset contributions up to the sector level.

    `sector_map`: ticker -> sector (e.g. from the `stocks` table).
    """
    df = asset_contrib.copy()
    df["sector"] = df["ticker"].map(sector_map).fillna("Unknown")
    grouped = (
        df.groupby("sector")
        .agg(
            weight=("weight", "sum"),
            marginal_contribution=("marginal_contribution", "sum"),
            pct_contribution=("pct_contribution", "sum"),
        )
        .reset_index()
    )
    return grouped.sort_values("pct_contribution", ascending=False).reset_index(drop=True)


def attribute_var(asset_contrib: pd.DataFrame, var_total: float) -> pd.DataFrame:
    """Allocate total portfolio VaR (or CVaR) across assets proportionally
    to each asset's share of total variance risk (`pct_contribution`)."""
    df = asset_contrib.copy()
    df["var_contribution"] = df["pct_contribution"] * var_total
    return df


def load_sector_map(engine: Engine, tickers: list[str] | None = None) -> dict[str, str]:
    query = "SELECT ticker, sector FROM stocks"
    params = {}
    if tickers:
        query += " WHERE ticker = ANY(:tickers)"
        params["tickers"] = tickers
    df = pd.read_sql(text(query), engine, params=params)
    return dict(zip(df["ticker"], df["sector"]))


def save_sector_contributions(engine: Engine, portfolio_id: int, date: str, sector_df: pd.DataFrame) -> int:
    if sector_df.empty:
        return 0
    records = [
        {
            "pid": portfolio_id,
            "date": date,
            "sector": row.sector,
            "weight": float(row.weight),
            "pct": float(row.pct_contribution) * 100.0,
        }
        for row in sector_df.itertuples(index=False)
    ]
    stmt = text("""
        INSERT INTO sector_risk_contributions (portfolio_id, date, sector, weight, risk_contribution_pct)
        VALUES (:pid, :date, :sector, :weight, :pct)
        ON CONFLICT (portfolio_id, date, sector) DO UPDATE SET
            weight = EXCLUDED.weight, risk_contribution_pct = EXCLUDED.risk_contribution_pct
        """)
    with engine.begin() as conn:
        conn.execute(stmt, records)
    return len(records)
