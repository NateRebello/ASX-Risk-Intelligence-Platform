-- ASX Risk Intelligence Platform — core warehouse schema.
-- Idempotent: safe to re-run (uses IF NOT EXISTS / CREATE OR REPLACE where possible).

CREATE TABLE IF NOT EXISTS stocks (
    ticker    TEXT PRIMARY KEY,
    name      TEXT,
    sector    TEXT,
    industry  TEXT
);

CREATE TABLE IF NOT EXISTS daily_prices (
    date       DATE NOT NULL,
    ticker     TEXT NOT NULL REFERENCES stocks(ticker),
    open       NUMERIC,
    high       NUMERIC,
    low        NUMERIC,
    close      NUMERIC,
    adj_close  NUMERIC,
    volume     BIGINT,
    PRIMARY KEY (date, ticker)
);
CREATE INDEX IF NOT EXISTS idx_daily_prices_ticker ON daily_prices(ticker);
CREATE INDEX IF NOT EXISTS idx_daily_prices_date ON daily_prices(date);

CREATE TABLE IF NOT EXISTS returns (
    date          DATE NOT NULL,
    ticker        TEXT NOT NULL REFERENCES stocks(ticker),
    daily_return  NUMERIC,
    log_return    NUMERIC,
    PRIMARY KEY (date, ticker)
);

CREATE TABLE IF NOT EXISTS volatility (
    date          DATE NOT NULL,
    ticker        TEXT NOT NULL REFERENCES stocks(ticker),
    rolling_vol   NUMERIC,          -- annualized rolling volatility
    regime        TEXT,             -- 'Normal' | 'Elevated' | 'Stress'
    regime_hmm    INTEGER,          -- hidden state index from GaussianHMM
    PRIMARY KEY (date, ticker)
);

CREATE TABLE IF NOT EXISTS macro (
    date            DATE PRIMARY KEY,
    cash_rate       NUMERIC,
    cpi             NUMERIC,
    unemployment    NUMERIC,
    aud_usd         NUMERIC,
    iron_ore_price  NUMERIC
);

CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id  SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_holdings (
    portfolio_id  INTEGER REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    ticker        TEXT REFERENCES stocks(ticker),
    weight        NUMERIC NOT NULL,
    PRIMARY KEY (portfolio_id, ticker)
);

CREATE TABLE IF NOT EXISTS portfolio_metrics (
    portfolio_id  INTEGER REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    date          DATE,
    volatility    NUMERIC,
    var_95        NUMERIC,
    cvar_95       NUMERIC,
    var_99        NUMERIC,
    cvar_99       NUMERIC,
    sharpe        NUMERIC,
    drawdown      NUMERIC,
    PRIMARY KEY (portfolio_id, date)
);

CREATE TABLE IF NOT EXISTS sector_risk_contributions (
    portfolio_id  INTEGER REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    date          DATE,
    sector        TEXT,
    weight        NUMERIC,
    risk_contribution_pct NUMERIC,  -- % of total portfolio variance/VaR
    PRIMARY KEY (portfolio_id, date, sector)
);

CREATE TABLE IF NOT EXISTS events (
    event_date   DATE PRIMARY KEY,
    event_type   TEXT,
    description  TEXT
);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id            SERIAL PRIMARY KEY,
    source        TEXT NOT NULL,       -- e.g. 'yahoo', 'rba', 'abs'
    run_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    rows_written  INTEGER,
    status        TEXT,                -- 'success' | 'failed' | 'partial'
    detail        TEXT
);
