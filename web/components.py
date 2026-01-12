"""
Web UI Components
可复用的可视化组件，供所有 Web 页面使用。
"""

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Any

from web.ui_theme import Colors, setup_matplotlib_style

# 初始化样式
setup_matplotlib_style()


# ==================== 时间选择组件 ====================

def render_period_selector(
    key_prefix: str = "",
    show_custom: bool = True,
    default_period: str = "📅 本周"
) -> Tuple[str, str]:
    """
    统一的时间周期选择器

    Args:
        key_prefix: widget key 前缀 (避免重复)
        show_custom: 是否显示自定义区间选项
        default_period: 默认选中的周期

    Returns:
        (start_str, end_str): YYYYMMDD 格式的开始和结束日期
    """
    # 延迟导入避免循环引用
    from web.data_service import get_latest_trading_day

    # 使用 session_state 记忆选择
    period_key = f"{key_prefix}_period_type"
    custom_start_key = f"{key_prefix}_custom_start"
    custom_end_key = f"{key_prefix}_custom_end"

    # 初始化 session_state
    if period_key not in st.session_state:
        st.session_state[period_key] = default_period

    # 选项列表
    if show_custom:
        period_options = ["📅 单日", "📅 本周", "📅 本月", "🗓 自定义区间"]
    else:
        period_options = ["📅 单日", "📅 本周", "📅 本月"]

    # 获取保存的索引
    saved_period = st.session_state.get(period_key, default_period)
    if saved_period in period_options:
        default_index = period_options.index(saved_period)
    else:
        default_index = period_options.index(default_period) if default_period in period_options else 1

    st.sidebar.subheader("📅 时间维度")
    period_type = st.sidebar.radio(
        "统计周期",
        period_options,
        index=default_index,
        horizontal=True,
        key=f"{key_prefix}_period_radio"
    )

    # 保存选择到 session_state
    st.session_state[period_key] = period_type

    # 使用统一的交易日计算函数
    today = get_latest_trading_day()

    if period_type == "📅 单日":
        s_date = e_date = today
    elif period_type == "📅 本周":
        s_date = today - timedelta(days=today.weekday())
        e_date = today
    elif period_type == "📅 本月":
        s_date = today.replace(day=1)
        e_date = today
    else:  # 自定义区间
        # 读取保存的自定义日期
        saved_start = st.session_state.get(custom_start_key, (today - timedelta(days=30)).strftime('%Y-%m-%d'))
        saved_end = st.session_state.get(custom_end_key, today.strftime('%Y-%m-%d'))

        col1, col2 = st.sidebar.columns(2)
        s_date = col1.date_input("开始", datetime.strptime(saved_start, '%Y-%m-%d'), key=f"{key_prefix}_start_input")
        e_date = col2.date_input("结束", datetime.strptime(saved_end, '%Y-%m-%d'), key=f"{key_prefix}_end_input")

        # 保存自定义日期
        st.session_state[custom_start_key] = s_date.strftime('%Y-%m-%d')
        st.session_state[custom_end_key] = e_date.strftime('%Y-%m-%d')

    start_str = s_date.strftime('%Y%m%d')
    end_str = e_date.strftime('%Y%m%d')

    # 显示区间
    st.sidebar.caption(f"区间: {start_str} - {end_str}")

    return start_str, end_str


