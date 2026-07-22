import pandas as pd
import pytest

from src.analytics.macro_analysis import (
    correlation_with_macro,
    detect_rate_change_events,
    merge_vol_with_macro,
    volatility_around_events,
)


def test_merge_vol_with_macro_forward_fills_lower_frequency_series():
    vol_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]),
            "rolling_vol": [0.10, 0.12, 0.11, 0.15],
        }
    )
    macro_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-03"]),
            "cash_rate": [4.35, 4.60],
        }
    )
    merged = merge_vol_with_macro(vol_df, macro_df)

    assert len(merged) == len(vol_df)  # every trading day retained
    # Jan 2 should pick up Jan 1's cash rate (as-of backward fill)
    assert merged.loc[merged["date"] == "2026-01-02", "cash_rate"].iloc[0] == 4.35
    # Jan 4 should pick up Jan 3's cash rate
    assert merged.loc[merged["date"] == "2026-01-04", "cash_rate"].iloc[0] == 4.60


def test_correlation_with_macro_returns_series_sorted_desc():
    merged = pd.DataFrame(
        {
            "rolling_vol": [0.1, 0.2, 0.3, 0.4, 0.5],
            "cash_rate": [1, 2, 3, 4, 5],  # perfectly correlated
            "aud_usd": [5, 4, 3, 2, 1],  # perfectly anti-correlated
        }
    )
    corr = correlation_with_macro(merged)
    assert round(corr["cash_rate"], 6) == 1.0
    assert round(corr["aud_usd"], 6) == -1.0
    assert corr.iloc[0] >= corr.iloc[-1]  # sorted descending


def test_detect_rate_change_events_only_flags_actual_changes():
    macro_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"]),
            "cash_rate": [4.35, 4.35, 4.60, 4.60],
        }
    )
    events = detect_rate_change_events(macro_df)
    assert len(events) == 1
    assert events.iloc[0]["change"] == pytest.approx(0.25)


def test_volatility_around_events_computes_before_after_averages():
    dates = pd.date_range("2026-01-01", periods=20, freq="D")
    vol_df = pd.DataFrame(
        {
            "date": dates,
            "rolling_vol": [0.10] * 10 + [0.30] * 10,  # jump at day 10
        }
    )
    event_dates = pd.Series([dates[10]])
    impact = volatility_around_events(vol_df, event_dates, window=5)

    assert len(impact) == 1
    row = impact.iloc[0]
    assert round(row["avg_vol_before"], 6) == 0.10
    assert round(row["avg_vol_after"], 6) == 0.30
    assert round(row["vol_change"], 6) == pytest.approx(0.20)
