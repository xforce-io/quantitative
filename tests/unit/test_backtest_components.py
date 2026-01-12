#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
回测组件单元测试
Unit Tests for Backtest Components
"""

import pytest
import pandas as pd
import numpy as np

from quant.engines.backtest_validator import BacktestValidator
from quant.engines.backtest_analyzer import BacktestAnalyzer
from quant.core.exceptions import (
    BacktestValidationError,
    InsufficientDataError,
)


class TestBacktestValidator:
    """测试回测验证器"""

    @pytest.fixture
    def validator(self):
        return BacktestValidator()

    @pytest.fixture
    def mock_strategy(self):
        """Mock策略"""
        class MockStrategy:
            def makeDecision(self, market_state):
                pass

            def reset(self, capital):
                pass

        return MockStrategy()

    def test_validate_positive_capital(self, validator, mock_strategy):
        """测试正常的初始资金"""
        # 不应抛出异常
        validator.validate_params(
            '000001.SZ', '20240101', '20241231', 100000, mock_strategy
        )

    def test_validate_zero_capital(self, validator, mock_strategy):
        """测试零资金"""
        with pytest.raises(BacktestValidationError):
            validator.validate_params(
                '000001.SZ', '20240101', '20241231', 0, mock_strategy
            )

    def test_validate_negative_capital(self, validator, mock_strategy):
        """测试负资金"""
        with pytest.raises(BacktestValidationError):
            validator.validate_params(
                '000001.SZ', '20240101', '20241231', -1000, mock_strategy
            )

    def test_validate_too_small_capital(self, validator, mock_strategy):
        """测试资金太小"""
        with pytest.raises(BacktestValidationError):
            validator.validate_params(
                '000001.SZ', '20240101', '20241231', 500, mock_strategy
            )

    def test_validate_none_strategy(self, validator):
        """测试空策略"""
        with pytest.raises(BacktestValidationError):
            validator.validate_params(
                '000001.SZ', '20240101', '20241231', 100000, None
            )

    def test_validate_valid_data(self, validator, sample_stock_data):
        """测试有效数据"""
        # 不应抛出异常
        validator.validate_data(
            sample_stock_data, '000001.SZ', '20240101', '20241231'
        )

    def test_validate_empty_data(self, validator):
        """测试空数据"""
        with pytest.raises(InsufficientDataError):
            validator.validate_data(
                pd.DataFrame(), '000001.SZ', '20240101', '20241231'
            )

    def test_validate_insufficient_data(self, validator):
        """测试数据不足"""
        # 只有10行数据，少于最小要求的30行
        df = pd.DataFrame({
            'open': [10] * 10,
            'high': [11] * 10,
            'low': [9] * 10,
            'close': [10.5] * 10,
            'volume': [1000] * 10
        }, index=pd.date_range('2024-01-01', periods=10))

        with pytest.raises(InsufficientDataError):
            validator.validate_data(df, '000001.SZ', '20240101', '20240110')

    def test_validate_data_missing_columns(self, validator):
        """测试缺少必要列"""
        df = pd.DataFrame({
            'close': [10, 11, 12] * 20,
        }, index=pd.date_range('2024-01-01', periods=60))

        with pytest.raises(BacktestValidationError):
            validator.validate_data(df, '000001.SZ', '20240101', '20240301')

    def test_validate_data_with_nulls(self, validator):
        """测试包含空值的数据"""
        df = pd.DataFrame({
            'open': [10, None, 12] * 20,
            'high': [11, 12, 13] * 20,
            'low': [9, 10, 11] * 20,
            'close': [10.5, 11.5, 12.5] * 20,
            'volume': [1000, 2000, 3000] * 20
        }, index=pd.date_range('2024-01-01', periods=60))

        with pytest.raises(BacktestValidationError):
            validator.validate_data(df, '000001.SZ', '20240101', '20240301')

    def test_validate_strategy_config_valid(self, validator):
        """测试有效的策略配置"""
        config = {
            'commission': 0.0003,
            'slippage': 0.001,
            'gridLevels': 5
        }
        # 不应抛出异常
        validator.validate_strategy_config(config)

    def test_validate_strategy_config_invalid_commission(self, validator):
        """测试无效的佣金配置"""
        config = {'commission': -0.01}  # 负数佣金
        with pytest.raises(BacktestValidationError):
            validator.validate_strategy_config(config)

        config = {'commission': 0.5}  # 佣金太高（50%）
        with pytest.raises(BacktestValidationError):
            validator.validate_strategy_config(config)

    def test_validate_strategy_config_invalid_slippage(self, validator):
        """测试无效的滑点配置"""
        config = {'slippage': -0.01}  # 负数滑点
        with pytest.raises(BacktestValidationError):
            validator.validate_strategy_config(config)


class TestBacktestAnalyzer:
    """测试回测分析器"""

    @pytest.fixture
    def analyzer(self):
        return BacktestAnalyzer()

    @pytest.fixture
    def mock_strategy(self):
        """Mock策略，提供基本的性能指标"""
        class MockStrategy:
            def get_performance_metrics(self):
                return {
                    'totalValue': 120000,
                    'totalReturn': 0.2,
                }
        return MockStrategy()

    def test_calculate_max_drawdown(self, analyzer):
        """测试最大回撤计算"""
        # 模拟组合价值序列：100 -> 120 -> 90 -> 110
        portfolio = pd.Series([100, 120, 90, 110])
        max_dd = analyzer._calculate_max_drawdown(portfolio)

        # 最大回撤应该是 (90-120)/120 = -25%
        assert abs(max_dd - (-0.25)) < 0.01

    def test_calculate_sharpe_ratio(self, analyzer):
        """测试夏普比率计算"""
        returns = pd.Series([0.01, -0.005, 0.015, 0.02, -0.01])
        annual_return = 0.15
        volatility = 0.20

        sharpe = analyzer._calculate_sharpe_ratio(
            returns, annual_return, volatility, risk_free_rate=0.03
        )

        # (0.15 - 0.03) / 0.20 = 0.6
        assert abs(sharpe - 0.6) < 0.01

    def test_calculate_sharpe_ratio_zero_volatility(self, analyzer):
        """测试零波动率的夏普比率"""
        returns = pd.Series([0] * 10)
        sharpe = analyzer._calculate_sharpe_ratio(returns, 0.0, 0.0)
        assert sharpe == 0.0

    def test_calculate_calmar_ratio(self, analyzer):
        """测试卡玛比率计算"""
        calmar = analyzer._calculate_calmar_ratio(0.20, -0.10)
        # 0.20 / 0.10 = 2.0
        assert abs(calmar - 2.0) < 0.01

    def test_calculate_calmar_ratio_zero_drawdown(self, analyzer):
        """测试零回撤的卡玛比率"""
        calmar = analyzer._calculate_calmar_ratio(0.15, 0.0)
        assert calmar == 0.0

    def test_calculate_beta(self, analyzer):
        """测试Beta值计算"""
        # 相同的收益率序列，Beta应该为1
        returns = pd.Series([0.01, -0.005, 0.015, 0.02, -0.01])
        beta = analyzer._calculate_beta(returns, returns)
        assert abs(beta - 1.0) < 0.1

    def test_calculate_beta_insufficient_data(self, analyzer):
        """测试数据不足时的Beta计算"""
        returns = pd.Series([0.01])
        beta = analyzer._calculate_beta(returns, returns)
        assert beta == 0.0

    def test_calculate_trade_statistics_dict_trades(self, analyzer):
        """测试交易统计（字典类型）"""
        trades = [
            {'pnl': 100},
            {'pnl': -50},
            {'pnl': 80},
            {'pnl': -30},
        ]

        stats = analyzer._calculate_trade_statistics(trades)

        assert stats['totalTrades'] == 4
        assert stats['winRate'] == 0.5  # 2 profitable out of 4
        assert stats['avgProfit'] == 90  # (100 + 80) / 2
        assert stats['avgLoss'] == -40  # (-50 + -30) / 2

    def test_calculate_trade_statistics_empty(self, analyzer):
        """测试空交易列表"""
        stats = analyzer._calculate_trade_statistics([])

        assert stats['totalTrades'] == 0
        assert stats['winRate'] == 0.0
        assert stats['avgProfit'] == 0.0
        assert stats['avgLoss'] == 0.0

    def test_format_summary(self, analyzer):
        """测试格式化摘要"""
        metrics = {
            'totalReturn': 0.25,
            'annualReturn': 0.30,
            'benchmarkReturn': 0.15,
            'alpha': 0.10,
            'finalValue': 125000,
            'maxDrawdown': -0.08,
            'volatility': 0.18,
            'beta': 1.2,
            'sharpeRatio': 1.5,
            'calmarRatio': 3.75,
            'totalTrades': 20,
            'winRate': 0.65,
            'avgProfit': 5000,
            'avgLoss': -2000,
            'profitFactor': 2.5,
        }

        summary = analyzer.format_summary(metrics, '000001.SZ')

        assert '000001.SZ' in summary
        assert '25.00%' in summary or '25%' in summary
        assert '125,000' in summary or '125000' in summary


class TestMetricsValidation:
    """测试指标验证"""

    @pytest.fixture
    def analyzer(self):
        return BacktestAnalyzer()

    def test_validate_normal_metrics(self, analyzer):
        """测试正常指标（应该不抛出异常）"""
        metrics = {
            'finalValue': 120000,
            'totalReturn': 0.20,
            'sharpeRatio': 1.5,
        }
        # 不应抛出异常，只会记录日志
        analyzer._validate_metrics(metrics, 100000)

    def test_validate_zero_final_value(self, analyzer):
        """测试零最终价值（应警告）"""
        metrics = {
            'finalValue': 0,
            'totalReturn': -1.0,
        }
        # 应该记录警告但不抛出异常
        analyzer._validate_metrics(metrics, 100000)

    def test_validate_extreme_returns(self, analyzer):
        """测试极端收益（应警告）"""
        metrics = {
            'finalValue': 10000000,  # 100倍收益
            'totalReturn': 99.0,
        }
        analyzer._validate_metrics(metrics, 100000)

    def test_validate_extreme_sharpe(self, analyzer):
        """测试极端夏普比率（应警告）"""
        metrics = {
            'finalValue': 120000,
            'sharpeRatio': 15.0,  # 异常高的夏普比率
        }
        analyzer._validate_metrics(metrics, 100000)
