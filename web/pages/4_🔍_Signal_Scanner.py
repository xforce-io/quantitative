"""
🔍 信号扫描器
支持两种模式：箱体突破扫描（A股）和价值投资扫描（美股）
"""

import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# 导入统一的数据服务和组件
from web.data_service import (
    get_candidate_files,
    load_candidates,
    load_all_ashare_stocks,
    get_stock_technical_data,
    scan_box_breakouts,
    get_value_investing_analysis,
    scan_value_stocks,
    get_macro_liquidity,
    get_china_market_signals,
)
from web.components import render_stock_detail_card, render_period_selector
from web.ui_theme import Colors, apply_custom_css

# 导入 AI 面板组件
from web.components_ai_panel import render_ai_right_panel, init_ai_panel_for_page, get_ai_panel_layout
from web.page_registry import get_page_registry


def _render_box_chart(symbol: str, name: str, box_high: float, box_low: float,
                       days: int = 120, key_prefix: str = ""):
    """渲染K线图 + 箱体区域叠加"""
    end_str = datetime.now().strftime('%Y%m%d')
    start_str = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')

    df = get_stock_technical_data(symbol, start_str, end_str)
    if df.empty or len(df) < 10:
        st.warning(f"无法获取 {name} 的K线数据")
        return

    df = df.tail(days)

    if 'trade_date' in df.columns:
        df['date'] = pd.to_datetime(df['trade_date'])
    elif df.index.name == 'trade_date' or df.index.dtype == 'datetime64[ns]':
        df['date'] = df.index
    else:
        df['date'] = range(len(df))

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
        subplot_titles=[f'{name} ({symbol}) K线 + 箱体', '成交量']
    )

    fig.add_trace(go.Candlestick(
        x=df['date'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        increasing_line_color=Colors.RISE,
        decreasing_line_color=Colors.FALL,
        name='K线',
        showlegend=False,
    ), row=1, col=1)

    fig.add_hrect(
        y0=box_low, y1=box_high,
        fillcolor="rgba(52, 152, 219, 0.15)",
        line=dict(color="rgba(52, 152, 219, 0.6)", width=1, dash="dash"),
        annotation_text=f"箱体 {box_low:.2f} ~ {box_high:.2f}",
        annotation_position="top left",
        annotation_font_size=11,
        annotation_font_color=Colors.PRIMARY,
        row=1, col=1,
    )

    colors = [Colors.RISE if c >= o else Colors.FALL
              for c, o in zip(df['close'], df['open'])]
    fig.add_trace(go.Bar(
        x=df['date'],
        y=df['volume'],
        marker_color=colors,
        opacity=0.6,
        name='成交量',
        showlegend=False,
    ), row=2, col=1)

    fig.update_layout(
        height=500,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_rangeslider_visible=False,
        showlegend=False,
    )
    fig.update_xaxes(type='category', row=1, col=1)
    fig.update_xaxes(type='category', row=2, col=1)

    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}box_chart_{symbol}")


def _render_radar_chart(criteria: dict, key: str = ""):
    """渲染五因子雷达图"""
    factors = ['ROE持续性', '负债率', '自由现金流', '护城河', '估值合理性']
    factor_keys = ['roe', 'debt', 'fcf', 'moat', 'valuation']

    values = [criteria.get(k, {}).get('score', 0) for k in factor_keys]
    values.append(values[0])  # 闭合

    fig = go.Figure(data=go.Scatterpolar(
        r=values,
        theta=factors + [factors[0]],
        fill='toself',
        fillcolor='rgba(99, 102, 241, 0.2)',
        line=dict(color='#6366f1', width=2),
        marker=dict(size=6),
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100]),
        ),
        height=350,
        margin=dict(l=60, r=60, t=30, b=30),
        showlegend=False,
    )

    st.plotly_chart(fig, use_container_width=True, key=f"radar_{key}")


# ==================== 箱体突破模式 ====================

