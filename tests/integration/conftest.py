"""
Integration test fixtures.

Provides real (or mock-patched) provider instances and shared data
for cross-module integration tests.
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock


@pytest.fixture
def tmp_cache_dir(tmp_path):
    """Temporary cache directory for provider tests."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def realistic_stock_data():
    """
    Generate realistic A-share stock data with OHLCV.

    Simulates ~6 months of daily data with plausible price movement.
    """
    dates = pd.bdate_range(start="2024-01-02", end="2024-06-28")
    n = len(dates)

    np.random.seed(42)
    base_price = 15.0
    returns = np.random.normal(0.0005, 0.025, n)
    prices = base_price * np.exp(np.cumsum(returns))

    data = pd.DataFrame(
        {
            "open": prices * (1 + np.random.normal(0, 0.005, n)),
            "high": prices * (1 + np.abs(np.random.normal(0, 0.015, n))),
            "low": prices * (1 - np.abs(np.random.normal(0, 0.015, n))),
            "close": prices,
            "volume": np.random.randint(5_000_000, 50_000_000, n).astype(float),
        },
        index=dates,
    )

    # Enforce OHLC constraints
    data["high"] = data[["open", "close", "high"]].max(axis=1)
    data["low"] = data[["open", "close", "low"]].min(axis=1)
    data.index.name = "date"

    return data


@pytest.fixture
def mock_tushare_provider(realistic_stock_data):
    """
    A TushareProvider-like mock that returns realistic_stock_data
    without hitting the real Tushare API.
    """
    provider = MagicMock()
    provider.get_stock_data.return_value = realistic_stock_data
    provider.__class__.__name__ = "TushareProvider"
    return provider
