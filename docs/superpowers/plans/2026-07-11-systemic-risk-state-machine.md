# Systemic Risk State Machine — Implementation Plan

**Goal:** Replace linear macro risk averaging with a validated systemic-risk state machine (`normal|building|confirmed|releasing|degraded`) that can lead risk spikes, using existing FRED/Yahoo/Tushare only.

**Architecture:** Feature panel (`as_of`) → non-compensatory state machine → single semantic outlet consumed by Verdict/Dashboard; legacy `MacroLiquidityAnalyzer` retained as drill-down. Event-protocol evaluation is mandatory before UI promotion.

**Tech Stack:** Python, pandas, fredapi, yfinance, pytest, Streamlit (Phase 4 only)

**Spec:** `docs/superpowers/specs/2026-07-11-systemic-risk-state-machine-design.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `config/systemic_risk.yaml` | Windows, thresholds, freshness (frozen after calibration) |
| `config/systemic_risk_events.yaml` | Fixed event protocol for eval |
| `quant/analysis/indicators/systemic_risk/types.py` | Dataclasses |
| `quant/analysis/indicators/systemic_risk/features.py` | Feature → stress mapping |
| `quant/analysis/indicators/systemic_risk/panel.py` | Point-in-time panel |
| `quant/analysis/indicators/systemic_risk/state_machine.py` | State transitions |
| `quant/analysis/indicators/systemic_risk/legacy_map.py` | Legacy score → pseudo-state |
| `quant/analysis/indicators/systemic_risk/actions.py` | Action hints (Phase 4) |
| `scripts/systemic_risk_event_eval.py` | Walk-forward event evaluation |
| `tests/unit/test_systemic_risk_*.py` | L0 correctness |
| `web/data_service.py` | `get_systemic_risk_state()` (Phase 4) |
| `reports/systemic_risk_*.md` | Baseline + calibration artifacts |

---

## Phase 0 — Baseline Replay (no new product logic)

- [x] **0.1** Add `config/systemic_risk_events.yaml` with 6 events (incl. `alice_2025_01` anchor 2025-01-23)
- [x] **0.2** Implement `scripts/systemic_risk_event_eval.py` (legacy map + offline demo path; live FRED walk-forward still open)
- [x] **0.3** Metrics helpers: lead / hit / miss / flicker (`metrics.py` + unit tests)
- [x] **0.4** Live event eval report: `reports/systemic_risk_eval.md` (FRED/Yahoo walk-forward)
- [ ] **0.5** Extract pure helpers from `MacroLiquidityAnalyzer` for snapshot scoring to reduce replay bias

**Exit:** Baseline report exists; team agrees target is state machine not more lights.

---

## Phase 1 — Feature Panel

- [x] **1.1** `types.py`: `FeaturePoint`, panel container
- [x] **1.2** `features.py`: L1–L5 stress mapping; MomentumDelta velocity
- [x] **1.3** `gold_fc_divergence` derived feature
- [x] **1.4** `panel.py`: `build_panel_from_frames(as_of)`; freshness flags
- [x] **1.5** Unit tests: polarity, missing → None, no-lookahead
- [x] **1.6** `config/systemic_risk.yaml` initial defaults (pre-calibration)

**Exit:** `build_panel(as_of)` works offline with mocks; real FRED path smoke-tested manually.

---

## Phase 2 — State Machine

- [x] **2.1** `state_machine.py`: transitions per spec §5
- [x] **2.2** Non-compensatory rules: critical subgraph veto, divergence boost, VIX-only not confirmed
- [x] **2.3** `degraded` on missing critical L1 / stale data
- [x] **2.4** Spec tests S1–S6
- [x] **2.5** `legacy_map.py` for A/B eval

**Exit:** All S1–S6 green; synthetic Alice-like path → building/confirmed.

---

## Phase 3 — Calibration & Freeze

- [ ] **3.1** Extend `systemic_risk_event_eval.py` for models: legacy, usd_liq, systemic_v1 (± ablation L1-only)
- [ ] **3.2** Calibrate on 2018/2020/2022/2023; hold out 2024-08 and 2025-01
- [ ] **3.3** Freeze thresholds into `config/systemic_risk.yaml`
- [ ] **3.4** Write `reports/systemic_risk_calibration_YYYYMMDD.md` (lead/FP/flicker tables + figures)
- [ ] **3.5** Confirm success criteria from spec §2.3 (or document adjusted frozen targets with rationale)

**Exit:** v1 params frozen; holdout events not hard-miss; better than legacy lead/miss.

---

## Phase 4 — Product Integration

- [x] **4.1** `get_systemic_risk_state()` in `web/data_service.py` (TTL 4h; degraded on failure)
- [x] **4.1b** `get_dashboard_summary()` exposes `macro.systemic_risk`
- [ ] **4.2** Dashboard: primary state row + ≤3 drivers + data quality; legacy 8-dim collapsed
- [ ] **4.3** VerdictEngine hooks: building/confirmed/degraded behavior
- [ ] **4.4** `actions.py` copy in English for logs / Chinese OK for UI labels per project norms (log messages English)
- [ ] **4.5** Spot-check: 3 historical dates match eval script output
- [ ] **4.6** Shadow mode note in report: log daily state for 2 weeks before hard-wiring position rules

**Exit:** UI primary conclusion is SystemicRiskState; no silent green on API failure.

---

## Phase 5 — Optional Enhancements (only if eval plateaus)

Add **one** class at a time and re-run eval:

- [ ] VIX term structure (VIX9D / VIX3M)
- [ ] Full NFCI / ANFCI
- [ ] WRESBAL / breakevens
- [ ] HYG/LQD/TLT proxies
- [ ] CFTC crowding (weekly)

Reject any feature that does not improve lead/FP on the event table.

---

## Test Commands

```bash
# L0
./tests/run_tests.sh unit -f "systemic_risk"

# L1 research eval (network + FRED_API_KEY)
uv run python scripts/systemic_risk_event_eval.py \
  --events config/systemic_risk_events.yaml \
  --models legacy,usd_liq,systemic_v1 \
  --out reports/systemic_risk_eval.md
```

---

## Dependencies / Order

```text
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4
                                      │
                                      └──► Phase 5 (optional)
```

Do not start Phase 4 before Phase 3 freeze without explicit exception.

---

## Out of Scope (enforce)

- Paid basis / private credit feeds
- Replacing pool RegimeDetector
- Telegram / realtime streaming
- ML backend as v1 decision core