def _render_box_breakout_mode(main_col, registry):
    """渲染箱体突破扫描模式"""

    # --- 侧边栏配置 ---
    pool_files = get_candidate_files()
    # 过滤掉美股候选池
    ashare_pools = [f for f in pool_files if not f.startswith('us_')]
    ALL_ASHARE = "📊 全 A 股"
    pool_options = [ALL_ASHARE] + ashare_pools

    selected_pool = st.sidebar.selectbox(
        "📁 候选池",
        options=pool_options,
        index=0,
        help="选择要扫描的股票池，全 A 股约 5000 只（首次较慢，有缓存）"
    )

    st.sidebar.subheader("📦 箱体参数")

    period_options = {
        "1 年": 250,
        "3 年": 750,
        "5 年": 1250,
        "10 年": 2500,
    }
    period_label = st.sidebar.selectbox(
        "箱体周期",
        options=list(period_options.keys()),
        index=1,
        help="Donchian Channel 计算周期"
    )
    period = period_options[period_label]

    volume_threshold = st.sidebar.slider(
        "放量倍数",
        min_value=1.0, max_value=3.0, value=1.5, step=0.1,
        help="成交量需达到均量的 N 倍才确认突破"
    )

    proximity_pct = st.sidebar.slider(
        "接近突破阈值",
        min_value=0.0, max_value=10.0, value=5.0, step=0.5,
        format="%.1f%%",
        help="距箱顶 N% 以内视为「临近突破」，设 0 关闭"
    )

    start_str, end_str = render_period_selector(key_prefix="scanner")
    registry.set_date_range(start_str, end_str)

    # --- 加载候选池 ---
    if selected_pool == ALL_ASHARE:
        candidates_df = load_all_ashare_stocks()
    else:
        candidates_df = load_candidates(selected_pool)

    if candidates_df.empty:
        st.sidebar.warning(f"候选池 '{selected_pool}' 为空")
        return

    st.sidebar.divider()
    st.sidebar.markdown(f"**标的数量**: {len(candidates_df)} 只")

    with main_col:
        st.title("🔍 信号扫描器")
        st.caption("箱体突破模式 — 从候选池中扫描箱体突破信号")

        symbols = candidates_df['symbol'].tolist()
        data_days = period + 120

        with st.status(f"🔄 正在扫描 {len(symbols)} 只标的...", expanded=True) as status:
            results = scan_box_breakouts(
                tuple(symbols),
                period=period,
                days=data_days,
                volume_threshold=volume_threshold,
                proximity_pct=proximity_pct,
            )
            status.update(label=f"✅ 扫描完成 ({len(results)} 只)", state="complete", expanded=False)

        if not results:
            st.warning("扫描未返回结果")
            return

        name_map = dict(zip(candidates_df['symbol'], candidates_df['name']))
        industry_map = dict(zip(candidates_df['symbol'], candidates_df['industry']))

        df_results = pd.DataFrame(results)
        df_results['name'] = df_results['symbol'].map(name_map)
        df_results['industry'] = df_results['symbol'].map(industry_map)

        has_error = df_results['score'].isna() if 'error' in df_results.columns else pd.Series([False] * len(df_results))
        valid = df_results[~has_error].copy() if has_error.any() else df_results.copy()

        up_breakouts = valid[valid['breakout_type'] == 'up']
        near_up = valid[valid['breakout_type'] == 'near_up']
        down_breakouts = valid[valid['breakout_type'] == 'down']
        no_breakout = valid[valid['breakout_type'] == 'none']

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("扫描数", f"{len(valid)}")
        col2.metric("向上突破", f"{len(up_breakouts)}", delta=f"{len(up_breakouts)}" if len(up_breakouts) > 0 else None)
        col3.metric("临近突破", f"{len(near_up)}", delta=f"{len(near_up)}" if len(near_up) > 0 else None, delta_color="off")
        col4.metric("向下突破", f"{len(down_breakouts)}", delta=f"-{len(down_breakouts)}" if len(down_breakouts) > 0 else None, delta_color="inverse")
        col5.metric("箱体内", f"{len(no_breakout)}")

        st.divider()

        display_df = valid.copy()
        display_df = display_df.sort_values('score', ascending=False).reset_index(drop=True)
        display_df.index = display_df.index + 1
        display_df.index.name = '排名'

        direction_map = {'up': '🔼 向上突破', 'near_up': '⏳ 临近突破', 'down': '🔽 向下突破', 'none': '➖ 箱体内'}
        display_df['direction'] = display_df['breakout_type'].map(direction_map)

        st.markdown("### 📊 扫描结果")

        filter_option = st.radio(
            "显示范围",
            ["全部", "突破+临近", "仅向上突破", "仅临近突破", "仅向下突破"],
            horizontal=True
        )

        filtered_df = display_df.copy()
        if filter_option == "突破+临近":
            filtered_df = filtered_df[filtered_df['breakout_type'].isin(['up', 'near_up', 'down'])]
        elif filter_option == "仅向上突破":
            filtered_df = filtered_df[filtered_df['breakout_type'] == 'up']
        elif filter_option == "仅临近突破":
            filtered_df = filtered_df[filtered_df['breakout_type'] == 'near_up']
        elif filter_option == "仅向下突破":
            filtered_df = filtered_df[filtered_df['breakout_type'] == 'down']

        event = None

        if filtered_df.empty:
            st.info("当前筛选条件下无结果")
        else:
            show_cols = ['name', 'industry', 'direction', 'score',
                         'breakout_pct', 'volume_ratio', 'box_range_pct', 'latest_close',
                         'box_high', 'box_low', 'level']
            show_cols = [c for c in show_cols if c in filtered_df.columns]

            event = st.dataframe(
                filtered_df[show_cols],
                column_config={
                    "name": "名称",
                    "industry": "行业",
                    "direction": "方向",
                    "score": st.column_config.ProgressColumn("评分", min_value=0, max_value=100, format="%.1f"),
                    "breakout_pct": st.column_config.NumberColumn("突破幅度%", format="%.2f"),
                    "volume_ratio": st.column_config.NumberColumn("量比", format="%.2f"),
                    "box_range_pct": st.column_config.NumberColumn("箱体宽度%", format="%.2f"),
                    "latest_close": st.column_config.NumberColumn("最新价", format="%.2f"),
                    "box_high": st.column_config.NumberColumn("箱顶", format="%.2f"),
                    "box_low": st.column_config.NumberColumn("箱底", format="%.2f"),
                    "level": "状态",
                },
                use_container_width=True,
                hide_index=False,
                on_select="rerun",
                selection_mode="single-row",
            )

            if len(up_breakouts) > 0:
                top_up = up_breakouts.nlargest(3, 'score')
                top_parts = []
                for _, row in top_up.iterrows():
                    sym = row['symbol']
                    nm = name_map.get(sym, sym)
                    sc = row['score']
                    top_parts.append(f"{nm}({sc:.1f}分)")
                st.success(f"🔼 **向上突破 Top 3**: {', '.join(top_parts)}")

            if len(near_up) > 0:
                top_near = near_up.nlargest(3, 'score')
                near_parts = []
                for _, row in top_near.iterrows():
                    sym = row['symbol']
                    nm = name_map.get(sym, sym)
                    pct = row.get('breakout_pct', 0)
                    near_parts.append(f"{nm}(距箱顶{pct:.1f}%)")
                st.info(f"⏳ **临近突破 Top 3**: {', '.join(near_parts)}")

            # AI Context 注入
            registry.register_data(
                "scanner",
                "breakout_results",
                filtered_df,
                summary_extractor=lambda df: {
                    "scan_params": {
                        "pool": selected_pool,
                        "period": period,
                        "volume_threshold": volume_threshold,
                    },
                    "total_scanned": len(valid),
                    "up_breakout_count": len(up_breakouts),
                    "near_up_count": len(near_up),
                    "down_breakout_count": len(down_breakouts),
                    "no_breakout_count": len(no_breakout),
                    "up_breakout_top10": up_breakouts.nlargest(10, 'score')[
                        ['symbol', 'name', 'score', 'breakout_pct', 'volume_ratio', 'box_range_pct', 'level']
                    ].to_dict('records') if len(up_breakouts) > 0 else [],
                    "down_breakout_top5": down_breakouts.nlargest(5, 'score')[
                        ['symbol', 'name', 'score', 'breakout_pct', 'volume_ratio', 'level']
                    ].to_dict('records') if len(down_breakouts) > 0 else [],
                }
            )

        # --- 选中股票详情 ---
        st.divider()
        st.markdown("### 📋 详细分析")

        selected_rows = (event.selection.rows if event and event.selection else [])

        if selected_rows:
            selected_idx = selected_rows[0]
            selected_row = filtered_df.iloc[selected_idx]
            selected_stock_name = selected_row['name']
            st.info(f"📌 已选中表格中的: **{selected_stock_name}**")
        else:
            if len(up_breakouts) > 0:
                default_options = up_breakouts.sort_values('score', ascending=False)
            else:
                default_options = valid.sort_values('score', ascending=False)

            option_names = default_options['symbol'].map(name_map).dropna().tolist()
            if not option_names:
                option_names = valid['symbol'].map(name_map).dropna().tolist()

            if option_names:
                selected_stock_name = st.selectbox(
                    "选择标的查看详情（或点击上方表格中的行）",
                    options=option_names,
                )
            else:
                selected_stock_name = None

        if selected_stock_name:
            stock_match = valid[valid['symbol'].map(name_map) == selected_stock_name]
            if stock_match.empty:
                stock_match = valid[valid['name'] == selected_stock_name]

            if not stock_match.empty:
                stock_row = stock_match.iloc[0]
                symbol = stock_row['symbol']

                with st.expander(f"📊 {selected_stock_name} ({symbol}) 箱体突破分析", expanded=True):
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("评分", f"{stock_row.get('score', 0):.1f}")
                    m2.metric("方向", direction_map.get(stock_row.get('breakout_type', 'none'), '未知'))
                    m3.metric("突破幅度", f"{stock_row.get('breakout_pct', 0):.2f}%")
                    m4.metric("量比", f"{stock_row.get('volume_ratio', 0):.2f}x")
                    m5.metric("箱体宽度", f"{stock_row.get('box_range_pct', 0):.2f}%")

                    if 'details' in stock_row and isinstance(stock_row['details'], dict):
                        details = stock_row['details']
                        d1, d2, d3 = st.columns(3)
                        d1.metric("突破强度(40%)", f"{details.get('strength_score', 0):.1f}")
                        d2.metric("量能放大(30%)", f"{details.get('volume_score', 0):.1f}")
                        d3.metric("箱体紧度(30%)", f"{details.get('tightness_score', 0):.1f}")

                    if 'signals' in stock_row and isinstance(stock_row['signals'], list):
                        for sig in stock_row['signals']:
                            st.markdown(f"- {sig}")

                    if 'recommendation' in stock_row:
                        st.info(stock_row['recommendation'])

                    st.divider()

                    chart_days = max(period, 120)
                    st.markdown("#### 📈 K线 + 箱体区域")
                    _render_box_chart(
                        symbol=symbol,
                        name=selected_stock_name,
                        box_high=stock_row.get('box_high', 0),
                        box_low=stock_row.get('box_low', 0),
                        days=chart_days,
                        key_prefix="detail_"
                    )

                    st.divider()

                    render_stock_detail_card(
                        symbol=symbol,
                        name=selected_stock_name,
                        start_str=start_str,
                        end_str=end_str,
                        key_prefix="scanner_"
                    )


