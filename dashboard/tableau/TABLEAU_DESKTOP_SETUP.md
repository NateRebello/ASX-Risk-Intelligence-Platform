# Tableau Desktop setup

The supplied `asx_risk_starter.twb` is an XML reference artifact, not a
supported Tableau Desktop workbook. Build the workbook through Tableau
Desktop's PostgreSQL connector and Custom SQL interface instead.

## Prerequisites

Before opening Tableau, confirm all of the following:

1. The SSM port-forwarding terminal remains open on the Tableau Desktop host.
2. `Test-NetConnection localhost -Port 5432` returns
   `TcpTestSucceeded : True`.
3. The read-only `asx_risk_tableau` user can connect to `asx_risk`.
4. Data exists:

```sql
SELECT COUNT(*) AS volatility_rows FROM volatility;
SELECT COUNT(*) AS portfolio_count FROM portfolios;
SELECT COUNT(*) AS sector_contribution_rows FROM sector_risk_contributions;
```

`volatility_rows` must be greater than zero for Market Overview and Macro
Analysis. Seed a portfolio before building Sector & Portfolio:

```bash
python scripts/seed_demo_portfolio.py \
  --name "Demo Equal-Weight 5" \
  --tickers CBA BHP CSL WES TLS
```

## Connect Tableau Desktop

1. Open Tableau Desktop and select **File → New**.
2. Under **Connect → To a Server**, select **PostgreSQL**.
3. Enter:
   - Server: `localhost`
   - Port: `5432`
   - Database: `asx_risk`
   - Username: `asx_risk_tableau`
   - Password: the reporting-user password
   - SSL: require SSL, when Tableau offers the option
4. Select **Sign In**.
5. Select **Live** for development. Do not configure an extract until a
   refresh host or Tableau Bridge is available.

## Add a Custom SQL source

Repeat this sequence for each query:

1. On the Data Source page, select **New Custom SQL**.
2. Paste one query below, without its trailing semicolon.
3. Select **OK** and give the source the shown name.
4. Select a new worksheet.

### Market Overview

Name: `Market Overview`

```sql
SELECT
  date,
  AVG(rolling_vol) AS avg_rolling_vol,
  MODE() WITHIN GROUP (ORDER BY regime) AS market_regime
FROM volatility
WHERE rolling_vol IS NOT NULL
GROUP BY date
ORDER BY date
```

Create worksheet `Market Volatility`:

1. Drag `date` to Columns and set it to a continuous date.
2. Drag `avg_rolling_vol` to Rows.
3. Select Line in Marks.
4. Drag `market_regime` to Color.
5. Format `avg_rolling_vol` as a percentage.
6. Set title to `ASX Market — Average 30-Day Annualised Volatility`.

Create worksheet `Current Regime`:

1. Create calculation `Is Latest Date`:

```text
[date] = { FIXED : MAX([date]) }
```

2. Filter `Is Latest Date` to `True`.
3. Drag `market_regime` and `avg_rolling_vol` to Text.
4. Increase font size and format volatility as a percentage.

### Correlation Heatmap

Create a new data source via **Data → New Data Source → PostgreSQL**, then
choose New Custom SQL.

Name: `Correlation Heatmap`

```sql
SELECT
  a.ticker AS ticker_a,
  b.ticker AS ticker_b,
  CORR(a.daily_return, b.daily_return) AS correlation
FROM returns a
JOIN returns b ON a.date = b.date AND a.ticker <> b.ticker
GROUP BY a.ticker, b.ticker
```

Create worksheet `Correlation Heatmap`:

1. Drag `ticker_a` to Rows and `ticker_b` to Columns.
2. Set Marks to Square.
3. Drag `correlation` to Color and Label.
4. Edit Colors: choose a diverging palette, range `-1` to `1`, center `0`.
5. Format labels to two decimal places.

### Sector Exposure

Create a new PostgreSQL Custom SQL data source.

Name: `Sector Exposure`

```sql
SELECT
  s.sector,
  SUM(ph.weight) AS exposure
FROM portfolio_holdings ph
JOIN stocks s USING (ticker)
GROUP BY s.sector
ORDER BY exposure DESC
```

Create worksheet `Sector Exposure`:

1. Set Marks to Pie.
2. Drag `sector` to Color.
3. Drag `exposure` to Angle and Label.
4. Format `exposure` as a percentage.
5. Sort descending by `SUM(exposure)`.

### Sector Risk Contribution

Record the `portfolio_id` returned by:

```sql
SELECT portfolio_id, name FROM portfolios;
```

Create a new PostgreSQL Custom SQL source. Replace `1` with that id.

Name: `Sector Risk Contribution`

```sql
SELECT
  sector,
  weight,
  risk_contribution_pct
FROM sector_risk_contributions
WHERE portfolio_id = 1
  AND date = (
    SELECT MAX(date)
    FROM sector_risk_contributions
    WHERE portfolio_id = 1
  )
ORDER BY risk_contribution_pct DESC
```

Create worksheet `Sector Risk Contribution`:

1. Drag `sector` to Rows.
2. Drag `risk_contribution_pct` to Columns and Label.
3. Set Marks to Bar.
4. Format `risk_contribution_pct` as a percentage.

### Macro vs Volatility

Create a new PostgreSQL Custom SQL data source.

Name: `Macro vs Volatility`

```sql
SELECT
  v.date,
  AVG(v.rolling_vol) AS avg_rolling_vol,
  m.cash_rate,
  m.cpi,
  m.aud_usd,
  m.iron_ore_price
FROM volatility v
LEFT JOIN macro m ON v.date = m.date
GROUP BY v.date, m.cash_rate, m.cpi, m.aud_usd, m.iron_ore_price
ORDER BY v.date
```

Create worksheet `Cash Rate vs Volatility`:

1. Drag `date` to Columns as a continuous date.
2. Drag `avg_rolling_vol` to Rows, then drag `cash_rate` alongside it.
3. Right-click the second axis and select Dual Axis.
4. Do not synchronize axes; the measures have different units.
5. Set each Marks card to Line with distinct colors.
6. Format both measures as percentages.

Create worksheet `Volatility vs AUD/USD`:

1. Drag `aud_usd` to Columns.
2. Drag `avg_rolling_vol` to Rows.
3. Drag `date` to Detail.
4. Set Marks to Circle.

The supplied macro source has no regime column, so do not claim the scatter
is colored by regime unless a later query adds a daily regime field.

## Assemble dashboards

Create four dashboards at a fixed desktop size of `1366 × 768`:

1. `1 — Market Overview`: Market Volatility and Current Regime.
2. `2 — Risk Metrics`: Correlation Heatmap.
3. `3 — Sector & Portfolio`: Sector Exposure and Sector Risk Contribution.
4. `4 — Macro Analysis`: Cash Rate vs Volatility and Volatility vs AUD/USD.

On each, add a footer:

```text
Data: PostgreSQL RDS | Connection: live via SSM port forward | Refresh: manual
```

Save the finished workbook as `asx_risk_dashboard_local.twb`. Do not overwrite
the starter XML reference.

## Validate each dashboard

Run the corresponding Custom SQL in `psql`, then compare row count, latest
date, and displayed values with Tableau. Validate sector totals sum to 100%
and use the same `portfolio_id` in SQL and Tableau.

## Production connectivity

The laptop + SSM tunnel is development-only.

- Tableau Server in the VPC can use a live RDS connection.
- Tableau Cloud requires Tableau Bridge on a VPC-connected host, or extracts.
- `scripts/tableau_refresh.py` can call Tableau Server/Cloud's refresh API,
  but it is not yet scheduled by the AWS pipeline.
