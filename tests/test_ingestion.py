import responses

from src.ingestion.rba_loader import fetch_cash_rate
from src.ingestion.yahoo_loader import _none_if_nan, load_universe

# A trimmed but structurally faithful sample of the real RBA F1.1 CSV
# format (verified against https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv):
# title row, then a header row, several metadata rows, then data rows.
SAMPLE_RBA_CSV = (
    "F1.1 INTEREST RATES AND YIELDS - MONEY MARKET\n"
    "Title,Cash Rate Target,Interbank Overnight Cash Rate\n"
    "Description,Cash Rate Target; monthly average,Interbank Overnight Cash Rate\n"
    "Frequency,Monthly,Monthly\n"
    "Type,Original,Original\n"
    "Units,Per cent,Per cent\n"
    "\n"
    "Source,RBA,RBA\n"
    "Publication date,01-Jul-2026,01-Jul-2026\n"
    "Series ID,FIRMMCRT,FIRMMCRI\n"
    "31/05/2026,4.35,4.34\n"
    "30/06/2026,4.35,4.33\n"
    "31/07/2026,4.60,4.58\n"
)


def test_load_universe_default_matches_settings_when_no_file():
    universe = load_universe(tickers_file="")
    assert len(universe) > 0
    assert {"ticker", "name", "sector", "industry"}.issubset(universe[0].keys())


def test_none_if_nan_converts_nan_to_none():
    assert _none_if_nan(float("nan")) is None
    assert _none_if_nan(1.23) == 1.23


@responses.activate
def test_fetch_cash_rate_parses_real_rba_csv_format():
    url = "https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv"
    responses.add(responses.GET, url, body=SAMPLE_RBA_CSV, status=200)

    result = fetch_cash_rate(url=url)

    assert list(result.columns) == ["date", "cash_rate"]
    assert len(result) == 3
    assert result.iloc[-1]["cash_rate"] == 4.60
    # metadata rows (Description, Frequency, ...) must not leak into the data
    assert not result["date"].astype(str).str.contains("Description|Frequency|Source").any()
