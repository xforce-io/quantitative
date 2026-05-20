#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Base Data Provider Abstract Class

This module defines the abstract interface for all data providers.
All methods use snake_case naming.
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime


class BaseDataProvider(ABC):
    """
    Abstract base class for all data providers.

    All data providers must implement this interface to ensure unified data access.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize data provider.
        
        Args:
            config: Provider-specific configuration
        """
        self.config = config or {}
        self.provider_name = self.__class__.__name__
    
    # Core abstract methods
    
    @abstractmethod
    def get_stock_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        freq: str = 'D'
    ) -> pd.DataFrame:
        """
        Get stock OHLCV data for a given symbol and date range.
        
        Args:
            symbol: Stock symbol (e.g., '000001.SZ', 'AAPL')
            start_date: Start date in YYYYMMDD or YYYY-MM-DD format
            end_date: End date in YYYYMMDD or YYYY-MM-DD format
            freq: Data frequency ('D' for daily, 'W' for weekly, 'M' for monthly)
            
        Returns:
            DataFrame with columns: [open, high, low, close, volume]
            Index: DatetimeIndex named 'date'
            
        Raises:
            ValueError: If symbol is invalid or no data found
        """
        pass
    
    @abstractmethod
    def get_stock_info(self, symbol: str) -> Dict:
        """
        Get basic information about a stock.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dict containing stock info: name, industry, market, etc.
        """
        pass
    
    @abstractmethod
    def validate_symbol(self, symbol: str) -> bool:
        """
        Validate if a symbol is valid for this provider.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            True if valid, False otherwise
        """
        pass
    
    @abstractmethod
    def format_symbol(self, symbol: str) -> str:
        """
        Format symbol to provider-specific format.
        
        Args:
            symbol: Raw symbol
            
        Returns:
            Provider-formatted symbol
        """
        pass
    
    # Optional methods with default implementations
    
    def get_index_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        freq: str = 'D'
    ) -> pd.DataFrame:
        """
        Get index data for a given symbol and date range.
        
        Default implementation raises NotImplementedError.
        Providers that support index data should override this method.
        """
        raise NotImplementedError(
            f"Index data not supported by {self.provider_name}"
        )
    
    def get_fund_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        freq: str = 'D'
    ) -> pd.DataFrame:
        """
        Get fund/ETF data for a given symbol and date range.
        
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError(
            f"Fund data not supported by {self.provider_name}"
        )
    
    def get_financial_data(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict:
        """
        Get financial data including EPS, PE, PB, etc.
        
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError(
            f"Financial data not supported by {self.provider_name}"
        )
    
    def search_stock(self, keyword: str) -> pd.DataFrame:
        """
        Search for stocks by keyword.
        
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError(
            f"Stock search not supported by {self.provider_name}"
        )
    
    # Utility methods
    
    def get_provider_info(self) -> Dict:
        """
        Get information about this data provider.
        
        Returns:
            Dict with provider name, config, supported frequencies and markets
        """
        return {
            'name': self.provider_name,
            'config': {k: v for k, v in self.config.items() if k != 'token'},
            'supported_frequencies': self.get_supported_frequencies(),
            'supported_markets': self.get_supported_markets()
        }
    
    def get_supported_frequencies(self) -> List[str]:
        """
        Get list of supported data frequencies.
        
        Returns:
            List of frequency codes: ['D', 'W', 'M', '1h', etc.]
        """
        return ['D']  # Daily only by default
    
    def get_supported_markets(self) -> List[str]:
        """
        Get list of supported markets.
        
        Returns:
            List of market codes: ['CN', 'US', 'HK', etc.]
        """
        return ['CN']  # China only by default
    
    def validate_date_range(self, start_date: str, end_date: str) -> bool:
        """
        Validate date range.
        
        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Try YYYYMMDD format first
            try:
                start = datetime.strptime(start_date, '%Y%m%d')
                end = datetime.strptime(end_date, '%Y%m%d')
            except ValueError:
                # Try YYYY-MM-DD format
                start = datetime.strptime(start_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d')
            return start <= end
        except Exception:
            return False
    
    def standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize column names to lowercase.
        
        Args:
            df: Raw data from provider
            
        Returns:
            DataFrame with standardized columns
        """
        standard_columns = {
            'Date': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
            'Amount': 'amount',
            'trade_date': 'date',
            'vol': 'volume',
        }
        
        rename_mapping = {}
        for col in df.columns:
            if col in standard_columns:
                rename_mapping[col] = standard_columns[col]
            elif col.lower() != col:
                rename_mapping[col] = col.lower()
        
        if rename_mapping:
            df = df.rename(columns=rename_mapping)
        
        return df
    
    # Backward-compatible aliases.
    # Keep compatibility with the legacy interface during migration.
    
    def getStockData(self, symbol: str, startDate: str, endDate: str, freq: str = 'D') -> pd.DataFrame:
        """Deprecated: Use get_stock_data instead."""
        return self.get_stock_data(symbol, startDate, endDate, freq)
    
    def getStockInfo(self, symbol: str) -> Dict:
        """Deprecated: Use get_stock_info instead."""
        return self.get_stock_info(symbol)
    
    def getIndexData(self, symbol: str, startDate: str, endDate: str, freq: str = 'D') -> pd.DataFrame:
        """Deprecated: Use get_index_data instead."""
        return self.get_index_data(symbol, startDate, endDate, freq)
    
    def validateSymbol(self, symbol: str) -> bool:
        """Deprecated: Use validate_symbol instead."""
        return self.validate_symbol(symbol)
    
    def formatSymbol(self, symbol: str) -> str:
        """Deprecated: Use format_symbol instead."""
        return self.format_symbol(symbol)
    
    def searchStock(self, keyword: str) -> pd.DataFrame:
        """Deprecated: Use search_stock instead."""
        return self.search_stock(keyword)
