#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Data Providers Module (DEPRECATED)

⚠️  DEPRECATION WARNING ⚠️
This module is deprecated and will be removed in a future version.
Please use `quant.data` instead.

Migration guide:
    # Old way (deprecated)
    from quant.data_providers import TushareDataProvider
    from quant.data_providers import YahooDataProvider
    from quant.data_providers import DataProviderFactory
    
    # New way (recommended)
    from quant.data import TushareProvider
    from quant.data import YahooProvider
    from quant.data import create_data_provider
    
    # Or use the factory function
    from quant.data import create_data_provider
    provider = create_data_provider('tushare')  # or 'yahoo', 'auto'

This module re-exports the old implementations for backward compatibility,
but all new code should use `quant.data`.
"""

import warnings


def _emit_deprecation_warning():
    """Emit deprecation warning when this module is imported."""
    warnings.warn(
        "quant.data_providers is deprecated and will be removed in a future version. "
        "Please use quant.data instead. "
        "See quant/data/__init__.py for migration guide.",
        DeprecationWarning,
        stacklevel=3
    )


# Emit warning on import
_emit_deprecation_warning()


# Re-export for backward compatibility
# These are the original implementations (camelCase interface)
from .base_data_provider import BaseDataProvider
from .data_provider import TushareDataProvider
from .yahoo_data_provider import YahooDataProvider
from .data_provider_factory import DataProviderFactory
from .cache_manager import CacheManager, getCacheManager

# Also re-export the new implementations for smooth migration
# Users can start using the new names even when importing from here
try:
    from quant.data import TushareProvider, YahooProvider, create_data_provider
except ImportError:
    # Fallback if new module not yet available
    TushareProvider = TushareDataProvider
    YahooProvider = YahooDataProvider
    create_data_provider = None

__all__ = [
    # Legacy exports (deprecated but still functional)
    'BaseDataProvider',
    'TushareDataProvider',
    'YahooDataProvider',
    'DataProviderFactory',
    'CacheManager',
    'getCacheManager',
    
    # New exports (recommended)
    'TushareProvider',
    'YahooProvider',
    'create_data_provider',
]
