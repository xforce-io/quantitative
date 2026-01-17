
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
    get_latest_trading_day
)
from web.components import plot_trend_chart, plot_comparison_bar, plot_technical_chart, render_stock_detail_card, render_period_selector
from web.utils import load_watchlist, save_watchlist
from web.ui_theme import Colors, apply_custom_css

# 导入 AI 面板组件
from web.components_ai_panel import render_ai_right_panel, init_ai_panel_for_page, get_ai_panel_layout
from web.page_registry import get_page_registry


# ================= 页面逻辑 =================

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
        # 预处理：确保已存的股票在选项列表中，否则 multiselect 会报错或丢失
        # 简单处理：追加 default 到 options 开头 (去重)
        # 优化显示格式：把名称放在前面，如 "比亚迪 (002594.SZ)"
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
        # 检查更变并保存
        if set(select_stocks) != set(watchlist['stocks']):
            watchlist['stocks'] = select_stocks
            save_watchlist(watchlist)
            st.rerun()

    with st.sidebar.expander("🏭 管理关注行业", expanded=False):
        if not all_ind_options:
            all_ind_options = watchlist['industries'] # Fallback
            
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

    # --- 主界面：监控仪表盘 + AI 面板 ---
    
    # 设置时间范围到 registry
    registry = get_page_registry()
    registry.set_date_range(start_str, end_str)
    
    # 左右分栏布局
    main_col, ai_col = get_ai_panel_layout(main_ratio=7, panel_ratio=3)
    
    with main_col:
        st.title("👀 自选监控驾驶舱")
        # Tab 1: 股票监控
        # Tab 2: 行业监控
        tab_stock, tab_ind = st.tabs(["📈 个股监控", "🏭 赛道监控"])
    
        # >>> 股票监控 <<<
        with tab_stock:
            if not watchlist['stocks']:
                st.info("👈 请在侧边栏添加关注的股票")
            else:
                st.markdown(f"### 🛡️ 重点持仓/关注 ({len(watchlist['stocks'])})")
                
                # ========== 1. 全局概览 (Summary) ==========
                with st.expander("📊 资金流向排行 (概览)", expanded=True):
                    stock_results = []
                    with st.spinner("正在扫描自选股资金动向..."):
                        for s_str in watchlist['stocks']:
                            symbol = s_str.split(' ')[0]
                            name = s_str.split(' ')[1] if len(s_str.split(' ')) > 1 else symbol
                            
                            res = get_stock_money_flow(symbol, start_str, end_str)
                            if 'error' not in res:
                                inst_net = res.get('institutional', {}).get('total_net_flow', 0)
                                retail_net = res.get('retail', {}).get('total_net_flow', 0)
                                stock_results.append({
                                    'code': symbol,
                                    'name': name,
                                    'inst_net': inst_net,
                                    'inst_net_亿': inst_net / 1e8,
                                    'retail_net': retail_net,
                                    'retail_net_亿': retail_net / 1e8
                                })
                    
                    if stock_results:
                        df_stock = pd.DataFrame(stock_results)
                        df_sorted = df_stock.sort_values('inst_net', ascending=True)
                        
                        fig, ax = plt.subplots(figsize=(10, max(3, len(df_stock) * 0.5 + 1)))
                        y_pos = range(len(df_sorted))
                        ax.barh(y_pos, df_sorted['inst_net_亿'],
                                color=[Colors.RISE if x > 0 else Colors.FALL for x in df_sorted['inst_net_亿']],
                                alpha=0.8)
                        ax.set_yticks(y_pos)
                        ax.set_yticklabels(df_sorted['name'], fontsize=10)
                        ax.set_xlabel("机构净流入 (亿元)")
                        ax.set_title(f"自选股资金排行 ({start_str}-{end_str})")
                        ax.grid(axis='x', linestyle='--', alpha=0.3)
                        ax.bar_label(ax.containers[0], fmt='%.2f', padding=3)
                        st.pyplot(fig)
                    else:
                        st.warning("暂无数据")
                
                st.divider()
                
                # ========== 2. 逐个标的分析 (标的优先) ==========
                st.markdown("### 📋 逐个标的分析")
                
                for s_str in watchlist['stocks']:
                    symbol = s_str.split(' ')[0]
                    name = s_str.split(' ')[1] if len(s_str.split(' ')) > 1 else symbol
                    
                    # 获取资金流向数据
                    flow_res = get_stock_money_flow(symbol, start_str, end_str)
                    
                    # 计算指示器（用于标题显示）
                    if 'error' not in flow_res:
                        inst_net = flow_res.get('institutional', {}).get('total_net_flow', 0) / 1e8
                        trend_icon = "🔴" if inst_net > 0.5 else ("🟢" if inst_net < -0.5 else "⚪")
                        trend_text = f"{inst_net:+.2f}亿"
                    else:
                        trend_icon = "❓"
                        trend_text = "无数据"
                    
                    # 每个标的一个可展开卡片
                    with st.expander(f"{trend_icon} **{name}** ({symbol}) | 机构: {trend_text}", expanded=False):
                        # 使用统一的个股详情组件
                        render_stock_detail_card(
                            symbol=symbol,
                            name=name,
                            start_str=start_str,
                            end_str=end_str,
                            key_prefix="watch_"
                        )

        # >>> 行业监控 <<<
        with tab_ind:
            if not watchlist['industries']:
                st.info("👈 请在侧边栏添加关注的行业")
            else:
                st.markdown(f"### 🔭 赛道追踪 ({len(watchlist['industries'])})")
                
                with st.spinner("正在聚合行业数据..."):
                    df_all_ind, df_raw_ind = get_industry_flow_with_details(start_str, end_str)
                
                if df_all_ind.empty:
                    st.warning("暂无数据")
                else:
                    target_inds = watchlist['industries']
                    filtered_df = df_all_ind[df_all_ind['name'].isin(target_inds)].copy()
                    
                    # ========== 1. 全局概览 ==========
                    with st.expander("📊 赛道资金排行 (概览)", expanded=True):
                        if not filtered_df.empty:
                            filtered_df['net_amount_亿'] = filtered_df['net_amount'] / 1e8
                            df_sorted = filtered_df.sort_values('net_amount', ascending=True)
                            
                            fig, ax = plt.subplots(figsize=(10, max(3, len(df_sorted) * 0.5 + 1)))
                            y_pos = range(len(df_sorted))
                            ax.barh(y_pos, df_sorted['net_amount_亿'],
                                    color=[Colors.RISE if x > 0 else Colors.FALL for x in df_sorted['net_amount_亿']],
                                    alpha=0.8)
                            ax.set_yticks(y_pos)
                            ax.set_yticklabels(df_sorted['name'], fontsize=10)
                            ax.set_xlabel("净流入 (亿元)")
                            ax.set_title(f"自选赛道资金排行 ({start_str}-{end_str})")
                            ax.grid(axis='x', linestyle='--', alpha=0.3)
                            ax.bar_label(ax.containers[0], fmt='%.2f', padding=3)
                            st.pyplot(fig)
                        else:
                            st.warning("未找到所选行业的数据")
                    
                    st.divider()
                    
                    # ========== 2. 逐个赛道分析 (标的优先) ==========
                    st.markdown("### 📋 逐个赛道分析")
                    
                    for ind_name in target_inds:
                        # 获取该行业数据
                        ind_summary = filtered_df[filtered_df['name'] == ind_name]
                        ind_trend = df_raw_ind[df_raw_ind['name'] == ind_name].sort_values('trade_date') if not df_raw_ind.empty else pd.DataFrame()
                        
                        # 计算指示器
                        if not ind_summary.empty:
                            net_flow = ind_summary['net_amount'].values[0] / 1e8
                            trend_icon = "🔥" if net_flow > 1 else ("🧊" if net_flow < -1 else "➖")
                            trend_text = f"{net_flow:+.2f}亿"
                        else:
                            trend_icon = "❓"
                            trend_text = "无数据"
                        
                        # 每个赛道一个可展开卡片
                        with st.expander(f"{trend_icon} **{ind_name}** | 净流入: {trend_text}", expanded=False):
                            
                            # 子 Tab：不同分析维度
                            dim_tabs = st.tabs(["💸 资金流向", "📊 成分股", "📉 技术形态"])
                            
                            # ---------- 资金流向维度 ----------
                            with dim_tabs[0]:
                                if ind_summary.empty:
                                    st.warning("暂无数据")
                                else:
                                    # Metrics
                                    col1, col2, col3 = st.columns(3)
                                    col1.metric("累计净流入", f"{net_flow:+.2f} 亿")
                                    col2.metric("区间涨幅", f"{ind_summary['pct_change'].values[0]:.2f}%")
                                    col3.metric("数据天数", f"{len(ind_trend)} 天")
                                    
                                    # 趋势图（带价格曲线）
                                    if not ind_trend.empty:
                                        from web.components import plot_interactive_trend
                                        
                                        # 确保有日期索引或列
                                        trend_plot = ind_trend.copy()
                                        if 'trade_date' in trend_plot.columns:
                                            trend_plot['trade_date'] = pd.to_datetime(trend_plot['trade_date'])
                                            trend_plot = trend_plot.sort_values('trade_date')
                                        
                                        # 构建价格指数（使用涨跌幅累积）
                                        if 'pct_change' in trend_plot.columns:
                                            trend_plot['close'] = (1 + trend_plot['pct_change']/100).cumprod() * 100
                                            
                                        fig = plot_interactive_trend(
                                            trend_plot,
                                            date_col='trade_date',
                                            inst_col='institutional_net',
                                            retail_col='retail_net',
                                            total_col='net_amount',
                                            title=f"{ind_name} 资金流向与价格走势"
                                        )
                                        if fig:
                                            st.plotly_chart(fig, use_container_width=True)
                                            
                                            # 计算并显示趋势强度
                                            if len(trend_plot) >= 60 and 'close' in trend_plot.columns:
                                                st.divider()
                                                from web.data_service import get_trend_strength_from_price_data
                                                from web.components import render_trend_strength_card
                                                
                                                with st.spinner("正在计算趋势强度..."):
                                                    trend_data = get_trend_strength_from_price_data(trend_plot, ind_name)
                                                render_trend_strength_card(trend_data, key_prefix=f"watch_ind_trend_{ind_name}_")
                                            elif len(trend_plot) < 60:
                                                st.caption(f"💡 趋势强度计算需至少60个交易日数据（当前: {len(trend_plot)}天）")
                                        else:
                                            st.warning("绘图失败")
                                    else:
                                        st.info("暂无时序数据")
                            
                            # ---------- 成分股维度 ----------
                            with dim_tabs[1]:
                                with st.spinner("加载成分股..."):
                                    constituent_df = get_industry_constituent_stocks(ind_name)
                                
                                if constituent_df is not None and not constituent_df.empty:
                                    st.info(f"**{ind_name}** 共有 **{len(constituent_df)}** 只成分股")
                                    
                                    # 显示成分股列表
                                    display_cols = ['ts_code', 'name']
                                    if 'industry' in constituent_df.columns:
                                        display_cols.append('industry')
                                    
                                    st.dataframe(
                                        constituent_df[[c for c in display_cols if c in constituent_df.columns]],
                                        column_config={
                                            "ts_code": "股票代码",
                                            "name": "股票名称",
                                            "industry": "所属行业"
                                        },
                                        height=300,
                                        use_container_width=True
                                    )
                                else:
                                    st.warning("该板块暂无成分股数据")
                                    st.caption("💡 提示：概念板块的成分股数据可能暂不可用")
                            
                            # ---------- 技术形态维度 ----------
                            with dim_tabs[2]:
                                if not ind_trend.empty and 'pct_change' in ind_trend.columns:
                                    # 构建价格指数和技术指标
                                    tech_df = ind_trend.sort_values('trade_date').copy()
                                    tech_df['trade_date'] = pd.to_datetime(tech_df['trade_date'])
                                    tech_df = tech_df.set_index('trade_date')
                                    
                                    # 构建价格指数（使用涨跌幅累积）
                                    tech_df['close'] = (1 + tech_df['pct_change']/100).cumprod() * 100
                                    
                                    # 计算技术指标
                                    tech_df['MA5'] = tech_df['close'].rolling(window=5).mean()
                                    tech_df['MA10'] = tech_df['close'].rolling(window=10).mean()
                                    tech_df['MA20'] = tech_df['close'].rolling(window=20).mean()
                                    
                                    # 计算 MACD
                                    exp12 = tech_df['close'].ewm(span=12, adjust=False).mean()
                                    exp26 = tech_df['close'].ewm(span=26, adjust=False).mean()
                                    tech_df['MACD_DIF'] = exp12 - exp26
                                    tech_df['MACD_DEA'] = tech_df['MACD_DIF'].ewm(span=9, adjust=False).mean()
                                    tech_df['MACD_HIST'] = (tech_df['MACD_DIF'] - tech_df['MACD_DEA']) * 2
                                    
                                    # 绘制技术分析图
                                    from web.components import plot_technical_chart
                                    
                                    # 添加必要列用于技术图表
                                    if 'open' not in tech_df.columns:
                                        tech_df['open'] = tech_df['close'].shift(1).fillna(tech_df['close'])
                                    if 'high' not in tech_df.columns:
                                        tech_df['high'] = tech_df['close'] * 1.01
                                    if 'low' not in tech_df.columns:
                                        tech_df['low'] = tech_df['close'] * 0.99
                                    if 'volume' not in tech_df.columns and 'net_amount' in tech_df.columns:
                                        tech_df['volume'] = abs(tech_df['net_amount'])
                                    
                                    fig, analysis = plot_technical_chart(
                                        tech_df,
                                        symbol=ind_name,
                                        show_volume=True,
                                        show_macd=True,
                                        show_rsi=False
                                    )
                                    
                                    if fig:
                                        st.pyplot(fig)
                                        plt.close(fig)
                                    
                                    # 显示技术信号
                                    st.divider()
                                    st.markdown("#### 📊 技术信号")
                                    
                                    sig_cols = st.columns(4)
                                    
                                    # 最新收盘（指数值）
                                    if 'latest_close' in analysis:
                                        sig_cols[0].metric("指数", f"{analysis['latest_close']:.2f}")
                                    
                                    # 均线趋势
                                    if 'ma_trend' in analysis:
                                        trend = analysis['ma_trend']
                                        color = "🟢" if "多头" in trend else "🔴"
                                        sig_cols[1].metric("均线趋势", f"{color} {trend}")
                                    
                                    # MACD
                                    if 'macd_signal' in analysis:
                                        signal = analysis['macd_signal']
                                        color = "🟢" if "金叉" in signal else "🔴"
                                        sig_cols[2].metric("MACD", f"{color} {signal}")
                                    
                                    # 区间涨跌
                                    price_change = (tech_df['close'].iloc[-1] - tech_df['close'].iloc[0]) / tech_df['close'].iloc[0] * 100
                                    color = "🔴" if price_change > 0 else "🟢"
                                    sig_cols[3].metric("区间涨跌", f"{color} {price_change:+.2f}%")
                                    
                                    # 智能解读
                                    if 'interpretations' in analysis and analysis['interpretations']:
                                        st.markdown("#### 🤖 技术解读")
                                        for interp in analysis['interpretations'][:3]:
                                            st.markdown(f"- {interp}")
                                else:
                                    st.warning("暂无技术数据")
    
    # 渲染右侧 AI 面板
    with ai_col:
        render_ai_right_panel(session_id="watchlist_ai")


if __name__ == "__main__":
    main()