def plot_trend_chart(
    df: pd.DataFrame,
    date_col: Optional[str] = 'trade_date',
    inst_col: str = 'institutional_net',
    retail_col: str = 'retail_net',
    total_col: str = 'net_amount'
) -> Tuple[Optional[plt.Figure], str]:
    """
    通用资金趋势绘图组件
    
    Args:
        df: 数据表，需包含日期和金额列
        date_col: 日期列名，如果为 None 则使用 index
        inst_col: 机构净流入列名
        retail_col: 散户净流入列名
        total_col: 总净流入列名 (降级时使用)
    
    Returns:
        (fig, summary_text): matplotlib Figure 和摘要文字
    """
    if df.empty:
        return None, "无数据"
    
    # 确定日期来源
    if date_col and date_col in df.columns:
        dates = pd.to_datetime(df[date_col])
    else:
        dates = pd.to_datetime(df.index)
    
    fig, ax = plt.subplots(figsize=(6, 4))
    width = 0.4
    x = range(len(dates))
    
    # 检查是否有机构/散户明细数据
    has_breakdown = (inst_col in df.columns and df[inst_col].abs().sum() > 0)
    
    if has_breakdown:
        # 转换为亿元
        inst_vals = df[inst_col] / 1e8
        retail_vals = df[retail_col] / 1e8
        total_net_raw = df[inst_col].sum()
        
        ax.bar([i - width/2 for i in x], inst_vals, width, label='机构', color=Colors.INSTITUTIONAL, alpha=0.8)
        ax.bar([i + width/2 for i in x], retail_vals, width, label='散户', color=Colors.RETAIL, alpha=0.8)
        ax.legend(fontsize=8, loc='upper left')
        
        trend_text = "🔴 主力大幅买入" if total_net_raw > 5e7 else ("🟢 主力大幅撤退" if total_net_raw < -5e7 else "⚪️ 资金震荡")
        summary_text = f"{trend_text} | 机构净额: {total_net_raw/1e8:+.2f}亿"
    else:
        # 降级：只画总净流入
        net_vals = df[total_col] / 1e8
        total_net_raw = df[total_col].sum()
        
        # 不使用 label，避免误导性图例
        ax.bar(x, net_vals, width * 1.5, color=[Colors.RISE if v > 0 else Colors.FALL for v in net_vals], alpha=0.8)
        
        trend_text = "🔥 资金抢筹" if total_net_raw > 0 else "🧊 资金流出"
        summary_text = f"{trend_text} | 累计净额: {total_net_raw/1e8:+.2f}亿"
    
    ax.set_title(f"资金流向 ({len(dates)}日)", fontsize=10)
    ax.set_ylabel("亿元", fontsize=8)
    ax.tick_params(axis='x', rotation=45, labelsize=8)
    ax.tick_params(axis='y', labelsize=8)
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    
    # 简化 X 轴标签
    if len(dates) > 1:
        step = max(1, len(dates) // 5)
        ax.set_xticks([i for i in x[::step]])
        ax.set_xticklabels([d.strftime('%m-%d') for d in dates[::step]])
    else:
        ax.set_xticks(list(x))
        ax.set_xticklabels([d.strftime('%m-%d') for d in dates])
    
    plt.tight_layout()
    return fig, summary_text


def plot_comparison_bar(
    df: pd.DataFrame,
    name_col: str,
    value_col: str,
    title: str,
    xlabel: str = "亿元"
) -> plt.Figure:
    """
    横向对比柱状图 (用于资金排行)
    
    Args:
        df: 数据表
        name_col: 名称列
        value_col: 数值列
        title: 图表标题
        xlabel: X轴标签
    
    Returns:
        matplotlib Figure
    """
    df_sorted = df.sort_values(value_col, ascending=True)
    
    fig, ax = plt.subplots(figsize=(10, max(3, len(df) * 0.5 + 1)))
    
    y_pos = range(len(df_sorted))
    values = df_sorted[value_col]
    colors = [Colors.RISE if v > 0 else Colors.FALL for v in values]
    
    ax.barh(y_pos, values, color=colors, alpha=0.8)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(df_sorted[name_col], fontsize=10)
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.grid(axis='x', linestyle='--', alpha=0.3)
    
    # 添加数值标签
    ax.bar_label(ax.containers[0], fmt='%.2f', padding=3)
    
    plt.tight_layout()
    return fig


def plot_technical_chart(
    df: pd.DataFrame,
    symbol: str = "",
    show_volume: bool = True,
    show_macd: bool = True,
    show_rsi: bool = False
) -> Tuple[Optional[plt.Figure], dict]:
    """
    专业技术分析图表 (K线 + 均线 + MACD/RSI)
    
    Args:
        df: OHLCV 数据，需包含 open/high/low/close/volume 及技术指标列
        symbol: 股票代码 (用于标题)
        show_volume: 是否显示成交量
        show_macd: 是否显示 MACD
        show_rsi: 是否显示 RSI
    
    Returns:
        (fig, analysis_dict): matplotlib Figure 和分析结果字典
    """
    if df.empty or 'close' not in df.columns:
        return None, {"error": "数据不足"}
    
    # 确保索引是日期
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'trade_date' in df.columns:
            df = df.set_index('trade_date')
        df.index = pd.to_datetime(df.index)
    
    # 计算子图数量
    n_subplots = 1  # 主图 (K线+均线)
    if show_volume:
        n_subplots += 1
    if show_macd:
        n_subplots += 1
    if show_rsi:
        n_subplots += 1
    
    # 设置子图高度比例
    if n_subplots == 1:
        height_ratios = [1]
    elif n_subplots == 2:
        height_ratios = [3, 1]
    elif n_subplots == 3:
        height_ratios = [3, 1, 1]
    else:
        height_ratios = [3, 1, 1, 1]
    
    fig, axes = plt.subplots(n_subplots, 1, figsize=(10, 2 + n_subplots * 2), 
                              gridspec_kw={'height_ratios': height_ratios}, sharex=True)
    
    if n_subplots == 1:
        axes = [axes]
    
    ax_idx = 0
    dates = df.index
    x = range(len(dates))
    
    # ========== 主图：价格 + 均线 ==========
    ax_price = axes[ax_idx]
    ax_idx += 1
    
    # 绘制收盘价线
    ax_price.plot(x, df['close'], color='#1a1a2e', linewidth=1.5, label='收盘价')
    
    # 绘制均线
    ma_colors = {'MA5': Colors.RISE, 'MA10': Colors.WARNING, 'MA20': Colors.FALL, 'MA60': Colors.INFO}
    for ma, color in ma_colors.items():
        if ma in df.columns:
            ax_price.plot(x, df[ma], color=color, linewidth=1, alpha=0.8, label=ma)
    
    # 绘制布林带
    if 'BOLL_UP' in df.columns and 'BOLL_DOWN' in df.columns:
        ax_price.fill_between(x, df['BOLL_UP'], df['BOLL_DOWN'], alpha=0.1, color=Colors.PRIMARY)
        ax_price.plot(x, df['BOLL_UP'], color=Colors.PRIMARY, linewidth=0.8, linestyle='--', alpha=0.6)
        ax_price.plot(x, df['BOLL_DOWN'], color=Colors.PRIMARY, linewidth=0.8, linestyle='--', alpha=0.6)
    
    ax_price.set_title(f"{symbol} 技术形态分析", fontsize=12, fontweight='bold')
    ax_price.legend(loc='upper left', fontsize=7, ncol=3)
    ax_price.set_ylabel("价格", fontsize=9)
    ax_price.grid(True, linestyle='--', alpha=0.3)
    
    # ========== 成交量 ==========
    if show_volume and 'volume' in df.columns:
        ax_vol = axes[ax_idx]
        ax_idx += 1
        
        # 涨跌颜色
        colors = [Colors.RISE if df['close'].iloc[i] >= df['open'].iloc[i] else Colors.FALL
                  for i in range(len(df))]
        ax_vol.bar(x, df['volume'] / 1e6, color=colors, alpha=0.7, width=0.8)
        
        # 添加图例：红色代表收盘价高于开盘价（收阳），绿色代表收盘价低于开盘价（收阴）
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor=Colors.RISE, alpha=0.7, label='收阳 (涨)'),
            Patch(facecolor=Colors.FALL, alpha=0.7, label='收阴 (跌)')
        ]
        ax_vol.legend(handles=legend_elements, loc='upper left', fontsize=7, ncol=2)
        
        ax_vol.set_ylabel("成交量(百万)", fontsize=8)
        ax_vol.grid(True, linestyle='--', alpha=0.3)
    
    # ========== MACD ==========
    if show_macd and 'MACD_DIF' in df.columns:
        ax_macd = axes[ax_idx]
        ax_idx += 1
        
        ax_macd.plot(x, df['MACD_DIF'], color=Colors.RISE, linewidth=1, label='DIF')
        ax_macd.plot(x, df['MACD_DEA'], color=Colors.PRIMARY, linewidth=1, label='DEA')
        
        # MACD 柱状图
        hist = df['MACD_HIST']
        colors = [Colors.RISE if v >= 0 else Colors.FALL for v in hist]
        ax_macd.bar(x, hist, color=colors, alpha=0.7, width=0.8)
        
        ax_macd.axhline(y=0, color='gray', linewidth=0.5)
        ax_macd.set_ylabel("MACD", fontsize=8)
        ax_macd.legend(loc='upper left', fontsize=7)
        ax_macd.grid(True, linestyle='--', alpha=0.3)
    
    # ========== RSI ==========
    if show_rsi and 'RSI' in df.columns:
        ax_rsi = axes[ax_idx]
        ax_idx += 1
        
        ax_rsi.plot(x, df['RSI'], color=Colors.INFO, linewidth=1)
        ax_rsi.axhline(y=70, color=Colors.RISE, linewidth=0.8, linestyle='--', alpha=0.7)
        ax_rsi.axhline(y=30, color=Colors.FALL, linewidth=0.8, linestyle='--', alpha=0.7)
        ax_rsi.fill_between(x, 30, 70, alpha=0.1, color='gray')
        ax_rsi.set_ylim(0, 100)
        ax_rsi.set_ylabel("RSI", fontsize=8)
        ax_rsi.grid(True, linestyle='--', alpha=0.3)
    
    # X 轴标签
    step = max(1, len(dates) // 8)
    axes[-1].set_xticks([i for i in x[::step]])
    axes[-1].set_xticklabels([d.strftime('%m-%d') for d in dates[::step]], fontsize=8, rotation=45)
    
    plt.tight_layout()
    
    # ========== 生成分析结果 ==========
    analysis = {}
    interpretations = []  # 收集解读文字
    
    if len(df) > 0:
        latest = df.iloc[-1]
        analysis['latest_close'] = latest['close']
        
        # 均线趋势判断
        if 'MA5' in df.columns and 'MA20' in df.columns:
            ma5 = latest['MA5']
            ma20 = latest['MA20']
            ma60 = latest.get('MA60', None)
            
            if pd.notna(ma5) and pd.notna(ma20):
                if ma5 > ma20:
                    analysis['ma_trend'] = '短期多头'
                    interpretations.append("📈 短期均线向上，多头排列")
                else:
                    analysis['ma_trend'] = '短期空头'
                    interpretations.append("📉 短期均线向下，空头排列")
                
                # 价格相对均线位置
                close = latest['close']
                if close > ma5 > ma20:
                    interpretations.append("💪 价格站稳均线上方，趋势强劲")
                elif close < ma5 < ma20:
                    interpretations.append("⚠️ 价格跌破均线，注意风险")
        
        # MACD 信号
        if 'MACD_DIF' in df.columns and 'MACD_DEA' in df.columns:
            dif = latest['MACD_DIF']
            dea = latest['MACD_DEA']
            hist = latest.get('MACD_HIST', 0)
            
            if pd.notna(dif) and pd.notna(dea):
                if dif > dea:
                    analysis['macd_signal'] = '金叉/多头'
                    if hist > 0:
                        interpretations.append("🟢 MACD金叉且红柱放大，动能增强")
                    else:
                        interpretations.append("🟡 MACD金叉但动能不足")
                else:
                    analysis['macd_signal'] = '死叉/空头'
                    if hist < 0:
                        interpretations.append("🔴 MACD死叉且绿柱放大，下跌动能强")
                    else:
                        interpretations.append("🟡 MACD死叉但跌势趋缓")
        
        # RSI 状态
        if 'RSI' in df.columns:
            rsi = latest['RSI']
            if pd.notna(rsi):
                if rsi > 70:
                    analysis['rsi_status'] = '超买区'
                    interpretations.append(f"⚠️ RSI={rsi:.0f}，进入超买区，注意回调风险")
                elif rsi < 30:
                    analysis['rsi_status'] = '超卖区'
                    interpretations.append(f"💡 RSI={rsi:.0f}，进入超卖区，可能存在反弹机会")
                else:
                    analysis['rsi_status'] = '中性'
                analysis['rsi_value'] = round(rsi, 1)
        
        # 布林带位置
        if 'BOLL_UP' in df.columns and 'BOLL_DOWN' in df.columns:
            close = latest['close']
            boll_up = latest['BOLL_UP']
            boll_down = latest['BOLL_DOWN']
            boll_mid = latest.get('BOLL_MID', (boll_up + boll_down) / 2)
            
            if pd.notna(boll_up) and pd.notna(boll_down):
                if close > boll_up:
                    interpretations.append("🔺 价格突破布林上轨，超买状态")
                elif close < boll_down:
                    interpretations.append("🔻 价格跌破布林下轨，超卖状态")
                elif close > boll_mid:
                    interpretations.append("📊 价格位于布林带上半区")
                else:
                    interpretations.append("📊 价格位于布林带下半区")
        
        # 生成综合解读
        analysis['interpretation'] = " | ".join(interpretations[:3]) if interpretations else "暂无明显信号"
        analysis['interpretations'] = interpretations
    
    return fig, analysis


def plot_interactive_trend(
    df: pd.DataFrame,
    date_col: Optional[str] = 'trade_date',
    inst_col: str = 'institutional_net',
    retail_col: str = 'retail_net',
    total_col: str = 'net_amount',
    title: str = "资金流向趋势"
) -> go.Figure:
    """
    交互式资金趋势图 (Plotly)
    """
    if df.empty:
        return None

    # 确定日期来源
    if date_col and date_col in df.columns:
        dates = pd.to_datetime(df[date_col])
    else:
        dates = pd.to_datetime(df.index)
        
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 检查是否有机构/散户明细
    has_breakdown = (inst_col in df.columns and df[inst_col].abs().sum() > 0)
    
    if has_breakdown:
        # 机构
        fig.add_trace(go.Bar(
            x=dates,
            y=df[inst_col]/1e8,
            name="机构净额",
            marker_color=Colors.INSTITUTIONAL
        ))
        # 散户
        fig.add_trace(go.Bar(
            x=dates,
            y=df[retail_col]/1e8,
            name="散户净额",
            marker_color=Colors.RETAIL
        ))
    else:
        # 总额
        colors = [Colors.RISE if v > 0 else Colors.FALL for v in df[total_col]]
        fig.add_trace(go.Bar(
            x=dates,
            y=df[total_col]/1e8,
            name="净流入",
            marker_color=colors
        ))
        
    # 添加收盘价曲线 (如果有)
    if 'close' in df.columns:
        fig.add_trace(go.Scatter(
            x=dates,
            y=df['close'],
            name="收盘价",
            mode='lines+markers',
            marker=dict(size=4),
            line=dict(color=Colors.WARNING, width=2)
        ), secondary_y=True)
        
    fig.update_layout(
        title=title,
        xaxis_title="日期",
        yaxis_title="净流入 (亿元)",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=50, b=50),
        height=400
    )
    fig.update_yaxes(title_text="股价 (元)", secondary_y=True, showgrid=False)
    
    return fig


