# Integration Implementation Plan (Track 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the signal foundation (Track 2) into the UI layer (Track 1) — replace heuristic verdicts with VerdictEngine output, add hit-rate badges, add transmission chain visualization, make Scanner regime-aware.

**Architecture:** A new `web/data_service_verdict.py` module wraps the analysis layer (RegimeDetector, SignalRegistry, TransmissionGraph, VerdictEngine) with Streamlit caching. Dashboard, Watchlist, and Scanner import from this module instead of using heuristic functions.

**Tech Stack:** Streamlit, Plotly, all Track 2 modules

**Prerequisites:** Both Track 1 (UI restructure) and Track 2 (signal foundation) must be complete before starting this plan.

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `web/data_service_verdict.py` | Cached wrappers for VerdictEngine + RegimeDetector + TransmissionGraph |
| **Modify** | `web/pages/1_📊_Dashboard.py` | Replace heuristic verdict with VerdictEngine, add transmission viz |
| **Modify** | `web/pages/2_👀_Watchlist.py` | Add hit-rate badges, use real regime from RegimeDetector |
| **Modify** | `web/scanner/ashare_scan.py` | Filter results by regime + hit-rate |
| **Modify** | `web/scanner/us_value_scan.py` | Filter results by regime + hit-rate |
| **Modify** | `web/scanner/commodity_scan.py` | Use CommodityAnalyzer for real signals |
| **Modify** | `web/data_service.py` | Remove heuristic verdict functions (replaced) |

---

### Task 1: Create verdict data service layer

**Files:**
- Create: `web/data_service_verdict.py`

This module wraps Track 2's analysis modules with Streamlit caching so the UI can call them efficiently.

- [ ] **Step 1: Create data_service_verdict.py**

```python
# web/data_service_verdict.py
"""
Verdict data service — cached wrappers for the signal foundation layer.

Provides Streamlit-cached access to:
- RegimeDetector (regime per pool)
- SignalRegistry (signal definitions + validations)
- TransmissionGraph (active transmission chains)
- VerdictEngine (per-pool verdicts + position alerts)
- CommodityAnalyzer (gold & commodity data)
"""
import streamlit as st
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from quant.analysis.regime import RegimeDetector, RegimeState
from quant.analysis.signals import SignalRegistry, SignalValidation, ActiveSignal
from quant.analysis.transmission import TransmissionGraph, ActiveTransmission
from quant.analysis.verdict import VerdictEngine, DashboardVerdict, PoolVerdict, PositionAlert
from quant.analysis.indicators.commodity_analyzer import CommodityAnalyzer


_VALIDATION_DIR = str(Path(__file__).parent.parent / "data" / "signal_validations")


@st.cache_resource
def _get_regime_detector() -> RegimeDetector:
    return RegimeDetector()


@st.cache_resource
def _get_signal_registry() -> SignalRegistry:
    registry = SignalRegistry()
    registry.load_validations_from_dir(_VALIDATION_DIR)
    return registry


@st.cache_resource
def _get_transmission_graph() -> TransmissionGraph:
    return TransmissionGraph()


@st.cache_resource
def _get_verdict_engine() -> VerdictEngine:
    return VerdictEngine()


@st.cache_resource
def _get_commodity_analyzer() -> CommodityAnalyzer:
    return CommodityAnalyzer()


@st.cache_data(ttl=3600, show_spinner=False)
def get_regime(pool: str) -> Dict[str, Any]:
    """Get current regime for a single pool. Returns dict for JSON-serializable caching."""
    # Gather indicators for the pool from existing analyzers
    from web.data_service import get_china_market_signals, get_macro_liquidity, get_global_usd_liquidity

    detector = _get_regime_detector()
    indicators = {}

    if pool == "a_shares":
        try:
            china = get_china_market_signals(lookback_days=60)
            indicators["china_risk_score"] = china.get("risk_score", 50)
            # margin_debt_trend and northbound_flow require additional data sources
            # Use available data for now
            indicators["market_breadth"] = 50.0  # TODO: compute from actual breadth data
        except Exception:
            pass

    elif pool == "us_stocks":
        try:
            macro = get_macro_liquidity(lookback_days=365)
            indicators["macro_risk_score"] = macro.get("risk_score", 50)
            # yield_curve, credit_spread, vix from leading indicators
            from web.data_service import get_leading_indicators
            leading = get_leading_indicators()
            if leading:
                yc = leading.get("yield_curve", {})
                indicators["yield_curve_2s10s"] = yc.get("current_value", 0.0)
                cs = leading.get("credit_spread", {})
                indicators["credit_spread"] = cs.get("current_value", 1.5)
                vix = leading.get("vix", {})
                indicators["vix"] = vix.get("current_value", 20.0)
        except Exception:
            pass

    elif pool == "gold":
        try:
            usd = get_global_usd_liquidity()
            # Use USD liquidity as proxy for real rates direction
            confidence = usd.get("confidence", 0) or 0
            indicators["dxy_trend"] = -confidence / 10  # rough proxy
            indicators["gold_silver_ratio"] = 80.0  # TODO: from CommodityAnalyzer
            indicators["real_rate_10y"] = 1.5  # TODO: from FRED
        except Exception:
            pass

    elif pool == "commodities":
        try:
            macro = get_macro_liquidity(lookback_days=365)
            dims = macro.get("dimension_scores", {})
            cg = dims.get("copper_gold", {})
            indicators["copper_gold_ratio"] = (cg.get("score", 50) - 50) / 5
            crude = dims.get("crude_oil", {})
            indicators["crude_oil_trend"] = (crude.get("score", 50) - 50) / 3
            indicators["dxy_trend"] = 0.0
        except Exception:
            pass

    state = detector.classify_pool(pool, indicators)
    return {
        "pool": state.pool,
        "regime": state.regime,
        "confidence": state.confidence,
        "days_since_change": state.days_since_change,
        "drivers": state.drivers,
        "updated_at": state.updated_at,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def get_all_regimes() -> Dict[str, Dict[str, Any]]:
    """Get regimes for all four pools."""
    return {pool: get_regime(pool) for pool in ("a_shares", "us_stocks", "gold", "commodities")}


@st.cache_data(ttl=3600, show_spinner=False)
def get_dashboard_verdict() -> Dict[str, Any]:
    """Get the full dashboard verdict from VerdictEngine."""
    regimes_raw = get_all_regimes()

    # Convert back to RegimeState objects for VerdictEngine
    regimes = {}
    for pool, data in regimes_raw.items():
        regimes[pool] = RegimeState(**data)

    engine = _get_verdict_engine()

    # For now, pass empty signals (until signal scanning is integrated)
    signals_by_pool: Dict[str, list] = {p: [] for p in regimes}
    transmissions_by_pool: Dict[str, list] = {p: [] for p in regimes}

    verdict = engine.compute_dashboard_verdict(regimes, signals_by_pool, transmissions_by_pool, [])

    # Convert to dict for caching
    return {
        "overall_stance": verdict.overall_stance,
        "pool_verdicts": [
            {
                "pool": v.pool,
                "action": v.action,
                "confidence": v.confidence,
                "reasoning": v.reasoning,
                "regime": v.regime.regime,
                "regime_confidence": v.regime.confidence,
            }
            for v in verdict.pool_verdicts
        ],
        "updated_at": verdict.updated_at,
    }


@st.cache_data(ttl=1800, show_spinner=False)
def get_active_transmissions() -> List[Dict[str, Any]]:
    """Get currently active transmission chains."""
    graph = _get_transmission_graph()
    active = graph.get_active_transmissions()
    return [
        {
            "source": a.edge.source,
            "target": a.edge.target,
            "direction": a.edge.direction,
            "source_move": a.source_move,
            "expected_target": a.expected_target,
            "days_remaining": a.days_remaining,
            "strength": a.edge.strength,
            "status": a.status,
            "triggered_at": a.triggered_at,
        }
        for a in active
    ]
```