# ==================== 价值投资模式 ====================

def _render_value_investing_mode(main_col, registry):
    """渲染价值投资扫描模式"""

    # --- 侧边栏配置 ---
    st.sidebar.subheader("📁 候选池")

    pool_files = get_candidate_files()
    us_pools = [f for f in pool_files if f.startswith('us_')]

    input_mode = st.sidebar.radio(
        "选股方式",
        ["候选池", "手动输入"],
        horizontal=True,
        key="value_input_mode",
    )

    symbols = []
    if input_mode == "候选池":
        if us_pools:
            selected_pool = st.sidebar.selectbox(
                "美股候选池",
                options=us_pools,
                index=0,
            )
            candidates_df = load_candidates(selected_pool)
            if not candidates_df.empty:
                # 行业过滤
                industries = sorted(candidates_df['industry'].unique().tolist())
                selected_industries = st.sidebar.multiselect(
                    "行业筛选",
                    options=industries,
                    default=industries,
                    key="value_industries",
                )
                if selected_industries:
                    filtered = candidates_df[candidates_df['industry'].isin(selected_industries)]
                else:
                    filtered = candidates_df
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
    st.sidebar.subheader("⚙️ 阈值调整")

    min_score = st.sidebar.slider(
        "最低评分",
        min_value=0, max_value=100, value=40, step=5,
        key="value_min_score",
        help="只显示总分高于此阈值的股票"
    )

    with main_col:
        st.title("🔍 信号扫描器")
        st.caption("价值投资模式 — 基于五因子模型评估美股基本面")

        if not symbols:
            st.info("请在侧边栏选择候选池或手动输入股票代码")
            return

        # 执行扫描
        with st.status(f"🔄 正在分析 {len(symbols)} 只美股...", expanded=True) as status:
            results = scan_value_stocks(tuple(symbols))
            status.update(label=f"✅ 分析完成 ({len(results)} 只)", state="complete", expanded=False)

        if not results:
            st.warning("分析未返回结果")
            return

        # 过滤有效结果
        valid_results = [r for r in results if 'error' not in r and r.get('score', 0) >= min_score]
        error_results = [r for r in results if 'error' in r]

        # 概览
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

        # 构建结果表格
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

        # 评级颜色
        rating_colors = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🔴'}
        df_table['rating_display'] = df_table['rating'].map(lambda r: f"{rating_colors.get(r, '')} {r}")

        event = st.dataframe(
            df_table,
            column_config={
                "symbol": "代码",
                "name": "名称",
                "rating_display": "评级",
                "score": st.column_config.ProgressColumn("总分", min_value=0, max_value=100, format="%.1f"),
                "roe_score": st.column_config.NumberColumn("ROE(25%)", format="%.0f"),
                "debt_score": st.column_config.NumberColumn("负债(20%)", format="%.0f"),
                "fcf_score": st.column_config.NumberColumn("FCF(20%)", format="%.0f"),
                "moat_score": st.column_config.NumberColumn("护城河(15%)", format="%.0f"),
                "val_score": st.column_config.NumberColumn("估值(20%)", format="%.0f"),
                "forward_pe": st.column_config.NumberColumn("Forward PE", format="%.1f"),
                "market_cap_b": st.column_config.NumberColumn("市值($B)", format="%.1f"),
                "sector": "行业",
                "rating": None,  # 隐藏原始列
            },
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )

        # AI Context 注入
        registry.register_data(
            "scanner",
            "value_investing_results",
            df_table,
            summary_extractor=lambda df: {
                "mode": "value_investing",
                "total_analyzed": len(results),
                "valid_count": len(valid_results),
                "rating_distribution": ratings,
                "top_5": df.nlargest(5, 'score')[
                    ['symbol', 'name', 'rating', 'score', 'forward_pe', 'market_cap_b']
                ].to_dict('records') if len(df) > 0 else [],
            }
        )

        # --- 选中股票详情 ---
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
            # 找到完整分析结果
            detail = next((r for r in results if r['symbol'] == selected_symbol), None)
            if detail and 'error' not in detail:
                criteria = detail.get('criteria', {})
                summary = detail.get('summary', {})

                with st.expander(
                    f"📊 {detail.get('name', selected_symbol)} ({selected_symbol}) — "
                    f"评级 {detail.get('rating', '-')} | 总分 {detail.get('score', 0)}",
                    expanded=True
                ):
                    # 概览指标
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("评级", detail.get('rating', '-'))
                    m2.metric("总分", f"{detail.get('score', 0):.1f}")
                    m3.metric("Forward PE", f"{summary.get('forward_pe', '-')}")
                    m4.metric("市值", f"${summary.get('market_cap_b', 0):.0f}B")
                    m5.metric("价格", f"${summary.get('current_price', 0):.2f}" if summary.get('current_price') else "-")

                    st.divider()

                    # 雷达图 + 因子详情
                    chart_col, detail_col = st.columns([1, 1])

                    with chart_col:
                        st.markdown("#### 五因子雷达图")
                        _render_radar_chart(criteria, key=selected_symbol)

                    with detail_col:
                        st.markdown("#### 因子评分明细")
                        for key, label in [('roe', 'ROE持续性'), ('debt', '负债率'),
                                           ('fcf', '自由现金流'), ('moat', '护城河'), ('valuation', '估值合理性')]:
                            factor = criteria.get(key, {})
                            score = factor.get('score', 0)
                            weight = factor.get('weight', 0)
                            weighted = score * weight / 100

                            bar_color = '🟢' if score >= 70 else '🟡' if score >= 40 else '🔴'
                            st.markdown(f"{bar_color} **{label}** ({weight}%): {score:.0f}分 → 贡献 {weighted:.1f}")

                            # 显示关键数据
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

                    # 信号列表
                    if detail.get('signals'):
                        st.divider()
                        st.markdown("#### 信号列表")
                        for sig in detail['signals']:
                            st.markdown(f"- {sig}")

                    # 建议
                    if detail.get('recommendation'):
                        st.divider()
                        st.info(detail['recommendation'])


