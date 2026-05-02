"""
Watchlist page — organised by asset pool (A-Shares / US Stocks / Gold / Commodities).
"""

import streamlit as st
from datetime import datetime, timedelta

from web.utils import load_watchlist, save_watchlist, add_to_watchlist, remove_from_watchlist, POOLS
from web.data_service import get_stock_technical_data
from web.data_service_verdict import get_regime, get_all_regimes
from web.ui_theme import apply_custom_css
from web.components_ai_panel import render_ai_right_panel, init_ai_panel_for_page, get_ai_panel_layout
from web.page_registry import get_page_registry

# ---------- helpers ----------

POOL_META = {
    "a_shares":    {"flag": "🇨🇳", "label": "A股"},
    "us_stocks":   {"flag": "🇺🇸", "label": "美股"},
    "gold":        {"flag": "🥇",  "label": "黄金"},
    "commodities": {"flag": "🛢",  "label": "大宗"},
}


_REGIME_ICON_MAP = {
    "risk-on": "🟢", "expansion": "🟢", "bullish": "🟢", "reflation": "🟢",
    "risk-off": "🔴", "contraction": "🔴", "bearish": "🔴", "deflation": "🔴",
}


def _regime_icon(regime: str) -> str:
    return _REGIME_ICON_MAP.get(regime.lower(), "🟡")


def _regime_badge(regime_dict: dict) -> str:
    regime = regime_dict.get("regime", "unknown")
    confidence = regime_dict.get("confidence", 0)
    icon = _regime_icon(regime)
    return f"{icon} **{regime}** (confidence: {confidence:.0%})"


def _parse_input(raw: str):
    """Parse 'SYMBOL Name' or just 'SYMBOL' — returns (symbol, name)."""
    parts = raw.strip().split(None, 1)
    if not parts:
        return None, None
    symbol = parts[0].upper()
    name   = parts[1] if len(parts) > 1 else symbol
    return symbol, name


def _tech_summary(symbol: str) -> str:
    """Return a short metric string from recent technical data."""
    try:
        end   = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
        df = get_stock_technical_data(symbol, start, end)
        if df.empty:
            return "无数据"
        row   = df.iloc[-1]
        price = row.get("close", 0)
        rsi   = row.get("RSI", float("nan"))
        ma20  = row.get("MA20", float("nan"))
        ma60  = row.get("MA60", float("nan"))
        above = "↑MA20" if price > ma20 else "↓MA20"
        rsi_s = f"{rsi:.0f}" if rsi == rsi else "—"
        return f"收 {price:.2f}  RSI {rsi_s}  {above}"
    except Exception:
        return "获取失败"


def _rsi_color(symbol: str) -> str:
    """Return colored RSI indicator string."""
    try:
        end   = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
        df    = get_stock_technical_data(symbol, start, end)
        if df.empty:
            return "⚪"
        rsi = df.iloc[-1].get("RSI", 50)
        if rsi > 70:
            return "🔴"
        if rsi < 30:
            return "🟢"
        return "🟡"
    except Exception:
        return "⚪"


# ---------- per-pool tab ----------

