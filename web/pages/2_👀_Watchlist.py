
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

# 导入统一的数据服务和组件
from web.data_service import (
    get_stock_list,
    get_stock_money_flow,
    get_stock_technical_data,
    get_industry_list,
    get_industry_flow_with_details,
    get_industry_constituent_stocks,
    get_latest_trading_day,
    get_trend_strength,
    get_trend_strength_from_price_data
)
from web.components import plot_trend_chart, plot_comparison_bar, plot_technical_chart, render_stock_detail_card, render_period_selector, render_trend_strength_card
from web.utils import load_watchlist, save_watchlist
from web.ui_theme import Colors, apply_custom_css
from quant.core.indicators import TechnicalIndicators

# 导入 AI 面板组件
from web.components_ai_panel import render_ai_right_panel, init_ai_panel_for_page, get_ai_panel_layout
from web.page_registry import get_page_registry


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


@st.cache_data(ttl=3600)  # 1小时缓存
def calculate_industry_tech_signals(ind_name: str, ind_trend: pd.DataFrame):
    """提取行业技术指标计算逻辑并缓存，避免重复计算"""
    if ind_trend.empty or 'pct_change' not in ind_trend.columns:
        return None, None
    
    tech_df = ind_trend.sort_values('trade_date').copy()
    tech_df['trade_date'] = pd.to_datetime(tech_df['trade_date'])
    tech_df = tech_df.set_index('trade_date')

    # 构建价格指数（使用涨跌幅累积）
    tech_df['close'] = (1 + tech_df['pct_change']/100).cumprod() * 100

    # 使用统一的技术指标计算
    tech_df = TechnicalIndicators.calculate_all_indicators(tech_df)

    # 列名别名：保持中国市场惯例
    if 'MACD' in tech_df.columns:
        tech_df['MACD_DIF'] = tech_df['MACD']
    if 'MACD_Signal' in tech_df.columns:
        tech_df['MACD_DEA'] = tech_df['MACD_Signal']
    if 'MACD_DIF' in tech_df.columns and 'MACD_DEA' in tech_df.columns:
        tech_df['MACD_HIST'] = (tech_df['MACD_DIF'] - tech_df['MACD_DEA']) * 2

    # 补充必要列用于绘图
    tech_df['open'] = tech_df['close'].shift(1).fillna(tech_df['close'])
    tech_df['high'] = tech_df['close'] * 1.01
    tech_df['low'] = tech_df['close'] * 0.99
    if 'net_amount' in tech_df.columns:
        tech_df['volume'] = abs(tech_df['net_amount'])
    
    # 统一绘图逻辑
    from web.components import plot_technical_chart
    fig, analysis = plot_technical_chart(
        tech_df,
        symbol=ind_name,
        show_volume=True,
        show_macd=True,
        show_rsi=False
    )
    return fig, analysis, tech_df

