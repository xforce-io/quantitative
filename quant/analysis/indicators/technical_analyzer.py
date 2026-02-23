#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
技术分析器 - 基于新架构
Technical Analyzer - Based on New Architecture

集成各种技术指标分析功能
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from quant.core.indicators import TechnicalIndicators
from quant.core.metrics import PerformanceMetrics


class TechnicalAnalyzer:
    """技术分析器"""

    # 信号到分数的映射
    SIGNAL_SCORES = {
        'strong_buy': 100,
        'buy': 75,
        'hold': 50,
        'sell': 25,
        'strong_sell': 0
    }

    def score(self, symbol: str, data: pd.DataFrame = None) -> float:
        """
        计算技术形态评分 (0-100)

        Args:
            symbol: 股票代码
            data: 股票数据 (如果为None则需要外部提供)

        Returns:
            0-100 的标准化分数，技术形态越好分数越高
        """
        if data is None or data.empty:
            return 50.0  # 无数据时返回中性分数

        result = self.analyze_stock(data, symbol)

        if not result.get('success', False):
            return 50.0

        # 从综合信号获取分数
        overall_signal = result.get('signals', {}).get('overall', 'hold')
        return self.SIGNAL_SCORES.get(overall_signal, 50.0)

    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.metrics = PerformanceMetrics()

    def analyze_stock(self, data: pd.DataFrame, symbol: str = None) -> Dict[str, Any]:
        """
        股票技术分析

        Args:
            data: 股票数据
            symbol: 股票代码

        Returns:
            分析结果
        """
        if data.empty:
            return {'error': 'No data provided'}

        try:
            # 计算技术指标
            indicators = TechnicalIndicators.calculate_all_indicators(data)

            # 基础统计
            current_price = data['close'].iloc[-1]
            price_change = (current_price / data['close'].iloc[0] - 1) * 100

            # 波动率分析
            volatility = data['close'].pct_change().std() * np.sqrt(252) * 100

            # 趋势分析
            ma5 = indicators.get('ma5', pd.Series()).iloc[-1] if 'ma5' in indicators else None
            ma20 = indicators.get('ma20', pd.Series()).iloc[-1] if 'ma20' in indicators else None
            ma60 = indicators.get('ma60', pd.Series()).iloc[-1] if 'ma60' in indicators else None

            trend_signal = self._analyze_trend(current_price, ma5, ma20, ma60)

            # RSI分析
            rsi = indicators.get('rsi', pd.Series()).iloc[-1] if 'rsi' in indicators else None
            rsi_signal = self._analyze_rsi(rsi) if rsi else 'unknown'

            # 成交量分析
            volume_ma = data['volume'].rolling(20).mean().iloc[-1]
            current_volume = data['volume'].iloc[-1]
            volume_ratio = current_volume / volume_ma if volume_ma > 0 else 1
            volume_signal = self._analyze_volume(volume_ratio)

            return {
                'symbol': symbol,
                'analysis_type': 'technical',
                'current_price': current_price,
                'price_change_pct': price_change,
                'volatility': volatility,
                'technical_indicators': {
                    'rsi': rsi,
                    'ma5': ma5,
                    'ma20': ma20,
                    'ma60': ma60,
                    'volume_ratio': volume_ratio
                },
                'signals': {
                    'trend': trend_signal,
                    'rsi': rsi_signal,
                    'volume': volume_signal,
                    'overall': self._generate_overall_signal(trend_signal, rsi_signal, volume_signal)
                },
                'success': True
            }

        except Exception as e:
            return {
                'symbol': symbol,
                'error': str(e),
                'success': False
            }

    def _analyze_trend(self, price: float, ma5: float, ma20: float, ma60: float) -> str:
        """趋势分析"""
        if not all([ma5, ma20, ma60]):
            return 'insufficient_data'

        if price > ma5 > ma20 > ma60:
            return 'strong_uptrend'
        elif price > ma5 > ma20:
            return 'uptrend'
        elif price < ma5 < ma20 < ma60:
            return 'strong_downtrend'
        elif price < ma5 < ma20:
            return 'downtrend'
        else:
            return 'sideways'

    def _analyze_rsi(self, rsi: float) -> str:
        """RSI分析"""
        if rsi >= 70:
            return 'overbought'
        elif rsi <= 30:
            return 'oversold'
        elif rsi >= 50:
            return 'bullish'
        else:
            return 'bearish'

    def _analyze_volume(self, volume_ratio: float) -> str:
        """成交量分析"""
        if volume_ratio >= 2.0:
            return 'very_high'
        elif volume_ratio >= 1.5:
            return 'high'
        elif volume_ratio >= 0.8:
            return 'normal'
        else:
            return 'low'

    def _generate_overall_signal(self, trend: str, rsi: str, volume: str) -> str:
        """生成综合信号"""
        bullish_signals = ['strong_uptrend', 'uptrend', 'oversold', 'bullish', 'very_high', 'high']
        bearish_signals = ['strong_downtrend', 'downtrend', 'overbought', 'bearish']

        score = 0
        if trend in bullish_signals:
            score += 2
        elif trend in bearish_signals:
            score -= 2

        if rsi in bullish_signals:
            score += 1
        elif rsi in bearish_signals:
            score -= 1

        if volume in bullish_signals:
            score += 1

        if score >= 3:
            return 'strong_buy'
        elif score >= 1:
            return 'buy'
        elif score <= -3:
            return 'strong_sell'
        elif score <= -1:
            return 'sell'
        else:
            return 'hold'

    @staticmethod
    def interpret_latest_signals(df: pd.DataFrame) -> Dict[str, Any]:
        """
        解读最新一行的技术信号（MA 趋势、MACD 信号等）

        Args:
            df: 包含技术指标列的 DataFrame（至少含 MA5/MA20/MA60, MACD_DIF/MACD_DEA, RSI, BOLL_UP 等）

        Returns:
            Dict with: latest_close, ma5, ma20, ma60, ma_trend, macd_signal, rsi_value, boll_position
        """
        if df is None or df.empty:
            return {}

        latest = df.iloc[-1]
        result: Dict[str, Any] = {
            'latest_close': round(float(latest.get('close', 0)), 2),
        }

        # MA 值
        for col in ['MA5', 'MA20', 'MA60']:
            val = latest.get(col)
            result[col.lower()] = round(float(val), 2) if pd.notna(val) else None

        # 均线趋势
        ma5 = latest.get('MA5')
        ma20 = latest.get('MA20')
        ma60 = latest.get('MA60')
        if pd.notna(ma5) and pd.notna(ma20) and pd.notna(ma60):
            if ma5 > ma20 > ma60:
                result['ma_trend'] = "多头排列"
            elif ma5 < ma20 < ma60:
                result['ma_trend'] = "空头排列"
            else:
                result['ma_trend'] = "震荡整理"
        else:
            result['ma_trend'] = "unknown"

        # MACD 信号 (支持两套列名)
        dif = latest.get('MACD_DIF', latest.get('MACD'))
        dea = latest.get('MACD_DEA', latest.get('MACD_Signal'))
        if pd.notna(dif) and pd.notna(dea):
            result['macd_signal'] = "金叉/多头" if dif > dea else "死叉/空头"
        else:
            result['macd_signal'] = "unknown"

        # RSI
        rsi = latest.get('RSI')
        result['rsi_value'] = round(float(rsi), 1) if pd.notna(rsi) else None

        # 布林带位置
        if any(col in latest.index for col in ['BOLL_UP', 'BB_Upper']):
            result['boll_position'] = TechnicalAnalyzer.bollinger_position(latest)

        return result

    @staticmethod
    def bollinger_position(row) -> str:
        """
        计算价格在布林带中的位置

        Args:
            row: 包含 close, BOLL_UP/BB_Upper, BOLL_DOWN/BB_Lower, BOLL_MID/BB_Middle 的数据行

        Returns:
            位置描述字符串
        """
        try:
            close = row.get('close', 0)
            up = row.get('BOLL_UP', row.get('BB_Upper', 0))
            down = row.get('BOLL_DOWN', row.get('BB_Lower', 0))
            mid = row.get('BOLL_MID', row.get('BB_Middle', 0))

            if pd.isna(up) or pd.isna(down) or up == down:
                return "unknown"

            if close >= up:
                return "上轨之上（超买）"
            elif close <= down:
                return "下轨之下（超卖）"
            elif close > mid:
                return "中轨之上"
            else:
                return "中轨之下"
        except Exception:
            return "unknown"

    def batch_analyze(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """批量技术分析"""
        results = {}

        for symbol, data in data_dict.items():
            results[symbol] = self.analyze_stock(data, symbol)

        return {
            'batch_analysis': results,
            'summary': self._generate_batch_summary(results)
        }

    def _generate_batch_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """生成批量分析摘要"""
        signals = []
        success_count = 0

        for symbol, result in results.items():
            if result.get('success', False):
                success_count += 1
                signal = result.get('signals', {}).get('overall', 'unknown')
                signals.append(signal)

        signal_counts = {signal: signals.count(signal) for signal in set(signals)}

        return {
            'total_symbols': len(results),
            'successful_analysis': success_count,
            'signal_distribution': signal_counts,
            'dominant_signal': max(signal_counts, key=signal_counts.get) if signal_counts else 'unknown'
        }