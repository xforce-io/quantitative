#!/usr/bin/env python3
"""
子行业分类器 - Sub-Industry Classifier
根据产业链位置和竞争格局细分ETF
"""

import yaml
from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class SubIndustryClassifier:
    """
    子行业分类器

    功能:
    1. 加载产业链分类配置
    2. 根据ETF代码查询分类信息
    3. 获取行业特征和风险系数
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化分类器

        Args:
            config_path: 配置文件路径，默认使用config/industry_taxonomy.yaml
        """
        if config_path is None:
            # 默认配置路径
            project_root = Path(__file__).parent.parent.parent.parent
            config_path = project_root / "config" / "industry_taxonomy.yaml"

        self.config_path = Path(config_path)
        self.taxonomy = self._load_taxonomy()
        self.etf_index = self.taxonomy.get('etf_to_category_index', {})

        logger.info(f"✅ 子行业分类器初始化完成，已加载 {len(self.etf_index)} 个ETF分类")

    def _load_taxonomy(self) -> Dict:
        """加载产业链分类配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                taxonomy = yaml.safe_load(f)

            if not taxonomy:
                logger.warning(f"配置文件为空: {self.config_path}")
                return {}

            return taxonomy

        except FileNotFoundError:
            logger.error(f"配置文件不存在: {self.config_path}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"YAML解析错误: {e}")
            return {}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}

    def get_industry_meta(self, symbol: str) -> Optional[Dict]:
        """
        获取ETF的行业元数据

        Args:
            symbol: ETF代码 (如 '512480.SH')

        Returns:
            行业元数据字典，包含:
            - category: 大分类 (如 '科技_产业链分类')
            - sub_category: 子分类 (如 '上游_半导体')
            - industry: 行业 (如 '半导体')
            - characteristics: 行业特征 (风险系数、周期属性等)
            - risk_multiplier: 风险系数
        """
        # 查询索引
        index_info = self.etf_index.get(symbol)
        if not index_info:
            logger.debug(f"未找到 {symbol} 的分类信息")
            return None

        category = index_info.get('category')
        sub_category = index_info.get('sub_category')

        # 获取详细特征
        category_data = self.taxonomy.get(category, {})
        sub_category_data = category_data.get(sub_category, {})
        characteristics = sub_category_data.get('特征', {})

        return {
            'symbol': symbol,
            'category': category,
            'sub_category': sub_category,
            'industry': index_info.get('industry', ''),
            'characteristics': characteristics,
            'risk_multiplier': characteristics.get('风险系数', 1.0),
            'cycle_property': characteristics.get('周期属性', '中'),
            'profit_margin_range': characteristics.get('利润率区间', [0, 0]),
            'competition_level': characteristics.get('竞争格局', '未知'),
            'supply_chain_position': characteristics.get('产业链位置', '未知'),
            'main_risks': characteristics.get('主要风险', [])
        }

    def is_high_risk_category(self, symbol: str) -> bool:
        """
        判断是否为高风险类别

        Args:
            symbol: ETF代码

        Returns:
            是否为高风险 (风险系数 >= 1.5)
        """
        meta = self.get_industry_meta(symbol)
        if not meta:
            return False

        return meta.get('risk_multiplier', 1.0) >= 1.5

    def is_cyclical(self, symbol: str) -> bool:
        """
        判断是否为周期性行业

        Args:
            symbol: ETF代码

        Returns:
            是否为周期性行业
        """
        meta = self.get_industry_meta(symbol)
        if not meta:
            return False

        cycle_property = meta.get('cycle_property', '中')
        return cycle_property in ['强', '极强']

    def get_expected_profit_margin(self, symbol: str) -> tuple:
        """
        获取预期利润率区间

        Args:
            symbol: ETF代码

        Returns:
            (最小利润率, 最大利润率) 元组，单位为小数 (0.05 = 5%)
        """
        meta = self.get_industry_meta(symbol)
        if not meta:
            return (0.0, 0.0)

        profit_range = meta.get('profit_margin_range', [0, 0])
        if len(profit_range) == 2:
            # 转换百分比字符串为小数
            try:
                min_margin = float(str(profit_range[0]).rstrip('%')) / 100
                max_margin = float(str(profit_range[1]).rstrip('%')) / 100
                return (min_margin, max_margin)
            except (ValueError, AttributeError):
                return (0.0, 0.0)

        return (0.0, 0.0)

    def calculate_industry_risk_adjustment(self, symbol: str, context: Dict = None) -> float:
        """
        根据行业特征计算风险调整系数

        Args:
            symbol: ETF代码
            context: 上下文信息 (可包含当前利润率、估值等)

        Returns:
            风险调整系数 (-0.3 到 +0.1)
        """
        meta = self.get_industry_meta(symbol)
        if not meta:
            return 0.0

        adjustment = 0.0

        # 1. 基于风险系数的调整
        risk_multiplier = meta.get('risk_multiplier', 1.0)
        if risk_multiplier >= 1.8:
            adjustment -= 0.15  # 极高风险
        elif risk_multiplier >= 1.5:
            adjustment -= 0.10  # 高风险
        elif risk_multiplier <= 0.8:
            adjustment += 0.05  # 低风险

        # 2. 下游应用行业的额外惩罚
        sub_category = meta.get('sub_category', '')
        if '下游' in sub_category:
            # 检查是否处于价格战阶段
            characteristics = meta.get('characteristics', {})
            if characteristics.get('价格战烈度') == '极高':
                adjustment -= 0.2

            # 检查利润率是否低于预期
            if context and 'profit_margin' in context:
                expected_min, expected_max = self.get_expected_profit_margin(symbol)
                actual_margin = context['profit_margin']

                if actual_margin < expected_min:
                    adjustment -= 0.1  # 利润率低于预期

        # 3. 产能过剩风险
        characteristics = meta.get('characteristics', {})
        if characteristics.get('产能过剩风险') == '高':
            adjustment -= 0.05

        # 4. 技术迭代风险
        if characteristics.get('技术迭代') == '快':
            adjustment -= 0.05

        # 限制在合理范围内
        return max(-0.3, min(0.1, adjustment))

    def get_all_categories(self) -> list:
        """获取所有大分类名称"""
        categories = []
        for key in self.taxonomy.keys():
            if key.endswith('_分类') or key.endswith('_产业链分类'):
                categories.append(key)
        return categories

    def get_etfs_by_category(self, category: str, sub_category: Optional[str] = None) -> list:
        """
        按分类获取ETF列表

        Args:
            category: 大分类名称
            sub_category: 子分类名称（可选）

        Returns:
            ETF代码列表
        """
        etfs = []

        for symbol, info in self.etf_index.items():
            if info.get('category') == category:
                if sub_category is None or info.get('sub_category') == sub_category:
                    etfs.append(symbol)

        return etfs

    def get_statistics(self) -> Dict:
        """获取分类统计信息"""
        stats = {
            'total_etfs': len(self.etf_index),
            'categories': {},
            'risk_distribution': {
                '低风险 (<1.0)': 0,
                '中等风险 (1.0-1.5)': 0,
                '高风险 (1.5-2.0)': 0,
                '极高风险 (>2.0)': 0
            },
            'cycle_distribution': {
                '弱': 0,
                '中': 0,
                '强': 0,
                '极强': 0
            }
        }

        for symbol in self.etf_index.keys():
            meta = self.get_industry_meta(symbol)
            if not meta:
                continue

            # 统计分类
            category = meta.get('category', '未分类')
            stats['categories'][category] = stats['categories'].get(category, 0) + 1

            # 统计风险分布
            risk = meta.get('risk_multiplier', 1.0)
            if risk < 1.0:
                stats['risk_distribution']['低风险 (<1.0)'] += 1
            elif risk < 1.5:
                stats['risk_distribution']['中等风险 (1.0-1.5)'] += 1
            elif risk < 2.0:
                stats['risk_distribution']['高风险 (1.5-2.0)'] += 1
            else:
                stats['risk_distribution']['极高风险 (>2.0)'] += 1

            # 统计周期分布
            cycle = meta.get('cycle_property', '中')
            stats['cycle_distribution'][cycle] = stats['cycle_distribution'].get(cycle, 0) + 1

        return stats


def main():
    """测试函数"""
    import json

    # 初始化分类器
    classifier = SubIndustryClassifier()

    print("\n" + "="*80)
    logger.info("📊 ETF子行业分类器测试")
    print("="*80)

    # 测试案例
    test_symbols = [
        '516850.SH',  # 新能源车ETF (下游应用)
        '516780.SH',  # 光伏ETF (中游制造)
        '516770.SH',  # 稀土ETF (上游资源)
        '512480.SH',  # 半导体ETF (上游半导体)
        '512690.SH',  # 白酒ETF (上游白酒)
        '512200.SH',  # 房地产ETF (房地产)
        '512820.SH',  # 银行龙头ETF (银行)
    ]

    logger.info("\n1️⃣ 分类信息测试:")
    print("-"*80)

    for symbol in test_symbols:
        meta = classifier.get_industry_meta(symbol)
        if meta:
            logger.info("\n{symbol} - {meta['industry']}")
            logger.info("  大分类: {meta['category']}")
            logger.info("  子分类: {meta['sub_category']}")
            logger.info("  产业链位置: {meta['supply_chain_position']}")
            logger.info("  风险系数: {meta['risk_multiplier']}")
            logger.info("  周期属性: {meta['cycle_property']}")
            logger.info("  利润率区间: {meta['profit_margin_range']}")
            logger.info("  竞争格局: {meta['competition_level']}")

            # 风险调整测试
            adjustment = classifier.calculate_industry_risk_adjustment(
                symbol,
                context={'profit_margin': 0.03}  # 模拟3%利润率
            )
            logger.info("  风险调整系数: {adjustment:+.3f}")

    print("\n" + "="*80)
    logger.info("2️⃣ 统计信息:")
    print("-"*80)

    stats = classifier.get_statistics()
    logger.info("\n总ETF数量: {stats['total_etfs']}")

    logger.info("\n分类分布:")
    for cat, count in sorted(stats['categories'].items(), key=lambda x: -x[1]):
        logger.info("  {cat}: {count}")

    logger.info("\n风险分布:")
    for level, count in stats['risk_distribution'].items():
        pct = count / stats['total_etfs'] * 100 if stats['total_etfs'] > 0 else 0
        logger.info("  {level}: {count} ({pct:.1f}%)")

    logger.info("\n周期属性分布:")
    for cycle, count in stats['cycle_distribution'].items():
        pct = count / stats['total_etfs'] * 100 if stats['total_etfs'] > 0 else 0
        logger.info("  {cycle}: {count} ({pct:.1f}%)")

    print("\n" + "="*80)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
