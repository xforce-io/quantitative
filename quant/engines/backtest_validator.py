#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
回测参数验证器
Backtest Parameter Validator

负责验证回测参数的合法性
"""

import pandas as pd
from typing import Optional
from datetime import datetime

from ..core.exceptions import (
    BacktestValidationError,
    InvalidSymbolError,
    InvalidDateRangeError,
    InsufficientDataError,
    StrategyError,
)


class BacktestValidator:
    """回测参数验证器"""

    MIN_REQUIRED_BARS = 30  # 最少需要的数据行数

    def validate_params(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        initial_capital: float,
        strategy
    ):
        """
        验证回测参数

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            initial_capital: 初始资金
            strategy: 策略实例

        Raises:
            BacktestValidationError: 参数验证失败
        """
        # 验证初始资金
        if initial_capital is None:
            raise BacktestValidationError(
                "Initial capital is required",
                {'initial_capital': initial_capital}
            )

        if initial_capital <= 0:
            raise BacktestValidationError(
                "Initial capital must be positive",
                {'initial_capital': initial_capital}
            )

        if initial_capital < 1000:
            raise BacktestValidationError(
                "Initial capital too small (minimum 1000)",
                {'initial_capital': initial_capital}
            )

        # 验证策略
        if strategy is None:
            raise BacktestValidationError(
                "Strategy is required",
                {'strategy': None}
            )

        # 验证策略是否有必要的方法
        if not (hasattr(strategy, 'makeDecision') or hasattr(strategy, 'onMarketData')):
            raise StrategyError(
                f"Strategy {strategy.__class__.__name__} missing required methods"
            )

    def validate_data(self, data: pd.DataFrame, symbol: str, start_date: str, end_date: str):
        """
        验证回测数据

        Args:
            data: 股票数据
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Raises:
            InsufficientDataError: 数据不足
            BacktestValidationError: 数据验证失败
        """
        # 检查数据是否为空
        if data.empty:
            raise InsufficientDataError(
                symbol,
                required_bars=self.MIN_REQUIRED_BARS,
                actual_bars=0
            )

        # 检查数据量是否足够
        if len(data) < self.MIN_REQUIRED_BARS:
            raise InsufficientDataError(
                symbol,
                required_bars=self.MIN_REQUIRED_BARS,
                actual_bars=len(data)
            )

        # 检查必要的列
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            raise BacktestValidationError(
                f"Missing required columns: {missing_columns}",
                {'missing_columns': missing_columns, 'symbol': symbol}
            )

        # 检查数据类型
        if not isinstance(data.index, pd.DatetimeIndex):
            raise BacktestValidationError(
                "Data index must be DatetimeIndex",
                {'index_type': type(data.index).__name__, 'symbol': symbol}
            )

        # 检查是否有缺失值
        null_counts = data[required_columns].isnull().sum()
        if null_counts.any():
            raise BacktestValidationError(
                "Data contains missing values",
                {
                    'symbol': symbol,
                    'null_counts': null_counts[null_counts > 0].to_dict()
                }
            )

        # 检查是否有负值或零值
        for col in ['open', 'high', 'low', 'close']:
            if (data[col] <= 0).any():
                raise BacktestValidationError(
                    f"Column '{col}' contains zero or negative values",
                    {'symbol': symbol, 'column': col}
                )

    def validate_strategy_config(self, config: dict):
        """
        验证策略配置

        Args:
            config: 策略配置字典

        Raises:
            BacktestValidationError: 配置验证失败
        """
        if config is None:
            return  # 配置可选

        if not isinstance(config, dict):
            raise BacktestValidationError(
                "Strategy config must be a dictionary",
                {'config_type': type(config).__name__}
            )

        # 验证常见的配置参数
        if 'commission' in config:
            commission = config['commission']
            if not isinstance(commission, (int, float)):
                raise BacktestValidationError(
                    "Commission must be a number",
                    {'commission': commission, 'type': type(commission).__name__}
                )
            if commission < 0 or commission > 0.1:  # 0-10%
                raise BacktestValidationError(
                    "Commission out of reasonable range (0-10%)",
                    {'commission': commission}
                )

        if 'slippage' in config:
            slippage = config['slippage']
            if not isinstance(slippage, (int, float)):
                raise BacktestValidationError(
                    "Slippage must be a number",
                    {'slippage': slippage, 'type': type(slippage).__name__}
                )
            if slippage < 0 or slippage > 0.1:  # 0-10%
                raise BacktestValidationError(
                    "Slippage out of reasonable range (0-10%)",
                    {'slippage': slippage}
                )
