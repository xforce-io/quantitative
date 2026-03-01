
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

# 导入统一的数据服务
from web.data_service import (
    get_stock_list,
    get_stock_money_flow,
    get_stock_price,
    get_industry_flow_daily,
    get_industry_flow_aggregated,
    get_industry_list,
    get_industry_flow_with_details,
    get_industry_constituent_stocks,
    get_market_summary,
    get_latest_trading_day
)
from web.components import render_period_selector
from web.ui_theme import Colors, apply_custom_css

# 导入 AI 面板组件
from web.components_ai_panel import render_ai_right_panel, init_ai_panel_for_page, get_ai_panel_layout
from web.page_registry import get_page_registry



def main():
    # 应用自定义样式
    apply_custom_css()
    
    # 初始化 AI 面板所需组件
    init_ai_panel_for_page("Money Flow", "pages/1_💸_Money_Flow.py")
    
    # 设置时间范围到 registry
    registry = get_page_registry()

    # 侧边栏配置
    st.sidebar.header("配置面板")
    analysis_mode = st.sidebar.selectbox(
        "选择分析模式",
        ["🌍 市场概览 (Market)", "🏭 行业分析 (Industry)", "📈 个股追踪 (Stock)"]
    )

    # 使用统一的时间选择组件
    start_date_str, end_date_str = render_period_selector(key_prefix="money_flow")
    is_range = start_date_str != end_date_str
    date_str = start_date_str  # 用于单日模式
    
    # 更新 registry 的时间范围
    registry.set_date_range(start_date_str, end_date_str)
    
    # 左右分栏布局 (主内容 + AI 面板)
    main_col, ai_col = get_ai_panel_layout(main_ratio=7, panel_ratio=3)

    with main_col:
        st.title("💸 A股市场资金流向分析")
        # ==================== 1. 市场概览模式 ====================
        if "Market" in analysis_mode:
            # 市场概览模式只支持单日快照
            if is_range:
                st.info("💡 市场概览模式展示单日快照，已自动选择区间最后一个交易日")

            # 尝试获取数据，如果失败则回溯查找最近交易日
            display_date = end_date_str  # 优先用结束日期
            summary = None

            with st.spinner("正在分析市场资金数据 (A股)..."):
                # 尝试当前日期
                summary = get_market_summary(display_date)

                # 如果失败，尝试回溯最近5个工作日
                if 'error' in summary:
                    from web.data_service import get_trading_days
                    from datetime import datetime, timedelta

                    end_dt = datetime.strptime(end_date_str, '%Y%m%d')
                    start_dt = end_dt - timedelta(days=10)
                    trading_days = get_trading_days(start_dt.strftime('%Y%m%d'), end_date_str)

                    if trading_days:
                        # 从最近的交易日开始尝试
                        for td in reversed(trading_days):
                            summary = get_market_summary(td)
                            if 'error' not in summary:
                                display_date = td
                                break

            st.header(f"🌍 A股全市场资金流向概览 ({display_date})")

            if summary is None or 'error' in summary:
                error_msg = summary.get('error', '未知错误') if summary else '无法获取数据'
                st.warning(f"📅 **暂无数据**: {error_msg}")
                st.info("💡 可能原因：\\n- 当前选择的日期是非交易日（周末/节假日）\\n- 数据尚未更新（盘中或盘后延迟）\\n- 请尝试选择其他日期")
                return
            
            # 🆕 注册市场汇总数据到 registry，供 AI 分析师使用
            registry.register_market_summary(summary, display_date)

            # 展示关键指标 (使用更稳健的排列方式)
            st.markdown("### 📊 核心指标概览")
            
            inst_net = summary.get('institutional_analysis', {}).get('total_net_flow', 0) / 100000000
            retail_net = summary.get('retail_analysis', {}).get('total_net_flow', 0) / 100000000
            north_net = summary.get('north_money', {}).get('north_money_in', 0) / 100000000
            sentiment = summary.get('market_sentiment', {})
            
            # 使用列表或更少列的布局
            m_col1, m_col2, m_col3 = st.columns(3)
            with m_col1:
                st.metric("机构净流入", f"{inst_net:+.2f} 亿")
            with m_col2:
                st.metric("散户净流入", f"{retail_net:+.2f} 亿")
            with m_col3:
                st.metric("北向资金", f"{north_net:+.2f} 亿")
            
            st.success(f"🎭 **市场情绪: {sentiment.get('sentiment', 'N/A')}** | {sentiment.get('reason', 'N/A')}")
            
            # 绘图区域容器化
            with st.container():
                try:
                    import plotly.express as px
                    from plotly.subplots import make_subplots
                    import plotly.graph_objects as go

                    # 行业流入排行 (替代原有的两张组合图，改为更现代的 Plotly)
                    ranking = summary.get('industry_ranking', {})
                    top_in = ranking.get('top_10_inflow', [])[:10]
                    if top_in:
                        df_top = pd.DataFrame(top_in)
                        df_top['net_in_100m'] = df_top['net_amount'] / 1e8
                        fig = px.bar(
                            df_top.sort_values('net_in_100m'), 
                            x='net_in_100m', y='name', orientation='h',
                            title=f"今日领涨主力 (板块净流入 Top 10)",
                            color='net_in_100m',
                            color_continuous_scale='Reds',
                            labels={'net_in_100m': '亿元', 'name': '板块'}
                        )
                        fig.update_layout(height=400, margin=dict(l=0, r=10, t=30, b=10))
                        st.plotly_chart(fig, use_container_width=True, key="market_top_industry")
                except Exception as e:
                    st.error(f"可视化加载失败: {e}")

        # ==================== 2. 行业分析模式 ====================
        elif "Industry" in analysis_mode:
            date_display = f"{start_date_str} - {end_date_str}" if is_range else start_date_str
            st.header(f"🏭 A股行业板块资金流向 ({date_display})")
            
            industry_list = get_industry_list()
            selected_industry = st.selectbox("选择行业/概念板块", options=["全部行业"] + industry_list, index=0)
            
            with st.spinner("正在获取和聚合行业数据..."):
                if is_range:
                    df = get_industry_flow_aggregated(start_date_str, end_date_str)
                    metric_label = "累计净流入"
                else:
                    df = get_industry_flow_daily(start_date_str)
                    metric_label = "净流入"

            # 若当前日期无数据（如非交易日），回溯查找最近10天内有数据的交易日
            if df.empty:
                from web.data_service import get_trading_days
                end_dt = datetime.strptime(end_date_str, '%Y%m%d')
                start_dt = end_dt - timedelta(days=14)
                recent_days = get_trading_days(start_dt.strftime('%Y%m%d'), end_date_str)
                for td in reversed(recent_days):
                    df = get_industry_flow_daily(td)
                    if not df.empty:
                        start_date_str = end_date_str = td
                        is_range = False
                        metric_label = "净流入"
                        date_display = td
                        st.header(f"🏭 A股行业板块资金流向 ({date_display})")
                        break

            if df.empty:
                st.warning("未找到近期行业数据，请尝试其他日期。")
                st.info("💡 可能原因：\n- 当前选择的日期是非交易日（周末/节假日）\n- 数据尚未更新（盘中或盘后延迟）")
                tab1, tab2, tab3 = st.tabs(["🔥 净流入 Top 30", "🥶 资金流出 Top 30", "📋 完整数据"])
                with tab3:
                    st.dataframe(pd.DataFrame(), use_container_width=True)
                return
            
            registry.register_industry_data(df, is_aggregated=is_range)
            
            if selected_industry != "全部行业":
                with st.container():
                    st.markdown(f"### 📊 {selected_industry} - 详细分析")
                    detail_tab1, detail_tab2, detail_tab3 = st.tabs(["📈 资金趋势", "🏢 成分股", "📋 详细数据"])
                    
                    with detail_tab1:
                        with st.spinner("正在加载趋势数据..."):
                            if is_range:
                                _, trend_df = get_industry_flow_with_details(start_date_str, end_date_str)
                            else:
                                end_dt = datetime.strptime(start_date_str, '%Y%m%d')
                                trend_start = (end_dt - timedelta(days=30)).strftime('%Y%m%d')
                                _, trend_df = get_industry_flow_with_details(trend_start, start_date_str)
                            
                            industry_trend = trend_df[trend_df['name'] == selected_industry].copy()
                        
                        if not industry_trend.empty:
                            industry_trend = industry_trend.sort_values('trade_date')
                            industry_trend['trade_date'] = pd.to_datetime(industry_trend['trade_date'])
                            
                            if 'pct_change' in industry_trend.columns:
                                industry_trend['close'] = (1 + industry_trend['pct_change']/100).cumprod() * 100
                            
                            from web.components import plot_interactive_trend
                            fig = plot_interactive_trend(industry_trend.set_index('trade_date'), date_col=None, inst_col='institutional_net', retail_col='retail_net', title=f"{selected_industry} 资金流向趋势")
                            if fig:
                                st.plotly_chart(fig, use_container_width=True, key=f"ind_flow_{selected_industry}")
                                
                                # 统计指标
                                t_inst = industry_trend['institutional_net'].sum() / 1e8
                                t_pct = industry_trend['pct_change'].sum()
                                st.info(f"💰 **资金特征**: 机构累计净流入 **{t_inst:+.2f}** 亿 | 区间累计涨幅 **{t_pct:+.2f}%**")
                                
                                if len(industry_trend) >= 60:
                                    st.divider()
                                    from web.data_service import get_trend_strength_from_price_data
                                    from web.components import render_trend_strength_card
                                    trend_data = get_trend_strength_from_price_data(industry_trend, selected_industry)
                                    render_trend_strength_card(trend_data, key_prefix=f"ind_trend_{selected_industry}_")
                        else:
                            st.info("暂无趋势数据")
                    
                    with detail_tab2:
                        constituent_stocks = get_industry_constituent_stocks(selected_industry)
                        if constituent_stocks is not None and not constituent_stocks.empty:
                            st.dataframe(constituent_stocks, height=400, use_container_width=True)
                    
                    with detail_tab3:
                        industry_data = df[df['name'] == selected_industry]
                        if not industry_data.empty: st.dataframe(industry_data, use_container_width=True)

                st.divider()
                
            # 全行业看板
            if 'net_amount' in df.columns:
                df['net_amount_100m'] = df['net_amount'] / 1e8
                tab1, tab2, tab3 = st.tabs([f"🔥 {metric_label} Top 30", f"🥶 资金流出 Top 30", "📋 完整数据"])
                
                with tab1:
                    top_in = df[df['net_amount'] > 0].nlargest(30, 'net_amount')
                    if not top_in.empty:
                        import plotly.express as px
                        fig = px.bar(top_in.sort_values('net_amount'), x='net_amount_100m', y='name', orientation='h', color='net_amount_100m', color_continuous_scale='Reds')
                        fig.update_layout(height=700, margin=dict(l=0, r=10, t=10, b=10))
                        st.plotly_chart(fig, use_container_width=True, key="ind_top_in")
                
                with tab2:
                    top_out = df.nsmallest(30, 'net_amount')
                    if not top_out.empty:
                        fig = px.bar(top_out.sort_values('net_amount', ascending=False), x='net_amount_100m', y='name', orientation='h', color='net_amount_100m', color_continuous_scale='Blues_r')
                        fig.update_layout(height=700, margin=dict(l=0, r=10, t=10, b=10))
                        st.plotly_chart(fig, use_container_width=True, key="ind_top_out")
                
                with tab3:
                    st.dataframe(df.sort_values('net_amount', ascending=False), height=500, use_container_width=True)

        # ==================== 3. 个股追踪模式 ====================
        elif "Stock" in analysis_mode:
            st.header(f"📈 A股个股资金趋势追踪")
            all_stocks = get_stock_list()
            
            selected_stock_str = st.selectbox("选择或搜索股票", options=all_stocks if all_stocks else ["正在加载..."], index=0)
            symbol = selected_stock_str.split(' ')[0] if selected_stock_str else ""
            
            if st.button("开始分析", type="primary") and symbol:
                with st.container():
                    with st.spinner(f"正在分析 {symbol}..."):
                        result = get_stock_money_flow(symbol, start_date_str, end_date_str)
                    
                    if 'error' not in result:
                        trend = result.get('trend', 'neutral')
                        interpretation = result.get('interpretation', '暂无解读')
                        st.info(f"🤖 **智能解读**: {interpretation}")
                        
                        inst = result.get('institutional', {})
                        st.write(f"📊 **数据统计**: 机构累计流入 `{inst.get('total_net_flow',0)/1e4:+.2f} 亿` | 交易日 `{result.get('total_days', 0)}` 天")
                        
                        if 'flow_data' in result:
                            from web.components import plot_interactive_trend
                            flow_df = result['flow_data'].copy()
                            price_df = get_stock_price(symbol, start_date_str, end_date_str)
                            if not price_df.empty:
                                flow_df['close'] = price_df['close']
                            
                            fig = plot_interactive_trend(flow_df, date_col=None, inst_col='institutional_net', retail_col='retail_net', title=f"{symbol} 资金趋势")
                            if fig: st.plotly_chart(fig, use_container_width=True, key=f"stock_flow_{symbol}")
                            
                            with st.expander("查看原始数据"):
                                st.dataframe(flow_df.sort_index(ascending=False), use_container_width=True)
    
    # 渲染右侧 AI 面板
    with ai_col:
        render_ai_right_panel(session_id="money_flow_ai")

if __name__ == "__main__":
    main()
