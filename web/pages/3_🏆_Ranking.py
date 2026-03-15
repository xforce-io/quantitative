"""
🏆 风向排行榜
对候选池标的进行多维度分析和排序
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

# 导入统一的数据服务和组件
from web.data_service import (
    get_candidate_files,
    load_candidates,
    get_candidate_industries,
    get_stock_money_flow,
    get_stock_technical_data,
    get_industry_flow_with_details,
    get_latest_trading_day,
    get_ranking_profiles,
    rank_stocks,
    get_etf_pool,
    rank_etfs,
)
from web.components import plot_trend_chart, plot_technical_chart, render_stock_detail_card, render_period_selector
from web.ui_theme import Colors, apply_custom_css

# 导入 AI 面板组件
from web.components_ai_panel import render_ai_right_panel, init_ai_panel_for_page, get_ai_panel_layout
from web.page_registry import get_page_registry

# 注意: page_config 只能在 Home.py 中设置一次，这里不再重复设置


def main():
    # 应用自定义样式
    apply_custom_css()
    
    # 初始化 AI 面板所需组件
    init_ai_panel_for_page("Ranking", "pages/3_🏆_Ranking.py")
    
    # --- 侧边栏配置 ---
    st.sidebar.header("🎛️ 分析设置")
    
    # 1. 选择候选池
    pool_files = get_candidate_files()
    if not pool_files:
        st.error("未找到候选池文件，请在 config/candidates/ 目录下创建 .txt 文件")
        return
    
    selected_pool = st.sidebar.selectbox(
        "📁 候选池",
        options=pool_files,
        help="选择要分析的股票池"
    )
    
    # 2. 使用统一的时间选择组件
    start_str, end_str = render_period_selector(key_prefix="ranking")
    
    # 设置时间范围到 registry
    registry = get_page_registry()
    registry.set_date_range(start_str, end_str)
    
    # 3. 排序维度
    st.sidebar.subheader("📊 排序维度")

    # 获取可用的排名配置
    profiles = get_ranking_profiles()
    profile_options = list(profiles.keys())
    profile_labels = {k: f"{v['name']}" for k, v in profiles.items()}

    # 排名模式选择
    ranking_mode = st.sidebar.radio(
        "排名模式",
        ["🎯 智能排名", "📊 传统排名"],
        horizontal=True,
        help="智能排名使用多因子加权评分系统"
    )

    # 智能排名的配置选择
    selected_profile = 'balanced'
    if ranking_mode == "🎯 智能排名":
        selected_profile = st.sidebar.selectbox(
            "评分策略",
            options=profile_options,
            format_func=lambda x: profile_labels.get(x, x),
            index=profile_options.index('balanced') if 'balanced' in profile_options else 0
        )

        # 显示权重配置
        if selected_profile in profiles:
            weights = profiles[selected_profile]['weights']
            st.sidebar.caption(
                f"权重: 资金{weights.get('money_flow', 0):.0%} | "
                f"技术{weights.get('technical', 0):.0%} | "
                f"估值{weights.get('valuation', 0):.0%} | "
                f"趋势{weights.get('trend', 0):.0%}"
            )
    else:
        sort_dimension = st.sidebar.radio(
            "排序依据",
            ["💸 资金流向", "📉 技术形态", "🎯 综合评分"],
            horizontal=True
        )
    
    # --- 加载候选池 ---
    candidates_df = load_candidates(selected_pool)
    if candidates_df.empty:
        st.warning(f"候选池 '{selected_pool}' 为空")
        return
    
    st.sidebar.divider()
    st.sidebar.markdown(f"**标的数量**: {len(candidates_df)} 只")
    
    # --- 主界面：左右分栏布局 ---
    main_col, ai_col = get_ai_panel_layout(main_ratio=7, panel_ratio=3)

    # 先渲染 AI 面板（在耗时的 tab 内容计算前），确保面板及时出现
    with ai_col:
        render_ai_right_panel(session_id="ranking_ai")

    with main_col:
        st.title("🏆 风向排行榜")
        st.caption("对候选池标的进行多维度分析和排序")
        tab_stock, tab_industry, tab_etf = st.tabs(["📈 个股排行", "🏭 赛道排行", "🏛️ ETF排行"])

    # ========== 个股排行 ==========
    with tab_stock:
        st.markdown(f"### 📈 {selected_pool} 个股排行 ({len(candidates_df)}只)")

        # ===== 智能排名模式 =====
        if ranking_mode == "🎯 智能排名":
            st.info(f"🎯 使用 **{profile_labels.get(selected_profile, selected_profile)}** 策略进行智能排名")

            # 获取股票代码列表
            symbols = candidates_df['symbol'].tolist()

            # 调用排名服务
            with st.spinner(f"正在分析 {len(symbols)} 只标的..."):
                df_ranked = rank_stocks(symbols, profile=selected_profile, days=60)

            if df_ranked.empty:
                st.warning("排名分析未返回结果")
            else:
                # 合并名称信息
                name_map = dict(zip(candidates_df['symbol'], candidates_df['name']))
                industry_map = dict(zip(candidates_df['symbol'], candidates_df['industry']))
                df_ranked['name'] = df_ranked['symbol'].map(name_map)
                df_ranked['industry'] = df_ranked['symbol'].map(industry_map)

                # 计算趋势强度（4条规则评分）
                # 使用 st.status 替代原来的 st.info + st.progress，体验更平滑且会自动收起
                with st.status("🔄 正在计算趋势强度...", expanded=True) as status:
                    from web.data_service import get_trend_strength

                    @st.cache_data(ttl=300, show_spinner=False)
                    def compute_trend_labels(symbols: tuple, days: int = 90) -> list:
                        """批量计算趋势强度标签（缓存5分钟避免 rerun 重复计算）"""
                        import logging
                        labels = []
                        for symbol in symbols:
                            try:
                                result = get_trend_strength(symbol, days=days)
                                if 'error' not in result:
                                    score = result.get('score', 0)
                                    level_icon = result.get('level_icon', '')
                                    if score == 4:
                                        labels.append(f"🔥 {score}/4")
                                    else:
                                        labels.append(f"{level_icon} {score}/4")
                                else:
                                    labels.append("-")
                            except Exception as e:
                                logging.warning(f"趋势强度计算失败 {symbol}: {e}")
                                labels.append("-")
                        return labels

                    symbols_tuple = tuple(df_ranked['symbol'].tolist())
                    trend_labels = compute_trend_labels(symbols_tuple, days=90)

                    df_ranked['trend_label'] = trend_labels
                    valid_count = sum(1 for l in trend_labels if l != "-")
                    if valid_count == 0:
                        status.update(label="⚠️ 趋势强度数据为空，请检查数据源", state="error", expanded=False)
                    else:
                        status.update(label=f"✅ 趋势强度计算完成（{valid_count}/{len(trend_labels)} 有效）", state="complete", expanded=False)

                # ... (AI Context 注入代码保持不变) ...
                
                # --- 注入 AI Context: 个股排名 ---
                registry.register_data(
                    "ranking",
                    "stock_ranking",
                    df_ranked,
                    summary_extractor=lambda df: {
                        "profile": selected_profile,
                        "description": profiles.get(selected_profile, {}).get('description', ''),
                        "weights": profiles.get(selected_profile, {}).get('weights', {}),
                        "total_count": len(df),
                        "top_20_summary": df.head(20)[['rank', 'symbol', 'name', 'industry', 'composite_score', 'trend_score', 'trend_label', 'valuation_score']].to_dict('records'),
                        "trend_perfect_count": len(df[df['trend_label'].str.contains('🔥', na=False)])
                    }
                )
                
                # 注册配置详情
                registry.register_data(
                    "ranking",
                    "configuration",
                    {
                        "mode": ranking_mode,
                        "profile": selected_profile,
                        "profile_name": profile_labels.get(selected_profile, selected_profile),
                        "weights": profiles.get(selected_profile, {}).get('weights', {}),
                        "description": profiles.get(selected_profile, {}).get('description', '')
                    }
                )

                # 显示排行榜
                event = st.dataframe(
                    df_ranked[['rank', 'name', 'industry', 'composite_score',
                               'money_flow_score', 'technical_score', 'valuation_score', 'trend_score', 'trend_label', 'status']],
                    column_config={
                        "rank": st.column_config.NumberColumn("排名", width="small"),
                        "name": "名称",
                        "industry": "行业",
                        "composite_score": st.column_config.ProgressColumn(
                            "综合评分",
                            min_value=0,
                            max_value=100,
                            format="%.1f"
                        ),
                        "money_flow_score": st.column_config.NumberColumn("资金分", format="%.1f"),
                        "technical_score": st.column_config.NumberColumn("技术分", format="%.1f"),
                        "valuation_score": st.column_config.NumberColumn("估值分", format="%.1f"),
                        "trend_score": st.column_config.NumberColumn("趋势分", format="%.1f"),
                        "trend_label": "趋势强度",
                        "status": "状态"
                    },
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",  # 支持行选择
                    selection_mode="single-row"
                )
                
                # 显示趋势强度满分的股票统计
                try:
                    perfect_trend_count = len(df_ranked[df_ranked['trend_label'].str.contains('🔥', na=False)])
                    if perfect_trend_count > 0:
                        st.success(f"🔥 **{perfect_trend_count}** 只股票达到趋势强度满分（4/4），四条均线规则全部满足！")
                    else:
                        st.info("💡 当前没有股票达到趋势强度满分（4/4）")
                except Exception:
                    pass

                # 可视化区 (使用 container 包裹，且不使用嵌套列以防渲染异常)
                with st.container():
                    st.divider()
                    import plotly.express as px
                    
                    # 1. 综合评分 Top 10
                    st.markdown("#### 🎯 综合评分 Top 10")
                    try:
                        top_score = df_ranked.head(10).copy()
                        top_score = top_score.iloc[::-1] # 逆序
                        
                        fig = px.bar(
                            top_score, 
                            x='composite_score', 
                            y='name',
                            orientation='h',
                            text='composite_score',
                            color='status',
                            color_discrete_map={'success': Colors.PRIMARY, 'normal': Colors.NEUTRAL, 'warning': Colors.WARNING},
                            labels={'name': '股票名称', 'composite_score': '综合评分'}
                        )
                        fig.update_layout(
                            showlegend=False,
                            margin=dict(l=10, r=10, t=10, b=10),
                            height=400, # 稍微增加高度
                            xaxis_range=[0, 100]
                        )
                        fig.update_traces(texttemplate='%{text:.1f}', textposition='outside')
                        st.plotly_chart(fig, use_container_width=True, key="ranking_top10_chart")
                    except Exception as e:
                        st.error(f"Top 10 图表渲染失败: {e}")

                    # 2. 因子分布
                    st.markdown("#### 📊 Top 5 因子分布")
                    try:
                        top5 = df_ranked.head(5).copy()
                        top5_melted = top5.melt(
                            id_vars=['name'], 
                            value_vars=['money_flow_score', 'technical_score', 'valuation_score', 'trend_score'],
                            var_name='Factor', 
                            value_name='Score'
                        )
                        factor_map = {
                            'money_flow_score': '资金', 'technical_score': '技术', 
                            'valuation_score': '估值', 'trend_score': '趋势'
                        }
                        top5_melted['Factor'] = top5_melted['Factor'].map(factor_map)
                        
                        fig = px.bar(
                            top5_melted,
                            x='name',
                            y='Score',
                            color='Factor',
                            barmode='group',
                            labels={'name': '股票名称', 'Score': '得分', 'Factor': '因子'},
                            color_discrete_map={'资金': Colors.INSTITUTIONAL, '技术': Colors.PRIMARY, '估值': Colors.RETAIL, '趋势': '#9333EA'}
                        )
                        fig.update_layout(
                            margin=dict(l=10, r=10, t=30, b=10),
                            height=400,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                        )
                        st.plotly_chart(fig, use_container_width=True, key="ranking_factors_chart")
                    except Exception as e:
                        st.error(f"因子分布图表渲染失败: {e}")

                # 详细分析
                st.divider()
                st.markdown("### 📋 详细分析")

                # 获取表格选中的行
                selected_rows = event.selection.rows if event.selection else []

                # 如果有选中行，使用选中的股票；否则使用下拉框
                if selected_rows:
                    selected_idx = selected_rows[0]
                    selected_stock = df_ranked.iloc[selected_idx]['name']
                    st.info(f"📌 已选中表格中的: **{selected_stock}**")
                else:
                    selected_stock = st.selectbox(
                        "选择标的查看详情（或点击上方表格中的行）",
                        options=df_ranked['name'].dropna().tolist(),
                        format_func=lambda x: f"{df_ranked[df_ranked['name']==x]['rank'].values[0]}. {x}"
                    )

                if selected_stock:
                    stock_row = df_ranked[df_ranked['name'] == selected_stock].iloc[0]
                    symbol = stock_row['symbol']

                    with st.expander(f"📊 {selected_stock} ({symbol}) 详细分析", expanded=True):
                        # 显示得分详情
                        score_col1, score_col2, score_col3, score_col4, score_col5 = st.columns(5)
                        with score_col1:
                            st.metric("综合评分", f"{stock_row['composite_score']:.1f}")
                        with score_col2:
                            st.metric("资金流向分", f"{stock_row['money_flow_score']:.1f}")
                        with score_col3:
                            st.metric("技术形态分", f"{stock_row['technical_score']:.1f}")
                        with score_col4:
                            st.metric("估值分", f"{stock_row['valuation_score']:.1f}")
                        with score_col5:
                            st.metric("趋势动量分", f"{stock_row['trend_score']:.1f}")

                        st.divider()

                        # 使用统一的个股详情组件
                        render_stock_detail_card(
                            symbol=symbol,
                            name=selected_stock,
                            start_str=start_str,
                            end_str=end_str,
                            key_prefix="smart_rank_"
                        )

        # ===== 传统排名模式 =====
        else:
            # 批量分析
            results = []
            progress_bar = st.progress(0, text="正在分析...")

            for idx, row in candidates_df.iterrows():
                symbol = row['symbol']
                name = row['name']
                industry = row['industry']

                result = {
                    'symbol': symbol,
                    'name': name,
                    'industry': industry,
                    'description': row['description'],
                    'inst_net': 0,
                    'inst_net_亿': 0,
                    'inst_days': 0,
                    'ma_trend': '-',
                    'ma_score': 0,
                    'macd_signal': '-',
                    'macd_score': 0,
                    'rsi': 0,
                    'rsi_status': '-',
                    'rsi_score': 0,
                }

                try:
                    # 获取资金流向
                    flow_data = get_stock_money_flow(symbol, start_str, end_str)

                    if 'error' not in flow_data:
                        inst = flow_data.get('institutional', {})
                        result['inst_net'] = inst.get('total_net_flow', 0)
                        result['inst_net_亿'] = result['inst_net'] / 1e8
                        result['inst_days'] = inst.get('net_inflow_days', 0)

                    # 获取技术数据 (90天)
                    tech_start = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
                    tech_df = get_stock_technical_data(symbol, tech_start, end_str)

                    if not tech_df.empty and len(tech_df) > 20:
                        latest = tech_df.iloc[-1]

                        # 均线趋势
                        ma5 = latest.get('MA5')
                        ma20 = latest.get('MA20')
                        if pd.notna(ma5) and pd.notna(ma20):
                            result['ma_trend'] = '多头' if ma5 > ma20 else '空头'
                            result['ma_score'] = 1 if ma5 > ma20 else -1

                        # MACD
                        dif = latest.get('MACD_DIF')
                        dea = latest.get('MACD_DEA')
                        if pd.notna(dif) and pd.notna(dea):
                            result['macd_signal'] = '金叉' if dif > dea else '死叉'
                            result['macd_score'] = 1 if dif > dea else -1

                        # RSI
                        rsi = latest.get('RSI')
                        if pd.notna(rsi):
                            result['rsi'] = round(rsi, 1)
                            if rsi > 70:
                                result['rsi_status'] = '超买'
                                result['rsi_score'] = -1
                            elif rsi < 30:
                                result['rsi_status'] = '超卖'
                                result['rsi_score'] = 1
                            else:
                                result['rsi_status'] = '中性'

                except Exception as e:
                    # 单个股票出错不影响整体
                    pass

                results.append(result)
                progress_bar.progress((idx + 1) / len(candidates_df), text=f"正在分析: {name}")

            progress_bar.empty()

            # 使用 StockRanker.simple_rank() 计算综合评分并排序
            from quant.analysis.screener.ranker import StockRanker
            sort_key_map = {
                "💸 资金流向": 'inst_net_亿',
                "📉 技术形态": 'ma_score',
                "🎯 综合评分": 'total_score',
            }
            df_sorted = StockRanker.simple_rank(
                results, sort_by=sort_key_map.get(sort_dimension, 'total_score')
            )

            # 显示排行榜
            st.dataframe(
                df_sorted[['name', 'industry', 'inst_net_亿', 'ma_trend', 'macd_signal', 'rsi', 'total_score']].head(30),
                column_config={
                    "name": "名称",
                    "industry": "行业",
                    "inst_net_亿": st.column_config.NumberColumn("机构净额(亿)", format="%.2f"),
                    "ma_trend": "均线",
                    "macd_signal": "MACD",
                    "rsi": st.column_config.NumberColumn("RSI", format="%.1f"),
                    "total_score": st.column_config.ProgressColumn(
                        "综合评分",
                        min_value=0,
                        max_value=100,
                        format="%.1f"  # 显示为数值
                    )
                },
                use_container_width=True
            )

            # 可视化排行
            st.divider()
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### 💸 资金流向 Top 10")
                top_flow = df_sorted.nlargest(10, 'inst_net_亿')
                fig, ax = plt.subplots(figsize=(8, 5))
                colors = [Colors.RISE if x > 0 else Colors.FALL for x in top_flow['inst_net_亿']]
                ax.barh(range(len(top_flow)), top_flow['inst_net_亿'], color=colors, alpha=0.8)
                ax.set_yticks(range(len(top_flow)))
                ax.set_yticklabels(top_flow['name'])
                ax.set_xlabel("机构净额 (亿元)")
                ax.invert_yaxis()
                ax.grid(axis='x', linestyle='--', alpha=0.3)
                st.pyplot(fig)
                plt.close(fig)

            with col2:
                st.markdown("#### 🎯 综合评分 Top 10")
                top_score = df_sorted.nlargest(10, 'total_score')
                fig, ax = plt.subplots(figsize=(8, 5))
                ax.barh(range(len(top_score)), top_score['total_score'], color=Colors.PRIMARY, alpha=0.8)
                ax.set_yticks(range(len(top_score)))
                ax.set_yticklabels(top_score['name'])
                ax.set_xlabel("综合评分")
                ax.set_xlim(0, 100)
                ax.invert_yaxis()
                ax.grid(axis='x', linestyle='--', alpha=0.3)
                st.pyplot(fig)
                plt.close(fig)

            # 详细分析 (可展开)
            st.divider()
            st.markdown("### 📋 详细分析")

            selected_stock = st.selectbox(
                "选择标的查看详情",
                options=df_sorted['name'].tolist(),
                format_func=lambda x: f"{df_sorted[df_sorted['name']==x].index[0]}. {x}"
            )

            if selected_stock:
                stock_row = df_sorted[df_sorted['name'] == selected_stock].iloc[0]
                symbol = stock_row['symbol']

                with st.expander(f"📊 {selected_stock} ({symbol}) 详细分析", expanded=True):
                    # 使用统一的个股详情组件
                    render_stock_detail_card(
                        symbol=symbol,
                        name=selected_stock,
                        start_str=start_str,
                        end_str=end_str,
                        key_prefix="rank_"
                    )
    
    # ========== 赛道排行 ==========
    with tab_industry:
        st.markdown(f"### 🏭 赛道排行")

        # 获取候选池中的行业
        industries = get_candidate_industries(selected_pool)
        if not industries:
            st.warning("候选池中无行业数据")
            return

        # 获取行业资金数据
        df_ind_agg, df_ind_raw = get_industry_flow_with_details(start_str, end_str)

        if df_ind_agg.empty:
            st.warning("暂无行业资金数据")
        else:
            from quant.core.symbol_resolver import IndustryMapper

            # 过滤候选池中的行业
            ind_results = []

            for ind in industries:
                # 统计该行业的股票数量
                ind_stocks = candidates_df[candidates_df['industry'] == ind]
                stock_count = len(ind_stocks)

                # 从行业资金数据中智能匹配
                matched = IndustryMapper.match_industry(ind, df_ind_agg)
                if not matched.empty:
                    net_amount = matched['net_amount'].sum()
                else:
                    net_amount = 0

                ind_results.append({
                    'industry': ind,
                    'stock_count': stock_count,
                    'net_amount': net_amount,
                    'net_amount_亿': net_amount / 1e8
                })
            
            df_ind_results = pd.DataFrame(ind_results)
            df_ind_results = df_ind_results.sort_values('net_amount_亿', ascending=False)
            df_ind_results = df_ind_results.reset_index(drop=True)
            df_ind_results.index = df_ind_results.index + 1
            df_ind_results.index.name = '排名'
            
            # --- 注入 AI Context: 行业排名 ---
            registry.register_data(
                registry.CATEGORY_INDUSTRY,
                "flow_ranking",
                df_ind_results,
                summary_extractor=lambda df: {
                    "total_industries": len(df),
                    "top_inflow": df.head(5)[['industry', 'net_amount_亿', 'stock_count']].to_dict('records'),
                    "top_outflow": df.tail(5)[['industry', 'net_amount_亿', 'stock_count']].to_dict('records')
                }
            )

            st.dataframe(
                df_ind_results[['industry', 'stock_count', 'net_amount_亿']],
                column_config={
                    "industry": "行业",
                    "stock_count": "候选股票数",
                    "net_amount_亿": st.column_config.NumberColumn("净流入(亿)", format="%.2f")
                },
                use_container_width=True
            )
            
            # 可视化
            fig, ax = plt.subplots(figsize=(10, max(3, len(df_ind_results) * 0.4)))
            df_plot = df_ind_results.sort_values('net_amount_亿', ascending=True)
            colors = [Colors.RISE if x > 0 else Colors.FALL for x in df_plot['net_amount_亿']]
            ax.barh(range(len(df_plot)), df_plot['net_amount_亿'], color=colors, alpha=0.8)
            ax.set_yticks(range(len(df_plot)))
            ax.set_yticklabels(df_plot['industry'])
            ax.set_xlabel("净流入 (亿元)")
            ax.set_title(f"赛道资金排行 ({start_str}-{end_str})")
            ax.grid(axis='x', linestyle='--', alpha=0.3)
            st.pyplot(fig)
            plt.close(fig)
    
    # ========== ETF 排行 ==========
    with tab_etf:
        st.markdown("### 🏛️ ETF 趋势排行")

        # 控制栏
        etf_col1, etf_col2 = st.columns([1, 1])
        with etf_col1:
            etf_source = st.radio(
                "ETF 池", ["精选池 (25只)", "Tushare 热门"],
                horizontal=True, key="etf_source"
            )
        with etf_col2:
            etf_sort = st.selectbox(
                "排序维度",
                ["🎯 综合得分", "📈 20日涨幅", "📊 60日涨幅"],
                key="etf_sort"
            )

        source_key = "default" if "精选" in etf_source else "tushare"

        with st.status("🔄 正在计算 ETF 轮动排名...", expanded=True) as etf_status:
            df_etf = rank_etfs(etf_pool=source_key, top_n=50)

            if df_etf.empty:
                etf_status.update(label="⚠️ ETF 排名数据为空", state="error", expanded=False)
                st.warning("未能获取 ETF 排名数据，请检查数据源")
            else:
                etf_status.update(
                    label=f"✅ 已完成 {len(df_etf)} 只 ETF 排名",
                    state="complete", expanded=False
                )

        if not df_etf.empty:
            # 排序
            sort_col_map = {
                "🎯 综合得分": "score",
                "📈 20日涨幅": "ret_20d",
                "📊 60日涨幅": "ret_60d",
            }
            sort_col = sort_col_map.get(etf_sort, "score")
            df_etf = df_etf.sort_values(sort_col, ascending=False).reset_index(drop=True)
            df_etf.index = df_etf.index + 1
            df_etf.index.name = '排名'

            # 信号图标映射
            signal_icons = {
                "长短期共振向上": "🟢",
                "短期转负中期为正": "🟡",
                "排名持续下滑": "🔴",
                "得分回升但短期仍负": "🟠",
                "滞胀预警": "⚠️",
                "无明显信号": "⚪",
            }
            df_etf['signal_icon'] = df_etf['signal'].map(
                lambda s: signal_icons.get(s, "⚪") + " " + s
            )

            # 显示排行表格
            display_cols = {
                'name': '名称',
                'ts_code': '代码',
                'category': '分类',
                'score': '综合得分',
                'ret_20d_pct': '20日涨幅',
                'ret_60d_pct': '60日涨幅',
                'tier': '分层',
                'signal_icon': '信号',
            }
            df_display = df_etf[[c for c in display_cols if c in df_etf.columns]].rename(
                columns=display_cols
            )

            st.dataframe(
                df_display,
                use_container_width=True,
                height=min(600, 40 + len(df_display) * 35),
                column_config={
                    '综合得分': st.column_config.NumberColumn(format="%.4f"),
                }
            )

            # 可视化
            with st.container():
                st.divider()
                import plotly.express as px

                # 1. Top 10 综合得分
                st.markdown("#### 🎯 综合得分 Top 10")
                try:
                    top10 = df_etf.head(10).copy().iloc[::-1]
                    fig = px.bar(
                        top10, y='name', x='score',
                        orientation='h',
                        text=top10['score'].round(4),
                        color='tier',
                        color_discrete_map={
                            '强势主线': Colors.RISE,
                            '震荡观望': Colors.PRIMARY,
                            '弱势回避': Colors.FALL,
                        }
                    )
                    fig.update_layout(
                        showlegend=True,
                        margin=dict(l=10, r=10, t=10, b=10),
                        height=400,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    fig.update_traces(texttemplate='%{text:.4f}', textposition='outside')
                    st.plotly_chart(fig, use_container_width=True, key="etf_top10_chart")
                except Exception as e:
                    st.error(f"Top 10 图表渲染失败: {e}")

                # 2. 板块动量热力图
                st.markdown("#### 📊 板块动量概览")
                try:
                    df_cat = df_etf.groupby('category').agg(
                        avg_ret_20d=('ret_20d', 'mean'),
                        avg_ret_60d=('ret_60d', 'mean'),
                        avg_score=('score', 'mean'),
                        count=('ts_code', 'count'),
                    ).reset_index()
                    df_cat = df_cat.sort_values('avg_score', ascending=False)
                    df_cat['avg_ret_20d_pct'] = (df_cat['avg_ret_20d'] * 100).round(2)
                    df_cat['avg_ret_60d_pct'] = (df_cat['avg_ret_60d'] * 100).round(2)

                    fig = px.bar(
                        df_cat, x='category', y=['avg_ret_20d_pct', 'avg_ret_60d_pct'],
                        barmode='group',
                        labels={'value': '平均涨幅(%)', 'category': '板块', 'variable': ''},
                        color_discrete_map={
                            'avg_ret_20d_pct': Colors.PRIMARY,
                            'avg_ret_60d_pct': Colors.INSTITUTIONAL,
                        }
                    )
                    # 重命名图例
                    fig.for_each_trace(lambda t: t.update(
                        name='20日均涨幅' if '20' in t.name else '60日均涨幅'
                    ))
                    fig.update_layout(
                        margin=dict(l=10, r=10, t=10, b=10),
                        height=350,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig, use_container_width=True, key="etf_sector_chart")
                except Exception as e:
                    st.error(f"板块概览图表渲染失败: {e}")

            # 分层汇总
            st.divider()
            st.markdown("#### 📋 分层汇总")
            for tier_name, tier_icon in [("强势主线", "🟢"), ("震荡观望", "🟡"), ("弱势回避", "🔴")]:
                sub = df_etf[df_etf['tier'] == tier_name]
                if not sub.empty:
                    names = "、".join(sub['name'].tolist())
                    st.markdown(f"**{tier_icon} {tier_name}** ({len(sub)}只): {names}")

if __name__ == "__main__":
    main()
