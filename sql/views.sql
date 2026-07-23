-- Example SQL views used by analytics scripts, ad-hoc queries, and the
-- Tableau dashboard (Milestones 2 & 6).

-- Daily returns computed directly in SQL (mirrors src/analytics/returns.py;
-- handy for quick ad-hoc checks without spinning up Python).
CREATE OR REPLACE VIEW daily_returns_sql AS
SELECT
    dp.date,
    dp.ticker,
    (dp.adj_close / LAG(dp.adj_close) OVER (PARTITION BY dp.ticker ORDER BY dp.date) - 1) AS daily_return,
    LN(dp.adj_close / LAG(dp.adj_close) OVER (PARTITION BY dp.ticker ORDER BY dp.date)) AS log_return
FROM daily_prices dp;

-- Latest volatility + regime per ticker (for dashboard "current state" cards).
CREATE OR REPLACE VIEW latest_volatility AS
SELECT v.*
FROM volatility v
JOIN (
    SELECT ticker, MAX(date) AS max_date FROM volatility GROUP BY ticker
) latest ON v.ticker = latest.ticker AND v.date = latest.max_date;

-- Sector-level exposure for a given portfolio (Milestone 4/6).
CREATE OR REPLACE VIEW portfolio_sector_exposure AS
SELECT
    ph.portfolio_id,
    s.sector,
    SUM(ph.weight) AS exposure
FROM portfolio_holdings ph
JOIN stocks s USING (ticker)
GROUP BY ph.portfolio_id, s.sector;

-- Pairwise return correlation (small universes only — O(n^2) rows).
CREATE OR REPLACE VIEW pairwise_correlation AS
SELECT
    a.ticker AS ticker_a,
    b.ticker AS ticker_b,
    CORR(a.daily_return, b.daily_return) AS correlation
FROM returns a
JOIN returns b ON a.date = b.date AND a.ticker < b.ticker
GROUP BY a.ticker, b.ticker;

-- Portfolio daily return time series (weighted sum of holdings' returns).
CREATE OR REPLACE VIEW portfolio_daily_return AS
SELECT
    ph.portfolio_id,
    r.date,
    SUM(r.daily_return * ph.weight) AS portfolio_return
FROM returns r
JOIN portfolio_holdings ph USING (ticker)
GROUP BY ph.portfolio_id, r.date
ORDER BY ph.portfolio_id, r.date;

-- ASX-wide "market" regime per day: majority vote of the percentile regime
-- across all tickers (a simple proxy for an index-level regime label).
CREATE OR REPLACE VIEW market_regime_daily AS
SELECT
    date,
    regime,
    COUNT(*) AS ticker_count
FROM volatility
WHERE regime IS NOT NULL
GROUP BY date, regime
ORDER BY date;

-- Macro vs volatility join, used by the Macro Analysis dashboard page.
CREATE OR REPLACE VIEW volatility_macro_join AS
SELECT
    v.date,
    v.ticker,
    v.rolling_vol,
    v.regime,
    m.cash_rate,
    m.cpi,
    m.aud_usd,
    m.iron_ore_price
FROM volatility v
LEFT JOIN macro m ON v.date = m.date;
