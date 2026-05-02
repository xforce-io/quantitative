"""
📊 Dashboard — decision cockpit: open it and know what to do right now.
"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
from datetime import datetime, timedelta

from web.data_service import get_stock_technical_data
from web.data_service_verdict import get_dashboard_verdict, get_all_regimes, get_active_transmissions
from web.utils import load_watchlist, get_all_symbols
from web.ui_theme import apply_custom_css
from web.components_ai_panel import render_ai_right_panel, init_ai_panel_for_page, get_ai_panel_layout
from web.page_registry import get_page_registry


# ==================== Constants ====================

_POOL_LABELS = {
    "a_shares":    "A 股",
    "us_stocks":   "美股",
    "gold":        "黄金",
    "commodities": "大宗商品",
}

_ACTION_COLORS = {
    "add":    "#27ae60",   # green
    "hold":   "#f39c12",   # amber
    "reduce": "#e74c3c",   # red
}

_ACTION_EMOJIS = {
    "add":    "🟢",
    "hold":   "🟡",
    "reduce": "🔴",
}

_STANCE_ORDER = ["defensive", "cautious", "neutral", "aggressive"]
_STANCE_COLORS = {
    "aggressive": "#27ae60",
    "neutral":    "#f39c12",
    "cautious":   "#e67e22",
    "defensive":  "#e74c3c",
}
_STANCE_EMOJIS = {
    "aggressive": "🟢",
    "neutral":    "🟡",
    "cautious":   "🟠",
    "defensive":  "🔴",
}

# Pool display order
_POOL_ORDER = ["a_shares", "us_stocks", "gold", "commodities"]


# ==================== Helpers ====================

def _regime_icon(regime: str) -> str:
    """Map a regime string to a traffic-light icon."""
    regime_lower = regime.lower() if regime else ""
    if any(k in regime_lower for k in ("risk-on", "expansion", "bullish", "reflation")):
        return "🟢"
    if any(k in regime_lower for k in ("risk-off", "contraction", "bearish", "deflation")):
        return "🔴"
    return "🟡"


def _action_badge(action: str) -> str:
    emoji = _ACTION_EMOJIS.get(action, "⚪")
    label = {"add": "加仓", "hold": "持仓", "reduce": "减仓"}.get(action, action)
    return f"{emoji} {label}"


# ==================== Section: Verdict Bar ====================

def _render_verdict_bar():
    """Overall stance + per-pool action lines."""
    st.markdown("### 🎯 决策总览")

    try:
        verdict = get_dashboard_verdict()
    except Exception:
        st.warning("无法获取资产池判断，请稍后重试。")
        return

    stance = verdict["overall_stance"]
    stance_color = _STANCE_COLORS.get(stance, "#95a5a6")
    stance_emoji = _STANCE_EMOJIS.get(stance, "⚪")
    stance_label = {
        "aggressive": "积极",
        "neutral":    "中性",
        "cautious":   "谨慎",
        "defensive":  "防御",
    }.get(stance, stance)

    # Overall stance banner
    st.markdown(
        f"""
        <div style="
            background:{stance_color}22;
            border-left:4px solid {stance_color};
            border-radius:6px;
            padding:10px 16px;
            margin-bottom:12px;
        ">
            <span style="font-size:1.2rem;font-weight:700;color:{stance_color};">
                {stance_emoji} 当前总体姿态：{stance_label}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Build a pool → verdict lookup for ordered display
    pool_verdicts_map = {v["pool"]: v for v in verdict.get("pool_verdicts", [])}

    # Per-pool action lines
    cols = st.columns(4)
    for i, pool in enumerate(_POOL_ORDER):
        v = pool_verdicts_map.get(pool, {})
        action = v.get("action", "hold")
        regime_dict = v.get("regime", {})
        regime_str = regime_dict.get("regime", "unknown") if isinstance(regime_dict, dict) else str(regime_dict)
        icon = _regime_icon(regime_str)
        reasoning_list = v.get("reasoning", [])
        reasoning = "; ".join(reasoning_list[:2]) if reasoning_list else "—"
        label = _POOL_LABELS.get(pool, pool)
        color = _ACTION_COLORS.get(action, "#95a5a6")
        badge = _action_badge(action)

        with cols[i]:
            st.markdown(
                f"""
                <div style="
                    background:{color}18;
                    border:1px solid {color}55;
                    border-radius:8px;
                    padding:8px 12px;
                    text-align:center;
                ">
                    <div style="font-size:0.8rem;color:#7f8c8d;">{label}</div>
                    <div style="font-size:1rem;font-weight:700;color:{color};">{badge}</div>
                    <div style="font-size:0.75rem;color:#95a5a6;margin-top:4px;">{icon} {reasoning}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Updated timestamp
    updated_at = verdict.get("updated_at")
    if updated_at:
        st.caption(f"更新时间：{updated_at}")


# ==================== Section: Transmission Alerts ====================

def _render_transmission_alerts():
    """Cross-asset transmission signals from TransmissionGraph."""
    st.markdown("### 📡 传导预警")
    try:
        transmissions = get_active_transmissions()
    except Exception:
        transmissions = []

    if not transmissions:
        st.caption("暂无活跃跨资产传导信号")
        return

    for t in transmissions:
        direction_label = "→" if t["direction"] == "direct" else "→ (反向)"
        st.markdown(
            f"**{t['source']}** {t['source_move']:+.1f}% {direction_label} "
            f"**{t['target']}** — {t['expected_target']} "
            f"(强度: {t['strength']:.0%}, 剩余 {t['days_remaining']}天)"
        )


# ==================== Section: Pool Cards ====================

def _render_pool_cards():
    """2×2 grid of asset pool cards with regime badge + key metrics."""
    st.markdown("### 🗂 资产池状态")

    try:
        regimes = get_all_regimes()
        verdict = get_dashboard_verdict()
        pool_verdicts = {v["pool"]: v for v in verdict["pool_verdicts"]}
    except Exception:
        st.warning("无法获取资产池数据。")
        return

    rows = [_POOL_ORDER[:2], _POOL_ORDER[2:]]

    for row_pools in rows:
        cols = st.columns(2)
        for col, pool in zip(cols, row_pools):
            pv = pool_verdicts.get(pool, {})
            regime_data = regimes.get(pool, {})
            action = pv.get("action", "hold")
            regime = regime_data.get("regime", "unknown")
            icon = _regime_icon(regime)
            confidence = regime_data.get("confidence", 0.0)
            reasoning_list = pv.get("reasoning", [])
            reasoning = "; ".join(reasoning_list[:2]) if reasoning_list else "—"
            label = _POOL_LABELS.get(pool, pool)
            color = _ACTION_COLORS.get(action, "#95a5a6")
            badge = _action_badge(action)

            with col:
                st.markdown(
                    f"""
                    <div style="
                        background:{color}12;
                        border:1.5px solid {color}66;
                        border-radius:10px;
                        padding:14px 18px;
                        margin-bottom:10px;
                    ">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:1rem;font-weight:700;color:#2c3e50;">{label}</span>
                            <span style="
                                background:{color};
                                color:#fff;
                                border-radius:12px;
                                padding:2px 10px;
                                font-size:0.8rem;
                                font-weight:600;
                            ">{badge}</span>
                        </div>
                        <div style="margin-top:8px;font-size:0.85rem;color:#555;">
                            {icon} <strong>情景</strong>：{regime}
                            <span style="font-size:0.75rem;color:#95a5a6;margin-left:8px;">置信度 {confidence:.0%}</span>
                        </div>
                        <div style="margin-top:4px;font-size:0.8rem;color:#7f8c8d;">
                            {reasoning}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ==================== Section: Position Alerts ====================

def _compute_position_alert(symbol: str) -> dict:
    """Fetch 90-day technical data and compute a simple RSI-based alert."""
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=90)
    start_str = start_dt.strftime("%Y%m%d")
    end_str = end_dt.strftime("%Y%m%d")

    try:
        df = get_stock_technical_data(symbol, start_str, end_str)
        if df.empty or len(df) < 5:
            return {"action": "hold", "rsi": None, "close": None, "error": "data unavailable"}
    except Exception:
        return {"action": "hold", "rsi": None, "close": None, "error": "fetch failed"}

    last = df.iloc[-1]
    rsi = last.get("RSI", 50)
    close = last.get("close", 0)
    ma20 = last.get("MA20", close)
    pct_vs_ma20 = ((close / ma20) - 1) * 100 if ma20 else 0

    if rsi >= 70:
        action = "sell"
        reason = f"RSI 超买 ({rsi:.0f})，考虑减仓"
    elif rsi <= 30:
        action = "buy"
        reason = f"RSI 超卖 ({rsi:.0f})，买入机会"
    else:
        action = "hold"
        reason = f"RSI 正常 ({rsi:.0f})，持仓观望"

    return {
        "action": action,
        "reason": reason,
        "rsi": rsi,
        "close": close,
        "pct_vs_ma20": pct_vs_ma20,
    }


