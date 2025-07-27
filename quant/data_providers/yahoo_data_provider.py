#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Yahoo Finance Data Provider
Yahoo Finance数据提供者

This module provides data from Yahoo Finance API
此模块提供Yahoo Finance API的数据访问
"""

import pandas as pd
import numpy as np
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List
from .base_data_provider import BaseDataProvider

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

class YahooDataProvider(BaseDataProvider):
    """Yahoo Finance data provider for global stock data"""
    
    def __init__(self, config: Dict = None):
        """Initialize Yahoo Finance data provider"""
        super().__init__(config)
        
        if not YFINANCE_AVAILABLE:
            raise ImportError("yfinance package is required. Install with: pip install yfinance")
        
        # Create data directory if specified
        self.dataPath = self.config.get('dataPath', './data/yahoo/')
        if not os.path.exists(self.dataPath):
            os.makedirs(self.dataPath)
    
    def getStockData(self, symbol: str, startDate: str, endDate: str, freq: str = 'D') -> pd.DataFrame:
        """
        Get stock data from Yahoo Finance
        
        Args:
            symbol (str): Stock symbol (e.g., 'AAPL', 'TSLA')
            startDate (str): Start date in YYYYMMDD format
            endDate (str): End date in YYYYMMDD format
            freq (str): Data frequency ('D' for daily, '1h' for hourly)
            
        Returns:
            pd.DataFrame: Stock data with standardized columns
        """
        try:
            # Validate date range
            if not self._validateDateRange(startDate, endDate):
                raise ValueError("Invalid date range")
            
            # Format symbol for Yahoo Finance
            symbol = self.formatSymbol(symbol)
            
            # Cache file path
            cacheEnabled = self.config.get('cacheEnabled', True)
            cacheExpiry = self.config.get('cacheExpiry', 3600)
            cacheFile = os.path.join(self.dataPath, f"{symbol}_{startDate}_{endDate}_{freq}.csv")
            
            # Check cache
            if cacheEnabled and os.path.exists(cacheFile):
                fileTime = os.path.getmtime(cacheFile)
                if time.time() - fileTime < cacheExpiry:
                    print(f"Loading cached data for {symbol}")
                    return pd.read_csv(cacheFile, index_col=0, parse_dates=True)
            
            print(f"Fetching data for {symbol} from Yahoo Finance")
            
            # Convert dates to Yahoo Finance format
            start = pd.to_datetime(startDate, format='%Y%m%d')
            end = pd.to_datetime(endDate, format='%Y%m%d')
            
            # Map frequency
            intervalMapping = {
                'D': '1d',
                '1h': '1h',
                '1min': '1m',
                '5min': '5m',
                '15min': '15m',
                '30min': '30m',
                '60min': '1h'
            }
            interval = intervalMapping.get(freq, '1d')
            
            # Fetch data from Yahoo Finance
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start, end=end, interval=interval)
            
            if df.empty:
                raise ValueError(f"No data found for symbol {symbol}")
            
            # Process and standardize data
            df = self._processYahooData(df)
            
            # Add technical indicators
            df = self._addTechnicalIndicators(df)
            
            # Save to cache
            if cacheEnabled:
                df.to_csv(cacheFile)
            
            return df
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {str(e)}")
            raise
    
    def _processYahooData(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process raw data from Yahoo Finance"""
        # Yahoo Finance column mapping
        columnMapping = {
            'Open': 'open',
            'High': 'high', 
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        }
        
        # Rename columns
        df = df.rename(columns=columnMapping)
        
        # Reset index to make date a column
        df = df.reset_index()
        df = df.rename(columns={'Date': 'date'})
        df = df.set_index('date')
        
        # Sort by date
        df = df.sort_index()
        
        # Fill missing values
        df = df.fillna(method='ffill')
        
        # Calculate amount (approximation)
        if 'volume' in df.columns and 'close' in df.columns:
            df['amount'] = df['volume'] * df['close']
        
        return df
    
    def getStockInfo(self, symbol: str) -> Dict:
        """Get basic stock information from Yahoo Finance"""
        try:
            symbol = self.formatSymbol(symbol)
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Standardize the info format
            return {
                'symbol': symbol,
                'name': info.get('longName', info.get('shortName', symbol)),
                'industry': info.get('industry', 'Unknown'),
                'sector': info.get('sector', 'Unknown'),
                'market': info.get('exchange', 'Unknown'),
                'currency': info.get('currency', 'USD'),
                'country': info.get('country', 'Unknown')
            }
            
        except Exception as e:
            print(f"Error getting stock info for {symbol}: {str(e)}")
            raise
    
    def searchStock(self, keyword: str) -> pd.DataFrame:
        """
        Search for stocks by keyword (limited functionality in Yahoo Finance)
        Note: Yahoo Finance doesn't have a built-in search API, 
        so this is a simplified implementation
        """
        try:
            # This is a basic implementation - in practice, you might want to 
            # use a separate search service or maintain a symbol database
            
            # Common symbols for demonstration
            commonSymbols = {
                'apple': 'AAPL',
                'tesla': 'TSLA', 
                'microsoft': 'MSFT',
                'google': 'GOOGL',
                'amazon': 'AMZN',
                'meta': 'META',
                'nvidia': 'NVDA',
                'berkshire': 'BRK-B'
            }
            
            results = []
            keyword_lower = keyword.lower()
            
            for name, symbol in commonSymbols.items():
                if keyword_lower in name or keyword_lower in symbol.lower():
                    try:
                        info = self.getStockInfo(symbol)
                        results.append({
                            'symbol': symbol,
                            'name': info['name'],
                            'industry': info['industry'],
                            'market': info['market']
                        })
                    except:
                        continue
            
            return pd.DataFrame(results)
            
        except Exception as e:
            print(f"Error searching stocks: {str(e)}")
            return pd.DataFrame()
    
    def validateSymbol(self, symbol: str) -> bool:
        """Validate if a symbol exists in Yahoo Finance"""
        try:
            symbol = self.formatSymbol(symbol)
            ticker = yf.Ticker(symbol)
            # Try to get basic info to validate
            info = ticker.info
            return 'symbol' in info or 'shortName' in info
        except:
            return False
    
    def formatSymbol(self, symbol: str) -> str:
        """Format symbol for Yahoo Finance"""
        symbol = symbol.upper().strip()
        
        # Yahoo Finance uses different formats for different markets
        # This is a basic implementation - extend as needed
        
        # Handle Chinese stocks (if trading on US exchanges)
        chineseAdrs = {
            'BABA': 'BABA',    # Alibaba
            'JD': 'JD',        # JD.com
            'BIDU': 'BIDU',    # Baidu
            'NIO': 'NIO',      # NIO
            'XPEV': 'XPEV',    # XPeng
            'LI': 'LI'         # Li Auto
        }
        
        if symbol in chineseAdrs:
            return chineseAdrs[symbol]
        
        return symbol
    
    def getSupportedFrequencies(self) -> List[str]:
        """Get supported data frequencies for Yahoo Finance"""
        return ['D', '1h', '1min', '5min', '15min', '30min', '60min']
    
    def getSupportedMarkets(self) -> List[str]:
        """Get supported markets for Yahoo Finance"""
        return ['US', 'CA', 'EU', 'UK', 'JP', 'AU', 'HK', 'CN'] 