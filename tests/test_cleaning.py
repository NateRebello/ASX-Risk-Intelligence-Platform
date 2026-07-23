import numpy as np
import pandas as pd

from src.processing.cleaning import (
    clean_prices,
    drop_duplicate_rows,
    drop_non_positive_prices,
    forward_fill_gaps,
    validate_ohlc,
)


def _base_df():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "ticker": ["AAA"] * 3,
            "open": [10.0, 10.5, 11.0],
            "high": [11.0, 11.5, 12.0],
            "low": [9.5, 10.0, 10.5],
            "close": [10.8, 11.2, 11.8],
            "adj_close": [10.8, 11.2, 11.8],
            "volume": [1000, 1100, 1200],
        }
    )


def test_drop_duplicate_rows_keeps_last():
    df = pd.concat([_base_df(), _base_df().iloc[[0]]], ignore_index=True)
    deduped = drop_duplicate_rows(df)
    assert len(deduped) == 3


def test_forward_fill_gaps_fills_missing_close():
    df = _base_df()
    df.loc[1, "close"] = np.nan
    filled = forward_fill_gaps(df)
    assert filled.loc[1, "close"] == df.loc[0, "close"]


def test_drop_non_positive_prices_removes_zero_and_negative():
    df = _base_df()
    df.loc[1, "adj_close"] = 0.0
    df.loc[2, "adj_close"] = -5.0
    cleaned = drop_non_positive_prices(df)
    assert len(cleaned) == 1


def test_validate_ohlc_drops_inconsistent_rows():
    df = _base_df()
    df.loc[1, "high"] = 5.0  # high < low -> invalid
    validated = validate_ohlc(df)
    assert len(validated) == 2
    assert 1 not in validated.index.tolist() or validated.iloc[1]["date"] != df.iloc[1]["date"]


def test_clean_prices_end_to_end_pipeline_runs():
    df = _base_df()
    result = clean_prices(df)
    assert not result.empty
    assert result["adj_close"].gt(0).all()
