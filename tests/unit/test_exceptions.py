#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
异常体系单元测试
Unit Tests for Exception System
"""

import pytest
from quant.core.exceptions import *


class TestExceptionHierarchy:
    """测试异常层次结构"""

    def test_base_exception(self):
        """测试基础异常"""
        error = QuantTradingError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.details == {}

    def test_base_exception_with_details(self):
        """测试带详情的异常"""
        error = QuantTradingError("Test error", {'key': 'value'})
        assert "key=value" in str(error)
        assert error.details['key'] == 'value'

    def test_config_error_inheritance(self):
        """测试配置异常继承"""
        error = ConfigError("Config error")
        assert isinstance(error, QuantTradingError)
        assert isinstance(error, Exception)

    def test_data_error_inheritance(self):
        """测试数据异常继承"""
        error = DataError("Data error")
        assert isinstance(error, QuantTradingError)


class TestConfigExceptions:
    """测试配置相关异常"""

    def test_config_file_not_found(self):
        """测试配置文件未找到"""
        error = ConfigFileNotFoundError('/path/to/config.yaml')
        assert '/path/to/config.yaml' in str(error)
        assert error.details['config_path'] == '/path/to/config.yaml'

    def test_config_validation_error(self):
        """测试配置验证错误"""
        error = ConfigValidationError('timeout', 'must be positive')
        assert 'timeout' in str(error)
        assert 'must be positive' in str(error)
        assert error.details['field'] == 'timeout'

    def test_missing_config_error(self):
        """测试缺少配置"""
        error = MissingConfigError('TUSHARE_TOKEN')
        assert 'TUSHARE_TOKEN' in str(error)


class TestDataExceptions:
    """测试数据相关异常"""

    def test_data_not_found(self):
        """测试数据未找到"""
        error = DataNotFoundError('000001.SZ')
        assert '000001.SZ' in str(error)
        assert error.details['symbol'] == '000001.SZ'

    def test_data_not_found_with_date_range(self):
        """测试带日期范围的数据未找到"""
        error = DataNotFoundError('000001.SZ', '20240101 to 20241231')
        assert '000001.SZ' in str(error)
        assert '20240101 to 20241231' in str(error)

    def test_invalid_symbol_error(self):
        """测试无效股票代码"""
        error = InvalidSymbolError('INVALID')
        assert 'INVALID' in str(error)

    def test_invalid_symbol_with_format(self):
        """测试带格式说明的无效代码"""
        error = InvalidSymbolError('INVALID', 'XXXXXX.SH')
        assert 'XXXXXX.SH' in str(error)

    def test_invalid_date_range(self):
        """测试无效日期范围"""
        error = InvalidDateRangeError('20240201', '20240101', 'start > end')
        assert '20240201' in str(error)
        assert '20240101' in str(error)
        assert 'start > end' in str(error)


class TestProviderExceptions:
    """测试数据提供者异常"""

    def test_provider_error(self):
        """测试提供者错误"""
        error = ProviderError('tushare', 'Connection failed')
        assert 'tushare' in str(error)
        assert 'Connection failed' in str(error)
        assert error.provider == 'tushare'

    def test_provider_not_available(self):
        """测试提供者不可用"""
        error = ProviderNotAvailableError('tushare', 'Not installed')
        assert 'tushare' in str(error)
        assert 'Not installed' in str(error)

    def test_provider_auth_error(self):
        """测试认证错误"""
        error = ProviderAuthError('tushare', 'TUSHARE_TOKEN')
        assert 'tushare' in str(error)
        assert 'TUSHARE_TOKEN' in str(error)

    def test_provider_rate_limit(self):
        """测试限流错误"""
        error = ProviderRateLimitError('tushare', retry_after=60)
        assert 'tushare' in str(error)
        assert '60' in str(error)
        assert error.details['retry_after'] == 60

    def test_provider_connection_error(self):
        """测试连接错误"""
        original = Exception("Network timeout")
        error = ProviderConnectionError('yahoo', original)
        assert 'yahoo' in str(error)
        assert 'Network timeout' in str(error)


class TestStrategyExceptions:
    """测试策略相关异常"""

    def test_strategy_not_found(self):
        """测试策略未找到"""
        error = StrategyNotFoundError('my_strategy')
        assert 'my_strategy' in str(error)

    def test_strategy_initialization_error(self):
        """测试策略初始化错误"""
        error = StrategyInitializationError('grid', 'Invalid parameters')
        assert 'grid' in str(error)
        assert 'Invalid parameters' in str(error)

    def test_strategy_parameter_error(self):
        """测试策略参数错误"""
        error = StrategyParameterError('gridLevels', -5, 'must be positive')
        assert 'gridLevels' in str(error)
        assert '-5' in str(error)
        assert 'must be positive' in str(error)


class TestBacktestExceptions:
    """测试回测相关异常"""

    def test_backtest_validation_error(self):
        """测试回测验证错误"""
        error = BacktestValidationError(
            'Invalid capital',
            {'capital': -1000}
        )
        assert 'Invalid capital' in str(error)

    def test_insufficient_data_error(self):
        """测试数据不足错误"""
        error = InsufficientDataError('000001.SZ', 30, 10)
        assert '000001.SZ' in str(error)
        assert '30' in str(error)
        assert '10' in str(error)

    def test_backtest_execution_error(self):
        """测试回测执行错误"""
        error = BacktestExecutionError('Calculation failed', {'step': 100})
        assert 'Calculation failed' in str(error)


class TestPortfolioExceptions:
    """测试投资组合异常"""

    def test_portfolio_not_found(self):
        """测试组合未找到"""
        error = PortfolioNotFoundError('MY_PORTFOLIO')
        assert 'MY_PORTFOLIO' in str(error)

    def test_invalid_portfolio(self):
        """测试无效组合"""
        error = InvalidPortfolioError('MY_PORTFOLIO', 'Invalid weights')
        assert 'MY_PORTFOLIO' in str(error)
        assert 'Invalid weights' in str(error)


class TestUtilityFunctions:
    """测试工具函数"""

    def test_handle_provider_error_auth(self):
        """测试处理认证错误"""
        error = Exception("Authentication failed")
        result = handle_provider_error(error, 'tushare')
        assert isinstance(result, ProviderAuthError)
        assert result.provider == 'tushare'

    def test_handle_provider_error_rate_limit(self):
        """测试处理限流错误"""
        error = Exception("Rate limit exceeded")
        result = handle_provider_error(error, 'tushare')
        assert isinstance(result, ProviderRateLimitError)

    def test_handle_provider_error_connection(self):
        """测试处理连接错误"""
        error = Exception("Connection timeout")
        result = handle_provider_error(error, 'yahoo')
        assert isinstance(result, ProviderConnectionError)

    def test_handle_provider_error_generic(self):
        """测试处理通用错误"""
        error = Exception("Unknown error")
        result = handle_provider_error(error, 'test')
        assert isinstance(result, ProviderError)
        assert result.provider == 'test'
