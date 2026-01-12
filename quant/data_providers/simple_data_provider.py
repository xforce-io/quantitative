#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
简化的数据提供者 - 统一接口
Simplified Data Provider - Unified Interface
"""

import os
import json
import pickle
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from functools import lru_cache
import pandas as pd
import tushare as ts
import yfinance as yf
from datetime import datetime, timedelta

from quant.core.logging_config import get_logger
logger = get_logger(__name__)


class DataProvider:
    """统一的数据提供者，集成多个数据源和缓存功能"""

    def __init__(self, provider: str = 'auto', config: Optional[Dict] = None):
        """
        初始化数据提供者

        Args:
            provider: 数据源 ('tushare', 'yahoo', 'auto')
            config: 配置参数
        """
        self.config = config or {}
        self.cache_dir = Path(self.config.get('cache_dir', 'cache'))
        self.cache_enabled = self.config.get('cache_enabled', True)
        self.cache_ttl_hours = self.config.get('cache_ttl_hours', 24)

        # 创建缓存目录
        if self.cache_enabled:
            self.cache_dir.mkdir(exist_ok=True)

        # 初始化数据源
        self.provider = self._init_provider(provider)
        self.provider_name = provider if provider != 'auto' else self._detect_provider()

    def _init_provider(self, provider: str):
        """初始化数据提供者"""
        if provider == 'auto':
            # 自动选择可用的数据源
            return self._auto_select_provider()
        elif provider == 'tushare':
            return self._init_tushare()
        elif provider == 'yahoo':
            return self._init_yahoo()
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _auto_select_provider(self):
        """自动选择可用的数据提供者"""
        # 优先尝试 Tushare
        try:
            return self._init_tushare()
        except Exception as e:
            logger.info("Tushare initialization failed: {e}")

        # 回退到 Yahoo Finance
        try:
            return self._init_yahoo()
        except Exception as e:
            logger.info("Yahoo Finance initialization failed: {e}")

        raise RuntimeError("No data providers available")

    def _init_tushare(self):
        """初始化 Tushare"""
        token = os.getenv('TUSHARE_TOKEN') or self.config.get('tushare_token')
        if not token:
            raise ValueError("Tushare token not found")

        ts.set_token(token)
        return ts.pro_api()

    def _init_yahoo(self):
        """初始化 Yahoo Finance"""
        # Yahoo Finance 不需要特殊初始化
        return yf

    def _detect_provider(self):
        """检测当前使用的数据提供者"""
        if hasattr(self.provider, 'query'):
            return 'tushare'
        else:
            return 'yahoo'

    def _get_cache_key(self, method: str, *args, **kwargs) -> str:
        """生成缓存键"""
        key_data = f"{method}:{args}:{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{self.provider_name}_{cache_key}.pkl"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """检查缓存是否有效"""
        if not cache_path.exists():
            return False

        # 检查缓存时间
        cache_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
        expire_time = datetime.now() - timedelta(hours=self.cache_ttl_hours)

        return cache_time > expire_time

    def _load_cache(self, cache_path: Path):
        """加载缓存数据"""
        try:
            with open(cache_path, 'rb') as f:
                return pickle.load(f)
        except Exception:
            return None

    def _save_cache(self, cache_path: Path, data):
        """保存缓存数据"""
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.info("Failed to save cache: {e}")

    def _with_cache(self, func, *args, **kwargs):
        """带缓存的函数调用"""
        if not self.cache_enabled:
            return func(*args, **kwargs)

        # 生成缓存键
        cache_key = self._get_cache_key(func.__name__, *args, **kwargs)
        cache_path = self._get_cache_path(cache_key)

        # 检查缓存
        if self._is_cache_valid(cache_path):
            cached_data = self._load_cache(cache_path)
            if cached_data is not None:
                return cached_data

        # 获取新数据
        data = func(*args, **kwargs)

        # 保存缓存
        self._save_cache(cache_path, data)

        return data

    def get_stock_data(self, symbol: str, start_date: str, end_date: str, freq: str = 'D') -> pd.DataFrame:
        """
        获取股票数据

        Args:
            symbol: 股票代码
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            freq: 频率 ('D', 'W', 'M')

        Returns:
            pandas.DataFrame: 股票数据
        """
        return self._with_cache(self._fetch_stock_data, symbol, start_date, end_date, freq)

    def _fetch_stock_data(self, symbol: str, start_date: str, end_date: str, freq: str = 'D') -> pd.DataFrame:
        """内部获取股票数据方法"""
        if self.provider_name == 'tushare':
            return self._fetch_tushare_data(symbol, start_date, end_date, freq)
        elif self.provider_name == 'yahoo':
            return self._fetch_yahoo_data(symbol, start_date, end_date, freq)
        else:
            raise ValueError(f"Unknown provider: {self.provider_name}")

    def _fetch_tushare_data(self, symbol: str, start_date: str, end_date: str, freq: str) -> pd.DataFrame:
        """从 Tushare 获取数据"""
        # 转换股票代码格式
        ts_symbol = self._format_symbol_for_tushare(symbol)

        # 调用 Tushare API
        df = self.provider.daily(ts_code=ts_symbol, start_date=start_date, end_date=end_date)

        if df.empty:
            raise ValueError(f"No data found for {symbol}")

        # 标准化列名和格式
        df = df.rename(columns={
            'trade_date': 'date',
            'vol': 'volume',
            'amount': 'turnover'
        })

        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()

        # 确保必要的列存在
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                df[col] = 0.0

        return df[required_cols]

    def _fetch_yahoo_data(self, symbol: str, start_date: str, end_date: str, freq: str) -> pd.DataFrame:
        """从 Yahoo Finance 获取数据"""
        # 转换日期格式
        start = datetime.strptime(start_date, '%Y%m%d').strftime('%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y%m%d').strftime('%Y-%m-%d')

        # 转换股票代码格式
        yahoo_symbol = self._format_symbol_for_yahoo(symbol)

        # 获取数据
        ticker = self.provider.Ticker(yahoo_symbol)
        df = ticker.history(start=start, end=end)

        if df.empty:
            raise ValueError(f"No data found for {symbol}")

        # 标准化列名
        df = df.rename(columns={
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        })

        # 确保必要的列存在
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                df[col] = 0.0

        return df[required_cols]

    def _format_symbol_for_tushare(self, symbol: str) -> str:
        """格式化股票代码为 Tushare 格式"""
        if '.' in symbol:
            return symbol
        elif symbol.startswith('00') or symbol.startswith('30'):
            return f"{symbol}.SZ"
        elif symbol.startswith('60') or symbol.startswith('68'):
            return f"{symbol}.SH"
        else:
            return symbol

    def _format_symbol_for_yahoo(self, symbol: str) -> str:
        """格式化股票代码为 Yahoo Finance 格式"""
        if symbol.endswith('.SZ'):
            return symbol.replace('.SZ', '.SZ')
        elif symbol.endswith('.SH'):
            return symbol.replace('.SH', '.SS')
        else:
            return symbol

    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """获取股票基本信息"""
        return self._with_cache(self._fetch_stock_info, symbol)

    def _fetch_stock_info(self, symbol: str) -> Dict[str, Any]:
        """内部获取股票信息方法"""
        if self.provider_name == 'tushare':
            ts_symbol = self._format_symbol_for_tushare(symbol)
            df = self.provider.stock_basic(ts_code=ts_symbol)
            if not df.empty:
                return df.iloc[0].to_dict()
        elif self.provider_name == 'yahoo':
            yahoo_symbol = self._format_symbol_for_yahoo(symbol)
            ticker = self.provider.Ticker(yahoo_symbol)
            return ticker.info

        return {'symbol': symbol, 'name': 'Unknown'}

    def search_stock(self, keyword: str) -> pd.DataFrame:
        """搜索股票"""
        return self._with_cache(self._fetch_search_results, keyword)

    def _fetch_search_results(self, keyword: str) -> pd.DataFrame:
        """内部搜索股票方法"""
        if self.provider_name == 'tushare':
            df = self.provider.stock_basic()
            if not df.empty:
                mask = df['name'].str.contains(keyword, na=False) | df['ts_code'].str.contains(keyword, na=False)
                return df[mask]

        # Yahoo Finance 不支持搜索，返回空 DataFrame
        return pd.DataFrame()

    def get_provider_info(self) -> Dict[str, Any]:
        """获取数据提供者信息"""
        return {
            'name': self.provider_name,
            'cache_enabled': self.cache_enabled,
            'cache_dir': str(self.cache_dir),
            'cache_ttl_hours': self.cache_ttl_hours,
            'status': 'active'
        }

# 便捷函数
def create_data_provider(provider: str = 'auto', config: Optional[Dict] = None) -> DataProvider:
    """创建数据提供者实例"""
    return DataProvider(provider, config)