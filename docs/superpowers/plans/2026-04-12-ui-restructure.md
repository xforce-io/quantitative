# UI Restructure Implementation Plan (Track 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the three-page web system around four asset pools, add a verdict layer to Dashboard, unify charts to Plotly, and close the Scanner→Watchlist loop. Initially uses heuristic rules for verdicts; Track 2's signal framework replaces them later.

**Architecture:** Dashboard gets four sections (verdict bar, transmission alerts, pool cards, position alerts). Watchlist tabs by asset pool instead of stock/industry. Scanner tabs by asset pool with one-click "add to watchlist". All matplotlib removed, Plotly only. Watchlist config migrated from JSON to YAML with pool grouping.

**Tech Stack:** Streamlit, Plotly, PyYAML, existing `data_service.py` + analyzers

**Dependency:** This plan can start immediately. Tasks 1-6 use heuristic rules. After Track 2 (signal-foundation) completes, the Integration plan replaces heuristics with validated signals.

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `config/watchlist.yaml` | New watchlist format with pool grouping |
| **Modify** | `web/utils.py` | Load/save watchlist.yaml, auto-classify symbols |
| **Rewrite** | `web/pages/1_📊_Dashboard.py` | Verdict bar + transmission + pool cards + position alerts |
| **Rewrite** | `web/pages/2_👀_Watchlist.py` | Tabs by asset pool, in-page add/remove |
| **Create** | `web/scanner/__init__.py` | Scanner sub-package |
| **Create** | `web/scanner/ashare_scan.py` | A-share scanning tab |
| **Create** | `web/scanner/us_value_scan.py` | US value scanning tab |
| **Create** | `web/scanner/commodity_scan.py` | Gold & commodity scanning tab |
| **Rewrite** | `web/pages/3_🔍_Scanner.py` | Thin shell importing per-tab modules |
| **Modify** | `web/components.py` | Remove matplotlib functions, add shared utilities |
| **Modify** | `web/data_service.py` | Add verdict/regime helper functions |
| **Modify** | `web/Home.py` | Update descriptions for new system |

---

### Task 1: Migrate watchlist config from JSON to YAML

**Files:**
- Create: `config/watchlist.yaml`
- Modify: `web/utils.py`

- [ ] **Step 1: Create watchlist.yaml from existing watchlist.json**

Read the existing `config/watchlist.json` and convert to YAML format with pool grouping. If the file doesn't exist, create a starter:

```yaml
# config/watchlist.yaml
# Watchlist organized by asset pool.
# Each pool contains a list of {symbol, name} entries.

a_shares:
  - symbol: "000001.SZ"
    name: "平安银行"
  - symbol: "600519.SH"
    name: "贵州茅台"

us_stocks: []

gold: []

commodities: []

industries:
  - "半导体"
  - "商业航天"
```

- [ ] **Step 2: Update web/utils.py to support new format**

