
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
    get_market_summary,
    get_latest_trading_day
)
from web.components import render_period_selector
from web.ui_theme import Colors, apply_custom_css



def main():
    # 注意: page_config 只能在 Home.py 中设置一次，这里不再重复设置
    st.title("💸 A股市场资金流向分析 (Money Flow)")

    # 应用自定义样式
    apply_custom_css()

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
            st.info("💡 可能原因：\n- 当前选择的日期是非交易日（周末/节假日）\n- 数据尚未更新（盘中或盘后延迟）\n- 请尝试选择其他日期")
            return

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
            
        # 数据处理
        if 'net_amount' in df.columns:
            # 元 -> 亿元
            df['net_amount_100m'] = df['net_amount'] / 100000000
            
            # 改为 Top 30
            tab1, tab2, tab3 = st.tabs([f"🔥 {metric_label} Top 30", f"🥶 资金流出 Top 30", "📋 完整数据"])
            
            with tab1:
                top_in = df.nlargest(30, 'net_amount')
                # 增加高度以适应30条数据
                fig, ax = plt.subplots(figsize=(10, 12)) 
                names = top_in['name'].iloc[::-1]
                values = top_in['net_amount_100m'].iloc[::-1]
                
                bars = ax.barh(names, values, color=Colors.RISE, alpha=0.8)
                ax.set_title(f'资金{metric_label} Top 30 行业')
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

if __name__ == "__main__":
    main()
