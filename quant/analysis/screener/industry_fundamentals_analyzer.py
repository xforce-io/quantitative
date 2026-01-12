#!/usr/bin/env python3
"""
行业基本面分析器 - Industry Fundamentals Analyzer
分析行业利润率、产能利用率、竞争格局等基本面指标
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class IndustryFundamentalsAnalyzer:
    """
    行业基本面分析器

    功能:
    1. 利润率趋势分析
    2. 竞争格局评估
    3. 行业健康度评分
    4. 基本面风险识别
    """

    def __init__(self):
        """初始化分析器"""
        # 行业基本面数据库（基于公开数据和行业研究）
        self.industry_fundamentals = {
            # 科技类
            '半导体': {
                'profit_margin': 0.20,
                'margin_trend': '下降',  # 周期下行
                'capacity_utilization': 0.75,
                'competition_level': '激烈',
                'hhi_index': 2500,  # Herfindahl指数
                'subsidy_dependency': 0.10,
                'cycle_stage': '下行',
                'key_risks': ['地缘政治', '产能过剩', '技术迭代']
            },
            '科技': {
                'profit_margin': 0.15,
                'margin_trend': '平稳',
                'capacity_utilization': 0.80,
                'competition_level': '中等',
                'hhi_index': 1500,
                'subsidy_dependency': 0.05,
                'cycle_stage': '成长',
                'key_risks': ['市场竞争', '技术变革']
            },

            # 新能源类
            '新能源车': {
                'profit_margin': 0.02,
                'margin_trend': '下降',  # 价格战激烈
                'capacity_utilization': 0.65,
                'competition_level': '极度激烈',
                'hhi_index': 800,  # 高度分散
                'subsidy_dependency': 0.20,
                'cycle_stage': '成熟前期',
                'key_risks': ['价格战', '补贴退坡', '需求波动']
            },
            '光伏': {
                'profit_margin': 0.08,
                'margin_trend': '下降',
                'capacity_utilization': 0.70,
                'competition_level': '激烈',
                'hhi_index': 1200,
                'subsidy_dependency': 0.15,
                'cycle_stage': '扩张',
                'key_risks': ['产能过剩', '价格战', '政策变化']
            },
            '风电': {
                'profit_margin': 0.12,
                'margin_trend': '平稳',
                'capacity_utilization': 0.75,
                'competition_level': '中等',
                'hhi_index': 2000,
                'subsidy_dependency': 0.12,
                'cycle_stage': '稳定增长',
                'key_risks': ['政策依赖', '装机量波动']
            },
            '储能': {
                'profit_margin': 0.15,
                'margin_trend': '上升',  # 新兴赛道
                'capacity_utilization': 0.85,
                'competition_level': '中等',
                'hhi_index': 1800,
                'subsidy_dependency': 0.10,
                'cycle_stage': '早期成长',
                'key_risks': ['技术路线', '成本压力']
            },

            # 消费类
            '白酒': {
                'profit_margin': 0.45,
                'margin_trend': '平稳',
                'capacity_utilization': 0.90,
                'competition_level': '寡头',
                'hhi_index': 3500,  # 高集中度
                'subsidy_dependency': 0.0,
                'cycle_stage': '成熟',
                'key_risks': ['消费降级', '库存积压']
            },
            '食品饮料': {
                'profit_margin': 0.18,
                'margin_trend': '平稳',
                'capacity_utilization': 0.85,
                'competition_level': '中等',
                'hhi_index': 1500,
                'subsidy_dependency': 0.0,
                'cycle_stage': '成熟',
                'key_risks': ['原材料成本', '品牌竞争']
            },
            '消费': {
                'profit_margin': 0.12,
                'margin_trend': '下降',  # 消费疲软
                'capacity_utilization': 0.75,
                'competition_level': '激烈',
                'hhi_index': 1000,
                'subsidy_dependency': 0.0,
                'cycle_stage': '调整',
                'key_risks': ['宏观经济', '消费信心']
            },

            # 医药类
            '医药': {
                'profit_margin': 0.18,
                'margin_trend': '下降',  # 集采影响
                'capacity_utilization': 0.80,
                'competition_level': '激烈',
                'hhi_index': 1200,
                'subsidy_dependency': 0.05,
                'cycle_stage': '结构调整',
                'key_risks': ['集采降价', '研发失败', '监管政策']
            },

            # 金融类
            '银行': {
                'profit_margin': 0.30,
                'margin_trend': '下降',  # 息差收窄
                'capacity_utilization': 0.90,
                'competition_level': '寡头',
                'hhi_index': 3000,
                'subsidy_dependency': 0.0,
                'cycle_stage': '成熟',
                'key_risks': ['不良率', '息差压力', '地产风险']
            },
            '券商': {
                'profit_margin': 0.20,
                'margin_trend': '波动',  # 周期性强
                'capacity_utilization': 0.70,
                'competition_level': '激烈',
                'hhi_index': 1500,
                'subsidy_dependency': 0.0,
                'cycle_stage': '周期',
                'key_risks': ['市场波动', '业务周期性']
            },

            # 周期类
            '煤炭': {
                'profit_margin': 0.15,
                'margin_trend': '波动',
                'capacity_utilization': 0.80,
                'competition_level': '中等',
                'hhi_index': 2000,
                'subsidy_dependency': 0.0,
                'cycle_stage': '周期',
                'key_risks': ['价格波动', '政策调控', '能源转型']
            },
            '钢铁': {
                'profit_margin': 0.05,
                'margin_trend': '下降',
                'capacity_utilization': 0.75,
                'competition_level': '激烈',
                'hhi_index': 1000,
                'subsidy_dependency': 0.0,
                'cycle_stage': '周期下行',
                'key_risks': ['需求萎缩', '成本压力', '环保限产']
            },
            '有色金属': {
                'profit_margin': 0.10,
                'margin_trend': '波动',
                'capacity_utilization': 0.75,
                'competition_level': '中等',
                'hhi_index': 1500,
                'subsidy_dependency': 0.0,
                'cycle_stage': '周期',
                'key_risks': ['全球经济', '商品价格', '地缘政治']
            },

            # 基建地产
            '房地产': {
                'profit_margin': 0.05,
                'margin_trend': '下降',  # 行业困境
                'capacity_utilization': 0.60,
                'competition_level': '激烈',
                'hhi_index': 800,
                'subsidy_dependency': 0.0,
                'cycle_stage': '衰退',
                'key_risks': ['政策调控', '债务风险', '销售下滑']
            },
            'REITs': {
                'profit_margin': 0.06,
                'margin_trend': '平稳',
                'capacity_utilization': 0.85,
                'competition_level': '中等',
                'hhi_index': 1500,
                'subsidy_dependency': 0.0,
                'cycle_stage': '成熟',
                'key_risks': ['利率波动', '租金收益']
            },
            '基建': {
                'profit_margin': 0.08,
                'margin_trend': '平稳',
                'capacity_utilization': 0.75,
                'competition_level': '激烈',
                'hhi_index': 1000,
                'subsidy_dependency': 0.0,
                'cycle_stage': '稳定',
                'key_risks': ['政府投资', '回款周期']
            },

            # 制造军工
            '机械': {
                'profit_margin': 0.10,
                'margin_trend': '平稳',
                'capacity_utilization': 0.75,
                'competition_level': '中等',
                'hhi_index': 1200,
                'subsidy_dependency': 0.05,
                'cycle_stage': '成长',
                'key_risks': ['下游需求', '产能过剩']
            },
            '军工': {
                'profit_margin': 0.18,
                'margin_trend': '上升',
                'capacity_utilization': 0.85,
                'competition_level': '壁垒高',
                'hhi_index': 2500,
                'subsidy_dependency': 0.0,
                'cycle_stage': '成长',
                'key_risks': ['订单波动', '国际关系']
            },
        }

        logger.info(f"✅ 行业基本面分析器初始化完成，已配置 {len(self.industry_fundamentals)} 个行业")

    def get_industry_metrics(self, industry: str) -> Optional[Dict]:
        """
        获取行业基本面指标

        Args:
            industry: 行业名称

        Returns:
            行业基本面指标字典
        """
        if not industry:
            return None

        # 精确匹配
        if industry in self.industry_fundamentals:
            return self.industry_fundamentals[industry].copy()

        # 模糊匹配
        for key, value in self.industry_fundamentals.items():
            if key in industry or industry in key:
                return value.copy()

        return None

    def analyze_fundamentals(
        self,
        industry: str,
        price_data: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        分析行业基本面

        Args:
            industry: 行业名称
            price_data: 价格数据（用于动态调整）

        Returns:
            基本面分析结果
        """
        # 获取基本面数据
        metrics = self.get_industry_metrics(industry)

        if metrics is None:
            return self._empty_result(industry)

        try:
            # 计算基本面得分
            fundamentals_score = self._calculate_fundamentals_score(metrics)

            # 计算风险调整
            risk_adjustment = self._calculate_risk_adjustment(metrics)

            # 健康度评级
            health_rating = self._classify_health(fundamentals_score)

            return {
                'available': True,
                'industry': industry,
                'metrics': metrics,
                'fundamentals_score': fundamentals_score,
                'health_rating': health_rating,
                'risk_adjustment': risk_adjustment,
                'warnings': self._generate_warnings(metrics),
                'strengths': self._identify_strengths(metrics)
            }

        except Exception as e:
            logger.error(f"基本面分析失败: {e}")
            return self._empty_result(industry)

    def _calculate_fundamentals_score(self, metrics: Dict) -> float:
        """
        计算基本面得分 (0-1)

        综合考虑:
        1. 利润率水平
        2. 利润率趋势
        3. 产能利用率
        4. 竞争格局
        5. 补贴依赖度
        """
        score = 0.5  # 基准分

        # 1. 利润率得分 (0-0.25)
        profit_margin = metrics.get('profit_margin', 0.10)
        if profit_margin >= 0.30:
            score += 0.25
        elif profit_margin >= 0.15:
            score += 0.15
        elif profit_margin >= 0.08:
            score += 0.10
        elif profit_margin < 0.05:
            score -= 0.10

        # 2. 利润率趋势 (-0.15 ~ +0.15)
        margin_trend = metrics.get('margin_trend', '平稳')
        if margin_trend == '上升':
            score += 0.15
        elif margin_trend == '下降':
            score -= 0.15

        # 3. 产能利用率 (-0.10 ~ +0.10)
        capacity_util = metrics.get('capacity_utilization', 0.75)
        if capacity_util >= 0.85:
            score += 0.10
        elif capacity_util < 0.70:
            score -= 0.10

        # 4. 竞争格局 (-0.10 ~ +0.10)
        competition = metrics.get('competition_level', '中等')
        if competition in ['寡头', '壁垒高']:
            score += 0.10
        elif competition == '极度激烈':
            score -= 0.10

        # 5. 补贴依赖度 (-0.10 ~ 0)
        subsidy_dep = metrics.get('subsidy_dependency', 0.0)
        if subsidy_dep > 0.15:
            score -= 0.10
        elif subsidy_dep > 0.10:
            score -= 0.05

        # 限制在[0, 1]
        return max(0.0, min(1.0, score))

    def _calculate_risk_adjustment(self, metrics: Dict) -> float:
        """
        计算基本面风险调整 (-0.20 ~ +0.10)

        Args:
            metrics: 基本面指标

        Returns:
            风险调整系数
        """
        adjustment = 0.0

        # 1. 利润率下降扣分
        if metrics.get('margin_trend') == '下降':
            adjustment -= 0.08

        # 2. 产能过剩扣分
        if metrics.get('capacity_utilization', 0.75) < 0.70:
            adjustment -= 0.06

        # 3. 高度依赖补贴扣分
        if metrics.get('subsidy_dependency', 0.0) > 0.15:
            adjustment -= 0.06

        # 4. 周期下行扣分
        cycle_stage = metrics.get('cycle_stage', '成长')
        if cycle_stage in ['衰退', '周期下行', '调整']:
            adjustment -= 0.10

        # 5. 竞争极度激烈扣分
        if metrics.get('competition_level') == '极度激烈':
            adjustment -= 0.10

        # 6. 优势行业加分
        if metrics.get('profit_margin', 0) > 0.25 and metrics.get('margin_trend') != '下降':
            adjustment += 0.10

        # 限制在合理范围
        return max(-0.20, min(0.10, adjustment))

    def _classify_health(self, score: float) -> str:
        """行业健康度分类"""
        if score >= 0.75:
            return "优秀"
        elif score >= 0.60:
            return "良好"
        elif score >= 0.45:
            return "一般"
        elif score >= 0.30:
            return "较弱"
        else:
            return "困难"

    def _generate_warnings(self, metrics: Dict) -> List[str]:
        """生成风险警告"""
        warnings = []

        if metrics.get('margin_trend') == '下降':
            warnings.append("⚠️ 利润率下降趋势")

        if metrics.get('capacity_utilization', 0.75) < 0.70:
            warnings.append("⚠️ 产能过剩")

        if metrics.get('subsidy_dependency', 0.0) > 0.15:
            warnings.append("⚠️ 高度依赖补贴")

        if metrics.get('competition_level') == '极度激烈':
            warnings.append("⚠️ 竞争极度激烈")

        if metrics.get('cycle_stage') in ['衰退', '周期下行']:
            warnings.append("⚠️ 行业周期下行")

        return warnings

    def _identify_strengths(self, metrics: Dict) -> List[str]:
        """识别行业优势"""
        strengths = []

        if metrics.get('profit_margin', 0) > 0.20:
            strengths.append("✅ 高利润率")

        if metrics.get('margin_trend') == '上升':
            strengths.append("✅ 利润率提升")

        if metrics.get('capacity_utilization', 0) > 0.85:
            strengths.append("✅ 产能利用率高")

        if metrics.get('competition_level') in ['寡头', '壁垒高']:
            strengths.append("✅ 竞争格局良好")

        if metrics.get('subsidy_dependency', 0) < 0.05:
            strengths.append("✅ 不依赖补贴")

        return strengths

    def _empty_result(self, industry: str) -> Dict:
        """返回空结果"""
        return {
            'available': False,
            'industry': industry,
            'reason': '无基本面数据',
            'fundamentals_score': 0.5,
            'health_rating': '未知',
            'risk_adjustment': 0.0,
            'warnings': [],
            'strengths': []
        }

    def generate_report(self, fundamentals_result: Dict) -> str:
        """
        生成基本面分析报告

        Args:
            fundamentals_result: 基本面分析结果

        Returns:
            格式化的报告文本
        """
        report = []
        report.append("\n" + "="*60)
        report.append("📊 行业基本面分析报告")
        report.append("="*60)

        if not fundamentals_result.get('available', False):
            report.append(f"\n行业: {fundamentals_result['industry']}")
            report.append(f"⚠️ {fundamentals_result.get('reason', '数据不足')}")
            report.append("="*60 + "\n")
            return "\n".join(report)

        report.append(f"\n行业: {fundamentals_result['industry']}")
        report.append(f"健康度评级: {fundamentals_result['health_rating']}")
        report.append(f"基本面得分: {fundamentals_result['fundamentals_score']:.3f}/1.000")
        report.append(f"风险调整: {fundamentals_result['risk_adjustment']:+.3f}")

        metrics = fundamentals_result['metrics']
        report.append(f"\n📈 核心指标:")
        report.append(f"  利润率: {metrics['profit_margin']*100:.1f}% ({metrics['margin_trend']})")
        report.append(f"  产能利用率: {metrics['capacity_utilization']*100:.1f}%")
        report.append(f"  竞争格局: {metrics['competition_level']}")
        report.append(f"  补贴依赖: {metrics['subsidy_dependency']*100:.1f}%")
        report.append(f"  周期阶段: {metrics['cycle_stage']}")

        if fundamentals_result['strengths']:
            report.append(f"\n💪 行业优势:")
            for strength in fundamentals_result['strengths']:
                report.append(f"  {strength}")

        if fundamentals_result['warnings']:
            report.append(f"\n⚠️  风险警示:")
            for warning in fundamentals_result['warnings']:
                report.append(f"  {warning}")

        report.append("\n" + "="*60 + "\n")

        return "\n".join(report)


def main():
    """测试函数"""
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*80)
    logger.info("📊 行业基本面分析器测试")
    print("="*80)

    # 初始化分析器
    analyzer = IndustryFundamentalsAnalyzer()

    # 测试行业
    test_industries = [
        '半导体',
        '新能源车',
        '光伏',
        '白酒',
        '银行',
        '房地产',
        '军工'
    ]

    for industry in test_industries:
        result = analyzer.analyze_fundamentals(industry)
        report = analyzer.generate_report(result)
        logger.info("%s", report)

    print("="*80)


if __name__ == "__main__":
    main()
