"""
Shared data-cleaning routines applied before analytics run on raw
`daily_prices` data pulled from Postgres.
"""

from __future__ import annotations

import pandas as pd


def drop_duplicate_rows(df: pd.DataFrame, subset: list[str] | None = None) -> pd.DataFrame:
    subset = subset or ["date", "ticker"]
    return df.drop_duplicates(subset=subset, keep="last").reset_index(drop=True)


def forward_fill_gaps(df: pd.DataFrame, group_col: str = "ticker", value_cols: list[str] | None = None) -> pd.DataFrame:
    """Forward-fill missing price values within each ticker's time series.

    Handles the common case of a stock not trading on a given day (holiday,
    trading halt) without breaking downstream return calculations. Leading
    NaNs (before a ticker's first observation) are left as NaN.
    """
    value_cols = value_cols or ["open", "high", "low", "close", "adj_close", "volume"]
    df = df.sort_values(["ticker", "date"]).copy()
    df[value_cols] = df.groupby(group_col)[value_cols].ffill()
    return df


def drop_non_positive_prices(df: pd.DataFrame, price_col: str = "adj_close") -> pd.DataFrame:
    """Remove rows with non-positive or missing prices (invalid for log returns)."""
    mask = df[price_col].notna() & (df[price_col] > 0)
    return df.loc[mask].reset_index(drop=True)


def validate_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Flag/drop rows where high < low or high/low are inconsistent with open/close."""
    valid = (
        (df["high"] >= df["low"])
        & (df["high"] >= df["open"].fillna(df["high"]))
        & (df["high"] >= df["close"].fillna(df["high"]))
        & (df["low"] <= df["open"].fillna(df["low"]))
        & (df["low"] <= df["close"].fillna(df["low"]))
    )
    return df.loc[valid].reset_index(drop=True)


def clean_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Full cleaning pipeline applied to a raw daily_prices DataFrame."""
    df = drop_duplicate_rows(df)
    df = validate_ohlc(df)
    df = forward_fill_gaps(df)
    df = drop_non_positive_prices(df)
    return df
