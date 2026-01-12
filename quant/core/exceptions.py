#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一异常体系
Unified Exception System

为量化交易系统提供清晰、层次化的异常处理机制
"""


class QuantTradingError(Exception):
    """
    量化交易系统基础异常类

    所有自定义异常都应继承此类
    """
    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            details_str = ', '.join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


# ============================================================================
# 配置相关异常
# ============================================================================

class ConfigError(QuantTradingError):
    """配置相关错误"""
    pass


class ConfigFileNotFoundError(ConfigError):
    """配置文件未找到"""
    def __init__(self, config_path: str):
        super().__init__(
            f"Configuration file not found: {config_path}",
            {'config_path': config_path}
        )


class ConfigValidationError(ConfigError):
    """配置验证失败"""
    def __init__(self, field: str, reason: str):
        super().__init__(
            f"Invalid configuration for '{field}': {reason}",
            {'field': field, 'reason': reason}
        )


class MissingConfigError(ConfigError):
    """缺少必要配置"""
    def __init__(self, config_key: str):
        super().__init__(
            f"Required configuration '{config_key}' is missing",
            {'config_key': config_key}
        )


# ============================================================================
# 数据相关异常
# ============================================================================

class DataError(QuantTradingError):
    """数据相关错误基类"""
    pass


class DataNotFoundError(DataError):
    """数据未找到"""
    def __init__(self, symbol: str, date_range: str = None):
        message = f"No data found for symbol: {symbol}"
        details = {'symbol': symbol}
        if date_range:
            message += f" in date range: {date_range}"
            details['date_range'] = date_range
        super().__init__(message, details)


class DataValidationError(DataError):
    """数据验证失败"""
    def __init__(self, reason: str, data_info: dict = None):
        super().__init__(
            f"Data validation failed: {reason}",
            data_info or {}
        )


class InvalidSymbolError(DataError):
    """无效的股票代码"""
    def __init__(self, symbol: str, expected_format: str = None):
        message = f"Invalid symbol format: {symbol}"
        details = {'symbol': symbol}
        if expected_format:
            message += f", expected format: {expected_format}"
            details['expected_format'] = expected_format
        super().__init__(message, details)


class InvalidDateRangeError(DataError):
    """无效的日期范围"""
    def __init__(self, start_date: str, end_date: str, reason: str = None):
        message = f"Invalid date range: {start_date} to {end_date}"
        if reason:
            message += f" - {reason}"
        super().__init__(
            message,
            {'start_date': start_date, 'end_date': end_date}
        )


# ============================================================================
# 数据提供者相关异常
# ============================================================================

class ProviderError(DataError):
    """数据提供者错误基类"""
    def __init__(self, provider: str, message: str, details: dict = None):
        self.provider = provider
        details = details or {}
        details['provider'] = provider
        super().__init__(f"[{provider}] {message}", details)


class ProviderNotAvailableError(ProviderError):
    """数据提供者不可用"""
    def __init__(self, provider: str, reason: str = None):
        message = f"Provider not available"
        if reason:
            message += f": {reason}"
        super().__init__(provider, message)


class ProviderAuthError(ProviderError):
    """数据提供者认证失败"""
    def __init__(self, provider: str, token_name: str = None):
        message = "Authentication failed"
        if token_name:
            message += f", please check {token_name}"
        super().__init__(provider, message, {'token_name': token_name})


class ProviderRateLimitError(ProviderError):
    """数据提供者API限流"""
    def __init__(self, provider: str, retry_after: int = None):
        message = "Rate limit exceeded"
        details = {}
        if retry_after:
            message += f", retry after {retry_after} seconds"
            details['retry_after'] = retry_after
        super().__init__(provider, message, details)


class ProviderConnectionError(ProviderError):
    """数据提供者连接错误"""
    def __init__(self, provider: str, original_error: Exception = None):
        message = "Connection failed"
        details = {}
        if original_error:
            message += f": {str(original_error)}"
            details['original_error'] = str(original_error)
        super().__init__(provider, message, details)


# ============================================================================
# 策略相关异常
# ============================================================================

class StrategyError(QuantTradingError):
    """策略相关错误基类"""
    pass


class StrategyNotFoundError(StrategyError):
    """策略未找到"""
    def __init__(self, strategy_name: str):
        super().__init__(
            f"Strategy not found: {strategy_name}",
            {'strategy_name': strategy_name}
        )


class StrategyInitializationError(StrategyError):
    """策略初始化失败"""
    def __init__(self, strategy_name: str, reason: str):
        super().__init__(
            f"Failed to initialize strategy '{strategy_name}': {reason}",
            {'strategy_name': strategy_name, 'reason': reason}
        )


class StrategyParameterError(StrategyError):
    """策略参数错误"""
    def __init__(self, param_name: str, param_value, reason: str):
        super().__init__(
            f"Invalid strategy parameter '{param_name}' = {param_value}: {reason}",
            {'param_name': param_name, 'param_value': param_value, 'reason': reason}
        )


class StrategyExecutionError(StrategyError):
    """策略执行错误"""
    def __init__(self, strategy_name: str, error_detail: str):
        super().__init__(
            f"Strategy execution failed for '{strategy_name}': {error_detail}",
            {'strategy_name': strategy_name, 'error_detail': error_detail}
        )


# ============================================================================
# 回测相关异常
# ============================================================================

class BacktestError(QuantTradingError):
    """回测相关错误基类"""
    pass


class BacktestValidationError(BacktestError):
    """回测参数验证失败"""
    def __init__(self, reason: str, params: dict = None):
        super().__init__(
            f"Backtest validation failed: {reason}",
            params or {}
        )


class InsufficientDataError(BacktestError):
    """回测数据不足"""
    def __init__(self, symbol: str, required_bars: int, actual_bars: int):
        super().__init__(
            f"Insufficient data for {symbol}: required {required_bars} bars, got {actual_bars}",
            {'symbol': symbol, 'required_bars': required_bars, 'actual_bars': actual_bars}
        )


class BacktestExecutionError(BacktestError):
    """回测执行错误"""
    def __init__(self, reason: str, context: dict = None):
        super().__init__(
            f"Backtest execution failed: {reason}",
            context or {}
        )


# ============================================================================
# 分析相关异常
# ============================================================================

class AnalysisError(QuantTradingError):
    """分析相关错误基类"""
    pass


class PortfolioError(AnalysisError):
    """投资组合错误"""
    pass


class PortfolioNotFoundError(PortfolioError):
    """投资组合未找到"""
    def __init__(self, portfolio_name: str):
        super().__init__(
            f"Portfolio not found: {portfolio_name}",
            {'portfolio_name': portfolio_name}
        )


class InvalidPortfolioError(PortfolioError):
    """无效的投资组合配置"""
    def __init__(self, portfolio_name: str, reason: str):
        super().__init__(
            f"Invalid portfolio '{portfolio_name}': {reason}",
            {'portfolio_name': portfolio_name, 'reason': reason}
        )


class AdvisorError(AnalysisError):
    """投资顾问错误"""
    pass


class ScreenerError(AnalysisError):
    """筛选器错误"""
    pass


# ============================================================================
# 缓存相关异常
# ============================================================================

class CacheError(QuantTradingError):
    """缓存相关错误"""
    pass


class CacheReadError(CacheError):
    """缓存读取失败"""
    def __init__(self, cache_key: str, reason: str):
        super().__init__(
            f"Failed to read cache for '{cache_key}': {reason}",
            {'cache_key': cache_key, 'reason': reason}
        )


class CacheWriteError(CacheError):
    """缓存写入失败"""
    def __init__(self, cache_key: str, reason: str):
        super().__init__(
            f"Failed to write cache for '{cache_key}': {reason}",
            {'cache_key': cache_key, 'reason': reason}
        )


# ============================================================================
# 工具函数
# ============================================================================

def handle_provider_error(error: Exception, provider: str) -> ProviderError:
    """
    统一处理数据提供者的异常，转换为标准异常

    Args:
        error: 原始异常
        provider: 数据提供者名称

    Returns:
        ProviderError: 标准化的提供者异常
    """
    error_str = str(error).lower()

    # 认证错误
    if 'auth' in error_str or 'token' in error_str or 'permission' in error_str:
        return ProviderAuthError(provider)

    # 限流错误
    if 'rate limit' in error_str or 'too many requests' in error_str:
        return ProviderRateLimitError(provider)

    # 连接错误
    if 'connection' in error_str or 'timeout' in error_str or 'network' in error_str:
        return ProviderConnectionError(provider, error)

    # 默认错误
    return ProviderError(provider, str(error))


def safe_import(module_name: str, class_name: str = None):
    """
    安全导入模块，失败时抛出清晰的异常

    Args:
        module_name: 模块名称
        class_name: 类名称（可选）

    Returns:
        导入的模块或类

    Raises:
        ProviderNotAvailableError: 导入失败
    """
    try:
        module = __import__(module_name, fromlist=[class_name] if class_name else [])
        if class_name:
            return getattr(module, class_name)
        return module
    except ImportError as e:
        provider = module_name.split('.')[-1]
        raise ProviderNotAvailableError(
            provider,
            f"Package '{module_name}' not installed. Please run: pip install {module_name}"
        )