# ==================== 高级组合组件 ====================

def render_stock_detail_card(
    symbol: str,
    name: str,
    start_str: str,
    end_str: str,
    key_prefix: str = ""
):
    """
    渲染个股详情分析卡片 (可复用组件)
    
    包含三个维度 Tab:
    - 💸 资金流向: 机构/散户净流入、趋势图
    - 📉 技术形态: K线+均线、MACD、RSI、智能解读
    - 💰 估值分析: (预留)
    
    Args:
        symbol: 股票代码 (如 600519.SH)
        name: 股票名称 (如 贵州茅台)
        start_str: 开始日期 YYYYMMDD
        end_str: 结束日期 YYYYMMDD
        key_prefix: Streamlit widget key 前缀 (防止重复)
    """
    import streamlit as st
    from datetime import datetime, timedelta
    
    # 延迟导入避免循环引用
    from web.data_service import get_stock_money_flow, get_stock_technical_data

    # 检测是否为港股
    is_hk_stock = symbol.endswith('.HK')

    dim_tabs = st.tabs(["💸 资金流向", "📉 技术形态", "💰 估值分析", "🤖 AI 分析师"])

    # ---------- 资金流向维度 ----------
    with dim_tabs[0]:
        if is_hk_stock:
            # 港股不支持资金流向分析
            st.info("⚠️ **港股暂不支持资金流向分析**\n\nTushare 资金流向接口仅支持 A 股（沪深交易所）。")
        else:
            flow_res = get_stock_money_flow(symbol, start_str, end_str)
            if 'error' not in flow_res:
                # Metrics
                col1, col2, col3 = st.columns(3)
                inst = flow_res.get('institutional', {})
                retail = flow_res.get('retail', {})
                col1.metric("机构净流入", f"{inst.get('total_net_flow', 0)/1e8:+.2f} 亿")
                col2.metric("散户净流入", f"{retail.get('total_net_flow', 0)/1e8:+.2f} 亿")
                col3.metric("机构流入天数", f"{inst.get('net_inflow_days', 0)} / {flow_res.get('total_days', 0)}")

                # 趋势图
                if 'flow_data' in flow_res and not flow_res['flow_data'].empty:
                    import pandas as pd
                    flow_df = flow_res['flow_data'].copy()
                    flow_df.index = pd.to_datetime(flow_df.index)
                    
                    # 优先尝试交互式图表
                    try:
                        # 尝试添加股价数据以增强展示
                        from web.data_service import get_stock_price
                        price_df = get_stock_price(symbol, start_str, end_str)
                        if not price_df.empty:
                            # 确保索引类型一致
                            price_df.index = pd.to_datetime(price_df.index)
                            common_idx = flow_df.index.intersection(price_df.index)
                            flow_df.loc[common_idx, 'close'] = price_df.loc[common_idx, 'close']
                        
                        fig = plot_interactive_trend(
                            flow_df, date_col=None,
                            inst_col='institutional_net', retail_col='retail_net',
                            title=f"{name} 资金流向趋势"
                        )
                        st.plotly_chart(fig, use_container_width=True)
                        
                    except Exception as e:
                        # 降级回 Matplotlib
                        st.warning(f"交互图表加载失败，使用静态图表: {e}")
                        fig, summary_text = plot_trend_chart(
                            flow_df, date_col=None,
                            inst_col='institutional_net', retail_col='retail_net'
                        )
                        if fig:
                            st.pyplot(fig)
                            st.caption(summary_text)
                            plt.close(fig)
                else:
                    st.info("暂无时序数据")
            else:
                st.warning("暂无资金数据")
    
    # ---------- 技术形态维度 ----------
    with dim_tabs[1]:
        tech_start = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
        tech_end = datetime.now().strftime('%Y%m%d')
        
        with st.spinner("正在加载技术数据..."):
            tech_df = get_stock_technical_data(symbol, tech_start, tech_end)
        
        if tech_df is not None and not tech_df.empty:
            # 显示选项
            col_opt1, col_opt2 = st.columns(2)
            show_vol = col_opt1.checkbox("显示成交量", value=True, key=f"{key_prefix}vol_{symbol}")
            show_rsi = col_opt2.checkbox("显示RSI", value=False, key=f"{key_prefix}rsi_{symbol}")
            
            # 绘制技术图表
            fig, analysis = plot_technical_chart(
                tech_df, 
                symbol=name, 
                show_volume=show_vol,
                show_macd=True,
                show_rsi=show_rsi
            )
            
            if fig:
                st.pyplot(fig)
                plt.close(fig)
            
            # 显示分析结论
            st.divider()
            st.markdown("#### 📊 技术信号")
            
            sig_cols = st.columns(4)
            
            if 'latest_close' in analysis:
                sig_cols[0].metric("最新收盘", f"¥{analysis['latest_close']:.2f}")
            
            if 'ma_trend' in analysis:
                trend = analysis['ma_trend']
                color = "🟢" if "多头" in trend else "🔴"
                sig_cols[1].metric("均线趋势", f"{color} {trend}")
            
            if 'macd_signal' in analysis:
                signal = analysis['macd_signal']
                color = "🟢" if "金叉" in signal else "🔴"
                sig_cols[2].metric("MACD", f"{color} {signal}")
            
            if 'rsi_value' in analysis:
                rsi_val = analysis['rsi_value']
                status = analysis.get('rsi_status', '')
                if rsi_val > 70:
                    color = "🔴"
                elif rsi_val < 30:
                    color = "🟢"
                else:
                    color = "⚪"
                sig_cols[3].metric("RSI", f"{color} {rsi_val} ({status})")
            
            # 显示智能解读
            if 'interpretations' in analysis and analysis['interpretations']:
                st.markdown("#### 🤖 智能解读")
                for interp in analysis['interpretations']:
                    st.markdown(f"- {interp}")
        else:
            st.warning("暂无技术数据")
    
    # ---------- 估值分析维度 ----------
    with dim_tabs[2]:
        if is_hk_stock:
            # 港股不支持估值分析
            st.info("⚠️ **港股暂不支持估值分析**\n\nTushare daily_basic 接口仅支持 A 股（沪深交易所）。")
        else:
            from web.data_service import get_stock_valuation

            with st.spinner("正在加载估值数据..."):
                val_data = get_stock_valuation(symbol, days=250)

            if 'error' in val_data:
                st.warning(f"暂无估值数据: {val_data['error']}")
            else:
                latest = val_data['latest']
                percentile = val_data['percentile']
                status = val_data['status']

                # 核心估值指标
                st.markdown("#### 💹 核心估值指标")

                val_cols = st.columns(4)

                # PE-TTM
                pe_ttm = latest.get('pe_ttm')
                pe_pct = percentile.get('pe_ttm')
                pe_status = status.get('pe_ttm', '-')
                if pe_ttm and pd.notna(pe_ttm):
                    val_cols[0].metric(
                        "PE (TTM)",
                        f"{pe_ttm:.1f}",
                        delta=f"分位: {pe_pct:.0f}%" if pe_pct else None,
                        delta_color="inverse"  # 分位越低越好
                    )
                    val_cols[0].caption(f"状态: {pe_status}")
                else:
                    val_cols[0].metric("PE (TTM)", "N/A (亏损)")

                # PB
                pb = latest.get('pb')
                pb_pct = percentile.get('pb')
                pb_status = status.get('pb', '-')
                if pb and pd.notna(pb):
                    val_cols[1].metric(
                        "PB",
                        f"{pb:.2f}",
                        delta=f"分位: {pb_pct:.0f}%" if pb_pct else None,
                        delta_color="inverse"
                    )
                    val_cols[1].caption(f"状态: {pb_status}")
                else:
                    val_cols[1].metric("PB", "N/A")

                # PS-TTM
                ps_ttm = latest.get('ps_ttm')
                ps_pct = percentile.get('ps_ttm')
                ps_status = status.get('ps_ttm', '-')
                if ps_ttm and pd.notna(ps_ttm):
                    val_cols[2].metric(
                        "PS (TTM)",
                        f"{ps_ttm:.2f}",
                        delta=f"分位: {ps_pct:.0f}%" if ps_pct else None,
                        delta_color="inverse"
                    )
                    val_cols[2].caption(f"状态: {ps_status}")
                else:
                    val_cols[2].metric("PS (TTM)", "N/A")

                # 股息率
                dv_ratio = latest.get('dv_ratio')
                if dv_ratio and pd.notna(dv_ratio):
                    val_cols[3].metric("股息率", f"{dv_ratio:.2f}%")
                else:
                    val_cols[3].metric("股息率", "N/A")

                # 市值信息
                st.divider()
                st.markdown("#### 📊 市值信息")

                mv_cols = st.columns(3)
                total_mv = latest.get('total_mv')
                circ_mv = latest.get('circ_mv')

                if total_mv and pd.notna(total_mv):
                    mv_cols[0].metric("总市值", f"{total_mv/10000:.0f} 亿")
                if circ_mv and pd.notna(circ_mv):
                    mv_cols[1].metric("流通市值", f"{circ_mv/10000:.0f} 亿")

                mv_cols[2].metric("数据天数", f"{val_data.get('data_days', 0)} 日")

                # 估值分位图
                st.divider()
                st.markdown("#### 📈 历史估值分位")

                if percentile:
                    # 绘制分位条形图
                    pct_df = pd.DataFrame([
                        {'指标': 'PE-TTM', '分位': percentile.get('pe_ttm', 50), '状态': status.get('pe_ttm', '-')},
                        {'指标': 'PB', '分位': percentile.get('pb', 50), '状态': status.get('pb', '-')},
                        {'指标': 'PS-TTM', '分位': percentile.get('ps_ttm', 50), '状态': status.get('ps_ttm', '-')},
                    ])
                    pct_df = pct_df.dropna(subset=['分位'])

                    if not pct_df.empty:
                        fig, ax = plt.subplots(figsize=(8, 2.5))

                        colors = []
                        for pct in pct_df['分位']:
                            if pct < 20:
                                colors.append(Colors.FALL)  # 低估-绿 (便宜)
                            elif pct < 40:
                                colors.append('#82e0aa')
                            elif pct < 60:
                                colors.append('#f4d03f')  # 中性-黄
                            elif pct < 80:
                                colors.append('#e59866')
                            else:
                                colors.append(Colors.RISE)  # 高估-红 (贵)

                        ax.barh(pct_df['指标'], pct_df['分位'], color=colors, alpha=0.8)
                        ax.set_xlim(0, 100)
                        ax.set_xlabel('历史分位 (%)')
                        ax.axvline(x=50, color='gray', linestyle='--', alpha=0.5)

                        # 添加数值标签
                        for i, (idx, row) in enumerate(pct_df.iterrows()):
                            ax.text(row['分位'] + 2, i, f"{row['分位']:.0f}% ({row['状态']})",
                                    va='center', fontsize=9)

                        ax.set_title(f"估值分位 (近{val_data.get('data_days', 250)}日)")
                        plt.tight_layout()
                        st.pyplot(fig)
                        plt.close(fig)

                        # 解读
                        st.markdown("#### 🤖 估值解读")
                        interpretations = []

                        avg_pct = sum(percentile.values()) / len(percentile) if percentile else 50

                        if avg_pct < 30:
                            interpretations.append("🟢 **综合估值偏低**，可能具有较好的安全边际")
                        elif avg_pct < 50:
                            interpretations.append("🟡 **综合估值中性偏低**，估值较为合理")
                        elif avg_pct < 70:
                            interpretations.append("🟡 **综合估值中性偏高**，注意估值风险")
                        else:
                            interpretations.append("🔴 **综合估值偏高**，需警惕估值泡沫")

                        # 单项解读
                        if 'pe_ttm' in status and status['pe_ttm'] in ['低估', '偏低']:
                            interpretations.append(f"💡 PE处于历史{percentile.get('pe_ttm', 0):.0f}%分位，盈利估值较低")
                        if 'pb' in status and status['pb'] in ['低估', '偏低']:
                            interpretations.append(f"💡 PB处于历史{percentile.get('pb', 0):.0f}%分位，资产估值较低")

                        for interp in interpretations:
                            st.markdown(f"- {interp}")
                else:
                    st.info("分位数据不足（需要至少10个交易日数据）")

    # ---------- AI 分析师维度 ----------
    with dim_tabs[3]:
        render_stock_chat(symbol, name, start_str, end_str, key_prefix)


