# System Simplification: 6 Pages → 3 Pages

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate 6 Streamlit pages into 3 focused pages (Dashboard / Watchlist / Scanner), delete redundant pages and unused code, and add signal alert levels.

**Architecture:** The current 6-page system spreads decision-relevant information across too many views. We consolidate into 3 pages aligned with the low-frequency trader's decision loop: (1) Dashboard — macro environment + alerts at a glance, (2) Watchlist — position health, (3) Scanner — opportunity discovery. Pages 1 (Money Flow), 3 (Ranking), 5 (Event Graph), 6 (USD Liquidity) are deleted as standalone pages; their useful data is absorbed into Dashboard or Scanner.

**Tech Stack:** Streamlit, Plotly, existing `data_service.py` functions, existing analyzers

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `web/pages/1_📊_Dashboard.py` | Macro status bar + watchlist alerts + top signals |
| **Keep+Modify** | `web/pages/2_👀_Watchlist.py` | Position tracking (minor: add alert level badges) |
| **Create** | `web/pages/3_🔍_Scanner.py` | Merged scanner: tabs for macro/A-share/value/breakout |
| **Modify** | `web/Home.py` | Update navigation cards to 3 pages |
| **Modify** | `web/data_service.py` | Add `get_dashboard_summary()` function |
| **Delete** | `web/pages/1_💸_Money_Flow.py` | Absorbed into Scanner |
| **Delete** | `web/pages/3_🏆_Ranking.py` | Absorbed into Scanner |
| **Delete** | `web/pages/5_📰_Event_Graph.py` | Remove (not core decision dependency) |
| **Delete** | `web/pages/6_💧_USD_Liquidity.py` | Absorbed into Dashboard macro bar |
| **Delete** | `web/components_ic_report.py` | Unused after page removal |

---

### Task 1: Create Dashboard page

**Files:**
- Create: `web/pages/1_📊_Dashboard.py`
- Modify: `web/data_service.py` (add `get_dashboard_summary()`)

The Dashboard is the "open it and know what to do" page. Three sections stacked vertically:

1. **Macro Status Bar** — one row of colored indicators showing USD Liquidity confidence, macro liquidity status, China market sentiment
2. **Watchlist Alerts** — watchlist items that have triggered signals, sorted by alert level
3. **Top Scanner Signals** — top 5 results from signal scanner (box breakout + value investing)

- [ ] **Step 1: Add `get_dashboard_summary()` to data_service.py**

Append to the end of `web/data_service.py`:

```python
@st.cache_data(ttl=3600, show_spinner=False)
def get_dashboard_summary() -> Dict[str, Any]:
    """
    Aggregate dashboard data: macro status + watchlist alerts + top signals.
    Returns dict with keys: macro, watchlist_alerts, top_signals
    """
    summary = {}

    # 1. Macro status
    macro = {}
    try:
        usd_liq = get_global_usd_liquidity()
        macro['usd_liquidity'] = {
            'confidence': usd_liq.get('confidence'),
            'wow_change': usd_liq.get('wow_change'),
        }
    except Exception:
        macro['usd_liquidity'] = {'confidence': None}

    try:
        macro_liq = get_macro_liquidity(lookback_days=365)
        macro['macro_status'] = macro_liq.get('status', 'Unknown')
        macro['macro_score'] = macro_liq.get('weighted_score', 50)
    except Exception:
        macro['macro_status'] = 'Unknown'
        macro['macro_score'] = 50

    try:
        china = get_china_market_signals(lookback_days=60)
        macro['china_sentiment'] = china.get('status', 'Unknown')
    except Exception:
        macro['china_sentiment'] = 'Unknown'

    summary['macro'] = macro
    return summary
```

- [ ] **Step 2: Create Dashboard page**

Create `web/pages/1_📊_Dashboard.py`:

