#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
回测执行器
Backtest Executor

负责执行具体的回测逻辑
"""

import logging
from typing import List, Tuple
from dataclasses import dataclass

import pandas as pd

from ..strategies.base_strategy import MarketState, TradingDecision
from ..core.exceptions import BacktestExecutionError

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """回测结果数据类"""
    symbol: str
    start_date: str
    end_date: str
    initial_capital: float
    stock_data: pd.DataFrame
    portfolio_values: List[float]
    positions: List[float]
    cash_values: List[float]
    trades: List
    strategy: object
    grid_adjustments: List = None

    def __post_init__(self):
        if self.grid_adjustments is None:
            self.grid_adjustments = []


class BacktestExecutor:
    """回测执行器"""

    def execute(
        self,
        strategy,
        stock_data: pd.DataFrame,
        initial_capital: float
    ) -> Tuple[List, List[float], List[float], List[float]]:
        """
        执行回测

        Args:
            strategy: 策略实例
            stock_data: 股票数据
            initial_capital: 初始资金

        Returns:
            Tuple: (trades, portfolio_values, positions, cash_values)

        Raises:
            BacktestExecutionError: 回测执行错误
        """
        try:
            # 重置策略
            strategy.reset(initial_capital)

            # 如果策略支持网格设置，进行初始化
            if hasattr(strategy, 'setupGrids'):
                self._setup_grid_strategy(strategy, stock_data)

            # 执行回测循环
            portfolio_values = []
            positions = []
            cash_values = []

            for timestamp, row in stock_data.iterrows():
                try:
                    # 根据策略接口类型执行
                    if hasattr(strategy, 'makeDecision'):
                        portfolio_value = self._execute_new_strategy(
                            strategy, timestamp, row
                        )
                    elif hasattr(strategy, 'onMarketData'):
                        portfolio_value = self._execute_legacy_strategy(
                            strategy, timestamp, row
                        )
                    else:
                        raise BacktestExecutionError(
                            f"Strategy {strategy.__class__.__name__} has unknown interface",
                            {'strategy_class': strategy.__class__.__name__}
                        )

                    # 记录每日数据
                    portfolio_values.append(portfolio_value)

                    if hasattr(strategy, 'position'):
                        positions.append(strategy.position)
                        cash_values.append(strategy.cash)
                    elif hasattr(strategy, 'currentPosition'):
                        positions.append(strategy.currentPosition)
                        cash_values.append(strategy.currentCash)
                    else:
                        positions.append(0)
                        cash_values.append(initial_capital)

                except Exception as e:
                    logger.error(f"Error at {timestamp}: {e}")
                    raise BacktestExecutionError(
                        f"Failed to process market data at {timestamp}",
                        {'timestamp': str(timestamp), 'error': str(e)}
                    )

            return strategy.trades, portfolio_values, positions, cash_values

        except BacktestExecutionError:
            raise
        except Exception as e:
            raise BacktestExecutionError(
                f"Backtest execution failed: {str(e)}",
                {'error_type': type(e).__name__, 'error': str(e)}
            )

    def _setup_grid_strategy(self, strategy, stock_data: pd.DataFrame):
        """
        设置网格交易策略

        Args:
            strategy: 策略实例
            stock_data: 股票数据
        """
        price_high = stock_data['high'].max()
        price_low = stock_data['low'].min()
        reference_price = stock_data['close'].iloc[0]

        # 设置网格，留有缓冲
        max_price = price_high * 1.1
        min_price = price_low * 0.9

        logger.info(
            f"Setting up grid strategy: "
            f"reference={reference_price:.2f}, "
            f"range=[{min_price:.2f}, {max_price:.2f}]"
        )

        strategy.setupGrids(reference_price, max_price, min_price)

    def _execute_new_strategy(
        self,
        strategy,
        timestamp,
        row: pd.Series
    ) -> float:
        """
        执行新接口策略（BaseStrategy）

        Args:
            strategy: 策略实例
            timestamp: 时间戳
            row: 当前行数据

        Returns:
            float: 当前组合价值
        """
        # 构建市场状态
        market_state = MarketState(
            timestamp=timestamp,
            open=row.get('open', row['close']),
            high=row.get('high', row['close']),
            low=row.get('low', row['close']),
            close=row['close'],
            volume=row.get('volume', 0)
        )

        # 执行决策
        decision = strategy.makeDecision(market_state)

        # 计算组合价值
        current_price = row['close']
        portfolio_value = strategy.cash + (strategy.position * current_price)

        return portfolio_value

    def _execute_legacy_strategy(
        self,
        strategy,
        timestamp,
        row: pd.Series
    ) -> float:
        """
        执行旧接口策略

        Args:
            strategy: 策略实例
            timestamp: 时间戳
            row: 当前行数据

        Returns:
            float: 当前组合价值
        """
        current_price = row['close']
        current_volume = row.get('volume', 0)

        # 调用旧接口
        if 'volume' in strategy.onMarketData.__code__.co_varnames:
            strategy.onMarketData(timestamp, current_price, current_volume)
        else:
            strategy.onMarketData(timestamp, current_price)

        # 更新组合价值
        strategy.updatePortfolioValue(current_price)

        return strategy.totalValue

    def create_result(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        initial_capital: float,
        stock_data: pd.DataFrame,
        trades: List,
        portfolio_values: List[float],
        positions: List[float],
        cash_values: List[float],
        strategy
    ) -> BacktestResult:
        """
        创建回测结果对象

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            initial_capital: 初始资金
            stock_data: 股票数据
            trades: 交易列表
            portfolio_values: 组合价值列表
            positions: 持仓列表
            cash_values: 现金列表
            strategy: 策略实例

        Returns:
            BacktestResult: 回测结果
        """
        # 获取网格调整记录（如果有）
        grid_adjustments = []
        if hasattr(strategy, 'gridAdjustments'):
            grid_adjustments = strategy.gridAdjustments

        return BacktestResult(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            stock_data=stock_data,
            portfolio_values=portfolio_values,
            positions=positions,
            cash_values=cash_values,
            trades=trades,
            strategy=strategy,
            grid_adjustments=grid_adjustments
        )
