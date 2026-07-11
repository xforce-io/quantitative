import traceback
import tushare as ts
import pandas as pd
import numpy as np
import os
import time
import json
import hashlib
from datetime import datetime, timedelta
from quant.core.legacy_config import Config
from .base_data_provider import BaseDataProvider

from quant.core.logging_config import get_logger
logger = get_logger(__name__)

# 统一缓存配置
CACHE_TTL = {
    'historical': 7 * 24 * 3600,   # 历史数据: 7天
    'today': 1 * 3600,             # 当日数据: 1小时
    'static': 30 * 24 * 3600,      # 静态数据 (股票列表、交易日历): 30天
    'default': 24 * 3600           # 默认: 24小时
}


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
        self._cache_dir = dataPath
    
    def _get_cache_ttl(self, date_str: str = None) -> int:
        """根据日期智能选择 TTL"""
        if date_str is None:
            return CACHE_TTL['default']
        
        today_str = datetime.now().strftime('%Y%m%d')
        if date_str >= today_str:
            return CACHE_TTL['today']  # 当日数据，短缓存
        else:
            return CACHE_TTL['historical']  # 历史数据，长缓存
    
    def _disk_cache(self, cache_key: str, fetch_fn, ttl: int = None, date_hint: str = None):
        """
        统一的磁盘缓存逻辑
        
        Args:
            cache_key: 缓存键名 (会被 hash 用于文件名)
            fetch_fn: 获取数据的函数 (无参数)
            ttl: 缓存过期时间 (秒)，如果为 None 则根据 date_hint 智能选择
            date_hint: 日期提示，用于智能 TTL
        
        Returns:
            DataFrame 或 dict
        """
        if ttl is None:
            ttl = self._get_cache_ttl(date_hint)
        
        # 生成缓存文件路径
        cache_hash = hashlib.md5(cache_key.encode()).hexdigest()[:12]
        cache_file = os.path.join(self._cache_dir, f"cache_{cache_hash}.pkl")
        
        # 检查缓存
        if os.path.exists(cache_file):
            file_time = os.path.getmtime(cache_file)
            if time.time() - file_time < ttl:
                try:
                    logger.debug(f"Cache hit: {cache_key[:50]}...")
                    return pd.read_pickle(cache_file)
                except Exception as e:
                    logger.warning(f"Cache read failed: {e}")
        
        # 获取新数据
        result = fetch_fn()
        
        # 保存到缓存
        if result is not None:
            try:
                if isinstance(result, pd.DataFrame):
                    result.to_pickle(cache_file)
                elif isinstance(result, dict):
                    pd.DataFrame([result]).to_pickle(cache_file)
                logger.debug(f"Cache saved: {cache_key[:50]}...")
            except Exception as e:
                logger.warning(f"Cache save failed: {e}")
        
        return result

    def _parse_trade_date(self, value) -> datetime:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            raise ValueError("trade_date is missing")

        if isinstance(value, (int, np.integer)):
            value = str(int(value))
        else:
            value = str(value).strip()

        if len(value) >= 10 and value[4] == '-' and value[7] == '-':
            return datetime.strptime(value[:10], '%Y-%m-%d')

        if len(value) == 8 and value.isdigit():
            return datetime.strptime(value, '%Y%m%d')

        return pd.to_datetime(value).to_pydatetime()

    def _fetch_with_backward_paging(
        self,
        fetch_fn,
        startDate: str,
        endDate: str,
        *,
        date_col: str = 'trade_date',
        paging_threshold: int = 1800,
        max_pages: int = 50,
        sleep_seconds: float = 0.0,
    ) -> pd.DataFrame:
        desired_start = datetime.strptime(startDate, '%Y%m%d')
        cur_end = datetime.strptime(endDate, '%Y%m%d')

        pages = []
        last_end = None

        for _ in range(max_pages):
            cur_end_str = cur_end.strftime('%Y%m%d')
            if cur_end_str == last_end:
                break
            last_end = cur_end_str

            df = fetch_fn(startDate, cur_end_str)
            if df is None or df.empty:
                break

            if date_col not in df.columns:
                return df

            pages.append(df)

            try:
                min_dt = self._parse_trade_date(df[date_col].min())
            except Exception:
                break

            if min_dt <= desired_start:
                break

            if len(df) < paging_threshold:
                break

            next_end = min_dt - timedelta(days=1)
            if next_end >= cur_end:
                break

            cur_end = next_end
            if sleep_seconds and sleep_seconds > 0:
                time.sleep(sleep_seconds)

        if not pages:
            return pd.DataFrame()

        combined = pd.concat(pages, ignore_index=True)
        if date_col in combined.columns:
            combined = combined.drop_duplicates(subset=[date_col])
            combined = combined.sort_values(date_col)

        return combined
    
    def getStockData(self, symbol, startDate, endDate, freq='D'):
        """
        Get stock daily data from Tushare
        
        Args:
            symbol (str): Stock symbol (e.g., '000001.SZ' for A-share, '00700.HK' for HK stock)
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
                    logger.info(f"Loading cached data for {symbol}")
                    return pd.read_csv(cacheFile, index_col=0, parse_dates=True)
            
            logger.info(f"Fetching data for {symbol} from {startDate} to {endDate}")
            
            # Detect if it's a Hong Kong stock
            is_hk_stock = symbol.endswith('.HK')
            
            if freq == 'D':
                if is_hk_stock:
                    # Use hk_daily API for Hong Kong stocks
                    # Need to convert format: 0700.HK -> 00700.HK (5 digits)
                    hk_symbol = self._formatHKSymbol(symbol)
                    df = self._fetch_with_backward_paging(
                        lambda s, e: self.pro.hk_daily(ts_code=hk_symbol, start_date=s, end_date=e),
                        startDate,
                        endDate,
                        paging_threshold=int(self.config.get('pagingThreshold', 1800)),
                        max_pages=int(self.config.get('pagingMaxPages', 50)),
                        sleep_seconds=float(self.config.get('pagingSleepSeconds', 0.0)),
                    )
                else:
                    # Get A-share daily data
                    df = self._fetch_with_backward_paging(
                        lambda s, e: self.pro.daily(ts_code=symbol, start_date=s, end_date=e),
                        startDate,
                        endDate,
                        paging_threshold=int(self.config.get('pagingThreshold', 1800)),
                        max_pages=int(self.config.get('pagingMaxPages', 50)),
                        sleep_seconds=float(self.config.get('pagingSleepSeconds', 0.0)),
                    )
            else:
                # Get minute/hourly data (requires special handling)
                df = self._getIntraDayData(symbol, startDate, endDate, freq)
            
            if df.empty:
                # Smart date handling: if single date query fails, try expanding date range
                if startDate == endDate:
                    logger.info(f"No data for single date {startDate}, trying extended date range...")
                    return self._getDataWithExtendedRange(symbol, startDate, endDate, freq, cacheFile, cacheEnabled)

                # ETFs/funds are not on pro.daily — fall back to fund_daily path.
                # Mirrors quant.data.providers.DataProvider stock→fund fallback.
                if not is_hk_stock and freq == 'D':
                    try:
                        logger.info(
                            f"No daily data for {symbol}; trying fund/ETF API fallback"
                        )
                        return self.getFundData(symbol, startDate, endDate, freq)
                    except Exception as fund_e:
                        logger.info(f"Fund/ETF fallback failed for {symbol}: {fund_e}")

                raise ValueError(f"No data found for symbol {symbol}")
            
            # Process data
            df = self._processStockData(df)
            
            # Save to cache
            if cacheEnabled:
                df.to_csv(cacheFile)
            
            return df
            
        except Exception as e:
            logger.error(
                f"fetching data for {symbol}: {e} traceback: {traceback.format_exc()}"
            )
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
                    logger.info(f"Loading cached index data for {indexSymbol}")
                    return pd.read_csv(cacheFile, index_col=0, parse_dates=True)
            
            logger.info(f"Fetching index data for {indexSymbol} from {startDate} to {endDate}")
            
            if freq == 'D':
                # Use index_daily API according to Tushare Pro documentation
                df = self._fetch_with_backward_paging(
                    lambda s, e: self.pro.index_daily(ts_code=indexSymbol, start_date=s, end_date=e),
                    startDate,
                    endDate,
                    paging_threshold=int(self.config.get('pagingThreshold', 1800)),
                    max_pages=int(self.config.get('pagingMaxPages', 50)),
                    sleep_seconds=float(self.config.get('pagingSleepSeconds', 0.0)),
                )
            else:
                logger.warning("Intraday index data requires Tushare Pro subscription")
                return pd.DataFrame()
            
            if df.empty:
                # Smart date handling: if single date query fails, try expanding date range
                if startDate == endDate:
                    logger.info(f"No index data for single date {startDate}, trying extended date range...")
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
            logger.error(f"fetching index data for {symbol}: {e} traceback: {traceback.format_exc()}")
            raise

    def _formatHKSymbol(self, symbol):
        """Format Hong Kong stock symbol to 5-digit format
        
        Args:
            symbol: HK stock code like '0700.HK' or '00700.HK'
            
        Returns:
            Formatted symbol like '00700.HK'
        """
        if not symbol.endswith('.HK'):
            return symbol
        
        # Split code and suffix
        code, suffix = symbol.split('.')
        
        # Pad with zeros to 5 digits
        code = code.zfill(5)
        
        formatted = f"{code}.{suffix}"
        if formatted != symbol:
            logger.info(f"📝 HK symbol formatting: {symbol} -> {formatted}")
        
        return formatted
    
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
            logger.info(f"📝 Index symbol mapping: {symbol} -> {mappedSymbol}")
        
        return mappedSymbol
    
    def _getIntraDayData(self, symbol, startDate, endDate, freq):
        """Get intraday data (implementation depends on subscription level)"""
        # Note: Intraday data requires Tushare Pro subscription
        # This is a placeholder implementation
        logger.warning("Intraday data requires Tushare Pro subscription")
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
            logger.error(f"getting stock info for {symbol}: {e}")
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
            logger.error(f"searching stocks: {e}")
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
    
    def getFundData(self, symbol, startDate, endDate, freq='D'):
        """
        Get fund/ETF daily data from Tushare using fund_daily API
        
        Args:
            symbol (str): Fund/ETF symbol (e.g., '510330.SH', '518880.SH')
            startDate (str): Start date in YYYYMMDD format
            endDate (str): End date in YYYYMMDD format
            freq (str): Data frequency ('D' for daily)
            
        Returns:
            pd.DataFrame: Fund data with OHLCV columns
        """
        try:
            # Cache file path (include adj version so pre-fix caches are not reused)
            from quant.data.etf_adjust import ETF_ADJ_CACHE_VERSION, apply_fund_adj_factors

            dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare')
            cacheFile = os.path.join(
                dataPath,
                f"fund_{symbol}_{startDate}_{endDate}_{freq}_{ETF_ADJ_CACHE_VERSION}.csv",
            )
            
            # Check if cached data exists and is valid
            cacheEnabled = self.config.get('cacheEnabled', True)
            cacheExpiry = self.config.get('cacheExpiry', 3600)
            
            if cacheEnabled and os.path.exists(cacheFile):
                fileTime = os.path.getmtime(cacheFile)
                if time.time() - fileTime < cacheExpiry:
                    logger.info(f"Loading cached fund data for {symbol}")
                    return pd.read_csv(cacheFile, index_col=0, parse_dates=True)
            
            logger.info(f"Fetching fund data for {symbol} from {startDate} to {endDate}")
            
            if freq == 'D':
                # 优先使用fund_daily接口获取ETF日线行情数据
                try:
                    logger.info(f"🔄 Trying fund_daily API for ETF {symbol}")
                    df = self._fetch_with_backward_paging(
                        lambda s, e: self.pro.fund_daily(
                            ts_code=symbol,
                            start_date=s,
                            end_date=e,
                            fields='ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
                        ),
                        startDate,
                        endDate,
                        paging_threshold=int(self.config.get('pagingThreshold', 1800)),
                        max_pages=int(self.config.get('pagingMaxPages', 50)),
                        sleep_seconds=float(self.config.get('pagingSleepSeconds', 0.0)),
                    )
                    
                    if not df.empty:
                        logger.info(f"✅ Successfully fetched {len(df)} records from fund_daily for {symbol}")
                    else:
                        logger.info(f"⚠️  fund_daily returned empty data for {symbol}, trying alternatives")
                        raise ValueError("fund_daily returned no data")
                    
                except Exception as fund_daily_e:
                    logger.info(f"❌ fund_daily failed for {symbol}: {fund_daily_e}")
                    
                    # 回退到fund_nav接口
                    try:
                        logger.info(f"🔄 Trying fund_nav API as fallback for {symbol}")
                        nav_df = self.pro.fund_nav(
                            ts_code=symbol,
                            start_date=startDate,
                            end_date=endDate
                        )
                        
                        if not nav_df.empty:
                            logger.info(f"✅ Successfully fetched {len(nav_df)} NAV records for {symbol}")
                            # Convert NAV data to OHLCV format
                            df = self._convertNavToOHLCV(nav_df)
                        else:
                            raise ValueError(f"No fund data found from any API for symbol {symbol}")
                    except Exception as nav_e:
                        logger.info(f"❌ fund_nav also failed for {symbol}: {nav_e}")
                        raise ValueError(f"All fund data APIs failed for symbol {symbol}")
            else:
                logger.warning("Intraday fund data not supported")
                return pd.DataFrame()
            
            if df.empty:
                raise ValueError(f"No fund data found for symbol {symbol}")

            # Apply Tushare fund_adj (前复权) so historical NAV reflects share splits.
            # fund_daily returns unadjusted prices; without this step, ETFs that
            # split (e.g. 512010 -73.92% on 2021-06-28) show fake single-day jumps.
            # See docs/incidents/2026-05-etf-split-data-anomaly.md.
            try:
                adj = self.pro.fund_adj(ts_code=symbol, start_date=startDate, end_date=endDate)
                df = apply_fund_adj_factors(df, adj, date_col='trade_date')
            except Exception as adj_e:
                logger.warning(f"fund_adj failed for {symbol}: {adj_e}; using unadjusted prices")

            # Process data (same as stock data)
            df = self._processFundData(df)
            
            # Save to cache
            if cacheEnabled:
                df.to_csv(cacheFile)
            
            return df
            
        except Exception as e:
            logger.error(f"fetching fund data for {symbol}: {e}")
            # 不要在这里直接抛出异常，让调用者处理回退逻辑
            raise
    
    def _convertNavToOHLCV(self, nav_df):
        """Convert fund NAV data to OHLCV format"""
        # Convert NAV data to OHLCV format using unit_nav as close price
        df = nav_df.copy()
        df['trade_date'] = df['nav_date']  # Use nav_date as trade_date
        df['open'] = df['unit_nav']        # NAV as open
        df['high'] = df['unit_nav']        # NAV as high
        df['low'] = df['unit_nav']         # NAV as low
        df['close'] = df['unit_nav']       # NAV as close
        df['vol'] = 0                      # No volume data for NAV
        df['amount'] = 0                   # No amount data for NAV
        
        # Keep only required columns
        required_cols = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount']
        return df[required_cols]
    
    def _processFundData(self, df):
        """Process raw fund data from Tushare"""
        # Same processing as stock data
        return self._processStockData(df)
    
    def isFundSymbol(self, symbol):
        """Check if symbol is a fund/ETF"""
        try:
            # Query fund basic info to check if it's a fund
            fund_info = self.pro.fund_basic(ts_code=symbol)
            return not fund_info.empty
        except:
            return False
    
    def getFinancialData(self, symbol, start_date=None, end_date=None):
        """
        Get financial data including EPS, financial indicators, and basic metrics
        
        Args:
            symbol (str): Stock symbol
            start_date (str): Start date in YYYYMMDD format (optional)
            end_date (str): End date in YYYYMMDD format (optional)
            
        Returns:
            dict: Financial data including EPS, ratios, and other indicators
        """
        try:
            # Cache file path - 使用新的目录结构
            dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare', 'stocks')
            cache_key = f"financial_{symbol}_{start_date or 'latest'}_{end_date or 'latest'}"
            cacheFile = os.path.join(dataPath, f"{cache_key}.csv")
            
            # Check cache
            cacheEnabled = self.config.get('cacheEnabled', True)
            cacheExpiry = self.config.get('cacheExpiry', 86400)  # 24小时缓存
            
            if cacheEnabled and os.path.exists(cacheFile):
                fileTime = os.path.getmtime(cacheFile)
                if time.time() - fileTime < cacheExpiry:
                    logger.info(f"Loading cached financial data for {symbol}")
                    cached_df = pd.read_csv(cacheFile)
                    return self._process_financial_data(cached_df)
            
            logger.info(f"Fetching financial data for {symbol}")
            
            # 获取基本财务指标 (包含EPS)
            financial_indicators = self.pro.fina_indicator(
                ts_code=symbol,
                start_date=start_date or '20200101',
                end_date=end_date or datetime.now().strftime('%Y%m%d')
            )
            
            # 获取每日基本面数据 (包含PE, PB等)
            daily_basic = self.pro.daily_basic(
                ts_code=symbol,
                start_date=start_date or (datetime.now() - timedelta(days=30)).strftime('%Y%m%d'),
                end_date=end_date or datetime.now().strftime('%Y%m%d')
            )
            
            # 获取利润表数据
            income_data = self.pro.income(
                ts_code=symbol,
                start_date=start_date or '20200101',
                end_date=end_date or datetime.now().strftime('%Y%m%d')
            )
            
            # 合并数据
            financial_data = {
                'indicators': financial_indicators,
                'daily_basic': daily_basic,
                'income': income_data
            }
            
            # 缓存原始数据
            if cacheEnabled and not financial_indicators.empty:
                combined_df = pd.DataFrame({
                    'type': ['indicators'] * len(financial_indicators) + 
                           ['daily_basic'] * len(daily_basic) + 
                           ['income'] * len(income_data),
                    'data': list(financial_indicators.to_dict('records')) + 
                           list(daily_basic.to_dict('records')) + 
                           list(income_data.to_dict('records'))
                })
                combined_df.to_csv(cacheFile, index=False)
            
            return self._process_financial_data_dict(financial_data)
            
        except Exception as e:
            logger.error(f"fetching financial data for {symbol}: {e}")
            return {}
    
    def _process_financial_data(self, cached_df):
        """Process cached financial data"""
        try:
            financial_data = {'indicators': pd.DataFrame(), 'daily_basic': pd.DataFrame(), 'income': pd.DataFrame()}
            
            for _, row in cached_df.iterrows():
                data_type = row['type']
                if data_type in financial_data:
                    financial_data[data_type] = pd.DataFrame([eval(row['data'])])
            
            return self._process_financial_data_dict(financial_data)
        except:
            return {}
    
    def _process_financial_data_dict(self, financial_data):
        """Process financial data dictionary into structured format with William O'Neil CANSLIM analysis"""
        try:
            indicators_df = financial_data.get('indicators', pd.DataFrame())
            daily_basic_df = financial_data.get('daily_basic', pd.DataFrame()) 
            income_df = financial_data.get('income', pd.DataFrame())
            
            result = {
                'eps_data': [],
                'pe_data': [],
                'pb_data': [],
                'revenue_data': [],
                'profit_data': [],
                'latest_eps': None,
                'latest_pe': None,
                'latest_pb': None,
                'quarterly_earnings': [],
                'annual_earnings': [],
                'canslim_analysis': {},
                'william_oneil_signals': {}
            }
            
            # 处理EPS数据 - 增强版本支持CANSLIM分析
            if not indicators_df.empty and 'eps' in indicators_df.columns:
                # 按日期排序确保数据时间序列正确
                eps_data = indicators_df[['end_date', 'eps']].dropna().sort_values('end_date', ascending=False)
                result['eps_data'] = eps_data.to_dict('records')
                
                if len(eps_data) > 0:
                    result['latest_eps'] = float(eps_data.iloc[0]['eps'])
                    
                    # 构建按时间排序的EPS数据（最新在前）
                    eps_values = eps_data['eps'].tolist()
                    eps_dates = eps_data['end_date'].tolist()
                    
                    result['quarterly_earnings'] = eps_values
                    result['eps_dates'] = eps_dates
                    
                    # 威廉·欧奈尔CANSLIM方法分析
                    canslim_result = self._analyze_william_oneil_canslim(eps_values, eps_dates)
                    result['canslim_analysis'] = canslim_result
                    
                    # 计算年度收益趋势
                    annual_analysis = self._calculate_annual_eps_trends(eps_values, eps_dates)
                    result['annual_earnings'] = annual_analysis['annual_eps']
                    result['annual_growth_trends'] = annual_analysis['growth_trends']
            
            # 处理PE/PB数据
            if not daily_basic_df.empty:
                if 'pe_ttm' in daily_basic_df.columns:
                    pe_data = daily_basic_df[['trade_date', 'pe_ttm']].dropna()
                    result['pe_data'] = pe_data.to_dict('records')
                    if len(pe_data) > 0:
                        result['latest_pe'] = float(pe_data.iloc[-1]['pe_ttm']) if pd.notna(pe_data.iloc[-1]['pe_ttm']) else None
                
                if 'pb' in daily_basic_df.columns:
                    pb_data = daily_basic_df[['trade_date', 'pb']].dropna()
                    result['pb_data'] = pb_data.to_dict('records')
                    if len(pb_data) > 0:
                        result['latest_pb'] = float(pb_data.iloc[-1]['pb']) if pd.notna(pb_data.iloc[-1]['pb']) else None
            
            # 处理收入和利润数据
            if not income_df.empty:
                if 'total_revenue' in income_df.columns:
                    revenue_data = income_df[['end_date', 'total_revenue']].dropna()
                    result['revenue_data'] = revenue_data.to_dict('records')
                
                if 'n_income_attr_p' in income_df.columns:
                    profit_data = income_df[['end_date', 'n_income_attr_p']].dropna()
                    result['profit_data'] = profit_data.to_dict('records')
            
            return result
            
        except Exception as e:
            logger.error(f"processing financial data: {e}")
            return {}
    
    def _analyze_william_oneil_canslim(self, eps_values, eps_dates):
        """威廉·欧奈尔CANSLIM方法的C和A分析"""
        try:
            analysis = {
                'current_earnings_score': 0,
                'annual_earnings_score': 0,
                'quarterly_growth_trend': [],
                'annual_growth_trend': [],
                'eps_acceleration': False,
                'earnings_quality': 'unknown',
                'oneil_rating': 0,
                'detailed_analysis': {}
            }
            
            if len(eps_values) < 4:
                analysis['detailed_analysis']['warning'] = '数据不足，至少需要4个季度的EPS数据'
                return analysis
            
            # C - Current Earnings (当前季度盈利)
            # 威廉·欧奈尔要求：最近季度EPS同比增长 >= 25%
            current_analysis = self._analyze_current_quarter_eps(eps_values, eps_dates)
            analysis['current_earnings_score'] = current_analysis['score']
            analysis['detailed_analysis']['current'] = current_analysis
            
            # A - Annual Earnings (年度盈利)
            # 威廉·欧奈尔要求：过去3年年度EPS增长率均 >= 25%
            annual_analysis = self._analyze_annual_eps_growth(eps_values, eps_dates)
            analysis['annual_earnings_score'] = annual_analysis['score']
            analysis['detailed_analysis']['annual'] = annual_analysis
            
            # EPS加速度分析
            acceleration_analysis = self._analyze_eps_acceleration(eps_values)
            analysis['eps_acceleration'] = acceleration_analysis['has_acceleration']
            analysis['detailed_analysis']['acceleration'] = acceleration_analysis
            
            # 盈利质量评估
            quality_analysis = self._assess_earnings_quality(eps_values)
            analysis['earnings_quality'] = quality_analysis['quality']
            analysis['detailed_analysis']['quality'] = quality_analysis
            
            # 威廉·欧奈尔综合评分 (0-100)
            oneil_score = self._calculate_oneil_score(analysis)
            analysis['oneil_rating'] = oneil_score
            
            return analysis
            
        except Exception as e:
            logger.error(f"in William O'Neil CANSLIM analysis: {e}")
            return {'error': str(e)}
    
    def _analyze_current_quarter_eps(self, eps_values, eps_dates):
        """分析当前季度EPS - 威廉·欧奈尔C标准"""
        try:
            if len(eps_values) < 4:
                return {'score': 0, 'reason': '数据不足'}
            
            # 最近季度 vs 去年同期
            current_q = eps_values[0]
            same_q_last_year = eps_values[4] if len(eps_values) >= 5 else eps_values[-1]
            
            if same_q_last_year <= 0:
                return {'score': 0, 'reason': '去年同期EPS为负或零'}
            
            yoy_growth = (current_q - same_q_last_year) / same_q_last_year
            
            # 威廉·欧奈尔评分标准
            if yoy_growth >= 0.50:  # 50%+ 增长
                score = 95
                rating = '超级增长'
            elif yoy_growth >= 0.40:  # 40%+ 增长
                score = 85
                rating = '强劲增长'
            elif yoy_growth >= 0.25:  # 25%+ 增长（O'Neil最低标准）
                score = 75
                rating = '优秀增长'
            elif yoy_growth >= 0.15:  # 15%+ 增长
                score = 60
                rating = '良好增长'
            elif yoy_growth >= 0.05:  # 5%+ 增长
                score = 40
                rating = '温和增长'
            elif yoy_growth >= 0:  # 正增长
                score = 20
                rating = '微弱增长'
            else:  # 负增长
                score = 0
                rating = '收入下降'
            
            return {
                'score': score,
                'yoy_growth': yoy_growth,
                'rating': rating,
                'current_eps': current_q,
                'same_quarter_last_year': same_q_last_year,
                'meets_oneil_standard': yoy_growth >= 0.25,
                'reason': f'当前季度EPS同比增长{yoy_growth:.1%}，{rating}'
            }
            
        except Exception as e:
            return {'score': 0, 'reason': f'分析失败: {str(e)}'}
    
    def _analyze_annual_eps_growth(self, eps_values, eps_dates):
        """分析年度EPS增长趋势 - 威廉·欧奈尔A标准"""
        try:
            if len(eps_values) < 12:  # 需要至少3年数据
                return {'score': 0, 'reason': '数据不足，需要至少3年EPS数据'}
            
            # 计算年度EPS（每年4个季度）
            annual_eps = []
            for i in range(0, min(len(eps_values), 16), 4):  # 最多4年
                if i + 3 < len(eps_values):
                    year_eps = sum(eps_values[i:i+4])
                    annual_eps.append(year_eps)
            
            if len(annual_eps) < 3:
                return {'score': 0, 'reason': '无法构建3年年度EPS数据'}
            
            # 计算年度增长率
            annual_growth_rates = []
            for i in range(1, len(annual_eps)):
                if annual_eps[i] > 0:
                    growth = (annual_eps[i-1] - annual_eps[i]) / annual_eps[i]
                    annual_growth_rates.append(growth)
            
            if len(annual_growth_rates) < 2:
                return {'score': 0, 'reason': '无法计算年度增长率'}
            
            # 威廉·欧奈尔标准：过去3年每年增长>=25%
            excellent_years = sum(1 for rate in annual_growth_rates if rate >= 0.25)
            good_years = sum(1 for rate in annual_growth_rates if rate >= 0.15)
            positive_years = sum(1 for rate in annual_growth_rates if rate > 0)
            
            # 评分逻辑
            if excellent_years >= 2:  # 至少2年达到25%+增长
                score = 90
                rating = '符合O\'Neil标准'
            elif excellent_years >= 1 and good_years >= 2:  # 1年25%+ + 2年15%+
                score = 75
                rating = '接近O\'Neil标准'
            elif good_years >= 2:  # 至少2年15%+增长
                score = 60
                rating = '良好增长趋势'
            elif positive_years >= 2:  # 至少2年正增长
                score = 40
                rating = '稳定增长'
            else:
                score = 20
                rating = '增长乏力'
            
            avg_growth = np.mean(annual_growth_rates)
            
            return {
                'score': score,
                'rating': rating,
                'annual_eps': annual_eps,
                'growth_rates': annual_growth_rates,
                'avg_annual_growth': avg_growth,
                'excellent_years': excellent_years,
                'meets_oneil_standard': excellent_years >= 2,
                'reason': f'过去{len(annual_growth_rates)}年平均增长{avg_growth:.1%}，{excellent_years}年达到25%+增长'
            }
            
        except Exception as e:
            return {'score': 0, 'reason': f'分析失败: {str(e)}'}
    
    def _analyze_eps_acceleration(self, eps_values):
        """分析EPS增长加速度"""
        try:
            if len(eps_values) < 8:  # 需要至少2年数据
                return {'has_acceleration': False, 'reason': '数据不足'}
            
            # 计算最近4个季度和前4个季度的同比增长率
            recent_growth_rates = []
            previous_growth_rates = []
            
            for i in range(4):
                if i + 4 < len(eps_values) and i + 8 < len(eps_values):
                    current = eps_values[i]
                    last_year = eps_values[i + 4]
                    prev_year = eps_values[i + 8]
                    
                    if last_year > 0 and prev_year > 0:
                        recent_rate = (current - last_year) / last_year
                        previous_rate = (last_year - prev_year) / prev_year
                        
                        recent_growth_rates.append(recent_rate)
                        previous_growth_rates.append(previous_rate)
            
            if len(recent_growth_rates) < 2:
                return {'has_acceleration': False, 'reason': '无法计算增长率'}
            
            recent_avg = np.mean(recent_growth_rates)
            previous_avg = np.mean(previous_growth_rates)
            
            # 判断是否有加速
            has_acceleration = recent_avg > previous_avg and recent_avg > 0.15
            acceleration_magnitude = recent_avg - previous_avg
            
            return {
                'has_acceleration': has_acceleration,
                'recent_avg_growth': recent_avg,
                'previous_avg_growth': previous_avg,
                'acceleration_magnitude': acceleration_magnitude,
                'reason': f'最近4季度平均增长{recent_avg:.1%} vs 前4季度{previous_avg:.1%}'
            }
            
        except Exception as e:
            return {'has_acceleration': False, 'reason': f'分析失败: {str(e)}'}
    
    def _assess_earnings_quality(self, eps_values):
        """评估盈利质量"""
        try:
            if len(eps_values) < 8:
                return {'quality': 'unknown', 'reason': '数据不足'}
            
            # 盈利稳定性 - 计算EPS波动性
            eps_array = np.array(eps_values[:8])  # 最近2年
            eps_std = np.std(eps_array)
            eps_mean = np.mean(eps_array)
            cv = eps_std / eps_mean if eps_mean > 0 else float('inf')
            
            # 盈利趋势性 - 计算上升趋势强度
            positive_quarters = sum(1 for i in range(len(eps_values)-1) if eps_values[i] > eps_values[i+1])
            trend_ratio = positive_quarters / min(len(eps_values)-1, 7)
            
            # 质量评分
            if cv < 0.2 and trend_ratio > 0.6:
                quality = 'excellent'
                score = 90
            elif cv < 0.3 and trend_ratio > 0.5:
                quality = 'good'
                score = 75
            elif cv < 0.5 and trend_ratio > 0.3:
                quality = 'fair'
                score = 50
            else:
                quality = 'poor'
                score = 25
            
            return {
                'quality': quality,
                'score': score,
                'coefficient_of_variation': cv,
                'trend_ratio': trend_ratio,
                'reason': f'盈利{quality}，变异系数{cv:.2f}，上升趋势比例{trend_ratio:.1%}'
            }
            
        except Exception as e:
            return {'quality': 'unknown', 'reason': f'评估失败: {str(e)}'}
    
    def _calculate_oneil_score(self, analysis):
        """计算威廉·欧奈尔综合评分"""
        try:
            score = 0
            
            # C - 当前季度盈利 (40%权重)
            current_score = analysis.get('current_earnings_score', 0)
            score += current_score * 0.4
            
            # A - 年度盈利 (30%权重)
            annual_score = analysis.get('annual_earnings_score', 0)
            score += annual_score * 0.3
            
            # 盈利加速度加分 (15%权重)
            if analysis.get('eps_acceleration', False):
                score += 85 * 0.15
            
            # 盈利质量 (15%权重)
            quality_info = analysis.get('detailed_analysis', {}).get('quality', {})
            quality_score = quality_info.get('score', 0)
            score += quality_score * 0.15
            
            return min(100, max(0, int(score)))
            
        except Exception as e:
            return 0
    
    def _calculate_annual_eps_trends(self, eps_values, eps_dates):
        """计算年度EPS趋势"""
        try:
            annual_eps = []
            growth_trends = []
            
            # 按年度分组计算EPS
            for i in range(0, len(eps_values), 4):
                if i + 3 < len(eps_values):
                    year_eps = sum(eps_values[i:i+4])
                    annual_eps.append(year_eps)
            
            # 计算年度增长趋势
            for i in range(1, len(annual_eps)):
                if annual_eps[i] > 0:
                    growth = (annual_eps[i-1] - annual_eps[i]) / annual_eps[i]
                    growth_trends.append(growth)
            
            return {
                'annual_eps': annual_eps,
                'growth_trends': growth_trends
            }
            
        except Exception as e:
            return {'annual_eps': [], 'growth_trends': []}
    
    def getEnhancedStockData(self, symbol, startDate, endDate, freq='D', include_financials=True):
        """
        Get enhanced stock data including technical indicators, volume, and optional financial data
        
        Args:
            symbol (str): Stock symbol
            startDate (str): Start date in YYYYMMDD format
            endDate (str): End date in YYYYMMDD format
            freq (str): Data frequency
            include_financials (bool): Whether to include financial data
            
        Returns:
            dict: Enhanced stock data with OHLCV, technical indicators, and financial data
        """
        try:
            # 获取基本股票数据
            stock_data = self.getStockData(symbol, startDate, endDate, freq)
            
            result = {
                'price_data': stock_data,
                'symbol': symbol,
                'data_date_range': f"{startDate} to {endDate}",
                'has_volume': 'volume' in stock_data.columns if not stock_data.empty else False,
                'has_amount': 'amount' in stock_data.columns if not stock_data.empty else False,
            }
            
            # 添加成交量统计
            if not stock_data.empty and 'volume' in stock_data.columns:
                result['volume_stats'] = {
                    'avg_volume': float(stock_data['volume'].mean()),
                    'max_volume': float(stock_data['volume'].max()),
                    'min_volume': float(stock_data['volume'].min()),
                    'recent_avg_volume': float(stock_data['volume'].tail(20).mean()),
                    'volume_trend': 'increasing' if stock_data['volume'].tail(10).mean() > stock_data['volume'].tail(30).mean() else 'decreasing'
                }
            
            # 添加财务数据
            if include_financials:
                financial_data = self.getFinancialData(symbol, startDate, endDate)
                result['financial_data'] = financial_data
            
            return result
            
        except Exception as e:
            logger.error(f"getting enhanced stock data for {symbol}: {e}")
            raise

    def getGlobalIndexData(self, symbol, startDate, endDate, freq='D'):
        """
        Get global index data from Tushare
        
        Args:
            symbol (str): Global index symbol (e.g., 'IXIC', 'SPX', 'DJI')
            startDate (str): Start date in YYYYMMDD format
            endDate (str): End date in YYYYMMDD format
            freq (str): Data frequency ('D' for daily)
            
        Returns:
            pd.DataFrame: Global index data with OHLCV columns
        """
        try:
            # Cache file path
            dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare')
            cacheFile = os.path.join(
                dataPath, 
                f"global_{symbol}_{startDate}_{endDate}_{freq}.csv"
            )
            
            # Check if cached data exists and is valid
            cacheEnabled = self.config.get('cacheEnabled', True)
            cacheExpiry = self.config.get('cacheExpiry', 3600)
            
            if cacheEnabled and os.path.exists(cacheFile):
                fileTime = os.path.getmtime(cacheFile)
                if time.time() - fileTime < cacheExpiry:
                    logger.info(f"Loading cached global index data for {symbol}")
                    return pd.read_csv(cacheFile, index_col=0, parse_dates=True)
            
            logger.info(f"Fetching global index data for {symbol} from {startDate} to {endDate}")
            
            # Use index_global API for global indices
            df = self._fetch_with_backward_paging(
                lambda s, e: self.pro.index_global(ts_code=symbol, start_date=s, end_date=e),
                startDate,
                endDate,
                paging_threshold=int(self.config.get('pagingThreshold', 3500)),
                max_pages=int(self.config.get('pagingMaxPages', 50)),
                sleep_seconds=float(self.config.get('pagingSleepSeconds', 0.0)),
            )
            
            if df.empty:
                logger.info(f"No global index data found for {symbol}")
                # Try common global index mappings
                mappedSymbol = self._mapGlobalIndexSymbol(symbol)
                if mappedSymbol != symbol:
                    logger.info(f"Trying mapped symbol: {mappedSymbol}")
                    df = self._fetch_with_backward_paging(
                        lambda s, e: self.pro.index_global(ts_code=mappedSymbol, start_date=s, end_date=e),
                        startDate,
                        endDate,
                        paging_threshold=int(self.config.get('pagingThreshold', 3500)),
                        max_pages=int(self.config.get('pagingMaxPages', 50)),
                        sleep_seconds=float(self.config.get('pagingSleepSeconds', 0.0)),
                    )
                
                if df.empty:
                    raise ValueError(f"No global index data found for symbol {symbol}")
            
            # Process data
            df = self._processGlobalIndexData(df)
            
            # Save to cache
            if cacheEnabled:
                df.to_csv(cacheFile)
            
            return df
            
        except Exception as e:
            logger.error(f"fetching global index data for {symbol}: {e}")
            raise
    
    def _mapGlobalIndexSymbol(self, symbol):
        """Map global index symbols to Tushare format"""
        # 更新全球指数映射，支持更多Tushare全球指数代码
        globalMapping = {
            # 美股主要指数
            '^IXIC': 'IXIC',     # 纳斯达克综合指数
            'NASDAQ': 'IXIC',    # 纳斯达克综合指数
            'IXIC': 'IXIC',      # 纳斯达克综合指数（直接映射）
            '^SPX': 'SPX',       # 标普500指数
            'SP500': 'SPX',      # 标普500指数
            'SPX': 'SPX',        # 标普500指数（直接映射）
            '^DJI': 'DJI',       # 道琼斯指数
            'DOW': 'DJI',        # 道琼斯指数
            'DJI': 'DJI',        # 道琼斯指数（直接映射）
            '^NDX': 'NDX',       # 纳斯达克100指数
            'NASDAQ100': 'NDX',  # 纳斯达克100指数
            'NDX': 'NDX',        # 纳斯达克100指数（直接映射）
            
            # 其他全球指数（根据Tushare支持情况）
            '^FTSE': 'UKX',      # 英国富时100
            'FTSE100': 'UKX',    # 英国富时100
            '^N225': 'NKY',      # 日经225
            'NIKKEI': 'NKY',     # 日经225
            '^HSI': 'HSI',       # 恒生指数
            'HANGSENG': 'HSI',   # 恒生指数
            '^GDAXI': 'DAX',     # 德国DAX指数
            'DAX': 'DAX',        # 德国DAX指数
            
            # 中国相关指数（通过富时中国系列）
            'XIN9': 'XIN9',      # 富时中国50指数
            'FTSE_CHINA_50': 'XIN9',  # 富时中国50指数
        }
        
        mappedSymbol = globalMapping.get(symbol, symbol)
        if mappedSymbol != symbol:
            logger.info(f"📝 Global index symbol mapping: {symbol} -> {mappedSymbol}")
        
        return mappedSymbol
    
    def _processGlobalIndexData(self, df):
        """Process raw global index data from Tushare"""
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
        
        # Only rename columns that exist
        existingColumns = {k: v for k, v in columnMapping.items() if k in df.columns}
        df = df.rename(columns=existingColumns)
        
        # Convert date to datetime
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
        elif 'trade_date' in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df = df.set_index('trade_date')
            df.index.name = 'date'
        
        # Sort by date
        df = df.sort_index()
        
        # Fill missing values
        df = df.fillna(method='ffill')
        
        # Calculate additional technical indicators
        if 'close' in df.columns:
            df['returns'] = df['close'].pct_change()
            df['logReturns'] = np.log(df['close'] / df['close'].shift(1))
            
            # Calculate moving averages
            df['ma5'] = df['close'].rolling(window=5).mean()
            df['ma20'] = df['close'].rolling(window=20).mean()
            df['ma60'] = df['close'].rolling(window=60).mean()
            
            # Calculate volatility
            df['volatility'] = df['returns'].rolling(window=20).std() * np.sqrt(252)
        
        return df
    
    def getMoneyFlow(self, symbol, start_date, end_date):
        """
        Get individual stock money flow data from Tushare

        Args:
            symbol (str): Stock symbol (e.g., '000001.SZ')
            start_date (str): Start date in YYYYMMDD format
            end_date (str): End date in YYYYMMDD format

        Returns:
            pd.DataFrame: Money flow data with columns for different order sizes
        """
        try:
            # Cache file path
            dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare')
            cacheFile = os.path.join(
                dataPath,
                f"moneyflow_{symbol}_{start_date}_{end_date}.csv"
            )

            # Check cache
            cacheEnabled = self.config.get('cacheEnabled', True)
            # 智能 TTL：历史数据7天，当日数据1小时
            cacheExpiry = self._get_cache_ttl(end_date)

            if cacheEnabled and os.path.exists(cacheFile):
                fileTime = os.path.getmtime(cacheFile)
                if time.time() - fileTime < cacheExpiry:
                    logger.info(f"Loading cached money flow data for {symbol}")
                    return pd.read_csv(cacheFile, index_col=0, parse_dates=True)

            logger.info(f"Fetching money flow data for {symbol} from {start_date} to {end_date}")

            # Get money flow data using moneyflow API
            df = self.pro.moneyflow(
                ts_code=symbol,
                start_date=start_date,
                end_date=end_date
            )

            if df.empty:
                logger.info(f"No money flow data found for symbol {symbol}")
                return pd.DataFrame()

            # Process money flow data
            df = self._processMoneyFlowData(df)

            # Save to cache
            if cacheEnabled:
                df.to_csv(cacheFile)

            return df

        except Exception as e:
            logger.error(f"fetching money flow data for {symbol}: {e}")
            # Return empty DataFrame if API fails (graceful degradation)
            return pd.DataFrame()

    def getHSGTFlow(self, start_date, end_date):
        """
        Get HSGT (Hong Kong-Shanghai-Shenzhen Stock Connect) capital flow data

        Args:
            start_date (str): Start date in YYYYMMDD format
            end_date (str): End date in YYYYMMDD format

        Returns:
            pd.DataFrame: HSGT flow data
        """
        try:
            # Cache file path
            dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare')
            cacheFile = os.path.join(
                dataPath,
                f"hsgt_flow_{start_date}_{end_date}.csv"
            )

            # Check cache
            cacheEnabled = self.config.get('cacheEnabled', True)
            cacheExpiry = self.config.get('cacheExpiry', 3600)

            if cacheEnabled and os.path.exists(cacheFile):
                fileTime = os.path.getmtime(cacheFile)
                if time.time() - fileTime < cacheExpiry:
                    logger.info("Loading cached HSGT flow data")
                    return pd.read_csv(cacheFile, index_col=0, parse_dates=True)

            logger.info(f"Fetching HSGT flow data from {start_date} to {end_date}")

            # Get HSGT flow data using moneyflow_hsgt API
            df = self.pro.moneyflow_hsgt(
                start_date=start_date,
                end_date=end_date
            )

            if df.empty:
                logger.info("No HSGT flow data found")
                return pd.DataFrame()

            # Process HSGT flow data
            df = self._processHSGTFlowData(df)

            # Save to cache
            if cacheEnabled:
                df.to_csv(cacheFile)

            return df

        except Exception as e:
            logger.error(f"fetching HSGT flow data: {e}")
            return pd.DataFrame()

    def getHSGTTop10(self, trade_date, market='SH'):
        """
        Get HSGT top 10 traded stocks for a specific date

        Args:
            trade_date (str): Trade date in YYYYMMDD format
            market (str): Market code ('SH' for Shanghai, 'SZ' for Shenzhen)

        Returns:
            pd.DataFrame: Top 10 traded stocks data
        """
        try:
            # Cache file path
            dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare')
            cacheFile = os.path.join(
                dataPath,
                f"hsgt_top10_{market}_{trade_date}.csv"
            )

            # Check cache
            cacheEnabled = self.config.get('cacheEnabled', True)
            cacheExpiry = self.config.get('cacheExpiry', 3600)

            if cacheEnabled and os.path.exists(cacheFile):
                fileTime = os.path.getmtime(cacheFile)
                if time.time() - fileTime < cacheExpiry:
                    logger.info(f"Loading cached HSGT top10 data for {market} on {trade_date}")
                    return pd.read_csv(cacheFile, index_col=0)

            logger.info(f"Fetching HSGT top10 data for {market} on {trade_date}")

            # Get HSGT top 10 data using hsgt_top10 API
            df = self.pro.hsgt_top10(
                trade_date=trade_date,
                market=market
            )

            if df.empty:
                logger.info(f"No HSGT top10 data found for {market} on {trade_date}")
                return pd.DataFrame()

            # Process top 10 data
            df = self._processHSGTTop10Data(df)

            # Save to cache
            if cacheEnabled:
                df.to_csv(cacheFile)

            return df

        except Exception as e:
            logger.error(f"fetching HSGT top10 data: {e}")
            return pd.DataFrame()

    def _processMoneyFlowData(self, df):
        """Process raw money flow data from Tushare"""
        # Rename columns to standard format
        columnMapping = {
            'trade_date': 'date',
            'buy_sm_vol': 'small_buy_vol',      # 小单买入量
            'buy_sm_amount': 'small_buy_amount', # 小单买入金额
            'sell_sm_vol': 'small_sell_vol',     # 小单卖出量
            'sell_sm_amount': 'small_sell_amount', # 小单卖出金额
            'buy_md_vol': 'mid_buy_vol',         # 中单买入量
            'buy_md_amount': 'mid_buy_amount',   # 中单买入金额
            'sell_md_vol': 'mid_sell_vol',       # 中单卖出量
            'sell_md_amount': 'mid_sell_amount', # 中单卖出金额
            'buy_lg_vol': 'large_buy_vol',       # 大单买入量
            'buy_lg_amount': 'large_buy_amount', # 大单买入金额
            'sell_lg_vol': 'large_sell_vol',     # 大单卖出量
            'sell_lg_amount': 'large_sell_amount', # 大单卖出金额
            'buy_elg_vol': 'xlarge_buy_vol',     # 特大单买入量
            'buy_elg_amount': 'xlarge_buy_amount', # 特大单买入金额
            'sell_elg_vol': 'xlarge_sell_vol',   # 特大单卖出量
            'sell_elg_amount': 'xlarge_sell_amount', # 特大单卖出金额
            'net_mf_vol': 'net_main_vol',        # 主力净流入量
            'net_mf_amount': 'net_main_amount'   # 主力净流入额
        }

        # Only rename columns that exist
        existingColumns = {k: v for k, v in columnMapping.items() if k in df.columns}
        df = df.rename(columns=existingColumns)

        # Convert date to datetime
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
        elif 'trade_date' in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df = df.set_index('trade_date')
            df.index.name = 'date'

        # Sort by date
        df = df.sort_index()

        # Calculate additional metrics
        if 'net_main_amount' in df.columns:
            # Calculate main force inflow ratio
            total_amount = df.get('xlarge_buy_amount', 0) + df.get('large_buy_amount', 0) + \
                          df.get('xlarge_sell_amount', 0) + df.get('large_sell_amount', 0)
            df['main_inflow_ratio'] = df['net_main_amount'] / total_amount.replace(0, np.nan)

        # Calculate net flows for different order sizes
        if 'small_buy_amount' in df.columns and 'small_sell_amount' in df.columns:
            df['small_net_amount'] = df['small_buy_amount'] - df['small_sell_amount']
        if 'mid_buy_amount' in df.columns and 'mid_sell_amount' in df.columns:
            df['mid_net_amount'] = df['mid_buy_amount'] - df['mid_sell_amount']
        if 'large_buy_amount' in df.columns and 'large_sell_amount' in df.columns:
            df['large_net_amount'] = df['large_buy_amount'] - df['large_sell_amount']
        if 'xlarge_buy_amount' in df.columns and 'xlarge_sell_amount' in df.columns:
            df['xlarge_net_amount'] = df['xlarge_buy_amount'] - df['xlarge_sell_amount']

        return df

    def _processHSGTFlowData(self, df):
        """Process raw HSGT flow data from Tushare"""
        # Convert date to datetime
        if 'trade_date' in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df = df.set_index('trade_date')
            df.index.name = 'date'

        # Sort by date
        df = df.sort_index()

        # Ensure money columns are numeric (Tushare/CSV may return strings)
        money_cols = [c for c in df.columns if c != 'trade_date']
        for col in money_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Calculate net flows if individual flows are available
        if 'hk2sh_buy' in df.columns and 'hk2sh_sell' in df.columns:
            df['hk2sh_net'] = df['hk2sh_buy'] - df['hk2sh_sell']
        if 'hk2sz_buy' in df.columns and 'hk2sz_sell' in df.columns:
            df['hk2sz_net'] = df['hk2sz_buy'] - df['hk2sz_sell']
        if 'sh2hk_buy' in df.columns and 'sh2hk_sell' in df.columns:
            df['sh2hk_net'] = df['sh2hk_buy'] - df['sh2hk_sell']
        if 'sz2hk_buy' in df.columns and 'sz2hk_sell' in df.columns:
            df['sz2hk_net'] = df['sz2hk_buy'] - df['sz2hk_sell']

        return df

    def _processHSGTTop10Data(self, df):
        """Process raw HSGT top 10 data from Tushare"""
        # Convert date to datetime if present
        if 'trade_date' in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date'])

        # Sort by rank if available
        if 'rank' in df.columns:
            df = df.sort_values('rank')

        return df

    def getSupportedMarkets(self) -> list:
        """Get supported markets for Tushare"""
        return ['CN', 'US', 'GLOBAL']  # China A-shares, US stocks, and global indices
    
    def getStockList(self, exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date,market'):
        """
        获取所有上市公司列表
        
        Args:
            exchange (str): 交易所代码，默认获取所有
            list_status (str): 上市状态，默认'L'表示上市
            fields (str): 获取字段
            
        Returns:
            pd.DataFrame: 股票基本信息
        """
        try:
            logger.info("Fetching stock list from Tushare...")
            data = self.pro.stock_basic(
                exchange=exchange,
                list_status=list_status,
                fields=fields
            )
            logger.info(f"Retrieved {len(data)} stocks")
            return data
        except Exception as e:
            logger.error(f"fetching stock list: {e}")
            raise

    def getFundBasic(self, market='E', status='L'):
        """
        Get fund basic information
        
        Args:
            market (str): Market, E for exchange traded funds
            status (str): Status, L for listed
            
        Returns:
            pd.DataFrame: Fund basic information
        """
        try:
            logger.info("Fetching fund basic information from Tushare...")
            data = self.pro.fund_basic(
                market=market,
                status=status
            )
            logger.info(f"Retrieved {len(data)} funds")
            return data
        except Exception as e:
            logger.error(f"fetching fund basic information: {e}")
            raise
    
    def getIncomeData(self, period, fields='ts_code,ann_date,f_ann_date,end_date,report_type,basic_eps,diluted_eps,total_revenue,revenue,n_income'):
        """
        获取指定报告期的利润表数据
        
        Args:
            period (str): 报告期 (YYYYMMDD格式)
            fields (str): 获取字段
            
        Returns:
            pd.DataFrame: 利润表数据
        """
        try:
            logger.info(f"Fetching income data for period {period}")
            df = self.pro.income_vip(period=period, fields=fields)
            if df is None or df.empty:
                logger.info(f"No income data found for period {period}")
                return pd.DataFrame()
            logger.info(f"Retrieved {len(df)} income records for period {period}")
            return df
        except Exception as e:
            logger.error(f"fetching income data for period {period}: {e}")
            raise
    
    def getPeriodFinancialData(self, period, fields='ts_code,ann_date,f_ann_date,end_date,report_type,basic_eps,diluted_eps,total_revenue,revenue,n_income'):
        """
        获取指定季度的财务数据（getIncomeData的别名，保持接口一致性）
        
        Args:
            period (str): 报告期 (YYYYMMDD格式)
            fields (str): 获取字段
            
        Returns:
            pd.DataFrame: 财务数据
        """
        return self.getIncomeData(period, fields)
    
    def getCompanyInfo(self, symbol):
        """
        获取公司基本信息（等同于getStockInfo，保持接口一致性）
        
        Args:
            symbol (str): 股票代码
            
        Returns:
            dict: 公司信息
        """
        return self.getStockInfo(symbol)

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
            
            logger.info(f"🔄 Extending date range for {symbol}: {extendedStartDate} - {extendedEndDate}")
            
            # Get data with extended range
            if freq == 'D':
                df = self.pro.daily(
                    ts_code=symbol,
                    start_date=extendedStartDate,
                    end_date=extendedEndDate
                )
                # ETFs/funds may only exist on fund_daily
                if df.empty and not str(symbol).endswith('.HK'):
                    try:
                        return self.getFundData(
                            symbol, extendedStartDate, extendedEndDate, freq
                        )
                    except Exception as fund_e:
                        logger.info(
                            f"Extended-range fund fallback failed for {symbol}: {fund_e}"
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
            
            logger.info(f"✅ Found closest trading day data for {symbol}: {closest_data.index[0].strftime('%Y-%m-%d')}")
            
            # Save to cache using original cache file name
            if cacheEnabled:
                closest_data.to_csv(cacheFile)
            
            return closest_data
            
        except Exception as e:
            logger.info(f"❌ Extended date range also failed for {symbol}: {e}")
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
            
            logger.info(f"🔄 Extending date range for index {indexSymbol}: {extendedStartDate} - {extendedEndDate}")
            
            # Get index data with extended range
            if freq == 'D':
                df = self.pro.index_daily(
                    ts_code=indexSymbol,
                    start_date=extendedStartDate,
                    end_date=extendedEndDate
                )
            else:
                logger.warning("Intraday index data requires Tushare Pro subscription")
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
            
            logger.info(f"✅ Found closest index trading day data for {indexSymbol}: {closest_data.index[0].strftime('%Y-%m-%d')}")
            
            # Save to cache using original cache file name
            if cacheEnabled:
                closest_data.to_csv(cacheFile)
            
            return closest_data
            
        except Exception as e:
            logger.info(f"❌ Extended date range also failed for index {indexSymbol}: {e}")
            raise 

    # ==================== 行业/板块资金流向接口 ====================
    
    def getIndustryMoneyFlowTHS(self, trade_date=None, start_date=None, end_date=None, ts_code=None):
        """
        获取同花顺行业资金流向数据
        
        Args:
            trade_date (str): 交易日期 (YYYYMMDD格式)，与start_date/end_date二选一
            start_date (str): 开始日期 (YYYYMMDD格式)
            end_date (str): 结束日期 (YYYYMMDD格式)
            ts_code (str): 行业代码，如 '881101.TI' (可选)
            
        Returns:
            pd.DataFrame: 行业资金流向数据，包含:
                - ts_code: 行业代码
                - trade_date: 交易日期
                - name: 行业名称
                - pct_change: 涨跌幅(%)
                - close: 收盘点位
                - net_amount: 净流入额(万元)
                - net_amount_rate: 净流入占比(%)
                - buy_elg_amount: 特大单买入额(万元)
                - buy_lg_amount: 大单买入额(万元)
                - buy_md_amount: 中单买入额(万元)
                - buy_sm_amount: 小单买入额(万元)
                - sell_elg_amount: 特大单卖出额(万元)
                - sell_lg_amount: 大单卖出额(万元)
                - sell_md_amount: 中单卖出额(万元)
                - sell_sm_amount: 小单卖出额(万元)
        """
        try:
            # Build cache key
            cache_key = f"ind_flow_ths_{trade_date or ''}_{start_date or ''}_{end_date or ''}_{ts_code or ''}"
            dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare')
            cacheFile = os.path.join(dataPath, f"{cache_key}.csv")
            
            # Check cache
            cacheEnabled = self.config.get('cacheEnabled', True)
            cacheExpiry = self.config.get('cacheExpiry', 3600)
            
            if cacheEnabled and os.path.exists(cacheFile):
                fileTime = os.path.getmtime(cacheFile)
                if time.time() - fileTime < cacheExpiry:
                    logger.info("Loading cached THS industry money flow data")
                    return pd.read_csv(cacheFile, index_col=0, parse_dates=['trade_date'])
            
            logger.info(f"📊 Fetching THS industry money flow data...")
            
            # Build API parameters
            params = {}
            if trade_date:
                params['trade_date'] = trade_date
            if start_date:
                params['start_date'] = start_date
            if end_date:
                params['end_date'] = end_date
            if ts_code:
                params['ts_code'] = ts_code
            
            df = self.pro.moneyflow_ind_ths(**params)
            
            if df.empty:
                logger.warning("No THS industry money flow data found")
                return pd.DataFrame()
            
            # Process data
            df = self._processIndustryMoneyFlowData(df)
            
            # Save to cache
            if cacheEnabled:
                df.to_csv(cacheFile)
            
            logger.info(f"✅ Retrieved {len(df)} THS industry money flow records")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching THS industry money flow: {str(e)}")
            return pd.DataFrame()
    
    def getIndustryMoneyFlowDC(self, trade_date=None, start_date=None, end_date=None, ts_code=None):
        """
        获取东方财富行业板块资金流向数据
        
        Args:
            trade_date (str): 交易日期 (YYYYMMDD格式)
            start_date (str): 开始日期 (YYYYMMDD格式)
            end_date (str): 结束日期 (YYYYMMDD格式)
            ts_code (str): 板块代码 (可选)
            
        Returns:
            pd.DataFrame: 行业板块资金流向数据
        """
        try:
            # Build cache key
            cache_key = f"ind_flow_dc_{trade_date or ''}_{start_date or ''}_{end_date or ''}_{ts_code or ''}"
            dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare')
            cacheFile = os.path.join(dataPath, f"{cache_key}.csv")
            
            # Check cache
            cacheEnabled = self.config.get('cacheEnabled', True)
            # 使用智能 TTL：历史数据7天，当日数据1小时
            cacheExpiry = self._get_cache_ttl(trade_date or start_date)
            
            if cacheEnabled and os.path.exists(cacheFile):
                fileTime = os.path.getmtime(cacheFile)
                if time.time() - fileTime < cacheExpiry:
                    logger.debug("Loading cached DC industry money flow data")
                    return pd.read_csv(cacheFile, index_col=0, parse_dates=['trade_date'])
            
            logger.info(f"📊 Fetching DC industry money flow data...")
            
            # Build API parameters
            params = {}
            if trade_date:
                params['trade_date'] = trade_date
            if start_date:
                params['start_date'] = start_date
            if end_date:
                params['end_date'] = end_date
            if ts_code:
                params['ts_code'] = ts_code
            
            df = self.pro.moneyflow_ind_dc(**params)
            
            if df.empty:
                logger.warning("No DC industry money flow data found")
                return pd.DataFrame()
            
            # Process data
            df = self._processIndustryMoneyFlowData(df)
            
            # Save to cache
            if cacheEnabled:
                df.to_csv(cacheFile)
            
            logger.info(f"✅ Retrieved {len(df)} DC industry money flow records")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching DC industry money flow: {str(e)}")
            return pd.DataFrame()
    
    def getMarketMoneyFlowSummary(self, trade_date):
        """
        获取市场资金流向汇总分析（机构 vs 散户）
        
        Args:
            trade_date (str): 交易日期 (YYYYMMDD格式)
            
        Returns:
            dict: 资金流向汇总分析，包含:
                - institutional_net_flow: 机构净流入（特大单+大单）
                - retail_net_flow: 散户净流入（中单+小单）
                - top_inflow_industries: 资金净流入TOP行业
                - top_outflow_industries: 资金净流出TOP行业
                - north_money_flow: 北向资金流向
                - market_sentiment: 市场情绪判断
        """
        try:
            result = {
                'trade_date': trade_date,
                'institutional_analysis': {},
                'retail_analysis': {},
                'industry_ranking': {},
                'north_money': {},
                'market_sentiment': {}
            }
            
            # 1. 获取行业资金流向
            # Use DC data as it contains detailed order size breakdown (institutional vs retail)
            industry_flow = self.getIndustryMoneyFlowDC(trade_date=trade_date)
            
            if not industry_flow.empty:
                # 计算机构净流入（特大单+大单）
                if 'buy_elg_amount' in industry_flow.columns:
                    industry_flow['institutional_buy'] = (
                        industry_flow.get('buy_elg_amount', 0) + 
                        industry_flow.get('buy_lg_amount', 0)
                    )
                    industry_flow['institutional_sell'] = (
                        industry_flow.get('sell_elg_amount', 0) + 
                        industry_flow.get('sell_lg_amount', 0)
                    )
                    industry_flow['institutional_net'] = (
                        industry_flow['institutional_buy'] - 
                        industry_flow['institutional_sell']
                    )
                    
                    # 计算散户净流入（中单+小单）
                    industry_flow['retail_buy'] = (
                        industry_flow.get('buy_md_amount', 0) + 
                        industry_flow.get('buy_sm_amount', 0)
                    )
                    industry_flow['retail_sell'] = (
                        industry_flow.get('sell_md_amount', 0) + 
                        industry_flow.get('sell_sm_amount', 0)
                    )
                    industry_flow['retail_net'] = (
                        industry_flow['retail_buy'] - 
                        industry_flow['retail_sell']
                    )
                
                # 创建用于计算总量的数据集（过滤掉重复的概念/地域，只保留行业）
                summary_df = industry_flow
                if 'content_type' in industry_flow.columns:
                    # 仅保留 '行业' 类型以避免重复计算
                    industry_only = industry_flow[industry_flow['content_type'] == '行业']
                    if not industry_only.empty:
                        summary_df = industry_only
                
                # 机构资金汇总 (总量使用去重数据，排名使用全量数据)
                result['institutional_analysis'] = {
                    'total_net_flow': float(summary_df['institutional_net'].sum()) if 'institutional_net' in summary_df.columns else 0,
                    'top_5_inflow': industry_flow.nlargest(5, 'institutional_net')[['name', 'institutional_net']].to_dict('records') if 'institutional_net' in industry_flow.columns else [],
                    'top_5_outflow': industry_flow.nsmallest(5, 'institutional_net')[['name', 'institutional_net']].to_dict('records') if 'institutional_net' in industry_flow.columns else []
                }
                
                # 散户资金汇总 (总量使用去重数据，排名使用全量数据)
                result['retail_analysis'] = {
                    'total_net_flow': float(summary_df['retail_net'].sum()) if 'retail_net' in summary_df.columns else 0,
                    'top_5_inflow': industry_flow.nlargest(5, 'retail_net')[['name', 'retail_net']].to_dict('records') if 'retail_net' in industry_flow.columns else [],
                    'top_5_outflow': industry_flow.nsmallest(5, 'retail_net')[['name', 'retail_net']].to_dict('records') if 'retail_net' in industry_flow.columns else []
                }
                
                # 净流入行业排名
                if 'net_amount' in industry_flow.columns:
                    result['industry_ranking'] = {
                        'top_10_inflow': industry_flow.nlargest(10, 'net_amount')[['name', 'net_amount', 'pct_change']].to_dict('records'),
                        'top_10_outflow': industry_flow.nsmallest(10, 'net_amount')[['name', 'net_amount', 'pct_change']].to_dict('records')
                    }
            
            # 2. 获取北向资金数据
            try:
                hsgt_flow = self.getHSGTFlow(trade_date, trade_date)
                if not hsgt_flow.empty:
                    result['north_money'] = {
                        'north_money_in': float(hsgt_flow['north_money'].sum()) if 'north_money' in hsgt_flow.columns else 0,
                        'south_money_in': float(hsgt_flow['south_money'].sum()) if 'south_money' in hsgt_flow.columns else 0,
                        'data': hsgt_flow.to_dict('records')[0] if len(hsgt_flow) > 0 else {}
                    }
            except Exception as e:
                logger.warning(f"Failed to get HSGT flow: {e}")
            
            # 3. 市场情绪判断
            inst_flow = result['institutional_analysis'].get('total_net_flow', 0)
            retail_flow = result['retail_analysis'].get('total_net_flow', 0)
            north_flow = result['north_money'].get('north_money_in', 0)
            
            if inst_flow > 0 and north_flow > 0:
                sentiment = 'bullish'
                reason = '机构和北向资金均净流入'
            elif inst_flow < 0 and north_flow < 0:
                sentiment = 'bearish'
                reason = '机构和北向资金均净流出'
            elif inst_flow > 0 and retail_flow < 0:
                sentiment = 'divergent_institutional_buying'
                reason = '机构买入，散户卖出，可能是底部信号'
            elif inst_flow < 0 and retail_flow > 0:
                sentiment = 'divergent_retail_buying'
                reason = '机构卖出，散户买入，需要警惕'
            else:
                sentiment = 'neutral'
                reason = '资金面信号不明确'
            
            result['market_sentiment'] = {
                'sentiment': sentiment,
                'reason': reason,
                'institutional_net': inst_flow,
                'retail_net': retail_flow,
                'north_money_net': north_flow
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating market money flow summary: {str(e)}")
            return {'error': str(e)}
    
    def _processIndustryMoneyFlowData(self, df):
        """处理行业资金流向数据"""
        # Rename column for consistency
        if 'industry' in df.columns:
            df = df.rename(columns={'industry': 'name'})

        # Convert date column
        if 'trade_date' in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        # Sort by date and net_amount
        if 'trade_date' in df.columns and 'net_amount' in df.columns:
            df = df.sort_values(['trade_date', 'net_amount'], ascending=[False, False])
        
        # Calculate additional metrics
        # DC 数据中，buy_elg_amount 等通常已经是净流入金额（如果 sell 字段不存在）
        if 'buy_elg_amount' in df.columns:
            if 'sell_elg_amount' in df.columns:
                df['xlarge_net'] = df['buy_elg_amount'] - df['sell_elg_amount']
            else:
                # 只有 buy 字段，说明该字段本身就是净额
                df['xlarge_net'] = df['buy_elg_amount']
                
        if 'buy_lg_amount' in df.columns:
            if 'sell_lg_amount' in df.columns:
                df['large_net'] = df['buy_lg_amount'] - df['sell_lg_amount']
            else:
                df['large_net'] = df['buy_lg_amount']
                
        if 'buy_md_amount' in df.columns:
            if 'sell_md_amount' in df.columns:
                df['mid_net'] = df['buy_md_amount'] - df['sell_md_amount']
            else:
                df['mid_net'] = df['buy_md_amount']
                
        if 'buy_sm_amount' in df.columns:
            if 'sell_sm_amount' in df.columns:
                df['small_net'] = df['buy_sm_amount'] - df['sell_sm_amount']
            else:
                df['small_net'] = df['buy_sm_amount']
        
        # Calculate institutional vs retail
        if 'xlarge_net' in df.columns or 'large_net' in df.columns:
            df['institutional_net'] = df.get('xlarge_net', 0) + df.get('large_net', 0)
        if 'mid_net' in df.columns or 'small_net' in df.columns:
            df['retail_net'] = df.get('mid_net', 0) + df.get('small_net', 0)
            
        # 如果存在 institutional_net 和 retail_net，重新计算真正的全市场净流入 (net_amount)
        # 因为 Tushare raw 中的 net_amount 往往只是主力净流入 (xlarge+large)
        if 'institutional_net' in df.columns and 'retail_net' in df.columns:
            df['net_amount'] = df['institutional_net'] + df['retail_net']
        
        return df
    
    def analyzeInstitutionalVsRetail(self, symbol, start_date, end_date):
        """
        分析个股的机构 vs 散户资金博弈
        
        Args:
            symbol (str): 股票代码
            start_date (str): 开始日期
            end_date (str): 结束日期
            
        Returns:
            dict: 机构散户资金博弈分析结果
        """
        try:
            # Get money flow data
            flow_data = self.getMoneyFlow(symbol, start_date, end_date)
            
            if flow_data.empty:
                return {'error': 'No money flow data available'}
            
            # Calculate institutional flow (大单 + 特大单)
            if 'xlarge_buy_amount' in flow_data.columns:
                flow_data['institutional_buy'] = (
                    flow_data.get('xlarge_buy_amount', 0) + 
                    flow_data.get('large_buy_amount', 0)
                )
                flow_data['institutional_sell'] = (
                    flow_data.get('xlarge_sell_amount', 0) + 
                    flow_data.get('large_sell_amount', 0)
                )
                flow_data['institutional_net'] = (
                    flow_data['institutional_buy'] - 
                    flow_data['institutional_sell']
                )
            
            # Calculate retail flow (小单 + 中单)
            if 'small_buy_amount' in flow_data.columns:
                flow_data['retail_buy'] = (
                    flow_data.get('small_buy_amount', 0) + 
                    flow_data.get('mid_buy_amount', 0)
                )
                flow_data['retail_sell'] = (
                    flow_data.get('small_sell_amount', 0) + 
                    flow_data.get('mid_sell_amount', 0)
                )
                flow_data['retail_net'] = (
                    flow_data['retail_buy'] - 
                    flow_data['retail_sell']
                )
            
            # Summary statistics
            result = {
                'symbol': symbol,
                'period': f'{start_date} to {end_date}',
                'total_days': len(flow_data),
                'institutional': {
                    'total_net_flow': float(flow_data['institutional_net'].sum()) if 'institutional_net' in flow_data.columns else 0,
                    'avg_daily_net': float(flow_data['institutional_net'].mean()) if 'institutional_net' in flow_data.columns else 0,
                    'net_inflow_days': int((flow_data['institutional_net'] > 0).sum()) if 'institutional_net' in flow_data.columns else 0,
                    'net_outflow_days': int((flow_data['institutional_net'] < 0).sum()) if 'institutional_net' in flow_data.columns else 0,
                },
                'retail': {
                    'total_net_flow': float(flow_data['retail_net'].sum()) if 'retail_net' in flow_data.columns else 0,
                    'avg_daily_net': float(flow_data['retail_net'].mean()) if 'retail_net' in flow_data.columns else 0,
                    'net_inflow_days': int((flow_data['retail_net'] > 0).sum()) if 'retail_net' in flow_data.columns else 0,
                    'net_outflow_days': int((flow_data['retail_net'] < 0).sum()) if 'retail_net' in flow_data.columns else 0,
                },
                'flow_data': flow_data
            }
            
            # Determine trend
            inst_trend = result['institutional']['total_net_flow']
            retail_trend = result['retail']['total_net_flow']
            
            if inst_trend > 0 and retail_trend < 0:
                result['trend'] = 'institutional_accumulation'
                result['interpretation'] = '机构吸筹中，散户在卖出，可能是积极信号'
            elif inst_trend < 0 and retail_trend > 0:
                result['trend'] = 'institutional_distribution'
                result['interpretation'] = '机构在派发，散户在接盘，需要警惕'
            elif inst_trend > 0 and retail_trend > 0:
                result['trend'] = 'broad_buying'
                result['interpretation'] = '市场整体看多，买入力量强劲'
            elif inst_trend < 0 and retail_trend < 0:
                result['trend'] = 'broad_selling'
                result['interpretation'] = '市场整体看空，卖出压力大'
            else:
                result['trend'] = 'neutral'
                result['interpretation'] = '资金面无明显方向'
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing institutional vs retail flow: {str(e)}")
            return {'error': str(e)}

    def get_stock_basic(self):
        """
        获取所有股票基础信息（代码、名称等）
        """
        try:
            # Cache path
            dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare')
            if not os.path.exists(dataPath):
                os.makedirs(dataPath)
            cache_path = os.path.join(dataPath, 'stock_basic.csv')
            
            # Check cache (valid for 30 days - 静态数据)
            if os.path.exists(cache_path):
                if time.time() - os.path.getmtime(cache_path) < CACHE_TTL['static']:
                    try:
                        return pd.read_csv(cache_path, dtype={'ts_code': str, 'symbol': str})
                    except Exception:
                        pass
            
            # Fetch from API
            fields = 'ts_code,symbol,name,area,industry,list_date'
            df = self.pro.stock_basic(exchange='', list_status='L', fields=fields)
            
            if not df.empty:
                df.to_csv(cache_path, index=False)
            return df
            
        except Exception as e:
            logger.error(f"Error fetching stock_basic: {e}")
            return pd.DataFrame()

    def get_hk_stock_basic(self):
        """
        获取港股基础信息（代码、名称等）
        港股代码格式: 00700.HK (腾讯)
        """
        try:
            # Cache path
            dataPath = self.config.get('dataPath') or os.path.join(Config.DATA_DIR, 'tushare')
            if not os.path.exists(dataPath):
                os.makedirs(dataPath)
            cache_path = os.path.join(dataPath, 'hk_stock_basic.csv')
            
            # Check cache (valid for 30 days - 静态数据)
            if os.path.exists(cache_path):
                if time.time() - os.path.getmtime(cache_path) < CACHE_TTL['static']:
                    try:
                        return pd.read_csv(cache_path, dtype={'ts_code': str, 'symbol': str})
                    except Exception:
                        pass
            
            # Fetch from API
            logger.info("Fetching Hong Kong stock basic info...")
            df = self.pro.hk_basic()  # 不传 list_status，之后过滤
            
            if not df.empty:
                # 只保留上市中的股票
                if 'list_status' in df.columns:
                    df = df[df['list_status'] == 'L']
                # 统一格式：确保 ts_code 是 XXXXX.HK 格式
                df.to_csv(cache_path, index=False)
                logger.info(f"Retrieved {len(df)} Hong Kong stocks")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching hk_basic: {e}")
            return pd.DataFrame()

