import numpy as np
import pandas as pd
import pytest

from src.portfolio.optimizer import (
    RiskSummary,
    compute_risk_summary,
    historical_cvar,
    historical_var,
    max_drawdown,
    parametric_cvar,
    parametric_var,
    sharpe_ratio,
)


def test_parametric_var_matches_z_score_for_standard_normal():
    """95% VaR of N(0,1) should be ~1.645 * sigma (mean ~ 0)."""
    rng = np.random.default_rng(0)
    returns = pd.Series(rng.normal(0, 1, 200_000))  # large N so sample stats ~ true params
    var_95 = parametric_var(returns, confidence=0.95)
    assert var_95 == pytest.approx(1.645, abs=0.02)


def test_parametric_var_99_greater_than_95():
    rng = np.random.default_rng(1)
    returns = pd.Series(rng.normal(0, 0.02, 5000))
    var_95 = parametric_var(returns, confidence=0.95)
    var_99 = parametric_var(returns, confidence=0.99)
    assert var_99 > var_95


def test_parametric_cvar_greater_than_var():
    """Expected shortfall must always be >= VaR at the same confidence
    level (it's the average of losses beyond VaR)."""
    rng = np.random.default_rng(2)
    returns = pd.Series(rng.normal(0, 0.02, 5000))
    var_95 = parametric_var(returns, confidence=0.95)
    cvar_95 = parametric_cvar(returns, confidence=0.95)
    assert cvar_95 >= var_95


def test_historical_var_matches_percentile_definition():
    returns = pd.Series(np.linspace(-0.05, 0.05, 1000))
    var_95 = historical_var(returns, confidence=0.95)
    losses = -returns
    assert var_95 == pytest.approx(np.percentile(losses, 95), abs=1e-9)


def test_historical_cvar_at_least_as_large_as_var():
    rng = np.random.default_rng(3)
    returns = pd.Series(rng.standard_t(df=5, size=5000) * 0.01)  # fat tails
    var_95 = historical_var(returns, confidence=0.95)
    cvar_95 = historical_cvar(returns, confidence=0.95)
    assert cvar_95 >= var_95


def test_max_drawdown_is_non_positive():
    rng = np.random.default_rng(4)
    returns = pd.Series(rng.normal(0, 0.02, 500))
    dd = max_drawdown(returns)
    assert dd <= 0


def test_sharpe_ratio_scales_with_trading_days():
    rng = np.random.default_rng(5)
    returns = pd.Series(rng.normal(0.001, 0.01, 500))
    sharpe_252 = sharpe_ratio(returns, trading_days=252)
    sharpe_1 = sharpe_ratio(returns, trading_days=1)
    assert sharpe_252 == pytest.approx(sharpe_1 * np.sqrt(252), rel=1e-6)


def test_compute_risk_summary_returns_plausible_values():
    rng = np.random.default_rng(6)
    returns = pd.Series(rng.normal(0.0002, 0.015, 1000))
    summary = compute_risk_summary(returns, method="historical")
    assert isinstance(summary, RiskSummary)
    assert summary.volatility_annualized > 0
    assert summary.var_95 > 0
    assert summary.cvar_95 >= summary.var_95
    assert summary.var_99 >= summary.var_95
    assert summary.cvar_99 >= summary.var_99
