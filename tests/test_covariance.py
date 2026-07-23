import numpy as np
import pandas as pd
import pytest
from sklearn.covariance import LedoitWolf

from src.analytics.covariance import (
    compute_correlation_matrix,
    compute_covariance_matrix,
    compute_shrunk_covariance,
    pivot_returns,
)


@pytest.fixture
def synthetic_returns_wide():
    rng = np.random.default_rng(7)
    n_obs, n_assets = 300, 4
    data = rng.normal(0, 0.01, size=(n_obs, n_assets))
    return pd.DataFrame(data, columns=["A", "B", "C", "D"])


def test_pivot_returns_shapes_correctly():
    long_df = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02"],
            "ticker": ["A", "B", "A", "B"],
            "daily_return": [0.01, -0.02, 0.03, 0.04],
        }
    )
    wide = pivot_returns(long_df)
    assert list(wide.columns) == ["A", "B"]
    assert wide.shape == (2, 2)
    assert wide.loc["2026-01-01", "A"] == 0.01


def test_correlation_matrix_diagonal_is_one(synthetic_returns_wide):
    corr = compute_correlation_matrix(synthetic_returns_wide)
    assert np.allclose(np.diag(corr.values), 1.0)
    assert corr.shape == (4, 4)
    # correlation matrix must be symmetric
    assert np.allclose(corr.values, corr.values.T)


def test_covariance_matrix_matches_pandas_cov(synthetic_returns_wide):
    cov = compute_covariance_matrix(synthetic_returns_wide)
    expected = synthetic_returns_wide.cov()
    pd.testing.assert_frame_equal(cov, expected)


def test_shrunk_covariance_matches_sklearn_ledoitwolf(synthetic_returns_wide):
    cov_df, shrinkage = compute_shrunk_covariance(synthetic_returns_wide)

    lw = LedoitWolf().fit(synthetic_returns_wide.values)
    assert cov_df.shape == lw.covariance_.shape
    assert np.allclose(cov_df.values, lw.covariance_)
    assert round(shrinkage, 10) == round(lw.shrinkage_, 10)
    assert 0.0 <= shrinkage <= 1.0


def test_shrunk_covariance_raises_on_insufficient_data():
    tiny = pd.DataFrame({"A": [0.01], "B": [0.02]})
    with pytest.raises(ValueError):
        compute_shrunk_covariance(tiny)
