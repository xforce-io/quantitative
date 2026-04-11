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
