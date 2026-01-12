#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
用户真实投资组合分析工具 - 基于新架构
User Real Portfolio Analyzer - Based on New Architecture
分析169.5万元真实投资组合
"""

import sys
import json
import yaml
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any
import warnings
warnings.filterwarnings('ignore')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from quant.core.config import get_config
from quant.data.providers import create_data_provider
from quant.core.indicators import TechnicalIndicators
from quant.analysis.etf_valuation_analyzer import ETFValuationAnalyzer
from quant.core.logging_config import get_logger

logger = get_logger(__name__)

class PortfolioAnalyzer:
    """用户真实投资组合分析器"""

    def __init__(self):
        self.config = get_config()
        self.data_provider = create_data_provider('auto', self.config.get_providers_config())

        # 加载用户真实投资组合配置
        self.portfolio_config = self._load_portfolio_config()

        # 投资组合基本信息
        self.total_value = 1695000  # 169.5万元
        self.currency = "CNY"
        
        # 初始化估值分析器
        self.valuation_analyzer = ETFValuationAnalyzer()

    def _load_portfolio_config(self) -> Dict[str, Any]:
        """加载投资组合配置"""
        config_path = project_root / "config/portfolios.yaml"

        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _is_etf_or_fund(self, symbol: str) -> bool:
        """判断是否为ETF或基金"""
        # ETF通常以.SH或.SZ结尾，且代5开头
        # 基金通常以.OF结尾
        if symbol.endswith('.OF'):
            return True
        if symbol.endswith(('.SH', '.SZ')):
            code = symbol.split('.')[0]
            # ETF代码通常为51xxxx, 159xxx, 588xxx, 512xxx, 513xxx, 515xxx, 516xxx
            if code.startswith(('51', '159', '588', '512', '513', '515', '516')):
                return True
        return False
    
    def _analyze_symbol_valuation(self, symbol: str, data: pd.DataFrame) -> Dict[str, Any]:
        """
        分析单个标的的估值
        
        Args:
            symbol: 标的代码
            data: 价格数据
            
        Returns:
            估值分析结果
        """
        try:
            # 只为ETF/基金进行估值分析
            if not self._is_etf_or_fund(symbol):
                return {
                    'applicable': False,
                    'reason': '非ETF/基金资产，不适用价格分位数估值'
                }
            
            if len(data) < 252:  # 至少需要1年数据
                return {
                    'applicable': False,
                    'reason': f'数据不足（{len(data)}天，需要至少252天）'
                }
            
            # 价格分位数分析
            percentile_analysis = self.valuation_analyzer.calculate_price_percentile(
                data,
                lookback_periods=[252, 504, 756]  # 1年、2年、3年
            )
            
            # 均值回归信号
            mean_reversion = self.valuation_analyzer.calculate_mean_reversion_signals(
                data,
                ma_period=20,
                std_multiplier=2.0
            )
            
            # 估值区间
            valuation_zone = self.valuation_analyzer.calculate_valuation_zone(
                data,
                periods=[20, 60, 120, 250]
            )
            
            return {
                'applicable': True,
                'valuation_level': percentile_analysis.get('overall_valuation', '合理'),
                'percentile': percentile_analysis.get('overall_percentile', 50.0),
                'percentile_1y': percentile_analysis.get('percentiles', {}).get('1年', {}).get('percentile', 50.0),
                'percentile_2y': percentile_analysis.get('percentiles', {}).get('2年', {}).get('percentile', 50.0),
                'percentile_3y': percentile_analysis.get('percentiles', {}).get('3年', {}).get('percentile', 50.0),
                'valuation_zone': valuation_zone.get('valuation_zone', '合理区'),
                'ma_trend': valuation_zone.get('ma_trend', '震荡'),
                'mean_reversion_signal': mean_reversion.get('signal', '持有'),
                'mean_reversion_strength': mean_reversion.get('signal_strength', '中等'),
                'bollinger_position': mean_reversion.get('bollinger_position', 50.0),
                'deviation_from_ma': mean_reversion.get('deviation_from_ma_pct', 0.0)
            }
            
        except Exception as e:
            return {
                'applicable': False,
                'reason': f'估值分析失败: {str(e)}'
            }

    def get_portfolio_structure(self) -> Dict[str, Any]:
        """获取投资组合结构信息"""
        logger.info("📊 分析投资组合结构...")

        # 获取USER_REAL_PORTFOLIO配置
        portfolio = self.portfolio_config['portfolios']['USER_REAL_PORTFOLIO']
        meta = self.portfolio_config['portfolio_meta']['USER_REAL_PORTFOLIO']
        sleeves = self.portfolio_config['portfolio_sleeves']['USER_REAL_PORTFOLIO']

        # 分析Sleeve结构
        sleeve_analysis = {}
        total_allocation = 0

        for sleeve in sleeves:
            name = sleeve['name']
            allocation = sleeve['allocation_ratio']
            target_return = sleeve['target_return']
            risk_level = sleeve['risk_level']

            sleeve_value = self.total_value * allocation
            total_allocation += allocation

            sleeve_analysis[name] = {
                'allocation_ratio': allocation,
                'allocation_value': sleeve_value,
                'target_return': target_return,
                'risk_level': risk_level,
                'description': sleeve.get('description', ''),
                'symbols': sleeve.get('symbols', {}),
                'symbol_count': len(sleeve.get('symbols', {}))
            }

        # 计算最终权重分配
        final_weights = {}
        for sleeve in sleeves:
            sleeve_allocation = sleeve['allocation_ratio']
            for symbol, weight in sleeve.get('symbols', {}).items():
                if symbol not in final_weights:
                    final_weights[symbol] = 0
                final_weights[symbol] += sleeve_allocation * weight

        # 按行业分类
        sector_allocation = {}
        for symbol, weight in final_weights.items():
            if weight > 0:
                sector = portfolio.get(symbol, {}).get('sector', 'unknown')
                if sector not in sector_allocation:
                    sector_allocation[sector] = 0
                sector_allocation[sector] += weight

        return {
            'total_value': self.total_value,
            'currency': self.currency,
            'sleeve_count': len(sleeves),
            'total_symbols': len([s for s in final_weights.values() if s > 0]),
            'total_allocation': total_allocation,
            'sleeve_analysis': sleeve_analysis,
            'final_weights': final_weights,
            'sector_allocation': sector_allocation,
            'expected_return': sum(s['target_return'] * s['allocation_ratio'] for s in sleeve_analysis.values())
        }

    def analyze_sleeve_performance(self, start_date: str = None,
                                 end_date: str = None) -> Dict[str, Any]:
        """分析各个Sleeve的表现"""
        # 设置默认日期范围：过去12个月到当前
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")

        logger.info("🎯 分析各Sleeve表现...")
        logger.info("📅 使用日期范围: {start_date} - {end_date}")

        structure = self.get_portfolio_structure()
        sleeve_analysis = structure['sleeve_analysis']

        performance_results = {}

        for sleeve_name, sleeve_info in sleeve_analysis.items():
            logger.info("  分析 {sleeve_name}...")

            symbols = sleeve_info['symbols']
            if not symbols:
                continue

            sleeve_performance = {
                'basic_info': sleeve_info,
                'symbol_performance': {},
                'sleeve_metrics': {}
            }

            # 分析sleeve中每个标的的表现
            sleeve_returns = []
            sleeve_weights = []

            for symbol, weight in symbols.items():
                if symbol == 'CASH':
                    # 现金假设0收益
                    sleeve_performance['symbol_performance'][symbol] = {
                        'total_return': 0.0,
                        'volatility': 0.0,
                        'weight_in_sleeve': weight,
                        'status': 'cash'
                    }
                    sleeve_returns.append(0.0)
                    sleeve_weights.append(weight)
                    continue

                try:
                    # 获取股票数据
                    data = self.data_provider.get_stock_data(symbol, start_date, end_date)

                    if data.empty:
                        logger.info("    ⚠️ {symbol} 无法获取数据")
                        continue

                    # 计算基础指标
                    start_price = data['close'].iloc[0]
                    end_price = data['close'].iloc[-1]
                    total_return = (end_price / start_price - 1) * 100

                    # 计算时间跨度和年化收益率
                    days_span = (data.index[-1] - data.index[0]).days
                    years_span = days_span / 365.25
                    annualized_return = ((end_price / start_price) ** (1/years_span) - 1) * 100 if years_span > 0 else total_return

                    returns = data['close'].pct_change().fillna(0)
                    volatility = returns.std() * np.sqrt(252) * 100
                    
                    # 添加估值分析
                    valuation = self._analyze_symbol_valuation(symbol, data)

                    sleeve_performance['symbol_performance'][symbol] = {
                        'total_return': total_return,
                        'annualized_return': annualized_return,
                        'volatility': volatility,
                        'weight_in_sleeve': weight,
                        'start_price': start_price,
                        'end_price': end_price,
                        'data_points': len(data),
                        'start_date': data.index[0].strftime('%Y-%m-%d'),
                        'end_date': data.index[-1].strftime('%Y-%m-%d'),
                        'time_span_days': days_span,
                        'time_span_years': round(years_span, 2),
                        'valuation': valuation  # 新增估值信息
                    }

                    sleeve_returns.append(total_return)
                    sleeve_weights.append(weight)

                    # 打印收益和估值信息
                    valuation_info = ""
                    if valuation.get('applicable'):
                        val_level = valuation.get('valuation_level', '合理')
                        percentile = valuation.get('percentile', 50.0)
                        valuation_info = f" | 估值:{val_level}({percentile:.1f}%)"                    
                    logger.info("    ✓ {symbol}: 总收益{total_return:.2f}% | 年化{annualized_return:.2f}% | {years_span:.1f}年({days_span}天){valuation_info}")

                except Exception as e:
                    logger.info("    ✗ {symbol}: {e}")
                    continue

            # 计算sleeve整体表现
            if sleeve_returns and sleeve_weights:
                # 加权平均收益率
                weighted_return = np.average(sleeve_returns, weights=sleeve_weights)

                sleeve_performance['sleeve_metrics'] = {
                    'weighted_return': weighted_return,
                    'target_return': sleeve_info['target_return'] * 100,  # 转换为百分比
                    'return_vs_target': weighted_return - (sleeve_info['target_return'] * 100),
                    'successful_symbols': len([r for r in sleeve_returns if r > 0]),
                    'total_symbols': len(sleeve_returns)
                }

            performance_results[sleeve_name] = sleeve_performance

        return performance_results

    def calculate_overall_portfolio_metrics(self, sleeve_performance: Dict[str, Any]) -> Dict[str, Any]:
        """计算投资组合整体指标"""
        logger.info("📈 计算投资组合整体指标...")

        structure = self.get_portfolio_structure()

        # 按sleeve权重计算整体收益
        overall_return = 0
        overall_risk_score = 0
        total_allocation = 0

        sleeve_summary = {}

        for sleeve_name, performance in sleeve_performance.items():
            sleeve_info = structure['sleeve_analysis'][sleeve_name]
            allocation = sleeve_info['allocation_ratio']

            sleeve_metrics = performance.get('sleeve_metrics', {})
            sleeve_return = sleeve_metrics.get('weighted_return', 0)

            # 加权到整体收益
            overall_return += sleeve_return * allocation

            # 风险评分 (简单评估)
            risk_level = sleeve_info['risk_level']
            risk_score = {'conservative': 1, 'income': 2, 'growth': 3, 'aggressive': 4}.get(risk_level, 2)
            overall_risk_score += risk_score * allocation

            total_allocation += allocation

            sleeve_summary[sleeve_name] = {
                'allocation': allocation,
                'value': allocation * self.total_value,
                'return': sleeve_return,
                'target_return': sleeve_info['target_return'] * 100,
                'risk_level': risk_level,
                'performance_vs_target': sleeve_metrics.get('return_vs_target', 0)
            }

        # 整体指标
        overall_metrics = {
            'total_portfolio_return': overall_return,
            'expected_return': structure['expected_return'] * 100,
            'return_vs_expected': overall_return - (structure['expected_return'] * 100),
            'overall_risk_score': overall_risk_score,
            'total_allocation': total_allocation,
            'portfolio_efficiency': overall_return / (structure['expected_return'] * 100) if structure['expected_return'] > 0 else 1
        }

        return {
            'overall_metrics': overall_metrics,
            'sleeve_summary': sleeve_summary
        }

    def generate_rebalancing_recommendations(self, performance_data: Dict[str, Any]) -> List[str]:
        """生成再平衡建议"""
        logger.info("💡 生成再平衡建议...")

        recommendations = []

        overall_metrics = performance_data['overall_metrics']
        sleeve_summary = performance_data['sleeve_summary']

        # 基于整体表现的建议
        portfolio_return = overall_metrics['total_portfolio_return']
        return_vs_expected = overall_metrics['return_vs_expected']

        if return_vs_expected > 5:
            recommendations.append(f"🎉 投资组合表现优异，实际收益{portfolio_return:.2f}%超出预期{abs(return_vs_expected):.2f}%")
        elif return_vs_expected < -5:
            recommendations.append(f"⚠️ 投资组合表现低于预期{abs(return_vs_expected):.2f}%，需要调整策略")

        # 基于各sleeve表现的建议
        best_sleeve = max(sleeve_summary.items(), key=lambda x: x[1]['return'])
        worst_sleeve = min(sleeve_summary.items(), key=lambda x: x[1]['return'])

        recommendations.append(f"🏆 表现最佳Sleeve: {best_sleeve[0]} ({best_sleeve[1]['return']:.2f}%)")
        recommendations.append(f"📉 表现最差Sleeve: {worst_sleeve[0]} ({worst_sleeve[1]['return']:.2f}%)")

        # 具体调整建议
        for sleeve_name, metrics in sleeve_summary.items():
            performance_gap = metrics['performance_vs_target']

            if performance_gap > 10:
                recommendations.append(f"💰 {sleeve_name}: 表现超出目标{performance_gap:.1f}%，考虑部分止盈")
            elif performance_gap < -10:
                recommendations.append(f"📊 {sleeve_name}: 表现低于目标{abs(performance_gap):.1f}%，考虑策略调整")

        # 配置建议
        cash_allocation = sleeve_summary.get('现金组合', {}).get('allocation', 0)
        aggressive_allocation = sleeve_summary.get('进攻组合', {}).get('allocation', 0)

        if cash_allocation > 0.05:
            recommendations.append("💵 现金配置偏高，考虑投入收益性资产")

        if aggressive_allocation > 0.4:
            recommendations.append("⚠️ 激进配置较高，注意风险控制")

        # 市场环境建议
        recommendations.append("📅 建议每季度进行组合再平衡")
        recommendations.append("🔍 关注各sleeve的实际表现，动态调整目标收益率")

        return recommendations

    def create_detailed_report(self, start_date: str = None,
                             end_date: str = None) -> Dict[str, Any]:
        """创建详细分析报告"""
        # 设置默认日期范围
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")

        logger.info("🚀 开始分析用户真实投资组合 (169.5万元)")
        logger.info("📅 分析期间: {start_date} - {end_date}")
        print("=" * 60)

        # 1. 组合结构分析
        structure = self.get_portfolio_structure()

        # 2. Sleeve表现分析
        sleeve_performance = self.analyze_sleeve_performance(start_date, end_date)

        # 3. 整体指标计算
        overall_analysis = self.calculate_overall_portfolio_metrics(sleeve_performance)

        # 4. 再平衡建议
        recommendations = self.generate_rebalancing_recommendations(overall_analysis)

        # 整合结果
        comprehensive_report = {
            'analysis_info': {
                'portfolio_name': 'USER_REAL_PORTFOLIO',
                'total_value': self.total_value,
                'currency': self.currency,
                'analysis_period': f"{start_date} - {end_date}",
                'timestamp': datetime.now().isoformat()
            },
            'portfolio_structure': structure,
            'sleeve_performance': sleeve_performance,
            'overall_analysis': overall_analysis,
            'recommendations': recommendations
        }

        return comprehensive_report

    def print_comprehensive_report(self, report: Dict[str, Any]):
        """打印综合报告"""
        print("\n" + "=" * 80)
        logger.info("📋 用户真实投资组合深度分析报告")
        print("=" * 80)

        # 基本信息
        info = report['analysis_info']
        logger.info("💰 投资组合总价值: {info['total_value']:,} {info['currency']}")
        logger.info("📅 分析期间: {info['analysis_period']}")
        logger.info("🕐 分析时间: {info['timestamp'][:19]}")

        # 投资组合结构
        structure = report['portfolio_structure']
        logger.info("\n🏗️ 投资组合结构:")
        logger.info("  Sleeve数量: {structure['sleeve_count']}")
        logger.info("  投资标的: {structure['total_symbols']} 个")
        logger.info("  预期年化收益: {structure['expected_return']:.2%}")

        # Sleeve配置详情
        logger.info("\n🎯 Sleeve配置详情:")
        for sleeve_name, sleeve_info in structure['sleeve_analysis'].items():
            allocation = sleeve_info['allocation_ratio']
            value = sleeve_info['allocation_value']
            target_return = sleeve_info['target_return']

            logger.info("\n  📊 {sleeve_name}:")
            logger.info("    配置比例: {allocation:.1%}")
            logger.info("    配置金额: {value:,.0f} 元")
            logger.info("    目标收益: {target_return:.1%}")
            logger.info("    风险等级: {sleeve_info['risk_level']}")
            logger.info("    标的数量: {sleeve_info['symbol_count']}")

        # 实际表现分析
        overall = report['overall_analysis']['overall_metrics']
        period = info['analysis_period']
        logger.info("\n📈 实际表现分析 ({period}):")
        logger.info("  ⚠️  注意：以下收益率为总收益率，非年化收益率")
        logger.info("  ⚠️  数据期间：{period}")
        logger.info("  实际收益率: {overall['total_portfolio_return']:.2f}% (总收益)")
        logger.info("  预期收益率: {overall['expected_return']:.2f}% (年化目标)")
        logger.info("  收益偏差: {overall['return_vs_expected']:+.2f}%")
        logger.info("  组合效率: {overall['portfolio_efficiency']:.2f}")

        # 各Sleeve表现
        sleeve_summary = report['overall_analysis']['sleeve_summary']
        logger.info("\n🏆 各Sleeve表现排行:")
        sorted_sleeves = sorted(sleeve_summary.items(),
                               key=lambda x: x[1]['return'], reverse=True)

        for i, (sleeve_name, metrics) in enumerate(sorted_sleeves, 1):
            performance = metrics['performance_vs_target']
            status = "✅" if performance > 0 else "❌" if performance < -5 else "⚡"

            print(f"  {i}. {status} {sleeve_name:12}: "
                  f"{metrics['return']:6.2f}% (目标: {metrics['target_return']:5.1f}%, "
                  f"偏差: {performance:+.1f}%)")

        # 行业分布
        sector_allocation = structure['sector_allocation']
        logger.info("\n🏭 资产类别分布:")
        sorted_sectors = sorted(sector_allocation.items(),
                               key=lambda x: x[1], reverse=True)

        for sector, allocation in sorted_sectors:
            if allocation > 0.01:  # 只显示占比>1%的
                value = allocation * self.total_value
                logger.info("  {sector:15}: {allocation:6.1%} = {value:8,.0f} 元")

        # 投资建议
        logger.info("\n💡 投资建议:")
        for i, recommendation in enumerate(report['recommendations'], 1):
            logger.info("  {i}. {recommendation}")

        print("\n" + "=" * 80)

    def save_analysis_report(self, report: Dict[str, Any], filename: str = None,
                             write_markdown: bool = True,
                             use_dated_subdir: bool = True) -> Dict[str, str]:
        """保存分析报告

        Args:
            report: 综合分析结果
            filename: 可选的自定义JSON文件名
            write_markdown: 是否同时输出Markdown可读报告
            use_dated_subdir: 是否使用按日期分类的子目录（reports/portfolio/YYYYMMDD）

        Returns:
            包含 'json' 和可选 'markdown' 路径的字典
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        date_part = datetime.now().strftime("%Y%m%d")

        # 组织输出目录：reports/portfolio/YYYYMMDD/
        base_dir = Path(self.config.reports_dir)
        if use_dated_subdir:
            out_dir = base_dir / 'portfolio' / date_part
        else:
            out_dir = base_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        # JSON 文件名
        if filename is None:
            filename = f"user_real_portfolio_analysis_{timestamp}.json"
        json_path = out_dir / filename

        # 序列化处理
        serializable_report = self._make_serializable(report)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_report, f, ensure_ascii=False, indent=2)

        logger.info("✅ JSON 报告已保存到: {json_path}")

        paths = {'json': str(json_path)}

        # Markdown 输出
        if write_markdown:
            md_name = f"portfolio_USER_REAL_PORTFOLIO_{timestamp}_report.md"
            md_path = out_dir / md_name
            md_content = self._format_as_markdown(report)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            logger.info("✅ Markdown 报告已保存到: {md_path}")
            paths['markdown'] = str(md_path)

        return paths

    def _format_as_markdown(self, report: Dict[str, Any]) -> str:
        """将综合分析结果格式化为Markdown文本"""
        info = report.get('analysis_info', {})
        structure = report.get('portfolio_structure', {})
        overall = report.get('overall_analysis', {}).get('overall_metrics', {})
        sleeve_summary = report.get('overall_analysis', {}).get('sleeve_summary', {})
        sector_allocation = structure.get('sector_allocation', {})
        sleeve_perf = report.get('sleeve_performance', {})

        # 建立 symbol -> name 的映射，优先使用组合配置中的名称
        symbol_to_name: Dict[str, str] = {}
        try:
            user_port = self.portfolio_config.get('portfolios', {}).get('USER_REAL_PORTFOLIO', {})
            for sym, meta in (user_port or {}).items():
                if isinstance(meta, dict) and meta.get('name'):
                    symbol_to_name[sym] = str(meta.get('name'))
        except Exception:
            pass

        lines: List[str] = []
        lines.append(f"# 用户真实投资组合深度分析报告")
        lines.append("")
        lines.append(f"- 组合: USER_REAL_PORTFOLIO")
        lines.append(f"- 总价值: {info.get('total_value', 0):,} {info.get('currency', 'CNY')}")
        lines.append(f"- 分析期间: {info.get('analysis_period', '-')}")
        lines.append(f"- 生成时间: {info.get('timestamp', '')[:19]}")
        lines.append("")

        # 结构
        lines.append("## 组合结构")
        lines.append(f"- Sleeve 数量: {structure.get('sleeve_count', 0)}")
        lines.append(f"- 投资标的数: {structure.get('total_symbols', 0)}")
        lines.append(f"- 预期年化收益: {structure.get('expected_return', 0.0):.2%}")
        lines.append("")

        lines.append("### Sleeve 配置")
        for sname, sinfo in structure.get('sleeve_analysis', {}).items():
            lines.append(f"- {sname}")
            lines.append(f"  - 配置比例: {sinfo.get('allocation_ratio', 0.0):.1%}")
            lines.append(f"  - 配置金额: {sinfo.get('allocation_value', 0.0):,.0f} 元")
            lines.append(f"  - 目标收益: {sinfo.get('target_return', 0.0):.1%}")
            lines.append(f"  - 风险等级: {sinfo.get('risk_level', 'unknown')}")
            lines.append(f"  - 标的数量: {sinfo.get('symbol_count', 0)}")
        lines.append("")

        # 实际表现与袖套贡献
        lines.append("## 实际表现（区间总收益）")
        lines.append(f"- 实际收益率: {overall.get('total_portfolio_return', 0.0):.2f}%")
        lines.append(f"- 预期收益率: {overall.get('expected_return', 0.0):.2f}%")
        lines.append(f"- 收益偏差: {overall.get('return_vs_expected', 0.0):+.2f}%")
        lines.append(f"- 组合效率: {overall.get('portfolio_efficiency', 0.0):.2f}")
        lines.append("")

        # Sleeve表现排行与贡献
        lines.append("### 各Sleeve表现与贡献")
        sorted_sleeves = sorted(sleeve_summary.items(), key=lambda x: x[1].get('return', 0), reverse=True)
        underperf = []
        for i, (sname, metrics) in enumerate(sorted_sleeves, 1):
            alloc = metrics.get('allocation', 0.0)
            sleeve_return = metrics.get('return', 0.0)
            contribution = alloc * sleeve_return / 100.0  # 贡献为权重*收益（百分比→小数）
            tgt = metrics.get('target_return', 0.0)
            delta = metrics.get('performance_vs_target', 0.0)
            lines.append(f"{i}. {sname}: {sleeve_return:.2f}% (目标: {tgt:.1f}%, 偏差: {delta:+.1f}%) | 对组合贡献: {contribution*100:.2f}%")
            if delta < -5.0:
                underperf.append((sname, delta))
        lines.append("")

        if underperf:
            lines.append("> 需关注：以下Sleeve低于目标较多（<-5%）")
            for sname, delta in sorted(underperf, key=lambda x: x[1]):
                lines.append(f"- {sname}: 偏差 {delta:+.1f}%")
            lines.append("")

        # 行业/资产类别分布
        lines.append("。## 资产类别分布")
        for sector, alloc in sorted(sector_allocation.items(), key=lambda x: x[1], reverse=True):
            if alloc > 0.001:
                value = alloc * float(info.get('total_value', 0))
                lines.append(f"- {sector}: {alloc:.1%} ≈ {value:,.0f} 元")
        lines.append("")
        
        # 估值汇总章节
        lines.append("。## 💰 ETF/基金估值汇总")
        lines.append("")
        
        # 收集所有有估值数据的标的
        valuation_summary = []
        for sname, sperf in sleeve_perf.items():
            symbols_perf = sperf.get('symbol_performance', {}) or {}
            for symbol, sp in symbols_perf.items():
                valuation = sp.get('valuation', {})
                if valuation.get('applicable'):
                    nm = symbol_to_name.get(symbol, symbol)
                    valuation_summary.append({
                        'symbol': symbol,
                        'name': nm,
                        'sleeve': sname,
                        'valuation_level': valuation.get('valuation_level', '合理'),
                        'percentile': valuation.get('percentile', 50.0),
                        'zone': valuation.get('valuation_zone', '合理区'),
                        'signal': valuation.get('mean_reversion_signal', '持有')
                    })
        
        if valuation_summary:
            # 按估值水平分组
            undervalued = [v for v in valuation_summary if v['valuation_level'] in ['极度低估', '低估', '偏低']]
            reasonable = [v for v in valuation_summary if v['valuation_level'] == '合理']
            overvalued = [v for v in valuation_summary if v['valuation_level'] in ['极度高估', '高估', '偏高']]
            
            lines.append(f"> 共分析 {len(valuation_summary)} 只 ETF/基金的估值水平")
            lines.append("")
            
            if undervalued:
                lines.append(f"### 💚 低估机会 ({len(undervalued)}只)")
                for v in sorted(undervalued, key=lambda x: x['percentile']):
                    lines.append(f"- **{v['symbol']} {v['name']}** [{v['sleeve']}]")
                    lines.append(f"  - 估值: {v['valuation_level']} (分位数: {v['percentile']:.1f}%)")
                    lines.append(f"  - 区间: {v['zone']} | 信号: {v['signal']}")
                lines.append("")
            
            if overvalued:
                lines.append(f"### ⚠️ 高估警告 ({len(overvalued)}只)")
                for v in sorted(overvalued, key=lambda x: x['percentile'], reverse=True):
                    lines.append(f"- **{v['symbol']} {v['name']}** [{v['sleeve']}]")
                    lines.append(f"  - 估值: {v['valuation_level']} (分位数: {v['percentile']:.1f}%)")
                    lines.append(f"  - 区间: {v['zone']} | 信号: {v['signal']}")
                lines.append("")
            
            if reasonable:
                lines.append(f"### ✅ 合理估值 ({len(reasonable)}只)")
                lines.append("> 以下标的估值处于合理区间")
                for v in reasonable:
                    lines.append(f"- {v['symbol']} {v['name']} (分位数: {v['percentile']:.1f}%)")
                lines.append("")
        else:
            lines.append("> 暂无ETF/基金估值数据（需要至少1年以上历史数据）")
            lines.append("")

        # 计算标的层面的贡献（基于sleeve权重*标的权重*标的区间收益）
        lines.append("## 标的贡献与拖累（Top/Bottom）")
        symbol_contrib = []  # (symbol, name, sleeve, overall_weight, total_return, contribution)
        # 构造 sleeve 配置查找
        sleeve_alloc_map = {k: v.get('allocation_ratio', 0.0) for k, v in structure.get('sleeve_analysis', {}).items()}
        # 遍历每个sleeve的标的表现
        for sname, sperf in sleeve_perf.items():
            symbols_perf = sperf.get('symbol_performance', {}) or {}
            alloc = sleeve_alloc_map.get(sname, 0.0)
            # 原始定义中的权重在结构里
            s_symbols = structure.get('sleeve_analysis', {}).get(sname, {}).get('symbols', {}) or {}
            for symbol, sp in symbols_perf.items():
                total_return = float(sp.get('total_return', 0.0))
                w_in_sleeve = float(sp.get('weight_in_sleeve', s_symbols.get(symbol, 0.0)))
                overall_weight = alloc * w_in_sleeve
                contribution = overall_weight * (total_return / 100.0)
                name = symbol_to_name.get(symbol, symbol)
                symbol_contrib.append((symbol, name, sname, overall_weight, total_return, contribution))

        # 排序并输出Top/Bottom
        if symbol_contrib:
            top = sorted(symbol_contrib, key=lambda x: x[5], reverse=True)[:5]
            bottom = sorted(symbol_contrib, key=lambda x: x[5])[:5]
            lines.append("### Top 贡献 (前5)")
            for sym, name, sname, w, r, c in top:
                lines.append(f"- {sym} {name} [{sname}]: 收益 {r:.2f}% | 组合权重 {w*100:.2f}% | 贡献 {c*100:.2f}%")
            lines.append("")
            lines.append("### 拖累标的 (前5)")
            for sym, name, sname, w, r, c in bottom:
                lines.append(f"- {sym} {name} [{sname}]: 收益 {r:.2f}% | 组合权重 {w*100:.2f}% | 贡献 {c*100:.2f}%")
            lines.append("")

        # 分Sleeve列出明细(包含估值)
        lines.append("## 分Sleeve标的明细")
        for sname, sperf in sleeve_perf.items():
            lines.append(f"### {sname}")
            alloc = sleeve_alloc_map.get(sname, 0.0)
            symbols_perf = sperf.get('symbol_performance', {}) or {}
            defined_symbols = set((structure.get('sleeve_analysis', {}).get(sname, {}).get('symbols', {}) or {}).keys())
            seen = set()
            for symbol, sp in sorted(symbols_perf.items(), key=lambda kv: kv[1].get('weight_in_sleeve', 0), reverse=True):
                seen.add(symbol)
                r = float(sp.get('total_return', 0.0))
                ar = float(sp.get('annualized_return', 0.0))
                vol = float(sp.get('volatility', 0.0))
                w_in = float(sp.get('weight_in_sleeve', 0.0))
                w_overall = alloc * w_in
                contrib = w_overall * (r/100.0)
                nm = symbol_to_name.get(symbol, symbol)
                
                # 添加估值信息
                valuation = sp.get('valuation', {})
                val_info = ""
                if valuation.get('applicable'):
                    val_level = valuation.get('valuation_level', '合理')
                    percentile = valuation.get('percentile', 50.0)
                    val_zone = valuation.get('valuation_zone', '合理区')
                    val_info = f" | 估值: {val_level}({percentile:.1f}%) {val_zone}"
                
                lines.append(f"- {symbol} {nm}: 收益 {r:.2f}% | 年化 {ar:.2f}% | 波动 {vol:.2f}% | Sleeve权重 {w_in*100:.2f}% | 组合权重 {w_overall*100:.2f}% | 贡献 {contrib*100:.2f}%{val_info}")
            # 缺数据标的
            missing = sorted(list(defined_symbols - seen))
            if missing:
                lines.append("> 缺少行情数据（未计入收益）：" + ", ".join(missing))
            lines.append("")

        # 建议
        lines.append("## 投资建议")
        for idx, rec in enumerate(report.get('recommendations', []), 1):
            lines.append(f"{idx}. {rec}")
        lines.append("")

        return "\n".join(lines)

    def _make_serializable(self, obj):
        """使对象可序列化"""
        if isinstance(obj, dict):
            return {str(k): self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        elif isinstance(obj, (pd.Timestamp, datetime)):
            return str(obj)
        elif isinstance(obj, (np.int64, np.int32, np.float64, np.float32)):
            return float(obj)
        elif pd.isna(obj) or obj is None:
            return None
        else:
            return obj


def main():
    """主函数"""
    try:
        # 创建分析器
        analyzer = UserRealPortfolioAnalyzer()

        # 生成综合分析报告（使用动态日期范围）
        report = analyzer.create_detailed_report()

        # 打印综合报告
        analyzer.print_comprehensive_report(report)

        # 保存报告
        analyzer.save_analysis_report(report)

    except Exception as e:
        logger.error(f"❌ 分析失败: {e}")
        logger.exception("详细错误信息:")


if __name__ == '__main__':
    main()
