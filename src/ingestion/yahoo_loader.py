"""
Milestone 1 — ASX daily OHLCV ingestion via yfinance.

Downloads daily price history for the configured ASX universe and upserts
it into the `stocks` and `daily_prices` tables. Designed to be run either:

  * as a CLI script:      python -m src.ingestion.yahoo_loader --period 5y
  * as an AWS Lambda:      handler = lambda_handler

Missing/failed tickers are logged and skipped rather than aborting the
whole run (a single delisted or renamed ticker should not break the ETL).
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

import pandas as pd
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.engine import Engine

from config import settings
from src.db.engine import get_engine
from src.storage.s3_archive import archive_dataframe

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class LoadResult:
    ticker: str
    rows: int
    status: str  # "success" | "empty" | "error"
    detail: str = ""


def load_universe(tickers_file: str = "") -> list[dict[str, str]]:
    """Return the list of {ticker, name, sector, industry} dicts to ingest."""
    tickers_file = tickers_file or settings.ASX_TICKERS_FILE
    if tickers_file:
        df = pd.read_csv(tickers_file)
        required = {"ticker", "name", "sector", "industry"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Tickers file is missing columns: {missing}")
        return df[list(required)].to_dict("records")
    return settings.DEFAULT_UNIVERSE


def upsert_stocks(engine: Engine, universe: list[dict[str, str]]) -> None:
    stmt = text("""
        INSERT INTO stocks (ticker, name, sector, industry)
        VALUES (:ticker, :name, :sector, :industry)
        ON CONFLICT (ticker) DO UPDATE SET
            name = EXCLUDED.name,
            sector = EXCLUDED.sector,
            industry = EXCLUDED.industry
        """)
    with engine.begin() as conn:
        conn.execute(stmt, universe)
    logger.info("Upserted %d rows into stocks", len(universe))


def fetch_prices(ticker: str, period: str = "5y", start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Download OHLCV history for a single ASX ticker via yfinance.

    ASX tickers require the `.AX` suffix on Yahoo Finance. Returns a
    DataFrame with columns [date, open, high, low, close, adj_close, volume],
    or an empty DataFrame if no data was returned.
    """
    symbol = f"{ticker}{settings.YAHOO_SUFFIX}"
    if start or end:
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=False)
    else:
        df = yf.download(symbol, period=period, progress=False, auto_adjust=False)

    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "adj_close", "volume"])

    # yfinance may return a MultiIndex column frame for a single ticker in
    # newer versions; normalize to flat columns.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index().rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    if "adj_close" not in df.columns:
        df["adj_close"] = df["close"]

    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df[["date", "open", "high", "low", "close", "adj_close", "volume"]]


def upsert_prices(engine: Engine, ticker: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    df = df.dropna(subset=["close"])  # a row with no close price is useless
    records = [
        {
            "date": row.date,
            "ticker": ticker,
            "open": _none_if_nan(row.open),
            "high": _none_if_nan(row.high),
            "low": _none_if_nan(row.low),
            "close": _none_if_nan(row.close),
            "adj_close": _none_if_nan(row.adj_close),
            "volume": int(row.volume) if pd.notna(row.volume) else None,
        }
        for row in df.itertuples(index=False)
    ]
    stmt = text("""
        INSERT INTO daily_prices (date, ticker, open, high, low, close, adj_close, volume)
        VALUES (:date, :ticker, :open, :high, :low, :close, :adj_close, :volume)
        ON CONFLICT (date, ticker) DO UPDATE SET
            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
            close = EXCLUDED.close, adj_close = EXCLUDED.adj_close, volume = EXCLUDED.volume
        """)
    with engine.begin() as conn:
        conn.execute(stmt, records)
    return len(records)


def _none_if_nan(value: float) -> float | None:
    return None if pd.isna(value) else float(value)


def _log_ingestion(engine: Engine, source: str, rows: int, status: str, detail: str = "") -> None:
    stmt = text("""
        INSERT INTO ingestion_log (source, rows_written, status, detail)
        VALUES (:source, :rows, :status, :detail)
        """)
    with engine.begin() as conn:
        conn.execute(stmt, {"source": source, "rows": rows, "status": status, "detail": detail[:500]})


def run(
    period: str = "5y", start: str | None = None, end: str | None = None, tickers_file: str = ""
) -> list[LoadResult]:
    engine = get_engine()
    universe = load_universe(tickers_file)
    upsert_stocks(engine, universe)

    results: list[LoadResult] = []
    total_rows = 0
    for row in universe:
        ticker = row["ticker"]
        try:
            df = fetch_prices(ticker, period=period, start=start, end=end)
            archive_dataframe(df, source="yahoo-prices", identifier=ticker)
            n = upsert_prices(engine, ticker, df)
            total_rows += n
            status = "success" if n > 0 else "empty"
            results.append(LoadResult(ticker, n, status))
            logger.info("%s: upserted %d rows (%s)", ticker, n, status)
        except Exception as exc:  # noqa: BLE001 — one bad ticker must not kill the run
            logger.warning("%s: failed to load — %s", ticker, exc)
            results.append(LoadResult(ticker, 0, "error", str(exc)))

    failed = [r for r in results if r.status == "error"]
    overall_status = "success" if not failed else ("partial" if len(failed) < len(results) else "failed")
    _log_ingestion(engine, "yahoo", total_rows, overall_status, f"{len(failed)} tickers failed")
    return results


def lambda_handler(event: dict, context) -> dict:  # noqa: ANN001 — AWS Lambda signature
    """AWS Lambda entry point. `event` may contain {"period": "...", "start": "...", "end": "..."}."""
    period = event.get("period", "5d") if event else "5d"
    start = event.get("start") if event else None
    end = event.get("end") if event else None
    results = run(period=period, start=start, end=end)
    ok = sum(1 for r in results if r.status == "success")
    return {
        "statusCode": 200,
        "tickers_processed": len(results),
        "tickers_ok": ok,
        "tickers_failed": len(results) - ok,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load ASX daily OHLCV into Postgres via yfinance")
    parser.add_argument("--period", default=settings.DEFAULT_LOOKBACK_PERIOD, help="yfinance period, e.g. 5y, 1y, 5d")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD (overrides --period)")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--tickers-file", default="", help="Optional CSV of ticker,name,sector,industry")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    results = run(period=args.period, start=args.start, end=args.end, tickers_file=args.tickers_file)
    failed = [r for r in results if r.status == "error"]
    ok = [r for r in results if r.status == "success"]
    logger.info(
        "Done: %d ok, %d empty, %d failed (of %d)",
        len(ok),
        len(results) - len(ok) - len(failed),
        len(failed),
        len(results),
    )
    return 0 if len(failed) < len(results) else 1  # non-zero only if EVERYTHING failed


if __name__ == "__main__":
    sys.exit(main())