_SORT_KEY = {"sell": 0, "buy": 1, "hold": 2}
_ALERT_COLORS = {
    "sell": "#e74c3c",
    "buy":  "#27ae60",
    "hold": "#95a5a6",
}
_ALERT_EMOJIS = {
    "sell": "🔴",
    "buy":  "🟢",
    "hold": "⚪",
}


def _render_position_alerts():
    """Watchlist positions with simple action suggestions."""
    st.markdown("### 🚨 持仓提示")

    symbols = get_all_symbols()

    if not symbols:
        st.info("暂无自选股，请在 Watchlist 页面添加。")
        return

    # Fetch pool verdicts for context
    try:
        verdict = get_dashboard_verdict()
        pool_verdicts = {v["pool"]: v for v in verdict["pool_verdicts"]}
    except Exception:
        pool_verdicts = {}

    alerts = []
    with st.spinner("扫描持仓信号..."):
        for entry in symbols:
            symbol = entry["symbol"]
            name = entry.get("name", symbol)
            pool = entry.get("pool", "")

            result = _compute_position_alert(symbol)
            pool_action = pool_verdicts.get(pool, {}).get("action", "hold")  # VerdictEngine action
            pool_label = _POOL_LABELS.get(pool, pool)

            alerts.append({
                "symbol": symbol,
                "name": name,
                "pool": pool,
                "pool_label": pool_label,
                "pool_action": pool_action,
                **result,
            })

    if not alerts:
        st.success("暂无持仓数据。")
        return

    # Sort: sell first, buy second, hold last
    alerts.sort(key=lambda x: _SORT_KEY.get(x.get("action", "hold"), 2))

    for a in alerts:
        action = a.get("action", "hold")
        color = _ALERT_COLORS.get(action, "#95a5a6")
        emoji = _ALERT_EMOJIS.get(action, "⚪")
        reason = a.get("reason", "—")
        pool_badge = _action_badge(a["pool_action"])
        rsi = a.get("rsi")
        close = a.get("close")
        pct = a.get("pct_vs_ma20")
        error = a.get("error")

        label = f"{emoji} **{a['name']}** ({a['symbol']})  —  {reason}"
        expanded = action in ("sell", "buy")

        with st.expander(label, expanded=expanded):
            if error:
                st.caption(f"⚠️ {error}")
            else:
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("收盘价", f"{close:.2f}" if close else "—")
                m2.metric("RSI", f"{rsi:.1f}" if rsi is not None else "—")
                m3.metric("vs MA20", f"{pct:+.1f}%" if pct is not None else "—")
                m4.metric("资产池", a["pool_label"])

            st.caption(f"资产池判断：{pool_badge}  |  池：{a['pool_label']}")


# ==================== Main ====================

def main():
    apply_custom_css()
    init_ai_panel_for_page("Dashboard", "pages/1_📊_Dashboard.py")
    registry = get_page_registry()
    registry.set_page_info("Dashboard", "pages/1_📊_Dashboard.py")

    main_col, ai_col = get_ai_panel_layout()

    with main_col:
        st.title("📊 决策驾驶舱")
        st.caption("打开就知道现在该干什么 — 总览姿态 · 资产池状态 · 持仓提示")

        _render_verdict_bar()
        st.divider()
        _render_transmission_alerts()
        st.divider()
        _render_pool_cards()
        st.divider()
        _render_position_alerts()

    with ai_col:
        render_ai_right_panel(session_id="dashboard")


if __name__ == "__main__":
    main()
