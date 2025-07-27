"""
Quantitative Trading Package

This package contains the core components for quantitative trading:
- strategies: Trading strategies implementation
- data_providers: Data source abstractions and implementations  
- engines: Backtesting and execution engines
"""

__version__ = "1.0.0"
__author__ = "Quantitative Trading Team"

# Import main components for easy access
from .data_providers.data_provider_factory import createDataProvider

# Import strategies through the strategies package (this will now use the unified strategy)
from .strategies import GridTradingStrategy, UnifiedGridTradingStrategy, GridLevel, Trade
from .engines.backtest_engine import BacktestEngine
from .news import NewsCollector, NewsAnalyzer

__all__ = [
    'GridTradingStrategy',
    'DataProviderFactory', 
    'BacktestEngine',
    'NewsCollector',
    'NewsAnalyzer'
] 