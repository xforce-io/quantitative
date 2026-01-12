"""Core modules for quantitative trading system."""

try:
    from .simple_config import SimpleConfig, get_config
except ImportError:
    from .config_manager import ConfigManager

from .data_manager import DataManager
from .report_generator import ReportGenerator
from .indicators import TechnicalIndicators, add_technical_indicators
from .metrics import PerformanceMetrics, calculate_performance_summary, format_performance_report

# Import unified exception system
from .exceptions import (
    # Base exceptions
    QuantTradingError,
    # Config exceptions
    ConfigError,
    ConfigFileNotFoundError,
    ConfigValidationError,
    MissingConfigError,
    # Data exceptions
    DataError,
    DataNotFoundError,
    DataValidationError,
    InvalidSymbolError,
    InvalidDateRangeError,
    # Provider exceptions
    ProviderError,
    ProviderNotAvailableError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderConnectionError,
    # Strategy exceptions
    StrategyError,
    StrategyNotFoundError,
    StrategyInitializationError,
    StrategyParameterError,
    StrategyExecutionError,
    # Backtest exceptions
    BacktestError,
    BacktestValidationError,
    InsufficientDataError,
    BacktestExecutionError,
    # Analysis exceptions
    AnalysisError,
    PortfolioError,
    PortfolioNotFoundError,
    InvalidPortfolioError,
    AdvisorError,
    ScreenerError,
    # Cache exceptions
    CacheError,
    CacheReadError,
    CacheWriteError,
    # Utility functions
    handle_provider_error,
    safe_import,
)

__all__ = [
    'SimpleConfig',
    'get_config',
    'DataManager',
    'ReportGenerator',
    'TechnicalIndicators',
    'add_technical_indicators',
    'PerformanceMetrics',
    'calculate_performance_summary',
    'format_performance_report',
    # Exceptions
    'QuantTradingError',
    'ConfigError',
    'ConfigFileNotFoundError',
    'ConfigValidationError',
    'MissingConfigError',
    'DataError',
    'DataNotFoundError',
    'DataValidationError',
    'InvalidSymbolError',
    'InvalidDateRangeError',
    'ProviderError',
    'ProviderNotAvailableError',
    'ProviderAuthError',
    'ProviderRateLimitError',
    'ProviderConnectionError',
    'StrategyError',
    'StrategyNotFoundError',
    'StrategyInitializationError',
    'StrategyParameterError',
    'StrategyExecutionError',
    'BacktestError',
    'BacktestValidationError',
    'InsufficientDataError',
    'BacktestExecutionError',
    'AnalysisError',
    'PortfolioError',
    'PortfolioNotFoundError',
    'InvalidPortfolioError',
    'AdvisorError',
    'ScreenerError',
    'CacheError',
    'CacheReadError',
    'CacheWriteError',
    'handle_provider_error',
    'safe_import',
]
