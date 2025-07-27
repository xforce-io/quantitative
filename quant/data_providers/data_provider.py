import traceback
import tushare as ts
import pandas as pd
import numpy as np
import os
import time
from datetime import datetime, timedelta
from quant.config.config import Config
from .base_data_provider import BaseDataProvider

class TushareDataProvider(BaseDataProvider):
    """Tushare data provider for A-share stock data"""
    
    def __init__(self, config: dict = None):
        """Initialize Tushare data provider"""
        super().__init__(config)
        
        token = self.config.get('token') or Config.TUSHARE_TOKEN
        if not token:
            raise ValueError("Tushare token is required. Please set TUSHARE_TOKEN in environment variables or pass in config.")
        
        ts.set_token(token)
        self.pro = ts.pro_api()
        
        # Create data directory if it doesn't exist
        dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare')
        if not os.path.exists(dataPath):
            os.makedirs(dataPath)
    
    def getStockData(self, symbol, startDate, endDate, freq='D'):
        """
        Get stock daily data from Tushare
        
        Args:
            symbol (str): Stock symbol (e.g., '000001.SZ')
            startDate (str): Start date in YYYYMMDD format
            endDate (str): End date in YYYYMMDD format
            freq (str): Data frequency ('D' for daily, '60' for hourly)
            
        Returns:
            pd.DataFrame: Stock data with OHLCV columns
        """
        try:
            # Cache file path
            dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare')
            cacheFile = os.path.join(
                dataPath, 
                f"{symbol}_{startDate}_{endDate}_{freq}.csv"
            )
            
            # Check if cached data exists and is valid
            cacheEnabled = self.config.get('cacheEnabled', True)
            cacheExpiry = self.config.get('cacheExpiry', 3600)
            
            if cacheEnabled and os.path.exists(cacheFile):
                fileTime = os.path.getmtime(cacheFile)
                if time.time() - fileTime < cacheExpiry:
                    print(f"Loading cached data for {symbol}")
                    return pd.read_csv(cacheFile, index_col=0, parse_dates=True)
            
            print(f"Fetching data for {symbol} from {startDate} to {endDate}")
            
            if freq == 'D':
                # Get daily data
                df = self.pro.daily(
                    ts_code=symbol,
                    start_date=startDate,
                    end_date=endDate
                )
            else:
                # Get minute/hourly data (requires special handling)
                df = self._getIntraDayData(symbol, startDate, endDate, freq)
            
            if df.empty:
                # Smart date handling: if single date query fails, try expanding date range
                if startDate == endDate:
                    print(f"No data for single date {startDate}, trying extended date range...")
                    return self._getDataWithExtendedRange(symbol, startDate, endDate, freq, cacheFile, cacheEnabled)
                else:
                    raise ValueError(f"No data found for symbol {symbol}")
            
            # Process data
            df = self._processStockData(df)
            
            # Save to cache
            if cacheEnabled:
                df.to_csv(cacheFile)
            
            return df
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {str(e)} traceback: {traceback.format_exc()}")
            raise

    def getIndexData(self, symbol, startDate, endDate, freq='D'):
        """
        Get index daily data from Tushare
        
        Args:
            symbol (str): Index symbol (e.g., '000300.SH', '399300.SZ')
            startDate (str): Start date in YYYYMMDD format
            endDate (str): End date in YYYYMMDD format
            freq (str): Data frequency ('D' for daily)
            
        Returns:
            pd.DataFrame: Index data with OHLCV columns
        """
        try:
            # Convert index symbol to correct Tushare format
            indexSymbol = self._convertToIndexSymbol(symbol)
            
            # Cache file path
            dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare')
            cacheFile = os.path.join(
                dataPath, 
                f"index_{indexSymbol}_{startDate}_{endDate}_{freq}.csv"
            )
            
            # Check if cached data exists and is valid
            cacheEnabled = self.config.get('cacheEnabled', True)
            cacheExpiry = self.config.get('cacheExpiry', 3600)
            
            if cacheEnabled and os.path.exists(cacheFile):
                fileTime = os.path.getmtime(cacheFile)
                if time.time() - fileTime < cacheExpiry:
                    print(f"Loading cached index data for {indexSymbol}")
                    return pd.read_csv(cacheFile, index_col=0, parse_dates=True)
            
            print(f"Fetching index data for {indexSymbol} from {startDate} to {endDate}")
            
            if freq == 'D':
                # Use index_daily API according to Tushare Pro documentation
                df = self.pro.index_daily(
                    ts_code=indexSymbol,
                    start_date=startDate,
                    end_date=endDate
                )
            else:
                print("Warning: Intraday index data requires Tushare Pro subscription")
                return pd.DataFrame()
            
            if df.empty:
                # Smart date handling: if single date query fails, try expanding date range
                if startDate == endDate:
                    print(f"No index data for single date {startDate}, trying extended date range...")
                    return self._getIndexDataWithExtendedRange(indexSymbol, startDate, endDate, freq, cacheFile, cacheEnabled)
                else:
                    raise ValueError(f"No index data found for symbol {indexSymbol}")
            
            # Process data (same as stock data)
            df = self._processStockData(df)
            
            # Save to cache
            if cacheEnabled:
                df.to_csv(cacheFile)
            
            return df
            
        except Exception as e:
            print(f"Error fetching index data for {symbol}: {str(e)} traceback: {traceback.format_exc()}")
            raise

    def _convertToIndexSymbol(self, symbol):
        """Convert index symbol to correct Tushare format"""
        # Map common index codes to correct Tushare format
        indexMapping = {
            '000300.SH': '000300.SH',  # 沪深300 (上海)
            '399300.SZ': '000300.SH',  # 沪深300 - 注意：399300.SZ不存在，映射到000300.SH
            '000001.SH': '000001.SH',  # 上证综指
            '399001.SZ': '399001.SZ',  # 深证成指
            '000016.SH': '000016.SH',  # 上证50
            '399006.SZ': '399006.SZ',  # 创业板指
            '399005.SZ': '399005.SZ',  # 中小板指
        }
        
        # 如果有映射，使用映射后的符号
        mappedSymbol = indexMapping.get(symbol, symbol)
        
        # 如果映射发生了变化，记录日志
        if mappedSymbol != symbol:
            print(f"📝 Index symbol mapping: {symbol} -> {mappedSymbol}")
        
        return mappedSymbol
    
    def _getIntraDayData(self, symbol, startDate, endDate, freq):
        """Get intraday data (implementation depends on subscription level)"""
        # Note: Intraday data requires Tushare Pro subscription
        # This is a placeholder implementation
        print("Warning: Intraday data requires Tushare Pro subscription")
        return pd.DataFrame()
    
    def _processStockData(self, df):
        """Process raw stock data from Tushare"""
        # Rename columns to standard format
        columnMapping = {
            'trade_date': 'date',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'vol': 'volume',
            'amount': 'amount'
        }
        
        df = df.rename(columns=columnMapping)
        
        # Convert date to datetime
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        
        # Sort by date
        df = df.sort_index()
        
        # Fill missing values
        df = df.fillna(method='ffill')
        
        # Calculate additional technical indicators
        df['returns'] = df['close'].pct_change()
        df['logReturns'] = np.log(df['close'] / df['close'].shift(1))
        
        # Calculate moving averages
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma60'] = df['close'].rolling(window=60).mean()
        
        # Calculate volatility
        df['volatility'] = df['returns'].rolling(window=20).std() * np.sqrt(252)
        
        return df
    
    def getStockInfo(self, symbol):
        """Get basic stock information"""
        try:
            stockInfo = self.pro.stock_basic(ts_code=symbol)
            if stockInfo.empty:
                raise ValueError(f"Stock {symbol} not found")
            
            return stockInfo.iloc[0].to_dict()
            
        except Exception as e:
            print(f"Error getting stock info for {symbol}: {str(e)}")
            raise
    
    def searchStock(self, keyword):
        """Search stocks by name or code"""
        try:
            stocks = self.pro.stock_basic()
            
            # Search by stock code or name
            result = stocks[
                stocks['ts_code'].str.contains(keyword, case=False, na=False) |
                stocks['name'].str.contains(keyword, case=False, na=False)
            ]
            
            return result[['ts_code', 'name', 'industry', 'market']].head(10)
            
        except Exception as e:
            print(f"Error searching stocks: {str(e)}")
            raise
    
    def validateSymbol(self, symbol: str) -> bool:
        """Validate if a symbol is valid for Tushare (A-share format)"""
        try:
            # A-share symbols should end with .SZ or .SH
            return symbol.endswith('.SZ') or symbol.endswith('.SH')
        except:
            return False
    
    def formatSymbol(self, symbol: str) -> str:
        """Format symbol to Tushare format"""
        symbol = symbol.upper().strip()
        
        # If already in correct format, return as is
        if self.validateSymbol(symbol):
            return symbol
        
        # Try to auto-format common patterns
        if len(symbol) == 6 and symbol.isdigit():
            # Guess market based on code range
            if symbol.startswith('00') or symbol.startswith('30'):
                return f"{symbol}.SZ"  # Shenzhen
            elif symbol.startswith('60') or symbol.startswith('68'):
                return f"{symbol}.SH"  # Shanghai
        
        return symbol
    
    def getSupportedFrequencies(self) -> list:
        """Get supported data frequencies for Tushare"""
        return ['D', '1min', '5min', '15min', '30min', '60min']
    
    def getSupportedMarkets(self) -> list:
        """Get supported markets for Tushare"""
        return ['CN']  # China A-shares 

    def _getDataWithExtendedRange(self, symbol, startDate, endDate, freq, cacheFile, cacheEnabled):
        """
        Get stock data with extended date range when single date fails
        
        Args:
            symbol (str): Stock symbol
            startDate (str): Original start date
            endDate (str): Original end date
            freq (str): Data frequency
            cacheFile (str): Cache file path
            cacheEnabled (bool): Whether caching is enabled
            
        Returns:
            pd.DataFrame: Stock data for the closest available trading day
        """
        try:
            startObj = datetime.strptime(startDate, '%Y%m%d')
            endObj = datetime.strptime(endDate, '%Y%m%d')
            
            # Extend date range by 10 days before and 5 days after
            extendedStartDate = (startObj - timedelta(days=10)).strftime('%Y%m%d')
            extendedEndDate = (endObj + timedelta(days=5)).strftime('%Y%m%d')
            
            print(f"🔄 Extending date range for {symbol}: {extendedStartDate} - {extendedEndDate}")
            
            # Get data with extended range
            if freq == 'D':
                df = self.pro.daily(
                    ts_code=symbol,
                    start_date=extendedStartDate,
                    end_date=extendedEndDate
                )
            else:
                df = self._getIntraDayData(symbol, extendedStartDate, extendedEndDate, freq)
            
            if df.empty:
                raise ValueError(f"No data found for symbol {symbol} even with extended date range")
            
            # Process data
            df = self._processStockData(df)
            
            # Filter to get the closest available data to the requested date
            requestedDate = pd.to_datetime(startDate, format='%Y%m%d')
            
            # Find the closest trading day
            df['date_diff'] = abs((df.index - requestedDate).days)
            closest_data = df.loc[df['date_diff'].idxmin()].to_frame().T
            closest_data = closest_data.drop('date_diff', axis=1)
            
            print(f"✅ Found closest trading day data for {symbol}: {closest_data.index[0].strftime('%Y-%m-%d')}")
            
            # Save to cache using original cache file name
            if cacheEnabled:
                closest_data.to_csv(cacheFile)
            
            return closest_data
            
        except Exception as e:
            print(f"❌ Extended date range also failed for {symbol}: {str(e)}")
            raise

    def _getIndexDataWithExtendedRange(self, indexSymbol, startDate, endDate, freq, cacheFile, cacheEnabled):
        """
        Get index data with extended date range when single date fails
        
        Args:
            indexSymbol (str): Index symbol
            startDate (str): Original start date
            endDate (str): Original end date
            freq (str): Data frequency
            cacheFile (str): Cache file path
            cacheEnabled (bool): Whether caching is enabled
            
        Returns:
            pd.DataFrame: Index data for the closest available trading day
        """
        try:
            startObj = datetime.strptime(startDate, '%Y%m%d')
            endObj = datetime.strptime(endDate, '%Y%m%d')
            
            # Extend date range by 10 days before and 5 days after
            extendedStartDate = (startObj - timedelta(days=10)).strftime('%Y%m%d')
            extendedEndDate = (endObj + timedelta(days=5)).strftime('%Y%m%d')
            
            print(f"🔄 Extending date range for index {indexSymbol}: {extendedStartDate} - {extendedEndDate}")
            
            # Get index data with extended range
            if freq == 'D':
                df = self.pro.index_daily(
                    ts_code=indexSymbol,
                    start_date=extendedStartDate,
                    end_date=extendedEndDate
                )
            else:
                print("Warning: Intraday index data requires Tushare Pro subscription")
                return pd.DataFrame()
            
            if df.empty:
                raise ValueError(f"No index data found for symbol {indexSymbol} even with extended date range")
            
            # Process data
            df = self._processStockData(df)
            
            # Filter to get the closest available data to the requested date
            requestedDate = pd.to_datetime(startDate, format='%Y%m%d')
            
            # Find the closest trading day
            df['date_diff'] = abs((df.index - requestedDate).days)
            closest_data = df.loc[df['date_diff'].idxmin()].to_frame().T
            closest_data = closest_data.drop('date_diff', axis=1)
            
            print(f"✅ Found closest index trading day data for {indexSymbol}: {closest_data.index[0].strftime('%Y-%m-%d')}")
            
            # Save to cache using original cache file name
            if cacheEnabled:
                closest_data.to_csv(cacheFile)
            
            return closest_data
            
        except Exception as e:
            print(f"❌ Extended date range also failed for index {indexSymbol}: {str(e)}")
            raise 