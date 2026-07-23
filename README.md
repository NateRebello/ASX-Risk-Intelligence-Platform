# ASX Risk Intelligence Platform

**Production-grade market risk analytics platform for the ASX 200.** Automated
daily ingestion & ETL of ASX OHLCV and macroeconomic data into PostgreSQL,
with Python analytics (rolling volatility, Ledoit-Wolf shrinkage covariance,
HMM regime detection, VaR/CVaR). Interactive Tableau dashboards and daily
executive summaries provide actionable **risk** insights — sector risk
contributions, volatility regimes, macro drivers — rather than naive price
prediction.

- **Tech stack:** Python (pandas/NumPy/scikit-learn/hmmlearn/arch),
  PostgreSQL, AWS Lambda + EventBridge, Tableau.
- **Key features:** automated ETL pipeline; percentile & HMM volatility
  regime detection; portfolio VaR/CVaR + sector risk attribution; Ledoit-Wolf
  shrinkage covariance; Tableau dashboard with risk heatmaps; daily markdown
  executive briefing.
- **Data sources:** Yahoo Finance (`yfinance`) for ASX prices, RBA for the
  cash rate, ABS for CPI (with a local CSV fallback), Yahoo Finance for
  AUD/USD and iron ore futures.
- **Local usage:** `docker compose up -d db` → `python scripts/run_pipeline.py`.
- **Production usage:** the same steps run as chained AWS Lambda functions
  on an EventBridge schedule timed to the ASX close (see `template.yaml`).

## Quickstart

```bash
# 1. Start Postgres (auto-applies sql/schema.sql + sql/views.sql on first boot)
docker compose up -d db

# 2. Create a virtualenv and install dependencies
#    (Python 3.11/3.12 recommended — hmmlearn/arch ship prebuilt wheels for
#    these; very new Python versions may force a from-source build that
#    requires MSVC build tools on Windows.)
python -m venv .venv
source .venv/bin/activate        # or .venv\Scripts\activate on Windows
pip install -r requirements.txt -r requirements-dev.txt

# 3. Copy .env.example -> .env and adjust DB credentials if needed
cp .env.example .env

# 4. Run the full pipeline end-to-end: ingest -> returns -> volatility ->
#    regimes -> executive briefing
python scripts/run_pipeline.py --period 2y

# 5. (Optional) seed a demo portfolio and compute its risk attribution
python scripts/seed_demo_portfolio.py --tickers CBA BHP CSL WES TLS

# 6. Run the test suite
pytest
```

## Repository Layout

```
asx-risk-intelligence/
├── config/settings.py          # DB credentials, ticker universe, risk params
├── sql/schema.sql, views.sql   # Warehouse DDL + example analytical views
├── src/
│   ├── ingestion/               # yahoo_loader.py, rba_loader.py
│   ├── processing/               # cleaning.py
│   ├── analytics/                 # returns, volatility, covariance, regimes, macro_analysis
│   ├── portfolio/                  # optimizer.py, attribution.py
│   ├── reports/                     # executive_summary.py
│   └── db/                          # SQLAlchemy engine + migration runner
├── scripts/                    # run_pipeline.py, seed_demo_portfolio.py, tableau_refresh.py
├── dashboard/tableau/           # Tableau starter workbook + panel SQL
├── tests/                       # pytest suite (55 tests) for every module above
├── template.yaml, Dockerfile.lambda   # AWS SAM Lambda deployment
└── .github/workflows/ci.yml     # lint + pytest on every push, PR
```

## Milestone Status

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Data Engineering (schema, `yahoo_loader.py`, `rba_loader.py`) | ✅ Done — verified against a live Postgres instance with real Yahoo Finance/RBA data |
| 2 | Financial Analytics (returns, volatility, Ledoit-Wolf covariance) | ✅ Done |
| 3 | Volatility Regime Detection (percentile + Gaussian HMM) | ✅ Done |
| 4 | Portfolio Risk Engine (VaR/CVaR, sector attribution) | ✅ Done |
| 5 | Macro Overlay (RBA/AUD/iron ore vs volatility) | ✅ Done |
| 6 | Dashboard & Reporting (Tableau starter workbook, executive briefing) | ✅ Starter delivered — open `dashboard/tableau/asx_risk_starter.twb` in Tableau Desktop to finish styling |
| 7 | Production & Automation (Lambda/EventBridge/CI) | ✅ IaC delivered (`template.yaml`, `Dockerfile.lambda`, `ci.yml`) — deploying to a real AWS account requires your own credentials/RDS instance |