def render_stock_chat(
    symbol: str,
    name: str,
    start_str: str,
    end_str: str,
    key_prefix: str = ""
):
    """
    渲染个股 AI 对话组件

    Args:
        symbol: 股票代码
        name: 股票名称
        start_str: 开始日期
        end_str: 结束日期
        key_prefix: widget key 前缀
    """
    import streamlit as st
    from datetime import datetime, timedelta

    # 初始化 session state
    chat_key = f"{key_prefix}chat_{symbol}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = {
            "messages": [],
            "context_built": False,
            "stock_context": None
        }

    chat_state = st.session_state[chat_key]

    # 标题栏 + 清空按钮
    col_title, col_clear = st.columns([4, 1])
    with col_title:
        st.markdown("#### 🤖 AI 股票分析师")
        st.caption(f"基于 {name} ({symbol}) 的多维度分析数据进行智能对话")
    
    with col_clear:
        if chat_state["messages"]:
            if st.button("🗑️ 清空", key=f"{chat_key}_clear", help="清空当前对话历史"):
                chat_state["messages"] = []
                st.rerun()

    # 检查 LLM 服务配置
    from web.stock_chat_service import (
        StockChatService, StockContext, build_stock_context, ChatMessage
    )

    # 创建服务实例
    service = StockChatService()

    # 构建/更新股票上下文
    if not chat_state["context_built"]:
        with st.spinner("正在构建分析上下文..."):
            try:
                from web.data_service import (
                    get_stock_money_flow, get_stock_technical_data, get_stock_valuation
                )

                # 获取各维度数据
                flow_data = get_stock_money_flow(symbol, start_str, end_str)

                tech_start = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
                tech_end = datetime.now().strftime('%Y%m%d')
                tech_df = get_stock_technical_data(symbol, tech_start, tech_end)

                # 从技术图表获取分析结果
                tech_analysis = {}
                if tech_df is not None and not tech_df.empty:
                    _, tech_analysis = plot_technical_chart(tech_df, symbol=name)

                valuation_data = get_stock_valuation(symbol, days=250)

                # 构建上下文
                stock_context = build_stock_context(
                    symbol=symbol,
                    name=name,
                    flow_data=flow_data,
                    tech_analysis=tech_analysis,
                    valuation_data=valuation_data
                )

                chat_state["stock_context"] = stock_context
                chat_state["context_built"] = True

            except Exception as e:
                st.error(f"构建上下文失败: {e}")
                return

    # 显示上下文摘要
    if chat_state["stock_context"]:
        ctx = chat_state["stock_context"]
        with st.expander("📊 已加载的分析数据", expanded=False):
            st.markdown(ctx.to_context_string())

    # 显示历史消息
    for msg in chat_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 处理新消息生成 (Pending State)
    if "pending_prompt" in chat_state and chat_state["pending_prompt"]:
        user_input = chat_state.pop("pending_prompt")
        
        # 显示用户刚才的提问
        with st.chat_message("user"):
            st.markdown(user_input)
        
        # 记录用户消息
        chat_state["messages"].append({"role": "user", "content": user_input})

        # 生成 AI 回复
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""

            try:
                # 构建历史消息 (不包含刚追加的这一条 user message，因为 service 可能会处理)
                # 注意：history 参数取决于 service.chat_stream 的预期。
                # 通常我们传给 LLM 的是之前的历史。
                history = [
                    ChatMessage(role=m["role"], content=m["content"])
                    for m in chat_state["messages"][:-1]
                ]

                # 流式输出
                for chunk in service.chat_stream(
                    message=user_input,
                    context=chat_state["stock_context"],
                    history=history
                ):
                    full_response += chunk
                    message_placeholder.markdown(full_response + "▌")

                message_placeholder.markdown(full_response)
                chat_state["messages"].append({"role": "assistant", "content": full_response})

            except Exception as e:
                error_msg = f"对话失败: {str(e)}"
                st.error(error_msg)
                chat_state["messages"].append({"role": "assistant", "content": error_msg})
        
        # 生成完毕，刷新页面以显示完整历史并重置输入框
        st.rerun()

    # 预设问题 (仅在无历史且无 pending 时显示)
    if not chat_state["messages"] and "pending_prompt" not in chat_state:
        st.markdown("##### 💡 你可以问我：")
        preset_questions = [
            "这只股票目前的技术形态如何？",
            "资金流向反映了什么信息？",
            "从估值角度看，现在贵不贵？",
            "综合分析一下这只股票的投资价值",
        ]
        cols = st.columns(2)
        for i, q in enumerate(preset_questions):
            if cols[i % 2].button(q, key=f"{chat_key}_preset_{i}", use_container_width=True):
                chat_state["pending_prompt"] = q
                st.rerun()

    # 输入框 (始终显示在底部)
    # 注意：在 Tab 中使用 st.chat_input 可能会退化为内联显示，
    # 但通过上述 Rerun 逻辑，我们可以保证它始终在历史消息下方。
    if prompt := st.chat_input("输入你的问题...", key=f"{chat_key}_chat_input"):
        chat_state["pending_prompt"] = prompt
        st.rerun()

