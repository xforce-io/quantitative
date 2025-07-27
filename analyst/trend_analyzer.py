#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
趋势分析工具
基于多个技术指标的综合趋势分析
Comprehensive trend analysis based on multiple technical indicators
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from analyst.stock_strategy_analyzer import StockStrategyAnalyzer
from quant.data_providers.data_provider_factory import DataProviderFactory

class TrendAnalyzer:
    """多技术指标趋势分析器"""
    
    def __init__(self, use_latest_data: bool = False):
        """
        初始化趋势分析器
        
        Args:
            use_latest_data: 是否强制获取最新数据（禁用缓存）
        """
        self.use_latest_data = use_latest_data
        
        if use_latest_data:
            # 强制使用Tushare并禁用缓存以确保获取最新数据
            self.dataProvider = DataProviderFactory.create('tushare', enableCache=False)
            self.analyzer = None
        else:
            # 使用默认的分析器（带缓存）
            self.analyzer = StockStrategyAnalyzer()
            self.dataProvider = None
            
        self.trend_data = None
    
    def analyze_trend(self, symbol: str, name: str = None, days: int = 250) -> Optional[Dict]:
        """分析单只股票的趋势"""
        if self.use_latest_data:
            return self._analyze_with_latest_data(symbol, name, days)
        else:
            return self._analyze_with_cached_data(symbol, name)
    
    def _analyze_with_latest_data(self, symbol: str, name: str = None, days: int = 250) -> Optional[Dict]:
        """使用最新数据分析趋势"""
        # 计算日期范围 - 获取最新数据
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 50)  # 多获取一些数据确保有足够的技术指标
        
        # 格式化日期
        start_date_str = start_date.strftime('%Y%m%d')
        end_date_str = end_date.strftime('%Y%m%d')
        
        print(f"🔄 正在从Tushare获取 {symbol} 的最新数据...")
        print(f"📅 数据期间: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
        
        try:
            # 直接获取最新数据
            latest_data = self.dataProvider.getStockData(symbol, start_date_str, end_date_str)
            
            if latest_data is None or latest_data.empty:
                print(f"❌ 无法获取 {symbol} 的最新数据")
                return None
            
            # 计算基础和扩展技术指标
            latest_data = self._calculate_all_indicators(latest_data)
            
            print(f"✅ 成功获取最新数据，共 {len(latest_data)} 个交易日")
            print(f"📊 最新交易日: {latest_data.index[-1].strftime('%Y-%m-%d')}")
            print(f"💰 最新收盘价: ¥{latest_data['close'].iloc[-1]:.2f}")
            
            # 执行趋势分析
            return self._analyze_trend_with_data(latest_data, symbol, name)
            
        except Exception as e:
            print(f"❌ 分析失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _analyze_with_cached_data(self, symbol: str, name: str = None) -> Optional[Dict]:
        """使用缓存数据分析趋势"""
        # 使用基础分析器加载数据
        self.analyzer.loadStockData(symbol)
        
        if self.analyzer.stockData is None or self.analyzer.stockData.empty:
            print(f"❌ 无法获取 {symbol} 的数据")
            return None
        
        # 计算扩展技术指标
        self._calculate_extended_indicators()
        
        # 确定股票名称
        if name is None:
            name = symbol
        
        # 获取最新数据
        latest_date = self.analyzer.stockData.index[-1]
        latest_price = self.analyzer.stockData['close'].iloc[-1]
        
        # 显示分析结果
        print(f"\n🎯 {name} ({symbol}) 趋势分析:")
        print("=" * 80)
        print(f"📅 数据日期: {latest_date.strftime('%Y-%m-%d')}")
        print(f"💰 最新价格: ¥{latest_price:.2f}")
        
        # 分析各项指标
        ma_signal = self._analyze_moving_averages()
        rsi_signal = self._analyze_rsi()
        momentum_signal = self._analyze_momentum()
        breakout_signal = self._analyze_breakout()
        
        # 综合趋势判断
        overall_trend = self._synthesize_trend_signals(ma_signal, rsi_signal, momentum_signal, breakout_signal)
        
        # 交易建议
        self._show_trading_recommendations(overall_trend)
        
        return {
            'symbol': symbol,
            'name': name,
            'date': latest_date,
            'price': latest_price,
            'ma_signal': ma_signal,
            'rsi_signal': rsi_signal,
            'momentum_signal': momentum_signal,
            'breakout_signal': breakout_signal,
            'overall_trend': overall_trend
        }
    
    def _calculate_all_indicators(self, data):
        """计算所有技术指标（用于最新数据）"""
        # 计算基础指标
        data = self._calculate_basic_indicators(data)
        
        # 计算扩展指标
        data = self._calculate_extended_indicators_for_data(data)
        
        return data
    
    def _calculate_basic_indicators(self, data):
        """计算基础技术指标"""
        # 计算移动平均线
        data['MA5'] = data['close'].rolling(window=5).mean()
        data['MA10'] = data['close'].rolling(window=10).mean()
        data['MA20'] = data['close'].rolling(window=20).mean()
        data['MA60'] = data['close'].rolling(window=60).mean()
        
        # 计算收益率
        data['daily_return'] = data['close'].pct_change()
        data['cumulative_return'] = (1 + data['daily_return']).cumprod() - 1
        
        # 计算波动率
        data['volatility_20d'] = data['daily_return'].rolling(window=20).std() * np.sqrt(252)
        
        # 计算最大回撤
        data['peak'] = data['close'].expanding().max()
        data['drawdown'] = (data['close'] - data['peak']) / data['peak']
        data['max_drawdown'] = data['drawdown'].expanding().min()
        
        # 计算RSI
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        data['RSI'] = 100 - (100 / (1 + rs))
        
        # 计算布林带
        data['BB_middle'] = data['close'].rolling(window=20).mean()
        bb_std = data['close'].rolling(window=20).std()
        data['BB_upper'] = data['BB_middle'] + (bb_std * 2)
        data['BB_lower'] = data['BB_middle'] - (bb_std * 2)
        
        # 计算成交量指标
        if 'volume' in data.columns:
            data['volume_ma'] = data['volume'].rolling(window=20).mean()
            data['volume_ratio'] = data['volume'] / data['volume_ma']
        
        return data
    
    def _calculate_extended_indicators_for_data(self, data):
        """为新数据计算扩展技术指标"""
        # 指数移动平均线 (EMA)
        data['EMA12'] = data['close'].ewm(span=12, adjust=False).mean()
        data['EMA26'] = data['close'].ewm(span=26, adjust=False).mean()
        data['EMA50'] = data['close'].ewm(span=50, adjust=False).mean()
        data['EMA200'] = data['close'].ewm(span=200, adjust=False).mean()
        
        # MACD 指标
        data['MACD'] = data['EMA12'] - data['EMA26']
        data['MACD_Signal'] = data['MACD'].ewm(span=9, adjust=False).mean()
        data['MACD_Histogram'] = data['MACD'] - data['MACD_Signal']
        
        # 动量指标 (Momentum)
        data['Momentum_10'] = data['close'] - data['close'].shift(10)
        data['Momentum_14'] = data['close'] - data['close'].shift(14)
        data['Momentum_ROC'] = (data['close'] / data['close'].shift(14) - 1) * 100
        
        # 突破点相关指标
        # Donchian Channel (20日)
        data['Donchian_High'] = data['high'].rolling(window=20).max()
        data['Donchian_Low'] = data['low'].rolling(window=20).min()
        data['Donchian_Mid'] = (data['Donchian_High'] + data['Donchian_Low']) / 2
        
        # ATR (平均真实区间)
        data['TR'] = np.maximum(
            data['high'] - data['low'],
            np.maximum(
                abs(data['high'] - data['close'].shift(1)),
                abs(data['low'] - data['close'].shift(1))
            )
        )
        data['ATR'] = data['TR'].rolling(window=14).mean()
        
        # 支撑阻力位
        data['Resistance'] = data['high'].rolling(window=20).max()
        data['Support'] = data['low'].rolling(window=20).min()
        
        return data
    
    def _calculate_extended_indicators(self):
        """计算扩展技术指标（原有方法，用于缓存数据模式）"""
        data = self.analyzer.stockData
        
        # 指数移动平均线 (EMA)
        data['EMA12'] = data['close'].ewm(span=12, adjust=False).mean()
        data['EMA26'] = data['close'].ewm(span=26, adjust=False).mean()
        data['EMA50'] = data['close'].ewm(span=50, adjust=False).mean()
        data['EMA200'] = data['close'].ewm(span=200, adjust=False).mean()
        
        # MACD 指标
        data['MACD'] = data['EMA12'] - data['EMA26']
        data['MACD_Signal'] = data['MACD'].ewm(span=9, adjust=False).mean()
        data['MACD_Histogram'] = data['MACD'] - data['MACD_Signal']
        
        # 动量指标 (Momentum)
        data['Momentum_10'] = data['close'] - data['close'].shift(10)
        data['Momentum_14'] = data['close'] - data['close'].shift(14)
        data['Momentum_ROC'] = (data['close'] / data['close'].shift(14) - 1) * 100
        
        # 突破点相关指标
        # Donchian Channel (20日)
        data['Donchian_High'] = data['high'].rolling(window=20).max()
        data['Donchian_Low'] = data['low'].rolling(window=20).min()
        data['Donchian_Mid'] = (data['Donchian_High'] + data['Donchian_Low']) / 2
        
        # ATR (平均真实区间)
        data['TR'] = np.maximum(
            data['high'] - data['low'],
            np.maximum(
                abs(data['high'] - data['close'].shift(1)),
                abs(data['low'] - data['close'].shift(1))
            )
        )
        data['ATR'] = data['TR'].rolling(window=14).mean()
        
        # 支撑阻力位
        data['Resistance'] = data['high'].rolling(window=20).max()
        data['Support'] = data['low'].rolling(window=20).min()
        
        self.trend_data = data
    
    def _analyze_moving_averages_for_data(self, data) -> Dict:
        """移动平均线分析（用于最新数据）"""
        print(f"\n📈 1. 移动平均线分析:")
        print("-" * 60)
        
        latest_price = data['close'].iloc[-1]
        
        # 获取最新MA值
        ma20 = data['MA20'].iloc[-1] if pd.notna(data['MA20'].iloc[-1]) else 0
        ma60 = data['MA60'].iloc[-1] if pd.notna(data['MA60'].iloc[-1]) else 0
        ema50 = data['EMA50'].iloc[-1] if pd.notna(data['EMA50'].iloc[-1]) else 0
        ema200 = data['EMA200'].iloc[-1] if pd.notna(data['EMA200'].iloc[-1]) else 0
        
        print(f"💰 当前价格: ¥{latest_price:.2f}")
        print(f"📊 MA20: ¥{ma20:.2f} | MA60: ¥{ma60:.2f}")
        print(f"📊 EMA50: ¥{ema50:.2f} | EMA200: ¥{ema200:.2f}")
        
        # MA排列分析
        values = [latest_price, ma20, ema50, ma60, ema200]
        if all(values[i] >= values[i+1] for i in range(len(values)-1)):
            arrangement = "多头排列"
        elif all(values[i] <= values[i+1] for i in range(len(values)-1)):
            arrangement = "空头排列"
        else:
            arrangement = "混乱排列"
        
        # 价格位置分析
        above_count = sum(1 for ma_value in [ma20, ema50, ema200] if ma_value > 0 and latest_price > ma_value)
        total_count = sum(1 for ma_value in [ma20, ema50, ema200] if ma_value > 0)
        
        if total_count > 0:
            above_ratio = above_count / total_count
            if above_ratio >= 0.67:
                position = "主要均线上方"
            elif above_ratio >= 0.33:
                position = "部分均线上方"
            else:
                position = "主要均线下方"
        else:
            position = "数据不足"
        
        print(f"🔍 MA排列: {arrangement}")
        print(f"🔍 价格位置: {position}")
        
        # 综合评分
        score = 0
        if arrangement == "多头排列":
            score += 40
        elif arrangement == "空头排列":
            score -= 40
        
        if "上方" in position:
            score += 20
        elif "下方" in position:
            score -= 20
        
        if score > 30:
            signal = "强烈上涨"
        elif score > 10:
            signal = "上涨"
        elif score > -10:
            signal = "震荡"
        elif score > -30:
            signal = "下跌"
        else:
            signal = "强烈下跌"
        
        print(f"🎯 MA综合信号: {signal} (评分: {score})")
        
        return {
            'signal': signal,
            'score': score,
            'arrangement': arrangement,
            'price_position': position
        }
    
    def _analyze_rsi_for_data(self, data) -> Dict:
        """RSI分析（用于最新数据）"""
        print(f"\n📊 2. RSI分析:")
        print("-" * 60)
        
        rsi_data = data['RSI'].dropna()
        
        if rsi_data.empty:
            print("❌ 无RSI数据")
            return {'signal': '数据不足', 'value': 0}
        
        latest_rsi = rsi_data.iloc[-1]
        print(f"📊 当前RSI: {latest_rsi:.1f}")
        
        # RSI信号判断
        if latest_rsi >= 70:
            signal = "超买"
        elif latest_rsi >= 50:
            signal = "强势"
        elif latest_rsi >= 30:
            signal = "中性"
        else:
            signal = "超卖"
        
        print(f"🎯 RSI信号: {signal}")
        
        return {
            'signal': signal,
            'value': latest_rsi
        }
    
    def _analyze_momentum_for_data(self, data) -> Dict:
        """动量分析（用于最新数据）"""
        print(f"\n🚀 3. 动量指标分析:")
        print("-" * 60)
        
        # 获取最新动量值
        momentum_14 = data['Momentum_14'].iloc[-1] if pd.notna(data['Momentum_14'].iloc[-1]) else 0
        momentum_roc = data['Momentum_ROC'].iloc[-1] if pd.notna(data['Momentum_ROC'].iloc[-1]) else 0
        macd = data['MACD'].iloc[-1] if pd.notna(data['MACD'].iloc[-1]) else 0
        macd_signal = data['MACD_Signal'].iloc[-1] if pd.notna(data['MACD_Signal'].iloc[-1]) else 0
        macd_histogram = data['MACD_Histogram'].iloc[-1] if pd.notna(data['MACD_Histogram'].iloc[-1]) else 0
        
        print(f"📊 14日动量: {momentum_14:.2f}")
        print(f"📊 ROC指标: {momentum_roc:.2f}%")
        print(f"📊 MACD: {macd:.3f}")
        print(f"📊 MACD柱状图: {macd_histogram:.3f}")
        
        # 动量评分
        score = 0
        
        if momentum_14 > 0:
            score += 25
        else:
            score -= 25
        
        if momentum_roc > 5:
            score += 25
        elif momentum_roc > 0:
            score += 10
        elif momentum_roc > -5:
            score -= 10
        else:
            score -= 25
        
        if macd > macd_signal and macd_histogram > 0:
            score += 30
        elif macd < macd_signal and macd_histogram < 0:
            score -= 30
        
        if score > 50:
            signal = "强烈加速上涨"
        elif score > 20:
            signal = "加速上涨"
        elif score > -20:
            signal = "动量震荡"
        elif score > -50:
            signal = "加速下跌"
        else:
            signal = "强烈加速下跌"
        
        print(f"🎯 动量信号: {signal} (评分: {score})")
        
        return {
            'signal': signal,
            'score': score,
            'momentum_14': momentum_14,
            'roc': momentum_roc,
            'macd': macd,
            'macd_histogram': macd_histogram
        }
    
    def _analyze_breakout_for_data(self, data) -> Dict:
        """突破点分析（用于最新数据）"""
        print(f"\n💥 4. 突破点分析:")
        print("-" * 60)
        
        latest_price = data['close'].iloc[-1]
        latest_high = data['high'].iloc[-1]
        latest_low = data['low'].iloc[-1]
        
        # 获取通道数据
        donchian_high = data['Donchian_High'].iloc[-1] if pd.notna(data['Donchian_High'].iloc[-1]) else 0
        donchian_low = data['Donchian_Low'].iloc[-1] if pd.notna(data['Donchian_Low'].iloc[-1]) else 0
        bb_upper = data['BB_upper'].iloc[-1] if pd.notna(data['BB_upper'].iloc[-1]) else 0
        bb_lower = data['BB_lower'].iloc[-1] if pd.notna(data['BB_lower'].iloc[-1]) else 0
        atr = data['ATR'].iloc[-1] if pd.notna(data['ATR'].iloc[-1]) else 0
        
        print(f"💰 当前价格: ¥{latest_price:.2f}")
        print(f"📊 Donchian通道: ¥{donchian_low:.2f} - ¥{donchian_high:.2f}")
        print(f"📊 布林带: ¥{bb_lower:.2f} - ¥{bb_upper:.2f}")
        print(f"📊 ATR波动率: ¥{atr:.2f}")
        
        # 突破分析
        breakout_signals = []
        score = 0
        
        if latest_high >= donchian_high * 0.999:
            breakout_signals.append("向上突破Donchian上轨")
            score += 40
        elif latest_low <= donchian_low * 1.001:
            breakout_signals.append("向下突破Donchian下轨")
            score -= 40
        
        if latest_price > bb_upper:
            breakout_signals.append("突破布林带上轨")
            score += 30
        elif latest_price < bb_lower:
            breakout_signals.append("跌破布林带下轨")
            score -= 30
        
        print(f"🔍 突破信号: {', '.join(breakout_signals) if breakout_signals else '无明显突破'}")
        
        if score > 40:
            signal = "强烈向上突破"
        elif score > 10:
            signal = "向上突破"
        elif score > -10:
            signal = "整理状态"
        elif score > -40:
            signal = "向下突破"
        else:
            signal = "强烈向下突破"
        
        print(f"🎯 突破信号: {signal} (评分: {score})")
        
        return {
            'signal': signal,
            'score': score,
            'breakout_signals': breakout_signals
        }
    
    def _analyze_moving_averages(self) -> Dict:
        """1. 移动平均线分析"""
        print(f"\n📈 1. 移动平均线分析:")
        print("-" * 60)
        
        data = self.analyzer.stockData
        latest_price = data['close'].iloc[-1]
        
        # 获取最新MA值
        ma20 = data['MA20'].iloc[-1] if pd.notna(data['MA20'].iloc[-1]) else 0
        ma60 = data['MA60'].iloc[-1] if pd.notna(data['MA60'].iloc[-1]) else 0
        ema50 = data['EMA50'].iloc[-1] if pd.notna(data['EMA50'].iloc[-1]) else 0
        ema200 = data['EMA200'].iloc[-1] if pd.notna(data['EMA200'].iloc[-1]) else 0
        
        # MA排列分析
        ma_arrangement = self._analyze_ma_arrangement(latest_price, ma20, ma60, ema50, ema200)
        
        # 金叉死叉分析
        cross_signals = self._analyze_ma_crosses()
        
        # 价格位置分析
        price_position = self._analyze_price_position(latest_price, ma20, ema50, ema200)
        
        print(f"💰 当前价格: ¥{latest_price:.2f}")
        print(f"📊 MA20: ¥{ma20:.2f} | MA60: ¥{ma60:.2f}")
        print(f"📊 EMA50: ¥{ema50:.2f} | EMA200: ¥{ema200:.2f}")
        print(f"🔍 MA排列: {ma_arrangement}")
        print(f"🔍 交叉信号: {cross_signals}")
        print(f"🔍 价格位置: {price_position}")
        
        # 综合MA信号
        ma_score = 0
        if ma_arrangement == "多头排列":
            ma_score += 40
        elif ma_arrangement == "空头排列":
            ma_score -= 40
        
        if "金叉" in cross_signals:
            ma_score += 30
        elif "死叉" in cross_signals:
            ma_score -= 30
            
        if "上方" in price_position:
            ma_score += 20
        elif "下方" in price_position:
            ma_score -= 20
        
        # 判断信号强度
        if ma_score > 60:
            signal = "强烈上涨"
        elif ma_score > 20:
            signal = "上涨"
        elif ma_score > -20:
            signal = "震荡"
        elif ma_score > -60:
            signal = "下跌"
        else:
            signal = "强烈下跌"
            
        print(f"🎯 MA综合信号: {signal} (评分: {ma_score})")
        
        return {
            'signal': signal,
            'score': ma_score,
            'arrangement': ma_arrangement,
            'crosses': cross_signals,
            'price_position': price_position
        }
    
    def _analyze_ma_arrangement(self, price: float, ma20: float, ma60: float, ema50: float, ema200: float) -> str:
        """分析均线排列"""
        values = [price, ma20, ema50, ma60, ema200]
        
        # 检查是否为多头排列 (从上到下：价格 > 短期MA > 长期MA)
        if all(values[i] >= values[i+1] for i in range(len(values)-1)):
            return "多头排列"
        # 检查是否为空头排列
        elif all(values[i] <= values[i+1] for i in range(len(values)-1)):
            return "空头排列"
        else:
            return "混乱排列"
    
    def _analyze_ma_crosses(self) -> str:
        """分析金叉死叉"""
        data = self.analyzer.stockData
        
        # 检查最近3天的交叉情况
        recent_data = data.tail(3)
        
        signals = []
        
        # EMA12和EMA26交叉 (MACD信号)
        if len(recent_data) >= 2:
            if (recent_data['EMA12'].iloc[-1] > recent_data['EMA26'].iloc[-1] and 
                recent_data['EMA12'].iloc[-2] <= recent_data['EMA26'].iloc[-2]):
                signals.append("MACD金叉")
            elif (recent_data['EMA12'].iloc[-1] < recent_data['EMA26'].iloc[-1] and 
                  recent_data['EMA12'].iloc[-2] >= recent_data['EMA26'].iloc[-2]):
                signals.append("MACD死叉")
        
        # MA20和MA60交叉
        if len(recent_data) >= 2:
            if (recent_data['MA20'].iloc[-1] > recent_data['MA60'].iloc[-1] and 
                recent_data['MA20'].iloc[-2] <= recent_data['MA60'].iloc[-2]):
                signals.append("MA金叉")
            elif (recent_data['MA20'].iloc[-1] < recent_data['MA60'].iloc[-1] and 
                  recent_data['MA20'].iloc[-2] >= recent_data['MA60'].iloc[-2]):
                signals.append("MA死叉")
        
        return ", ".join(signals) if signals else "无明显交叉"
    
    def _analyze_price_position(self, price: float, ma20: float, ema50: float, ema200: float) -> str:
        """分析价格相对位置"""
        above_count = 0
        total_count = 0
        
        for ma_value in [ma20, ema50, ema200]:
            if ma_value > 0:  # 确保MA值有效
                total_count += 1
                if price > ma_value:
                    above_count += 1
        
        if total_count == 0:
            return "数据不足"
        
        above_ratio = above_count / total_count
        
        if above_ratio >= 0.67:
            return "主要均线上方"
        elif above_ratio >= 0.33:
            return "部分均线上方"
        else:
            return "主要均线下方"
    
    def _analyze_rsi(self) -> Dict:
        """2. RSI分析"""
        print(f"\n📊 2. RSI分析:")
        print("-" * 60)
        
        data = self.analyzer.stockData
        rsi_data = data['RSI'].dropna()
        
        if rsi_data.empty:
            print("❌ 无RSI数据")
            return {'signal': '数据不足', 'value': 0, 'trend': '未知'}
        
        latest_rsi = rsi_data.iloc[-1]
        
        # RSI趋势分析
        if len(rsi_data) >= 5:
            rsi_trend = self._analyze_rsi_trend(rsi_data.tail(5))
        else:
            rsi_trend = "数据不足"
        
        # RSI背离分析
        divergence = self._analyze_rsi_divergence()
        
        print(f"📊 当前RSI: {latest_rsi:.1f}")
        print(f"📈 RSI趋势: {rsi_trend}")
        print(f"🔍 背离情况: {divergence}")
        
        # RSI信号判断
        if latest_rsi >= 70:
            if rsi_trend == "上升":
                signal = "强烈超买"
            else:
                signal = "超买"
        elif latest_rsi >= 50:
            signal = "强势"
        elif latest_rsi >= 30:
            signal = "中性"
        else:
            if rsi_trend == "下降":
                signal = "强烈超卖"
            else:
                signal = "超卖"
        
        print(f"🎯 RSI信号: {signal}")
        
        return {
            'signal': signal,
            'value': latest_rsi,
            'trend': rsi_trend,
            'divergence': divergence
        }
    
    def _analyze_rsi_trend(self, rsi_series: pd.Series) -> str:
        """分析RSI趋势"""
        if len(rsi_series) < 3:
            return "数据不足"
        
        # 计算线性回归斜率
        x = np.arange(len(rsi_series))
        slope = np.polyfit(x, rsi_series.values, 1)[0]
        
        if slope > 1:
            return "上升"
        elif slope < -1:
            return "下降"
        else:
            return "震荡"
    
    def _analyze_rsi_divergence(self) -> str:
        """分析RSI背离"""
        data = self.analyzer.stockData
        
        if len(data) < 20:
            return "数据不足"
        
        # 获取最近20天数据
        recent_data = data.tail(20)
        
        # 寻找价格和RSI的高点
        price_highs = recent_data['close'].rolling(window=5).max()
        rsi_highs = recent_data['RSI'].rolling(window=5).max()
        
        # 简化的背离检测
        latest_price_high = price_highs.iloc[-1]
        latest_rsi_high = rsi_highs.iloc[-1]
        
        if len(price_highs) >= 10:
            prev_price_high = price_highs.iloc[-10]
            prev_rsi_high = rsi_highs.iloc[-10]
            
            # 顶背离：价格创新高但RSI没有
            if (latest_price_high > prev_price_high and 
                latest_rsi_high < prev_rsi_high):
                return "顶背离"
            # 底背离：价格创新低但RSI没有
            elif (latest_price_high < prev_price_high and 
                  latest_rsi_high > prev_rsi_high):
                return "底背离"
        
        return "无明显背离"
    
    def _analyze_momentum(self) -> Dict:
        """3. 动量指标分析"""
        print(f"\n🚀 3. 动量指标分析:")
        print("-" * 60)
        
        data = self.analyzer.stockData
        
        # 获取最新动量值
        momentum_10 = data['Momentum_10'].iloc[-1] if pd.notna(data['Momentum_10'].iloc[-1]) else 0
        momentum_14 = data['Momentum_14'].iloc[-1] if pd.notna(data['Momentum_14'].iloc[-1]) else 0
        momentum_roc = data['Momentum_ROC'].iloc[-1] if pd.notna(data['Momentum_ROC'].iloc[-1]) else 0
        
        # MACD分析
        macd = data['MACD'].iloc[-1] if pd.notna(data['MACD'].iloc[-1]) else 0
        macd_signal = data['MACD_Signal'].iloc[-1] if pd.notna(data['MACD_Signal'].iloc[-1]) else 0
        macd_histogram = data['MACD_Histogram'].iloc[-1] if pd.notna(data['MACD_Histogram'].iloc[-1]) else 0
        
        print(f"📊 10日动量: {momentum_10:.2f}")
        print(f"📊 14日动量: {momentum_14:.2f}")
        print(f"📊 ROC指标: {momentum_roc:.2f}%")
        print(f"📊 MACD: {macd:.3f}")
        print(f"📊 MACD信号线: {macd_signal:.3f}")
        print(f"📊 MACD柱状图: {macd_histogram:.3f}")
        
        # 动量信号判断
        momentum_score = 0
        
        # 基于动量值
        if momentum_14 > 0:
            momentum_score += 25
        else:
            momentum_score -= 25
            
        # 基于ROC
        if momentum_roc > 5:
            momentum_score += 25
        elif momentum_roc > 0:
            momentum_score += 10
        elif momentum_roc > -5:
            momentum_score -= 10
        else:
            momentum_score -= 25
            
        # 基于MACD
        if macd > macd_signal and macd_histogram > 0:
            momentum_score += 30
        elif macd > macd_signal:
            momentum_score += 15
        elif macd < macd_signal and macd_histogram < 0:
            momentum_score -= 30
        else:
            momentum_score -= 15
        
        # 动量强度分析
        momentum_strength = self._analyze_momentum_strength()
        momentum_score += momentum_strength
        
        # 判断最终信号
        if momentum_score > 50:
            signal = "强烈加速上涨"
        elif momentum_score > 20:
            signal = "加速上涨"
        elif momentum_score > -20:
            signal = "动量震荡"
        elif momentum_score > -50:
            signal = "加速下跌"
        else:
            signal = "强烈加速下跌"
        
        print(f"🎯 动量信号: {signal} (评分: {momentum_score})")
        
        return {
            'signal': signal,
            'score': momentum_score,
            'momentum_10': momentum_10,
            'momentum_14': momentum_14,
            'roc': momentum_roc,
            'macd': macd,
            'macd_histogram': macd_histogram
        }
    
    def _analyze_momentum_strength(self) -> int:
        """分析动量强度"""
        data = self.analyzer.stockData
        
        if len(data) < 5:
            return 0
        
        # 分析最近5天的动量变化
        recent_momentum = data['Momentum_14'].tail(5)
        
        # 动量加速度 (动量的变化率)
        momentum_acceleration = recent_momentum.diff().iloc[-1]
        
        if momentum_acceleration > 1:
            return 20  # 动量加速
        elif momentum_acceleration > 0:
            return 10
        elif momentum_acceleration > -1:
            return -10
        else:
            return -20  # 动量减速
    
    def _analyze_breakout(self) -> Dict:
        """4. 突破点分析"""
        print(f"\n💥 4. 突破点分析:")
        print("-" * 60)
        
        data = self.analyzer.stockData
        latest_price = data['close'].iloc[-1]
        latest_high = data['high'].iloc[-1]
        latest_low = data['low'].iloc[-1]
        
        # Donchian Channel突破
        donchian_high = data['Donchian_High'].iloc[-1] if pd.notna(data['Donchian_High'].iloc[-1]) else 0
        donchian_low = data['Donchian_Low'].iloc[-1] if pd.notna(data['Donchian_Low'].iloc[-1]) else 0
        
        # 布林带突破
        bb_upper = data['BB_upper'].iloc[-1] if pd.notna(data['BB_upper'].iloc[-1]) else 0
        bb_lower = data['BB_lower'].iloc[-1] if pd.notna(data['BB_lower'].iloc[-1]) else 0
        
        # 支撑阻力位
        resistance = data['Resistance'].iloc[-1] if pd.notna(data['Resistance'].iloc[-1]) else 0
        support = data['Support'].iloc[-1] if pd.notna(data['Support'].iloc[-1]) else 0
        
        # ATR用于判断突破有效性
        atr = data['ATR'].iloc[-1] if pd.notna(data['ATR'].iloc[-1]) else 0
        
        print(f"💰 当前价格: ¥{latest_price:.2f}")
        print(f"📊 Donchian通道: ¥{donchian_low:.2f} - ¥{donchian_high:.2f}")
        print(f"📊 布林带: ¥{bb_lower:.2f} - ¥{bb_upper:.2f}")
        print(f"📊 支撑/阻力: ¥{support:.2f} / ¥{resistance:.2f}")
        print(f"📊 ATR波动率: ¥{atr:.2f}")
        
        # 突破分析
        breakout_signals = []
        breakout_score = 0
        
        # Donchian突破
        if latest_high >= donchian_high * 0.999:  # 允许小误差
            breakout_signals.append("向上突破Donchian上轨")
            breakout_score += 40
        elif latest_low <= donchian_low * 1.001:
            breakout_signals.append("向下突破Donchian下轨")
            breakout_score -= 40
        
        # 布林带突破
        if latest_price > bb_upper:
            breakout_signals.append("突破布林带上轨")
            breakout_score += 30
        elif latest_price < bb_lower:
            breakout_signals.append("跌破布林带下轨")
            breakout_score -= 30
        
        # 阻力支撑突破
        if latest_price > resistance * 1.005:  # 需要明显突破
            breakout_signals.append("突破阻力位")
            breakout_score += 25
        elif latest_price < support * 0.995:
            breakout_signals.append("跌破支撑位")
            breakout_score -= 25
        
        # 成交量确认 (如果有成交量数据)
        volume_confirmation = self._analyze_volume_confirmation()
        if volume_confirmation:
            breakout_score += 15
            breakout_signals.append("成交量放大确认")
        
        # 判断突破有效性
        breakout_validity = self._judge_breakout_validity(atr, latest_price)
        
        print(f"🔍 突破信号: {', '.join(breakout_signals) if breakout_signals else '无明显突破'}")
        print(f"🔍 突破有效性: {breakout_validity}")
        
        # 最终信号
        if breakout_score > 60:
            signal = "强烈向上突破"
        elif breakout_score > 20:
            signal = "向上突破"
        elif breakout_score > -20:
            signal = "整理状态"
        elif breakout_score > -60:
            signal = "向下突破"
        else:
            signal = "强烈向下突破"
        
        print(f"🎯 突破信号: {signal} (评分: {breakout_score})")
        
        return {
            'signal': signal,
            'score': breakout_score,
            'breakout_signals': breakout_signals,
            'validity': breakout_validity,
            'donchian_position': self._get_position_description(latest_price, donchian_low, donchian_high),
            'bb_position': self._get_position_description(latest_price, bb_lower, bb_upper)
        }
    
    def _analyze_volume_confirmation(self) -> bool:
        """分析成交量确认"""
        data = self.analyzer.stockData
        
        if 'volume' not in data.columns or 'volume_ma' not in data.columns:
            return False
        
        latest_volume = data['volume'].iloc[-1]
        avg_volume = data['volume_ma'].iloc[-1]
        
        # 成交量放大1.5倍以上认为是确认
        return latest_volume > avg_volume * 1.5
    
    def _judge_breakout_validity(self, atr: float, price: float) -> str:
        """判断突破有效性"""
        if atr == 0:
            return "无法判断"
        
        # 基于ATR的突破有效性判断
        atr_ratio = atr / price
        
        if atr_ratio > 0.03:
            return "高有效性"
        elif atr_ratio > 0.015:
            return "中等有效性"
        else:
            return "低有效性"
    
    def _get_position_description(self, price: float, lower: float, upper: float) -> str:
        """获取价格位置描述"""
        if lower == 0 or upper == 0:
            return "数据不足"
        
        position = (price - lower) / (upper - lower)
        
        if position > 0.8:
            return "接近上轨"
        elif position > 0.6:
            return "上方区域"
        elif position > 0.4:
            return "中性区域"
        elif position > 0.2:
            return "下方区域"
        else:
            return "接近下轨"
    
    def _synthesize_trend_signals(self, ma_signal: Dict, rsi_signal: Dict, 
                                momentum_signal: Dict, breakout_signal: Dict) -> Dict:
        """综合趋势信号判断"""
        print(f"\n🎯 综合趋势判断:")
        print("=" * 80)
        
        # 计算综合评分
        total_score = 0
        signal_weights = {
            'ma': 0.3,      # 移动平均线权重30%
            'momentum': 0.3, # 动量指标权重30%
            'breakout': 0.25, # 突破分析权重25%
            'rsi': 0.15     # RSI权重15%
        }
        
        # 加权计算
        total_score += ma_signal['score'] * signal_weights['ma']
        total_score += momentum_signal['score'] * signal_weights['momentum']
        total_score += breakout_signal['score'] * signal_weights['breakout']
        
        # RSI信号转换为分数
        rsi_score = self._convert_rsi_to_score(rsi_signal['signal'])
        total_score += rsi_score * signal_weights['rsi']
        
        # 趋势强度判断
        if total_score > 60:
            trend_direction = "强烈上涨趋势"
            trend_strength = "强"
            confidence = "高"
        elif total_score > 30:
            trend_direction = "上涨趋势"
            trend_strength = "中"
            confidence = "中"
        elif total_score > -30:
            trend_direction = "震荡趋势"
            trend_strength = "弱"
            confidence = "低"
        elif total_score > -60:
            trend_direction = "下跌趋势"
            trend_strength = "中"
            confidence = "中"
        else:
            trend_direction = "强烈下跌趋势"
            trend_strength = "强"
            confidence = "高"
        
        # 时间框架建议
        time_frame = self._suggest_time_frame(trend_strength, total_score)
        
        print(f"📊 各指标信号汇总:")
        print(f"  • 移动平均线: {ma_signal['signal']}")
        print(f"  • RSI指标: {rsi_signal['signal']}")
        print(f"  • 动量指标: {momentum_signal['signal']}")
        print(f"  • 突破分析: {breakout_signal['signal']}")
        print(f"")
        print(f"🎯 综合评分: {total_score:.1f}")
        print(f"📈 趋势方向: {trend_direction}")
        print(f"💪 趋势强度: {trend_strength}")
        print(f"🔒 置信度: {confidence}")
        print(f"⏰ 建议时间框架: {time_frame}")
        
        return {
            'direction': trend_direction,
            'strength': trend_strength,
            'confidence': confidence,
            'score': total_score,
            'time_frame': time_frame,
            'component_signals': {
                'ma': ma_signal['signal'],
                'rsi': rsi_signal['signal'],
                'momentum': momentum_signal['signal'],
                'breakout': breakout_signal['signal']
            }
        }
    
    def _convert_rsi_to_score(self, rsi_signal: str) -> float:
        """将RSI信号转换为分数"""
        rsi_scores = {
            '强烈超买': -30,
            '超买': -20,
            '强势': 20,
            '中性': 0,
            '超卖': 20,
            '强烈超卖': 30
        }
        return rsi_scores.get(rsi_signal, 0)
    
    def _suggest_time_frame(self, strength: str, score: float) -> str:
        """建议时间框架"""
        if strength == "强":
            if score > 0:
                return "短期(1-2周)至中期(1-2个月)"
            else:
                return "短期(1-2周)"
        elif strength == "中":
            return "中期(1-3个月)"
        else:
            return "短期(数天)或观望"
    
    def _show_trading_recommendations(self, overall_trend: Dict):
        """显示交易建议"""
        print(f"\n💡 交易策略建议:")
        print("=" * 80)
        
        direction = overall_trend['direction']
        strength = overall_trend['strength']
        confidence = overall_trend['confidence']
        score = overall_trend['score']
        
        if "强烈上涨" in direction:
            print("🟢 强烈看涨信号")
            print("  📋 建议操作:")
            print("  • 积极买入或加仓")
            print("  • 可适当追高，但控制仓位")
            print("  • 设置止损在最近支撑位")
            print("  • 目标位：下一个阻力位")
            
        elif "上涨" in direction:
            print("🟡 看涨信号")
            print("  📋 建议操作:")
            print("  • 适量买入或持有")
            print("  • 等待回调至均线支撑再加仓")
            print("  • 设置移动止损保护利润")
            print("  • 分批减仓获利了结")
            
        elif "震荡" in direction:
            print("🟠 震荡信号")
            print("  📋 建议操作:")
            print("  • 区间操作，高抛低吸")
            print("  • 等待明确突破信号")
            print("  • 控制仓位，保持灵活性")
            print("  • 关注关键支撑阻力位")
            
        elif "下跌" in direction:
            print("🔴 看跌信号")
            print("  📋 建议操作:")
            print("  • 减仓或清仓观望")
            print("  • 避免抄底，等待止跌")
            print("  • 可考虑反弹时减仓")
            print("  • 关注超卖反弹机会")
            
        elif "强烈下跌" in direction:
            print("🔴 强烈看跌信号")
            print("  📋 建议操作:")
            print("  • 立即清仓止损")
            print("  • 避免抄底和反弹抢反弹")
            print("  • 等待明确止跌信号")
            print("  • 关注重要支撑位")
        
        # 风险提示
        print(f"\n⚠️ 风险提示:")
        print(f"  • 置信度: {confidence} - {'建议谨慎操作' if confidence == '低' else '可适度操作' if confidence == '中' else '可积极操作'}")
        print(f"  • 建议时间框架: {overall_trend['time_frame']}")
        print(f"  • 技术指标为滞后指标，需结合基本面分析")
        print(f"  • 严格执行止损，控制风险")
        print(f"  • 分散投资，避免集中风险")
    
    def _analyze_trend_with_data(self, data, symbol, name):
        """使用数据进行趋势分析（用于最新数据模式）"""
        if name is None:
            name = symbol
        
        # 获取最新数据
        latest_date = data.index[-1]
        latest_price = data['close'].iloc[-1]
        
        # 显示分析结果
        print(f"\n🎯 {name} ({symbol}) 趋势分析:")
        print("=" * 80)
        print(f"📅 数据日期: {latest_date.strftime('%Y-%m-%d')}")
        print(f"💰 最新价格: ¥{latest_price:.2f}")
        
        # 分析各项指标
        ma_signal = self._analyze_moving_averages_for_data(data)
        rsi_signal = self._analyze_rsi_for_data(data)
        momentum_signal = self._analyze_momentum_for_data(data)
        breakout_signal = self._analyze_breakout_for_data(data)
        
        # 综合趋势判断
        overall_trend = self._synthesize_trend_signals(ma_signal, rsi_signal, momentum_signal, breakout_signal)
        
        # 交易建议
        self._show_trading_recommendations(overall_trend)
        
        return {
            'symbol': symbol,
            'name': name,
            'date': latest_date,
            'price': latest_price,
            'ma_signal': ma_signal,
            'rsi_signal': rsi_signal,
            'momentum_signal': momentum_signal,
            'breakout_signal': breakout_signal,
            'overall_trend': overall_trend
        }

    def analyze_multiple_stocks(self, stocks: List[Tuple[str, str]]) -> List[Dict]:
        """分析多只股票的趋势"""
        results = []
        
        for symbol, name in stocks:
            result = self.analyze_trend(symbol, name)
            if result:
                results.append(result)
            print("\n" + "="*100 + "\n")
        
        # 对比分析
        if len(results) >= 2:
            self._comparative_analysis(results)
        
        return results
    
    def analyze_multiple_stocks_latest(self, stocks: List[Tuple[str, str]], days: int = 250) -> List[Dict]:
        """分析多只股票的最新趋势（强制获取最新数据）"""
        results = []
        
        print(f"🎯 开始分析 {len(stocks)} 只股票的最新趋势")
        print("=" * 100)
        
        for i, (symbol, name) in enumerate(stocks, 1):
            print(f"\n📈 {i}/{len(stocks)} - 分析 {name} ({symbol})")
            print("-" * 80)
            
            result = self.analyze_trend(symbol, name, days)
            if result:
                results.append(result)
            
            if i < len(stocks):
                print("\n" + "="*100 + "\n")
        
        # 对比分析
        if len(results) >= 2:
            self._comparative_analysis_latest(results)
        
        return results
    
    def _comparative_analysis(self, results: List[Dict]):
        """对比分析多只股票"""
        print("📊 多股票趋势对比分析:")
        print("=" * 100)
        
        # 按综合评分排序
        results.sort(key=lambda x: x['overall_trend']['score'], reverse=True)
        
        print("🏆 综合评分排名:")
        for i, result in enumerate(results, 1):
            trend = result['overall_trend']
            print(f"{i}. {result['name']} ({result['symbol']})")
            print(f"   📊 评分: {trend['score']:.1f} | 趋势: {trend['direction']} | 强度: {trend['strength']}")
        
        # 分类汇总
        categories = {}
        for result in results:
            direction = result['overall_trend']['direction']
            if direction not in categories:
                categories[direction] = []
            categories[direction].append(result['name'])
        
        print(f"\n📈 趋势分类汇总:")
        for direction, stocks in categories.items():
            print(f"  • {direction}: {', '.join(stocks)}")
    
    def _comparative_analysis_latest(self, results: List[Dict]):
        """对比分析多只股票（最新数据模式）"""
        print("\n📊 最新数据趋势对比分析:")
        print("=" * 100)
        
        # 按综合评分排序
        results.sort(key=lambda x: x['overall_trend']['score'], reverse=True)
        
        print("🏆 综合评分排名 (基于最新数据):")
        for i, result in enumerate(results, 1):
            trend = result['overall_trend']
            latest_date = result['date'].strftime('%Y-%m-%d')
            print(f"{i}. {result['name']} ({result['symbol']})")
            print(f"   📊 评分: {trend['score']:.1f} | 趋势: {trend['direction']} | 强度: {trend['strength']}")
            print(f"   📅 数据日期: {latest_date} | 💰 最新价格: ¥{result['price']:.2f}")
        
        # 投资建议汇总
        print(f"\n💡 基于最新数据的投资建议汇总:")
        print("-" * 60)
        
        strong_bullish = [r for r in results if r['overall_trend']['score'] > 60]
        bullish = [r for r in results if 30 < r['overall_trend']['score'] <= 60]
        neutral = [r for r in results if -30 <= r['overall_trend']['score'] <= 30]
        bearish = [r for r in results if -60 <= r['overall_trend']['score'] < -30]
        strong_bearish = [r for r in results if r['overall_trend']['score'] < -60]
        
        if strong_bullish:
            print(f"🟢 强烈看涨 (>60分): {', '.join([r['name'] for r in strong_bullish])}")
        if bullish:
            print(f"🟡 看涨 (30-60分): {', '.join([r['name'] for r in bullish])}")
        if neutral:
            print(f"🟠 震荡 (-30至30分): {', '.join([r['name'] for r in neutral])}")
        if bearish:
            print(f"🔴 看跌 (-60至-30分): {', '.join([r['name'] for r in bearish])}")
        if strong_bearish:
            print(f"🔴 强烈看跌 (<-60分): {', '.join([r['name'] for r in strong_bearish])}")

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python trend_analyzer.py <股票代码> [股票名称] [--latest]")
        print("  python trend_analyzer.py 002594.SZ 比亚迪")
        print("  python trend_analyzer.py 002594.SZ 比亚迪 --latest  # 强制获取最新数据")
        print("")
        print("多股票分析示例:")
        print("  # 使用缓存数据")
        print("  analyzer = TrendAnalyzer()")
        print("  stocks = [('002594.SZ', '比亚迪'), ('600036.SH', '招商银行')]")
        print("  analyzer.analyze_multiple_stocks(stocks)")
        print("")
        print("  # 使用最新数据")
        print("  analyzer = TrendAnalyzer(use_latest_data=True)")
        print("  analyzer.analyze_multiple_stocks_latest(stocks)")
        return
    
    symbol = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else None
    use_latest = '--latest' in sys.argv
    
    if use_latest:
        print("🔄 使用最新数据模式（禁用缓存）")
        analyzer = TrendAnalyzer(use_latest_data=True)
    else:
        print("📁 使用缓存数据模式")
        analyzer = TrendAnalyzer(use_latest_data=False)
    
    result = analyzer.analyze_trend(symbol, name)
    
    if result:
        print(f"\n✅ {result['name']} 趋势分析完成")
        print(f"📈 综合趋势: {result['overall_trend']['direction']}")
        print(f"💪 趋势强度: {result['overall_trend']['strength']}")
        print(f"📊 综合评分: {result['overall_trend']['score']:.1f}")
        
        if use_latest:
            print(f"⏰ 数据时间: {result['date'].strftime('%Y-%m-%d %H:%M:%S')}")
            print("💡 提示: 基于最新数据的分析结果")

if __name__ == "__main__":
    main() 