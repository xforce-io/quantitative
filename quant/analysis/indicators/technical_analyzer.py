#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
技术分析器 - 基于新架构
Technical Analyzer - Based on New Architecture

集成各种技术指标分析功能
"""

import math
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

    def score(self, symbol: str, data: pd.DataFrame = None) -> Optional[float]:
        """
        计算技术形态评分 (0-100)，连续值

        基于三个维度打分:
        - 趋势分 (0-40): MA 排列 + 价格偏离 MA20 幅度
        - RSI 分 (0-30): RSI 值的连续映射
        - 成交量分 (0-30): volume_ratio 的对数映射

        Args:
            symbol: 股票代码
            data: 股票数据

        Returns:
            0-100 的连续分数，None 表示无法计算
        """
        if data is None or data.empty:
            return None

        result = self.analyze_stock(data, symbol)

        if not result.get('success', False):
            return None

        indicators = result.get('technical_indicators', {})
        signals = result.get('signals', {})

        # --- 趋势分 (0-40) ---
        trend = signals.get('trend', 'sideways')
        trend_base = {
            'strong_uptrend': 40,
            'uptrend': 30,
            'sideways': 20,
            'downtrend': 10,
            'strong_downtrend': 0,
            'insufficient_data': 20,
        }.get(trend, 20)

        # MA20 偏离度微调 ±5
        ma20 = indicators.get('ma20')
        current_price = result.get('current_price')
        if ma20 and current_price and ma20 > 0:
            ma_deviation = (current_price - ma20) / ma20
            ma_bonus = max(-5, min(5, ma_deviation * 50))
            trend_score = max(0, min(40, trend_base + ma_bonus))
        else:
            trend_score = trend_base

        # --- RSI 分 (0-30) ---
        rsi = indicators.get('rsi')
        if rsi is not None:
            if rsi <= 50:
                # 超卖区是买入机会: RSI 30→25, RSI 50→20
                rsi_score = 15 + (50 - rsi) / 50 * 10
            else:
                # 偏多但超买扣分: RSI 50→20, RSI 70→10, RSI 100→0
                rsi_score = 20 - (rsi - 50) / 50 * 20
            rsi_score = max(0, min(30, rsi_score))
        else:
            rsi_score = 15

        # --- 成交量分 (0-30) ---
        volume_ratio = indicators.get('volume_ratio', 1.0)
        if volume_ratio and volume_ratio > 0:
            log_ratio = math.log(volume_ratio)
            volume_score = 15 + log_ratio * 21.7
            volume_score = max(0, min(30, volume_score))
        else:
            volume_score = 0

        total = trend_score + rsi_score + volume_score
        return round(max(0, min(100, total)), 1)

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

            # 趋势分析（支持大小写列名）
            def _get_col(df, *names):
                for n in names:
                    if n in df.columns:
                        val = df[n].iloc[-1]
                        return val if pd.notna(val) else None
                return None

            ma5 = _get_col(indicators, 'MA5', 'ma5')
            ma20 = _get_col(indicators, 'MA20', 'ma20')
            ma60 = _get_col(indicators, 'MA60', 'ma60')

            trend_signal = self._analyze_trend(current_price, ma5, ma20, ma60)

            # RSI分析（支持大小写列名）
            rsi = _get_col(indicators, 'RSI', 'rsi')
            rsi_signal = self._analyze_rsi(rsi) if rsi else 'unknown'

            # 成交量分析（支持 volume/vol 列名）
            vol_col = 'volume' if 'volume' in data.columns else 'vol'
            volume_ma = data[vol_col].rolling(20).mean().iloc[-1]
            current_volume = data[vol_col].iloc[-1]
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