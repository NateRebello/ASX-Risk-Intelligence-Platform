"""
Milestone 6 — Daily executive risk briefing generator.

Pulls the latest regime, portfolio VaR/CVaR, sector risk drivers, and macro
context from the warehouse and renders a short markdown briefing, mirroring
the format real risk desks circulate each morning.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class BriefingInputs:
    as_of_date: dt.date
    regime: str
    market_vol_pct: float | None
    top_contributors: list[tuple[str, float]] = field(default_factory=list)  # (sector/ticker, pct)
    var_95: float | None = None
    cvar_95: float | None = None
    cash_rate: float | None = None
    cash_rate_change: float | None = None
    aud_usd: float | None = None
    correlation_note: str | None = None


def build_summary(data: BriefingInputs) -> str:
    """Render a BriefingInputs into the markdown executive summary format."""
    lines = [f"**ASX Market Risk Summary – {data.as_of_date.strftime('%d %b %Y')}**", ""]

    vol_txt = f" (30-day vol = {data.market_vol_pct:.1%})" if data.market_vol_pct is not None else ""
    lines.append(f"- **Volatility Regime:** {data.regime}{vol_txt}.")

    if data.top_contributors:
        parts = ", ".join(f"{name} ({pct:.0%})" for name, pct in data.top_contributors)
        lines.append(f"- **Top Risk Contributors:** {parts}.")

    if data.var_95 is not None and data.cvar_95 is not None:
        lines.append(f"- **Portfolio VaR/CVaR:** 1-day 95% VaR = {data.var_95:.1%}; CVaR = {data.cvar_95:.1%}.")

    macro_bits = []
    if data.cash_rate is not None:
        chg = ""
        if data.cash_rate_change:
            direction = "hiked" if data.cash_rate_change > 0 else "cut"
            chg = f" (RBA {direction} {abs(data.cash_rate_change):.2f}pp)"
        macro_bits.append(f"cash rate {data.cash_rate:.2f}%{chg}")
    if data.aud_usd is not None:
        macro_bits.append(f"AUD/USD {data.aud_usd:.4f}")
    if macro_bits:
        lines.append(f"- **Macro Update:** {'; '.join(macro_bits)}.")

    if data.correlation_note:
        lines.append(f"- **Cross-Asset Note:** {data.correlation_note}")

    lines.append(f"- **Action Items:** {_action_items(data)}")
    return "\n".join(lines)


def _action_items(data: BriefingInputs) -> str:
    if data.regime == "Stress":
        return "Reduce risk exposure, review hedges, and monitor for further volatility spikes."
    if data.regime == "Elevated":
        top = data.top_contributors[0][0] if data.top_contributors else "the top-weighted sector"
        return f"Monitor {top} closely and consider trimming concentrated positions."
    return "No immediate action required — maintain current allocations and monitor regime shifts."


# --------------------------------------------------------------------------
# DB wiring
# --------------------------------------------------------------------------
def fetch_latest_regime(engine: Engine) -> tuple[dt.date | None, str | None, float | None]:
    query = """
        SELECT date, regime, AVG(rolling_vol) AS avg_vol
        FROM volatility
        WHERE date = (SELECT MAX(date) FROM volatility)
        GROUP BY date, regime
        ORDER BY COUNT(*) DESC
        LIMIT 1
    """
    row = pd.read_sql(text(query), engine)
    if row.empty:
        return None, None, None
    return (
        row.iloc[0]["date"],
        row.iloc[0]["regime"],
        float(row.iloc[0]["avg_vol"]) if pd.notna(row.iloc[0]["avg_vol"]) else None,
    )


def fetch_latest_portfolio_metrics(engine: Engine, portfolio_id: int) -> pd.Series | None:
    query = """
        SELECT * FROM portfolio_metrics
        WHERE portfolio_id = :pid
        ORDER BY date DESC LIMIT 1
    """
    df = pd.read_sql(text(query), engine, params={"pid": portfolio_id})
    return df.iloc[0] if not df.empty else None


def fetch_top_sector_contributors(engine: Engine, portfolio_id: int, top_n: int = 3) -> list[tuple[str, float]]:
    query = """
        SELECT sector, risk_contribution_pct FROM sector_risk_contributions
        WHERE portfolio_id = :pid AND date = (
            SELECT MAX(date) FROM sector_risk_contributions WHERE portfolio_id = :pid
        )
        ORDER BY risk_contribution_pct DESC LIMIT :n
    """
    df = pd.read_sql(text(query), engine, params={"pid": portfolio_id, "n": top_n})
    return [(row.sector, row.risk_contribution_pct / 100.0) for row in df.itertuples(index=False)]


def fetch_latest_macro(engine: Engine) -> tuple[float | None, float | None, float | None]:
    query = "SELECT cash_rate, aud_usd FROM macro ORDER BY date DESC LIMIT 2"
    df = pd.read_sql(text(query), engine)
    if df.empty:
        return None, None, None
    latest = df.iloc[0]
    change = None
    if len(df) > 1 and pd.notna(latest["cash_rate"]) and pd.notna(df.iloc[1]["cash_rate"]):
        change = float(latest["cash_rate"] - df.iloc[1]["cash_rate"])
    return (
        float(latest["cash_rate"]) if pd.notna(latest["cash_rate"]) else None,
        change,
        float(latest["aud_usd"]) if pd.notna(latest["aud_usd"]) else None,
    )


def run(portfolio_id: int | None = None) -> str:
    from src.db.engine import get_engine

    engine = get_engine()
    as_of, regime, vol = fetch_latest_regime(engine)
    cash_rate, cash_rate_change, aud_usd = fetch_latest_macro(engine)

    var_95 = cvar_95 = None
    contributors: list[tuple[str, float]] = []
    if portfolio_id is not None:
        metrics = fetch_latest_portfolio_metrics(engine, portfolio_id)
        if metrics is not None:
            var_95, cvar_95 = metrics.get("var_95"), metrics.get("cvar_95")
        contributors = fetch_top_sector_contributors(engine, portfolio_id)

    data = BriefingInputs(
        as_of_date=as_of or dt.date.today(),
        regime=regime or "Unknown",
        market_vol_pct=vol,
        top_contributors=contributors,
        var_95=var_95,
        cvar_95=cvar_95,
        cash_rate=cash_rate,
        cash_rate_change=cash_rate_change,
        aud_usd=aud_usd,
    )
    summary = build_summary(data)
    logger.info("\n%s", summary)
    return summary


def lambda_handler(event: dict, context) -> dict:  # noqa: ANN001
    portfolio_id = (event or {}).get("portfolio_id")
    summary = run(portfolio_id=portfolio_id)
    return {"statusCode": 200, "summary": summary}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate the daily ASX risk executive briefing")
    parser.add_argument("--portfolio-id", type=int, default=None)
    parser.add_argument("--out", default=None, help="Optional path to write the markdown briefing to")
    args = parser.parse_args(argv)
    summary = run(portfolio_id=args.portfolio_id)
    if args.out:
        from pathlib import Path

        Path(args.out).write_text(summary, encoding="utf-8")
    else:
        print(summary)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
