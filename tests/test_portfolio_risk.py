import numpy as np
import pandas as pd
import pytest

from src.portfolio.optimizer import (
    Portfolio,
    compute_portfolio_returns,
    equal_weight_portfolio,
    portfolio_variance,
    portfolio_volatility,
)


def test_portfolio_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        Portfolio(name="bad", weights={"A": 0.5, "B": 0.6})


def test_equal_weight_portfolio_sums_to_one():
    p = equal_weight_portfolio("demo", ["A", "B", "C", "D"])
    assert round(sum(p.weights.values()), 8) == 1.0
    assert all(round(w, 8) == 0.25 for w in p.weights.values())


def test_two_asset_known_covariance_variance():
    """50/50 portfolio of two assets with known variances/covariance:
    Var_A = 0.04, Var_B = 0.09, Cov_AB = 0.02
    Var_p = w_A^2*Var_A + w_B^2*Var_B + 2*w_A*w_B*Cov_AB
          = 0.25*0.04 + 0.25*0.09 + 2*0.25*0.02 = 0.01 + 0.0225 + 0.01 = 0.0425
    """
    weights = np.array([0.5, 0.5])
    cov = np.array(
        [
            [0.04, 0.02],
            [0.02, 0.09],
        ]
    )
    var = portfolio_variance(weights, cov)
    assert round(var, 6) == 0.0425
    assert round(portfolio_volatility(weights, cov), 6) == round(np.sqrt(0.0425), 6)


def test_portfolio_volatility_increases_with_concentration():
    """A concentrated portfolio in the higher-vol asset should have higher
    vol than an equal-weight portfolio of the same two assets."""
    cov = np.array(
        [
            [0.01, 0.0],
            [0.0, 0.09],  # asset B is much more volatile
        ]
    )
    equal = portfolio_volatility(np.array([0.5, 0.5]), cov)
    concentrated_in_b = portfolio_volatility(np.array([0.1, 0.9]), cov)
    assert concentrated_in_b > equal


def test_compute_portfolio_returns_weighted_sum():
    dates = pd.date_range("2026-01-01", periods=3)
    wide = pd.DataFrame({"A": [0.01, 0.02, -0.01], "B": [0.03, -0.02, 0.04]}, index=dates)
    portfolio = Portfolio(name="p", weights={"A": 0.5, "B": 0.5})
    port_returns = compute_portfolio_returns(wide, portfolio)
    expected = wide["A"] * 0.5 + wide["B"] * 0.5
    pd.testing.assert_series_equal(port_returns, expected, check_names=False)
