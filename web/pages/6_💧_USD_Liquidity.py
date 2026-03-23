"""
💧 全球美元流动性
Global USD Liquidity Confidence — 复刻吸引子 Alice 系统 [A0007]
"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from web.data_service import get_global_usd_liquidity


def main():
    st.title("💧 全球美元流动性")
    st.caption("全球美元流动性置信度 — 基于百分位排名的方向性指标")

    col_range, col_refresh = st.columns([3, 1])
    with col_range:
        display_range = st.radio("时间范围", ["3M", "6M", "1Y"], index=2, horizontal=True)
    with col_refresh:
        force_refresh = st.button("🔄 刷新数据")

    display_days = {'3M': 90, '6M': 180, '1Y': 365}[display_range]

    with st.spinner("正在获取全球美元流动性数据..."):
        result = get_global_usd_liquidity(display_days=display_days, force_refresh=force_refresh)

    if 'error' in result:
        st.error(f"数据获取失败: {result['error']}")
        return

    _render_header(result)
    _render_confidence_chart(result)
    _render_group_cards(result)
    _render_indicator_details(result)


def _render_header(result):
    confidence = result.get('confidence')
    wow_change = result.get('wow_change')

    if confidence is None:
        st.warning("置信度数据不可用")
        return

    if wow_change is not None and wow_change > 2:
        arrow, trend = "↑", "宽松趋势"
    elif wow_change is not None and wow_change < -2:
        arrow, trend = "↓", "收紧趋势"
    else:
        arrow, trend = "→", "震荡"

    color = "#1f77b4" if confidence > 0 else "#d62728"

    st.markdown(
        f'<div style="text-align:center; padding: 1rem;">'
        f'<span style="font-size: 3rem; font-weight: bold; color: {color};">'
        f'{confidence:+.2f}%</span>'
        f'<span style="font-size: 1.5rem; margin-left: 0.5rem;">{arrow} {trend}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if wow_change is not None:
        st.caption(f"较上周: {wow_change:+.2f}pp（对比 5 个交易日前）")

    if result.get('from_cache'):
        st.info("📦 使用缓存数据")


def _render_confidence_chart(result):
    composite = result.get('composite_series')
    if composite is None or composite.dropna().empty:
        st.info("置信度曲线数据不可用")
        return

    series = composite.dropna()

    fig = go.Figure()

    positive = series.clip(lower=0)
    fig.add_trace(go.Scatter(
        x=series.index, y=positive,
        fill='tozeroy',
        fillcolor='rgba(31, 119, 180, 0.3)',
        line=dict(color='rgba(31, 119, 180, 0.8)', width=1),
        name='宽松',
        hovertemplate='%{x|%Y-%m-%d}<br>置信度: %{y:.1f}%<extra></extra>',
    ))

    negative = series.clip(upper=0)
    fig.add_trace(go.Scatter(
        x=series.index, y=negative,
        fill='tozeroy',
        fillcolor='rgba(214, 39, 40, 0.3)',
        line=dict(color='rgba(214, 39, 40, 0.8)', width=1),
        name='收紧',
        hovertemplate='%{x|%Y-%m-%d}<br>置信度: %{y:.1f}%<extra></extra>',
    ))

    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        title="全球美元流动性 (置信度)",
        yaxis_title="置信度 (%)",
        yaxis_range=[-105, 105],
        xaxis_title="",
        height=400,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=50, r=20, t=60, b=40),
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_group_cards(result):
    groups = result.get('groups', {})
    cols = st.columns(3)

    for col, (group_name, group_data) in zip(cols, groups.items()):
        with col:
            conf = group_data.get('confidence')
            weight = group_data.get('weight', 0)
            label = group_data.get('label', group_name)

            if conf is not None:
                st.metric(
                    label=f"{label} ({int(weight * 100)}%)",
                    value=f"{conf:+.1f}%",
                )
            else:
                st.metric(label=f"{label} ({int(weight * 100)}%)", value="N/A")


def _render_indicator_details(result):
    groups = result.get('groups', {})

    with st.expander("📊 子指标详情", expanded=False):
        for group_name, group_data in groups.items():
            st.subheader(group_data.get('label', group_name))

            indicators = group_data.get('indicators', {})
            if not indicators:
                st.caption("无数据")
                continue

            rows = []
            for ind_name, ind_data in indicators.items():
                if 'error' in ind_data:
                    rows.append({
                        '指标': ind_data.get('label', ind_name),
                        '当前值': '❌ ' + ind_data.get('error', ''),
                        '百分位': '',
                        '置信度': '',
                    })
                else:
                    conf = ind_data.get('confidence')
                    rows.append({
                        '指标': ind_data.get('label', ind_name),
                        '当前值': f"{ind_data.get('current_value', 'N/A')}",
                        '百分位': f"{ind_data.get('percentile', 'N/A')}%",
                        '置信度': f"{conf:+.1f}%" if isinstance(conf, (int, float)) else 'N/A',
                    })

            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.caption(f"分析时间: {result.get('analyzed_at', 'N/A')}")


main()
