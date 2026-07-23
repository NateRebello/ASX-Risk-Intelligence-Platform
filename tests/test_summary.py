import datetime as dt

from src.reports.executive_summary import BriefingInputs, build_summary


def test_build_summary_basic_format():
    data = BriefingInputs(
        as_of_date=dt.date(2026, 7, 22),
        regime="Elevated",
        market_vol_pct=0.22,
        top_contributors=[("Financials", 0.40), ("Materials", 0.30), ("CSL", 0.15)],
        var_95=0.028,
        cvar_95=0.035,
        cash_rate=4.60,
        cash_rate_change=0.25,
        aud_usd=0.68,
    )
    summary = build_summary(data)

    assert "22 Jul 2026" in summary
    assert "Elevated" in summary
    assert "22%" in summary or "22.0%" in summary
    assert "Financials (40%)" in summary
    assert "2.8%" in summary  # VaR
    assert "3.5%" in summary  # CVaR
    assert "hiked" in summary  # positive cash rate change
    assert "0.68" in summary


def test_build_summary_handles_missing_optional_fields():
    """Should not crash / should omit lines when portfolio metrics or macro
    data aren't available (e.g. no portfolio_id was passed)."""
    data = BriefingInputs(
        as_of_date=dt.date(2026, 7, 22),
        regime="Normal",
        market_vol_pct=None,
    )
    summary = build_summary(data)
    assert "Normal" in summary
    assert "VaR" not in summary
    assert "Action Items" in summary


def test_action_items_differ_by_regime():
    stress = build_summary(BriefingInputs(as_of_date=dt.date(2026, 1, 1), regime="Stress", market_vol_pct=0.4))
    normal = build_summary(BriefingInputs(as_of_date=dt.date(2026, 1, 1), regime="Normal", market_vol_pct=0.1))
    assert stress != normal
    assert "Reduce risk exposure" in stress
    assert "No immediate action" in normal


def test_cash_rate_cut_uses_correct_verb():
    data = BriefingInputs(
        as_of_date=dt.date(2026, 1, 1),
        regime="Normal",
        market_vol_pct=0.1,
        cash_rate=4.10,
        cash_rate_change=-0.25,
    )
    summary = build_summary(data)
    assert "cut" in summary
