#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unified Data Provider Module

This module integrates data sources behind a unified interface.
"""

import os
import re
import pickle
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, Union
from datetime import datetime, timedelta, date

import pandas as pd
import numpy as np

# Import the unified exception hierarchy.
from ..core.exceptions import (
    DataError,
    DataNotFoundError,
    InvalidSymbolError,
    InvalidDateRangeError,
    ProviderError,
    ProviderNotAvailableError,
    ProviderAuthError,
    ProviderConnectionError,
    handle_provider_error,
    CacheReadError,
    CacheWriteError,
)

# Configure logging.
logger = logging.getLogger(__name__)

# Try importing optional data sources.
try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False
    logger.warning("Tushare not available. Install with: pip install tushare")

try:
    import yfinance as yf
    YAHOO_AVAILABLE = True
except ImportError:
    YAHOO_AVAILABLE = False
    logger.warning("Yahoo Finance not available. Install with: pip install yfinance")


class DataProvider:
    """Unified data provider."""

    # Symbol validation regex.
    SYMBOL_PATTERN = re.compile(r'^(\d{6})\.(SH|SZ|OF)$')

    # Supported frequencies.
    VALID_FREQUENCIES = {'D', 'W', 'M', '5', '15', '30', '60'}

    def __init__(self, provider: str = 'auto', config: Optional[Dict] = None):
        """
        Initialize data provider.

        Args:
            provider: Data source ('tushare', 'yahoo', 'auto')
            config: Configuration parameters

        Raises:
            ProviderNotAvailableError: No data provider is available
        """
        self.config = config or {}
        self.cache_dir = Path(self.config.get('cache_dir', 'cache'))
        self.cache_enabled = self.config.get('cache_enabled', True)
        self.cache_ttl_hours = self.config.get('cache_ttl_hours', 24)

        # Create cache directory.
        if self.cache_enabled:
            try:
                self.cache_dir.mkdir(exist_ok=True, parents=True)
            except Exception as e:
                logger.warning(f"Failed to create cache directory: {e}")
                self.cache_enabled = False

        # Initialize data source.
        self.provider_name = self._select_provider(provider)
        self.provider = self._init_provider(self.provider_name)

        logger.info(f"Data provider initialized: {self.provider_name}")

    def _select_provider(self, provider: str) -> str:
        """
        Select an available data provider.

        Args:
            provider: Provider name or 'auto'

        Returns:
            str: Selected provider name

        Raises:
            ProviderNotAvailableError: No provider is available
        """
        if provider == 'auto':
            # Auto-select Tushare first when a token exists, then Yahoo.
            if TUSHARE_AVAILABLE and os.getenv('TUSHARE_TOKEN'):
                return 'tushare'
            elif YAHOO_AVAILABLE:
                return 'yahoo'
            else:
                raise ProviderNotAvailableError(
                    'auto',
                    "No data providers available. Please install tushare or yfinance."
                )

        # Validate the requested provider.
        if provider == 'tushare':
            if not TUSHARE_AVAILABLE:
                raise ProviderNotAvailableError(
                    'tushare',
                    "Tushare not installed. Install with: pip install tushare"
                )
        elif provider == 'yahoo':
            if not YAHOO_AVAILABLE:
                raise ProviderNotAvailableError(
                    'yahoo',
                    "Yahoo Finance not installed. Install with: pip install yfinance"
                )
        else:
            raise ProviderError(provider, f"Unknown provider: {provider}")

        return provider

    def _init_provider(self, provider_name: str):
        """
        Initialize data provider.

        Args:
            provider_name: Provider name

        Returns:
            Initialized provider object

        Raises:
            ProviderAuthError: Authentication failed
        """
        if provider_name == 'tushare':
            token = os.getenv('TUSHARE_TOKEN') or self.config.get('tushare', {}).get('api_token')
            if not token:
                raise ProviderAuthError('tushare', 'TUSHARE_TOKEN')

            try:
                ts.set_token(token)
                return ts.pro_api()
            except Exception as e:
                raise ProviderAuthError('tushare', f"Failed to initialize: {str(e)}")

        elif provider_name == 'yahoo':
            return yf

        else:
            raise ProviderError(provider_name, f"Unknown provider: {provider_name}")

    def get_stock_data(
        self,
        symbol: str,
        start_date: Union[str, date],
        end_date: Union[str, date],
        freq: str = 'D'
    ) -> pd.DataFrame:
        """
        Get stock data through the unified interface.

        Args:
            symbol: Stock symbol, such as '000001.SZ' or '600036.SH'
            start_date: Start date, supports '20240101' or date objects
            end_date: End date
            freq: Data frequency, 'D' daily, 'W' weekly, 'M' monthly

        Returns:
            pd.DataFrame: Normalized stock data
                - index: date (datetime)
                - columns: [open, high, low, close, volume]

        Raises:
            InvalidSymbolError: Invalid stock symbol format
            InvalidDateRangeError: Invalid date range
            DataNotFoundError: Data was not found
            ProviderError: Provider failure
        """
        # Validate arguments.
        self._validate_symbol(symbol)
        start_str = self._normalize_date(start_date)
        end_str = self._normalize_date(end_date)
        self._validate_date_range(start_str, end_str)
        self._validate_frequency(freq)

        # Generate cache key.
        cache_key = f"{symbol}_{start_str}_{end_str}_{freq}"

        # Try reading from cache.
        if self.cache_enabled:
            cached_data = self._load_from_cache(cache_key)
            if cached_data is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_data

        # Fetch fresh data.
        try:
            logger.info(f"Fetching {symbol} from {self.provider_name}: {start_str} to {end_str}")

            if self.provider_name == 'tushare':
                data = self._fetch_tushare_data(symbol, start_str, end_str, freq)
            elif self.provider_name == 'yahoo':
                data = self._fetch_yahoo_data(symbol, start_str, end_str, freq)
            else:
                raise ProviderError(self.provider_name, "Provider not initialized")

            # Validate and normalize data.
            data = self._validate_and_normalize(data, symbol)

            # Save to cache.
            if self.cache_enabled and not data.empty:
                self._save_to_cache(cache_key, data)

            return data

        except (DataNotFoundError, InvalidSymbolError, InvalidDateRangeError):
            # Re-raise data exceptions directly.
            raise
        except ProviderError:
            # Re-raise provider exceptions directly.
            raise
        except Exception as e:
            # Convert other exceptions to standard provider errors.
            error = handle_provider_error(e, self.provider_name)
            logger.error(f"Failed to fetch {symbol}: {error}")
            raise error

    def _validate_symbol(self, symbol: str):
        """
        Validate stock symbol format.

        Args:
            symbol: Stock symbol

        Raises:
            InvalidSymbolError: Invalid symbol format
        """
        if not symbol or not isinstance(symbol, str):
            raise InvalidSymbolError(symbol, "Symbol must be a non-empty string")

        if not self.SYMBOL_PATTERN.match(symbol):
            raise InvalidSymbolError(
                symbol,
                "Expected format: XXXXXX.SH or XXXXXX.SZ (e.g., 000001.SZ, 600036.SH)"
            )

    def _normalize_date(self, d: Union[str, date]) -> str:
        """
        Normalize date format to YYYYMMDD.

        Args:
            d: Date string or date object

        Returns:
            str: Date string in YYYYMMDD format
        """
        if isinstance(d, date):
            return d.strftime('%Y%m%d')
        elif isinstance(d, str):
            # Remove all separators.
            clean = d.replace('-', '').replace('/', '').replace('.', '')
            # Validate format.
            if len(clean) == 8 and clean.isdigit():
                return clean
            raise ValueError(f"Invalid date format: {d}, expected YYYYMMDD")
        else:
            raise ValueError(f"Date must be string or date object, got {type(d)}")

    def _validate_date_range(self, start_date: str, end_date: str):
        """
        Validate date range.

        Args:
            start_date: Start date (YYYYMMDD)
            end_date: End date (YYYYMMDD)

        Raises:
            InvalidDateRangeError: Invalid date range
        """
        try:
            start = datetime.strptime(start_date, '%Y%m%d')
            end = datetime.strptime(end_date, '%Y%m%d')

            if start > end:
                raise InvalidDateRangeError(
                    start_date, end_date,
                    "Start date must be before end date"
                )

            # Check whether the range is too old or too far in the future.
            if start < datetime(2000, 1, 1):
                raise InvalidDateRangeError(
                    start_date, end_date,
                    "Start date before 2000-01-01 may not be supported"
                )

            if end > datetime.now() + timedelta(days=1):
                raise InvalidDateRangeError(
                    start_date, end_date,
                    "End date cannot be in the future"
                )

        except ValueError as e:
            if "does not match format" in str(e):
                raise InvalidDateRangeError(start_date, end_date, "Invalid date format")
            raise

    def _validate_frequency(self, freq: str):
        """Validate frequency argument."""
        if freq not in self.VALID_FREQUENCIES:
            raise ValueError(
                f"Invalid frequency: {freq}, valid options: {self.VALID_FREQUENCIES}"
            )

    def _fetch_with_backward_paging(
        self,
        fetch_fn,
        start_date: str,
        end_date: str,
        *,
        date_col: str = 'trade_date',
        paging_threshold: int = 1800,
        max_pages: int = 50,
        sleep_seconds: float = 0.0,
    ) -> pd.DataFrame:
        desired_start = datetime.strptime(start_date, '%Y%m%d')
        cur_end = datetime.strptime(end_date, '%Y%m%d')

        pages = []
        last_end = None

        for _ in range(max_pages):
            cur_end_str = cur_end.strftime('%Y%m%d')
            if cur_end_str == last_end:
                break
            last_end = cur_end_str

            df = fetch_fn(start_date, cur_end_str)
            if df is None or df.empty:
                break

            if date_col not in df.columns:
                return df

            pages.append(df)

            min_raw = df[date_col].min()
            try:
                min_dt = datetime.strptime(str(min_raw), '%Y%m%d')
            except Exception:
                try:
                    min_dt = pd.to_datetime(min_raw).to_pydatetime()
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

    def _fetch_tushare_data(self, symbol: str, start_date: str, end_date: str, freq: str) -> pd.DataFrame:
        """Fetch data from Tushare."""
        ts_symbol = symbol  # Already in the correct format.

        # Try stock data first.
        try:
            df = self._fetch_with_backward_paging(
                lambda s, e: self.provider.daily(ts_code=ts_symbol, start_date=s, end_date=e),
                start_date,
                end_date,
                paging_threshold=int(self.config.get('tushare_paging_threshold', 1800)),
                max_pages=int(self.config.get('tushare_paging_max_pages', 50)),
                sleep_seconds=float(self.config.get('tushare_paging_sleep_seconds', 0.0)),
            )
        except Exception as e:
            logger.debug(f"Failed to fetch as stock: {e}")
            df = pd.DataFrame()

        # If stock data is empty, try fund/ETF data.
        if df.empty:
            try:
                df = self._fetch_with_backward_paging(
                    lambda s, e: self.provider.fund_daily(ts_code=ts_symbol, start_date=s, end_date=e),
                    start_date,
                    end_date,
                    paging_threshold=int(self.config.get('tushare_paging_threshold', 1800)),
                    max_pages=int(self.config.get('tushare_paging_max_pages', 50)),
                    sleep_seconds=float(self.config.get('tushare_paging_sleep_seconds', 0.0)),
                )
                # Fund data may not include a volume column.
                if not df.empty and 'vol' not in df.columns:
                    df['vol'] = 0.0
            except Exception as e:
                logger.debug(f"Failed to fetch as fund: {e}")
                pass

        if df.empty:
            raise DataNotFoundError(symbol, f"{start_date} to {end_date}")

        # Normalize column names.
        df = df.rename(columns={
            'trade_date': 'date',
            'vol': 'volume',
            'amount': 'turnover'
        })

        return df

    def _fetch_yahoo_data(self, symbol: str, start_date: str, end_date: str, freq: str) -> pd.DataFrame:
        """Fetch data from Yahoo Finance."""
        # Convert date format.
        start = datetime.strptime(start_date, '%Y%m%d').strftime('%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y%m%d').strftime('%Y-%m-%d')

        # Convert symbol format.
        yahoo_symbol = symbol.replace('.SH', '.SS')  # Shanghai to Yahoo format.

        try:
            ticker = self.provider.Ticker(yahoo_symbol)
            df = ticker.history(start=start, end=end)
        except Exception as e:
            raise ProviderConnectionError('yahoo', e)

        if df.empty:
            raise DataNotFoundError(symbol, f"{start_date} to {end_date}")

        # Normalize column names.
        df = df.rename(columns={
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        })

        return df

    def _validate_and_normalize(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        Validate and normalize data format.

        Args:
            df: Raw data
            symbol: Stock symbol

        Returns:
            pd.DataFrame: Normalized data
        """
        if df.empty:
            raise DataNotFoundError(symbol, "Data is empty after fetch")

        # Ensure date index.
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')

        if not isinstance(df.index, pd.DatetimeIndex):
            raise DataError(f"Data index is not DatetimeIndex for {symbol}")

        # Sort by index.
        df = df.sort_index()

        # Ensure required columns exist.
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                logger.warning(f"Missing column '{col}' for {symbol}, filling with 0")
                df[col] = 0.0

        # Keep only required columns.
        df = df[required_cols]

        # Run data quality checks.
        self._check_data_quality(df, symbol)

        return df

    def _check_data_quality(self, df: pd.DataFrame, symbol: str):
        """
        Check data quality.

        Args:
            df: Data
            symbol: Stock symbol
        """
        # Check missing values.
        missing_count = df.isnull().sum().sum()
        if missing_count > 0:
            logger.warning(f"Data for {symbol} has {missing_count} missing values")

        # Check invalid prices.
        if (df[['open', 'high', 'low', 'close']] <= 0).any().any():
            logger.warning(f"Data for {symbol} contains zero or negative prices")

        # Check unusual volume.
        if df['volume'].max() > 1e12:  # Greater than one trillion.
            logger.warning(f"Data for {symbol} has unusually high volume")

    def _get_cache_path(self, cache_key: str) -> Path:
        """Return cache file path."""
        key_hash = hashlib.md5(cache_key.encode()).hexdigest()
        return self.cache_dir / f"{self.provider_name}_{key_hash}.pkl"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check whether cache is valid."""
        if not cache_path.exists():
            return False

        try:
            cache_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
            expire_time = datetime.now() - timedelta(hours=self.cache_ttl_hours)
            return cache_time > expire_time
        except Exception as e:
            logger.warning(f"Failed to check cache validity: {e}")
            return False

    def _load_from_cache(self, cache_key: str) -> Optional[pd.DataFrame]:
        """Load data from cache."""
        cache_path = self._get_cache_path(cache_key)

        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
                # Delete corrupted cache.
                try:
                    cache_path.unlink()
                except:
                    pass

        return None

    def _save_to_cache(self, cache_key: str, data: pd.DataFrame):
        """Save data to cache."""
        cache_path = self._get_cache_path(cache_key)
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
            logger.debug(f"Saved cache: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def get_provider_info(self) -> Dict[str, Any]:
        """
        Get provider information.

        Returns:
            dict: Provider information
        """
        return {
            'name': self.provider_name,
            'cache_enabled': self.cache_enabled,
            'cache_dir': str(self.cache_dir),
            'cache_ttl_hours': self.cache_ttl_hours,
            'status': 'active',
            'tushare_available': TUSHARE_AVAILABLE,
            'yahoo_available': YAHOO_AVAILABLE,
        }


def create_data_provider(provider: str = 'auto', config: Optional[Dict] = None) -> DataProvider:
    """
    Create a data provider instance.

    Args:
        provider: Provider name ('tushare', 'yahoo', 'auto')
        config: Configuration dictionary

    Returns:
        DataProvider: Data provider instance

    Raises:
        ProviderNotAvailableError: No provider is available
        ProviderAuthError: Authentication failed
    """
    return DataProvider(provider, config)
