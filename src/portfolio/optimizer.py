"""
Milestone 4 — Portfolio construction & core risk metrics (Vol, VaR, CVaR).

"Optimizer" here is intentionally simple (equal-weight / user-defined
weights) — the focus of this project is *risk measurement*, not alpha
generation or mean-variance optimization. A Markowitz-style optimizer is
listed in the Advanced Feature Backlog if that's ever wanted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import text
from sqlalchemy.engine import Engine

from config import settings


@dataclass
class Portfolio:
    name: str
    weights: dict[str, float]  # ticker -> weight (should sum to ~1.0)
    portfolio_id: int | None = None
    description: str = ""

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        if not np.isclose(total, 1.0, atol=1e-6):
            raise ValueError(f"Portfolio weights must sum to 1.0 (got {total:.6f})")

    @property
    def tickers(self) -> list[str]:
        return list(self.weights.keys())

    def weight_vector(self, order: list[str] | None = None) -> np.ndarray:
        order = order or self.tickers
        return np.array([self.weights[t] for t in order])


def equal_weight_portfolio(name: str, tickers: list[str], description: str = "") -> Portfolio:
    n = len(tickers)
    return Portfolio(name=name, weights={t: 1.0 / n for t in tickers}, description=description)


def compute_portfolio_returns(returns_wide: pd.DataFrame, portfolio: Portfolio) -> pd.Series:
    """Given a wide returns DataFrame (date index, ticker columns) and a
    Portfolio, return the weighted daily portfolio return series."""
    cols = [t for t in portfolio.tickers if t in returns_wide.columns]
    if not cols:
        raise ValueError("None of the portfolio's tickers are present in returns_wide")
    weights = np.array([portfolio.weights[t] for t in cols])
    sub = returns_wide[cols].fillna(0.0)
    return sub.dot(weights)


def portfolio_variance(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
    """w' * Sigma * w"""
    return float(weights @ cov_matrix @ weights)


def portfolio_volatility(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
    return float(np.sqrt(max(portfolio_variance(weights, cov_matrix), 0.0)))


def parametric_var(
    port_returns: pd.Series,
    confidence: float = 0.95,
) -> float:
    """Variance-covariance (Gaussian) 1-day VaR, expressed as a positive
    fraction of portfolio value (e.g. 0.025 = 2.5% loss)."""
    mu = port_returns.mean()
    sigma = port_returns.std()
    z = stats.norm.ppf(confidence)
    return float(-mu + z * sigma)


def historical_var(port_returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical-simulation VaR: the loss at the given percentile of the
    empirical return distribution."""
    losses = -port_returns.dropna()
    return float(np.percentile(losses, confidence * 100))


def historical_cvar(port_returns: pd.Series, confidence: float = 0.95) -> float:
    """Expected Shortfall: mean loss beyond the historical VaR threshold."""
    losses = -port_returns.dropna()
    var = np.percentile(losses, confidence * 100)
    tail = losses[losses >= var]
    if tail.empty:
        return float(var)
    return float(tail.mean())


def parametric_cvar(port_returns: pd.Series, confidence: float = 0.95) -> float:
    """Closed-form Gaussian Expected Shortfall."""
    mu = port_returns.mean()
    sigma = port_returns.std()
    z = stats.norm.ppf(confidence)
    es_multiplier = stats.norm.pdf(z) / (1 - confidence)
    return float(-mu + sigma * es_multiplier)


def max_drawdown(port_returns: pd.Series) -> float:
    cum = (1.0 + port_returns.fillna(0)).cumprod()
    running_max = cum.cummax()
    return float((cum / running_max - 1.0).min())


def sharpe_ratio(
    port_returns: pd.Series, risk_free_rate: float = 0.0, trading_days: int = settings.TRADING_DAYS_PER_YEAR
) -> float:
    excess = port_returns - (risk_free_rate / trading_days)
    std = excess.std()
    if std == 0 or np.isnan(std):
        return float("nan")
    return float(excess.mean() / std * np.sqrt(trading_days))


@dataclass
class RiskSummary:
    volatility_annualized: float
    var_95: float
    cvar_95: float
    var_99: float
    cvar_99: float
    sharpe: float
    max_drawdown: float
    method: str = "historical"


def compute_risk_summary(
    port_returns: pd.Series,
    trading_days: int = settings.TRADING_DAYS_PER_YEAR,
    method: str = "historical",
) -> RiskSummary:
    var_fn, cvar_fn = (historical_var, historical_cvar) if method == "historical" else (parametric_var, parametric_cvar)
    vol_annual = float(port_returns.std() * np.sqrt(trading_days))
    return RiskSummary(
        volatility_annualized=vol_annual,
        var_95=var_fn(port_returns, 0.95),
        cvar_95=cvar_fn(port_returns, 0.95),
        var_99=var_fn(port_returns, 0.99),
        cvar_99=cvar_fn(port_returns, 0.99),
        sharpe=sharpe_ratio(port_returns, trading_days=trading_days),
        max_drawdown=max_drawdown(port_returns),
        method=method,
    )


# --------------------------------------------------------------------------
# DB wiring
# --------------------------------------------------------------------------
def save_portfolio(engine: Engine, portfolio: Portfolio) -> int:
    with engine.begin() as conn:
        if portfolio.portfolio_id is None:
            result = conn.execute(
                text("INSERT INTO portfolios (name, description) VALUES (:name, :description) RETURNING portfolio_id"),
                {"name": portfolio.name, "description": portfolio.description},
            )
            portfolio.portfolio_id = result.scalar_one()
        else:
            conn.execute(
                text(
                    "INSERT INTO portfolios (portfolio_id, name, description) VALUES (:pid, :name, :description) "
                    "ON CONFLICT (portfolio_id) DO UPDATE SET name=EXCLUDED.name, description=EXCLUDED.description"
                ),
                {"pid": portfolio.portfolio_id, "name": portfolio.name, "description": portfolio.description},
            )
        conn.execute(text("DELETE FROM portfolio_holdings WHERE portfolio_id = :pid"), {"pid": portfolio.portfolio_id})
        conn.execute(
            text("INSERT INTO portfolio_holdings (portfolio_id, ticker, weight) VALUES (:pid, :ticker, :weight)"),
            [{"pid": portfolio.portfolio_id, "ticker": t, "weight": w} for t, w in portfolio.weights.items()],
        )
    return portfolio.portfolio_id


def save_portfolio_metrics(engine: Engine, portfolio_id: int, date: str, summary: RiskSummary) -> None:
    stmt = text("""
        INSERT INTO portfolio_metrics
            (portfolio_id, date, volatility, var_95, cvar_95, var_99, cvar_99, sharpe, drawdown)
        VALUES (:pid, :date, :vol, :var95, :cvar95, :var99, :cvar99, :sharpe, :dd)
        ON CONFLICT (portfolio_id, date) DO UPDATE SET
            volatility = EXCLUDED.volatility, var_95 = EXCLUDED.var_95, cvar_95 = EXCLUDED.cvar_95,
            var_99 = EXCLUDED.var_99, cvar_99 = EXCLUDED.cvar_99, sharpe = EXCLUDED.sharpe, drawdown = EXCLUDED.drawdown
        """)
    with engine.begin() as conn:
        conn.execute(
            stmt,
            {
                "pid": portfolio_id,
                "date": date,
                "vol": summary.volatility_annualized,
                "var95": summary.var_95,
                "cvar95": summary.cvar_95,
                "var99": summary.var_99,
                "cvar99": summary.cvar_99,
                "sharpe": summary.sharpe,
                "dd": summary.max_drawdown,
            },
        )
