"""
Convenience CLI to run the full local pipeline end-to-end, in order:

    stocks/prices -> macro -> returns -> volatility -> regimes -> briefing

Equivalent to what the chained AWS Lambda functions do in production
(see template.yaml), but handy for local dev / Docker Compose runs where
you don't want to invoke six separate scripts by hand.

Usage:
    python scripts/run_pipeline.py --period 1y
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analytics import regimes, returns, volatility  # noqa: E402
from src.db.engine import run_migrations  # noqa: E402
from src.ingestion import rba_loader, yahoo_loader  # noqa: E402
from src.reports import executive_summary  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the full ASX risk pipeline locally")
    parser.add_argument("--period", default="1y", help="yfinance lookback period, e.g. 5y, 1y, 5d")
    parser.add_argument("--skip-migrations", action="store_true")
    parser.add_argument("--portfolio-id", type=int, default=None)
    args = parser.parse_args(argv)

    if not args.skip_migrations:
        logger.info("Step 0/6: applying schema migrations")
        run_migrations()

    logger.info("Step 1/6: ingesting ASX prices")
    yahoo_loader.run(period=args.period)

    logger.info("Step 2/6: ingesting macro data")
    rba_loader.run(period=args.period)

    logger.info("Step 3/6: computing returns")
    returns.run()

    logger.info("Step 4/6: computing rolling volatility")
    volatility.run()

    logger.info("Step 5/6: classifying volatility regimes")
    regimes.run()

    logger.info("Step 6/6: generating executive briefing")
    summary = executive_summary.run(portfolio_id=args.portfolio_id)
    print("\n" + summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