def render_pool_tab(pool: str, regime: dict, watchlist: dict):
    meta      = POOL_META[pool]
    positions = watchlist.get(pool, [])  # list of {symbol, name}

    # Regime badge
    st.markdown(f"**市场状态**: {_regime_badge(regime)}")
    drivers = regime.get("drivers", [])
    if drivers:
        st.caption(" · ".join(drivers))

    st.divider()

    # ---- positions ----
    if not positions:
        st.info("暂无持仓/关注标的，在下方添加。")
    else:
        for entry in positions:
            symbol = entry["symbol"]
            name   = entry["name"]

            # Determine expander icon based on RSI
            icon = _rsi_color(symbol)

            with st.expander(f"{icon} **{name}** · `{symbol}`", expanded=False):
                col_data, col_btn = st.columns([5, 1])
                with col_data:
                    summary = _tech_summary(symbol)
                    st.caption(summary)

                    # Mini metric row
                    try:
                        end   = datetime.now().strftime("%Y%m%d")
                        start = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
                        df    = get_stock_technical_data(symbol, start, end)
                        if not df.empty:
                            row   = df.iloc[-1]
                            price = row.get("close", 0)
                            rsi   = row.get("RSI", float("nan"))
                            ma20  = row.get("MA20", float("nan"))
                            ma60  = row.get("MA60", float("nan"))

                            m1, m2, m3, m4 = st.columns(4)
                            m1.metric("收盘价", f"{price:.2f}")
                            m2.metric("RSI(14)", f"{rsi:.1f}" if rsi == rsi else "—",
                                      delta="超买" if rsi > 70 else ("超卖" if rsi < 30 else "正常"))
                            m3.metric("MA20", f"{ma20:.2f}" if ma20 == ma20 else "—",
                                      delta="↑" if price > ma20 else "↓")
                            m4.metric("MA60", f"{ma60:.2f}" if ma60 == ma60 else "—",
                                      delta="↑" if price > ma60 else "↓")

                            # Simple Plotly price chart
                            if len(df) > 5:
                                import plotly.graph_objects as go
                                fig = go.Figure()
                                fig.add_trace(go.Scatter(
                                    x=df.index if df.index.name == "trade_date" else df.get("trade_date", df.index),
                                    y=df["close"],
                                    mode="lines",
                                    name="收盘价",
                                    line=dict(color="#3498db", width=1.5),
                                ))
                                if "MA20" in df.columns:
                                    fig.add_trace(go.Scatter(
                                        x=df.index if df.index.name == "trade_date" else df.get("trade_date", df.index),
                                        y=df["MA20"],
                                        mode="lines",
                                        name="MA20",
                                        line=dict(color="#e67e22", width=1, dash="dot"),
                                    ))
                                fig.update_layout(
                                    height=200,
                                    margin=dict(l=0, r=0, t=4, b=0),
                                    showlegend=True,
                                    legend=dict(orientation="h", y=1.1, x=0),
                                )
                                st.plotly_chart(fig, use_container_width=True,
                                                key=f"chart_{pool}_{symbol}")
                    except Exception:
                        pass

                    # Regime context
                    regime_label = regime.get("regime", "unknown")
                    confidence = regime.get("confidence", 0)
                    st.caption(f"Regime: {regime_label} (confidence: {confidence:.0%})")
                    st.caption("Signal validation: pending")

                with col_btn:
                    if st.button("移除", key=f"rm_{pool}_{symbol}", type="secondary"):
                        remove_from_watchlist(symbol)
                        st.rerun()

    st.divider()

    # ---- add section ----
    st.markdown("**+ 添加标的**")
    col_inp, col_add = st.columns([4, 1])
    with col_inp:
        raw = st.text_input(
            "代码 [名称]",
            placeholder="例: 000001.SZ 平安银行  或  AAPL",
            label_visibility="collapsed",
            key=f"add_input_{pool}",
        )
    with col_add:
        if st.button("添加", key=f"add_btn_{pool}", type="primary"):
            if raw.strip():
                symbol, name = _parse_input(raw)
                if symbol:
                    add_to_watchlist(symbol, name, pool)
                    st.rerun()
            else:
                st.warning("请输入代码")

    # ---- industry sub-section (A-shares only) ----
    if pool == "a_shares":
        industries = watchlist.get("industries", [])
        if industries or True:  # always show section
            st.divider()
            st.markdown("#### 🏭 关注行业")
            if not industries:
                st.caption("暂无关注行业。可在侧边栏管理行业列表。")
            else:
                for ind in industries:
                    st.markdown(f"- {ind}")


# ---------- main ----------

def main():
    apply_custom_css()
    init_ai_panel_for_page("Watchlist", "pages/2_👀_Watchlist.py")
    registry = get_page_registry()
    registry.set_page_info("Watchlist", "pages/2_👀_Watchlist.py")

    main_col, ai_col = get_ai_panel_layout()

    with main_col:
        st.title("👀 自选监控")

        watchlist = load_watchlist()

        with st.spinner("正在加载市场状态..."):
            regimes = get_all_regimes()

        tab_labels = [
            f"{POOL_META[p]['flag']} {POOL_META[p]['label']} {_regime_icon(regimes[p].get('regime', 'unknown'))} {regimes[p].get('regime', 'unknown')}"
            for p in POOLS
        ]
        tabs = st.tabs(tab_labels)

        for tab, pool in zip(tabs, POOLS):
            with tab:
                render_pool_tab(pool, regimes[pool], watchlist)

    with ai_col:
        render_ai_right_panel(session_id="watchlist")


if __name__ == "__main__":
    main()
