#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Data Provider Factory

This module provides factory functions to create data providers.
"""

from typing import Dict, Optional, Union
from .base_provider import BaseDataProvider
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


def create_data_provider(
    provider: str = 'auto',
    config: Optional[Dict] = None
) -> BaseDataProvider:
    """
    Create a data provider instance.
    
    Args:
        provider: Provider type, one of:
            - 'tushare': Tushare for A-share data
            - 'yahoo': Yahoo Finance for global data
            - 'auto': Automatically select based on symbol format
        config: Provider-specific configuration
            
    Returns:
        BaseDataProvider instance
        
    Raises:
        ValueError: If provider type is not supported
        
    Examples:
        >>> # Create Tushare provider
        >>> provider = create_data_provider('tushare')
        >>> df = provider.get_stock_data('000001.SZ', '20230101', '20231231')
        
        >>> # Create Yahoo provider
        >>> provider = create_data_provider('yahoo')
        >>> df = provider.get_stock_data('AAPL', '20230101', '20231231')
        
        >>> # Auto-select provider (uses Tushare by default)
        >>> provider = create_data_provider('auto')
    """
    config = config or {}
    provider = provider.lower().strip()
    
    if provider == 'tushare':
        from .implementations.tushare_provider import TushareProvider
        logger.info("Creating TushareProvider for A-share data")
        return TushareProvider(config)
    
    elif provider == 'yahoo':
        from .implementations.yahoo_provider import YahooProvider
        logger.info("Creating YahooProvider for global data")
        return YahooProvider(config)
    
    elif provider == 'auto':
        # Default to Tushare for A-share, with fallback logic
        try:
            from .implementations.tushare_provider import TushareProvider
            logger.info("Auto-selecting TushareProvider")
            return TushareProvider(config)
        except Exception as e:
            logger.warning(f"Failed to create TushareProvider: {e}, falling back to YahooProvider")
            from .implementations.yahoo_provider import YahooProvider
            return YahooProvider(config)
    
    else:
        raise ValueError(
            f"Unknown provider type: '{provider}'. "
            f"Supported providers: 'tushare', 'yahoo', 'auto'"
        )


def get_provider_for_symbol(
    symbol: str,
    config: Optional[Dict] = None
) -> BaseDataProvider:
    """
    Get appropriate data provider for a given symbol.
    
    Args:
        symbol: Stock/Index/ETF symbol
        config: Provider-specific configuration
        
    Returns:
        BaseDataProvider instance suitable for the symbol
        
    Examples:
        >>> provider = get_provider_for_symbol('000001.SZ')  # Returns TushareProvider
        >>> provider = get_provider_for_symbol('AAPL')       # Returns YahooProvider
        >>> provider = get_provider_for_symbol('510330.SH')  # Returns TushareProvider
    """
    symbol = symbol.upper().strip()
    
    # A-share symbols (Shanghai/Shenzhen)
    if symbol.endswith('.SH') or symbol.endswith('.SZ'):
        return create_data_provider('tushare', config)
    
    # Hong Kong symbols
    if symbol.endswith('.HK'):
        # Tushare supports HK stocks
        try:
            return create_data_provider('tushare', config)
        except Exception:
            return create_data_provider('yahoo', config)
    
    # US/Global symbols (no suffix or common US format)
    if '.' not in symbol or symbol.endswith('.SS'):  # .SS is Yahoo format for Shanghai
        return create_data_provider('yahoo', config)
    
    # Default to Tushare
    return create_data_provider('tushare', config)


class DataProviderFactory:
    """
    Factory class for creating data providers.
    
    This class provides a singleton-like pattern for managing provider instances.
    """
    
    _instances: Dict[str, BaseDataProvider] = {}
    
    @classmethod
    def get_provider(
        cls,
        provider: str = 'auto',
        config: Optional[Dict] = None,
        reuse: bool = True
    ) -> BaseDataProvider:
        """
        Get or create a data provider instance.
        
        Args:
            provider: Provider type ('tushare', 'yahoo', 'auto')
            config: Provider configuration
            reuse: If True, reuse existing instance; if False, create new
            
        Returns:
            BaseDataProvider instance
        """
        cache_key = f"{provider}_{hash(frozenset((config or {}).items()))}"
        
        if reuse and cache_key in cls._instances:
            return cls._instances[cache_key]
        
        instance = create_data_provider(provider, config)
        
        if reuse:
            cls._instances[cache_key] = instance
        
        return instance
    
    @classmethod
    def clear_cache(cls):
        """Clear cached provider instances."""
        cls._instances.clear()
