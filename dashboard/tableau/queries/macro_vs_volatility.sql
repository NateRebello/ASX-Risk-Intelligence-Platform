-- Page 4: Macro Analysis
-- ASX-wide volatility joined against macro series for the dual-axis /
-- scatter charts.
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
ORDER BY v.date;
