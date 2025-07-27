"""
Trading Engines Module

Contains backtesting, optimization and execution engines.
"""

from .backtest_engine import BacktestEngine
from .strategy_optimizer import StrategyOptimizer, ParameterSpace, OptimizationResult, OptimizationSummary

__all__ = ['BacktestEngine', 'StrategyOptimizer', 'ParameterSpace', 'OptimizationResult', 'OptimizationSummary'] 