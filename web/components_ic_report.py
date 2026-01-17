"""
Investment Committee (IC) Report Components - 投资决策委员会报告 UI 组件

提供可复用的投委会报告渲染组件，包括：
- 综合评分仪表盘
- 一句话穿透卡片
- 五维专家 Tab 面板
- 压力测试交互滑块
- 评级触发条件列表
- 信息黑箱提示
"""

import streamlit as st
from typing import Optional, Dict, Any
from web.ic_report_service import ICReport, get_ic_service, ExpertOpinion


def _inject_ic_css():
    """注入投委会报告专属 CSS"""
    st.markdown("""
    <style>
    /* ====== IC Report 顶层容器 ====== */
    .ic-report-container {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 16px;
        padding: 20px;
        color: #e2e8f0;
    }
    
    /* ====== 评分仪表盘 ====== */
    .ic-score-gauge {
        position: relative;
        width: 120px;
        height: 120px;
        margin: 0 auto;
    }
    
    .ic-score-circle {
        width: 100%;
        height: 100%;
        border-radius: 50%;
        background: conic-gradient(
            from 135deg,
            #ef4444 0%,
            #f97316 25%,
            #eab308 50%,
            #22c55e 75%,
            #22c55e 100%
        );
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    .ic-score-inner {
        width: 85%;
        height: 85%;
        border-radius: 50%;
        background: #1a1a2e;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }
    
    .ic-score-value {
        font-size: 2.5rem;
        font-weight: 800;
        color: #f8fafc;
        line-height: 1;
    }
    
    .ic-score-max {
        font-size: 0.95rem;
        font-weight: 600;
        color: #94a3b8;
    }
    
    /* ====== 评级标签 ====== */
    .ic-rating-badge {
        display: inline-block;
        padding: 6px 16px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 0.95rem;
        margin-top: 12px;
    }
    
    .ic-rating-badge.too-hard {
        background: linear-gradient(135deg, #dc2626, #b91c1c);
        color: white;
    }
    
    .ic-rating-badge.watch {
        background: linear-gradient(135deg, #f59e0b, #d97706);
        color: white;
    }
    
    .ic-rating-badge.hold {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white;
    }
    
    .ic-rating-badge.buy {
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
    }
    
    /* ====== 一句话穿透 ====== */
    .ic-insight-card {
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.1), rgba(251, 191, 36, 0.05));
        border-left: 5px solid #d97706;
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0;
        box-shadow: 0 4px 12px rgba(217, 119, 6, 0.08);
    }
    
    .ic-insight-label {
        font-size: 0.9rem;
        color: #475569;
        margin-bottom: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    .ic-insight-text {
        font-size: 1.25rem;
        font-weight: 800;
        color: #92400e;
        line-height: 1.6;
    }
    
    .ic-insight-highlight {
        color: #f97316;
        font-weight: 700;
    }
    
    /* ====== 风险/博弈点卡片 ====== */
    .ic-risk-card {
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.3);
        border-radius: 8px;
        padding: 12px 16px;
    }
    
    .ic-debate-card {
        background: rgba(99, 102, 241, 0.1);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 8px;
        padding: 12px 16px;
    }
    
    .ic-card-title {
        font-size: 0.95rem;
        font-weight: 800;
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 10px;
        color: #1e293b;
    }
    
    .ic-card-content {
        font-size: 1rem;
        color: #334155;
        line-height: 1.6;
        font-weight: 500;
    }
    
    /* ====== 专家 Tab ====== */
    .ic-expert-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
    }
    
    .ic-expert-icon {
        font-size: 1.5rem;
    }
    
    .ic-expert-name {
        font-size: 1.2rem;
        font-weight: 800;
        color: #0f172a;
    }
    
    .ic-expert-focus {
        font-size: 0.9rem;
        color: #475569;
        font-weight: 600;
        background: #f1f5f9;
        padding: 2px 8px;
        border-radius: 4px;
    }
    
    .ic-expert-point {
        padding: 12px 0;
        padding-left: 24px;
        border-left: 3px solid #6366f1;
        margin: 12px 0;
        color: #1e293b;
        font-size: 1.05rem;
        font-weight: 500;
        background: rgba(99, 102, 241, 0.05);
        border-radius: 0 8px 8px 0;
    }
    
    .ic-expert-point::before {
        content: "✦";
        color: #6366f1;
        font-weight: 900;
        margin-right: 12px;
        margin-left: -16px;
    }
    
    /* ====== 压力测试结果 ====== */
    .ic-stress-result {
        background: rgba(30, 41, 59, 0.8);
        border: 1px solid rgba(71, 85, 105, 0.5);
        border-radius: 12px;
        padding: 16px;
    }
    
    .ic-stress-metric {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 0;
        border-bottom: 1px solid rgba(71, 85, 105, 0.3);
    }
    
    .ic-stress-metric:last-child {
        border-bottom: none;
    }
    
    .ic-stress-label {
        color: #334155;
        font-size: 0.95rem;
        font-weight: 600;
    }
    
    .ic-stress-value {
        font-weight: 700;
        font-size: 1rem;
    }
    
    .ic-stress-value.safe { color: #10b981; }
    .ic-stress-value.neutral { color: #f59e0b; }
    .ic-stress-value.danger { color: #ef4444; }
    
    .ic-stress-conclusion {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.08), rgba(168, 85, 247, 0.05));
        border-radius: 12px;
        padding: 16px;
        margin-top: 12px;
        font-size: 1rem;
        color: #312e81;
        line-height: 1.7;
        font-weight: 500;
        border: 1px solid rgba(99, 102, 241, 0.15);
    }
    
    /* ====== 触发条件 ====== */
    .ic-trigger-item {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 10px 0;
        border-bottom: 1px solid rgba(71, 85, 105, 0.3);
    }
    
    .ic-trigger-icon {
        font-size: 1rem;
        flex-shrink: 0;
    }
    
    .ic-trigger-icon.up { color: #10b981; }
    .ic-trigger-icon.down { color: #ef4444; }
    
    .ic-trigger-text {
        font-size: 1rem;
        color: #1e293b;
        font-weight: 500;
    }
    
    .ic-trigger-target {
        font-weight: 800;
        color: #d97706;
    }
    
    /* ====== 信息黑箱 ====== */
    .ic-blackbox {
        background: rgba(30, 41, 59, 0.6);
        border: 1px dashed rgba(71, 85, 105, 0.5);
        border-radius: 8px;
        padding: 16px;
    }
    
    .ic-blackbox-title {
        font-size: 1rem;
        font-weight: 800;
        color: #1e293b;
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .ic-blackbox-item {
        padding: 8px 0;
        padding-left: 20px;
        color: #475569;
        font-size: 0.95rem;
        font-weight: 500;
        position: relative;
    }
    
    .ic-blackbox-item::before {
        content: "▫";
        position: absolute;
        left: 0;
        color: #64748b;
        font-weight: 800;
    }
    </style>
    """, unsafe_allow_html=True)


