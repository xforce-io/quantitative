#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mean Reversion Alpha Model
均值回归 Alpha 模型

Generates signals based on price deviations from moving average or trend.
"""

from typing import Dict, List, Optional, Union
from datetime import timedelta
import pandas as pd
import numpy as np
from .base_alpha import BaseAlpha, Insight
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


class MeanReversionAlpha(BaseAlpha):
    """
    Mean reversion Alpha model.
    
    Generates signals when price deviates significantly from its mean,
    expecting price to revert back to the mean.
    
    Uses:
    - Z-score relative to moving average
    - Bollinger Bands
    - Percentage deviation from trend
    """
    
    def __init__(
        self,
        lookback: int = 20,
        z_threshold: float = 2.0,
        bb_period: int = 20,
        bb_std: float = 2.0,
        max_deviation: float = 0.15,
        weight: float = 1.0,
        name: Optional[str] = None
    ):
        """
        Initialize Mean Reversion Alpha.
        
        Args:
            lookback: Lookback period for calculations
            z_threshold: Z-score threshold for signal generation
            bb_period: Bollinger Bands period
            bb_std: Bollinger Bands standard deviation multiplier
            max_deviation: Maximum expected deviation (for normalization)
            weight: Weight for combining with other alphas
        """
        super().__init__(name or "MeanReversionAlpha", weight)
        self.lookback = lookback
        self.z_threshold = z_threshold
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.max_deviation = max_deviation
    
    def generate_insights(
        self,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        symbols: Optional[List[str]] = None,
        **kwargs
    ) -> List[Insight]:
        """
        Generate mean reversion insights.
        
        Args:
            data: Price data (single DataFrame or dict by symbol)
            symbols: Symbols to analyze
            
        Returns:
            List of Insight objects
        """
        insights = []
        
        if isinstance(data, dict):
            for symbol in (symbols or data.keys()):
                if symbol in data:
                    insight = self.score_symbol(symbol, data[symbol])
                    if insight.direction != 0:
                        insights.append(insight)
        else:
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
        Generate mean reversion insight for a single symbol.
        
        Args:
            symbol: Stock symbol
            data: Price data with 'close' column
            
        Returns:
            Insight object
        """
        if not self.validate_data(data) or len(data) < self.lookback:
            return Insight(
                symbol=symbol,
                direction=0,
                magnitude=0.0,
                confidence=0.0,
                source=self.name
            )
        
        close = data['close']
        
        # Calculate mean reversion indicators
        z_score = self._calculate_z_score(close)
        bb_position = self._calculate_bb_position(close)
        deviation = self._calculate_deviation(close)
        
        # Combine signals
        direction, magnitude, confidence = self._combine_signals(
            z_score, bb_position, deviation
        )
        
        return Insight(
            symbol=symbol,
            direction=direction,
            magnitude=magnitude,
            confidence=confidence,
            period=timedelta(days=self.lookback // 2),  # Expect faster reversion
            source=self.name,
            metadata={
                'z_score': z_score,
                'bb_position': bb_position,
                'deviation': deviation
            }
        )
    
    def _calculate_z_score(self, close: pd.Series) -> float:
        """Calculate z-score relative to moving average."""
        ma = close.rolling(self.lookback).mean().iloc[-1]
        std = close.rolling(self.lookback).std().iloc[-1]
        
        if std == 0:
            return 0.0
        
        return (close.iloc[-1] - ma) / std
    
    def _calculate_bb_position(self, close: pd.Series) -> float:
        """
        Calculate position within Bollinger Bands.
        
        Returns:
            Value between -1 (below lower band) and 1 (above upper band)
        """
        ma = close.rolling(self.bb_period).mean().iloc[-1]
        std = close.rolling(self.bb_period).std().iloc[-1]
        
        if std == 0:
            return 0.0
        
        upper = ma + self.bb_std * std
        lower = ma - self.bb_std * std
        current = close.iloc[-1]
        
        if current >= upper:
            return 1.0
        elif current <= lower:
            return -1.0
        else:
            # Normalize to [-1, 1]
            band_width = upper - lower
            if band_width > 0:
                return (current - ma) / (band_width / 2)
            return 0.0
    
    def _calculate_deviation(self, close: pd.Series) -> float:
        """Calculate percentage deviation from moving average."""
        ma = close.rolling(self.lookback).mean().iloc[-1]
        
        if ma == 0:
            return 0.0
        
        return (close.iloc[-1] - ma) / ma
    
    def _combine_signals(
        self,
        z_score: float,
        bb_position: float,
        deviation: float
    ) -> tuple:
        """
        Combine signals into mean reversion insight.
        
        Mean reversion is contrarian: buy when oversold, sell when overbought.
        
        Returns:
            (direction, magnitude, confidence)
        """
        # Strong oversold = long signal
        # Strong overbought = short signal (or avoid if long-only)
        
        reversion_signals = 0
        total_signals = 0
        
        # Z-score signal (contrarian)
        if z_score < -self.z_threshold:
            reversion_signals += 1  # Oversold, expect bounce
            total_signals += 1
        elif z_score > self.z_threshold:
            reversion_signals -= 1  # Overbought, expect pullback
            total_signals += 1
        
        # Bollinger Bands signal (contrarian)
        if bb_position < -0.8:
            reversion_signals += 1
            total_signals += 1
        elif bb_position > 0.8:
            reversion_signals -= 1
            total_signals += 1
        
        # Deviation signal (contrarian)
        if deviation < -self.max_deviation * 0.5:
            reversion_signals += 1
            total_signals += 1
        elif deviation > self.max_deviation * 0.5:
            reversion_signals -= 1
            total_signals += 1
        
        # Determine direction
        if reversion_signals > 0:
            direction = 1  # Buy oversold
        elif reversion_signals < 0:
            direction = -1  # Sell overbought
        else:
            direction = 0
        
        if total_signals == 0:
            return 0, 0.0, 0.0
        
        # Calculate magnitude based on deviation size
        magnitude = min(1.0, abs(deviation) / self.max_deviation)
        
        # Confidence based on signal agreement
        confidence = min(1.0, abs(reversion_signals) / 3)
        
        return direction, magnitude, confidence
