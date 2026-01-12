#!/usr/bin/env python3
"""
PEG估值分析器 - PEG Valuation Analyzer
结合增长率的前瞻性估值评估
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ConsensusDataProvider:
    """
    一致预期数据提供者

    提供增长率估算的多种方案:
    1. 基于历史CAGR估算
    2. 行业平均增长率
    3. 综合估算（历史+行业）
    """

    def __init__(self):
        """初始化数据提供者"""
        # 行业平均增长率配置（基于历史数据和行业研究）
        self.industry_avg_growth = {
            # 科技类
            '半导体': 0.15,
            '科技': 0.12,
            '科创': 0.18,
            'TMT': 0.10,

            # 新能源类
            '新能源车': 0.25,
            '新能源': 0.20,
            '光伏': 0.18,
            '风电': 0.15,
            '储能': 0.30,
            '碳中和': 0.12,
            '稀土': 0.10,

            # 消费类
            '白酒': 0.08,
            '食品饮料': 0.06,
            '消费': 0.07,

            # 医药类
            '医药': 0.10,

            # 金融类
            '银行': 0.03,
            '券商': 0.08,
            '保险': 0.05,
            '金融': 0.05,

            # 周期类
            '煤炭': 0.02,
            '钢铁': 0.03,
            '有色金属': 0.05,
            '化工': 0.04,
            '建材': 0.04,

            # 基建地产
            '房地产': -0.05,
            'REITs': 0.03,
            '基建': 0.06,

            # 制造军工
            '机械': 0.08,
            '军工': 0.12,

            # 其他
            '农业': 0.05,
            '航空': 0.10,
            '交运': 0.06,
        }

        logger.info(f"✅ 一致预期数据提供者初始化完成，已配置 {len(self.industry_avg_growth)} 个行业")

    def calculate_historical_cagr(
        self,
        price_data: pd.DataFrame,
        years: int = 3
    ) -> float:
        """
        计算历史复合年增长率 (CAGR)

        Args:
            price_data: 价格数据
            years: 计算年数

        Returns:
            CAGR（小数形式，如0.15表示15%）
        """
        if price_data.empty or len(price_data) < 252 * years:
            logger.debug(f"数据不足{years}年，无法计算CAGR")
            return 0.0

        try:
            # 获取起始和结束价格
            end_price = price_data['close'].iloc[-1]
            start_price = price_data['close'].iloc[-(252 * years + 1)]

            if start_price <= 0 or pd.isna(start_price) or pd.isna(end_price):
                return 0.0

            # CAGR = (End/Start)^(1/years) - 1
            cagr = (end_price / start_price) ** (1 / years) - 1

            # 限制在合理范围内 [-50%, +100%]
            cagr = max(-0.5, min(1.0, cagr))

            return cagr

        except Exception as e:
            logger.warning(f"计算CAGR失败: {e}")
            return 0.0

    def get_industry_avg_growth(self, industry: str) -> float:
        """
        获取行业平均增长率

        Args:
            industry: 行业名称

        Returns:
            增长率（小数形式）
        """
        if not industry:
            return 0.08  # 默认8%

        # 精确匹配
        if industry in self.industry_avg_growth:
            return self.industry_avg_growth[industry]

        # 模糊匹配
        for key, value in self.industry_avg_growth.items():
            if key in industry or industry in key:
                return value

        # 默认值
        return 0.08

    def get_growth_estimate(
        self,
        price_data: pd.DataFrame,
        industry: Optional[str] = None,
        method: str = 'hybrid'
    ) -> Tuple[float, str]:
        """
        获取增长率估算

        Args:
            price_data: 价格数据
            industry: 行业名称
            method: 估算方法
                - 'historical': 仅基于历史CAGR
                - 'industry': 仅基于行业平均
                - 'hybrid': 混合方法（默认）

        Returns:
            (增长率, 数据来源说明)
        """
        if method == 'historical':
            cagr = self.calculate_historical_cagr(price_data, years=3)
            return cagr, "历史3年CAGR"

        elif method == 'industry':
            industry_growth = self.get_industry_avg_growth(industry)
            return industry_growth, f"行业平均 ({industry or '默认'})"

        else:  # hybrid
            # 计算历史CAGR
            historical_growth = self.calculate_historical_cagr(price_data, years=3)

            # 获取行业平均
            industry_growth = self.get_industry_avg_growth(industry)

            # 混合估算：60%历史 + 40%行业（考虑均值回归）
            if historical_growth != 0:
                estimated_growth = 0.6 * historical_growth + 0.4 * industry_growth
                source = f"混合估算 (60%历史+40%行业)"
            else:
                # 无历史数据，使用行业平均
                estimated_growth = industry_growth
                source = f"行业平均 ({industry or '默认'})"

            return estimated_growth, source


class PEGValuationAnalyzer:
    """
    PEG估值分析器

    PEG = PE / (增长率 * 100)

    评估标准:
    - PEG < 0.5: 严重低估
    - 0.5 ≤ PEG < 1.0: 合理偏低
    - 1.0 ≤ PEG < 1.5: 合理
    - 1.5 ≤ PEG < 2.0: 偏高
    - PEG ≥ 2.0: 高估
    """

    def __init__(self, data_provider=None):
        """
        初始化PEG分析器

        Args:
            data_provider: 数据提供者（可选）
        """
        self.consensus_provider = ConsensusDataProvider()
        self.data_provider = data_provider

        logger.info("✅ PEG估值分析器初始化完成")

    def calculate_pe_ttm(self, price_data: pd.DataFrame) -> Optional[float]:
        """
        计算滚动市盈率 (PE TTM)

        由于ETF没有直接的PE数据，这里使用简化方法:
        1. 对于指数型ETF，假设PE与价格增长率相关
        2. 使用历史波动性作为PE的代理指标

        Args:
            price_data: 价格数据

        Returns:
            PE TTM估算值
        """
        if price_data.empty or len(price_data) < 252:
            return None

        try:
            # 方法1: 基于价格增长率估算PE
            # 假设: PE ≈ 15 * (1 + 年化收益率)
            recent_data = price_data.tail(252)
            annual_return = (recent_data['close'].iloc[-1] / recent_data['close'].iloc[0]) - 1

            # 基准PE = 15（A股平均水平）
            base_pe = 15.0
            estimated_pe = base_pe * (1 + annual_return)

            # 限制在合理范围 [5, 100]
            estimated_pe = max(5.0, min(100.0, estimated_pe))

            return estimated_pe

        except Exception as e:
            logger.warning(f"计算PE失败: {e}")
            return None

    def calculate_peg_valuation(
        self,
        price_data: pd.DataFrame,
        industry: Optional[str] = None,
        pe_ttm: Optional[float] = None
    ) -> Dict:
        """
        计算PEG估值

        Args:
            price_data: 价格数据
            industry: 行业名称
            pe_ttm: PE TTM（可选，如果为None则自动计算）

        Returns:
            PEG估值结果字典
        """
        if price_data.empty:
            return self._empty_result()

        try:
            # 获取PE
            if pe_ttm is None:
                pe_ttm = self.calculate_pe_ttm(price_data)

            if pe_ttm is None or pe_ttm <= 0:
                logger.debug("PE数据不可用")
                return self._empty_result()

            # 获取增长率估算
            growth_rate, growth_source = self.consensus_provider.get_growth_estimate(
                price_data,
                industry,
                method='hybrid'
            )

            # 计算PEG
            if growth_rate > 0:
                peg = pe_ttm / (growth_rate * 100)
            else:
                # 负增长，PEG无意义
                return {
                    'available': False,
                    'reason': '负增长',
                    'growth_rate': growth_rate,
                    'growth_rate_pct': growth_rate * 100,
                    'growth_source': growth_source,
                    'pe_ttm': pe_ttm
                }

            # PEG评级
            valuation_level, score_adjustment = self._classify_peg(peg)

            return {
                'available': True,
                'peg': round(peg, 2),
                'pe_ttm': round(pe_ttm, 2),
                'growth_rate': round(growth_rate, 4),
                'growth_rate_pct': round(growth_rate * 100, 2),
                'growth_source': growth_source,
                'valuation_level': valuation_level,
                'score_adjustment': score_adjustment,
                'interpretation': self._interpret_peg(peg, growth_rate)
            }

        except Exception as e:
            logger.error(f"计算PEG估值失败: {e}")
            return self._empty_result()

    def _classify_peg(self, peg: float) -> Tuple[str, float]:
        """
        PEG分类

        Args:
            peg: PEG值

        Returns:
            (估值水平, 评分调整)
        """
        if peg < 0.5:
            return "严重低估", 0.15
        elif peg < 1.0:
            return "合理偏低", 0.10
        elif peg < 1.5:
            return "合理", 0.0
        elif peg < 2.0:
            return "偏高", -0.05
        else:
            return "高估", -0.10

    def _interpret_peg(self, peg: float, growth_rate: float) -> str:
        """
        解释PEG值

        Args:
            peg: PEG值
            growth_rate: 增长率

        Returns:
            解释文本
        """
        growth_pct = growth_rate * 100

        if peg < 1.0:
            return f"以{growth_pct:.1f}%增长率衡量，当前估值具有吸引力"
        elif peg < 1.5:
            return f"基于{growth_pct:.1f}%增长预期，估值处于合理区间"
        else:
            return f"相对{growth_pct:.1f}%增长率，估值偏高，需关注增长兑现"

    def _empty_result(self) -> Dict:
        """返回空结果"""
        return {
            'available': False,
            'reason': '数据不足',
            'peg': None,
            'pe_ttm': None,
            'growth_rate': None,
            'growth_rate_pct': None,
            'growth_source': None,
            'valuation_level': '数据不足',
            'score_adjustment': 0.0,
            'interpretation': '无法计算PEG估值'
        }

    def generate_report(self, peg_result: Dict) -> str:
        """
        生成PEG分析报告

        Args:
            peg_result: PEG分析结果

        Returns:
            格式化的报告文本
        """
        report = []
        report.append("\n" + "="*60)
        report.append("📊 PEG估值分析报告")
        report.append("="*60)

        if not peg_result.get('available', False):
            report.append(f"\n⚠️ PEG不可用: {peg_result.get('reason', '未知')}")
            if peg_result.get('growth_rate') is not None:
                report.append(f"增长率: {peg_result['growth_rate_pct']:.2f}%")
            report.append("="*60 + "\n")
            return "\n".join(report)

        report.append(f"\nPEG比率: {peg_result['peg']:.2f}")
        report.append(f"PE (TTM): {peg_result['pe_ttm']:.2f}")
        report.append(f"预期增长率: {peg_result['growth_rate_pct']:.2f}%")
        report.append(f"数据来源: {peg_result['growth_source']}")

        report.append(f"\n估值水平: {peg_result['valuation_level']}")
        report.append(f"评分调整: {peg_result['score_adjustment']:+.3f}")

        report.append(f"\n💡 解读:")
        report.append(f"  {peg_result['interpretation']}")

        report.append("\n" + "="*60 + "\n")

        return "\n".join(report)


def main():
    """测试函数"""
    import sys
    from pathlib import Path

    # 添加项目根目录到路径
    project_root = Path(__file__).parent.parent.parent.parent
    sys.path.insert(0, str(project_root))

    from quant.data import create_data_provider
    from quant.analysis.screener.industry_classifier import SubIndustryClassifier

    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*80)
    logger.info("📊 PEG估值分析器测试")
    print("="*80)

    # 初始化数据提供器
    try:
        import os
        token = os.getenv('TUSHARE_TOKEN')
        if token:
            provider = create_data_provider('tushare', {'token': token})
        else:
            provider = create_data_provider('yahoo', {})
    except Exception as e:
        logger.info("❌ 数据提供器初始化失败: {e}")
        return

    # 初始化分析器
    peg_analyzer = PEGValuationAnalyzer(provider)
    classifier = SubIndustryClassifier()

    # 测试ETF
    test_symbols = [
        ('512480.SH', '半导体ETF'),
        ('516850.SH', '新能源车ETF'),
        ('512690.SH', '白酒ETF'),
        ('512820.SH', '银行龙头ETF'),
    ]

    # 获取数据
    end_date = datetime.now()
    start_date = end_date - timedelta(days=1200)  # 3年数据

    for symbol, name in test_symbols:
        logger.info("\n{'='*60}")
        logger.info("测试标的: {name} ({symbol})")
        logger.info("{'='*60}")

        # 获取行业分类
        industry_meta = classifier.get_industry_meta(symbol)
        industry = industry_meta.get('industry', '') if industry_meta else ''

        logger.info("行业分类: {industry}")

        # 获取价格数据
        try:
            price_data = provider.get_stock_data(
                symbol,
                start_date.strftime('%Y%m%d'),
                end_date.strftime('%Y%m%d'),
                'D'
            )

            if price_data.empty:
                logger.info("❌ 数据为空")
                continue

            logger.info("数据行数: {len(price_data)}")

            # 计算PEG
            peg_result = peg_analyzer.calculate_peg_valuation(price_data, industry)

            # 打印报告
            report = peg_analyzer.generate_report(peg_result)
            logger.info("%s", report)

        except Exception as e:
            logger.info("❌ 分析失败: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*80)


if __name__ == "__main__":
    main()
