#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Momentum Alpha Model
动量 Alpha 模型

Generates signals based on price momentum and trend strength.
"""

from typing import Dict, List, Optional, Union
from datetime import timedelta
import pandas as pd
import numpy as np
from .base_alpha import BaseAlpha, Insight
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


class MomentumAlpha(BaseAlpha):
    """
    Momentum-based Alpha model.
    
    Generates long signals for assets with strong positive momentum
    and short signals for assets with strong negative momentum.
    
    Momentum is measured using:
    - Rate of change (ROC)
    - Moving average crossovers
    - RSI
    """
    
    def __init__(
        self,
        lookback: int = 20,
        fast_ma: int = 5,
        slow_ma: int = 20,
        roc_threshold: float = 0.05,
        rsi_overbought: float = 70,
        rsi_oversold: float = 30,
        weight: float = 1.0,
        name: Optional[str] = None
    ):
        """
        Initialize Momentum Alpha.
        
        Args:
            lookback: Lookback period for momentum calculation
            fast_ma: Fast moving average period
            slow_ma: Slow moving average period
            roc_threshold: Minimum ROC to generate signal
            rsi_overbought: RSI level for overbought
            rsi_oversold: RSI level for oversold
            weight: Weight for combining with other alphas
        """
        super().__init__(name or "MomentumAlpha", weight)
        self.lookback = lookback
        self.fast_ma = fast_ma
        self.slow_ma = slow_ma
        self.roc_threshold = roc_threshold
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
    
    def generate_insights(
        self,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        symbols: Optional[List[str]] = None,
        **kwargs
    ) -> List[Insight]:
        """
        Generate momentum-based insights.
        
        Args:
            data: Price data (single DataFrame or dict by symbol)
            symbols: Symbols to analyze (required if data is dict)
            
        Returns:
            List of Insight objects
        """
        insights = []
        
        if isinstance(data, dict):
            # Multiple symbols
            for symbol in (symbols or data.keys()):
                if symbol in data:
                    insight = self.score_symbol(symbol, data[symbol])
                    if insight.direction != 0:  # Only add non-neutral signals
                        insights.append(insight)
        else:
            # Single DataFrame - need symbol from kwargs
            symbol = kwargs.get('symbol', 'UNKNOWN')
            insight = self.score_symbol(symbol, data)
            if insight.direction != 0:
                insights.append(insight)
        
        # Sort by absolute score
        insights.sort(key=lambda x: abs(x.score), reverse=True)
        
        return insights
    
    def score_symbol(
        self,
        symbol: str,
        data: pd.DataFrame,
        **kwargs
    ) -> Insight:
        """
        Generate momentum insight for a single symbol.
        
        Args:
            symbol: Stock symbol
            data: Price data with 'close' column
            
        Returns:
            Insight object
        """
        if not self.validate_data(data) or len(data) < self.slow_ma:
            return Insight(
                symbol=symbol,
                direction=0,
                magnitude=0.0,
                confidence=0.0,
                source=self.name
            )
        
        close = data['close']
        
        # Calculate momentum indicators
        roc = self._calculate_roc(close)
        ma_signal = self._calculate_ma_signal(close)
        rsi = self._calculate_rsi(close)
        trend_strength = self._calculate_trend_strength(close)
        
        # Combine signals
        direction, magnitude, confidence = self._combine_signals(
            roc, ma_signal, rsi, trend_strength
        )
        
        return Insight(
            symbol=symbol,
            direction=direction,
            magnitude=magnitude,
            confidence=confidence,
            period=timedelta(days=self.lookback),
            source=self.name,
            metadata={
                'roc': roc,
                'ma_signal': ma_signal,
                'rsi': rsi,
                'trend_strength': trend_strength
            }
        )
    
    def _calculate_roc(self, close: pd.Series) -> float:
        """Calculate rate of change."""
        if len(close) < self.lookback:
            return 0.0
        return (close.iloc[-1] / close.iloc[-self.lookback] - 1)
    
    def _calculate_ma_signal(self, close: pd.Series) -> int:
        """Calculate moving average crossover signal."""
        fast = close.rolling(self.fast_ma).mean().iloc[-1]
        slow = close.rolling(self.slow_ma).mean().iloc[-1]
        
        if fast > slow * 1.01:  # 1% buffer
            return 1
        elif fast < slow * 0.99:
            return -1
        return 0
    
    def _calculate_rsi(self, close: pd.Series, period: int = 14) -> float:
        """Calculate RSI."""
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        if len(gain) < period or loss.iloc[-1] == 0:
            return 50.0
        
        rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] != 0 else 100
        return 100 - (100 / (1 + rs))
    
    def _calculate_trend_strength(self, close: pd.Series) -> float:
        """Calculate trend strength using linear regression slope."""
        if len(close) < self.lookback:
            return 0.0
        
        recent = close.iloc[-self.lookback:]
        x = np.arange(len(recent))
        slope, _ = np.polyfit(x, recent.values, 1)
        
        # Normalize slope by price
        normalized_slope = slope / recent.mean() * 100
        
        return normalized_slope
    
    def _combine_signals(
        self,
        roc: float,
        ma_signal: int,
        rsi: float,
        trend_strength: float
    ) -> tuple:
        """
        Combine individual signals into final insight.
        
        Returns:
            (direction, magnitude, confidence)
        """
        # Determine direction
        bullish_signals = 0
        bearish_signals = 0
        
        # ROC signal
        if roc > self.roc_threshold:
            bullish_signals += 1
        elif roc < -self.roc_threshold:
            bearish_signals += 1
        
        # MA signal
        if ma_signal > 0:
            bullish_signals += 1
        elif ma_signal < 0:
            bearish_signals += 1
        
        # RSI signal (contrarian for extremes)
        if rsi < self.rsi_oversold:
            bullish_signals += 1  # Oversold = potential bounce
        elif rsi > self.rsi_overbought:
            bearish_signals += 1  # Overbought = potential pullback
        
        # Trend strength
        if trend_strength > 0.5:
            bullish_signals += 1
        elif trend_strength < -0.5:
            bearish_signals += 1
        
        # Determine final direction
        if bullish_signals > bearish_signals:
            direction = 1
        elif bearish_signals > bullish_signals:
            direction = -1
        else:
            direction = 0
        
        # Calculate magnitude and confidence
        total_signals = bullish_signals + bearish_signals
        if total_signals == 0:
            return 0, 0.0, 0.0
        
        signal_strength = abs(bullish_signals - bearish_signals) / 4  # Max 4 signals
        magnitude = min(1.0, abs(roc) / 0.20 + signal_strength)  # 20% ROC = max magnitude
        confidence = min(1.0, total_signals / 4 * 0.5 + signal_strength * 0.5)
        
        return direction, magnitude, confidence
