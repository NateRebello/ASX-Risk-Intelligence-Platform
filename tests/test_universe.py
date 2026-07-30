"""Milestone/ADR 0001 — runtime ASX universe resolution.

Covers: CSV validation (columns, duplicates), the settings.yaml-driven
ASX 50 default, and switching to ASX 200 purely via configuration (SSM
filename lookup), with no application code changes.
"""

import pandas as pd
import pytest

from src.universe import loader as universe_loader


def test_committed_asx50_csv_is_valid_and_has_fifty_rows():
    df = universe_loader.load_from_local_file("asx50.csv")
    assert len(df) == 50
    assert set(df.columns) == universe_loader.REQUIRED_COLUMNS


def test_committed_asx200_csv_is_valid_and_has_two_hundred_rows():
    df = universe_loader.load_from_local_file("asx200.csv")
    assert len(df) == 200
    assert set(df.columns) == universe_loader.REQUIRED_COLUMNS


def test_asx50_is_a_subset_of_asx200_by_ticker():
    asx50 = set(universe_loader.load_from_local_file("asx50.csv")["ticker"])
    asx200 = set(universe_loader.load_from_local_file("asx200.csv")["ticker"])
    assert asx50.issubset(asx200)


def test_validate_rejects_missing_columns():
    df = pd.DataFrame({"ticker": ["CBA"], "name": ["Commonwealth Bank"]})
    with pytest.raises(universe_loader.UniverseValidationError, match="missing columns"):
        universe_loader._validate(df, source="test")


def test_validate_rejects_duplicate_tickers():
    df = pd.DataFrame(
        {
            "ticker": ["CBA", "cba"],
            "name": ["Commonwealth Bank", "Commonwealth Bank"],
            "sector": ["Financials", "Financials"],
            "industry": ["Banks", "Banks"],
        }
    )
    with pytest.raises(universe_loader.UniverseValidationError, match="duplicate tickers"):
        universe_loader._validate(df, source="test")


def test_validate_rejects_empty_frame():
    df = pd.DataFrame(columns=["ticker", "name", "sector", "industry"])
    with pytest.raises(universe_loader.UniverseValidationError, match="no rows"):
        universe_loader._validate(df, source="test")


def test_default_selection_is_asx50_from_settings_yaml(monkeypatch):
    monkeypatch.setattr(universe_loader, "active_filename_from_ssm", lambda: None)
    assert universe_loader.resolve_active_filename() == "asx50.csv"


def test_ssm_override_switches_to_asx200_without_code_change(monkeypatch):
    """Simulates `aws ssm put-parameter ... --value asx200.csv` — the active
    filename changes purely via configuration, no code path changes."""
    monkeypatch.setattr(universe_loader, "active_filename_from_ssm", lambda: "asx200.csv")
    monkeypatch.setattr(universe_loader, "load_from_s3", lambda filename: None)

    assert universe_loader.resolve_active_filename() == "asx200.csv"
    universe = universe_loader.load_universe()
    assert len(universe) == 200


def test_explicit_tickers_file_overrides_everything(tmp_path, monkeypatch):
    custom = tmp_path / "custom.csv"
    custom.write_text("ticker,name,sector,industry\nCBA,Commonwealth Bank,Financials,Banks\n", encoding="utf-8")

    monkeypatch.setattr(universe_loader, "active_filename_from_ssm", lambda: "asx200.csv")

    universe = universe_loader.load_universe(tickers_file=str(custom))

    assert universe == [{"ticker": "CBA", "name": "Commonwealth Bank", "sector": "Financials", "industry": "Banks"}]


def test_s3_source_takes_precedence_over_local_file(monkeypatch):
    fake_df = pd.DataFrame(
        [{"ticker": "XYZ", "name": "Test Co", "sector": "Financials", "industry": "Banks"}]
    )
    monkeypatch.setattr(universe_loader, "active_filename_from_ssm", lambda: None)
    monkeypatch.setattr(universe_loader, "load_from_s3", lambda filename: fake_df)

    universe = universe_loader.load_universe()

    assert universe == [{"ticker": "XYZ", "name": "Test Co", "sector": "Financials", "industry": "Banks"}]


def test_falls_back_to_default_universe_when_local_file_missing(monkeypatch):
    monkeypatch.setattr(universe_loader, "active_filename_from_ssm", lambda: "does-not-exist.csv")
    monkeypatch.setattr(universe_loader, "load_from_s3", lambda filename: None)

    universe = universe_loader.load_universe()

    from config import settings

    assert universe == settings.DEFAULT_UNIVERSE


def test_active_filename_from_ssm_returns_none_on_any_error(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "MARKET_UNIVERSE_SSM_PARAM", "/asx-risk/platform/market-universe")

    def boom(*args, **kwargs):
        raise RuntimeError("no AWS credentials in this environment")

    class FakeBoto3:
        @staticmethod
        def client(*args, **kwargs):
            raise RuntimeError("no AWS credentials in this environment")

    monkeypatch.setitem(__import__("sys").modules, "boto3", FakeBoto3())

    assert universe_loader.active_filename_from_ssm() is None
