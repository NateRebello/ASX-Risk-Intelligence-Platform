"""
Milestone 5 — Macro overlay: relate RBA/ABS/AUD/commodity series to ASX
volatility.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

MACRO_COLUMNS = ("cash_rate", "cpi", "unemployment", "aud_usd", "iron_ore_price")


def merge_vol_with_macro(vol_df: pd.DataFrame, macro_df: pd.DataFrame) -> pd.DataFrame:
    """Left-join daily volatility observations with macro series on date.

    Macro series are typically lower frequency (monthly/quarterly), so this
    performs an as-of forward-fill: each trading day picks up the most
    recently published macro value.
    """
    vol_df = vol_df.copy()
    macro_df = macro_df.copy()
    # merge_asof requires a proper datetime64 dtype on both sides — the
    # `date` column often comes back as plain python `date` objects
    # (dtype=object) from a SQL driver, which merge_asof rejects outright.
    vol_df["date"] = pd.to_datetime(vol_df["date"])
    macro_df["date"] = pd.to_datetime(macro_df["date"])
    vol_df = vol_df.sort_values("date")
    macro_df = macro_df.sort_values("date")
    merged = pd.merge_asof(vol_df, macro_df, on="date", direction="backward")
    return merged


def correlation_with_macro(merged: pd.DataFrame, vol_col: str = "rolling_vol") -> pd.Series:
    """Correlation of volatility with each available macro series."""
    cols = [c for c in MACRO_COLUMNS if c in merged.columns]
    return merged[[vol_col] + cols].corr()[vol_col].drop(vol_col).sort_values(ascending=False)


def detect_rate_change_events(macro_df: pd.DataFrame) -> pd.DataFrame:
    """Identify dates where the RBA cash rate changed from the prior
    observation. Returns [date, cash_rate, change]."""
    df = macro_df.sort_values("date").copy()
    df["change"] = df["cash_rate"].diff()
    events = df.loc[df["change"].fillna(0) != 0, ["date", "cash_rate", "change"]]
    return events.reset_index(drop=True)


def volatility_around_events(
    vol_df: pd.DataFrame,
    event_dates: pd.Series,
    window: int = 5,
    vol_col: str = "rolling_vol",
) -> pd.DataFrame:
    """For each event date, compute average volatility in the `window` days
    before vs after the event (e.g. RBA rate decisions)."""
    vol_df = vol_df.sort_values("date").reset_index(drop=True)
    dates = pd.to_datetime(vol_df["date"])
    rows = []
    for event in pd.to_datetime(event_dates):
        before_mask = (dates < event) & (dates >= event - pd.Timedelta(days=window * 2))
        after_mask = (dates >= event) & (dates <= event + pd.Timedelta(days=window * 2))
        before_vol = vol_df.loc[before_mask, vol_col].tail(window).mean()
        after_vol = vol_df.loc[after_mask, vol_col].head(window).mean()
        rows.append(
            {
                "event_date": event.date(),
                "avg_vol_before": before_vol,
                "avg_vol_after": after_vol,
                "vol_change": after_vol - before_vol if pd.notna(before_vol) and pd.notna(after_vol) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def load_market_volatility(engine: Engine, ticker: str | None = None) -> pd.DataFrame:
    """Load either a single ticker's volatility series, or the cross-
    sectional average across the universe as an ASX-wide vol proxy."""
    if ticker:
        query = "SELECT date, rolling_vol FROM volatility WHERE ticker = :ticker ORDER BY date"
        return pd.read_sql(text(query), engine, params={"ticker": ticker})
    query = "SELECT date, AVG(rolling_vol) AS rolling_vol FROM volatility GROUP BY date ORDER BY date"
    return pd.read_sql(text(query), engine)


def load_macro(engine: Engine) -> pd.DataFrame:
    return pd.read_sql(text("SELECT * FROM macro ORDER BY date"), engine)


def run(ticker: str | None = None, window: int = 5) -> dict:
    from src.db.engine import get_engine

    engine = get_engine()
    vol_df = load_market_volatility(engine, ticker=ticker)
    macro_df = load_macro(engine)
    if vol_df.empty or macro_df.empty:
        logger.warning("Insufficient data for macro analysis (vol rows=%d, macro rows=%d)", len(vol_df), len(macro_df))
        return {}

    merged = merge_vol_with_macro(vol_df, macro_df)
    corr = correlation_with_macro(merged)
    events = detect_rate_change_events(macro_df)
    event_impact = (
        volatility_around_events(vol_df, events["date"], window=window) if not events.empty else pd.DataFrame()
    )

    logger.info("Macro correlation with volatility:\n%s", corr)
    if not event_impact.empty:
        logger.info("Volatility around RBA rate changes:\n%s", event_impact)

    return {"correlation": corr, "rate_change_events": events, "event_impact": event_impact}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Analyze macro vs ASX volatility relationships")
    parser.add_argument("--ticker", default=None, help="Single ticker, or omit for ASX-wide average")
    parser.add_argument("--window", type=int, default=5)
    args = parser.parse_args(argv)
    run(ticker=args.ticker, window=args.window)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
