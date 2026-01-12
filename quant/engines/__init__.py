"""
Trading Engines Module

Contains backtesting, optimization and execution engines.
"""

# Legacy backtest engine (for backward compatibility)
from .backtest_engine import BacktestEngine as LegacyBacktestEngine

# New refactored backtest engine (recommended)
from .backtest_engine_new import BacktestEngine, create_backtest_engine

# Backtest components
from .backtest_validator import BacktestValidator
from .backtest_executor import BacktestExecutor, BacktestResult
from .backtest_analyzer import BacktestAnalyzer

# Strategy optimizer
from .strategy_optimizer import StrategyOptimizer, ParameterSpace, OptimizationResult, OptimizationSummary

# Algorithm engine (for componentized Alpha/Portfolio/Risk flow)
from .algorithm_engine import AlgorithmEngine, AlgorithmResult, AlgorithmState

__all__ = [
    # Main engines
    'BacktestEngine',           # New refactored engine (for traditional strategies)
    'LegacyBacktestEngine',     # Old engine (for compatibility)
    'AlgorithmEngine',          # New componentized engine (Alpha/Portfolio/Risk)
    'create_backtest_engine',
    # Backtest components
    'BacktestValidator',
    'BacktestExecutor',
    'BacktestAnalyzer',
    'BacktestResult',
    # Algorithm components
    'AlgorithmResult',
    'AlgorithmState',
    # Optimizer
    'StrategyOptimizer',
    'ParameterSpace',
    'OptimizationResult',
    'OptimizationSummary',
] 