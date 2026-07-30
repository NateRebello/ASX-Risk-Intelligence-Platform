# Tableau Dashboard — ASX Risk Intelligence Platform

This folder contains source SQL and instructions for building the Tableau
dashboard described in Milestone 6.

Start with [`TABLEAU_DESKTOP_SETUP.md`](TABLEAU_DESKTOP_SETUP.md). It is the
supported, click-by-click workflow for creating a Tableau Desktop workbook
through the PostgreSQL connector and Custom SQL interface.

`asx_risk_starter.twb` is retained only as an XML reference for the four
data-source queries. It is not a supported Tableau Desktop workbook.

`queries/` contains the raw SQL behind each panel, suitable for Tableau
Custom SQL or execution in another PostgreSQL client.

## Connecting Tableau to Postgres

* Tableau Desktop → **Connect → To a Server → PostgreSQL**.
* Server: `localhost` (or your RDS endpoint), Port `5432`, Database `asx_risk`.
* Use a **read-only** DB user in production (`GRANT SELECT` only) rather
  than the app's write credentials.
* For a live dashboard, use a **Live** connection; for scheduled snapshots,
  use an **Extract** refreshed via Tableau Server/Online's REST API after
  each ETL run (see Milestone 7 / `scripts/tableau_refresh.py`).

## Dashboard Layout

### Page 1 — Market Overview
* Big KPI: current ASX regime (Normal/Elevated/Stress), colored
  green/amber/red.
* ASX 200 index line chart with a colored background band per regime
  (query: `queries/market_overview.sql`).
* Summary stat cards: current 30-day annualized volatility, latest
  portfolio VaR, top single-name risk contributor.

### Page 2 — Risk Metrics
* Time series of rolling volatility (30d) with drawdown shaded beneath.
* Heatmap of pairwise sector/asset correlations (`queries/correlation_heatmap.sql`).
* Table of per-asset risk contributions, sorted descending.

### Page 3 — Sector & Portfolio View
* Pie chart: portfolio exposure by sector (`queries/sector_exposure.sql`).
* Bar chart: sector-wise risk contribution % (from `sector_risk_contributions`).
* Top-5 assets by marginal risk contribution.

### Page 4 — Macro Analysis
* Dual-axis line chart: RBA cash rate vs 30-day ASX volatility
  (`queries/macro_vs_volatility.sql`).
* Scatter plot: daily volatility vs AUD/USD level, colored by regime.
* CPI trend line with volatility overlay.

## Screenshot placeholders

Once built in Tableau Desktop, export screenshots/PNGs here for the README:

* `../../docs/dashboard_overview.png`
* `../../docs/dashboard_risk_metrics.png`
* `../../docs/dashboard_sector_view.png`
* `../../docs/dashboard_macro.png`