# ==================== 宏观流动性模式 ====================

def _hex_to_rgb(hex_color: str) -> str:
    """将 hex 颜色转为 r,g,b 字符串"""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"{r}, {g}, {b}"


def _render_trend_chart(series, column: str, title: str,
                        threshold: float = None, threshold_label: str = "",
                        y_title: str = "", color: str = Colors.PRIMARY,
                        key: str = ""):
    """渲染趋势图（带阈值线）"""
    if series is None or not isinstance(series, pd.DataFrame) or series.empty or column not in series.columns:
        st.info(f"暂无 {title} 数据")
        return

    data = series[column].dropna()
    if data.empty:
        st.info(f"暂无 {title} 数据")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data.index, y=data.values,
        mode='lines', name=title,
        line=dict(color=color, width=2),
        fill='tozeroy',
        fillcolor=f'rgba({_hex_to_rgb(color)}, 0.1)',
    ))

    if threshold is not None:
        fig.add_hline(
            y=threshold, line_dash="dash", line_color=Colors.RISE, line_width=1.5,
            annotation_text=threshold_label or f"阈值: {threshold}",
            annotation_position="top left",
            annotation_font_color=Colors.RISE, annotation_font_size=11,
        )

    fig.update_layout(
        title=title, height=300,
        margin=dict(l=10, r=10, t=40, b=10),
        yaxis_title=y_title, showlegend=False, hovermode='x unified',
    )
    st.plotly_chart(fig, use_container_width=True, key=f"macro_{key}")