All Python modules (Milestones 1–6) have been **executed end-to-end against a
live PostgreSQL instance with real Yahoo Finance and RBA data**, not just
unit-tested in isolation. Two real bugs were caught and fixed this way (a
pandas `groupby().apply()` grouping-column bug in `regimes.py`, and a
`merge_asof` dtype bug in `macro_analysis.py`) — see git history.

## Sample Executive Briefing (real output from this pipeline)

```
**ASX Market Risk Summary – 22 Jul 2026**

- **Volatility Regime:** Stress (30-day vol = 33.8%).
- **Top Risk Contributors:** Healthcare (29%), Financials (22%), Consumer Discretionary (20%).
- **Portfolio VaR/CVaR:** 1-day 95% VaR = 1.3%; CVaR = 1.9%.
- **Macro Update:** cash rate 4.35%; AUD/USD 0.6996.
- **Action Items:** Reduce risk exposure, review hedges, and monitor for further volatility spikes.
```

## Testing

```bash
pytest                          # 55 tests across ingestion/analytics/portfolio/reports
pytest --cov=src --cov=config   # with coverage
flake8 src config tests scripts --max-line-length=120 --extend-ignore=E203,W503
black --check --line-length 120 src config tests scripts
```

CI (`.github/workflows/ci.yml`) runs the same lint + pytest suite against a
disposable Postgres service container on every push/PR, then builds the
Lambda container image on `main`.

## AWS Deployment (Milestone 7)

The AWS stack deploys **seven** Lambda functions: six pipeline stages plus a
controlled schema-migration function. A single EventBridge rule starts a Step
Functions workflow: price and macro ingestion run in parallel, then returns →
volatility → regimes → briefing run sequentially. This removes the unsafe
assumption that time-offset cron jobs finish before the next job starts.

### Prerequisites

- An existing private RDS/Aurora PostgreSQL instance; this stack intentionally
  does not create the database.
- Private Lambda subnets with a NAT Gateway. The VPC is required for RDS, but
  the ingestion functions also need internet egress for Yahoo Finance, RBA,
  and ABS.
- An RDS security group allowing Lambda security-group traffic on PostgreSQL
  port 5432.
- A Secrets Manager secret containing either a plaintext password or JSON with
  a `password` field. The function fetches it at runtime; do not set
  `DB_PASSWORD` in AWS Lambda configuration.
- GitHub repository variables: `AWS_DEPLOY_ROLE_ARN`, `AWS_ECR_REPOSITORY`,
  `AWS_DB_HOST`, `AWS_DB_NAME`, `AWS_DB_USER`, `AWS_VPC_SUBNET_IDS`, and
  `AWS_VPC_SECURITY_GROUP_IDS`; plus secret `AWS_DB_SECRET_ARN`.

### Deploy

`deploy.yml` uses GitHub OIDC, builds an immutable ECR image tagged with the
commit SHA, validates SAM, and deploys on a release tag or manual dispatch.
The deploy role needs narrowly scoped CloudFormation, ECR, IAM pass-role,
Lambda, Step Functions, EventBridge, S3, SNS, SQS, and Secrets Manager
permissions for this stack.

Apply `sql/schema.sql` and `sql/views.sql` to RDS before the first normal run,
or start a one-off state-machine execution with `{"runMigrations": true}`.
Do not enable that flag for the daily schedule.

The state machine publishes failures to SNS and retains them in the provisioned
SQS failure queue. Inspect Lambda and Step Functions logs in CloudWatch, then
verify `daily_prices`, `returns`, and `volatility` row counts in PostgreSQL.

**Note:** provisioning real AWS resources (RDS, IAM roles, ECR, Lambda) and
a real Tableau Server site requires your own AWS account and Tableau
license/credentials, which are out of scope for this environment — the IaC
and application code are complete and ready to deploy against your
infrastructure.

## Assumptions & Constraints

- Free data sources only (Yahoo Finance, RBA, ABS) — no Bloomberg/Reuters.
- ASX-listed constituents + Australian macro only (a curated 40-ticker
  subset spanning all major GICS sectors ships by default; point
  `ASX_TICKERS_FILE` at a full ASX200 CSV for production runs).
- The ABS Indicator API occasionally changes/rate-limits; `rba_loader.py`
  falls back to `data/raw/abs_cpi.csv` (a small sample is included) rather
  than failing the whole ingestion run.
- Missing/delisted tickers (e.g. a stock that's since been acquired) are
  logged and skipped, not fatal — see `ingestion_log` table.
