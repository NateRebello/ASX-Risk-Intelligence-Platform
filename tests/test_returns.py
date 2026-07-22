import numpy as np
import pandas as pd

from src.analytics.returns import compute_daily_returns, compute_log_returns, compute_returns_frame


def test_simple_return_known_values():
    prices = pd.Series([100.0, 110.0])
    returns = compute_daily_returns(prices)
    assert np.isnan(returns.iloc[0])
    assert round(returns.iloc[1], 6) == 0.10


def test_log_return_known_values():
    prices = pd.Series([100.0, 110.0])
    log_returns = compute_log_returns(prices)
    assert round(log_returns.iloc[1], 6) == round(np.log(1.10), 6)


def test_returns_frame_multi_ticker():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-01", "2026-01-02"]),
            "ticker": ["AAA", "AAA", "BBB", "BBB"],
            "adj_close": [100.0, 105.0, 50.0, 45.0],
        }
    )
    result = compute_returns_frame(df)
    aaa = result[result["ticker"] == "AAA"].sort_values("date")
    bbb = result[result["ticker"] == "BBB"].sort_values("date")

    assert round(aaa["daily_return"].iloc[1], 6) == 0.05
    assert round(bbb["daily_return"].iloc[1], 6) == -0.10
    # first observation of each ticker has no prior price -> NaN
    assert np.isnan(aaa["daily_return"].iloc[0])
    assert np.isnan(bbb["daily_return"].iloc[0])


def test_returns_do_not_leak_across_tickers():
    """A ticker's first day must not compute a return from another ticker's
    last price (a classic groupby bug)."""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-02", "2026-01-03"]),
            "ticker": ["AAA", "AAA", "BBB", "BBB"],
            "adj_close": [100.0, 101.0, 999.0, 1000.0],
        }
    )
    result = compute_returns_frame(df)
    bbb_first = result[result["ticker"] == "BBB"].sort_values("date").iloc[0]
    assert np.isnan(bbb_first["daily_return"])
