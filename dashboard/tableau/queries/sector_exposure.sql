-- Page 3: Sector & Portfolio View
-- Exposure by sector for a given portfolio.
SELECT
    s.sector,
    SUM(ph.weight) AS exposure
FROM portfolio_holdings ph
JOIN stocks s USING (ticker)
WHERE ph.portfolio_id = :portfolio_id
GROUP BY s.sector
ORDER BY exposure DESC;

-- Sector-wise risk contribution % (latest date).
SELECT sector, weight, risk_contribution_pct
FROM sector_risk_contributions
WHERE portfolio_id = :portfolio_id
  AND date = (SELECT MAX(date) FROM sector_risk_contributions WHERE portfolio_id = :portfolio_id)
ORDER BY risk_contribution_pct DESC;