def render_score_gauge(score: float, rating: str, rating_subtitle: str = ""):
    """渲染评分仪表盘"""
    # 确定评级样式
    if "太难" in rating or "Too Hard" in rating:
        badge_class = "too-hard"
    elif "观望" in rating:
        badge_class = "watch"
    elif "持有" in rating:
        badge_class = "hold"
    else:
        badge_class = "buy"
    
    st.markdown(f"""
    <div style="text-align: center;">
        <div class="ic-score-gauge">
            <div class="ic-score-circle">
                <div class="ic-score-inner">
                    <span class="ic-score-value">{score}</span>
                    <span class="ic-score-max">/ 10</span>
                </div>
            </div>
        </div>
        <div class="ic-rating-badge {badge_class}">{rating}</div>
        <p style="color: #475569; font-size: 0.95rem; margin-top: 10px; font-weight: 600;">{rating_subtitle}</p>
    </div>
    """, unsafe_allow_html=True)


def render_penetrating_insight(insight: str):
    """渲染一句话穿透"""
    st.markdown(f"""
    <div class="ic-insight-card">
        <div class="ic-insight-label">💡 一句话身份穿透</div>
        <div class="ic-insight-text">{insight}</div>
    </div>
    """, unsafe_allow_html=True)


def render_risk_and_debate(risks: list, debate: str = ""):
    """渲染风险和核心博弈点"""
    # 风险列表项生成
    risks_html = "".join([f"<li>{r}</li>" for r in risks[:3]])
    
    # 渲染主要风险 (占满宽度)
    st.markdown(f"""
    <div class="ic-risk-card" style="margin-top: 12px; margin-bottom: 12px;">
        <div class="ic-card-title">⚠️ 主要风险</div>
        <ul class="ic-card-content" style="padding-left: 16px; margin: 0;">
            {risks_html}
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # 如果有博弈点，渲染博弈点
    if debate:
        st.markdown(f"""
        <div class="ic-debate-card" style="margin-bottom: 12px;">
            <div class="ic-card-title">🎯 核心博弈点</div>
            <div class="ic-card-content">{debate}</div>
        </div>
        """, unsafe_allow_html=True)


def render_expert_panel(opinions: Dict[str, ExpertOpinion], key_prefix: str = ""):
    """渲染五维专家面板"""
    expert_ids = ["munger", "industry", "quant", "cycle", "risk"]
    expert_names = ["🧠 查理·芒格", "🔬 产业专家", "📊 冷血审计", "🔄 资本周期", "⚠️ 风控经理"]
    
    tabs = st.tabs(expert_names)
    
    for i, expert_id in enumerate(expert_ids):
        with tabs[i]:
            opinion = opinions.get(expert_id)
            if opinion:
                # 专家标题
                st.markdown(f"""
                <div class="ic-expert-header">
                    <span class="ic-expert-icon">{opinion.expert_icon}</span>
                    <div>
                        <div class="ic-expert-name">{opinion.expert_name} ({opinion.focus_area})</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # 核心观点
                for point in opinion.key_points:
                    st.markdown(f'<div class="ic-expert-point">{point}</div>', unsafe_allow_html=True)
            else:
                st.info("暂无此专家的分析意见")


def render_stress_test(report: ICReport, key_prefix: str = ""):
    """渲染压力测试面板"""
    st.markdown("### 🧪 资金风控压力测试")
    st.caption("假设宏观环境变化，调整下方核心变量，查看对公司估值逻辑的打击程度。")
    
    # 创建场景滑块
    scenario_values = {}
    cols = st.columns(len(report.stress_test_scenarios))
    
    for i, scenario in enumerate(report.stress_test_scenarios):
        with cols[i]:
            value = st.slider(
                f"{scenario.name} ({scenario.unit})",
                min_value=int(scenario.min_value),
                max_value=int(scenario.max_value),
                value=int(scenario.current_value),
                key=f"{key_prefix}stress_{scenario.variable}"
            )
            scenario_values[scenario.variable] = value
    
    # 计算压力测试结果
    service = get_ic_service()
    result = service.calculate_stress_test(report, scenario_values)
    
    # 显示结果
    st.markdown("---")
    
    col_result, col_conclusion = st.columns([1, 1])
    
    with col_result:
        st.markdown("**模拟推演结果**")
        
        # 产能利用率
        cap_color = "safe" if result["capacity_utilization"] > 70 else ("neutral" if result["capacity_utilization"] > 50 else "danger")
        st.markdown(f"""
        <div class="ic-stress-result">
            <div class="ic-stress-metric">
                <span class="ic-stress-label">产能利用率预估</span>
                <span class="ic-stress-value {cap_color}">{result['capacity_utilization']}%</span>
            </div>
            <div class="ic-stress-metric">
                <span class="ic-stress-label">净利润修正 (Net Margin)</span>
                <span class="ic-stress-value {'safe' if result['net_margin'] > 3 else 'neutral' if result['net_margin'] > 0 else 'danger'}">{result['net_margin']}%</span>
            </div>
            <div class="ic-stress-metric">
                <span class="ic-stress-label">库存周转风险</span>
                <span class="ic-stress-value {result['inventory_risk_level']}">{result['inventory_risk']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_conclusion:
        st.markdown("**投资委员会结论**")
        st.markdown(f"""
        <div class="ic-stress-conclusion">
            {result['conclusion']}
        </div>
        """, unsafe_allow_html=True)


def render_rating_triggers(triggers: list):
    """渲染评级触发条件"""
    st.markdown("### ⚡ 评级调整触发条件 (Triggers)")
    
    for trigger in triggers:
        icon_class = "up" if trigger.direction == "upgrade" else "down"
        icon = "↑" if trigger.direction == "upgrade" else "↓"
        action = "上调" if trigger.direction == "upgrade" else "下调"
        
        st.markdown(f"""
        <div class="ic-trigger-item">
            <span class="ic-trigger-icon {icon_class}">{icon}</span>
            <div class="ic-trigger-text">
                <span class="ic-trigger-target">{action}至"{trigger.target_rating}"</span>：{trigger.condition}
            </div>
        </div>
        """, unsafe_allow_html=True)


def render_missing_data(missing: list):
    """渲染信息黑箱"""
    st.markdown("### ⬛ 信息黑箱 (Missing Data)")
    st.caption("以下关键数据缺失，需在此清单补全前保持谨慎：")
    
    items_html = "".join([f'<div class="ic-blackbox-item">{item}</div>' for item in missing])
    st.markdown(f"""
    <div class="ic-blackbox">
        {items_html}
    </div>
    """, unsafe_allow_html=True)


def render_investment_committee_tab(
    symbol: str,
    name: str,
    flow_data: Optional[Dict] = None,
    tech_data: Optional[Dict] = None,
    valuation_data: Optional[Dict] = None,
    key_prefix: str = ""
):
    """
    渲染投资决策委员会完整 Tab 内容
    
    这是个股卡片中 "🧠 AI投委会" Tab 的主入口函数。
    
    Args:
        symbol: 股票代码
        name: 股票名称
        flow_data: 资金流向数据（可选，从 data_service 获取）
        tech_data: 技术分析数据（可选）
        valuation_data: 估值数据（可选）
        key_prefix: Streamlit widget key 前缀
    """
    _inject_ic_css()
    
    # 生成报告
    service = get_ic_service()
    with st.spinner("正在生成投资决策委员会报告..."):
        report = service.generate_report(
            symbol=symbol,
            name=name,
            flow_data=flow_data,
            tech_data=tech_data,
            valuation_data=valuation_data,
            use_ai=False  # 先使用规则版本，后续可开启 AI
        )
    
    # ====== 顶部：评分 + 一句话穿透 ======
    col_score, col_insight = st.columns([1, 2])
    
    with col_score:
        render_score_gauge(report.overall_score, report.rating, report.rating_subtitle)
    
    with col_insight:
        render_penetrating_insight(report.penetrating_insight)
        render_risk_and_debate(report.main_risks, report.core_debate)
    
    st.divider()
    
    # ====== 中部：五维专家辩论 ======
    st.markdown("### 🎭 五维辩论现场")
    st.caption("点击下方不同的「大脑」标签，切换查看各位专家的深度剖析。每个人物代表一种特定的投资哲学。")
    render_expert_panel(report.expert_opinions, key_prefix)
    
    st.divider()
    
    # ====== 下部：压力测试 ======
    render_stress_test(report, key_prefix)
    
    st.divider()
    
    # ====== 底部：触发条件 + 信息黑箱 ======
    col_triggers, col_blackbox = st.columns(2)
    
    with col_triggers:
        render_rating_triggers(report.rating_triggers)
    
    with col_blackbox:
        render_missing_data(report.missing_data)
    
    # ====== 页脚：数据更新时间 ======
    st.caption(f"📅 数据更新: {report.generated_at.strftime('%Y.%m.%d %H:%M')}")