```python
"""
📊 Dashboard — 打开就知道现在该干什么
"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from web.data_service import (
    get_dashboard_summary,
    get_global_usd_liquidity,
    get_macro_liquidity,
    get_china_market_signals,
    get_stock_money_flow,
    get_stock_technical_data,
    scan_box_breakouts,
    load_candidates,
    get_candidate_files,
)
from web.utils import load_watchlist
from web.ui_theme import Colors, apply_custom_css


# ==================== Signal Alert Levels ====================

def _alert_level(score: float) -> tuple:
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


# ==================== Macro Status Bar ====================

def _render_macro_bar():
    """Render a single-row macro environment status bar."""
    st.markdown("### 🌍 Macro Environment")

    col1, col2, col3 = st.columns(3)

    # USD Liquidity
    with col1:
        try:
            usd = get_global_usd_liquidity()
            confidence = usd.get('confidence')
            wow = usd.get('wow_change')
            if confidence is not None:
                color = "#1f77b4" if confidence > 0 else "#d62728"
                arrow = "↑" if (wow or 0) > 2 else ("↓" if (wow or 0) < -2 else "→")
                st.metric("USD Liquidity", f"{confidence:+.1f}%", f"{arrow} {wow:+.1f}pp" if wow else None)
            else:
                st.metric("USD Liquidity", "N/A")
        except Exception:
            st.metric("USD Liquidity", "Error")

    # Macro Liquidity Status
    with col2:
        try:
            macro = get_macro_liquidity(lookback_days=365)
            status = macro.get('status', 'Unknown')
            score = macro.get('weighted_score', 50)
            status_colors = {
                'Abundant': '🟢', 'Normal': '🟡', 'Tight': '🟠', 'Crisis': '🔴'
            }
            emoji = status_colors.get(status, '⚪')
            st.metric("Macro Liquidity", f"{emoji} {status}", f"Score: {score:.0f}")
        except Exception:
            st.metric("Macro Liquidity", "Error")

    # China Market Sentiment
    with col3:
        try:
            china = get_china_market_signals(lookback_days=60)
            sentiment = china.get('status', 'Unknown')
            sentiment_colors = {
                'Bullish': '🟢', 'Neutral': '🟡', 'Cautious': '🟠', 'Defensive': '🔴'
            }
            emoji = sentiment_colors.get(sentiment, '⚪')
            st.metric("A-Share Sentiment", f"{emoji} {sentiment}")
        except Exception:
            st.metric("A-Share Sentiment", "Error")


# ==================== Watchlist Alerts ====================

def _render_watchlist_alerts():
    """Show watchlist items with alert level badges."""
    st.markdown("### 🚨 Watchlist Alerts")

    watchlist = load_watchlist()
    stocks = watchlist.get('stocks', [])

    if not stocks:
        st.info("No stocks in watchlist. Add some in the Watchlist page.")
        return

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=60)
    start_str = start_dt.strftime('%Y%m%d')
    end_str = end_dt.strftime('%Y%m%d')

    alerts = []
    with st.spinner("Scanning watchlist..."):
        for s_str in stocks:
            parts = s_str.split(' ')
            symbol = parts[0]
            name = parts[1] if len(parts) > 1 else symbol

            try:
                df = get_stock_technical_data(symbol, start_str, end_str)
                if df.empty:
                    continue

                last = df.iloc[-1]
                # Simple composite score from RSI + MA position
                rsi = last.get('RSI', 50)
                close = last.get('close', 0)
                ma20 = last.get('MA20', close)
                ma60 = last.get('MA60', close)

                # Score: RSI extremes + MA trend
                score = 50
                if rsi > 70:
                    score += 20
                elif rsi < 30:
                    score += 25  # Oversold = opportunity for low-freq
                if close > ma20 > ma60:
                    score += 15  # Uptrend
                elif close < ma20 < ma60:
                    score += 10  # Downtrend signal

                level_name, level_color, level_emoji = _alert_level(score)
                alerts.append({
                    'symbol': symbol,
                    'name': name,
                    'score': score,
                    'level': level_name,
                    'emoji': level_emoji,
                    'rsi': rsi,
                    'close': close,
                    'pct_vs_ma20': ((close / ma20) - 1) * 100 if ma20 else 0,
                })
            except Exception:
                continue

    if not alerts:
        st.info("No alerts triggered.")
        return

    # Sort by score descending
    alerts.sort(key=lambda x: x['score'], reverse=True)

    for a in alerts:
        col1, col2, col3, col4 = st.columns([1, 3, 2, 2])
        with col1:
            st.markdown(f"### {a['emoji']}")
        with col2:
            st.markdown(f"**{a['name']}** `{a['symbol']}`")
            st.caption(a['level'])
        with col3:
            st.metric("RSI", f"{a['rsi']:.1f}")
        with col4:
            st.metric("vs MA20", f"{a['pct_vs_ma20']:+.1f}%")


# ==================== Main ====================

def main():
    apply_custom_css()

    st.title("📊 Dashboard")
    st.caption("Macro + Alerts + Signals — one page to know what to do")

    _render_macro_bar()
    st.divider()
    _render_watchlist_alerts()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify Dashboard loads**

Run: `streamlit run web/Home.py` (already running)

Open http://localhost:8501 and navigate to Dashboard page. Verify:
- Macro status bar shows 3 metrics
- Watchlist alerts load and show alert levels
- No import errors in terminal

- [ ] **Step 4: Commit**

```bash
git add web/pages/1_📊_Dashboard.py web/data_service.py
git commit -m "feat(web): add Dashboard page with macro bar and watchlist alerts"
```

---

### Task 2: Create merged Scanner page

**Files:**
- Create: `web/pages/3_🔍_Scanner.py`

Move the Signal Scanner content to the new page number. This is essentially the existing `4_🔍_Signal_Scanner.py` re-numbered to `3_🔍_Scanner.py`. The four scan modes (Macro Liquidity, A-Share/HK, Value Investing, Box Breakout) already cover all the useful functionality from Money Flow and Ranking pages.

- [ ] **Step 1: Copy and rename Signal Scanner**

```bash
cp "web/pages/4_🔍_Signal_Scanner.py" "web/pages/3_🔍_Scanner.py"
```

- [ ] **Step 2: Update page title in the new file**

In `web/pages/3_🔍_Scanner.py`, change the docstring at the top:

```python
"""
🔍 Scanner — 市场机会扫描
Merged: macro liquidity, A-share/HK signals, value investing, box breakout
"""
```

And update the `init_ai_panel_for_page` call:

```python
init_ai_panel_for_page("Scanner", "pages/3_🔍_Scanner.py")
```

- [ ] **Step 3: Verify Scanner loads**

Open http://localhost:8501 and navigate to Scanner page. Verify all 4 scan modes work.

- [ ] **Step 4: Commit**

```bash
git add "web/pages/3_🔍_Scanner.py"
git commit -m "feat(web): add merged Scanner page (renumbered from Signal Scanner)"
```

---

### Task 3: Delete old pages

**Files:**
- Delete: `web/pages/1_💸_Money_Flow.py`
- Delete: `web/pages/3_🏆_Ranking.py`
- Delete: `web/pages/4_🔍_Signal_Scanner.py`
- Delete: `web/pages/5_📰_Event_Graph.py`
- Delete: `web/pages/6_💧_USD_Liquidity.py`
- Delete: `web/components_ic_report.py`

- [ ] **Step 1: Remove old page files**

```bash
git rm "web/pages/1_💸_Money_Flow.py"
git rm "web/pages/3_🏆_Ranking.py"
git rm "web/pages/4_🔍_Signal_Scanner.py"
git rm "web/pages/5_📰_Event_Graph.py"
git rm "web/pages/6_💧_USD_Liquidity.py"
git rm web/components_ic_report.py
```

- [ ] **Step 2: Verify no import errors**

Open http://localhost:8501. Navigate to Dashboard, Watchlist, Scanner. All three should load without errors. Sidebar should show only these 3 pages.

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(web): remove 5 redundant pages, consolidate to 3-page system"
```

