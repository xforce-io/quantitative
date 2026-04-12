"""US value stock scanning tab."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from web.data_service import get_candidate_files, load_candidates, scan_value_stocks
from web.utils import add_to_watchlist


def _regime_badge(verdict: dict) -> None:
    """Render a compact regime badge from a verdict dict."""
    icon = verdict.get("regime_icon", "⚪")
    regime = verdict.get("regime", "unknown")
    action = verdict.get("action", "hold")
    st.caption(f"{icon} Regime: **{regime}** — Action: **{action}**")


def _render_radar_chart(criteria: dict, key: str = "") -> None:
    """Five-factor radar chart."""
    factors = ['ROE持续性', '负债率', '自由现金流', '护城河', '估值合理性']
    factor_keys = ['roe', 'debt', 'fcf', 'moat', 'valuation']

    values = [criteria.get(k, {}).get('score', 0) for k in factor_keys]
    values.append(values[0])  # close the polygon

    fig = go.Figure(data=go.Scatterpolar(
        r=values,
        theta=factors + [factors[0]],
        fill='toself',
        fillcolor='rgba(99, 102, 241, 0.2)',
        line=dict(color='#6366f1', width=2),
        marker=dict(size=6),
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        height=350,
        margin=dict(l=60, r=60, t=30, b=30),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"radar_{key}")


def render_us_value_scan(verdict: dict) -> None:
    """US value stock scanning tab."""
    _regime_badge(verdict)

    # --- Sidebar config ---
    st.sidebar.subheader("📁 候选池")

    pool_files = get_candidate_files()
    us_pools = [f for f in pool_files if f.startswith('us_')]

    input_mode = st.sidebar.radio(
        "选股方式", ["候选池", "手动输入"], horizontal=True, key="value_input_mode",
    )

    symbols = []
    if input_mode == "候选池":
        if us_pools:
            selected_pool = st.sidebar.selectbox("美股候选池", options=us_pools, index=0)
            candidates_df = load_candidates(selected_pool)
            if not candidates_df.empty:
                industries = sorted(candidates_df['industry'].unique().tolist())
                selected_industries = st.sidebar.multiselect(
                    "行业筛选", options=industries, default=industries, key="value_industries",
                )
                filtered = (
                    candidates_df[candidates_df['industry'].isin(selected_industries)]
                    if selected_industries else candidates_df
                )
                symbols = filtered['symbol'].tolist()
                st.sidebar.markdown(f"**标的数量**: {len(symbols)} 只")
            else:
                st.sidebar.warning("候选池为空")
        else:
            st.sidebar.warning("未找到美股候选池文件 (us_*.txt)")
    else:
        manual_input = st.sidebar.text_area(
            "输入美股代码（每行一个或逗号分隔）",
            value="AAPL\nMSFT\nGOOGL\nAMZN\nMETA",
            height=120,
            key="value_manual_input",
        )
        if manual_input:
            symbols = [s.strip().upper() for s in manual_input.replace(',', '\n').split('\n') if s.strip()]

    st.sidebar.divider()
    min_score = st.sidebar.slider(
        "最低评分", min_value=0, max_value=100, value=40, step=5,
        key="value_min_score", help="只显示总分高于此阈值的股票",
    )

    # --- Main content ---
    st.subheader("🇺🇸 US Value Investing Scan")
    st.caption("基于五因子模型评估美股基本面：ROE持续性、负债率、自由现金流、护城河、估值合理性")

    if not symbols:
        st.info("请在侧边栏选择候选池或手动输入股票代码")
        return

    with st.status(f"🔄 正在分析 {len(symbols)} 只美股...", expanded=True) as status:
        results = scan_value_stocks(tuple(symbols))
        status.update(label=f"✅ 分析完成 ({len(results)} 只)", state="complete", expanded=False)

    if not results:
        st.warning("分析未返回结果")
        return

    valid_results = [r for r in results if 'error' not in r and r.get('score', 0) >= min_score]
    error_results = [r for r in results if 'error' in r]

    col1, col2, col3, col4 = st.columns(4)
    ratings = {r: len([x for x in valid_results if x.get('rating') == r]) for r in ['A', 'B', 'C', 'D']}
    col1.metric("分析成功", f"{len(valid_results)}/{len(results)}")
    col2.metric("A级 (优秀)", f"{ratings.get('A', 0)}", delta=f"{ratings.get('A', 0)}" if ratings.get('A', 0) > 0 else None)
    col3.metric("B级 (良好)", f"{ratings.get('B', 0)}")
    col4.metric("C/D级", f"{ratings.get('C', 0) + ratings.get('D', 0)}")

    if error_results:
        with st.expander(f"⚠️ {len(error_results)} 只分析失败", expanded=False):
            for r in error_results:
                st.text(f"{r['symbol']}: {r.get('error', '未知错误')}")

    st.divider()

    if not valid_results:
        st.info("没有满足最低评分阈值的股票")
        return

    table_data = []
    for r in valid_results:
        criteria = r.get('criteria', {})
        summary = r.get('summary', {})
        table_data.append({
            'symbol': r['symbol'],
            'name': r.get('name', r['symbol']),
            'rating': r.get('rating', '-'),
            'score': r.get('score', 0),
            'roe_score': criteria.get('roe', {}).get('score', 0),
            'debt_score': criteria.get('debt', {}).get('score', 0),
            'fcf_score': criteria.get('fcf', {}).get('score', 0),
            'moat_score': criteria.get('moat', {}).get('score', 0),
            'val_score': criteria.get('valuation', {}).get('score', 0),
            'forward_pe': summary.get('forward_pe'),
            'market_cap_b': summary.get('market_cap_b'),
            'sector': summary.get('sector', ''),
        })

    df_table = pd.DataFrame(table_data)

    st.markdown("### 📊 价值投资评分")

    rating_colors = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🔴'}
    df_table['rating_display'] = df_table['rating'].map(lambda r: f"{rating_colors.get(r, '')} {r}")

    event = st.dataframe(
        df_table,
        column_config={
            "symbol": "代码", "name": "名称", "rating_display": "评级",
            "score": st.column_config.ProgressColumn("总分", min_value=0, max_value=100, format="%.1f"),
            "roe_score": st.column_config.NumberColumn("ROE(25%)", format="%.0f"),
            "debt_score": st.column_config.NumberColumn("负债(20%)", format="%.0f"),
            "fcf_score": st.column_config.NumberColumn("FCF(20%)", format="%.0f"),
            "moat_score": st.column_config.NumberColumn("护城河(15%)", format="%.0f"),
            "val_score": st.column_config.NumberColumn("估值(20%)", format="%.0f"),
            "forward_pe": st.column_config.NumberColumn("Forward PE", format="%.1f"),
            "market_cap_b": st.column_config.NumberColumn("市值($B)", format="%.1f"),
            "sector": "行业",
            "rating": None,  # hide raw column
        },
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    # --- Detail section ---
    st.divider()
    st.markdown("### 📋 详细分析")

    selected_rows = (event.selection.rows if event and event.selection else [])

    selected_symbol = None
    if selected_rows:
        selected_idx = selected_rows[0]
        selected_symbol = df_table.iloc[selected_idx]['symbol']
        st.info(f"📌 已选中: **{df_table.iloc[selected_idx]['name']}** ({selected_symbol})")
    else:
        if valid_results:
            options = [f"{r['symbol']} - {r.get('name', r['symbol'])}" for r in valid_results]
            selected_option = st.selectbox(
                "选择标的查看详情（或点击上方表格中的行）",
                options=options,
                key="value_detail_select",
            )
            if selected_option:
                selected_symbol = selected_option.split(' - ')[0]

    if selected_symbol:
        detail = next((r for r in results if r['symbol'] == selected_symbol), None)
        if detail and 'error' not in detail:
            criteria = detail.get('criteria', {})
            summary = detail.get('summary', {})
            name = detail.get('name', selected_symbol)

            with st.expander(
                f"📊 {name} ({selected_symbol}) — "
                f"评级 {detail.get('rating', '-')} | 总分 {detail.get('score', 0)}",
                expanded=True,
            ):
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("评级", detail.get('rating', '-'))
                m2.metric("总分", f"{detail.get('score', 0):.1f}")
                m3.metric("Forward PE", f"{summary.get('forward_pe', '-')}")
                m4.metric("市值", f"${summary.get('market_cap_b', 0):.0f}B")
                m5.metric("价格", f"${summary.get('current_price', 0):.2f}" if summary.get('current_price') else "-")

                # Add to Watchlist
                if st.button(f"+ Add to Watchlist", key=f"wl_value_{selected_symbol}"):
                    pool_added = add_to_watchlist(selected_symbol, name, "us_stocks")
                    st.success(f"Added {name} to watchlist ({pool_added})")

                st.divider()

                chart_col, detail_col = st.columns([1, 1])

                with chart_col:
                    st.markdown("#### 五因子雷达图")
                    _render_radar_chart(criteria, key=selected_symbol)

                with detail_col:
                    st.markdown("#### 因子评分明细")
                    for key, label in [
                        ('roe', 'ROE持续性'), ('debt', '负债率'),
                        ('fcf', '自由现金流'), ('moat', '护城河'), ('valuation', '估值合理性'),
                    ]:
                        factor = criteria.get(key, {})
                        score = factor.get('score', 0)
                        weight = factor.get('weight', 0)
                        weighted = score * weight / 100

                        bar_color = '🟢' if score >= 70 else '🟡' if score >= 40 else '🔴'
                        st.markdown(f"{bar_color} **{label}** ({weight}%): {score:.0f}分 → 贡献 {weighted:.1f}")

                        detail_data = factor.get('detail', {})
                        if isinstance(detail_data, dict):
                            if key == 'roe' and 'latest_roe' in detail_data:
                                st.caption(f"  最新ROE: {detail_data['latest_roe']:.1f}%, 平均: {detail_data.get('avg_roe', 0):.1f}%")
                            elif key == 'debt' and 'debt_ratio' in detail_data:
                                st.caption(f"  负债率: {detail_data['debt_ratio']:.1f}%")
                            elif key == 'fcf' and 'ratio' in detail_data and detail_data['ratio'] is not None:
                                st.caption(f"  FCF/NI: {detail_data['ratio']:.1f}%")
                            elif key == 'moat':
                                parts = []
                                if detail_data.get('gross_margin') is not None:
                                    parts.append(f"毛利率{detail_data['gross_margin']:.1f}%")
                                if detail_data.get('operating_margin') is not None:
                                    parts.append(f"营利率{detail_data['operating_margin']:.1f}%")
                                if parts:
                                    st.caption(f"  {', '.join(parts)}")
                            elif key == 'valuation' and 'pe' in detail_data:
                                st.caption(f"  {detail_data.get('pe_type', '')} PE: {detail_data['pe']:.1f}")

                if detail.get('signals'):
                    st.divider()
                    st.markdown("#### 信号列表")
                    for sig in detail['signals']:
                        st.markdown(f"- {sig}")

                if detail.get('recommendation'):
                    st.divider()
                    st.info(detail['recommendation'])
