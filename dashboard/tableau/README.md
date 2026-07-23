# Tableau Dashboard — ASX Risk Intelligence Platform

This folder contains everything needed to build/refresh the Tableau
dashboard described in Milestone 6. Tableau workbooks are binary/XML
artifacts normally authored interactively in Tableau Desktop, so rather
than ship an unverifiable `.twbx`, this folder ships:

1. `asx_risk_starter.twb` — a starter workbook XML with the PostgreSQL
   connection and named custom-SQL data sources pre-wired for each
   dashboard page. Open it in Tableau Desktop (File → Open), enter your
   DB credentials when prompted, and build the visualizations below on
   top of the provided data sources.
2. `queries/` — the raw SQL behind each panel, in case you'd rather build
   the data sources manually or query the extracts elsewhere first (Excel,
   Power BI, Superset — the SQL is engine-agnostic Postgres).

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
