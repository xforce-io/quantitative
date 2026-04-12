"""A-share scanning tab: box breakout + China market signals."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

from web.data_service import (
    get_candidate_files,
    load_candidates,
    load_all_ashare_stocks,
    get_stock_technical_data,
    scan_box_breakouts,
    get_china_market_signals,
)
from web.components import render_stock_detail_card, render_period_selector
from web.ui_theme import Colors
from web.utils import add_to_watchlist


def _regime_badge(verdict: dict) -> None:
    """Render a compact regime badge from a verdict dict."""
    icon = verdict.get("regime_icon", "⚪")
    regime = verdict.get("regime", "unknown")
    action = verdict.get("action", "hold")
    st.caption(f"{icon} Regime: **{regime}** — Action: **{action}**")


def _render_box_chart(symbol: str, name: str, box_high: float, box_low: float,
                      days: int = 120, key_prefix: str = "") -> None:
    """K-line chart with box overlay."""
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
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.7, 0.3], subplot_titles=[f'{name} ({symbol}) K线 + 箱体', '成交量'])
    fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'],
                                  low=df['low'], close=df['close'],
                                  increasing_line_color=Colors.RISE, decreasing_line_color=Colors.FALL,
                                  name='K线', showlegend=False), row=1, col=1)
    fig.add_hrect(y0=box_low, y1=box_high, fillcolor="rgba(52, 152, 219, 0.15)",
                  line=dict(color="rgba(52, 152, 219, 0.6)", width=1, dash="dash"),
                  annotation_text=f"箱体 {box_low:.2f} ~ {box_high:.2f}",
                  annotation_position="top left", annotation_font_size=11,
                  annotation_font_color=Colors.PRIMARY, row=1, col=1)
    colors_bar = [Colors.RISE if c >= o else Colors.FALL for c, o in zip(df['close'], df['open'])]
    fig.add_trace(go.Bar(x=df['date'], y=df['volume'], marker_color=colors_bar,
                         opacity=0.6, name='成交量', showlegend=False), row=2, col=1)
    fig.update_layout(height=500, margin=dict(l=10, r=10, t=40, b=10),
                      xaxis_rangeslider_visible=False, showlegend=False)
    fig.update_xaxes(type='category', row=1, col=1)
    fig.update_xaxes(type='category', row=2, col=1)
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}box_chart_{symbol}")


def _render_capital_flow_chart(series: pd.DataFrame, net_col: str, cum_col: str,
                               title: str, color: str = Colors.PRIMARY, key: str = "") -> None:
    """Capital flow bar chart + cumulative line."""
    if series is None or series.empty or net_col not in series.columns:
        st.info(f"暂无 {title} 数据")
        return
    net = series[net_col].dropna()
    colors_bar = [Colors.RISE if v >= 0 else Colors.FALL for v in net.values]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=net.index, y=net.values, marker_color=colors_bar, opacity=0.7, name='日净流入(亿)'))
    if cum_col in series.columns:
        cum = series[cum_col].dropna()
        fig.add_trace(go.Scatter(x=cum.index, y=cum.values, mode='lines', name='累计(亿)',
                                  line=dict(color=color, width=2), yaxis='y2'))
    fig.add_hline(y=0, line_dash="dot", line_color="gray", line_width=0.5)
    fig.update_layout(title=title, height=280, margin=dict(l=10, r=50, t=40, b=10),
                      yaxis=dict(title='日净流入(亿)'),
                      yaxis2=dict(title='累计(亿)', side='right', overlaying='y'),
                      legend=dict(x=0, y=1.15, orientation='h'), hovermode='x unified')
    st.plotly_chart(fig, use_container_width=True, key=f"china_{key}")


def _render_trend_chart(series: pd.DataFrame, column: str, title: str,
                        threshold: float = None, threshold_label: str = "",
                        y_title: str = "", color: str = Colors.PRIMARY, key: str = "") -> None:
    """Simple area trend chart with optional threshold line."""
    if series is None or series.empty or column not in series.columns:
        st.info(f"暂无 {title} 数据")
        return
    data = series[column].dropna()
    if data.empty:
        st.info(f"暂无 {title} 数据")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=data.index, y=data.values, mode='lines', name=title,
                              line=dict(color=color, width=2), fill='tozeroy',
                              fillcolor='rgba(52, 152, 219, 0.1)'))
    if threshold is not None:
        fig.add_hline(y=threshold, line_dash="dash", line_color=Colors.RISE, line_width=1.5,
                      annotation_text=threshold_label or f"阈值: {threshold}",
                      annotation_position="top left",
                      annotation_font_color=Colors.RISE, annotation_font_size=11)
    fig.update_layout(title=title, height=280, margin=dict(l=10, r=10, t=40, b=10),
                      yaxis_title=y_title, showlegend=False, hovermode='x unified')
    st.plotly_chart(fig, use_container_width=True, key=f"china_{key}")


def _render_box_breakout_section(verdict: dict) -> None:
    """Box breakout scanner — sidebar config + results table."""
    pool_files = get_candidate_files()
    ashare_pools = [f for f in pool_files if not f.startswith('us_')]
    ALL_ASHARE = "📊 全 A 股"
    pool_options = [ALL_ASHARE] + ashare_pools

    selected_pool = st.sidebar.selectbox(
        "📁 候选池",
        options=pool_options,
        index=0,
        help="全 A 股约 5000 只（首次较慢，有缓存）",
    )

    st.sidebar.subheader("📦 箱体参数")

    period_options = {"1 年": 250, "3 年": 750, "5 年": 1250, "10 年": 2500}
    period_label = st.sidebar.selectbox(
        "箱体周期", options=list(period_options.keys()), index=1,
        help="Donchian Channel 计算周期",
    )
    period = period_options[period_label]

    volume_threshold = st.sidebar.slider(
        "放量倍数", min_value=1.0, max_value=3.0, value=1.5, step=0.1,
        help="成交量需达到均量的 N 倍才确认突破",
    )

    proximity_pct = st.sidebar.slider(
        "接近突破阈值", min_value=0.0, max_value=10.0, value=5.0, step=0.5,
        format="%.1f%%",
        help="距箱顶 N% 以内视为「临近突破」，设 0 关闭",
    )

    start_str, end_str = render_period_selector(key_prefix="ashare_scanner")

    if selected_pool == ALL_ASHARE:
        candidates_df = load_all_ashare_stocks()
    else:
        candidates_df = load_candidates(selected_pool)

    if candidates_df.empty:
        st.sidebar.warning(f"候选池 '{selected_pool}' 为空")
        return

    st.sidebar.divider()
    st.sidebar.markdown(f"**标的数量**: {len(candidates_df)} 只")

    # --- Main content ---
    st.subheader("📦 箱体突破扫描")
    st.caption("从候选池中扫描 Donchian Channel 箱体突破信号")

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

    display_df = valid.sort_values('score', ascending=False).reset_index(drop=True)
    display_df.index = display_df.index + 1
    display_df.index.name = '排名'

    direction_map = {
        'up': '🔼 向上突破', 'near_up': '⏳ 临近突破',
        'down': '🔽 向下突破', 'none': '➖ 箱体内',
    }
    display_df['direction'] = display_df['breakout_type'].map(direction_map)

    st.markdown("### 📊 扫描结果")

    filter_option = st.radio(
        "显示范围",
        ["全部", "突破+临近", "仅向上突破", "仅临近突破", "仅向下突破"],
        horizontal=True,
        key="ashare_filter",
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
                "name": "名称", "industry": "行业", "direction": "方向",
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
            parts = [f"{name_map.get(r['symbol'], r['symbol'])}({r['score']:.1f}分)"
                     for _, r in top_up.iterrows()]
            st.success(f"🔼 **向上突破 Top 3**: {', '.join(parts)}")

        if len(near_up) > 0:
            top_near = near_up.nlargest(3, 'score')
            parts = [f"{name_map.get(r['symbol'], r['symbol'])}(距箱顶{r.get('breakout_pct', 0):.1f}%)"
                     for _, r in top_near.iterrows()]
            st.info(f"⏳ **临近突破 Top 3**: {', '.join(parts)}")

    # --- Detail section ---
    st.divider()
    st.markdown("### 📋 详细分析")

    selected_rows = (event.selection.rows if event and event.selection else [])

    if selected_rows:
        selected_row = filtered_df.iloc[selected_rows[0]]
        selected_stock_name = selected_row['name']
        st.info(f"📌 已选中: **{selected_stock_name}**")
    else:
        default_options = (
            up_breakouts.sort_values('score', ascending=False)
            if len(up_breakouts) > 0 else valid.sort_values('score', ascending=False)
        )
        option_names = default_options['symbol'].map(name_map).dropna().tolist()
        if not option_names:
            option_names = valid['symbol'].map(name_map).dropna().tolist()

        selected_stock_name = None
        if option_names:
            selected_stock_name = st.selectbox(
                "选择标的查看详情（或点击上方表格中的行）",
                options=option_names,
                key="ashare_detail_select",
            )

    if selected_stock_name:
        stock_match = valid[valid['symbol'].map(name_map) == selected_stock_name]
        if stock_match.empty:
            stock_match = valid[valid['name'] == selected_stock_name]

        if not stock_match.empty:
            stock_row = stock_match.iloc[0]
            symbol = stock_row['symbol']

            with st.expander(f"📊 {selected_stock_name} ({symbol}) 箱体突破分析", expanded=True):
                cols = st.columns(5)
                cols[0].metric("评分", f"{stock_row.get('score', 0):.1f}")
                cols[1].metric("方向", direction_map.get(stock_row.get('breakout_type', 'none'), '未知'))
                cols[2].metric("突破幅度", f"{stock_row.get('breakout_pct', 0):.2f}%")
                cols[3].metric("量比", f"{stock_row.get('volume_ratio', 0):.2f}x")
                cols[4].metric("箱体宽度", f"{stock_row.get('box_range_pct', 0):.2f}%")

                if 'signals' in stock_row and isinstance(stock_row['signals'], list):
                    for sig in stock_row['signals']:
                        st.markdown(f"- {sig}")
                if 'recommendation' in stock_row:
                    st.info(stock_row['recommendation'])

                if st.button("+ Add to Watchlist", key=f"wl_box_{symbol}"):
                    pool_added = add_to_watchlist(symbol, selected_stock_name, "a_shares")
                    st.success(f"Added {selected_stock_name} to watchlist ({pool_added})")

                st.divider()
                st.markdown("#### 📈 K线 + 箱体区域")
                _render_box_chart(symbol=symbol, name=selected_stock_name,
                                  box_high=stock_row.get('box_high', 0),
                                  box_low=stock_row.get('box_low', 0),
                                  days=max(period, 120), key_prefix="detail_")
                st.divider()
                render_stock_detail_card(symbol=symbol, name=selected_stock_name,
                                         start_str=start_str, end_str=end_str,
                                         key_prefix="ashare_scanner_")


def _render_china_market_signals_section() -> None:
    """China A-share market signals: northbound, turnover, margin, southbound."""
    lookback = st.sidebar.selectbox(
        "回溯周期", options=[30, 60, 90, 180], index=1,
        format_func=lambda x: {30: '1个月', 60: '2个月', 90: '3个月', 180: '半年'}[x],
        key="china_lookback",
    )
    st.subheader("📡 A股/港股市场信号")
    with st.status("🔄 正在获取 A 股/港股市场数据...", expanded=True) as status:
        result = get_china_market_signals(lookback_days=lookback)
        if 'error' in result:
            status.update(label="❌ 数据获取失败", state="error")
            st.error(f"获取数据失败: {result['error']}")
            return
        status.update(label="✅ 数据加载完成", state="complete", expanded=False)

    status_en = result.get('status', 'Neutral')
    risk_score = result.get('risk_score', 0)
    color = {'Bullish': '#2ecc71', 'Neutral': '#f1c40f', 'Cautious': '#e67e22', 'Defensive': '#e74c3c'}.get(status_en, '#95a5a6')
    st.markdown(
        f'<div style="padding:12px;border-radius:8px;background:{color}22;border:2px solid {color}44;margin-bottom:12px;">'
        f'<strong style="color:{color};">{result.get("status_icon","🟡")} {result.get("status_cn","中性")}</strong>'
        f' — {status_en} | 风险 {risk_score}/100</div>', unsafe_allow_html=True,
    )

    signals = result.get('signals', [])
    if signals:
        warn = [s for s in signals if '🔴' in s]
        caution = [s for s in signals if '🟠' in s]
        ok = [s for s in signals if '🟢' in s]
        if warn:
            st.error("**预警信号** " + " | ".join(warn))
        if caution:
            st.warning("**关注信号** " + " | ".join(caution))
        if ok:
            with st.expander("正常信号", expanded=False):
                st.success(" | ".join(ok))

    st.divider()
    dimensions = result.get('dimensions', {})
    dim_scores = result.get('dimension_scores', {})
    thresholds = result.get('thresholds', {})
    nb = dimensions.get('northbound', {})
    tv = dimensions.get('turnover', {})
    mg = dimensions.get('margin', {})
    sb = dimensions.get('southbound', {})

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("北向资金", f"{nb.get('latest', 0):+.1f}亿" if 'latest' in nb else "N/A",
               delta=f"近5日 {nb.get('recent_5d_sum', 0):+.1f}亿" if 'recent_5d_sum' in nb else None, delta_color="normal")
    sc2.metric("两市成交额", f"{tv.get('latest', 0):.0f}亿" if 'latest' in tv else "N/A",
               delta=f"20日均 {tv.get('avg_20d', 0):.0f}亿" if 'avg_20d' in tv else None, delta_color="off")
    sc3.metric("融资余额", f"{mg.get('rz_balance', 0):.0f}亿" if 'rz_balance' in mg else "N/A",
               delta=f"周变化 {mg.get('weekly_change_pct', 0):+.1f}%" if 'weekly_change_pct' in mg else None, delta_color="normal")
    sc4.metric("南向资金", f"{sb.get('latest', 0):+.1f}亿" if 'latest' in sb else "N/A",
               delta=f"近5日 {sb.get('recent_5d_sum', 0):+.1f}亿" if 'recent_5d_sum' in sb else None, delta_color="normal")

    st.divider()
    r1c1, r1c2 = st.columns(2)
    with r1c1:
        st.markdown(f"#### 北向资金 (30%) — 风险 {dim_scores.get('northbound', 0):.0f}")
        nb_s = nb.get('series')
        if isinstance(nb_s, pd.DataFrame) and not nb_s.empty:
            _render_capital_flow_chart(nb_s, 'north_net', 'north_cumsum', '北向资金', color='#3498db', key='northbound')
        else:
            st.info(f"北向数据不可用{': ' + nb['error'] if 'error' in nb else ''}")
    with r1c2:
        st.markdown(f"#### 两市成交额 (25%) — 风险 {dim_scores.get('turnover', 0):.0f}")
        tv_s = tv.get('series')
        if isinstance(tv_s, pd.DataFrame) and not tv_s.empty:
            _render_trend_chart(tv_s, 'total_amount', '两市成交额(亿)',
                                threshold=thresholds.get('turnover_cold', 8000),
                                threshold_label=f"冷淡线 {thresholds.get('turnover_cold', 8000)}亿",
                                y_title='亿元', color='#e67e22', key='turnover')
        else:
            st.info(f"成交额数据不可用{': ' + tv['error'] if 'error' in tv else ''}")

    r2c1, r2c2 = st.columns(2)
    with r2c1:
        st.markdown(f"#### 融资融券 (25%) — 风险 {dim_scores.get('margin', 0):.0f}")
        mg_s = mg.get('series')
        if isinstance(mg_s, pd.DataFrame) and not mg_s.empty:
            _render_trend_chart(mg_s, 'rzye_yi', '融资余额(亿)', y_title='亿元', color='#9b59b6', key='margin')
        else:
            st.info(f"融资融券数据不可用{': ' + mg['error'] if 'error' in mg else ''}")
    with r2c2:
        st.markdown(f"#### 南向资金 (20%) — 风险 {dim_scores.get('southbound', 0):.0f}")
        sb_s = sb.get('series')
        if isinstance(sb_s, pd.DataFrame) and not sb_s.empty:
            _render_capital_flow_chart(sb_s, 'south_net', 'south_cumsum', '南向资金', color='#2ecc71', key='southbound')
        else:
            st.info(f"南向数据不可用{': ' + sb['error'] if 'error' in sb else ''}")


def render_ashare_scan(verdict: dict) -> None:
    """A-share scanning tab: box breakout + market signals."""
    _regime_badge(verdict)

    tab_box, tab_signals = st.tabs(["📦 箱体突破", "📡 市场信号"])

    with tab_box:
        _render_box_breakout_section(verdict)

    with tab_signals:
        _render_china_market_signals_section()
