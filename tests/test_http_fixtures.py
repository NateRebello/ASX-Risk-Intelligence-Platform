"""Step 9 — offline HTTP / provider contract tests using sanitized fixtures.

These tests never call live Yahoo, RBA, or ABS endpoints. Fixtures under
``tests/fixtures/http/`` are truncated, synthetic, or format-faithful samples
suitable for CI (no API keys, no full historical dumps).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import responses

from src.ingestion import rba_loader, yahoo_loader
from src.ingestion.rba_loader import fetch_aud_usd, fetch_cash_rate, fetch_cpi, fetch_iron_ore
from src.ingestion.yahoo_loader import fetch_prices

FIXTURES = Path(__file__).parent / "fixtures" / "http"


def _yf_ohlcv_frame(csv_name: str) -> pd.DataFrame:
    """Shape a fixture CSV like a typical yfinance single-ticker download."""
    raw = pd.read_csv(FIXTURES / csv_name, parse_dates=["date"])
    frame = raw.rename(
        columns={
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "adj_close": "Adj Close",
            "volume": "Volume",
        }
    ).set_index("Date")
    return frame


def _yf_close_frame(csv_name: str) -> pd.DataFrame:
    raw = pd.read_csv(FIXTURES / csv_name, parse_dates=["date"])
    return raw.rename(columns={"date": "Date", "close": "Close"}).set_index("Date")


@responses.activate
def test_rba_cash_rate_contract_from_fixture():
    body = (FIXTURES / "rba_f1_1_sample.csv").read_text(encoding="utf-8")
    url = "https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv"
    responses.add(responses.GET, url, body=body, status=200)

    result = fetch_cash_rate(url=url)

    assert list(result.columns) == ["date", "cash_rate"]
    assert len(result) == 3
    assert result.iloc[-1]["cash_rate"] == pytest.approx(4.60)


@responses.activate
def test_abs_cpi_contract_from_sdmx_fixture():
    payload = json.loads((FIXTURES / "abs_cpi_sdmx_sample.json").read_text(encoding="utf-8"))
    url = "https://api.data.abs.gov.au/data/CPI/fixture"
    responses.add(responses.GET, url, json=payload, status=200)

    result = fetch_cpi(api_url=url, fallback_csv="data/raw/does-not-exist.csv")

    assert list(result.columns) == ["date", "cpi"]
    assert len(result) == 3
    assert result.iloc[-1]["cpi"] == pytest.approx(3.4)


@responses.activate
def test_abs_cpi_fallback_csv_when_api_fails(tmp_path):
    fallback = tmp_path / "abs_cpi.csv"
    fallback.write_text("date,cpi\n2026-01-01,3.1\n2026-04-01,3.2\n", encoding="utf-8")
    responses.add(responses.GET, "https://api.data.abs.gov.au/data/CPI/fail", status=503)

    result = fetch_cpi(api_url="https://api.data.abs.gov.au/data/CPI/fail", fallback_csv=str(fallback))

    assert len(result) == 2
    assert result.iloc[0]["cpi"] == pytest.approx(3.1)


def test_yahoo_price_contract_uses_fixture(monkeypatch):
    frame = _yf_ohlcv_frame("yahoo_cba_ohlcv.csv")

    def fake_download(symbol, **kwargs):  # noqa: ARG001
        assert symbol == "CBA.AX"
        return frame

    monkeypatch.setattr(yahoo_loader.yf, "download", fake_download)
    result = fetch_prices("CBA", period="5d")

    assert list(result.columns) == ["date", "open", "high", "low", "close", "adj_close", "volume"]
    assert len(result) == 3
    assert result.iloc[0]["close"] == pytest.approx(101.5)


def test_aud_usd_contract_uses_fixture(monkeypatch):
    frame = _yf_close_frame("yahoo_audusd.csv")

    def fake_download(symbol, **kwargs):  # noqa: ARG001
        assert symbol == "AUDUSD=X"
        return frame

    monkeypatch.setattr(rba_loader.yf, "download", fake_download)
    result = fetch_aud_usd(period="5d")

    assert list(result.columns) == ["date", "aud_usd"]
    assert len(result) == 3
    assert result.iloc[1]["aud_usd"] == pytest.approx(0.6615)


def test_iron_ore_contract_uses_fixture(monkeypatch):
    frame = _yf_close_frame("yahoo_iron_ore.csv")

    def fake_download(symbol, **kwargs):  # noqa: ARG001
        assert symbol == "TIO=F"
        return frame

    monkeypatch.setattr(rba_loader.yf, "download", fake_download)
    result = fetch_iron_ore(period="5d")

    assert list(result.columns) == ["date", "iron_ore_price"]
    assert len(result) == 3
    assert result.iloc[-1]["iron_ore_price"] == pytest.approx(109.25)
