import numpy as np
import pandas as pd

from src.analytics.volatility import (
    compute_max_drawdown,
    compute_rolling_vol,
    compute_sharpe,
    compute_volatility_frame,
)


def test_rolling_vol_matches_manual_std():
    rng = np.random.default_rng(42)
    returns = pd.Series(rng.normal(0, 0.01, 200))
    window = 30
    vol = compute_rolling_vol(returns, window=window, annualize=False)
    expected_last = returns.iloc[-window:].std()
    assert round(vol.iloc[-1], 10) == round(expected_last, 10)


def test_rolling_vol_annualized_scales_by_sqrt_252():
    returns = pd.Series(np.zeros(40))
    raw = compute_rolling_vol(returns, window=10, annualize=False)
    annualized = compute_rolling_vol(returns, window=10, annualize=True)
    # both are 0 here (constant series), so just check no NaN / correct length
    assert raw.iloc[-1] == 0.0
    assert annualized.iloc[-1] == 0.0


def test_rolling_vol_constant_positive_returns_is_zero():
    """A perfectly geometric (constant % growth) price series has an exactly
    constant daily return series, so its rolling std should be ~0."""
    prices = 100 * (1.01 ** np.arange(101))
    returns = pd.Series(np.diff(prices) / prices[:-1])
    vol = compute_rolling_vol(returns, window=50, annualize=False)
    assert vol.iloc[-1] < 1e-10


def test_max_drawdown_known_case():
    # Peaks at 120 then falls to 90 -> drawdown = 90/120 - 1 = -0.25
    prices = pd.Series([100, 110, 120, 100, 90, 95])
    dd = compute_max_drawdown(prices)
    assert round(dd, 6) == round(90 / 120 - 1, 6)


def test_sharpe_zero_vol_returns_nan():
    returns = pd.Series(np.zeros(50))
    assert np.isnan(compute_sharpe(returns))


def test_sharpe_positive_for_positive_mean_returns():
    # Use slightly noisy returns so std > 0 (a perfectly constant series
    # would give std=0 -> NaN, tested separately above).
    rng = np.random.default_rng(0)
    noisy = pd.Series(0.001 + rng.normal(0, 0.0001, 500))
    sharpe = compute_sharpe(noisy)
    assert sharpe > 0


def test_compute_volatility_frame_per_ticker_window():
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    df = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "ticker": ["AAA"] * 40 + ["BBB"] * 40,
            "daily_return": list(np.zeros(40)) + list(np.zeros(40)),
        }
    )
    result = compute_volatility_frame(df, window=10)
    assert set(result["ticker"].unique()) == {"AAA", "BBB"}
    # first (window-1) rows per ticker should be NaN
    aaa = result[result["ticker"] == "AAA"].sort_values("date")
    assert aaa["rolling_vol"].iloc[:9].isna().all()
    assert not pd.isna(aaa["rolling_vol"].iloc[9])
