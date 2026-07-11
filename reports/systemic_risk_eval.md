# Systemic Risk Live Event Evaluation

Generated with live FRED/Yahoo frames.
Series: `copper_gold, cp_tbill_spread, dgs2, effr_iorb_spread, gold, hy_oas, move, net_liquidity, nfcirisk, real_yield, sofr_iorb_spread, stlfsi4, usdjpy, vix`
State machine: l1_threshold=0.58, persist=2, confirm_threshold=0.55

## Summary

| event | anchor | v1_first_building | v1_first_confirmed | v1_lead_conf | v1_hit | legacy_first_conf | legacy_lead | legacy_hit |
|-------|--------|-------------------|--------------------|--------------|--------|------------------|-------------|------------|
| vol_2018q4 | 2018-12-24 | 2018-08-03 | 2018-08-02 | -99 | True | 2018-08-13 | -92 | True |
| covid_2020 | 2020-03-23 | 2019-12-16 | 2019-12-03 | -75 | True | 2019-12-31 | -56 | True |
| tightening_2022 | 2022-09-28 | 2022-06-02 | 2021-11-02 | -227 | True | 2021-11-08 | -223 | True |
| svb_2023 | 2023-03-13 | 2023-01-12 | 2023-01-04 | -46 | True | 2023-01-03 | -47 | True |
| yen_2024_08 | 2024-08-05 | 2024-06-18 | 2024-06-04 | -42 | True | 2024-06-04 | -42 | True |
| alice_2025_01 | 2025-01-23 | 2024-11-08 | 2024-11-04 | -53 | True | 2025-02-25 | 22 | True |
| alice_2026_01 | 2026-01-31 | 2025-11-28 | 2025-11-04 | -60 | True | 2025-11-06 | -58 | True |

## Event details

### vol_2018q4 — 2018Q4 liquidity / trade shock

- window: 2018-08-01 → 2019-01-31
- anchor: 2018-12-24
- v1: building=2018-08-03, confirmed=2018-08-02, lead_confirmed=-99, hit=True, flicker=0.127
- proxy_legacy: confirmed=2018-08-13, lead=-92, hit=True
- sample state @ 2018-08-02: **confirmed** (l1=0.61, confirm=0.57, div=0.00)
- drivers: ['Elevated single-leg USD funding stress', 'L1 cp_tbill_spread stress=0.76', 'Confirm move stress=0.62']

### covid_2020 — COVID liquidity crash

- window: 2019-12-01 → 2020-04-30
- anchor: 2020-03-23
- v1: building=2019-12-16, confirmed=2019-12-03, lead_confirmed=-75, hit=True, flicker=0.0769
- proxy_legacy: confirmed=2019-12-31, lead=-56, hit=True
- sample state @ 2019-12-03: **confirmed** (l1=0.58, confirm=0.82, div=0.00)
- drivers: ['Elevated single-leg USD funding stress', 'L1 cp_tbill_spread stress=0.74', 'L1 stlfsi4 stress=0.67', 'Confirm vix stress=0.94', 'Confirm move stress=0.71']

### tightening_2022 — 2022 tightening / gilt stress

- window: 2021-11-01 → 2022-11-30
- anchor: 2022-09-28
- v1: building=2022-06-02, confirmed=2021-11-02, lead_confirmed=-227, hit=True, flicker=0.0659
- proxy_legacy: confirmed=2021-11-08, lead=-223, hit=True
- sample state @ 2021-11-02: **confirmed** (l1=0.71, confirm=0.76, div=0.42)
- drivers: ['Critical subgraph: funding + credit both stressed', 'Quiet funding tightening (multi-leg soft stress)', 'Elevated single-leg USD funding stress', 'L1 cp_tbill_spread stress=0.99', 'L1 nfcirisk stress=0.99']

### svb_2023 — SVB / regional bank stress

- window: 2023-01-01 → 2023-04-30
- anchor: 2023-03-13
- v1: building=2023-01-12, confirmed=2023-01-04, lead_confirmed=-46, hit=True, flicker=0.1481
- proxy_legacy: confirmed=2023-01-03, lead=-47, hit=True
- sample state @ 2023-01-04: **confirmed** (l1=0.70, confirm=0.73, div=0.51)
- drivers: ['Critical subgraph: funding + credit both stressed', 'Quiet funding tightening (multi-leg soft stress)', 'L1 effr_iorb_spread stress=0.58', 'L1 nfcirisk stress=0.80', 'L1 stlfsi4 stress=0.81']

### yen_2024_08 — Yen carry unwind volatility

- window: 2024-06-01 → 2024-09-15
- anchor: 2024-08-05
- v1: building=2024-06-18, confirmed=2024-06-04, lead_confirmed=-42, hit=True, flicker=0.0694
- proxy_legacy: confirmed=2024-06-04, lead=-42, hit=True
- sample state @ 2024-06-04: **confirmed** (l1=0.80, confirm=0.78, div=0.48)
- drivers: ['Critical subgraph: funding + credit both stressed', 'Quiet funding tightening (multi-leg soft stress)', 'Elevated single-leg USD funding stress', 'L1 sofr_iorb_spread stress=0.90', 'L1 cp_tbill_spread stress=0.75']

### alice_2025_01 — Alice systemic risk confirm (2025 reference)

- window: 2024-11-01 → 2025-03-31
- anchor: 2025-01-23
- v1: building=2024-11-08, confirmed=2024-11-04, lead_confirmed=-53, hit=True, flicker=0.2277
- proxy_legacy: confirmed=2025-02-25, lead=22, hit=True
- sample state @ 2024-11-04: **confirmed** (l1=0.52, confirm=0.97, div=0.00)
- drivers: ['Quiet funding tightening (multi-leg soft stress)', 'Elevated single-leg USD funding stress', 'L1 cp_tbill_spread stress=0.95', 'L1 stlfsi4 stress=0.96', 'Confirm vix stress=0.94']

### alice_2026_01 — Alice quiet tightening 2026-01-23; equity dump from ~2026-01-31

- window: 2025-11-01 → 2026-02-28
- anchor: 2026-01-31
- v1: building=2025-11-28, confirmed=2025-11-04, lead_confirmed=-60, hit=True, flicker=0.1875
- proxy_legacy: confirmed=2025-11-06, lead=-58, hit=True
- sample state @ 2025-11-04: **confirmed** (l1=0.80, confirm=0.53, div=0.00)
- drivers: ['Critical subgraph: funding + credit both stressed', 'Quiet funding tightening (multi-leg soft stress)', 'Elevated single-leg USD funding stress', 'L1 sofr_iorb_spread stress=0.91', 'L1 effr_iorb_spread stress=0.99']


## Notes

- `legacy_*` columns use a **stress-proxy** map (not full MacroLiquidityAnalyzer replay). Treat as rough baseline until snapshot scoring is extracted (plan 0.5).
- `lead_confirmed` = first_confirmed_index − anchor_index on the event calendar (negative = earlier than anchor).
- Alice reference event `alice_2025_01` uses anchor 2025-01-23.