- [ ] **Step 2: Commit**

```bash
git add web/data_service_verdict.py
git commit -m "feat(web): add verdict data service layer wrapping signal foundation"
```

---

### Task 2: Integrate VerdictEngine into Dashboard

**Files:**
- Modify: `web/pages/1_📊_Dashboard.py`

- [ ] **Step 1: Replace heuristic imports with verdict imports**

In Dashboard.py, replace:
```python
from web.data_service import get_all_pool_verdicts, get_heuristic_pool_verdict
```
with:
```python
from web.data_service_verdict import get_dashboard_verdict, get_all_regimes, get_active_transmissions
```

- [ ] **Step 2: Update _render_verdict_bar() to use VerdictEngine output**

Update the verdict bar section to read from `get_dashboard_verdict()` instead of `get_all_pool_verdicts()`. The data structure is:
```python
verdict = get_dashboard_verdict()
# verdict["overall_stance"] — "aggressive"|"neutral"|"cautious"|"defensive"
# verdict["pool_verdicts"] — list of {pool, action, confidence, reasoning, regime}
# verdict["updated_at"] — timestamp
```

Map `overall_stance` to colors:
```python
stance_styles = {
    "aggressive": ("🟢", "#2ecc71", "Increase exposure"),
    "neutral": ("🟡", "#f1c40f", "Maintain positions"),
    "cautious": ("🟠", "#e67e22", "Reduce risk exposure"),
    "defensive": ("🔴", "#e74c3c", "Minimize exposure"),
}
```

- [ ] **Step 3: Add transmission chain visualization**

Update `_render_transmission_alerts()` to show real data from `get_active_transmissions()`:

```python
def _render_transmission_alerts():
    transmissions = get_active_transmissions()
    if not transmissions:
        st.caption("No active cross-asset transmissions")
        return

    st.markdown("### 🔗 Cross-Asset Transmission")
    for t in transmissions:
        direction_arrow = "→" if t["direction"] == "direct" else "→ (inverse)"
        st.markdown(
            f"**{t['source']}** {t['source_move']:+.1f}% {direction_arrow} "
            f"**{t['target']}** — {t['expected_target']} "
            f"(strength: {t['strength']:.0%}, {t['days_remaining']}d remaining)"
        )
```

