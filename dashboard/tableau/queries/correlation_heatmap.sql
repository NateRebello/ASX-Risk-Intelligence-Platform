-- Page 2: Risk Metrics — pairwise return correlation heatmap.
SELECT
    a.ticker AS ticker_a,
    b.ticker AS ticker_b,
    CORR(a.daily_return, b.daily_return) AS correlation
FROM returns a
JOIN returns b ON a.date = b.date AND a.ticker <> b.ticker
GROUP BY a.ticker, b.ticker;

-- Per-asset risk contribution table (latest date, for a given portfolio).
-- :portfolio_id is a Tableau parameter bound to a selector control.
-- SELECT ticker, weight, marginal_contribution, pct_contribution
-- FROM portfolio_risk_contributions   -- (materialized by portfolio/attribution.py)
-- WHERE portfolio_id = :portfolio_id AND date = (
--     SELECT MAX(date) FROM portfolio_risk_contributions WHERE portfolio_id = :portfolio_id
-- );
