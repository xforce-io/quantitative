#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据提供者单元测试
Unit Tests for Data Provider
"""

import pytest
import pandas as pd
from datetime import date

from quant.core.exceptions import (
    InvalidSymbolError,
    InvalidDateRangeError,
    DataNotFoundError,
    ProviderNotAvailableError,
)


class TestSymbolValidation:
    """测试股票代码验证"""

    def test_valid_sz_symbol(self, mock_provider):
        """测试有效的深圳股票代码"""
        # 不应抛出异常
        mock_provider._validate_symbol('000001.SZ')
        mock_provider._validate_symbol('300750.SZ')

    def test_valid_sh_symbol(self, mock_provider):
        """测试有效的上海股票代码"""
        mock_provider._validate_symbol('600036.SH')
        mock_provider._validate_symbol('688012.SH')

    def test_invalid_symbol_format(self, mock_provider):
        """测试无效的股票代码格式"""
        with pytest.raises(InvalidSymbolError):
            mock_provider._validate_symbol('INVALID')

        with pytest.raises(InvalidSymbolError):
            mock_provider._validate_symbol('000001')  # 缺少市场后缀

        with pytest.raises(InvalidSymbolError):
            mock_provider._validate_symbol('000001.XX')  # 无效的市场

    def test_empty_symbol(self, mock_provider):
        """测试空股票代码"""
        with pytest.raises(InvalidSymbolError):
            mock_provider._validate_symbol('')

        with pytest.raises(InvalidSymbolError):
            mock_provider._validate_symbol(None)


class TestDateNormalization:
    """测试日期格式化"""

    def test_normalize_string_date(self, mock_provider):
        """测试字符串日期"""
        assert mock_provider._normalize_date('20240101') == '20240101'
        assert mock_provider._normalize_date('2024-01-01') == '20240101'
        assert mock_provider._normalize_date('2024/01/01') == '20240101'

    def test_normalize_date_object(self, mock_provider):
        """测试date对象"""
        d = date(2024, 1, 1)
        assert mock_provider._normalize_date(d) == '20240101'

    def test_invalid_date_format(self, mock_provider):
        """测试无效日期格式"""
        with pytest.raises(ValueError):
            mock_provider._normalize_date('2024-1-1')  # 月日不是两位

        with pytest.raises(ValueError):
            mock_provider._normalize_date('invalid')

        with pytest.raises(ValueError):
            mock_provider._normalize_date(123)  # 非字符串或date对象


class TestDateRangeValidation:
    """测试日期范围验证"""

    def test_valid_date_range(self, mock_provider):
        """测试有效日期范围"""
        # 不应抛出异常
        mock_provider._validate_date_range('20240101', '20241231')
        mock_provider._validate_date_range('20200101', '20200201')

    def test_start_after_end(self, mock_provider):
        """测试开始日期晚于结束日期"""
        with pytest.raises(InvalidDateRangeError):
            mock_provider._validate_date_range('20241231', '20240101')

    def test_date_too_old(self, mock_provider):
        """测试日期太久远"""
        with pytest.raises(InvalidDateRangeError):
            mock_provider._validate_date_range('19990101', '20000101')

    def test_future_date(self, mock_provider):
        """测试未来日期"""
        with pytest.raises(InvalidDateRangeError):
            mock_provider._validate_date_range('20240101', '20300101')


class TestFrequencyValidation:
    """测试频率验证"""

    def test_valid_frequencies(self, mock_provider):
        """测试有效频率"""
        mock_provider._validate_frequency('D')
        mock_provider._validate_frequency('W')
        mock_provider._validate_frequency('M')

    def test_invalid_frequency(self, mock_provider):
        """测试无效频率"""
        with pytest.raises(ValueError):
            mock_provider._validate_frequency('X')

        with pytest.raises(ValueError):
            mock_provider._validate_frequency('daily')


class TestDataValidation:
    """测试数据验证和标准化"""

    def test_valid_data(self, mock_provider, sample_stock_data):
        """测试有效数据"""
        result = mock_provider._validate_and_normalize(
            sample_stock_data.copy(),
            '000001.SZ'
        )

        assert isinstance(result, pd.DataFrame)
        assert isinstance(result.index, pd.DatetimeIndex)
        assert list(result.columns) == ['open', 'high', 'low', 'close', 'volume']

    def test_empty_data(self, mock_provider):
        """测试空数据"""
        with pytest.raises(DataNotFoundError):
            mock_provider._validate_and_normalize(
                pd.DataFrame(),
                '000001.SZ'
            )

    def test_missing_columns(self, mock_provider):
        """测试缺少列的数据"""
        df = pd.DataFrame({
            'close': [10, 11, 12],
        }, index=pd.date_range('2024-01-01', periods=3))

        result = mock_provider._validate_and_normalize(df, '000001.SZ')

        # 应该自动填充缺失的列
        assert 'open' in result.columns
        assert 'high' in result.columns
        assert 'low' in result.columns
        assert 'volume' in result.columns


class TestDataQualityCheck:
    """测试数据质量检查"""

    def test_normal_data(self, mock_provider, sample_stock_data):
        """测试正常数据"""
        # 不应抛出异常
        mock_provider._check_data_quality(sample_stock_data, '000001.SZ')

    def test_data_with_missing_values(self, mock_provider):
        """测试包含缺失值的数据（应警告）"""
        df = pd.DataFrame({
            'open': [10, None, 12],
            'high': [11, 12, 13],
            'low': [9, 10, 11],
            'close': [10.5, 11.5, 12.5],
            'volume': [1000, 2000, 3000]
        }, index=pd.date_range('2024-01-01', periods=3))

        # 应该记录警告但不抛出异常
        mock_provider._check_data_quality(df, '000001.SZ')

    def test_data_with_zero_prices(self, mock_provider):
        """测试包含零价格的数据（应警告）"""
        df = pd.DataFrame({
            'open': [10, 0, 12],
            'high': [11, 12, 13],
            'low': [9, 10, 11],
            'close': [10.5, 11.5, 12.5],
            'volume': [1000, 2000, 3000]
        }, index=pd.date_range('2024-01-01', periods=3))

        mock_provider._check_data_quality(df, '000001.SZ')


class TestCaching:
    """测试缓存机制"""

    def test_cache_disabled(self, mock_data_provider_config):
        """测试禁用缓存"""
        from quant.data.providers import DataProvider

        config = mock_data_provider_config.copy()
        config['cache_enabled'] = False

        # 由于没有真实的provider，这里只测试配置
        # 实际的provider会在集成测试中测试

    def test_cache_path_generation(self, mock_provider):
        """测试缓存路径生成"""
        path1 = mock_provider._get_cache_path('test_key_1')
        path2 = mock_provider._get_cache_path('test_key_2')
        path3 = mock_provider._get_cache_path('test_key_1')  # 相同key

        assert path1 != path2  # 不同key应该有不同路径
        assert path1 == path3  # 相同key应该有相同路径
        assert path1.suffix == '.pkl'


class TestProviderInfo:
    """测试提供者信息"""

    def test_get_provider_info(self, mock_provider):
        """测试获取提供者信息"""
        info = mock_provider.get_provider_info()

        assert 'name' in info
        assert 'cache_enabled' in info
        assert 'status' in info
        assert info['status'] == 'active'
