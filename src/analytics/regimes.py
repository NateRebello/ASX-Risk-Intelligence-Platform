"""
Milestone 3 — Volatility regime detection.

Two complementary approaches, both writing into the `volatility` table:

  1. Percentile method (`label_regime_percentile`): classifies rolling
     volatility into Normal / Elevated / Stress terciles based on the
     historical distribution. Simple, transparent, and easy to explain to
     a non-technical stakeholder.

  2. Hidden Markov Model (`fit_hmm_regimes`): fits a Gaussian HMM on the
     return series to infer latent regimes directly from return
     dynamics (mean/variance clustering), which can react faster to
     regime shifts than a rolling window.
"""

from __future__ import annotations

import logging
import sys

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sqlalchemy import text
from sqlalchemy.engine import Engine

from config import settings
from src.db.engine import get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# 1. Percentile method
# --------------------------------------------------------------------------
def compute_percentile_thresholds(
    vol_series: pd.Series,
    cutoffs: tuple[float, float] = settings.REGIME_PERCENTILE_CUTOFFS,
) -> dict[str, float]:
    """Return the lower/upper volatility cutoffs (terciles by default)."""
    lower_q, upper_q = cutoffs
    clean = vol_series.dropna()
    return {
        "lower": float(clean.quantile(lower_q)),
        "upper": float(clean.quantile(upper_q)),
    }


def label_regime_percentile(
    vol: float,
    thresholds: dict[str, float],
    labels: tuple[str, str, str] = settings.REGIME_LABELS,
) -> str | None:
    """Classify a single volatility observation into Normal/Elevated/Stress."""
    if pd.isna(vol):
        return None
    normal, elevated, stress = labels
    if vol < thresholds["lower"]:
        return normal
    if vol < thresholds["upper"]:
        return elevated
    return stress


def apply_percentile_regimes(
    vol_df: pd.DataFrame,
    cutoffs: tuple[float, float] = settings.REGIME_PERCENTILE_CUTOFFS,
    per_ticker: bool = True,
) -> pd.DataFrame:
    """Given [date, ticker, rolling_vol], add a `regime` column.

    When `per_ticker` is True (default), thresholds are computed
    independently per ticker (a mining stock's "normal" vol differs from a
    bank's). Set False to use a single global threshold, e.g. for an index.

    Implemented via a Series-only `groupby(...).transform(...)` (rather than
    a DataFrame-returning `.apply(...)`) so it isn't affected by pandas'
    grouping-column-exclusion behavior for `.apply()` on `DataFrameGroupBy`.
    """
    df = vol_df.copy()

    def _label_series(vol: pd.Series) -> pd.Series:
        thresholds = compute_percentile_thresholds(vol, cutoffs)
        return vol.apply(lambda v: label_regime_percentile(v, thresholds))

    if per_ticker:
        df["regime"] = df.groupby("ticker")["rolling_vol"].transform(_label_series)
    else:
        df["regime"] = _label_series(df["rolling_vol"])
    return df


# --------------------------------------------------------------------------
# 2. Hidden Markov Model method
# --------------------------------------------------------------------------
def fit_hmm_regimes(
    returns: np.ndarray | pd.Series,
    n_states: int = settings.HMM_N_STATES,
    covariance_type: str = "diag",
    n_iter: int = 200,
    random_state: int = 42,
) -> tuple[GaussianHMM, np.ndarray]:
    """Fit a Gaussian HMM on a 1-D return series and return (model, hidden_states).

    `returns` must not contain NaNs. Hidden states are relabeled 0..n-1 in
    order of *ascending volatility* (state 0 = lowest-vol regime) so the
    numeric label is comparable across independent fits.
    """
    if isinstance(returns, pd.Series):
        returns = returns.values
    x = np.asarray(returns, dtype=float).reshape(-1, 1)
    if np.isnan(x).any():
        raise ValueError("fit_hmm_regimes requires a return series with no NaNs")

    model = GaussianHMM(
        n_components=n_states, covariance_type=covariance_type, n_iter=n_iter, random_state=random_state
    )
    model.fit(x)
    raw_states = model.predict(x)

    # Reorder states by ascending variance so label 0 is always "calmest".
    variances = model.covars_.reshape(n_states, -1).mean(axis=1)
    order = np.argsort(variances)
    remap = {old: new for new, old in enumerate(order)}
    states = np.array([remap[s] for s in raw_states])
    return model, states


