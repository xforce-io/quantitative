#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Advisor 功能桥接工具 - 基于新架构
Advisor Bridge Tool - Based on New Architecture

为原有advisor功能提供新架构下的统一入口
"""

import sys
import argparse
from pathlib import Path
from typing import List, Optional, Dict, Any
import json
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 使用新架构的组件
from quant.core.config import get_config
from quant.data.providers import create_data_provider
from quant.strategies import STRATEGY_REGISTRY
from quant.engines.backtest_engine import BacktestEngine

# 导入分析工具
try:
    from quant.analysis.advisor.unified_advisor import UnifiedAdvisor
    from quant.analysis.advisor.investment_advisor import InvestmentAdvisor
except ImportError:
    # 回退处理
    UnifiedAdvisor = None
    InvestmentAdvisor = None

class AdvisorBridge:
    """Advisor功能桥接器"""

    def __init__(self):
        self.config = get_config()
        self.data_provider = create_data_provider('auto', self.config.get_providers_config())

    def single_analysis(self, symbol: str, days_back: int = 2500) -> Dict[str, Any]:
        """
        单标的深度分析
        等同于: python advisor.py --mode single --symbol SYMBOL
        """
        logger.info("🎯 单标的深度分析模式")
        logger.info("📊 标的: {symbol}")
        print("=" * 60)

        try:
            # 获取数据
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - pd.Timedelta(days=days_back)).strftime("%Y%m%d")

            data = self.data_provider.get_stock_data(symbol, start_date, end_date)

            if data.empty:
                return {
                    'symbol': symbol,
                    'error': 'No data available',
                    'success': False
                }

            # 基础分析
            start_price = data['close'].iloc[0]
            end_price = data['close'].iloc[-1]
            total_return = (end_price / start_price - 1) * 100

            # 技术分析
            from quant.core.indicators import TechnicalIndicators
            tech_data = pd.DataFrame({
                'close': data['close'],
                'high': data['high'],
                'low': data['low'],
                'open': data['open'],
                'volume': data['volume']
            })

            indicators = TechnicalIndicators.calculate_all_indicators(tech_data)

            # 策略分析
            strategy_results = {}
            for strategy_name in ['ma_crossover', 'momentum', 'unified_grid']:
                if strategy_name in STRATEGY_REGISTRY:
                    try:
                        strategy_config = self.config.get_strategy_config(strategy_name)
                        strategy_class = STRATEGY_REGISTRY[strategy_name]
                        strategy = strategy_class(symbol, strategy_config)

                        # 简化的策略评估
                        buy_hold_return = (data['close'].iloc[-1] / data['close'].iloc[0] - 1) * 100

                        strategy_results[strategy_name] = {
                            'buy_hold_return': buy_hold_return,
                            'data_points': len(data),
                            'recommendation': 'suitable' if buy_hold_return > 0 else 'not_recommended'
                        }
                    except Exception as e:
                        strategy_results[strategy_name] = {'error': str(e)}

            result = {
                'symbol': symbol,
                'mode': 'single',
                'analysis_time': datetime.now().isoformat(),
                'success': True,
                'basic_metrics': {
                    'total_return': total_return,
                    'start_price': start_price,
                    'end_price': end_price,
                    'data_points': len(data)
                },
                'technical_indicators': {
                    'rsi': indicators.get('rsi', pd.Series()).iloc[-1] if 'rsi' in indicators else None,
                    'ma5': indicators.get('ma5', pd.Series()).iloc[-1] if 'ma5' in indicators else None,
                    'ma20': indicators.get('ma20', pd.Series()).iloc[-1] if 'ma20' in indicators else None,
                },
                'strategy_analysis': strategy_results
            }

            # 打印分析结果
            self._print_single_analysis(result)

            return result

        except Exception as e:
            error_result = {
                'symbol': symbol,
                'mode': 'single',
                'error': str(e),
                'success': False
            }
            logger.info("❌ 分析失败: {e}")
            return error_result

    def comprehensive_analysis(self, symbol: str) -> Dict[str, Any]:
        """
        综合分析（深度分析+策略回测）
        等同于: python advisor.py --mode comprehensive --symbol SYMBOL
        """
        logger.info("🚀 综合分析模式")
        logger.info("📊 标的: {symbol}")
        print("=" * 60)

        try:
            # 1. 单标的分析
            single_result = self.single_analysis(symbol, days_back=1000)

            if not single_result.get('success', False):
                return single_result

            # 2. 策略回测分析
            backtest_results = {}

            for strategy_name in ['ma_crossover', 'momentum', 'unified_grid']:
                if strategy_name in STRATEGY_REGISTRY:
                    try:
                        logger.info("\n🎯 回测策略: {strategy_name}")

                        strategy_config = self.config.get_strategy_config(strategy_name)
                        strategy_class = STRATEGY_REGISTRY[strategy_name]
                        strategy = strategy_class(symbol, strategy_config)

                        # 创建回测引擎
                        engine = BacktestEngine('auto')

                        # 运行回测
                        backtest_result = engine.runBacktest(symbol, '20240101', '20241201', initialCapital=100000)
                        backtest_results[strategy_name] = backtest_result

                        logger.info("✓ {strategy_name} 回测完成")

                    except Exception as e:
                        logger.info("✗ {strategy_name} 回测失败: {e}")
                        backtest_results[strategy_name] = {'error': str(e)}

            # 3. 综合评估
            comprehensive_result = {
                'symbol': symbol,
                'mode': 'comprehensive',
                'analysis_time': datetime.now().isoformat(),
                'success': True,
                'single_analysis': single_result,
                'backtest_results': backtest_results,
                'recommendation': self._generate_comprehensive_recommendation(single_result, backtest_results)
            }

            # 打印综合分析结果
            self._print_comprehensive_analysis(comprehensive_result)

            return comprehensive_result

        except Exception as e:
            error_result = {
                'symbol': symbol,
                'mode': 'comprehensive',
                'error': str(e),
                'success': False
            }
            logger.info("❌ 综合分析失败: {e}")
            return error_result

    def portfolio_analysis(self, symbols: List[str]) -> Dict[str, Any]:
        """
        投资组合策略分析
        等同于: python advisor.py --mode portfolio --symbols SYMBOL1,SYMBOL2,SYMBOL3
        """
        logger.info("📊 投资组合策略分析模式")
        logger.info("📋 标的: {', '.join(symbols)}")
        print("=" * 60)

        portfolio_results = {}

        for symbol in symbols:
            logger.info("\n分析 {symbol}...")
            result = self.single_analysis(symbol, days_back=500)
            portfolio_results[symbol] = result

        # 组合分析
        portfolio_summary = self._analyze_portfolio_correlation(portfolio_results)

        comprehensive_result = {
            'mode': 'portfolio',
            'symbols': symbols,
            'analysis_time': datetime.now().isoformat(),
            'individual_analysis': portfolio_results,
            'portfolio_summary': portfolio_summary,
            'success': True
        }

        # 打印组合分析结果
        self._print_portfolio_analysis(comprehensive_result)

        return comprehensive_result

    def _print_single_analysis(self, result: Dict[str, Any]):
        """打印单标的分析结果"""
        if not result.get('success', False):
            return

        symbol = result['symbol']
        metrics = result['basic_metrics']
        indicators = result['technical_indicators']

        logger.info("\n📈 {symbol} 分析结果:")
        logger.info("  总收益率: {metrics['total_return']:+.2f}%")
        logger.info("  当前价格: {metrics['end_price']:.2f}")
        logger.info("  数据点数: {metrics['data_points']}")

        if indicators.get('rsi'):
            logger.info("  RSI: {indicators['rsi']:.1f}")

        logger.info("\n🎯 策略适用性:")
        strategy_analysis = result.get('strategy_analysis', {})
        for strategy, analysis in strategy_analysis.items():
            if 'error' not in analysis:
                rec = analysis.get('recommendation', 'unknown')
                logger.info("  {strategy}: {rec}")

    def _print_comprehensive_analysis(self, result: Dict[str, Any]):
        """打印综合分析结果"""
        symbol = result['symbol']
        single_analysis = result['single_analysis']
        backtest_results = result['backtest_results']
        recommendation = result['recommendation']

        logger.info("\n🎯 {symbol} 综合分析总结:")

        # 基础表现
        metrics = single_analysis.get('basic_metrics', {})
        logger.info("  基础表现: {metrics.get('total_return', 0):+.2f}%")

        # 策略回测结果
        logger.info("\n📊 策略回测结果:")
        for strategy, backtest in backtest_results.items():
            if 'error' not in backtest:
                total_return = backtest.get('total_return', 0)
                logger.info("  {strategy}: {total_return:+.2f}%")

        # 综合建议
        logger.info("\n💡 投资建议: {recommendation}")

    def _print_portfolio_analysis(self, result: Dict[str, Any]):
        """打印组合分析结果"""
        symbols = result['symbols']
        portfolio_summary = result['portfolio_summary']

        logger.info("\n📊 投资组合分析总结:")
        logger.info("  组合标的: {len(symbols)} 个")
        logger.info("  平均收益: {portfolio_summary.get('average_return', 0):.2f}%")
        logger.info("  收益分散: {portfolio_summary.get('return_std', 0):.2f}%")

        logger.info("\n🏆 表现排行:")
        individual_analysis = result['individual_analysis']
        sorted_symbols = sorted(individual_analysis.items(),
                               key=lambda x: x[1].get('basic_metrics', {}).get('total_return', 0),
                               reverse=True)

        for i, (symbol, analysis) in enumerate(sorted_symbols, 1):
            if analysis.get('success', False):
                return_rate = analysis.get('basic_metrics', {}).get('total_return', 0)
                logger.info("  {i}. {symbol}: {return_rate:+.2f}%")

    def _generate_comprehensive_recommendation(self, single_result: Dict[str, Any],
                                             backtest_results: Dict[str, Any]) -> str:
        """生成综合建议"""
        total_return = single_result.get('basic_metrics', {}).get('total_return', 0)

        # 策略表现统计
        strategy_returns = []
        for strategy, result in backtest_results.items():
            if 'error' not in result:
                strategy_returns.append(result.get('total_return', 0))

        if not strategy_returns:
            return "数据不足，建议进一步分析"

        avg_strategy_return = sum(strategy_returns) / len(strategy_returns)

        if total_return > 20 and avg_strategy_return > 15:
            return "强烈推荐 - 基础表现和策略回测均优秀"
        elif total_return > 10 or avg_strategy_return > 10:
            return "推荐 - 具有投资价值"
        elif total_return > 0:
            return "中性 - 可适当配置"
        else:
            return "不推荐 - 表现不佳，建议观望"

    def _analyze_portfolio_correlation(self, portfolio_results: Dict[str, Any]) -> Dict[str, Any]:
        """分析组合相关性"""
        returns = []
        successful_symbols = []

        for symbol, result in portfolio_results.items():
            if result.get('success', False):
                return_rate = result.get('basic_metrics', {}).get('total_return', 0)
                returns.append(return_rate)
                successful_symbols.append(symbol)

        if not returns:
            return {'error': 'No successful analysis'}

        import numpy as np

        return {
            'successful_count': len(successful_symbols),
            'average_return': np.mean(returns),
            'return_std': np.std(returns),
            'best_performer': successful_symbols[np.argmax(returns)] if returns else None,
            'worst_performer': successful_symbols[np.argmin(returns)] if returns else None
        }


def main():
    """主函数 - 提供与原advisor.py相同的命令行接口"""
    parser = argparse.ArgumentParser(description='投资顾问统一入口 - 新架构版本')

    parser.add_argument('--mode', choices=['single', 'comprehensive', 'portfolio'],
                       required=True, help='分析模式')
    parser.add_argument('--symbol', help='股票代码（单标的分析）')
    parser.add_argument('--symbols', help='股票代码列表（逗号分隔）')
    parser.add_argument('--days-back', type=int, default=2500, help='历史数据天数')
    parser.add_argument('--save', help='保存结果到文件')

    args = parser.parse_args()

    # 创建桥接器
    bridge = AdvisorBridge()

    try:
        # 根据模式执行相应分析
        if args.mode == 'single':
            if not args.symbol:
                logger.info("❌ 单标的分析需要提供 --symbol 参数")
                return

            result = bridge.single_analysis(args.symbol, args.days_back)

        elif args.mode == 'comprehensive':
            if not args.symbol:
                logger.info("❌ 综合分析需要提供 --symbol 参数")
                return

            result = bridge.comprehensive_analysis(args.symbol)

        elif args.mode == 'portfolio':
            if not args.symbols:
                logger.info("❌ 组合分析需要提供 --symbols 参数")
                return

            symbols_list = [s.strip() for s in args.symbols.split(',')]
            result = bridge.portfolio_analysis(symbols_list)

        # 保存结果
        if args.save and result:
            save_path = Path(args.save)
            save_path.parent.mkdir(exist_ok=True)

            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)

            logger.info("\n✅ 分析结果已保存到: {save_path}")

    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断分析")
    except Exception as e:
        logger.info("\n❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()


import pandas as pd

from quant.core.logging_config import get_logger
logger = get_logger(__name__)


if __name__ == '__main__':
    main()


# 提供便捷的导入接口
__all__ = ['AdvisorBridge']