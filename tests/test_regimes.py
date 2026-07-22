import numpy as np
import pandas as pd
import pytest

from src.analytics.regimes import (
    apply_percentile_regimes,
    compute_percentile_thresholds,
    fit_hmm_regimes,
    hmm_state_to_label,
    label_regime_percentile,
)


def test_percentile_thresholds_known_cutoffs():
    vol = pd.Series(np.arange(1, 101))  # 1..100
    thresholds = compute_percentile_thresholds(vol, cutoffs=(0.33, 0.66))
    assert round(thresholds["lower"], 1) == pytest.approx(vol.quantile(0.33), abs=0.5)
    assert round(thresholds["upper"], 1) == pytest.approx(vol.quantile(0.66), abs=0.5)


def test_label_regime_percentile_buckets_correctly():
    thresholds = {"lower": 10.0, "upper": 20.0}
    assert label_regime_percentile(5.0, thresholds) == "Normal"
    assert label_regime_percentile(15.0, thresholds) == "Elevated"
    assert label_regime_percentile(25.0, thresholds) == "Stress"
    assert label_regime_percentile(float("nan"), thresholds) is None


def test_apply_percentile_regimes_produces_all_three_buckets():
    # Continuously increasing (non-repeating) vol values so percentile
    # cutoffs land strictly between distinct observations, avoiding tie
    # edge-cases at the bucket boundaries.
    vol_values = np.concatenate(
        [
            np.linspace(1.0, 2.0, 20),  # low vol block
            np.linspace(10.0, 11.0, 20),  # mid vol block
            np.linspace(50.0, 51.0, 20),  # high vol block
        ]
    )
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=60),
            "ticker": ["AAA"] * 60,
            "rolling_vol": vol_values,
        }
    )
    labeled = apply_percentile_regimes(df)
    regimes_present = set(labeled["regime"].unique())
    assert regimes_present == {"Normal", "Elevated", "Stress"}
    # the low-vol block should be entirely Normal
    assert (labeled.iloc[:20]["regime"] == "Normal").all()
    # the high-vol block should be entirely Stress
    assert (labeled.iloc[40:]["regime"] == "Stress").all()


def test_fit_hmm_regimes_on_two_state_synthetic_returns():
    """Feed a return series with an obvious calm/volatile split and check
    the HMM recovers the expected number of distinct states, and that the
    volatile block is dominated by the higher-variance state label."""
    rng = np.random.default_rng(123)
    calm = rng.normal(0, 0.001, 300)
    volatile = rng.normal(0, 0.05, 300)
    returns = np.concatenate([calm, volatile])

    model, states = fit_hmm_regimes(returns, n_states=2, random_state=1)
    assert model.n_components == 2
    assert set(np.unique(states)).issubset({0, 1})

    # State 0 = calmest by construction (relabeled in fit_hmm_regimes).
    calm_block_state = pd.Series(states[:300]).mode()[0]
    volatile_block_state = pd.Series(states[300:]).mode()[0]
    assert calm_block_state != volatile_block_state
    assert calm_block_state == 0


def test_fit_hmm_regimes_rejects_nans():
    returns = np.array([0.01, np.nan, 0.02])
    with pytest.raises(ValueError):
        fit_hmm_regimes(returns, n_states=2)


def test_hmm_state_to_label_matches_state_count():
    labels = ("Normal", "Elevated", "Stress")
    assert hmm_state_to_label(0, 3, labels) == "Normal"
    assert hmm_state_to_label(2, 3, labels) == "Stress"
