"""
Milestone 1 / 5 — Macro data ingestion (RBA cash rate, ABS CPI, AUD/USD,
iron ore price) into the `macro` table.

Design notes (see README "Assumptions & Constraints" — free data only,
handle missing data gracefully):

  * RBA cash rate: parsed directly from the RBA's published F1.1 CSV table
    (https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv). This is a
    real, publicly documented file format with a fixed metadata header
    block followed by monthly data rows.
  * ABS CPI: the ABS Indicator API occasionally changes/rate-limits, so we
    try it first and fall back to a manual CSV at data/raw/abs_cpi.csv
    (columns: date, cpi) if the API call fails. If neither is available,
    CPI is simply left NULL for that run rather than failing the pipeline.
  * AUD/USD and iron ore: sourced from Yahoo Finance (AUDUSD=X, TIO=F) via
    yfinance, which is free and reliably available.
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.engine import Engine

from config import settings
from src.db.engine import get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_RBA_META_LABELS = {
    "Description",
    "Frequency",
    "Type",
    "Units",
    "Source",
    "Publication date",
    "Series ID",
}


def fetch_cash_rate(url: str | None = None) -> pd.DataFrame:
    """Download & parse the RBA F1.1 table, returning columns [date, cash_rate]."""
    url = url or settings.RBA_CASH_RATE_URL
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    # Row 0 is a free-text title; row 1 has the real column headers.
    raw = pd.read_csv(io.StringIO(resp.text), skiprows=1, dtype=str)
    raw = raw.rename(columns={raw.columns[0]: "date"})
    raw = raw[~raw["date"].isin(_RBA_META_LABELS)]
    raw = raw.dropna(subset=["date"])

    raw["date"] = pd.to_datetime(raw["date"], format="%d/%m/%Y", errors="coerce")
    raw = raw.dropna(subset=["date"])

    col = settings.RBA_F11_SHEET_KEY_ROW_HINT  # "Cash Rate Target"
    if col not in raw.columns:
        raise ValueError(f"Expected column '{col}' not found in RBA CSV; columns={list(raw.columns)}")

    out = raw[["date", col]].rename(columns={col: "cash_rate"})
    out["cash_rate"] = pd.to_numeric(out["cash_rate"], errors="coerce")
    out["date"] = out["date"].dt.date
    return out.dropna(subset=["cash_rate"]).reset_index(drop=True)


def fetch_cpi(api_url: str | None = None, fallback_csv: str = "data/raw/abs_cpi.csv") -> pd.DataFrame:
    """Fetch quarterly CPI. Tries the ABS API, falls back to a local CSV."""
    api_url = api_url or settings.ABS_CPI_API_URL
    try:
        resp = requests.get(api_url, timeout=20, headers={"Accept": "application/vnd.sdmx.data+json"})
        resp.raise_for_status()
        payload = resp.json()
        return _parse_abs_sdmx(payload)
    except Exception as exc:  # noqa: BLE001 — ABS API is flaky, fall back gracefully
        logger.warning("ABS CPI API failed (%s); trying local fallback %s", exc, fallback_csv)

    path = Path(fallback_csv)
    if path.exists():
        df = pd.read_csv(path, parse_dates=["date"])
        df["date"] = df["date"].dt.date
        return df[["date", "cpi"]]

    logger.warning("No ABS fallback CSV found at %s — CPI will be left NULL this run", fallback_csv)
    return pd.DataFrame(columns=["date", "cpi"])


def _parse_abs_sdmx(payload: dict) -> pd.DataFrame:
    """Best-effort parser for the ABS SDMX-JSON response shape."""
    try:
        series = payload["data"]["dataSets"][0]["series"]
        time_periods = payload["data"]["structure"]["dimensions"]["observation"][0]["values"]
        rows = []
        for _, s in series.items():
            for idx, obs in s["observations"].items():
                date_str = time_periods[int(idx)]["id"]
                rows.append({"date": pd.to_datetime(date_str), "cpi": obs[0]})
        df = pd.DataFrame(rows).sort_values("date")
        df["date"] = df["date"].dt.date
        return df
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unrecognized ABS SDMX-JSON shape: {exc}") from exc


def fetch_aud_usd(period: str = "5y") -> pd.DataFrame:
    df = yf.download("AUDUSD=X", period=period, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "aud_usd"])
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()[["Date", "Close"]].rename(columns={"Date": "date", "Close": "aud_usd"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def fetch_iron_ore(period: str = "5y", ticker: str = "TIO=F") -> pd.DataFrame:
    df = yf.download(ticker, period=period, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "iron_ore_price"])
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()[["Date", "Close"]].rename(columns={"Date": "date", "Close": "iron_ore_price"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def upsert_macro(engine: Engine, merged: pd.DataFrame) -> int:
    if merged.empty:
        return 0
    merged = merged.where(pd.notna(merged), None)
    records = merged.to_dict("records")
    stmt = text("""
        INSERT INTO macro (date, cash_rate, cpi, unemployment, aud_usd, iron_ore_price)
        VALUES (:date, :cash_rate, :cpi, :unemployment, :aud_usd, :iron_ore_price)
        ON CONFLICT (date) DO UPDATE SET
            cash_rate = COALESCE(EXCLUDED.cash_rate, macro.cash_rate),
            cpi = COALESCE(EXCLUDED.cpi, macro.cpi),
            unemployment = COALESCE(EXCLUDED.unemployment, macro.unemployment),
            aud_usd = COALESCE(EXCLUDED.aud_usd, macro.aud_usd),
            iron_ore_price = COALESCE(EXCLUDED.iron_ore_price, macro.iron_ore_price)
        """)
    with engine.begin() as conn:
        conn.execute(stmt, records)
    return len(records)


def run(period: str = "5y") -> int:
    engine = get_engine()
    frames = []

    try:
        cash_rate = fetch_cash_rate()
        frames.append(cash_rate)
        logger.info("Fetched %d cash rate rows", len(cash_rate))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cash rate fetch failed: %s", exc)

    try:
        cpi = fetch_cpi()
        if not cpi.empty:
            frames.append(cpi)
        logger.info("Fetched %d CPI rows", len(cpi))
    except Exception as exc:  # noqa: BLE001
        logger.warning("CPI fetch failed: %s", exc)

    try:
        aud = fetch_aud_usd(period=period)
        frames.append(aud)
        logger.info("Fetched %d AUD/USD rows", len(aud))
    except Exception as exc:  # noqa: BLE001
        logger.warning("AUD/USD fetch failed: %s", exc)

    try:
        iron_ore = fetch_iron_ore(period=period)
        frames.append(iron_ore)
        logger.info("Fetched %d iron ore rows", len(iron_ore))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Iron ore fetch failed: %s", exc)

    if not frames:
        logger.error("All macro sources failed — nothing to write")
        return 0

    merged = frames[0]
    for f in frames[1:]:
        merged = merged.merge(f, on="date", how="outer")
    for col in ("cash_rate", "cpi", "unemployment", "aud_usd", "iron_ore_price"):
        if col not in merged.columns:
            merged[col] = None
    merged = merged.sort_values("date")

    # Cash rate / CPI / unemployment are published monthly/quarterly, so a
    # daily row only has a *fresh* value on its publication date. Forward-
    # fill them across the daily grid so every day (and in particular the
    # latest date) carries the most recently published reading rather than
    # NULL — this is what downstream consumers (dashboard, briefing) expect.
    for col in ("cash_rate", "cpi", "unemployment"):
        merged[col] = merged[col].ffill()

    n = upsert_macro(engine, merged[["date", "cash_rate", "cpi", "unemployment", "aud_usd", "iron_ore_price"]])
    logger.info("Upserted %d macro rows", n)
    return n


def lambda_handler(event: dict, context) -> dict:  # noqa: ANN001
    period = (event or {}).get("period", "1mo")
    n = run(period=period)
    return {"statusCode": 200, "rows_written": n}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load RBA/ABS/AUD/iron-ore macro series into Postgres")
    parser.add_argument("--period", default="5y", help="yfinance period for AUD/USD & iron ore, e.g. 5y, 1mo")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    n = run(period=args.period)
    return 0 if n > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