---

### Task 4: Update Home.py navigation

**Files:**
- Modify: `web/Home.py`

Update the navigation cards to show only 3 pages (Dashboard, Watchlist, Scanner) instead of 4.

- [ ] **Step 1: Update Home.py**

Replace the entire card navigation section (lines 42-84) with:

```python
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; margin-bottom: 10px;">
        <span style="font-size: 48px;">📊</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("#### Dashboard")
    st.caption("Macro environment, watchlist alerts, top signals — one page to know what to do")
    st.page_link("pages/1_📊_Dashboard.py", label="Open →", icon="📊")

with col2:
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; margin-bottom: 10px;">
        <span style="font-size: 48px;">👀</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("#### Watchlist")
    st.caption("Position tracking, technical indicators, capital flow monitoring")
    st.page_link("pages/2_👀_Watchlist.py", label="Open →", icon="👀")

with col3:
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); border-radius: 15px; margin-bottom: 10px;">
        <span style="font-size: 48px;">🔍</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("#### Scanner")
    st.caption("Macro liquidity, A-share/HK signals, value investing, box breakout scans")
    st.page_link("pages/3_🔍_Scanner.py", label="Open →", icon="🔍")
```

- [ ] **Step 2: Update feature details expander**

Replace the content inside `with st.expander("📖 功能详情", expanded=False):` with:

```python
    st.markdown("""
    #### 1. 📊 Dashboard
    One-page overview of everything you need to know:
    - **Macro Status Bar**: USD liquidity, macro risk, A-share sentiment
    - **Watchlist Alerts**: Positions with triggered signals, sorted by alert level
    - **Signal Levels**: Watch → Warning → Signal → Strong Signal

    #### 2. 👀 Watchlist
    Monitor your positions and sectors:
    - **Capital Flow**: Institutional vs retail flows for each position
    - **Technical Indicators**: MA, MACD, RSI analysis
    - **Sector Tracking**: Industry fund flows and technical charts

    #### 3. 🔍 Scanner
    Find opportunities across markets:
    - **Macro Liquidity** (US): FRED-based risk monitoring
    - **A-Share/HK Signals**: China market sentiment and capital flows
    - **Value Investing** (US): Five-factor fundamental screening
    - **Box Breakout** (A-Share): Donchian Channel breakout detection
    """)
```

- [ ] **Step 3: Verify Home page**

Open http://localhost:8501. Verify 3 cards show and all links work.

- [ ] **Step 4: Commit**

