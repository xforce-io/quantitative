#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
技术指标计算模块 (Technical Indicators Module)

提供统一的技术指标计算功能，避免各分析器重复实现
Provides unified technical indicator calculations to avoid duplication across analyzers
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')


class TechnicalIndicators:
    """技术指标计算器"""
    
    @staticmethod
    def calculate_moving_averages(data: pd.DataFrame, price_col: str = 'close') -> pd.DataFrame:
        """
        计算移动平均线
        
        Args:
            data: 股价数据
            price_col: 价格列名
            
        Returns:
            带有MA指标的数据框
        """
        result = data.copy()
        
        # 简单移动平均线
        for period in [5, 10, 20, 50, 60, 100, 200]:
            if len(data) >= period:
                result[f'MA{period}'] = result[price_col].rolling(window=period).mean()
        
        # 指数移动平均线
        for period in [12, 26, 50, 200]:
            if len(data) >= period:
                result[f'EMA{period}'] = result[price_col].ewm(span=period, adjust=False).mean()
                
        return result
    
    @staticmethod
    def calculate_rsi(data: pd.DataFrame, price_col: str = 'close', period: int = 14) -> pd.Series:
        """
        计算RSI指标
        
        Args:
            data: 股价数据
            price_col: 价格列名
            period: 计算周期
            
        Returns:
            RSI数据序列
        """
        if len(data) < period + 1:
            return pd.Series(index=data.index, dtype=float)
            
        delta = data[price_col].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        # 避免除零
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def calculate_macd(data: pd.DataFrame, price_col: str = 'close', 
                      fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
        """
        计算MACD指标
        
        Args:
            data: 股价数据
            price_col: 价格列名
            fast: 快线周期
            slow: 慢线周期 
            signal: 信号线周期
            
        Returns:
            包含MACD、Signal、Histogram的字典
        """
        if len(data) < max(fast, slow, signal):
            empty_series = pd.Series(index=data.index, dtype=float)
            return {
                'MACD': empty_series,
                'MACD_Signal': empty_series,
                'MACD_Histogram': empty_series
            }
        
        ema_fast = data[price_col].ewm(span=fast, adjust=False).mean()
        ema_slow = data[price_col].ewm(span=slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'MACD': macd_line,
            'MACD_Signal': signal_line,
            'MACD_Histogram': histogram
        }
    
    @staticmethod
    def calculate_bollinger_bands(data: pd.DataFrame, price_col: str = 'close',
                                period: int = 20, std_dev: float = 2.0) -> Dict[str, pd.Series]:
        """
        计算布林带
        
        Args:
            data: 股价数据
            price_col: 价格列名
            period: 计算周期
            std_dev: 标准差倍数
            
        Returns:
            包含Upper、Middle、Lower的字典
        """
        if len(data) < period:
            empty_series = pd.Series(index=data.index, dtype=float)
            return {
                'BB_Upper': empty_series,
                'BB_Middle': empty_series,
                'BB_Lower': empty_series
            }
        
        middle = data[price_col].rolling(window=period).mean()
        std = data[price_col].rolling(window=period).std()
        
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return {
            'BB_Upper': upper,
            'BB_Middle': middle,
            'BB_Lower': lower
        }
    
    @staticmethod
    def calculate_volume_indicators(data: pd.DataFrame, volume_col: str = 'volume') -> Dict[str, pd.Series]:
        """
        计算成交量指标
        
        Args:
            data: 股价数据
            volume_col: 成交量列名
            
        Returns:
            成交量相关指标字典
        """
        if volume_col not in data.columns:
            empty_series = pd.Series(index=data.index, dtype=float)
            return {
                'Volume_MA': empty_series,
                'Volume_Ratio': empty_series
            }
        
        # 成交量移动平均
        volume_ma = data[volume_col].rolling(window=20).mean()
        
        # 成交量比率
        volume_ratio = data[volume_col] / volume_ma
        
        return {
            'Volume_MA': volume_ma,
            'Volume_Ratio': volume_ratio
        }
    
    @staticmethod
    def calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        计算平均真实波幅 (ATR)
        
        Args:
            data: OHLC数据
            period: 计算周期
            
        Returns:
            ATR数据序列
        """
        required_cols = ['high', 'low', 'close']
        if not all(col in data.columns for col in required_cols) or len(data) < period:
            return pd.Series(index=data.index, dtype=float)
        
        high_low = data['high'] - data['low']
        high_close = (data['high'] - data['close'].shift()).abs()
        low_close = (data['low'] - data['close'].shift()).abs()
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        
        return atr
    
    @staticmethod
    def calculate_donchian_channels(data: pd.DataFrame, period: int = 20) -> Dict[str, pd.Series]:
        """
        计算唐奇安通道
        
        Args:
            data: OHLC数据
            period: 计算周期
            
        Returns:
            包含High、Low的字典
        """
        required_cols = ['high', 'low']
        if not all(col in data.columns for col in required_cols) or len(data) < period:
            empty_series = pd.Series(index=data.index, dtype=float)
            return {
                'Donchian_High': empty_series,
                'Donchian_Low': empty_series
            }
        
        donchian_high = data['high'].rolling(window=period).max()
        donchian_low = data['low'].rolling(window=period).min()
        
        return {
            'Donchian_High': donchian_high,
            'Donchian_Low': donchian_low
        }
    
    @staticmethod
    def calculate_returns(data: pd.DataFrame, price_col: str = 'close') -> Dict[str, pd.Series]:
        """
        计算收益率相关指标
        
        Args:
            data: 股价数据
            price_col: 价格列名
            
        Returns:
            收益率相关指标字典
        """
        # 日收益率
        daily_returns = data[price_col].pct_change()
        
        # 累计收益率
        cumulative_returns = (1 + daily_returns).cumprod() - 1
        
        # 滚动波动率
        volatility_20d = daily_returns.rolling(window=20).std() * np.sqrt(252)
        
        return {
            'daily_return': daily_returns,
            'cumulative_return': cumulative_returns,
            'volatility_20d': volatility_20d
        }
    
    @staticmethod
    def calculate_drawdown(data: pd.DataFrame, price_col: str = 'close') -> Dict[str, pd.Series]:
        """
        计算回撤相关指标
        
        Args:
            data: 股价数据
            price_col: 价格列名
            
        Returns:
            回撤相关指标字典
        """
        # 滚动最高价
        peak = data[price_col].expanding().max()
        
        # 回撤
        drawdown = (data[price_col] - peak) / peak
        
        # 最大回撤
        max_drawdown = drawdown.expanding().min()
        
        return {
            'peak': peak,
            'drawdown': drawdown,
            'max_drawdown': max_drawdown
        }
    
    @classmethod
    def calculate_all_indicators(cls, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有技术指标
        
        Args:
            data: 股价数据（至少包含close列）
            
        Returns:
            包含所有指标的数据框
        """
        if data.empty or 'close' not in data.columns:
            return data.copy()
        
        result = data.copy()
        
        # 移动平均线
        result = cls.calculate_moving_averages(result)
        
        # RSI
        result['RSI'] = cls.calculate_rsi(result)
        
        # MACD
        macd_dict = cls.calculate_macd(result)
        for key, value in macd_dict.items():
            result[key] = value
        
        # 布林带
        bb_dict = cls.calculate_bollinger_bands(result)
        for key, value in bb_dict.items():
            result[key] = value
        
        # 成交量指标
        volume_dict = cls.calculate_volume_indicators(result)
        for key, value in volume_dict.items():
            result[key] = value
        
        # ATR
        result['ATR'] = cls.calculate_atr(result)
        if 'ATR' in result.columns and 'close' in result.columns:
            result['ATR_Ratio'] = result['ATR'] / result['close']
        
        # 唐奇安通道
        donchian_dict = cls.calculate_donchian_channels(result)
        for key, value in donchian_dict.items():
            result[key] = value
        
        # 收益率指标
        returns_dict = cls.calculate_returns(result)
        for key, value in returns_dict.items():
            result[key] = value
        
        # 回撤指标
        drawdown_dict = cls.calculate_drawdown(result)
        for key, value in drawdown_dict.items():
            result[key] = value
        
        return result


def add_technical_indicators(data: pd.DataFrame) -> pd.DataFrame:
    """
    便捷函数：为数据添加所有技术指标
    
    Args:
        data: 原始股价数据
        
    Returns:
        添加技术指标后的数据
    """
    return TechnicalIndicators.calculate_all_indicators(data)


# 为了向后兼容，提供单独的函数
def calculate_ma(data: pd.DataFrame, price_col: str = 'close', periods: list = None) -> pd.DataFrame:
    """计算移动平均线（向后兼容）"""
    if periods is None:
        periods = [5, 10, 20, 50]
        
    result = data.copy()
    for period in periods:
        if len(data) >= period:
            result[f'MA{period}'] = result[price_col].rolling(window=period).mean()
    return result


def calculate_rsi(data: pd.DataFrame, price_col: str = 'close', period: int = 14) -> pd.Series:
    """计算RSI（向后兼容）"""
    return TechnicalIndicators.calculate_rsi(data, price_col, period)


def calculate_macd(data: pd.DataFrame, price_col: str = 'close') -> Dict[str, pd.Series]:
    """计算MACD（向后兼容）"""
    return TechnicalIndicators.calculate_macd(data, price_col)


def calculate_bollinger_bands(data: pd.DataFrame, price_col: str = 'close') -> Dict[str, pd.Series]:
    """计算布林带（向后兼容）"""
    return TechnicalIndicators.calculate_bollinger_bands(data, price_col)
