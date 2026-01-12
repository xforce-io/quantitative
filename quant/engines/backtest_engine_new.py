#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
重构后的回测引擎
Refactored Backtest Engine

简化的回测引擎，只负责编排各个组件
"""

import logging
from typing import Dict, Any, Optional

from .backtest_validator import BacktestValidator
from .backtest_executor import BacktestExecutor, BacktestResult
from .backtest_analyzer import BacktestAnalyzer

from ..data.providers import DataProvider
from ..strategies.base_strategy import BaseStrategy
from ..core.exceptions import (
    BacktestError,
    BacktestValidationError,
    BacktestExecutionError,
)

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    重构后的回测引擎

    职责：
    1. 编排各个组件
    2. 协调数据获取、参数验证、回测执行、结果分析的流程
    3. 错误处理和日志记录
    """

    def __init__(self, data_provider: DataProvider, default_config: Dict = None):
        """
        初始化回测引擎

        Args:
            data_provider: 数据提供者
            default_config: 默认配置
        """
        self.data_provider = data_provider
        self.default_config = default_config or {}

        # 初始化各个组件
        self.validator = BacktestValidator()
        self.executor = BacktestExecutor()
        self.analyzer = BacktestAnalyzer()

        # 存储结果
        self.results = {}

        logger.info("BacktestEngine initialized")

    def run(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        strategy: BaseStrategy,
        initial_capital: float = 100000,
        strategy_config: Dict = None
    ) -> Dict[str, Any]:
        """
        运行回测（简化版本）

        Args:
            symbol: 股票代码
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            strategy: 策略实例
            initial_capital: 初始资金
            strategy_config: 策略配置（可选）

        Returns:
            dict: 回测结果字典

        Raises:
            BacktestValidationError: 参数验证失败
            BacktestExecutionError: 回测执行失败
        """
        logger.info(f"{'='*80}")
        logger.info(f"开始回测: {symbol} | {start_date} - {end_date} | ¥{initial_capital:,.0f}")
        logger.info(f"{'='*80}")

        try:
            # 1. 参数验证
            self.validator.validate_params(
                symbol, start_date, end_date, initial_capital, strategy
            )
            if strategy_config:
                self.validator.validate_strategy_config(strategy_config)

            # 2. 获取数据
            stock_data = self.data_provider.get_stock_data(
                symbol, start_date, end_date
            )

            # 3. 数据验证
            self.validator.validate_data(stock_data, symbol, start_date, end_date)

            # 4. 执行回测
            trades, portfolio_values, positions, cash_values = self.executor.execute(
                strategy, stock_data, initial_capital
            )

            # 5. 分析结果
            metrics = self.analyzer.calculate_metrics(
                stock_data, portfolio_values, trades, initial_capital, strategy
            )

            # 6. 创建结果对象
            result = self.executor.create_result(
                symbol, start_date, end_date, initial_capital,
                stock_data, trades, portfolio_values, positions,
                cash_values, strategy
            )

            # 7. 构建返回字典
            result_dict = {
                'symbol': symbol,
                'startDate': start_date,
                'endDate': end_date,
                'initialCapital': initial_capital,
                'stockData': stock_data,
                'portfolioValues': portfolio_values,
                'positions': positions,
                'cashValues': cash_values,
                'trades': trades,
                'performance': metrics,
                'strategy': strategy,
                'gridAdjustments': result.grid_adjustments
            }

            # 存储结果
            self.results[symbol] = result_dict

            # 打印摘要
            self._print_summary(result_dict, strategy_config)

            return result_dict

        except (BacktestValidationError, BacktestExecutionError) as e:
            logger.error(f"Backtest failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during backtest: {e}", exc_info=True)
            raise BacktestError(f"Backtest failed: {str(e)}")

    def _print_summary(self, result: Dict, strategy_config: Dict = None):
        """打印回测摘要"""
        perf = result['performance']
        symbol = result['symbol']

        # 提取策略参数
        dynamic_enabled = strategy_config.get('dynamicEnabled', True) if strategy_config else True
        grid_levels = strategy_config.get('gridLevels', 'N/A') if strategy_config else 'N/A'
        grid_spacing = strategy_config.get('gridSpacing', 0) if strategy_config else 0
        base_ratio = strategy_config.get('baseRatio', 0) if strategy_config else 0
        grid_adjustments_count = len(result.get('gridAdjustments', []))

        # 输出摘要
        logger.info(
            f"✅ 回测完成 {symbol} | "
            f"总收益: {perf.get('totalReturn', 0):+.2%} | "
            f"交易: {perf.get('totalTrades', 0)}次 | "
            f"胜率: {perf.get('winRate', 0):.1%}"
        )

        if grid_levels != 'N/A':
            logger.info(
                f"📊 策略参数 | "
                f"动态调整: {'启用' if dynamic_enabled else '禁用'} | "
                f"网格: {grid_levels}层 {grid_spacing:.1%}间距 | "
                f"基础仓位: {base_ratio:.1%} | "
                f"网格调整: {grid_adjustments_count}次"
            )

        logger.info(f"{'='*80}")

    def get_result(self, symbol: str) -> Optional[Dict]:
        """
        获取指定股票的回测结果

        Args:
            symbol: 股票代码

        Returns:
            dict: 回测结果，如果不存在返回None
        """
        return self.results.get(symbol)

    def generate_report(self, symbol: str = None) -> str:
        """
        生成回测报告

        Args:
            symbol: 股票代码，None表示生成所有结果的报告

        Returns:
            str: 报告文本
        """
        if symbol and symbol in self.results:
            results_to_report = [self.results[symbol]]
        else:
            results_to_report = list(self.results.values())

        if not results_to_report:
            return "No backtest results available"

        report_parts = ["="*80, "回测报告", "="*80, ""]

        for result in results_to_report:
            report_parts.append(
                self.analyzer.format_summary(
                    result['performance'],
                    result['symbol']
                )
            )

        return "\n".join(report_parts)

    def clear_results(self):
        """清空所有回测结果"""
        self.results.clear()
        logger.info("All backtest results cleared")


# 向后兼容：创建旧接口的适配器
def create_backtest_engine(data_provider, config: Dict = None) -> BacktestEngine:
    """
    创建回测引擎实例

    Args:
        data_provider: 数据提供者
        config: 配置字典

    Returns:
        BacktestEngine: 回测引擎实例
    """
    return BacktestEngine(data_provider, config)