Read the current `web/utils.py` first (it's ~38 lines), then replace with:

```python
# web/utils.py
"""Watchlist config management — load/save watchlist.yaml with pool grouping."""
from pathlib import Path
from typing import Any, Dict, List

import yaml

WATCHLIST_FILE = Path(__file__).parent.parent / "config" / "watchlist.yaml"
LEGACY_WATCHLIST_FILE = Path(__file__).parent.parent / "config" / "watchlist.json"

POOLS = ("a_shares", "us_stocks", "gold", "commodities")


def _classify_symbol(symbol: str) -> str:
    """Auto-detect asset pool from symbol format."""
    s = symbol.upper()
    if s.endswith(".SZ") or s.endswith(".SH"):
        return "a_shares"
    if s.endswith(".HK"):
        return "a_shares"  # treat HK as A-shares pool for now
    # Known commodity/gold tickers
    gold_tickers = {"GLD", "IAU", "GC=F", "SI=F", "SLV"}
    commodity_tickers = {"USO", "CL=F", "HG=F", "DJP", "GSG", "COPX"}
    ticker = s.split(".")[0].split(" ")[0]
    if ticker in gold_tickers:
        return "gold"
    if ticker in commodity_tickers:
        return "commodities"
    return "us_stocks"


def load_watchlist() -> Dict[str, Any]:
    """Load watchlist from YAML. Falls back to legacy JSON if YAML doesn't exist."""
    if WATCHLIST_FILE.exists():
        with open(WATCHLIST_FILE) as f:
            data = yaml.safe_load(f) or {}
        # Ensure all pools exist
        for pool in POOLS:
            if pool not in data:
                data[pool] = []
        if "industries" not in data:
            data["industries"] = []
        return data

    # Legacy fallback: convert old JSON format
    if LEGACY_WATCHLIST_FILE.exists():
        import json
        with open(LEGACY_WATCHLIST_FILE) as f:
            old = json.load(f)
        data = {pool: [] for pool in POOLS}
        data["industries"] = old.get("industries", [])
        for stock_str in old.get("stocks", []):
            parts = stock_str.split(" ", 1)
            symbol = parts[0]
            name = parts[1] if len(parts) > 1 else symbol
            pool = _classify_symbol(symbol)
            data[pool].append({"symbol": symbol, "name": name})
        # Save as new format
        save_watchlist(data)
        return data

    return {pool: [] for pool in POOLS, **{"industries": []}}


def save_watchlist(data: Dict[str, Any]) -> None:
    """Save watchlist to YAML."""
    WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHLIST_FILE, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def add_to_watchlist(symbol: str, name: str, pool: str | None = None) -> str:
    """Add a symbol to watchlist. Auto-detects pool if not specified. Returns pool name."""
    if pool is None:
        pool = _classify_symbol(symbol)
    data = load_watchlist()
    # Avoid duplicates
    existing = [s["symbol"] for s in data.get(pool, [])]
    if symbol not in existing:
        data[pool].append({"symbol": symbol, "name": name})
        save_watchlist(data)
    return pool


def remove_from_watchlist(symbol: str) -> bool:
    """Remove a symbol from watchlist. Returns True if found and removed."""
    data = load_watchlist()
    for pool in POOLS:
        entries = data.get(pool, [])
        for i, entry in enumerate(entries):
            if entry["symbol"] == symbol:
                entries.pop(i)
                save_watchlist(data)
                return True
    return False


def get_all_symbols() -> List[Dict[str, str]]:
    """Get all watchlist symbols across all pools, each with pool tag."""
    data = load_watchlist()
    result = []
    for pool in POOLS:
        for entry in data.get(pool, []):
            result.append({**entry, "pool": pool})
    return result
```

- [ ] **Step 3: Fix the syntax error in load_watchlist fallback**

The line `return {pool: [] for pool in POOLS, **{"industries": []}}` has a syntax error. Replace the last return in `load_watchlist`:

```python
    result = {pool: [] for pool in POOLS}
    result["industries"] = []
    return result
```

- [ ] **Step 4: Verify utils loads correctly**

Run: `python -c "from web.utils import load_watchlist, add_to_watchlist, _classify_symbol; print(_classify_symbol('000001.SZ'), _classify_symbol('AAPL'), _classify_symbol('GLD'))"`
Expected: `a_shares us_stocks gold`

- [ ] **Step 5: Commit**

```bash
git add config/watchlist.yaml web/utils.py
git commit -m "feat(watchlist): migrate to YAML with asset pool grouping"
```

---

### Task 2: Add heuristic verdict helpers to data_service

**Files:**
- Modify: `web/data_service.py`

Add functions that compute heuristic verdicts using existing analyzers. These will be replaced by VerdictEngine in the integration phase.

- [ ] **Step 1: Read current data_service.py to find insertion point**

Read `web/data_service.py` and find the end of the file. Add the new functions after the existing ones.

- [ ] **Step 2: Add heuristic verdict functions**

Append to the end of `web/data_service.py`:

```python
# ==================== Heuristic Verdict (pre-signal-framework) ====================

@st.cache_data(ttl=3600, show_spinner=False)
def get_heuristic_pool_verdict(pool: str) -> Dict[str, Any]:
    """
    Compute a heuristic verdict for an asset pool using existing analyzers.
    This is a temporary implementation — will be replaced by VerdictEngine
    once the signal foundation (Track 2) is complete.

    Returns:
        {action, reasoning, regime, regime_icon, updated_at}
    """
    from datetime import datetime

    result = {"pool": pool, "updated_at": datetime.now().strftime("%H:%M")}

    if pool == "a_shares":
        try:
            china = get_china_market_signals(lookback_days=60)
            status = china.get("status", "Unknown")
            risk_score = china.get("risk_score", 50)
            if status == "Defensive" or risk_score > 70:
                result.update(action="reduce", reasoning="A-share sentiment defensive, risk score high",
                             regime="risk-off", regime_icon="🔴")
            elif status == "Bullish" or risk_score < 30:
                result.update(action="add", reasoning="A-share sentiment bullish",
                             regime="risk-on", regime_icon="🟢")
            else:
                result.update(action="hold", reasoning=f"A-share sentiment {status}",
                             regime="transition", regime_icon="🟡")
        except Exception:
            result.update(action="hold", reasoning="data unavailable", regime="unknown", regime_icon="⚪")

    elif pool == "us_stocks":
        try:
            macro = get_macro_liquidity(lookback_days=365)
            status = macro.get("status", "Unknown")
            risk_score = macro.get("risk_score", 50)
            if status == "Abundant" or risk_score < 35:
                result.update(action="add", reasoning="macro liquidity abundant",
                             regime="expansion", regime_icon="🟢")
            elif status == "Crisis" or risk_score > 70:
                result.update(action="reduce", reasoning="macro liquidity crisis",
                             regime="contraction", regime_icon="🔴")
            else:
                result.update(action="hold", reasoning=f"macro liquidity {status}",
                             regime="transition", regime_icon="🟡")
        except Exception:
            result.update(action="hold", reasoning="data unavailable", regime="unknown", regime_icon="⚪")

    elif pool == "gold":
        try:
            usd = get_global_usd_liquidity()
            confidence = usd.get("confidence", 0)
            velocity = usd.get("velocity", 0)
            if confidence is not None and confidence < -10:
                result.update(action="add", reasoning="USD liquidity contracting — gold bullish",
                             regime="bullish", regime_icon="🟢")
            elif confidence is not None and confidence > 20:
                result.update(action="reduce", reasoning="USD liquidity expanding — gold headwind",
                             regime="bearish", regime_icon="🔴")
            else:
                result.update(action="hold", reasoning="USD liquidity neutral",
                             regime="neutral", regime_icon="🟡")
        except Exception:
            result.update(action="hold", reasoning="data unavailable", regime="unknown", regime_icon="⚪")

    elif pool == "commodities":
        try:
            macro = get_macro_liquidity(lookback_days=365)
            dimensions = macro.get("dimension_scores", {})
            copper_gold = dimensions.get("copper_gold", {}).get("score", 50)
            crude = dimensions.get("crude_oil", {}).get("score", 50)
            if copper_gold > 60 and crude > 60:
                result.update(action="add", reasoning="copper/gold + crude both bullish",
                             regime="reflation", regime_icon="🟢")
            elif copper_gold < 40 and crude < 40:
                result.update(action="reduce", reasoning="copper/gold + crude both weak",
                             regime="deflation", regime_icon="🔴")
            else:
                result.update(action="hold", reasoning="commodity signals mixed",
                             regime="neutral", regime_icon="🟡")
        except Exception:
            result.update(action="hold", reasoning="data unavailable", regime="unknown", regime_icon="⚪")

    return result


@st.cache_data(ttl=3600, show_spinner=False)
def get_all_pool_verdicts() -> Dict[str, Dict[str, Any]]:
    """Get heuristic verdicts for all four asset pools."""
    return {pool: get_heuristic_pool_verdict(pool) for pool in ("a_shares", "us_stocks", "gold", "commodities")}
```

- [ ] **Step 3: Commit**

```bash
git add web/data_service.py
git commit -m "feat(data_service): add heuristic pool verdict functions"
```

---

### Task 3: Rewrite Dashboard page

**Files:**
- Rewrite: `web/pages/1_📊_Dashboard.py`

- [ ] **Step 1: Read current Dashboard.py to understand existing structure**

Read `web/pages/1_📊_Dashboard.py` to understand what exists and what needs to change.

- [ ] **Step 2: Rewrite Dashboard with four sections**

Rewrite `web/pages/1_📊_Dashboard.py` with the new structure. The complete implementation should follow this structure:

1. **Verdict Bar** at top — call `get_all_pool_verdicts()`, render overall stance + per-pool action lines
2. **Transmission Alerts** — placeholder section (will be populated by Integration plan)
3. **Asset Pool Cards** — 2x2 grid using `st.columns(2)`, each card shows regime badge + key metrics from existing analyzers
4. **Position Alerts** — load watchlist via `get_all_symbols()`, for each position compute heuristic alert using existing `get_stock_technical_data()`

Key implementation details:
- Import from `web.utils` (new `load_watchlist`, `get_all_symbols`)
- Import from `web.data_service` (new `get_all_pool_verdicts`, existing `get_china_market_signals`, `get_macro_liquidity`, `get_global_usd_liquidity`, `get_leading_indicators`, `get_stock_technical_data`)
- Use `st.cache_data` decorators on data fetches
- Show "Updated: HH:MM" timestamps in each section
- Use Plotly for any charts (no matplotlib)
- Overall stance coloring: defensive=red, cautious=orange, neutral=yellow, aggressive=green
- Per-pool action badges: reduce=red, hold=yellow, add=green

The file should be approximately 300-400 lines. Focus on clear section separation with helper functions `_render_verdict_bar()`, `_render_transmission_alerts()`, `_render_pool_cards()`, `_render_position_alerts()`.

- [ ] **Step 3: Verify Dashboard loads**

Run the Streamlit app and navigate to Dashboard. Verify:
- Verdict bar shows with overall stance and per-pool actions
- Pool cards render in 2x2 grid with regime badges
- Position alerts load from watchlist
- No import errors

- [ ] **Step 4: Commit**

```bash
git add "web/pages/1_📊_Dashboard.py"
git commit -m "feat(dashboard): rewrite with verdict bar + pool cards + position alerts"
```

---

### Task 4: Rewrite Watchlist page with pool tabs

**Files:**
- Rewrite: `web/pages/2_👀_Watchlist.py`

- [ ] **Step 1: Read current Watchlist.py**

Read `web/pages/2_👀_Watchlist.py` to understand existing structure (~345 lines).

- [ ] **Step 2: Rewrite Watchlist with pool-based tabs**

Rewrite `web/pages/2_👀_Watchlist.py`:

- Replace stock/industry tabs with four asset pool tabs: A-Shares, US Stocks, Gold, Commodities
- Each tab header shows regime badge from `get_heuristic_pool_verdict(pool)`
- Per-position display: alert emoji + name + symbol + action suggestion
- Expandable detail: Plotly K-line chart + signal summary
- In-page add/remove: `st.text_input` for symbol + `st.button("+ Add")` calls `add_to_watchlist()`
- Remove button on each position calls `remove_from_watchlist()`
- Keep industry monitoring as a sub-section within A-shares tab
- All charts use Plotly (no matplotlib)
- Use `st.rerun()` after add/remove to refresh the page

Key implementation:
- Each tab is a function `_render_pool_tab(pool, entries, verdict)`
- Inside each tab, iterate over entries and show expanders
- The add widget is at the bottom of each tab
- Industry section is at the bottom of A-shares tab

- [ ] **Step 3: Verify Watchlist loads**

Navigate to Watchlist. Verify:
- Four tabs appear with regime badges
- Positions show in their correct pools
- Add/remove works (add a test symbol, see it appear, remove it)
- Expanders show Plotly charts

- [ ] **Step 4: Commit**

```bash
git add "web/pages/2_👀_Watchlist.py"
git commit -m "feat(watchlist): rewrite with asset pool tabs and in-page management"
```

---

### Task 5: Split Scanner into per-tab modules

**Files:**
- Create: `web/scanner/__init__.py`
- Create: `web/scanner/ashare_scan.py`
- Create: `web/scanner/us_value_scan.py`
- Create: `web/scanner/commodity_scan.py`
- Rewrite: `web/pages/3_🔍_Scanner.py`

- [ ] **Step 1: Read current Scanner.py to understand the four modes**

Read `web/pages/3_🔍_Scanner.py` (~1332 lines) to understand the existing scan modes and extract them.

- [ ] **Step 2: Create scanner package init**

```python
# web/scanner/__init__.py
```

- [ ] **Step 3: Extract A-share scan tab**

Create `web/scanner/ashare_scan.py`:
- Move the "Box Breakout" and "China Market Signals" scan modes from Scanner.py
- Function signature: `def render_ashare_scan(verdict: dict) -> None`
- Shows regime badge at top from verdict
- Each result row has "+ Add to Watchlist" button (calls `web.utils.add_to_watchlist`)
- Uses Plotly for all charts

- [ ] **Step 4: Extract US value scan tab**

Create `web/scanner/us_value_scan.py`:
- Move the "Value Investing" scan mode from Scanner.py
- Function signature: `def render_us_value_scan(verdict: dict) -> None`
- Shows regime badge
- Each result has "+ Add" button

- [ ] **Step 5: Create commodity scan tab**

Create `web/scanner/commodity_scan.py`:
- New tab — scan gold and commodity opportunities
- Function signature: `def render_commodity_scan(verdict: dict) -> None`
- Shows gold and commodities regime badges
- Uses CommodityAnalyzer (if available) or heuristic display
- Each result has "+ Add" button

- [ ] **Step 6: Rewrite Scanner.py as thin shell**

Rewrite `web/pages/3_🔍_Scanner.py` to ~50 lines:

```python
"""🔍 Scanner — market opportunity discovery by asset pool."""
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
from web.ui_theme import apply_custom_css
from web.data_service import get_heuristic_pool_verdict
from web.scanner.ashare_scan import render_ashare_scan
from web.scanner.us_value_scan import render_us_value_scan
from web.scanner.commodity_scan import render_commodity_scan

apply_custom_css()
st.title("🔍 Scanner")
st.caption("Find opportunities across asset pools")

tab_ashare, tab_us, tab_commodity = st.tabs([
    "🇨🇳 A-Share Scan",
    "🇺🇸 US Value Scan",
    "🥇 Gold & Commodity Scan",
])

with tab_ashare:
    render_ashare_scan(get_heuristic_pool_verdict("a_shares"))

with tab_us:
    render_us_value_scan(get_heuristic_pool_verdict("us_stocks"))

with tab_commodity:
    render_commodity_scan(get_heuristic_pool_verdict("gold"))
```

- [ ] **Step 7: Verify Scanner loads**

Navigate to Scanner. Verify:
- Three tabs appear
- A-share scan works (box breakout + signals)
- US value scan works
- Commodity tab renders (may show placeholder if CommodityAnalyzer not integrated yet)
- "+ Add to Watchlist" buttons work

- [ ] **Step 8: Commit**

```bash
git add web/scanner/ "web/pages/3_🔍_Scanner.py"
git commit -m "refactor(scanner): split into per-tab modules with add-to-watchlist"
```

---

### Task 6: Remove matplotlib and unify to Plotly

**Files:**
- Modify: `web/components.py`

- [ ] **Step 1: Read components.py and identify matplotlib functions**

Read `web/components.py` (~1221 lines). Identify all functions that use matplotlib (`import matplotlib`, `plt.`, `fig, ax =`).

- [ ] **Step 2: Remove matplotlib-only chart functions**

Remove functions that have Plotly equivalents already. Keep Plotly versions. Typical candidates:
- `plot_trend_chart()` (matplotlib) — replaced by `plot_interactive_trend()` (Plotly)
- `plot_comparison_bar()` (matplotlib) — rewrite to Plotly
- `plot_technical_chart()` (matplotlib) — rewrite to Plotly

For any function still used by pages, create a Plotly replacement before removing.

- [ ] **Step 3: Extract shared utility functions**

Move `_alert_level()` from Dashboard to `components.py` as a shared function used by Dashboard + Watchlist:

```python
def alert_level(score: float) -> tuple:
    """Map 0-100 score to alert level (label, color, emoji)."""
    if score >= 85:
        return "Strong Signal", "#e74c3c", "🔴"
    elif score >= 75:
        return "Signal", "#e67e22", "🟠"
    elif score >= 60:
        return "Warning", "#f1c40f", "🟡"
    elif score >= 40:
        return "Watch", "#95a5a6", "⚪"
    else:
        return "Quiet", "#2ecc71", "🟢"
```

- [ ] **Step 4: Remove matplotlib imports**

Remove `import matplotlib` and `import matplotlib.pyplot as plt` from `components.py`. Remove `setup_matplotlib_style()` calls from pages.

- [ ] **Step 5: Verify no matplotlib references remain in pages**

Run: `grep -r "matplotlib\|plt\." web/pages/ web/components.py --include="*.py"`
Expected: No matches (or only in comments)

- [ ] **Step 6: Commit**

```bash
git add web/components.py web/pages/
git commit -m "refactor(charts): remove matplotlib, unify to Plotly only"
```

---

### Task 7: Update Home.py and add data freshness

**Files:**
- Modify: `web/Home.py`

- [ ] **Step 1: Update Home.py card descriptions**

Read and update `web/Home.py` to reflect the new system:
- Dashboard description: "Overall verdict, cross-asset alerts, pool status — one page to know what to do"
- Watchlist description: "Positions organized by asset pool with regime context and action suggestions"
- Scanner description: "Find opportunities in A-shares, US value stocks, gold & commodities"

- [ ] **Step 2: Commit**

```bash
git add web/Home.py
git commit -m "refactor(home): update page descriptions for new system"
```

---

### Task 8: Smoke test the full UI

- [ ] **Step 1: Start Streamlit and test all pages**

Run: `streamlit run web/Home.py`

Test checklist:
1. Home: 3 cards render, all links work
2. Dashboard: verdict bar shows, pool cards render, position alerts load
3. Watchlist: 4 pool tabs, positions in correct pools, add/remove works
4. Scanner: 3 tabs, A-share scan runs, US value scan runs, commodity tab renders
5. No matplotlib import errors anywhere
6. Data freshness timestamps visible

- [ ] **Step 2: Fix any issues found during smoke test**

Address any errors or UI issues discovered.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "test: verify UI restructure — all pages functional"
```
