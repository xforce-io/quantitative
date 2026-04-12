"""
📊 Dashboard — 打开就知道现在该干什么
"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
from datetime import datetime, timedelta

from web.data_service import (
    get_global_usd_liquidity,
    get_macro_liquidity,
    get_china_market_signals,
    get_stock_money_flow,
    get_stock_technical_data,
    get_leading_indicators,
)
from web.utils import load_watchlist
from web.ui_theme import apply_custom_css


# ==================== 信号分级 ====================

ALERT_LEVELS = [
    (85, "强信号", "#e74c3c", "🔴"),
    (75, "信号",   "#e67e22", "🟠"),
    (60, "预警",   "#f1c40f", "🟡"),
    (40, "观察",   "#95a5a6", "⚪"),
    (0,  "平静",   "#2ecc71", "🟢"),
]


def _alert_level(score: float) -> tuple:
    """Map 0-100 score to (label, color, emoji)."""
    for threshold, label, color, emoji in ALERT_LEVELS:
        if score >= threshold:
            return label, color, emoji
    return "平静", "#2ecc71", "🟢"


# ==================== 宏观环境状态条 ====================

_MACRO_STATUS_CN = {
    'Abundant': '宽松', 'Normal': '正常', 'Tight': '偏紧', 'Crisis': '危机',
}
_SENTIMENT_CN = {
    'Bullish': '看多', 'Neutral': '中性', 'Cautious': '谨慎', 'Defensive': '防御',
}
_STATUS_EMOJI = {'Abundant': '🟢', 'Normal': '🟡', 'Tight': '🟠', 'Crisis': '🔴'}
_SENTIMENT_EMOJI = {'Bullish': '🟢', 'Neutral': '🟡', 'Cautious': '🟠', 'Defensive': '🔴'}


def _render_macro_bar():
    """宏观环境一行三灯。"""
    st.markdown("### 🌍 宏观环境")

    col1, col2, col3 = st.columns(3)

    with col1:
        try:
            usd = get_global_usd_liquidity()
            confidence = usd.get('confidence')
            wow = usd.get('wow_change')
            velocity = usd.get('velocity')
            if confidence is not None:
                arrow = "↑" if (wow or 0) > 2 else ("↓" if (wow or 0) < -2 else "→")
                st.metric("美元流动性", f"{confidence:+.1f}%",
                          f"{arrow} 周变化 {wow:+.1f}pp" if wow else None)
                if velocity is not None and abs(velocity) > 1:
                    v_dir = "加速宽松" if velocity > 0 else "加速收紧"
                    st.caption(f"⚡ {v_dir} (v={velocity:+.1f})")
            else:
                st.metric("美元流动性", "暂无数据")
        except Exception:
            st.metric("美元流动性", "获取失败")

    with col2:
        try:
            macro = get_macro_liquidity(lookback_days=365)
            status = macro.get('status', 'Unknown')
            score = macro.get('weighted_score', 50)
            emoji = _STATUS_EMOJI.get(status, '⚪')
            label = _MACRO_STATUS_CN.get(status, status)
            st.metric("宏观流动性", f"{emoji} {label}", f"风险分 {score:.0f}")
        except Exception:
            st.metric("宏观流动性", "获取失败")

    with col3:
        try:
            china = get_china_market_signals(lookback_days=60)
            sentiment = china.get('status', 'Unknown')
            emoji = _SENTIMENT_EMOJI.get(sentiment, '⚪')
            label = _SENTIMENT_CN.get(sentiment, sentiment)
            st.metric("A股情绪", f"{emoji} {label}")
        except Exception:
            st.metric("A股情绪", "获取失败")


# ==================== 领先信号 ====================

_VELOCITY_ARROWS = {
    "accelerating_up": "⬆️",
    "decelerating_up": "↗️",
    "accelerating_down": "⬇️",
    "decelerating_down": "↘️",
    "stable": "→",
}


def _render_leading_signals():
    """领先信号一行四灯。"""
    st.markdown("### ⚡ 领先信号")

    try:
        data = get_leading_indicators(lookback_days=365)
    except Exception:
        st.warning("领先指标数据获取失败")
        return

    col1, col2, col3, col4 = st.columns(4)

    # VIX
    with col1:
        vix = data.get("vix", {})
        if "error" in vix:
            st.metric("VIX 恐慌指数", "获取失败")
        else:
            value = vix.get("value", 0)
            emoji = vix.get("emoji", "⚪")
            delta = vix.get("delta", {})
            arrow = _VELOCITY_ARROWS.get(delta.get("status", "stable"), "→")
            status_cn = delta.get("status_cn", "")

            st.metric("VIX 恐慌指数", f"{emoji} {value:.1f}", f"{arrow} {status_cn}")

            alert = delta.get("alert")
            if alert:
                st.caption(f"⚠️ {alert}")
            streak = delta.get("streak", 0)
            if abs(streak) >= 3:
                direction = "上升" if streak > 0 else "下降"
                st.caption(f"连续 {abs(streak)} 日{direction}")

    # 信用利差
    with col2:
        cs = data.get("credit_spread", {})
        if "error" in cs:
            st.metric("信用利差 HY-IG", "获取失败")
        else:
            spread = cs.get("spread", 0)
            emoji = cs.get("emoji", "⚪")
            delta = cs.get("delta", {})
            arrow = _VELOCITY_ARROWS.get(delta.get("status", "stable"), "→")
            status_cn = delta.get("status_cn", "")

            st.metric("信用利差 HY-IG", f"{emoji} {spread:.2f}%", f"{arrow} {status_cn}")

            alert = delta.get("alert")
            if alert:
                st.caption(f"⚠️ {alert}")

    # 收益率曲线
    with col3:
        yc = data.get("yield_curve", {})
        if "error" in yc:
            st.metric("收益率曲线 2s10s", "获取失败")
        else:
            spread = yc.get("spread", 0)
            emoji = yc.get("emoji", "⚪")
            delta = yc.get("delta", {})
            arrow = _VELOCITY_ARROWS.get(delta.get("status", "stable"), "→")
            status_cn = delta.get("status_cn", "")

            st.metric("收益率曲线 2s10s", f"{emoji} {spread:+.2f}%", f"{arrow} {status_cn}")

            real_yield = yc.get("real_yield")
            if real_yield is not None:
                st.caption(f"实际利率 {real_yield:.1f}%")

            alert = delta.get("alert")
            if alert:
                st.caption(f"⚠️ {alert}")

    # 融资余额
    with col4:
        margin = data.get("margin", {})
        if "error" in margin:
            st.metric("融资余额", margin.get("error", "获取失败"))
        else:
            balance_yi = margin.get("balance_yi", 0)
            delta = margin.get("delta", {})
            arrow = _VELOCITY_ARROWS.get(delta.get("status", "stable"), "→")
            status_cn = delta.get("status_cn", "")

            st.metric("融资余额", f"{balance_yi:.0f} 亿", f"{arrow} {status_cn}")

            alert = delta.get("alert")
            if alert:
                st.caption(f"⚠️ {alert}")
            streak = delta.get("streak", 0)
            if abs(streak) >= 3:
                direction = "增加" if streak > 0 else "减少"
                st.caption(f"连续 {abs(streak)} 日{direction}")


# ==================== 持仓预警 ====================

def _analyze_stock_signals(symbol: str, start_str: str, end_str: str) -> dict | None:
    """
    分析单只股票，返回触发原因列表 + 综合分数。
    每个原因都有人话解释，让用户看得懂为什么。
    """
    try:
        df = get_stock_technical_data(symbol, start_str, end_str)
        if df.empty or len(df) < 5:
            return None
    except Exception:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last

    close = last.get('close', 0)
    rsi = last.get('RSI', 50)
    ma5 = last.get('MA5', close)
    ma20 = last.get('MA20', close)
    ma60 = last.get('MA60', close)
    ma200 = last.get('MA200', close)
    volume = last.get('volume', 0)

    # MACD
    macd_dif = last.get('MACD', last.get('MACD_DIF', 0))
    macd_dea = last.get('MACD_Signal', last.get('MACD_DEA', 0))
    prev_dif = prev.get('MACD', prev.get('MACD_DIF', 0))
    prev_dea = prev.get('MACD_Signal', prev.get('MACD_DEA', 0))

    # 均量
    avg_vol = df['volume'].tail(20).mean() if 'volume' in df.columns else 0

    reasons = []  # (原因文字, 分数贡献, 方向: 'bull'|'bear'|'neutral')
    score = 50  # 基准分

    # ---------- RSI 信号 ----------
    if rsi >= 80:
        reasons.append(("RSI 严重超买 (%.0f)" % rsi, +15, "bear"))
        score += 15
    elif rsi >= 70:
        reasons.append(("RSI 超买 (%.0f)" % rsi, +10, "bear"))
        score += 10
    elif rsi <= 20:
        reasons.append(("RSI 严重超卖 (%.0f)，可能有反弹机会" % rsi, +20, "bull"))
        score += 20
    elif rsi <= 30:
        reasons.append(("RSI 超卖 (%.0f)，关注反弹" % rsi, +15, "bull"))
        score += 15

    # ---------- 均线排列 ----------
    if ma5 and ma20 and ma60:
        if close > ma20 > ma60:
            reasons.append(("多头排列：价格 > MA20 > MA60", +10, "bull"))
            score += 10
            if ma200 and close > ma200:
                reasons.append(("站上年线 MA200", +5, "bull"))
                score += 5
        elif close < ma20 < ma60:
            reasons.append(("空头排列：价格 < MA20 < MA60", +10, "bear"))
            score += 10
            if ma200 and close < ma200:
                reasons.append(("跌破年线 MA200", +5, "bear"))
                score += 5

    # ---------- 均线突破/跌破 ----------
    if ma20 and prev.get('close', 0):
        prev_close = prev.get('close', 0)
        prev_ma20 = prev.get('MA20', prev_close)
        if prev_close < prev_ma20 and close > ma20:
            reasons.append(("突破 MA20 均线", +10, "bull"))
            score += 10
        elif prev_close > prev_ma20 and close < ma20:
            reasons.append(("跌破 MA20 均线", +10, "bear"))
            score += 10

    # ---------- MACD 金叉/死叉 ----------
    if macd_dif and macd_dea and prev_dif and prev_dea:
        if prev_dif <= prev_dea and macd_dif > macd_dea:
            reasons.append(("MACD 金叉", +10, "bull"))
            score += 10
        elif prev_dif >= prev_dea and macd_dif < macd_dea:
            reasons.append(("MACD 死叉", +10, "bear"))
            score += 10

    # ---------- 放量异动 ----------
    if avg_vol > 0 and volume > 0:
        vol_ratio = volume / avg_vol
        if vol_ratio >= 2.0:
            reasons.append(("成交量异动：放量 %.1f 倍" % vol_ratio, +8, "neutral"))
            score += 8
        elif vol_ratio >= 1.5:
            reasons.append(("温和放量 %.1f 倍" % vol_ratio, +4, "neutral"))
            score += 4

    # ---------- 距 MA20 偏离度 ----------
    pct_vs_ma20 = ((close / ma20) - 1) * 100 if ma20 else 0
    if pct_vs_ma20 > 10:
        reasons.append(("偏离 MA20 达 +%.1f%%，注意回调风险" % pct_vs_ma20, +5, "bear"))
        score += 5
    elif pct_vs_ma20 < -10:
        reasons.append(("偏离 MA20 达 %.1f%%，可能超跌" % pct_vs_ma20, +5, "bull"))
        score += 5

    # ---------- Velocity 异动 (MomentumDelta) ----------
    from quant.analysis.indicators.momentum_delta import MomentumDelta

    if 'RSI' in df.columns and len(df) >= 10:
        rsi_series = df['RSI'].dropna()
        if len(rsi_series) >= 10:
            rsi_delta = MomentumDelta.compute(rsi_series, velocity_window=5, zscore_window=min(60, len(rsi_series)))
            if rsi_delta['alert']:
                reasons.append((f"RSI {rsi_delta['status_cn']} ({rsi_delta['alert']})", +8, "neutral"))
                score += 8
            elif abs(rsi_delta['streak']) >= 5:
                direction = "上行" if rsi_delta['streak'] > 0 else "下行"
                reasons.append((f"RSI 连续 {abs(rsi_delta['streak'])} 日{direction}", +5, "neutral"))
                score += 5

    if 'volume' in df.columns and len(df) >= 10:
        vol_series = df['volume'].dropna()
        if len(vol_series) >= 10:
            vol_delta = MomentumDelta.compute(vol_series, velocity_window=5, zscore_window=min(60, len(vol_series)))
            if vol_delta['alert']:
                reasons.append((f"量能 {vol_delta['status_cn']} ({vol_delta['alert']})", +8, "neutral"))
                score += 8

    # 没有任何信号触发
    if not reasons:
        return None

    # cap score
    score = min(score, 100)

    return {
        'close': close,
        'rsi': rsi,
        'pct_vs_ma20': pct_vs_ma20,
        'reasons': reasons,
        'score': score,
    }


def _render_watchlist_alerts():
    """持仓预警：展示每只股票的具体触发原因。"""
    st.markdown("### 🚨 持仓预警")

    watchlist = load_watchlist()
    stocks = watchlist.get('stocks', [])

    if not stocks:
        st.info("暂无自选股，请在 Watchlist 页面添加。")
        return

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=90)
    start_str = start_dt.strftime('%Y%m%d')
    end_str = end_dt.strftime('%Y%m%d')

    alerts = []
    with st.spinner("正在扫描自选股信号..."):
        for s_str in stocks:
            parts = s_str.split(' ')
            symbol = parts[0]
            name = parts[1] if len(parts) > 1 else symbol

            result = _analyze_stock_signals(symbol, start_str, end_str)
            if result is None:
                continue

            level_label, level_color, level_emoji = _alert_level(result['score'])
            alerts.append({
                'symbol': symbol,
                'name': name,
                'emoji': level_emoji,
                'level': level_label,
                'level_color': level_color,
                **result,
            })

    if not alerts:
        st.success("所有持仓平静，暂无预警信号。")
        return

    # 按分数降序
    alerts.sort(key=lambda x: x['score'], reverse=True)

    for a in alerts:
        # 分类 reasons
        bull_reasons = [r for r in a['reasons'] if r[2] == 'bull']
        bear_reasons = [r for r in a['reasons'] if r[2] == 'bear']
        neutral_reasons = [r for r in a['reasons'] if r[2] == 'neutral']

        with st.expander(
            f"{a['emoji']} **{a['name']}** ({a['symbol']}) — {a['level']}",
            expanded=(a['score'] >= 75),
        ):
            # 指标概览行
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("收盘价", f"{a['close']:.2f}")
            m2.metric("RSI", f"{a['rsi']:.1f}")
            m3.metric("vs MA20", f"{a['pct_vs_ma20']:+.1f}%")
            m4.metric("信号分", f"{a['score']}")

            # 触发原因
            if bull_reasons:
                st.markdown("**看多信号：**")
                for reason_text, _, _ in bull_reasons:
                    st.markdown(f"- 🟢 {reason_text}")

            if bear_reasons:
                st.markdown("**风险信号：**")
                for reason_text, _, _ in bear_reasons:
                    st.markdown(f"- 🔴 {reason_text}")

            if neutral_reasons:
                st.markdown("**关注：**")
                for reason_text, _, _ in neutral_reasons:
                    st.markdown(f"- 🔵 {reason_text}")


# ==================== 信号分级说明 ====================

def _render_legend():
    """显示信号分级图例。"""
    with st.expander("📖 信号分级说明", expanded=False):
        st.markdown("""
