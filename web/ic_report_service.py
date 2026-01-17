"""
Investment Committee (IC) Report Service - 投资决策委员会报告服务

生成多视角深度分析报告，包括：
- 5维专家视角分析（查理芒格、产业专家、量化审计、资本周期、风控经理）
- 综合评分与评级
- 一句话身份穿透
- 压力测试模拟
- 评级触发条件
- 信息黑箱提示
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


# ==================== 数据模型 ====================

@dataclass
class ExpertOpinion:
    """单个专家视角的分析结果"""
    expert_id: str  # munger, industry, quant, cycle, risk
    expert_name: str  # 查理·芒格, 产业专家, etc.
    expert_icon: str  # 🧠, 🔬, 📊, 🔄, ⚠️
    focus_area: str  # 商业模式, 行业趋势, etc.
    key_points: List[str] = field(default_factory=list)  # 核心观点要点
    rating: float = 5.0  # 1-10 评分
    stance: str = "neutral"  # bullish, bearish, neutral
    summary: str = ""  # 简短总结


@dataclass
class StressTestScenario:
    """压力测试场景"""
    name: str  # 场景名称
    variable: str  # 变量名
    current_value: float  # 当前值
    min_value: float  # 最小值
    max_value: float  # 最大值
    unit: str = "%"  # 单位


@dataclass
class RatingTrigger:
    """评级调整触发条件"""
    direction: str  # upgrade, downgrade
    target_rating: str  # 买入, 持有, 卖出
    condition: str  # 触发条件描述
    data_source: str = ""  # 数据来源


@dataclass
class ICReport:
    """投资决策委员会完整报告"""
    symbol: str
    name: str
    generated_at: datetime = field(default_factory=datetime.now)
    
    # 核心评级
    overall_score: float = 5.0  # 1-10
    rating: str = "观望"  # 太难了/观望/周期反弹卖出/持有/买入
    rating_subtitle: str = ""  # 建议说明
    
    # 一句话穿透
    penetrating_insight: str = ""
    
    # 核心博弈点
    core_debate: str = ""
    
    # 主要风险
    main_risks: List[str] = field(default_factory=list)
    
    # 五维专家意见
    expert_opinions: Dict[str, ExpertOpinion] = field(default_factory=dict)
    
    # 压力测试
    stress_test_scenarios: List[StressTestScenario] = field(default_factory=list)
    stress_test_result: Dict[str, Any] = field(default_factory=dict)
    
    # 触发条件
    rating_triggers: List[RatingTrigger] = field(default_factory=list)
    
    # 信息黑箱
    missing_data: List[str] = field(default_factory=list)
    
    # 原始数据（用于压力测试计算）
    raw_data: Dict[str, Any] = field(default_factory=dict)


# ==================== 专家定义 ====================

EXPERTS = {
    "munger": {
        "name": "查理·芒格",
        "icon": "🧠",
        "focus": "商业模式",
        "prompt_focus": "护城河、竞争优势、商业模式可持续性、管理层能力"
    },
    "industry": {
        "name": "产业专家",
        "icon": "🔬",
        "focus": "行业趋势",
        "prompt_focus": "行业技术变革、产业链地位、市场空间、竞争格局变化"
    },
    "quant": {
        "name": "冷血审计",
        "icon": "📊",
        "focus": "财务质量",
        "prompt_focus": "财务指标异常、盈利质量、现金流状况、会计政策风险"
    },
    "cycle": {
        "name": "资本周期",
        "icon": "🔄",
        "focus": "周期定位",
        "prompt_focus": "行业周期阶段、产能利用率、资本开支周期、估值历史分位"
    },
    "risk": {
        "name": "风控经理",
        "icon": "⚠️",
        "focus": "风险敞口",
        "prompt_focus": "最大回撤风险、集中度风险、政策风险、黑天鹅事件概率"
    }
}


# ==================== 报告生成服务 ====================

class ICReportService:
    """投资决策委员会报告生成服务"""
    
    def __init__(self):
        self._cache: Dict[str, ICReport] = {}
    
    def generate_report(
        self,
        symbol: str,
        name: str,
        flow_data: Optional[Dict] = None,
        tech_data: Optional[Dict] = None,
        valuation_data: Optional[Dict] = None,
        use_ai: bool = False
    ) -> ICReport:
        """
        生成投资决策委员会报告
        
        Args:
            symbol: 股票代码
            name: 股票名称
            flow_data: 资金流向数据
            tech_data: 技术分析数据
            valuation_data: 估值数据
            use_ai: 是否使用 AI 生成深度分析（需要 agent）
            
        Returns:
            ICReport: 完整的投委会报告
        """
        report = ICReport(symbol=symbol, name=name)
        
        # 收集原始数据
        report.raw_data = {
            "flow": flow_data or {},
            "tech": tech_data or {},
            "valuation": valuation_data or {}
        }
        
        # 1. 生成基础分析（基于规则）
        self._generate_rule_based_analysis(report)
        
        # 2. 如果启用 AI，调用 Agent 生成深度分析
        if use_ai:
            self._enhance_with_ai(report)
        
        return report
    
    def _generate_rule_based_analysis(self, report: ICReport):
        """基于规则生成基础分析"""
        flow_data = report.raw_data.get("flow", {})
        tech_data = report.raw_data.get("tech", {})
        valuation_data = report.raw_data.get("valuation", {})
        
        # === 计算各维度得分 ===
        scores = {}
        
        # 1. 资金面得分 (基于机构资金流向)
        inst_net = flow_data.get("institutional", {}).get("total_net_flow", 0)
        if inst_net > 1e8:
            scores["fund"] = 7.5
        elif inst_net > 0:
            scores["fund"] = 6.0
        elif inst_net > -1e8:
            scores["fund"] = 4.5
        else:
            scores["fund"] = 3.0
        
        # 2. 技术面得分 (基于趋势和指标)
        tech_score = tech_data.get("tech_score", 5.0) if tech_data else 5.0
        scores["tech"] = tech_score
        
        # 3. 估值面得分 (基于 PE 分位)
        pe_percentile = valuation_data.get("pe_percentile", 50) if valuation_data else 50
        if pe_percentile < 20:
            scores["valuation"] = 8.0
        elif pe_percentile < 40:
            scores["valuation"] = 6.5
        elif pe_percentile < 60:
            scores["valuation"] = 5.0
        elif pe_percentile < 80:
            scores["valuation"] = 4.0
        else:
            scores["valuation"] = 2.5
        
        # === 综合评分 ===
        weights = {"fund": 0.3, "tech": 0.3, "valuation": 0.4}
        overall = sum(scores.get(k, 5.0) * w for k, w in weights.items())
        report.overall_score = round(overall, 1)
        
        # === 评级 ===
        if overall >= 7.5:
            report.rating = "买入"
            report.rating_subtitle = "建议: 积极配置"
        elif overall >= 6.0:
            report.rating = "持有"
            report.rating_subtitle = "建议: 观望 / 周期反弹卖出"
        elif overall >= 4.5:
            report.rating = "观望"
            report.rating_subtitle = "建议: 等待更好时机"
        else:
            report.rating = "太难了 (Too Hard)"
            report.rating_subtitle = "建议: 放入能力圈外"
        
        # === 生成专家意见（简版） ===
        for expert_id, expert_info in EXPERTS.items():
            opinion = ExpertOpinion(
                expert_id=expert_id,
                expert_name=expert_info["name"],
                expert_icon=expert_info["icon"],
                focus_area=expert_info["focus"],
                key_points=self._generate_expert_points(expert_id, report.raw_data),
                rating=scores.get(expert_id, 5.0),
                stance=self._determine_stance(scores.get(expert_id, 5.0))
            )
            report.expert_opinions[expert_id] = opinion
        
        # === 一句话穿透（模板版） ===
        report.penetrating_insight = self._generate_penetrating_insight(report)
        
        # === 主要风险 ===
        report.main_risks = self._identify_risks(report.raw_data)
        
        # === 压力测试场景 ===
        report.stress_test_scenarios = [
            StressTestScenario(
                name="行业增速变化",
                variable="industry_growth",
                current_value=15,
                min_value=-10,
                max_value=50,
                unit="%"
            ),
            StressTestScenario(
                name="大客户砍单幅度",
                variable="customer_cut",
                current_value=0,
                min_value=0,
                max_value=50,
                unit="%"
            )
        ]
        
        # === 评级触发条件 ===
        report.rating_triggers = [
            RatingTrigger(
                direction="downgrade",
                target_rating="卖出",
                condition="如果连续2个季度经营性现金流为负"
            ),
            RatingTrigger(
                direction="downgrade",
                target_rating="卖出",
                condition="如果机构连续10个交易日大幅净流出(>5000万/日)"
            ),
            RatingTrigger(
                direction="upgrade",
                target_rating="买入",
                condition="如果新产品发布后首月销量超预期30%以上"
            )
        ]
        
        # === 信息黑箱 ===
        report.missing_data = [
            "最新季度具体订单金额明细",
            "主要客户未来12个月采购计划",
            "核心技术专利到期时间表"
        ]
    
    def _generate_expert_points(self, expert_id: str, raw_data: Dict) -> List[str]:
        """生成专家核心观点（模板化）"""
        points = {
            "munger": [
                "需评估公司在产业链中的议价能力",
                "关注核心技术是否形成真正护城河",
                "管理层资本配置历史记录待验证"
            ],
            "industry": [
                "行业正处于技术变革期",
                "竞争格局可能在2-3年内重塑",
                "关注下游需求拐点信号"
            ],
            "quant": [
                "关注经营性现金流与净利润的匹配度",
                "存货周转天数变化趋势需警惕",
                "应收账款账龄结构待分析"
            ],
            "cycle": [
                "当前处于周期的什么阶段需判断",
                "资本开支强度与行业景气度的关系",
                "估值历史分位提供安全边际参考"
            ],
            "risk": [
                "客户集中度风险需要对冲",
                "汇率波动可能影响利润空间",
                "政策环境变化需持续跟踪"
            ]
        }
        return points.get(expert_id, ["数据不足，无法生成具体观点"])
    
    def _determine_stance(self, score: float) -> str:
        """根据分数确定立场"""
        if score >= 6.5:
            return "bullish"
        elif score <= 4.0:
            return "bearish"
        return "neutral"
    
    def _generate_penetrating_insight(self, report: ICReport) -> str:
        """生成一句话穿透"""
        score = report.overall_score
        name = report.name
        
        if score >= 7.0:
            return f"「{name}」是具备核心竞争力的行业领跑者，当前估值处于合理区间。"
        elif score >= 5.5:
            return f"「{name}」业务基本面尚可，但增长动能和护城河深度存疑。"
        elif score >= 4.0:
            return f"「{name}」面临多重不确定性，需要更多信息才能形成清晰判断。"
        else:
            return f"「{name}」当前投资难度较大，建议放入「太难了」清单。"
    
    def _identify_risks(self, raw_data: Dict) -> List[str]:
        """识别主要风险"""
        risks = []
        
        flow_data = raw_data.get("flow", {})
        inst_net = flow_data.get("institutional", {}).get("total_net_flow", 0)
        if inst_net < -5e7:
            risks.append("机构资金持续流出，需警惕进一步抛压")
        
        if not risks:
            risks = [
                "行业竞争加剧可能压缩利润空间",
                "宏观经济波动影响下游需求"
            ]
        
        return risks
    
    def _enhance_with_ai(self, report: ICReport):
        """使用 AI 增强分析（调用 Agent）"""
        # TODO: 接入 agent_manager 生成更深入的分析
        # 这里先保留为扩展点
        pass
    
    def calculate_stress_test(
        self,
        report: ICReport,
        scenario_values: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        计算压力测试结果
        
        Args:
            report: 原始报告
            scenario_values: 用户调整的场景变量值
            
        Returns:
            模拟结果
        """
        # 简化的压力测试模型
        industry_growth = scenario_values.get("industry_growth", 15)
        customer_cut = scenario_values.get("customer_cut", 0)
        
        # 基准值
        base_capacity_util = 72.5
        base_net_margin = 4.0
        
        # 调整后的值
        capacity_util = base_capacity_util * (1 + (industry_growth - 15) / 100) * (1 - customer_cut / 100)
        net_margin = base_net_margin * (1 + (industry_growth - 15) / 200) * (1 - customer_cut / 50)
        
        # 库存风险评估
        if capacity_util > 80:
            inventory_risk = "低风险"
            inventory_risk_level = "safe"
        elif capacity_util > 60:
            inventory_risk = "中性/安全"
            inventory_risk_level = "neutral"
        else:
            inventory_risk = "高风险"
            inventory_risk_level = "danger"
        
        return {
            "capacity_utilization": round(max(0, min(100, capacity_util)), 1),
            "net_margin": round(max(-10, min(20, net_margin)), 1),
            "inventory_risk": inventory_risk,
            "inventory_risk_level": inventory_risk_level,
            "conclusion": self._generate_stress_conclusion(capacity_util, net_margin)
        }
    
    def _generate_stress_conclusion(self, capacity_util: float, net_margin: float) -> str:
        """生成压力测试结论"""
        if capacity_util > 70 and net_margin > 3:
            return "如果能维持此高景气度，公司有望通过规模效应修复报表。但需警惕这是不是周期顶点。"
        elif capacity_util > 50 and net_margin > 0:
            return "基本面尚可维持，但利润空间有限，需关注成本控制能力。"
        else:
            return "当前场景下公司经营压力较大，建议谨慎观望。"


# ==================== 单例 ====================

_ic_service: Optional[ICReportService] = None

def get_ic_service() -> ICReportService:
    """获取 IC 报告服务单例"""
    global _ic_service
    if _ic_service is None:
        _ic_service = ICReportService()
    return _ic_service
