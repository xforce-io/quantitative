#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Base Data Provider Abstract Class
数据提供者抽象基类

This module defines the abstract interface for all data providers
此模块定义了所有数据提供者的抽象接口
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, List, Optional

class BaseDataProvider(ABC):
    """Abstract base class for all data providers"""
    
    def __init__(self, config: Dict = None):
        """
        Initialize data provider
        
        Args:
            config (Dict): Provider-specific configuration
        """
        self.config = config or {}
        self.providerName = self.__class__.__name__
        
    @abstractmethod
    def getStockData(self, symbol: str, startDate: str, endDate: str, freq: str = 'D') -> pd.DataFrame:
        """
        Get stock data for a given symbol and date range
        
        Args:
            symbol (str): Stock symbol
            startDate (str): Start date in YYYYMMDD format
            endDate (str): End date in YYYYMMDD format  
            freq (str): Data frequency ('D' for daily, '1h' for hourly, etc.)
            
        Returns:
            pd.DataFrame: Stock data with standardized columns
        """
        pass
    
    @abstractmethod
    def getStockInfo(self, symbol: str) -> Dict:
        """
        Get basic information about a stock
        
        Args:
            symbol (str): Stock symbol
            
        Returns:
            Dict: Stock information
        """
        pass
    
    @abstractmethod
    def searchStock(self, keyword: str) -> pd.DataFrame:
        """
        Search for stocks by keyword
        
        Args:
            keyword (str): Search keyword
            
        Returns:
            pd.DataFrame: Search results
        """
        pass
    
    def getIndexData(self, symbol: str, startDate: str, endDate: str, freq: str = 'D') -> pd.DataFrame:
        """
        Get index data for a given symbol and date range (optional implementation)
        
        Args:
            symbol (str): Index symbol
            startDate (str): Start date in YYYYMMDD format
            endDate (str): End date in YYYYMMDD format  
            freq (str): Data frequency ('D' for daily, '1h' for hourly, etc.)
            
        Returns:
            pd.DataFrame: Index data with standardized columns
            
        Raises:
            NotImplementedError: If provider doesn't support index data
        """
        raise NotImplementedError(f"Index data not supported by {self.providerName}")
    
    def getGlobalIndexData(self, symbol: str, startDate: str, endDate: str, freq: str = 'D') -> pd.DataFrame:
        """
        Get global index data for a given symbol and date range (optional implementation)
        
        Args:
            symbol (str): Global index symbol (e.g., IXIC, SPX, DJI)
            startDate (str): Start date in YYYYMMDD format
            endDate (str): End date in YYYYMMDD format  
            freq (str): Data frequency ('D' for daily, '1h' for hourly, etc.)
            
        Returns:
            pd.DataFrame: Global index data with standardized columns
            
        Raises:
            NotImplementedError: If provider doesn't support global index data
        """
        raise NotImplementedError(f"Global index data not supported by {self.providerName}")
    
    @abstractmethod
    def validateSymbol(self, symbol: str) -> bool:
        """
        Validate if a symbol is valid for this provider
        
        Args:
            symbol (str): Stock symbol
            
        Returns:
            bool: True if valid, False otherwise
        """
        pass
    
    @abstractmethod
    def formatSymbol(self, symbol: str) -> str:
        """
        Format symbol to provider-specific format
        
        Args:
            symbol (str): Raw symbol
            
        Returns:
            str: Provider-formatted symbol
        """
        pass
    
    def _standardizeColumns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize column names across different providers
        
        Args:
            df (pd.DataFrame): Raw data from provider
            
        Returns:
            pd.DataFrame: Data with standardized columns
        """
        # Default implementation - should be overridden by subclasses
        standardColumns = {
            'date': 'date',
            'open': 'open', 
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume',
            'amount': 'amount'
        }
        
        # Rename columns if they exist
        existingColumns = df.columns.tolist()
        renameMapping = {}
        
        for standard, provider in standardColumns.items():
            if provider in existingColumns:
                renameMapping[provider] = standard
        
        if renameMapping:
            df = df.rename(columns=renameMapping)
        
        return df
    
    def _addTechnicalIndicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add common technical indicators to the dataframe
        
        Args:
            df (pd.DataFrame): Stock data with OHLCV columns
            
        Returns:
            pd.DataFrame: Data with technical indicators added
        """
        if 'close' not in df.columns:
            return df
        
        # Calculate returns
        df['returns'] = df['close'].pct_change()
        df['logReturns'] = pd.Series(index=df.index, dtype=float)
        df.loc[df['close'].shift(1) > 0, 'logReturns'] = \
            (df['close'] / df['close'].shift(1)).apply(lambda x: pd.Series([x]).apply('log')[0] if x > 0 else 0)
        
        # Calculate moving averages
        for window in [5, 10, 20, 60]:
            df[f'ma{window}'] = df['close'].rolling(window=window).mean()
        
        # Calculate volatility (20-day rolling)
        df['volatility'] = df['returns'].rolling(window=20).std() * (252 ** 0.5)
        
        # Calculate RSI (14-day)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        return df
    
    def _validateDateRange(self, startDate: str, endDate: str) -> bool:
        """
        Validate date range
        
        Args:
            startDate (str): Start date in YYYYMMDD format
            endDate (str): End date in YYYYMMDD format
            
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            start = pd.to_datetime(startDate, format='%Y%m%d')
            end = pd.to_datetime(endDate, format='%Y%m%d')
            return start <= end
        except:
            return False
    
    def getProviderInfo(self) -> Dict:
        """
        Get information about this data provider
        
        Returns:
            Dict: Provider information
        """
        return {
            'name': self.providerName,
            'config': self.config,
            'supported_frequencies': self.getSupportedFrequencies(),
            'supported_markets': self.getSupportedMarkets()
        }
    
    def getSupportedFrequencies(self) -> List[str]:
        """
        Get list of supported data frequencies
        
        Returns:
            List[str]: Supported frequencies
        """
        # Default implementation - should be overridden
        return ['D']  # Daily only
    
    def getSupportedMarkets(self) -> List[str]:
        """
        Get list of supported markets
        
        Returns:
            List[str]: Supported markets
        """
        # Default implementation - should be overridden
        return ['CN']  # China only 