def hmm_state_to_label(state: int, n_states: int, labels: tuple[str, ...] = settings.REGIME_LABELS) -> str:
    """Map a numeric HMM state (0=calmest) onto Normal/Elevated/Stress-style
    labels, scaling to however many states were fit."""
    if n_states == len(labels):
        return labels[state]
    # Fallback: bucket proportionally into the available labels.
    bucket = min(int(state / n_states * len(labels)), len(labels) - 1)
    return labels[bucket]


# --------------------------------------------------------------------------
# DB wiring
# --------------------------------------------------------------------------
def load_volatility_and_returns(engine: Engine, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    query = """
        SELECT v.date, v.ticker, v.rolling_vol, r.daily_return
        FROM volatility v
        JOIN returns r ON v.date = r.date AND v.ticker = r.ticker
    """
    conditions, params = [], {}
    if start:
        conditions.append("v.date >= :start")
        params["start"] = start
    if end:
        conditions.append("v.date <= :end")
        params["end"] = end
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY v.ticker, v.date"
    return pd.read_sql(text(query), engine, params=params)


def upsert_regimes(engine: Engine, df: pd.DataFrame) -> int:
    cols = ["date", "ticker", "regime", "regime_hmm"]
    df = df[cols].where(pd.notna(df[cols]), None)
    records = df.to_dict("records")
    if not records:
        return 0
    stmt = text("""
        INSERT INTO volatility (date, ticker, regime, regime_hmm)
        VALUES (:date, :ticker, :regime, :regime_hmm)
        ON CONFLICT (date, ticker) DO UPDATE SET
            regime = EXCLUDED.regime,
            regime_hmm = EXCLUDED.regime_hmm
        """)
    with engine.begin() as conn:
        conn.execute(stmt, records)
    return len(records)


def run(n_states: int = settings.HMM_N_STATES, start: str | None = None, end: str | None = None) -> int:
    engine = get_engine()
    df = load_volatility_and_returns(engine, start=start, end=end)
    if df.empty:
        logger.warning("No volatility/returns data found; nothing to classify")
        return 0

    df = apply_percentile_regimes(df)

    hmm_results = []
    for ticker, group in df.groupby("ticker"):
        clean = group.dropna(subset=["daily_return"])
        if len(clean) < max(50, n_states * 10):
            logger.info("%s: not enough observations (%d) to fit HMM; skipping HMM label", ticker, len(clean))
            continue
        try:
            _, states = fit_hmm_regimes(clean["daily_return"], n_states=n_states)
            hmm_results.append(pd.DataFrame({"date": clean["date"].values, "ticker": ticker, "regime_hmm": states}))
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: HMM fit failed — %s", ticker, exc)

    if hmm_results:
        hmm_df = pd.concat(hmm_results, ignore_index=True)
        df = df.merge(hmm_df, on=["date", "ticker"], how="left")
    else:
        df["regime_hmm"] = None

    n = upsert_regimes(engine, df)
    logger.info("Upserted %d regime rows", n)
    return n


def lambda_handler(event: dict, context) -> dict:  # noqa: ANN001
    n = run()
    return {"statusCode": 200, "rows_written": n}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Classify volatility regimes (percentile + HMM)")
    parser.add_argument("--n-states", type=int, default=settings.HMM_N_STATES)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args(argv)
    run(n_states=args.n_states, start=args.start, end=args.end)
    return 0


if __name__ == "__main__":
    sys.exit(main())