def _render_dual_axis_chart(series, col1: str, col2: str,
                            label1: str, label2: str, title: str,
                            color1: str = Colors.PRIMARY,
                            color2: str = Colors.WARNING,
                            key: str = ""):
    """渲染双轴图表"""
    if series is None or not isinstance(series, pd.DataFrame) or series.empty:
        st.info(f"暂无 {title} 数据")
        return

    has_col1 = col1 in series.columns
    has_col2 = col2 in series.columns
    if not has_col1 and not has_col2:
        st.info(f"暂无 {title} 数据")
        return

    fig = go.Figure()
    if has_col1:
        d1 = series[col1].dropna()
        fig.add_trace(go.Scatter(x=d1.index, y=d1.values, mode='lines', name=label1,
                                  line=dict(color=color1, width=2)))
    if has_col2:
        d2 = series[col2].dropna()
        fig.add_trace(go.Scatter(x=d2.index, y=d2.values, mode='lines', name=label2,
                                  line=dict(color=color2, width=2), yaxis='y2'))

    fig.update_layout(
        title=title, height=300,
        margin=dict(l=10, r=50, t=40, b=10),
        yaxis=dict(title=label1, side='left'),
        yaxis2=dict(title=label2, side='right', overlaying='y'),
        legend=dict(x=0, y=1.15, orientation='h'), hovermode='x unified',
    )
    st.plotly_chart(fig, use_container_width=True, key=f"macro_{key}")


