#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unified Data Module

This module provides a unified interface for accessing market data
from various sources (Tushare, Yahoo Finance, etc.).

Usage:
    # Create a data provider
    from quant.data import create_data_provider
    
    provider = create_data_provider('tushare')
    data = provider.get_stock_data('000001.SZ', '20240101', '20240131')
    
    # Or use auto-selection
    provider = create_data_provider('auto')
    data = provider.get_stock_data('AAPL', '20240101', '20240131')
    
    # Get provider for specific symbol
    from quant.data import get_provider_for_symbol
    provider = get_provider_for_symbol('000001.SZ')  # Returns TushareProvider

Migration from quant.data_providers:
    # Old way (deprecated)
    from quant.data_providers import TushareDataProvider
    
    # New way (recommended)
    from quant.data import TushareProvider
    # or
    from quant.data import create_data_provider
"""

# Base classes
from .base_provider import BaseDataProvider

# Factory functions
from .provider_factory import (
    create_data_provider,
    get_provider_for_symbol,
    DataProviderFactory,
)

# Concrete implementations
from .implementations import (
    TushareProvider,
    TushareDataProvider,  # Backward compatibility alias
    YahooProvider,
    YahooDataProvider,    # Backward compatibility alias
)

# Backward compatibility - also export legacy providers.py content
# This ensures existing code using `from quant.data import DataProvider` still works
try:
    from .providers import DataProvider
except ImportError:
    # If providers.py doesn't have DataProvider, use TushareProvider as default
    DataProvider = TushareProvider

__all__ = [
    # Base class
    'BaseDataProvider',
    
    # Factory functions
    'create_data_provider',
    'get_provider_for_symbol',
    'DataProviderFactory',
    
    # New implementations (snake_case interface)
    'TushareProvider',
    'YahooProvider',
    
    # Backward compatibility (camelCase interface)
    'TushareDataProvider',
    'YahooDataProvider',
    'DataProvider',
]
