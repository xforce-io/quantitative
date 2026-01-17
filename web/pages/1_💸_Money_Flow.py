
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

            # 展示关键指标
            col1, col2, col3, col4 = st.columns(4)
            
            inst_net = summary.get('institutional_analysis', {}).get('total_net_flow', 0) / 100000000
            retail_net = summary.get('retail_analysis', {}).get('total_net_flow', 0) / 100000000
            north_net = summary.get('north_money', {}).get('north_money_in', 0) / 100000000
            
            sentiment = summary.get('market_sentiment', {})
            
            with col1:
                st.metric("机构净流入", f"{inst_net:+.2f} 亿", delta_color="normal")
            with col2:
                st.metric("散户净流入", f"{retail_net:+.2f} 亿", delta_color="inverse")
            with col3:
                st.metric("北向资金", f"{north_net:+.2f} 亿")
            with col4:
                st.metric("市场情绪", sentiment.get('sentiment', 'N/A'))
                
            st.info(f"💡 **情绪解读**: {sentiment.get('reason', 'N/A')}")
            
            # 绘图
            try:
                fig = plt.figure(figsize=(12, 6))
                gs = fig.add_gridspec(1, 2)
                
               # Pie Chart
                ax1 = fig.add_subplot(gs[0, 0])
                values = [abs(inst_net), abs(retail_net)]
                labels = ['机构', '散户']
                colors = [Colors.INSTITUTIONAL if inst_net > 0 else Colors.NEUTRAL, Colors.RETAIL if retail_net > 0 else Colors.NEUTRAL]
                ax1.pie(values, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
                ax1.set_title(f'机构 vs 散户 资金力度 ({display_date})')
                
                # Bar Chart
                ax2 = fig.add_subplot(gs[0, 1])
                ranking = summary.get('industry_ranking', {})
                top_in = ranking.get('top_10_inflow', [])[:5]
                
                names = [item['name'] for item in top_in[::-1]]
                vals = [item['net_amount']/100000000 for item in top_in[::-1]]
                
                ax2.barh(names, vals, color=Colors.RISE, alpha=0.7)
                ax2.set_title('今日领涨主力 (净流入 Top 5)')
                ax2.set_xlabel('亿元')
                
                st.pyplot(fig)
            except Exception as e:
                st.error(f"绘图失败: {e}")

        # ==================== 2. 行业分析模式 ====================
        elif "Industry" in analysis_mode:
            date_display = f"{start_date_str} - {end_date_str}" if is_range else start_date_str
            st.header(f"🏭 A股行业板块资金流向 ({date_display})")
            
            # 行业选择器
            industry_list = get_industry_list()
            selected_industry = st.selectbox(
                "选择行业/概念板块",
                options=["全部行业"] + industry_list,
                index=0
            )
            
            with st.spinner("正在获取和聚合行业数据..."):
                if is_range:
                    df = get_industry_flow_aggregated(start_date_str, end_date_str)
                    metric_label = "累计净流入"
                else:
                    df = get_industry_flow_daily(start_date_str)
                    metric_label = "净流入"
                
            if df.empty:
                st.warning("未找到该区间的行业数据，可能是非交易日。")
                return
            
            # 🆕 注册行业数据到 registry，供 AI 分析师使用
            registry.register_industry_data(df, is_aggregated=is_range)
            
            # 如果选择了特定行业，展示详细信息
            if selected_industry != "全部行业":
                st.markdown(f"### 📊 {selected_industry} - 详细分析")
                
                # 创建三个 tab：资金趋势、成分股、完整数据
                detail_tab1, detail_tab2, detail_tab3 = st.tabs(["📈 资金趋势", "🏢 成分股", "📋 详细数据"])
                
                with detail_tab1:
                    # 获取行业趋势数据（带价格）
                    with st.spinner("正在加载趋势数据..."):
                        if is_range:
                            # 获取区间内所有交易日数据
                            _, trend_df = get_industry_flow_with_details(start_date_str, end_date_str)
                            industry_trend = trend_df[trend_df['name'] == selected_industry].copy()
                        else:
                            # 单日数据，获取最近20个交易日趋势
                            end_dt = datetime.strptime(start_date_str, '%Y%m%d')
                            trend_start = (end_dt - timedelta(days=30)).strftime('%Y%m%d')
                            _, trend_df = get_industry_flow_with_details(trend_start, start_date_str)
                            industry_trend = trend_df[trend_df['name'] == selected_industry].copy()
                    
                    if not industry_trend.empty:
                        # 获取该行业的平均股价走势（使用成分股加权平均）
                        industry_trend = industry_trend.sort_values('trade_date')
                        industry_trend['trade_date'] = pd.to_datetime(industry_trend['trade_date'])
                        
                        # 绘制资金趋势图（包含价格曲线）
                        from web.components import plot_interactive_trend
                        
                        # 为行业添加代表性价格曲线（使用涨跌幅累积）
                        if 'pct_change' in industry_trend.columns:
                            industry_trend['price_index'] = (1 + industry_trend['pct_change']/100).cumprod() * 100
                            industry_trend = industry_trend.rename(columns={'price_index': 'close'})
                        
                        fig = plot_interactive_trend(
                            industry_trend.set_index('trade_date'),
                            date_col=None,
                            inst_col='institutional_net',
                            retail_col='retail_net',
                            title=f"{selected_industry} 资金流向趋势"
                        )
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # 统计信息
                            total_net = industry_trend['net_amount'].sum() / 1e8
                            inst_net = industry_trend['institutional_net'].sum() / 1e8 if 'institutional_net' in industry_trend.columns else 0
                            retail_net = industry_trend['retail_net'].sum() / 1e8 if 'retail_net' in industry_trend.columns else 0
                            avg_pct = industry_trend['pct_change'].mean()
                            
                            col1, col2, col3, col4 = st.columns(4)
                            col1.metric("累计净流入", f"{total_net:+.2f} 亿")
                            col2.metric("机构净流入", f"{inst_net:+.2f} 亿")
                            col3.metric("散户净流入", f"{retail_net:+.2f} 亿")
                            col4.metric("平均涨跌幅", f"{avg_pct:+.2f}%")
                            
                            # 计算并显示趋势强度
                            if len(industry_trend) >= 60 and 'close' in industry_trend.columns:
                                st.divider()
                                from web.data_service import get_trend_strength_from_price_data
                                from web.components import render_trend_strength_card
                                
                                with st.spinner("正在计算趋势强度..."):
                                    trend_data = get_trend_strength_from_price_data(industry_trend, selected_industry)
                                render_trend_strength_card(trend_data, key_prefix=f"ind_trend_{selected_industry}_")
                            elif len(industry_trend) < 60:
                                st.info(f"💡 趋势强度计算需要至少60个交易日数据（当前: {len(industry_trend)}天）")
                    else:
                        st.info("暂无该行业的趋势数据")
                
                with detail_tab2:
                    st.markdown(f"#### 🏢 {selected_industry} - 成分股列表")
                    
                    # 获取该行业/概念的成分股
                    with st.spinner("正在加载成分股信息..."):
                        constituent_stocks = get_industry_constituent_stocks(selected_industry)
                    
                    if constituent_stocks and not constituent_stocks.empty:
                        # 显示成分股数量
                        st.info(f"该板块共有 **{len(constituent_stocks)}** 只成分股")
                        
                        # 获取最新价格和涨跌幅
                        if 'ts_code' in constituent_stocks.columns:
                            # 显示成分股列表
                            display_cols = ['name', 'industry']
                            if 'ts_code' in constituent_stocks.columns:
                                display_cols.insert(0, 'ts_code')
                            
                            st.dataframe(
                                constituent_stocks[display_cols] if all(c in constituent_stocks.columns for c in display_cols) else constituent_stocks,
                                column_config={
                                    "ts_code": "股票代码",
                                    "name": "股票名称",
                                    "industry": "所属行业"
                                },
                                height=400
                            )
                    else:
                        st.warning("暂无成分股数据，该板块可能是概念板块，Tushare 暂不提供详细成分股信息。")
                        st.info("💡 提示：您可以查看完整数据 tab，了解该板块的整体资金流向情况。")
                
                with detail_tab3:
                    # 显示该行业的详细数据
                    industry_data = df[df['name'] == selected_industry]
                    if not industry_data.empty:
                        st.dataframe(industry_data, use_container_width=True)
                    else:
                        st.warning("未找到该行业的详细数据")
                
                st.divider()
                
            # 数据处理
            if 'net_amount' in df.columns:
                # 元 -> 亿元
                df['net_amount_100m'] = df['net_amount'] / 100000000
                
                # 改为 Top 30
                tab1, tab2, tab3 = st.tabs([f"🔥 {metric_label} Top 30", f"🥶 资金流出 Top 30", "📋 完整数据"])
                
                with tab1:
                    # 仅展示净流入 > 0 的行业，避免出现负数造成困惑
                    top_in = df[df['net_amount'] > 0]
                    
                    if top_in.empty:
                        st.warning(f"📉 该区间 ({date_display}) 所有行业均为资金净流出。")
                        st.caption("建议查看'资金流出 Top 30'或检查选择的时间范围。")
                    else:
                        top_in = top_in.nlargest(30, 'net_amount')
                        # 增加高度以适应30条数据
                        fig, ax = plt.subplots(figsize=(10, max(6, len(top_in) * 0.4))) 
                        names = top_in['name'].iloc[::-1]
                        values = top_in['net_amount_100m'].iloc[::-1]
                        
                        bars = ax.barh(names, values, color=Colors.RISE, alpha=0.8)
                        ax.set_title(f'资金{metric_label} Top {len(top_in)} 行业 (仅展示正流入)')
                        ax.set_xlabel('亿元')
                        ax.grid(axis='x', linestyle='--', alpha=0.3)
                        ax.bar_label(bars, fmt='%.2f', padding=3)
                        st.pyplot(fig)
                    
                with tab2:
                    top_out = df.nsmallest(30, 'net_amount')
                    fig, ax = plt.subplots(figsize=(10, 12))
                    names = top_out['name'].iloc[::-1]
                    values = abs(top_out['net_amount_100m'].iloc[::-1])
                    
                    bars = ax.barh(names, values, color=Colors.FALL, alpha=0.8)
                    ax.set_title('资金净流出 Top 30 行业')
                    ax.set_xlabel('亿元')
                    ax.grid(axis='x', linestyle='--', alpha=0.3)
                    ax.bar_label(bars, fmt='%.2f', padding=3)
                    st.pyplot(fig)
                    
                with tab3:
                    cols_to_show = ['name', 'net_amount_100m', 'pct_change']
                    if 'company_num' in df.columns:
                        cols_to_show.append('company_num')
                    
                    pct_label = "平均涨跌幅" if is_range else "涨跌幅"
                    
                    st.dataframe(
                        df[cols_to_show].sort_values('net_amount_100m', ascending=False),
                        column_config={
                            "name": "行业名称",
                            "net_amount_100m": st.column_config.NumberColumn(f"{metric_label} (亿元)", format="%.2f"),
                            "pct_change": st.column_config.NumberColumn(pct_label, format="%.2f%%"),
                            "company_num": "成分股数量"
                        },
                        height=500
                    )

        # ==================== 3. 个股追踪模式 ====================
        elif "Stock" in analysis_mode:
            date_display = f"{start_date_str} - {end_date_str}" if is_range else start_date_str
            st.header(f"📈 A股个股资金趋势追踪 ({date_display})")
            
            # 获取股票列表
            all_stocks = get_stock_list()
            
            col1, col2 = st.columns([1, 2])
            with col1:
                # 默认选中平安银行
                default_idx = 0
                if all_stocks:
                    for i, s in enumerate(all_stocks):
                        if '000001.SZ' in s:
                            default_idx = i
                            break
                
                selected_stock_str = st.selectbox(
                    "选择或搜索股票 (支持代码/名称)", 
                    all_stocks if all_stocks else ["请稍候，正在加载股票列表..."],
                    index=default_idx if all_stocks else 0
                )
                
                # 提取代码: "000001.SZ 平安银行" -> "000001.SZ"
                symbol = selected_stock_str.split(' ')[0] if selected_stock_str else ""
            
            run_btn = st.button("开始分析", type="primary")
            
            if run_btn and symbol:
                with st.spinner(f"正在分析 {symbol} ({start_date_str}-{end_date_str})..."):
                    result = get_stock_money_flow(symbol, start_date_str, end_date_str)
                    
                if 'error' in result:
                    st.error(f"分析失败: {result['error']}")
                    return
                
                # 结果解读
                st.markdown("### 🤖 智能解读")
                trend = result.get('trend', 'neutral')
                interpretation = result.get('interpretation', '暂无解读')
                
                if 'accumulation' in trend:
                    st.success(f"**{interpretation}**")
                elif 'distribution' in trend:
                    st.warning(f"**{interpretation}**")
                else:
                    st.info(f"**{interpretation}**")
                    
                # 统计数据
                inst = result.get('institutional', {})
                retail = result.get('retail', {})
                total_days = result.get('total_days', 0)
                
                m1, m2, m3, m4 = st.columns(4)
                # 注意: analyze_institutional_vs_retail 返回的单位是万元
                m1.metric("机构累计流入", f"{inst.get('total_net_flow',0)/1e4:+.2f} 亿")
                m2.metric("机构流入天数", f"{inst.get('net_inflow_days',0)} / {total_days}")
                m3.metric("散户累计流入", f"{retail.get('total_net_flow',0)/1e4:+.2f} 亿")
                m4.metric("分析区间", f"{total_days} 交易日")
                
                # 绘制趋势图
                if 'flow_data' in result:
                    from web.components import plot_interactive_trend
                    
                    flow_df = result['flow_data'].copy()
                    flow_df.index = pd.to_datetime(flow_df.index)
                    
                    # 获取股价数据以增强图表
                    price_df = get_stock_price(symbol, start_date_str, end_date_str)
                    if not price_df.empty:
                        # 确保索引类型一致
                        price_df.index = pd.to_datetime(price_df.index)
                        common_idx = flow_df.index.intersection(price_df.index)
                        flow_df.loc[common_idx, 'close'] = price_df.loc[common_idx, 'close']

                    # 使用交互式图表
                    fig = plot_interactive_trend(
                        flow_df,
                        date_col=None,
                        inst_col='institutional_net',
                        retail_col='retail_net',
                        title=f"{symbol} 资金趋势"
                    )
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("暂无数据可绘图")
                    
                    with st.expander("查看详细数据"):
                        display_df = flow_df[['institutional_net', 'retail_net', 'close'] if 'close' in flow_df.columns else ['institutional_net', 'retail_net']]
                        st.dataframe(display_df.sort_index(ascending=False))
    
    # 渲染右侧 AI 面板
    with ai_col:
        render_ai_right_panel(session_id="money_flow_ai")

if __name__ == "__main__":
    main()