def _render_macro_liquidity_mode(main_col, registry):
    """渲染宏观流动性监控模式"""

    # 侧边栏参数
    lookback = st.sidebar.selectbox(
        "回溯周期",
        options=[90, 180, 365, 730],
        index=2,
        format_func=lambda x: {90: '3个月', 180: '半年', 365: '1年', 730: '2年'}[x],
        key="macro_lookback",
    )

    with main_col:
        st.title("🔍 信号扫描器")
        st.caption("宏观流动性模式 — 监控净流动性、SOFR、MOVE指数、日元套利交易")

        with st.status("🔄 正在获取宏观流动性数据...", expanded=True) as status:
            result = get_macro_liquidity(lookback_days=lookback)
            if 'error' in result:
                status.update(label="❌ 数据获取失败", state="error")
                st.error(f"获取数据失败: {result['error']}")
                st.info(
                    "请确保已安装 fredapi 并设置 FRED_API_KEY 环境变量。\n\n"
                    "```bash\n"
                    "pip install fredapi\n"
                    "export FRED_API_KEY=your_key_here\n"
                    "```\n\n"
                    "免费申请: https://fred.stlouisfed.org/docs/api/api_key.html"
                )
                return
            status.update(label="✅ 数据加载完成", state="complete", expanded=False)

        # 顶部状态
        status_en = result.get('status', 'Normal')
        status_cn = result.get('status_cn', '正常')
        status_icon = result.get('status_icon', '🟡')
        risk_score = result.get('risk_score', 0)

        status_colors = {'Abundant': '#2ecc71', 'Normal': '#f1c40f', 'Tight': '#e67e22', 'Crisis': '#e74c3c'}
        color = status_colors.get(status_en, '#95a5a6')

        st.markdown(
            f'<div style="text-align:center;padding:20px;border-radius:12px;'
            f'background:linear-gradient(135deg,{color}22,{color}11);'
            f'border:2px solid {color}44;margin-bottom:20px;">'
            f'<h1 style="margin:0;color:{color};font-size:3rem;">{status_icon} {status_cn}</h1>'
            f'<p style="margin:5px 0 0;color:{color};font-size:1.2rem;">'
            f'{status_en} — 风险评分 {risk_score}/100</p></div>',
            unsafe_allow_html=True,
        )

        # 触发信号
        signals = result.get('signals', [])
        if signals:
            warning_signals = [s for s in signals if '🔴' in s]
            caution_signals = [s for s in signals if '🟠' in s]
            ok_signals = [s for s in signals if '🟢' in s]
            if warning_signals:
                st.error("**预警信号**\n\n" + "\n\n".join(warning_signals))
            if caution_signals:
                st.warning("**关注信号**\n\n" + "\n\n".join(caution_signals))
            if ok_signals:
                with st.expander("正常信号", expanded=False):
                    st.success("\n\n".join(ok_signals))

        st.divider()

        dimensions = result.get('dimensions', {})
        dim_scores = result.get('dimension_scores', {})
        thresholds = result.get('thresholds', {})

        # 维度评分概览
        nl = dimensions.get('net_liquidity', {})
        sofr = dimensions.get('sofr', {})
        move = dimensions.get('move', {})
        yen = dimensions.get('yen_carry', {})

        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("净流动性",
                   f"${nl.get('current', 0):.2f}T" if 'current' in nl else "N/A",
                   delta=f"{nl.get('weekly_change_pct', 0):+.1f}% 周变化" if 'weekly_change_pct' in nl else None,
                   delta_color="normal")
        sc2.metric("SOFR", f"{sofr.get('current', 0):.2f}%" if 'current' in sofr else "N/A")
        sc3.metric("MOVE指数", f"{move.get('current', 0):.1f}" if 'current' in move else "N/A")
        sc4.metric("USD/JPY",
                   f"{yen.get('current_usdjpy', 0):.1f}" if 'current_usdjpy' in yen else "N/A",
                   delta=f"{yen.get('jpy_weekly_change', 0):+.1f}% 周变化" if 'jpy_weekly_change' in yen else None)

        st.divider()

        # 2x2 图表网格
        row1_col1, row1_col2 = st.columns(2)

        with row1_col1:
            st.markdown(f"#### 净流动性 (40%) — 风险 {dim_scores.get('net_liquidity', 0):.0f}")
            nl_series = nl.get('series')
            if isinstance(nl_series, pd.DataFrame) and not nl_series.empty and 'net_liquidity' in nl_series.columns:
                max_val = nl_series['net_liquidity'].max()
                _render_trend_chart(
                    nl_series, 'net_liquidity', '联储净流动性 (百万美元)',
                    threshold=max_val * 0.95, threshold_label=f"峰值-5% ({max_val * 0.95 / 1e6:.2f}T)",
                    y_title='百万美元', color='#3498db', key='net_liquidity',
                )
                components = nl.get('components', {})
                if components:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Fed资产", f"${components.get('fed_assets', 0):.2f}T")
                    c2.metric("TGA", f"${components.get('tga', 0):.2f}T")
                    c3.metric("逆回购", f"${components.get('rrp', 0):.2f}T")
            else:
                st.info(f"净流动性数据不可用{': ' + nl['error'] if 'error' in nl else ''}")

        with row1_col2:
            st.markdown(f"#### SOFR (25%) — 风险 {dim_scores.get('sofr', 0):.0f}")
            sofr_series = sofr.get('series')
            if isinstance(sofr_series, pd.DataFrame) and not sofr_series.empty:
                _render_trend_chart(
                    sofr_series, 'sofr', 'SOFR 利率',
                    threshold=thresholds.get('sofr_high', 5.5),
                    threshold_label=f"预警线 {thresholds.get('sofr_high', 5.5)}%",
                    y_title='%', color='#e67e22', key='sofr',
                )
            else:
                st.info(f"SOFR 数据不可用{': ' + sofr['error'] if 'error' in sofr else ''}")

        row2_col1, row2_col2 = st.columns(2)

        with row2_col1:
            st.markdown(f"#### MOVE指数 (20%) — 风险 {dim_scores.get('move', 0):.0f}")
            move_series = move.get('series')
            if isinstance(move_series, pd.DataFrame) and not move_series.empty:
                _render_trend_chart(
                    move_series, 'move', 'MOVE 债市波动率指数',
                    threshold=thresholds.get('move_high', 130),
                    threshold_label=f"预警线 {thresholds.get('move_high', 130)}",
                    y_title='Index', color='#9b59b6', key='move',
                )
            else:
                st.info(f"MOVE 数据不可用{': ' + move['error'] if 'error' in move else ''}")

        with row2_col2:
            st.markdown(f"#### 日元套利 (15%) — 风险 {dim_scores.get('yen_carry', 0):.0f}")
            yen_series = yen.get('series')
            if isinstance(yen_series, pd.DataFrame) and not yen_series.empty:
                _render_dual_axis_chart(
                    yen_series, col1='usdjpy', col2='yield_spread',
                    label1='USD/JPY', label2='美日利差(%)',
                    title='USD/JPY 汇率 + 美日利差',
                    color1='#2ecc71', color2='#e74c3c', key='yen_carry',
                )
                if yen.get('yield_spread') is not None:
                    y1, y2 = st.columns(2)
                    y1.metric("美日利差", f"{yen['yield_spread']:.2f}%")
                    y2.metric("美国2Y", f"{yen.get('us_2y', 0):.2f}%")
            else:
                st.info(f"日元套利数据不可用{': ' + yen['error'] if 'error' in yen else ''}")

        # AI Context 注入
        registry.register_data(
            "scanner", "liquidity_status", result,
            summary_extractor=lambda data: {
                "status": data.get('status'),
                "status_cn": data.get('status_cn'),
                "risk_score": data.get('risk_score'),
                "signals": data.get('signals', []),
                "dimension_scores": data.get('dimension_scores', {}),
                "net_liquidity": {k: v for k, v in data.get('dimensions', {}).get('net_liquidity', {}).items() if k != 'series'},
                "sofr": {k: v for k, v in data.get('dimensions', {}).get('sofr', {}).items() if k != 'series'},
                "move": {k: v for k, v in data.get('dimensions', {}).get('move', {}).items() if k != 'series'},
                "yen_carry": {k: v for k, v in data.get('dimensions', {}).get('yen_carry', {}).items() if k != 'series'},
            }
        )


