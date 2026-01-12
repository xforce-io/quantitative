#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
回测结果分析器
Backtest Results Analyzer

负责分析回测结果并计算性能指标
"""

import logging
from typing import List, Dict, Any

import pandas as pd
import numpy as np

from ..core.exceptions import BacktestError

logger = logging.getLogger(__name__)


class BacktestAnalyzer:
    """回测结果分析器"""

    def calculate_metrics(
        self,
        stock_data: pd.DataFrame,
        portfolio_values: List[float],
        trades: List,
        initial_capital: float,
        strategy
    ) -> Dict[str, Any]:
        """
        计算回测性能指标

        Args:
            stock_data: 股票数据
            portfolio_values: 组合价值序列
            trades: 交易列表
            initial_capital: 初始资金
            strategy: 策略实例

        Returns:
            dict: 性能指标字典
        """
        # 获取策略自身的性能指标
        if hasattr(strategy, 'getPerformanceMetrics'):
            strategy_metrics = strategy.getPerformanceMetrics(initial_capital)
        elif hasattr(strategy, 'get_performance_metrics'):
            strategy_metrics = strategy.get_performance_metrics()
        else:
            strategy_metrics = {}

        # 计算额外的性能指标
        additional_metrics = self._calculate_additional_metrics(
            stock_data, portfolio_values, initial_capital, trades
        )

        # 合并所有指标
        all_metrics = {**strategy_metrics, **additional_metrics}

        # 验证结果
        self._validate_metrics(all_metrics, initial_capital)

        return all_metrics

    def _calculate_additional_metrics(
        self,
        stock_data: pd.DataFrame,
        portfolio_values: List[float],
        initial_capital: float,
        trades: List
    ) -> Dict[str, Any]:
        """计算额外的性能指标"""
        portfolio_series = pd.Series(portfolio_values, index=stock_data.index)
        stock_returns = stock_data['close'].pct_change().dropna()
        portfolio_returns = portfolio_series.pct_change().dropna()

        # 基础收益指标
        final_value = portfolio_series.iloc[-1]
        total_return = (final_value - initial_capital) / initial_capital

        # 计算年化收益
        num_days = (stock_data.index[-1] - stock_data.index[0]).days
        num_years = max(num_days / 365.25, 0.01)  # 避免除零
        annual_return = (1 + total_return) ** (1 / num_years) - 1

        # 风险指标
        max_drawdown = self._calculate_max_drawdown(portfolio_series)
        volatility = portfolio_returns.std() * np.sqrt(252)  # 年化波动率

        # 风险调整收益
        sharpe_ratio = self._calculate_sharpe_ratio(
            portfolio_returns, annual_return, volatility
        )
        calmar_ratio = self._calculate_calmar_ratio(annual_return, max_drawdown)

        # 市场相关指标
        beta = self._calculate_beta(portfolio_returns, stock_returns)

        # 基准收益
        benchmark_return = (stock_data['close'].iloc[-1] / stock_data['close'].iloc[0]) - 1

        # Alpha（超额收益）
        risk_free_rate = 0.03  # 3% 无风险利率
        alpha = annual_return - (risk_free_rate + beta * (benchmark_return - risk_free_rate))

        # 交易统计
        trade_stats = self._calculate_trade_statistics(trades)

        return {
            'finalValue': final_value,
            'totalReturn': total_return,
            'annualReturn': annual_return,
            'benchmarkReturn': benchmark_return,
            'maxDrawdown': max_drawdown,
            'volatility': volatility,
            'sharpeRatio': sharpe_ratio,
            'calmarRatio': calmar_ratio,
            'beta': beta,
            'alpha': alpha,
            **trade_stats
        }

    def _calculate_max_drawdown(self, portfolio_series: pd.Series) -> float:
        """计算最大回撤"""
        cum_max = portfolio_series.expanding().max()
        drawdown = (portfolio_series - cum_max) / cum_max
        return drawdown.min()

    def _calculate_sharpe_ratio(
        self,
        portfolio_returns: pd.Series,
        annual_return: float,
        volatility: float,
        risk_free_rate: float = 0.03
    ) -> float:
        """
        计算夏普比率

        Args:
            portfolio_returns: 组合收益率序列
            annual_return: 年化收益率
            volatility: 波动率
            risk_free_rate: 无风险利率

        Returns:
            float: 夏普比率
        """
        if volatility == 0 or volatility < 1e-10:
            return 0.0

        excess_return = annual_return - risk_free_rate
        sharpe = excess_return / volatility

        return sharpe

    def _calculate_calmar_ratio(
        self,
        annual_return: float,
        max_drawdown: float
    ) -> float:
        """
        计算卡玛比率

        Args:
            annual_return: 年化收益率
            max_drawdown: 最大回撤

        Returns:
            float: 卡玛比率
        """
        if abs(max_drawdown) < 1e-10:
            return 0.0

        return annual_return / abs(max_drawdown)

    def _calculate_beta(
        self,
        portfolio_returns: pd.Series,
        stock_returns: pd.Series
    ) -> float:
        """
        计算Beta值

        Args:
            portfolio_returns: 组合收益率
            stock_returns: 股票收益率

        Returns:
            float: Beta值
        """
        if len(portfolio_returns) < 2 or len(stock_returns) < 2:
            return 0.0

        try:
            # 清理NaN值
            portfolio_clean = portfolio_returns.dropna()
            stock_clean = stock_returns.dropna()

            if len(portfolio_clean) < 2 or len(stock_clean) < 2:
                return 0.0

            # 计算协方差和方差
            covariance = np.cov(portfolio_clean, stock_clean)[0][1]
            stock_variance = stock_clean.var()

            if stock_variance == 0 or stock_variance < 1e-10:
                return 0.0

            beta = covariance / stock_variance
            return beta

        except Exception as e:
            logger.warning(f"Failed to calculate beta: {e}")
            return 0.0

    def _calculate_trade_statistics(self, trades: List) -> Dict[str, Any]:
        """
        计算交易统计

        Args:
            trades: 交易列表

        Returns:
            dict: 交易统计
        """
        if not trades:
            return {
                'totalTrades': 0,
                'winRate': 0.0,
                'avgProfit': 0.0,
                'avgLoss': 0.0,
                'profitFactor': 0.0,
            }

        try:
            # 区分dict和object类型的交易
            if isinstance(trades[0], dict):
                profitable_trades = [t for t in trades if t.get('pnl', 0) > 0]
                losing_trades = [t for t in trades if t.get('pnl', 0) < 0]
                avg_profit = np.mean([t.get('pnl', 0) for t in profitable_trades]) if profitable_trades else 0
                avg_loss = np.mean([t.get('pnl', 0) for t in losing_trades]) if losing_trades else 0
            else:
                # Object类型
                profitable_trades = [t for t in trades if t.pnl > 0]
                losing_trades = [t for t in trades if t.pnl < 0]
                avg_profit = np.mean([t.pnl for t in profitable_trades]) if profitable_trades else 0
                avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0

            win_rate = len(profitable_trades) / len(trades) if trades else 0

            # 盈亏比
            if avg_loss != 0 and abs(avg_loss) > 1e-10:
                profit_factor = abs(avg_profit / avg_loss)
            else:
                profit_factor = float('inf') if avg_profit > 0 else 0.0

            return {
                'totalTrades': len(trades),
                'winRate': win_rate,
                'avgProfit': avg_profit,
                'avgLoss': avg_loss,
                'profitFactor': profit_factor,
            }

        except Exception as e:
            logger.warning(f"Failed to calculate trade statistics: {e}")
            return {
                'totalTrades': len(trades),
                'winRate': 0.0,
                'avgProfit': 0.0,
                'avgLoss': 0.0,
                'profitFactor': 0.0,
            }

    def _validate_metrics(self, metrics: Dict[str, Any], initial_capital: float):
        """
        验证指标的合理性

        Args:
            metrics: 指标字典
            initial_capital: 初始资金

        Raises:
            BacktestError: 指标异常
        """
        final_value = metrics.get('finalValue', 0)

        # 检查最终价值是否异常
        if final_value <= 0:
            logger.warning(
                f"Final portfolio value is zero or negative: {final_value}, "
                f"initial capital: {initial_capital}"
            )

        # 检查是否有异常高的收益
        if final_value > initial_capital * 100:  # 10000% 收益
            logger.warning(
                f"Extremely high returns detected: "
                f"final={final_value}, initial={initial_capital}, "
                f"return={metrics.get('totalReturn', 0):.1%}"
            )

        # 检查夏普比率是否异常
        sharpe_ratio = metrics.get('sharpeRatio', 0)
        if abs(sharpe_ratio) > 10:
            logger.warning(f"Unusually high Sharpe ratio: {sharpe_ratio:.2f}")

    def format_summary(self, metrics: Dict[str, Any], symbol: str) -> str:
        """
        格式化性能摘要

        Args:
            metrics: 性能指标
            symbol: 股票代码

        Returns:
            str: 格式化的摘要
        """
        summary = f"""
{'='*80}
回测结果摘要 - {symbol}
{'='*80}

📊 收益指标:
  总收益率: {metrics.get('totalReturn', 0):+.2%}
  年化收益: {metrics.get('annualReturn', 0):+.2%}
  基准收益: {metrics.get('benchmarkReturn', 0):+.2%}
  超额收益 (Alpha): {metrics.get('alpha', 0):+.2%}
  最终价值: ¥{metrics.get('finalValue', 0):,.2f}

⚠️  风险指标:
  最大回撤: {metrics.get('maxDrawdown', 0):.2%}
  波动率: {metrics.get('volatility', 0):.2%}
  Beta: {metrics.get('beta', 0):.2f}

📈 风险调整收益:
  夏普比率: {metrics.get('sharpeRatio', 0):.2f}
  卡玛比率: {metrics.get('calmarRatio', 0):.2f}

💼 交易统计:
  交易次数: {metrics.get('totalTrades', 0)}
  胜率: {metrics.get('winRate', 0):.1%}
  平均盈利: ¥{metrics.get('avgProfit', 0):,.2f}
  平均亏损: ¥{metrics.get('avgLoss', 0):,.2f}
  盈亏比: {metrics.get('profitFactor', 0):.2f}

{'='*80}
"""
        return summary
