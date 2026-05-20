#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Yahoo Finance Data Provider (New Architecture)

This module wraps the existing YahooDataProvider with snake_case interface.
It keeps full compatibility with the legacy interface.
"""

import sys
import os

# Add parent path for importing old provider
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from quant.data_providers.yahoo_data_provider import YahooDataProvider as _LegacyYahooProvider
from quant.data.base_provider import BaseDataProvider
from typing import Dict, Optional, List
import pandas as pd


class YahooProvider(BaseDataProvider):
    """
    Yahoo Finance data provider for global stock data.
    
    This is a wrapper around the legacy YahooDataProvider that provides
    a snake_case interface while maintaining full backward compatibility.
    
    Features:
    - US/Global stock data
    - International market data (EU, UK, JP, AU, HK)
    - Chinese ADRs
    - Multiple frequencies (daily, hourly, minute)
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize Yahoo Finance data provider.
        
        Args:
            config: Provider configuration, may include:
                - dataPath: Cache directory path (default './data/yahoo/')
                - cacheEnabled: Whether to enable caching (default True)
                - cacheExpiry: Cache expiry in seconds (default 3600)
        """
        super().__init__(config)
        # Delegate to legacy implementation
        self._legacy = _LegacyYahooProvider(config)
        self.data_path = self._legacy.dataPath
    
    # Core method implementations
    
    def get_stock_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        freq: str = 'D'
    ) -> pd.DataFrame:
        """
        Get stock OHLCV data from Yahoo Finance.
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL', 'TSLA', '0700.HK')
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            freq: Data frequency ('D', '1h', '1min', '5min', '15min', '30min', '60min')
            
        Returns:
            DataFrame with columns: [open, high, low, close, volume, amount, ...]
            Index: DatetimeIndex
        """
        return self._legacy.getStockData(symbol, start_date, end_date, freq)
    
    def get_stock_info(self, symbol: str) -> Dict:
        """
        Get basic stock information from Yahoo Finance.
        
        Returns:
            Dict with keys: symbol, name, industry, sector, market, currency, country
        """
        return self._legacy.getStockInfo(symbol)
    
    def validate_symbol(self, symbol: str) -> bool:
        """Validate if a symbol exists in Yahoo Finance."""
        return self._legacy.validateSymbol(symbol)
    
    def format_symbol(self, symbol: str) -> str:
        """
        Format symbol for Yahoo Finance.
        
        Handles various formats:
        - .SH -> .SS (Shanghai)
        - .SZ -> .SZ (Shenzhen)
        - .HK (Hong Kong)
        - Common indices (IXIC -> ^IXIC)
        """
        return self._legacy.formatSymbol(symbol)
    
    def search_stock(self, keyword: str) -> pd.DataFrame:
        """
        Search for stocks by keyword.
        
        Note: Yahoo Finance doesn't have a built-in search API,
        so this is a simplified implementation using common symbols.
        """
        return self._legacy.searchStock(keyword)
    
    # Metadata methods
    
    def get_supported_frequencies(self) -> List[str]:
        """Get supported data frequencies for Yahoo Finance."""
        return self._legacy.getSupportedFrequencies()
    
    def get_supported_markets(self) -> List[str]:
        """Get supported markets for Yahoo Finance."""
        return self._legacy.getSupportedMarkets()


# Backward compatibility alias
YahooDataProvider = YahooProvider