# ==================== A股/港股信号模式 ====================

def _render_capital_flow_chart(series, net_col: str, cum_col: str,
                               title: str, color: str = Colors.PRIMARY,
                               key: str = ""):
    """渲染资金流向柱状图 + 累计曲线"""
    if series is None or not isinstance(series, pd.DataFrame) or series.empty:
        st.info(f"暂无 {title} 数据")
        return

    if net_col not in series.columns:
        st.info(f"暂无 {title} 数据")
        return

    net = series[net_col].dropna()

    fig = go.Figure()

    # 柱状图: 正值绿色，负值红色
    colors_bar = [Colors.RISE if v >= 0 else Colors.FALL for v in net.values]
    fig.add_trace(go.Bar(
        x=net.index, y=net.values,
        marker_color=colors_bar, opacity=0.7,
        name='日净流入(亿)',
    ))

    # 累计曲线
    if cum_col in series.columns:
        cum = series[cum_col].dropna()
        fig.add_trace(go.Scatter(
            x=cum.index, y=cum.values,
            mode='lines', name='累计(亿)',
            line=dict(color=color, width=2),
            yaxis='y2',
        ))

    fig.add_hline(y=0, line_dash="dot", line_color="gray", line_width=0.5)

    fig.update_layout(
        title=title, height=300,
        margin=dict(l=10, r=50, t=40, b=10),
        yaxis=dict(title='日净流入(亿)'),
        yaxis2=dict(title='累计(亿)', side='right', overlaying='y'),
        legend=dict(x=0, y=1.15, orientation='h'),
        hovermode='x unified', showlegend=True,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"china_{key}")


