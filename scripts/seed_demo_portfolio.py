"""
Create a demo equal-weight portfolio and populate its risk metrics +
sector risk attribution for the latest date available in the warehouse.

Usage:
    python scripts/seed_demo_portfolio.py --tickers CBA BHP CSL WES TLS
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analytics.covariance import compute_shrunk_covariance, load_returns_wide  # noqa: E402
from src.db.engine import get_engine  # noqa: E402
from src.portfolio.attribution import (  # noqa: E402
    asset_risk_contributions,
    attribute_var,
    load_sector_map,
    save_sector_contributions,
    sector_risk_contributions,
)
from src.portfolio.optimizer import (  # noqa: E402
    compute_portfolio_returns,
    compute_risk_summary,
    equal_weight_portfolio,
    save_portfolio,
    save_portfolio_metrics,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed a demo portfolio with computed risk metrics")
    parser.add_argument("--name", default="Demo Equal-Weight 5")
    parser.add_argument("--tickers", nargs="+", default=["CBA", "BHP", "CSL", "WES", "TLS"])
    args = parser.parse_args(argv)

    engine = get_engine()
    portfolio = equal_weight_portfolio(args.name, args.tickers, description="Auto-seeded demo portfolio")
    portfolio_id = save_portfolio(engine, portfolio)
    logger.info("Saved portfolio_id=%s with tickers=%s", portfolio_id, args.tickers)

    wide = load_returns_wide(engine)
    wide = wide[[t for t in args.tickers if t in wide.columns]]
    if wide.shape[1] < 2:
        logger.error("Not enough tickers with return history found in DB — run the ETL pipeline first.")
        return 1

    port_returns = compute_portfolio_returns(wide, portfolio)
    summary = compute_risk_summary(port_returns, method="historical")
    latest_date = wide.dropna(how="all").index.max()
    save_portfolio_metrics(engine, portfolio_id, str(latest_date), summary)
    logger.info("Risk summary: %s", summary)

    cov, shrinkage = compute_shrunk_covariance(wide, annualize=True)
    asset_contrib = asset_risk_contributions(portfolio, cov)
    sector_map = load_sector_map(engine, args.tickers)
    sector_contrib = sector_risk_contributions(asset_contrib, sector_map)
    sector_contrib_with_var = attribute_var(
        sector_contrib.rename(columns={"pct_contribution": "pct_contribution"}), summary.var_95
    )

    save_sector_contributions(engine, portfolio_id, str(latest_date), sector_contrib)
    logger.info("Sector risk contributions:\n%s", sector_contrib_with_var)
    return 0


if __name__ == "__main__":
    sys.exit(main())
