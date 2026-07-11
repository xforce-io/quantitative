# Systemic Risk Demo Eval (synthetic, offline)

Anchor (demo): `2020-01-14`

## systemic_v1
- first_building: None
- first_confirmed: 2019-11-07
- lead_confirmed: -48
- hit: True miss: False flicker: 0.0125

## legacy_risk_score_map (synthetic mean L1)
- first_building: 2019-11-06
- first_confirmed: 2019-11-05
- lead_confirmed: -50
- hit: True miss: False

## State path (last 20)

| date | systemic_v1 | legacy_map |
|------|-------------|------------|
| 2020-01-28 | confirmed | confirmed |
| 2020-01-29 | confirmed | confirmed |
| 2020-01-30 | confirmed | confirmed |
| 2020-01-31 | confirmed | confirmed |
| 2020-02-03 | confirmed | confirmed |
| 2020-02-04 | confirmed | confirmed |
| 2020-02-05 | confirmed | confirmed |
| 2020-02-06 | confirmed | confirmed |
| 2020-02-07 | confirmed | confirmed |
| 2020-02-10 | confirmed | confirmed |
| 2020-02-11 | confirmed | confirmed |
| 2020-02-12 | confirmed | confirmed |
| 2020-02-13 | confirmed | confirmed |
| 2020-02-14 | confirmed | confirmed |
| 2020-02-17 | confirmed | confirmed |
| 2020-02-18 | confirmed | confirmed |
| 2020-02-19 | confirmed | confirmed |
| 2020-02-20 | confirmed | confirmed |
| 2020-02-21 | confirmed | confirmed |
| 2020-02-24 | confirmed | confirmed |

Note: This is an offline synthetic path (gold rising into funding/credit stress). Live FRED/Yahoo event eval is Phase 0/3 with API keys.