| 等级 | 分数 | 含义 |
|------|------|------|
| 🔴 强信号 | 85+ | 多个技术指标同时触发，需要立即关注 |
| 🟠 信号 | 75-84 | 有明确的技术信号，建议查看详情 |
| 🟡 预警 | 60-74 | 出现早期迹象，保持观察 |
| ⚪ 观察 | 40-59 | 有轻微异动，暂不需要行动 |
| 🟢 平静 | <40 | 无明显信号，不展示 |

**信号来源：** RSI 超买超卖、均线排列与突破、MACD 金叉死叉、成交量异动、均线偏离度、变化率异动

**变化率标注：**
| 箭头 | 含义 |
|------|------|
| ⬆️ | 加速上行 — 指标在加速上升 |
| ↗️ | 减速上行 — 仍在上升但动能减弱，可能见顶 |
| ⬇️ | 加速下行 — 指标在加速下降 |
| ↘️ | 减速下行 — 仍在下降但跌势减缓，可能见底 |
| → | 平稳 — 无明显变化 |
        """)


# ==================== Main ====================

def main():
    apply_custom_css()

    st.title("📊 总览")
    st.caption("宏观环境 + 领先信号 + 持仓预警 — 打开就知道现在该干什么")

    _render_macro_bar()
    st.divider()
    _render_leading_signals()
    st.divider()
    _render_watchlist_alerts()
    _render_legend()


if __name__ == "__main__":
    main()