- [ ] **Step 4: Update pool cards to use real regime data**

Replace `get_heuristic_pool_verdict(pool)` calls in pool cards with `get_all_regimes()[pool]`.

- [ ] **Step 5: Verify Dashboard shows real verdict data**

Navigate to Dashboard. Verify:
- Verdict bar shows VerdictEngine output
- Transmission section renders (may be empty if no edges triggered)
- Pool cards show real regime labels
- No import errors

- [ ] **Step 6: Commit**

```bash
git add "web/pages/1_📊_Dashboard.py"
git commit -m "feat(dashboard): integrate VerdictEngine — real regimes and verdicts"
```

---

### Task 3: Add hit-rate badges to Watchlist

**Files:**
- Modify: `web/pages/2_👀_Watchlist.py`

- [ ] **Step 1: Import regime from verdict service**

Add import:
```python
from web.data_service_verdict import get_regime
```

- [ ] **Step 2: Update tab headers with real regime**

Replace `get_heuristic_pool_verdict(pool)` in tab labels with `get_regime(pool)`:

```python
regimes = {pool: get_regime(pool) for pool in ("a_shares", "us_stocks", "gold", "commodities")}
tab_labels = [
    f"🇨🇳 A-Shares ({regimes['a_shares']['regime']})",
    f"🇺🇸 US Stocks ({regimes['us_stocks']['regime']})",
    f"🥇 Gold ({regimes['gold']['regime']})",
    f"🛢 Commodities ({regimes['commodities']['regime']})",
]
```

- [ ] **Step 3: Add signal hit-rate display in position expanders**

When showing signal alerts for positions, include the hit-rate from validation:
```python
# In position expander, after computing alert level
if signal_hit_rate:
    st.caption(f"Signal hit-rate: {signal_hit_rate:.0%} (N={sample_size})")
```

This requires loading validation data via `_get_signal_registry()`. If no validation exists yet, show "unvalidated" label.

- [ ] **Step 4: Commit**

```bash
git add "web/pages/2_👀_Watchlist.py"
git commit -m "feat(watchlist): add real regime badges and signal hit-rates"
```

---

### Task 4: Make Scanner regime-aware

**Files:**
- Modify: `web/scanner/ashare_scan.py`
- Modify: `web/scanner/us_value_scan.py`
- Modify: `web/scanner/commodity_scan.py`

- [ ] **Step 1: Update A-share scan with regime filtering**

In `ashare_scan.py`, add regime badge at top:
```python
from web.data_service_verdict import get_regime

def render_ashare_scan(verdict: dict) -> None:
    regime = get_regime("a_shares")
    st.info(f"Current regime: **{regime['regime']}** (confidence: {regime['confidence']:.0%})")
    if regime["regime"] == "risk-off":
        st.warning("Risk-off regime — scan biased toward defensive names")
```

Filter scan results: only show results with hit-rate > min_hit_rate (from signal registry).

- [ ] **Step 2: Update US value scan similarly**

Add regime badge and filter to `us_value_scan.py`.

- [ ] **Step 3: Update commodity scan with CommodityAnalyzer**

In `commodity_scan.py`, use CommodityAnalyzer for real gold/commodity data:
```python
from web.data_service_verdict import _get_commodity_analyzer, get_regime
```

- [ ] **Step 4: Verify all scanner tabs show regime context**

Navigate to Scanner. Verify:
- Each tab shows regime badge
- Risk-off warning appears when applicable
- Results include hit-rate info where available

- [ ] **Step 5: Commit**

```bash
git add web/scanner/
git commit -m "feat(scanner): add regime-aware filtering and hit-rate badges"
```

---

### Task 5: Clean up heuristic functions

**Files:**
- Modify: `web/data_service.py`

- [ ] **Step 1: Remove heuristic verdict functions**

Remove `get_heuristic_pool_verdict()` and `get_all_pool_verdicts()` from `web/data_service.py` — they are fully replaced by `web/data_service_verdict.py`.

- [ ] **Step 2: Verify no remaining references**

Run: `grep -r "get_heuristic_pool_verdict\|get_all_pool_verdicts" web/ --include="*.py"`
Expected: No matches

- [ ] **Step 3: Commit**

```bash
git add web/data_service.py
git commit -m "refactor: remove heuristic verdict functions (replaced by VerdictEngine)"
```

---

### Task 6: Full integration smoke test

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Start Streamlit and test the complete flow**

Run: `streamlit run web/Home.py`

Test checklist:
1. Dashboard: verdict bar shows VerdictEngine output with overall stance
2. Dashboard: transmission section renders (may be empty)
3. Dashboard: pool cards show real regime labels from RegimeDetector
4. Dashboard: position alerts show signal-based recommendations
5. Watchlist: tabs show real regime badges
6. Watchlist: position expanders show hit-rate where available
7. Scanner: each tab shows regime context badge
8. Scanner: A-share scan results filterable
9. Scanner → Watchlist: "+ Add" works and position appears in Watchlist
10. No import errors, no matplotlib references

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete integration — signal foundation powers all UI verdicts"
```
