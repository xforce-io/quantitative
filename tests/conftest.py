#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pytest配置和共享fixtures
Pytest Configuration and Shared Fixtures
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path


@pytest.fixture
def sample_stock_data():
    """生成示例股票数据"""
    dates = pd.date_range(start='2024-01-01', end='2024-12-31', freq='D')
    n = len(dates)

    # 生成模拟价格数据
    base_price = 10.0
    returns = np.random.randn(n) * 0.02  # 2% daily volatility
    prices = base_price * np.exp(np.cumsum(returns))

    data = pd.DataFrame({
        'open': prices * (1 + np.random.randn(n) * 0.01),
        'high': prices * (1 + np.abs(np.random.randn(n)) * 0.02),
        'low': prices * (1 - np.abs(np.random.randn(n)) * 0.02),
        'close': prices,
        'volume': np.random.randint(1000000, 10000000, n)
    }, index=dates)

    # 确保high >= low, close, open
    data['high'] = data[['open', 'close', 'high']].max(axis=1)
    data['low'] = data[['open', 'close', 'low']].min(axis=1)

    return data


@pytest.fixture
def sample_trades():
    """生成示例交易记录"""
    from quant.strategies.unified_grid_strategy import Trade

    trades = [
        Trade(
            timestamp=datetime(2024, 1, 10),
            price=10.0,
            quantity=100,
            side='buy',
            commission=3.0,
            slippage=1.0,
            pnl=0
        ),
        Trade(
            timestamp=datetime(2024, 2, 10),
            price=11.0,
            quantity=100,
            side='sell',
            commission=3.3,
            slippage=1.1,
            pnl=95.6  # (11-10)*100 - 3.0 - 3.3 - 1.0 - 1.1
        ),
        Trade(
            timestamp=datetime(2024, 3, 10),
            price=9.5,
            quantity=100,
            side='buy',
            commission=2.85,
            slippage=0.95,
            pnl=0
        ),
    ]

    return trades


@pytest.fixture
def mock_data_provider_config():
    """Mock数据提供者配置"""
    return {
        'cache_dir': 'cache/test',
        'cache_enabled': False,  # 测试时禁用缓存
        'cache_ttl_hours': 1,
    }


@pytest.fixture
def sample_strategy_config():
    """示例策略配置"""
    return {
        'gridLevels': 5,
        'gridSpacing': 0.02,
        'baseRatio': 0.3,
        'commission': 0.0003,
        'slippage': 0.001,
    }


@pytest.fixture
def mock_provider(monkeypatch, mock_data_provider_config, sample_stock_data):
    """Mock数据提供者，返回示例数据"""
    from quant.data.providers import DataProvider

    class MockDataProvider(DataProvider):
        def __init__(self, provider='auto', config=None):
            # 跳过真实初始化
            self.provider_name = 'mock'
            self.config = config or {}
            self.cache_dir = Path(self.config.get('cache_dir', 'cache'))
            self.cache_enabled = self.config.get('cache_enabled', False)
            self.cache_ttl_hours = self.config.get('cache_ttl_hours', 24)

        def get_stock_data(self, symbol, start_date, end_date, freq='D'):
            return sample_stock_data

    return MockDataProvider('auto', mock_data_provider_config)
