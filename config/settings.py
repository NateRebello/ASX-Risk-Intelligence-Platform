"""
Central configuration for the ASX Risk Intelligence Platform.

All values can be overridden via environment variables (see .env.example).
Never commit real secrets — this file only defines *defaults* for local dev.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()  # loads a local .env file if present (no-op in prod/Lambda)

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "asx_risk")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "YourStrongPassword")

SQLALCHEMY_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --------------------------------------------------------------------------
# Data sources
# --------------------------------------------------------------------------
# RBA statistical tables (published as XLS/CSV, no key required)
RBA_CASH_RATE_URL = os.getenv(
    "RBA_CASH_RATE_URL",
    "https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv",
)
RBA_F11_SHEET_KEY_ROW_HINT = "Cash Rate Target"

# ABS Indicator API (SDMX-JSON), used for CPI. Kept as a template — ABS
# occasionally changes dataflow ids, so the loader also supports a
# manual CSV fallback (data/raw/abs_cpi.csv).
ABS_CPI_API_URL = os.getenv(
    "ABS_CPI_API_URL",
    "https://api.data.abs.gov.au/data/CPI/1.10001.10.50.Q",
)

FRED_API_KEY = os.getenv("FRED_API_KEY", "")  # optional cross-check source

# --------------------------------------------------------------------------
# Universe: representative ASX 200 constituents across major GICS sectors.
# (A trimmed, hand-curated subset is used by default so the pipeline runs
# quickly in dev/CI; swap in the full ASX200 list for production runs by
# setting ASX_TICKERS_FILE to a CSV of ticker,name,sector,industry.)
# --------------------------------------------------------------------------
ASX_TICKERS_FILE = os.getenv("ASX_TICKERS_FILE", "")

DEFAULT_UNIVERSE: list[dict[str, str]] = [
    # Financials
    {"ticker": "CBA", "name": "Commonwealth Bank of Australia", "sector": "Financials", "industry": "Banks"},
    {"ticker": "WBC", "name": "Westpac Banking Corp", "sector": "Financials", "industry": "Banks"},
    {"ticker": "ANZ", "name": "ANZ Group Holdings", "sector": "Financials", "industry": "Banks"},
    {"ticker": "NAB", "name": "National Australia Bank", "sector": "Financials", "industry": "Banks"},
    {"ticker": "MQG", "name": "Macquarie Group", "sector": "Financials", "industry": "Diversified Financials"},
    {"ticker": "QBE", "name": "QBE Insurance Group", "sector": "Financials", "industry": "Insurance"},
    {"ticker": "SUN", "name": "Suncorp Group", "sector": "Financials", "industry": "Insurance"},
    {"ticker": "IAG", "name": "Insurance Australia Group", "sector": "Financials", "industry": "Insurance"},
    # Materials / Mining
    {"ticker": "BHP", "name": "BHP Group", "sector": "Materials", "industry": "Metals & Mining"},
    {"ticker": "RIO", "name": "Rio Tinto", "sector": "Materials", "industry": "Metals & Mining"},
    {"ticker": "FMG", "name": "Fortescue", "sector": "Materials", "industry": "Metals & Mining"},
    {"ticker": "NCM", "name": "Newcrest Mining", "sector": "Materials", "industry": "Gold"},
    {"ticker": "S32", "name": "South32", "sector": "Materials", "industry": "Metals & Mining"},
    {"ticker": "MIN", "name": "Mineral Resources", "sector": "Materials", "industry": "Metals & Mining"},
    {"ticker": "AMC", "name": "Amcor", "sector": "Materials", "industry": "Containers & Packaging"},
    # Energy
    {"ticker": "WDS", "name": "Woodside Energy Group", "sector": "Energy", "industry": "Oil & Gas"},
    {"ticker": "STO", "name": "Santos", "sector": "Energy", "industry": "Oil & Gas"},
    {"ticker": "WHC", "name": "Whitehaven Coal", "sector": "Energy", "industry": "Coal"},
    # Healthcare
    {"ticker": "CSL", "name": "CSL Limited", "sector": "Healthcare", "industry": "Biotechnology"},
    {"ticker": "RMD", "name": "ResMed", "sector": "Healthcare", "industry": "Health Care Equipment"},
    {"ticker": "COH", "name": "Cochlear", "sector": "Healthcare", "industry": "Health Care Equipment"},
    {"ticker": "SHL", "name": "Sonic Healthcare", "sector": "Healthcare", "industry": "Health Care Services"},
    # Consumer Staples / Discretionary
    {"ticker": "WES", "name": "Wesfarmers", "sector": "Consumer Discretionary", "industry": "Retailing"},
    {"ticker": "WOW", "name": "Woolworths Group", "sector": "Consumer Staples", "industry": "Food & Staples Retailing"},
    {"ticker": "COL", "name": "Coles Group", "sector": "Consumer Staples", "industry": "Food & Staples Retailing"},
    {"ticker": "JBH", "name": "JB Hi-Fi", "sector": "Consumer Discretionary", "industry": "Retailing"},
    {"ticker": "TWE", "name": "Treasury Wine Estates", "sector": "Consumer Staples", "industry": "Beverages"},
    # Industrials
    {"ticker": "TCL", "name": "Transurban Group", "sector": "Industrials", "industry": "Transportation Infrastructure"},
    {"ticker": "SYD", "name": "Sydney Airport", "sector": "Industrials", "industry": "Transportation Infrastructure"},
    {"ticker": "BXB", "name": "Brambles", "sector": "Industrials", "industry": "Commercial Services"},
    {"ticker": "QAN", "name": "Qantas Airways", "sector": "Industrials", "industry": "Airlines"},
    # Real Estate
    {"ticker": "GMG", "name": "Goodman Group", "sector": "Real Estate", "industry": "REIT"},
    {"ticker": "SCG", "name": "Scentre Group", "sector": "Real Estate", "industry": "REIT"},
    {"ticker": "SGP", "name": "Stockland", "sector": "Real Estate", "industry": "REIT"},
    # Technology
    {"ticker": "XRO", "name": "Xero", "sector": "Information Technology", "industry": "Software"},
    {"ticker": "WTC", "name": "WiseTech Global", "sector": "Information Technology", "industry": "Software"},
    {"ticker": "CPU", "name": "Computershare", "sector": "Information Technology", "industry": "IT Services"},
    # Telecom / Utilities
    {"ticker": "TLS", "name": "Telstra Group", "sector": "Communication Services", "industry": "Telecommunication"},
    {"ticker": "APA", "name": "APA Group", "sector": "Utilities", "industry": "Gas Utilities"},
    {"ticker": "AGL", "name": "AGL Energy", "sector": "Utilities", "industry": "Electric Utilities"},
    {"ticker": "ORG", "name": "Origin Energy", "sector": "Utilities", "industry": "Multi-Utilities"},
]

ASX_TICKERS: list[str] = [row["ticker"] for row in DEFAULT_UNIVERSE]

YAHOO_SUFFIX = ".AX"  # ASX tickers on Yahoo Finance need the .AX suffix
BENCHMARK_TICKER = "^AXJO"  # ASX 200 index (no .AX suffix on Yahoo)

DEFAULT_LOOKBACK_PERIOD = os.getenv("DEFAULT_LOOKBACK_PERIOD", "5y")

# --------------------------------------------------------------------------
# Risk model parameters
# --------------------------------------------------------------------------
TRADING_DAYS_PER_YEAR = 252
ROLLING_VOL_WINDOW = 30
VAR_CONFIDENCE_LEVELS = (0.95, 0.99)
REGIME_LABELS = ("Normal", "Elevated", "Stress")
REGIME_PERCENTILE_CUTOFFS = (0.33, 0.66)  # lower/upper tercile cutoffs
HMM_N_STATES = 3

# --------------------------------------------------------------------------
# AWS (used only by Lambda handlers / deploy scripts)
# --------------------------------------------------------------------------
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")
S3_BUCKET = os.getenv("S3_BUCKET", "asx-risk-data-lake")
