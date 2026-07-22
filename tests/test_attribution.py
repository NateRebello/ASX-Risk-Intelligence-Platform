import pandas as pd
import pytest

from src.portfolio.attribution import asset_risk_contributions, attribute_var, sector_risk_contributions
from src.portfolio.optimizer import Portfolio, portfolio_volatility


@pytest.fixture
def three_asset_setup():
    tickers = ["CBA", "BHP", "CSL"]
    weights = {"CBA": 0.4, "BHP": 0.35, "CSL": 0.25}
    portfolio = Portfolio(name="test", weights=weights)
    cov = pd.DataFrame(
        [
            [0.030, 0.010, 0.005],
            [0.010, 0.050, 0.008],
            [0.005, 0.008, 0.020],
        ],
        index=tickers,
        columns=tickers,
    )
    return portfolio, cov


def test_asset_contributions_sum_to_portfolio_volatility(three_asset_setup):
    portfolio, cov = three_asset_setup
    contrib = asset_risk_contributions(portfolio, cov)

    w = portfolio.weight_vector(order=list(cov.columns))
    expected_vol = portfolio_volatility(w, cov.values)

    assert contrib["marginal_contribution"].sum() == pytest.approx(expected_vol, rel=1e-8)
    assert contrib["pct_contribution"].sum() == pytest.approx(1.0, rel=1e-8)


def test_sector_contributions_aggregate_correctly(three_asset_setup):
    portfolio, cov = three_asset_setup
    contrib = asset_risk_contributions(portfolio, cov)
    sector_map = {"CBA": "Financials", "BHP": "Materials", "CSL": "Healthcare"}
    sector_contrib = sector_risk_contributions(contrib, sector_map)

    assert set(sector_contrib["sector"]) == {"Financials", "Materials", "Healthcare"}
    assert sector_contrib["pct_contribution"].sum() == pytest.approx(1.0, rel=1e-8)


def test_sector_contributions_merge_multiple_tickers_same_sector(three_asset_setup):
    portfolio, cov = three_asset_setup
    contrib = asset_risk_contributions(portfolio, cov)
    # Put BHP and CSL in the same synthetic sector to test aggregation.
    sector_map = {"CBA": "Financials", "BHP": "Resources", "CSL": "Resources"}
    sector_contrib = sector_risk_contributions(contrib, sector_map)

    resources_row = sector_contrib[sector_contrib["sector"] == "Resources"].iloc[0]
    bhp_csl_sum = contrib[contrib["ticker"].isin(["BHP", "CSL"])]["marginal_contribution"].sum()
    assert resources_row["marginal_contribution"] == pytest.approx(bhp_csl_sum, rel=1e-8)


def test_attribute_var_allocates_proportionally(three_asset_setup):
    portfolio, cov = three_asset_setup
    contrib = asset_risk_contributions(portfolio, cov)
    var_total = 0.025
    with_var = attribute_var(contrib, var_total)

    assert with_var["var_contribution"].sum() == pytest.approx(var_total, rel=1e-8)
    # Larger pct_contribution -> larger var_contribution (monotonic check).
    ranked = with_var.sort_values("pct_contribution", ascending=False)
    assert (ranked["var_contribution"].diff().dropna() <= 1e-12).all()
