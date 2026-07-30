# ADR 0001: Default market universe (ASX 50) and Tableau Desktop manual-refresh scope

- **Status:** Accepted
- **Date:** 2026-07-30
- **Deciders:** Project owner (via chat direction on 2026-07-28/29)

## Context

`PROJECT_SPEC.md`'s Milestone 1 acceptance criteria call out "all ASX 200
tickers." The platform shipped with a 41-ticker, hand-curated
`DEFAULT_UNIVERSE` in `config/settings.py` as a development placeholder. The
project owner directed two scope decisions that this ADR records:

1. Use a **version-controlled ASX 50 universe as the default**, with ASX 200
   available as a config-only switch (no code change, no image rebuild).
2. Use **Tableau Desktop with a live PostgreSQL connection and manual
   refresh** as the Milestone 6/7 reporting target — not Tableau
   Cloud/Server/Bridge with automated nightly extract refresh, which
   `PROJECT_SPEC.md`'s Milestone 7 acceptance criteria originally implied
   ("Dashboard refreshes nightly with new data").

## Decision 1 — ASX 50 default, version-controlled universe

- `config/universes/asx50.csv` and `config/universes/asx200.csv` are
  committed, versioned CSVs with columns `ticker,name,sector,industry`.
- `settings.yaml` (repo root) selects the default with
  `market_universe: asx50.csv`.
- The ingestion pipeline resolves the active universe at **runtime** (see
  `src/universe/loader.py`), in this order:
  1. An explicit `--tickers-file` / `ASX_TICKERS_FILE` override (local
     ad-hoc runs and tests — unchanged from the platform's original
     behavior).
  2. An AWS SSM Parameter Store value (`/asx-risk/platform/market-universe`)
     naming the active CSV filename, whose contents are read from a
     versioned S3 config prefix (`config/universes/` inside the existing
     `RawDataBucket` — see "Scope reduction" below).
  3. `settings.yaml`'s `market_universe` value, read from the local
     `config/universes/` CSV baked into the Lambda image (used locally, in
     CI, and as the Lambda fallback before the S3/SSM runtime config has
     been provisioned or if it is temporarily unavailable).
  4. `config.settings.DEFAULT_UNIVERSE` — a small hardcoded list, so the
     pipeline never has zero tickers even if every configuration source
     fails.
- **Switching ASX50 → ASX200 in production** is a single command with no
  code change and no redeployment:
  ```bash
  aws ssm put-parameter \
    --name /asx-risk/platform/market-universe \
    --type String --value asx200.csv --overwrite \
    --region ap-southeast-2
  ```
  **Operational caveat:** this SSM parameter is also declared in
  `template.yaml` (seeded from the `MarketUniverseFile` stack parameter, so
  the very first deploy provisions it automatically). Because CloudFormation
  owns the resource, the **next** `sam deploy` will reset the parameter back
  to whatever `MarketUniverseFile` is passed for that deploy (default
  `asx50.csv`) unless the deploy explicitly also passes
  `--parameter-overrides MarketUniverseFile=asx200.csv` (or the
  `AWS_MARKET_UNIVERSE_FILE` GitHub Actions variable is set — see
  `.github/workflows/deploy.yml`). A manual SSM override is therefore a
  same-day operational switch; a durable switch also needs the deploy-time
  parameter updated. This is documented explicitly rather than silently
  surprising an operator — see `docs/runbooks/data-quality.md`.

### Scope reduction from the original plan draft

The completion-roadmap plan described a **dedicated** S3 config bucket. This
implementation instead reuses the existing `RawDataBucket` under a
`config/universes/` prefix. This avoids provisioning a second bucket (one
fewer resource to secure/monitor/pay for) while delivering the same runtime
behavior; it is called out explicitly since it is a deviation from the
original plan text.

### Source data and provenance (as of this ADR)