def _render_china_market_mode(main_col, registry):
    """渲染 A 股/港股信号监控模式"""

    lookback = st.sidebar.selectbox(
        "回溯周期",
        options=[30, 60, 90, 180],
        index=1,
        format_func=lambda x: {30: '1个月', 60: '2个月', 90: '3个月', 180: '半年'}[x],
        key="china_lookback",
    )

    with main_col:
        st.title("🔍 信号扫描器")
        st.caption("A股/港股信号 — 北向资金、两市成交额、融资融券、南向资金")

        with st.status("🔄 正在获取 A 股/港股市场数据...", expanded=True) as status:
            result = get_china_market_signals(lookback_days=lookback)
            if 'error' in result:
                status.update(label="❌ 数据获取失败", state="error")
                st.error(f"获取数据失败: {result['error']}")
                return
            status.update(label="✅ 数据加载完成", state="complete", expanded=False)

        # 顶部状态
        status_en = result.get('status', 'Neutral')
        status_cn = result.get('status_cn', '中性')
        status_icon = result.get('status_icon', '🟡')
        risk_score = result.get('risk_score', 0)

        status_colors = {'Bullish': '#2ecc71', 'Neutral': '#f1c40f', 'Cautious': '#e67e22', 'Defensive': '#e74c3c'}
        color = status_colors.get(status_en, '#95a5a6')

        st.markdown(
            f'<div style="text-align:center;padding:20px;border-radius:12px;'
            f'background:linear-gradient(135deg,{color}22,{color}11);'
            f'border:2px solid {color}44;margin-bottom:20px;">'
            f'<h1 style="margin:0;color:{color};font-size:3rem;">{status_icon} {status_cn}</h1>'
            f'<p style="margin:5px 0 0;color:{color};font-size:1.2rem;">'
            f'{status_en} — 风险评分 {risk_score}/100</p></div>',
            unsafe_allow_html=True,
        )

        # 触发信号
        signals = result.get('signals', [])
        if signals:
            warning_signals = [s for s in signals if '🔴' in s]
            caution_signals = [s for s in signals if '🟠' in s]
            ok_signals = [s for s in signals if '🟢' in s]
            if warning_signals:
                st.error("**预警信号**\n\n" + "\n\n".join(warning_signals))
            if caution_signals:
                st.warning("**关注信号**\n\n" + "\n\n".join(caution_signals))
            if ok_signals:
                with st.expander("正常信号", expanded=False):
                    st.success("\n\n".join(ok_signals))

        st.divider()

        dimensions = result.get('dimensions', {})
        dim_scores = result.get('dimension_scores', {})

        nb = dimensions.get('northbound', {})
        tv = dimensions.get('turnover', {})
        mg = dimensions.get('margin', {})
        sb = dimensions.get('southbound', {})

        # 概览指标
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("北向资金",
                   f"{nb.get('latest', 0):+.1f}亿" if 'latest' in nb else "N/A",
                   delta=f"近5日 {nb.get('recent_5d_sum', 0):+.1f}亿" if 'recent_5d_sum' in nb else None,
                   delta_color="normal")
        sc2.metric("两市成交额",
                   f"{tv.get('latest', 0):.0f}亿" if 'latest' in tv else "N/A",
                   delta=f"20日均 {tv.get('avg_20d', 0):.0f}亿" if 'avg_20d' in tv else None,
                   delta_color="off")
        sc3.metric("融资余额",
                   f"{mg.get('rz_balance', 0):.0f}亿" if 'rz_balance' in mg else "N/A",
                   delta=f"周变化 {mg.get('weekly_change_pct', 0):+.1f}%" if 'weekly_change_pct' in mg else None,
                   delta_color="normal")
        sc4.metric("南向资金",
                   f"{sb.get('latest', 0):+.1f}亿" if 'latest' in sb else "N/A",
                   delta=f"近5日 {sb.get('recent_5d_sum', 0):+.1f}亿" if 'recent_5d_sum' in sb else None,
                   delta_color="normal")

        st.divider()

        # 2x2 图表网格
        row1_col1, row1_col2 = st.columns(2)

        with row1_col1:
            st.markdown(f"#### 北向资金 (30%) — 风险 {dim_scores.get('northbound', 0):.0f}")
            nb_series = nb.get('series')
            if isinstance(nb_series, pd.DataFrame) and not nb_series.empty:
                _render_capital_flow_chart(
                    nb_series, 'north_net', 'north_cumsum',
                    '北向资金日净流入 + 累计', color='#3498db', key='northbound',
                )
            else:
                st.info(f"北向数据不可用{': ' + nb['error'] if 'error' in nb else ''}")

        with row1_col2:
            st.markdown(f"#### 两市成交额 (25%) — 风险 {dim_scores.get('turnover', 0):.0f}")
            tv_series = tv.get('series')
            if isinstance(tv_series, pd.DataFrame) and not tv_series.empty:
                thresholds = result.get('thresholds', {})
                _render_trend_chart(
                    tv_series, 'total_amount', '两市成交额(亿)',
                    threshold=thresholds.get('turnover_cold', 8000),
                    threshold_label=f"冷淡线 {thresholds.get('turnover_cold', 8000)}亿",
                    y_title='亿元', color='#e67e22', key='turnover',
                )
            else:
                st.info(f"成交额数据不可用{': ' + tv['error'] if 'error' in tv else ''}")

        row2_col1, row2_col2 = st.columns(2)

        with row2_col1:
            st.markdown(f"#### 融资融券 (25%) — 风险 {dim_scores.get('margin', 0):.0f}")
            mg_series = mg.get('series')
            if isinstance(mg_series, pd.DataFrame) and not mg_series.empty:
                _render_trend_chart(
                    mg_series, 'rzye_yi', '融资余额(亿)',
                    y_title='亿元', color='#9b59b6', key='margin',
                )
            else:
                st.info(f"融资融券数据不可用{': ' + mg['error'] if 'error' in mg else ''}")

        with row2_col2:
            st.markdown(f"#### 南向资金 (20%) — 风险 {dim_scores.get('southbound', 0):.0f}")
            sb_series = sb.get('series')
            if isinstance(sb_series, pd.DataFrame) and not sb_series.empty:
                _render_capital_flow_chart(
                    sb_series, 'south_net', 'south_cumsum',
                    '南向资金日净流入 + 累计', color='#2ecc71', key='southbound',
                )
            else:
                st.info(f"南向数据不可用{': ' + sb['error'] if 'error' in sb else ''}")

        # AI Context
        registry.register_data(
            "scanner", "china_market_signals", result,
            summary_extractor=lambda data: {
                "status": data.get('status'),
                "status_cn": data.get('status_cn'),
                "risk_score": data.get('risk_score'),
                "signals": data.get('signals', []),
                "dimension_scores": data.get('dimension_scores', {}),
                "northbound": {k: v for k, v in data.get('dimensions', {}).get('northbound', {}).items() if k != 'series'},
                "turnover": {k: v for k, v in data.get('dimensions', {}).get('turnover', {}).items() if k != 'series'},
                "margin": {k: v for k, v in data.get('dimensions', {}).get('margin', {}).items() if k != 'series'},
                "southbound": {k: v for k, v in data.get('dimensions', {}).get('southbound', {}).items() if k != 'series'},
            }
        )


# ==================== 主函数 ====================

def main():
    apply_custom_css()
    init_ai_panel_for_page("SignalScanner", "pages/4_🔍_Signal_Scanner.py")

    # --- 侧边栏顶部：模式选择 ---
    st.sidebar.header("🎛️ 扫描设置")

    scan_mode = st.sidebar.radio(
        "扫描模式",
        ["宏观流动性 (美股)", "A股/港股信号", "价值投资 (美股)", "箱体突破 (A股)"],
        key="scan_mode",
    )

    registry = get_page_registry()
    main_col, ai_col = get_ai_panel_layout(main_ratio=7, panel_ratio=3)

    if scan_mode == "宏观流动性 (美股)":
        _render_macro_liquidity_mode(main_col, registry)
    elif scan_mode == "A股/港股信号":
        _render_china_market_mode(main_col, registry)
    elif scan_mode == "价值投资 (美股)":
        _render_value_investing_mode(main_col, registry)
    else:
        _render_box_breakout_mode(main_col, registry)

    # 渲染右侧 AI 面板
    with ai_col:
        render_ai_right_panel(session_id="scanner_ai")


if __name__ == "__main__":
    main()
