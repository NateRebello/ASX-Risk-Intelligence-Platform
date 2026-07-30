# HTTP / provider fixtures (Step 9)

Sanitized samples for offline CI. Do **not** commit live API keys or full
historical dumps.

| File | Source shape | Notes |
|------|--------------|-------|
| `rba_f1_1_sample.csv` | RBA F1.1 CSV | Truncated 3-row sample; metadata header preserved |
| `abs_cpi_sdmx_sample.json` | ABS SDMX-JSON | Synthetic quarterly CPI observations |
| `yahoo_cba_ohlcv.csv` | Yahoo OHLCV | Synthetic CBA-like rows (no live download) |
| `yahoo_audusd.csv` | Yahoo FX close | Synthetic AUDUSD closes |
| `yahoo_iron_ore.csv` | Yahoo futures close | Synthetic TIO=F closes |

Provenance: format-faithful / synthetic for contract tests only — not redistributed
as official market data.
