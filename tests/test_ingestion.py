import responses

from src.ingestion.rba_loader import fetch_cash_rate
from src.ingestion.yahoo_loader import _none_if_nan, load_universe
from src.universe import loader as universe_loader
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "http"


def test_load_universe_default_matches_settings_when_no_file(monkeypatch):
    """With no explicit override, SSM/S3 unavailable, this resolves to the
    local settings.yaml default (asx50.csv) — see src/universe/loader.py."""
    monkeypatch.setattr(universe_loader, "active_filename_from_ssm", lambda: None)
    monkeypatch.setattr(universe_loader, "load_from_s3", lambda filename: None)

    universe = load_universe(tickers_file="")

    assert len(universe) == 50
    assert {"ticker", "name", "sector", "industry"}.issubset(universe[0].keys())


def test_none_if_nan_converts_nan_to_none():
    assert _none_if_nan(float("nan")) is None
    assert _none_if_nan(1.23) == 1.23


@responses.activate
def test_fetch_cash_rate_parses_real_rba_csv_format():
    url = "https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv"
    body = (FIXTURES / "rba_f1_1_sample.csv").read_text(encoding="utf-8")
    responses.add(responses.GET, url, body=body, status=200)

    result = fetch_cash_rate(url=url)

    assert list(result.columns) == ["date", "cash_rate"]
    assert len(result) == 3
    assert result.iloc[-1]["cash_rate"] == 4.60
    # metadata rows (Description, Frequency, ...) must not leak into the data
    assert not result["date"].astype(str).str.contains("Description|Frequency|Source").any()