def main():
    # 应用自定义样式
    apply_custom_css()
    
    # 初始化 AI 面板所需组件
    init_ai_panel_for_page("Watchlist", "pages/2_👀_Watchlist.py")

    # --- 侧边栏：配置与管理 ---
    st.sidebar.header("🕹️ 指挥面板")
    
    # 加载配置
    watchlist = load_watchlist()

    # 1. 使用统一的时间选择组件
    start_str, end_str = render_period_selector(key_prefix="watchlist")

    # 2. 标的管理 (CURD)
    st.sidebar.divider()
    st.sidebar.subheader("❤️ 自选管理")
    
    all_stock_options = get_stock_list()
    all_ind_options = get_industry_list()
    
    with st.sidebar.expander("📈 管理关注股票", expanded=False):
        def format_option(option_str):
            parts = option_str.split(' ')
            if len(parts) > 1:
                return f"{parts[1]} ({parts[0]})"
            return option_str

        select_stocks = st.multiselect(
            "添加/删除股票",
            options=all_stock_options,
            default=[s for s in watchlist['stocks'] if s in all_stock_options],
            format_func=format_option,
            help="输入代码或名称搜索，点击x删除"
        )
        if set(select_stocks) != set(watchlist['stocks']):
            watchlist['stocks'] = select_stocks
            save_watchlist(watchlist)
            st.rerun()

    with st.sidebar.expander("🏭 管理关注行业", expanded=False):
        if not all_ind_options:
            all_ind_options = watchlist['industries']
            
        select_inds = st.multiselect(
            "添加/删除行业",
            options=all_ind_options,
            default=[i for i in watchlist['industries'] if i in all_ind_options],
            help="选择您关注的赛道"
        )
        if set(select_inds) != set(watchlist['industries']):
            watchlist['industries'] = select_inds
            save_watchlist(watchlist)
            st.rerun()

    # --- 主界面 ---
    registry = get_page_registry()
    registry.set_date_range(start_str, end_str)

    main_col, ai_col = get_ai_panel_layout(main_ratio=7, panel_ratio=3)

    # 先渲染 AI 面板（在耗时的 tab 内容计算前），确保面板及时出现
    with ai_col:
        render_ai_right_panel(session_id="watchlist_ai")

    with main_col:
        st.title("👀 自选监控驾驶舱")
        tab_stock, tab_ind = st.tabs(["📈 个股监控", "🏭 赛道监控"])
    
        # >>> 股票监控 <<<
        with tab_stock:
            if not watchlist['stocks']:
                st.info("👈 请在侧边栏添加关注的股票")
            else:
                with st.container():
                    st.markdown(f"### 🛡️ 重点持仓/关注 ({len(watchlist['stocks'])})")
                    
                    with st.expander("📊 资金流向排行 (概览)", expanded=True):
                        stock_results = []
                        with st.spinner("正在扫描自选股资金动向..."):
                            for s_str in watchlist['stocks']:
                                symbol = s_str.split(' ')[0]
                                name = s_str.split(' ')[1] if len(s_str.split(' ')) > 1 else symbol
                                res = get_stock_money_flow(symbol, start_str, end_str)
                                if 'error' not in res:
                                    inst_net = res.get('institutional', {}).get('total_net_flow', 0)
                                    stock_results.append({
                                        'name': name,
                                        'inst_net': inst_net,
                                        'inst_net_亿': inst_net / 1e8
                                    })
                        
                        if stock_results:
                            df_stock = pd.DataFrame(stock_results)
                            df_sorted = df_stock.sort_values('inst_net', ascending=True)
                            
                            import plotly.express as px
                            fig = px.bar(
                                df_sorted, x='inst_net_亿', y='name', orientation='h',
                                color='inst_net_亿',
                                color_continuous_scale='RdYlGn_r',
                                labels={'inst_net_亿': '机构净流入 (亿元)', 'name': '名称'}
                            )
                            fig.update_layout(height=max(300, len(df_stock)*30), margin=dict(l=0, r=10, t=10, b=10))
                            st.plotly_chart(fig, use_container_width=True, key="watchlist_stock_summary")
                        else:
                            st.warning("暂无数据")
                    
                    st.divider()
                    st.markdown("### 📋 逐个标的分析")
                    for s_str in watchlist['stocks']:
                        symbol = s_str.split(' ')[0]
                        name = s_str.split(' ')[1] if len(s_str.split(' ')) > 1 else symbol
                        flow_res = get_stock_money_flow(symbol, start_str, end_str)
                        if 'error' not in flow_res:
                            inst_net = flow_res.get('institutional', {}).get('total_net_flow', 0) / 1e8
                            trend_icon = "🔴" if inst_net > 0.5 else ("🟢" if inst_net < -0.5 else "⚪")
                            trend_text = f"{inst_net:+.2f}亿"
                        else:
                            trend_icon = "❓"; trend_text = "无数据"
                        
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
                            render_stock_detail_card(symbol=symbol, name=name, start_str=start_str, end_str=end_str, key_prefix="watch_")

        # >>> 行业监控 <<<
        with tab_ind:
            if not watchlist['industries']:
                st.info("👈 请在侧边栏添加关注的行业")
            else:
                with st.container():
                    st.markdown(f"### 🔭 赛道追踪 ({len(watchlist['industries'])})")
                    with st.spinner("正在聚合行业数据..."):
                        df_all_ind, df_raw_ind = get_industry_flow_with_details(start_str, end_str)
                    
                    if df_all_ind.empty:
                        st.warning("暂无数据")
                    else:
                        target_inds = watchlist['industries']
                        filtered_df = df_all_ind[df_all_ind['name'].isin(target_inds)].copy()
                        
                        with st.expander("📊 赛道资金排行 (概览)", expanded=True):
                            if not filtered_df.empty:
                                df_sorted = filtered_df.sort_values('net_amount', ascending=True)
                                df_sorted['net_amount_亿'] = df_sorted['net_amount'] / 1e8
                                fig = px.bar(
                                    df_sorted, x='net_amount_亿', y='name', orientation='h',
                                    color='net_amount_亿',
                                    color_continuous_scale='RdYlGn_r',
                                    labels={'net_amount_亿': '净流入 (亿元)', 'name': '名称'}
                                )
                                fig.update_layout(height=max(300, len(df_sorted)*30), margin=dict(l=0, r=10, t=10, b=10))
                                st.plotly_chart(fig, use_container_width=True, key="watchlist_ind_summary")
                            else:
                                st.warning("未找到所选行业的数据")
                        
                        st.divider()
                        st.markdown("### 📋 逐个赛道分析")
                        for ind_name in target_inds:
                            ind_summary = filtered_df[filtered_df['name'] == ind_name]
                            ind_trend = df_raw_ind[df_raw_ind['name'] == ind_name] if not df_raw_ind.empty else pd.DataFrame()
                            
                            if not ind_summary.empty:
                                net_flow = ind_summary['net_amount'].values[0] / 1e8
                                trend_icon = "🔥" if net_flow > 1 else ("🧊" if net_flow < -1 else "➖")
                                trend_text = f"{net_flow:+.2f}亿"
                            else:
                                trend_icon = "❓"; trend_text = "无数据"
                            
                            with st.expander(f"{trend_icon} **{ind_name}** | 净流入: {trend_text}", expanded=False):
                                dim_tabs = st.tabs(["💸 资金流向", "📊 成分股", "📉 技术形态"])
                                
                                with dim_tabs[0]:
                                    if ind_summary.empty:
                                        st.warning("暂无数据")
                                    else:
                                        # 简化统计显示，避免 columns 过多引起崩溃
                                        st.markdown(f"**累计净流入**: `{net_flow:+.2f} 亿` | **历史涨幅**: `{ind_summary['pct_change'].values[0]:.2f}%` | **数据天数**: `{len(ind_trend)} 天`")
                                        if not ind_trend.empty:
                                            from web.components import plot_interactive_trend
                                            trend_plot = ind_trend.copy().sort_values('trade_date')
                                            if 'pct_change' in trend_plot.columns:
                                                trend_plot['close'] = (1 + trend_plot['pct_change']/100).cumprod() * 100
                                            fig = plot_interactive_trend(trend_plot, date_col='trade_date', inst_col='institutional_net', retail_col='retail_net', total_col='net_amount', title=f"{ind_name} 资金流向与价格走势")
                                            st.plotly_chart(fig, use_container_width=True, key=f"watch_flow_{ind_name}")
                                            
                                            # 独立获取90天数据计算趋势强度，不依赖用户选择的时间范围
                                            st.divider()
                                            with st.spinner("正在计算趋势强度..."):
                                                # 使用行业价格指数计算趋势强度
                                                # 获取更长时间的数据以确保有足够的交易日
                                                from datetime import datetime, timedelta
                                                trend_end = datetime.now().strftime('%Y%m%d')
                                                trend_start = (datetime.now() - timedelta(days=120)).strftime('%Y%m%d')
                                                _, full_trend_df = get_industry_flow_with_details(trend_start, trend_end)
                                                
                                                if not full_trend_df.empty:
                                                    ind_full_trend = full_trend_df[full_trend_df['name'] == ind_name].copy()
                                                    if not ind_full_trend.empty:
                                                        ind_full_trend = ind_full_trend.sort_values('trade_date')
                                                        if 'pct_change' in ind_full_trend.columns:
                                                            ind_full_trend['close'] = (1 + ind_full_trend['pct_change']/100).cumprod() * 100
                                                        trend_data = get_trend_strength_from_price_data(ind_full_trend, ind_name)
                                                        render_trend_strength_card(trend_data, key_prefix=f"watch_ind_trend_{ind_name}_")
                                                    else:
                                                        st.warning("⚠️ 无法获取足够的行业数据计算趋势强度")
                                                else:
                                                    st.warning("⚠️ 无法获取足够的行业数据计算趋势强度")
                                
                                with dim_tabs[1]:
                                    constituent_df = get_industry_constituent_stocks(ind_name)
                                    if constituent_df is not None and not constituent_df.empty:
                                        st.dataframe(constituent_df[['ts_code', 'name', 'industry']] if 'industry' in constituent_df.columns else constituent_df[['ts_code', 'name']], height=300, use_container_width=True)
                                    else:
                                        st.warning("暂无成分股数据")
                                
                                with dim_tabs[2]:
                                    fig, analysis, tech_df = calculate_industry_tech_signals(ind_name, ind_trend)
                                    if fig:
                                        st.pyplot(fig)
                                        plt.close(fig)
                                        st.divider()
                                        st.markdown("#### 📊 技术信号")
                                        # 使用 Markdown 代替 columns 布局更稳
                                        if analysis:
                                            st.write(f"**指数水平**: `{analysis.get('latest_close', 0):.2f}` | **均线趋势**: `{analysis.get('ma_trend', '-')}` | **MACD**: `{analysis.get('macd_signal', '-')}`")
                                            if 'interpretations' in analysis:
                                                for interp in analysis['interpretations'][:2]:
                                                    st.markdown(f"- {interp}")
                                    else:
                                        st.warning("数据不足，无法生成技术图表")
    
if __name__ == "__main__":
    main()