- **ASX 200 constituents, sectors, and market caps:** Wikipedia,
  ["S&P/ASX 200"](https://en.wikipedia.org/wiki/S%26P/ASX_200), snapshot
  dated by the article as "as of 5 April 2026," fetched 2026-07-30. This is
  a secondary, best-effort, non-licensed reference source — acceptable under
  `PROJECT_SPEC.md`'s "no paid data" constraint but **not** an official,
  paid S&P Dow Jones Indices data feed. It should be refreshed periodically
  (quarterly, aligned with the real index's rebalance schedule) and replaced
  outright if an authoritative redistributable feed becomes available.
- **ASX 50 constituent membership** (which 50 of the ASX 200 names are
  used): [Solactive Australia 50 Index ordinary adjustment
  announcement](https://www.solactive.com/announcements/64509), effective
  22 June 2026 — a real index-provider announcement with an explicit
  effective date, used because it is materially more authoritative for
  *exact* membership than taking a naive top-50-by-market-cap cut (S&P's
  actual buffer/liquidity rules are not purely market-cap-rank-based).
- **GICS sector** values reuse the taxonomy already established by the
  platform's original `DEFAULT_UNIVERSE` (`Financials`, `Materials`,
  `Energy`, `Healthcare`, `Consumer Discretionary`, `Consumer Staples`,
  `Industrials`, `Real Estate`, `Information Technology`, `Communication
  Services`, `Utilities`).
- **GICS sub-industry** ("industry" column) is populated with a specific
  value for well-known constituents (carried over from `DEFAULT_UNIVERSE`
  where available, extended by hand for the rest of the ASX 50). For the
  remaining ASX 200 names without a confident sub-industry classification,
  `industry` is set equal to `sector` as a documented simplification — the
  `industry` column is metadata only and is not read by any analytics or
  attribution logic (only `sector` is).
- **Licensing:** index constituent lists and GICS sector classifications
  reproduced here are factual/non-copyrightable membership data, consistent
  with how the platform already redistributes ASX-listed ticker/sector data
  in `DEFAULT_UNIVERSE`. No index values, weights, or S&P/ASX-branded
  index-level data are redistributed.
- **Known data-quality caveat:** a handful of ASX 200 constituents are
  foreign-exempt/NZX dual-listings (e.g. `AIA`, `CNU`, `MCY`, `FPH`, `EBO`).
  Some of these may not resolve on Yahoo Finance under the `<TICKER>.AX`
  convention `src/ingestion/yahoo_loader.py` uses. This is expected and
  handled gracefully: a single ticker failing to download is logged and
  skipped without aborting the run (see `LoadResult.status == "error"`
  handling in `yahoo_loader.run()`). See `docs/runbooks/data-quality.md`
  for the acceptance-check query that reports per-run failed-ticker counts.

## Decision 2 — Tableau Desktop, manual refresh only

- The reporting target is Tableau Desktop, connected live to PostgreSQL,
  refreshed manually by the operator.
- Tableau Cloud, Tableau Server, Tableau Bridge, and any automated
  extract-refresh schedule are explicitly **out of scope** for this project.
  `scripts/tableau_refresh.py` remains in the repository as a documented,
  unscheduled future-enhancement stub.
- **This is an approved deviation from `PROJECT_SPEC.md`'s Milestone 7
  acceptance criterion** ("Dashboard refreshes nightly with new data").
  Under this ADR, Milestone 7's automation scope is limited to the
  ETL → analytics → briefing pipeline; the dashboard step of that pipeline
  is manual by design.
- Rationale: Tableau Cloud/Server/Bridge licensing, hosting, and scheduled
  Bridge-agent infrastructure were judged out of scope for a project of this
  size; a live, manually-refreshed Tableau Desktop connection to the same
  PostgreSQL warehouse used by the automated pipeline still demonstrates the
  full stack (automated data → analytics → dashboard) end-to-end on demand.

## Consequences

- Positive: the universe is reproducible, testable, and diffable in code
  review; switching universes in production is a config change, not a
  redeploy; the Tableau scope is now unambiguous and testable (no more
  chasing an automated-refresh acceptance criterion this project doesn't
  implement).
- Negative: the ASX 50/200 snapshot will drift from the live index over
  time and is not an official licensed feed; the `industry` column is
  approximate for most ASX 200 names outside the ASX 50; Milestone 7's
  "nightly dashboard refresh" acceptance criterion is formally not met and
  is instead superseded by this ADR's manual-refresh decision.