```bash
git add web/Home.py
git commit -m "refactor(web): update Home.py navigation for 3-page layout"
```

---

### Task 5: Add alert level badges to Watchlist page

**Files:**
- Modify: `web/pages/2_👀_Watchlist.py`

Add the same `_alert_level()` function and display alert level badges next to each stock in the watchlist expanders.

- [ ] **Step 1: Add alert level function to Watchlist**

Add at the top of `web/pages/2_👀_Watchlist.py` (after imports, before `calculate_industry_tech_signals`):

```python
def _alert_level(score: float) -> tuple:
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

- [ ] **Step 2: Update stock expander to show alert levels**

In the stock monitoring section (around line 183-195), replace the expander line. Change:

```python
with st.expander(f"{trend_icon} **{name}** ({symbol}) | 机构: {trend_text}", expanded=False):
```

To compute an alert score from technical data and show it:

```python
# Compute alert level from technicals
alert_emoji = "⚪"
alert_label = ""
try:
    _tech_end = datetime.now().strftime('%Y%m%d')
    _tech_start = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')
    _df = get_stock_technical_data(symbol, _tech_start, _tech_end)
    if not _df.empty:
        _last = _df.iloc[-1]
        _rsi = _last.get('RSI', 50)
        _close = _last.get('close', 0)
        _ma20 = _last.get('MA20', _close)
        _ma60 = _last.get('MA60', _close)
        _score = 50
        if _rsi > 70:
            _score += 20
        elif _rsi < 30:
            _score += 25
        if _close > _ma20 > _ma60:
            _score += 15
        elif _close < _ma20 < _ma60:
            _score += 10
        alert_label, _, alert_emoji = _alert_level(_score)
except Exception:
    pass

with st.expander(f"{alert_emoji} **{name}** ({symbol}) | {alert_label} | 机构: {trend_text}", expanded=False):
```

- [ ] **Step 3: Verify Watchlist shows alert badges**

Open http://localhost:8501, navigate to Watchlist. Each stock expander should now show an alert level emoji and label.

- [ ] **Step 4: Commit**

```bash
git add "web/pages/2_👀_Watchlist.py"
git commit -m "feat(web): add signal alert level badges to Watchlist page"
```

---

### Task 6: Clean up unused code in data_service.py

**Files:**
- Modify: `web/data_service.py`

After deleting Event Graph and Ranking pages, check if any `data_service.py` functions are now unused. The following functions were only used by deleted pages:

- `get_ranking_profiles()` — only used by Ranking page
- `rank_stocks()` — only used by Ranking page
- `get_etf_pool()` — only used by Ranking page
- `rank_etfs()` — only used by Ranking page

Do NOT remove functions that Scanner still uses (it re-uses all signal scanner functions).

- [ ] **Step 1: Verify which functions are unused**

```bash
# Search for usage of ranking functions across remaining pages
grep -r "get_ranking_profiles\|rank_stocks\|get_etf_pool\|rank_etfs" web/pages/ web/Home.py --include="*.py"
```

Expected: no matches (only hits would be in deleted files).

- [ ] **Step 2: Remove unused functions from data_service.py**

Remove these functions from `web/data_service.py`:
- `get_ranking_profiles()`
- `rank_stocks()`
- `get_etf_pool()`
- `rank_etfs()`
- `_classify_etf()` (helper only used by `get_etf_pool`)

Also remove their associated imports if any become unused.

- [ ] **Step 3: Verify no import errors**

Open http://localhost:8501 and navigate to all 3 pages. No errors.

- [ ] **Step 4: Commit**

```bash
git add web/data_service.py
git commit -m "refactor(web): remove unused ranking/ETF functions from data_service"
```

---

### Task 7: Clean up __pycache__ and verify final state

- [ ] **Step 1: Clean pycache**

```bash
find web/pages/__pycache__ -name "*.pyc" -path "*Money_Flow*" -o -name "*.pyc" -path "*Ranking*" -o -name "*.pyc" -path "*Signal_Scanner*" -o -name "*.pyc" -path "*Event_Graph*" -o -name "*.pyc" -path "*USD_Liquidity*" | xargs rm -f 2>/dev/null
```

- [ ] **Step 2: Verify final page list**

```bash
ls web/pages/*.py
```

Expected output:
```
web/pages/1_📊_Dashboard.py
web/pages/2_👀_Watchlist.py
web/pages/3_🔍_Scanner.py
```

- [ ] **Step 3: Full smoke test**

Open http://localhost:8501 and verify:
1. Home page shows 3 navigation cards
2. Dashboard: macro bar renders, watchlist alerts load
3. Watchlist: stocks show alert level badges, industry tracking works
4. Scanner: all 4 scan modes (Macro, A-Share, Value, Box Breakout) work

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: clean up pycache and finalize 3-page system"
```
