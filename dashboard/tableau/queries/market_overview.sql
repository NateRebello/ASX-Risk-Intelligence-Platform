-- Page 1: Market Overview
-- ASX-wide (cross-sectional average) volatility & majority regime per day,
-- suitable for a line chart with a colored background band per regime.
SELECT
    date,
    AVG(rolling_vol) AS avg_rolling_vol,
    MODE() WITHIN GROUP (ORDER BY regime) AS market_regime
FROM volatility
WHERE rolling_vol IS NOT NULL
GROUP BY date
ORDER BY date;
