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
    rank_stocks
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
    
    with main_col:
        st.title("🏆 风向排行榜")
        st.caption("对候选池标的进行多维度分析和排序")
        tab_stock, tab_industry = st.tabs(["📈 个股排行", "🏭 赛道排行"])
    
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
                    
                    def get_trend_label(symbol):
                        """获取趋势强度标签"""
                        try:
                            result = get_trend_strength(symbol, days=90)
                            if 'error' not in result:
                                score = result.get('score', 0)
                                level_icon = result.get('level_icon', '')
                                # 满分标记
                                if score == 4:
                                    return f"🔥 {score}/4"
                                else:
                                    return f"{level_icon} {score}/4"
                            return "-"
                        except:
                            return "-"
                    
                    trend_labels = []
                    # 批量计算
                    for idx, symbol in enumerate(df_ranked['symbol']):
                        label = get_trend_label(symbol)
                        trend_labels.append(label)
                        # 更新状态文本而非进度条
                        if (idx + 1) % 5 == 0:
                            status.update(label=f"🔄 正在计算趋势强度... ({idx+1}/{len(df_ranked)})")
                    
                    df_ranked['trend_label'] = trend_labels
                    status.update(label="✅ 趋势强度计算完成", state="complete", expanded=False)

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

                # 可视化 (使用 Plotly 替代 Matplotlib 以防渲染崩溃)
                st.divider()
                col1, col2 = st.columns(2)

                import plotly.express as px
                
                with col1:
                    st.markdown("#### 🎯 综合评分 Top 10")
                    try:
                        top_score = df_ranked.head(10).copy()
                        # 逆序以便 barh 从上到下显示
                        top_score = top_score.iloc[::-1]
                        
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
                            margin=dict(l=0, r=0, t=0, b=0),
                            height=300,
                            xaxis_range=[0, 100]
                        )
                        fig.update_traces(texttemplate='%{text:.1f}', textposition='outside')
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.error(f"图表渲染失败: {e}")

                with col2:
                    st.markdown("#### 📊 Top 5 因子分布")
                    try:
                        top5 = df_ranked.head(5).copy()
                        # 转换为长格式以便 Plotly 分组绘制
                        top5_melted = top5.melt(
                            id_vars=['name'], 
                            value_vars=['money_flow_score', 'technical_score', 'valuation_score', 'trend_score'],
                            var_name='Factor', 
                            value_name='Score'
                        )
                        # 因子名称映射
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
                            margin=dict(l=0, r=0, t=0, b=0),
                            height=300,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.error(f"图表渲染失败: {e}")

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

                # 综合评分 (资金权重40% + 技术权重60%)
                flow_score = min(max(result['inst_net_亿'] * 2, -10), 10)  # -10 ~ 10
                tech_score = (result['ma_score'] + result['macd_score'] + result['rsi_score']) * 3  # -9 ~ 9
                result['total_score'] = round(50 + flow_score * 2 + tech_score * 2, 1)  # 0 ~ 100

                results.append(result)
                progress_bar.progress((idx + 1) / len(candidates_df), text=f"正在分析: {name}")

            progress_bar.empty()

            # 生成排行榜
            df_results = pd.DataFrame(results)

            # 根据维度排序
            if sort_dimension == "💸 资金流向":
                df_sorted = df_results.sort_values('inst_net_亿', ascending=False)
            elif sort_dimension == "📉 技术形态":
                df_sorted = df_results.sort_values(['ma_score', 'macd_score'], ascending=False)
            else:
                df_sorted = df_results.sort_values('total_score', ascending=False)

            df_sorted = df_sorted.reset_index(drop=True)
            df_sorted.index = df_sorted.index + 1  # 排名从1开始
            df_sorted.index.name = '排名'

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
                top_flow = df_results.nlargest(10, 'inst_net_亿')
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
                top_score = df_results.nlargest(10, 'total_score')
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
            # 行业名称映射表：候选池行业 -> API 行业关键词列表
            INDUSTRY_MAPPING = {
                '交通运输': ['铁路公路', '航空机场', '物流行业', '船舶制造', '港口航运'],
                '家电零售': ['家电行业', '零售'],
                '计算机及软件': ['软件开发', '计算机设备', 'IT设备', '通信设备'],
                '汽车相关': ['汽车零部件', '汽车整车', '汽车服务'],
                '养殖农产品': ['养殖业', '农牧饲渔', '农业综合'],
                '食品饮料': ['食品饮料', '酿酒行业'],
                '医药': ['医药制造', '医疗器械', '中药', '生物制品', '化学制药'],
                '金融': ['银行', '保险', '证券', '多元金融'],
                '半导体': ['半导体', '电子元件'],
                '房地产': ['房地产', '房地产服务', '房地产开发'],
                '基建': ['工程建设', '建筑材料', '钢铁行业', '工程机械'],
                '资源': ['贵金属', '小金属', '有色金属', '采掘行业', '煤炭行业'],
                '能源': ['石油行业', '电力行业', '煤炭行业', '燃气'],
                '化工': ['化学制品', '化工行业', '化肥行业'],
                '军工': ['航天航空', '船舶制造', '国防军工'],
                '消费电子': ['消费电子', '电子元件'],
                '光伏': ['光伏设备', '电源设备'],
                '通信': ['通信设备', '通信服务'],
            }

            def match_industry(ind_name: str, api_industries: pd.Series) -> pd.DataFrame:
                """智能匹配行业名称"""
                # 1. 先尝试直接包含匹配
                matched = df_ind_agg[api_industries.str.contains(ind_name, na=False)]
                if not matched.empty:
                    return matched

                # 2. 使用映射表匹配
                keywords = INDUSTRY_MAPPING.get(ind_name, [])
                for kw in keywords:
                    matched = df_ind_agg[api_industries.str.contains(kw, na=False)]
                    if not matched.empty:
                        return matched

                # 3. 尝试部分匹配（行业名称的前两个字）
                if len(ind_name) >= 2:
                    matched = df_ind_agg[api_industries.str.contains(ind_name[:2], na=False)]
                    if not matched.empty:
                        return matched

                return pd.DataFrame()

            # 过滤候选池中的行业
            ind_results = []
            api_names = df_ind_agg['name']

            for ind in industries:
                # 统计该行业的股票数量
                ind_stocks = candidates_df[candidates_df['industry'] == ind]
                stock_count = len(ind_stocks)

                # 从行业资金数据中智能匹配
                matched = match_industry(ind, api_names)
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
    
    # 渲染右侧 AI 面板
    with ai_col:
        render_ai_right_panel(session_id="ranking_ai")


if __name__ == "__main__":
    main()
