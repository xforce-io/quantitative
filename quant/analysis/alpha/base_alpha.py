#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Base Alpha Model
Alpha 模型基类

This module defines the abstract interface for Alpha models.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta
import pandas as pd
import numpy as np


@dataclass
class Insight:
    """
    Alpha model generated insight (trading signal).
    Alpha 模型产生的交易信号。
    
    Attributes:
        symbol: Stock/ETF symbol
        direction: Trade direction: 1=long, -1=short, 0=neutral
        magnitude: Signal strength: 0.0 ~ 1.0
        confidence: Confidence level: 0.0 ~ 1.0
        period: Expected holding period
        source: Source alpha model name
        generated_at: Timestamp when insight was generated
        metadata: Additional signal-specific data
    """
    symbol: str
    direction: int
    magnitude: float
    confidence: float
    period: timedelta = field(default_factory=lambda: timedelta(days=5))
    source: str = 'unknown'
    generated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)
    
    def __post_init__(self):
        # Validate direction
        if self.direction not in (-1, 0, 1):
            raise ValueError(f"Direction must be -1, 0, or 1, got {self.direction}")
        
        # Clamp magnitude and confidence to [0, 1]
        self.magnitude = max(0.0, min(1.0, self.magnitude))
        self.confidence = max(0.0, min(1.0, self.confidence))
    
    @property
    def score(self) -> float:
        """
        Combined score = direction * magnitude * confidence.
        
        Returns:
            Score in range [-1, 1]
        """
        return self.direction * self.magnitude * self.confidence
    
    @property
    def is_bullish(self) -> bool:
        """Check if insight is bullish (long signal)."""
        return self.direction > 0
    
    @property
    def is_bearish(self) -> bool:
        """Check if insight is bearish (short signal)."""
        return self.direction < 0
    
    @property
    def is_neutral(self) -> bool:
        """Check if insight is neutral."""
        return self.direction == 0
    
    def __str__(self):
        direction_str = {1: '📈 LONG', -1: '📉 SHORT', 0: '⚪ NEUTRAL'}
        return (
            f"{self.symbol}: {direction_str[self.direction]} "
            f"(mag={self.magnitude:.2f}, conf={self.confidence:.2f}, "
            f"score={self.score:.2f})"
        )


class BaseAlpha(ABC):
    """
    Abstract base class for Alpha models.
    
    Alpha models analyze market data and generate Insights (trading signals).
    These Insights are then passed to the Portfolio layer for position sizing.
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        weight: float = 1.0
    ):
        """
        Initialize Alpha model.
        
        Args:
            name: Model name (defaults to class name)
            weight: Weight for combining with other alphas (default 1.0)
        """
        self.name = name or self.__class__.__name__
        self.weight = weight
    
    @abstractmethod
    def generate_insights(
        self,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        symbols: Optional[List[str]] = None,
        **kwargs
    ) -> List[Insight]:
        """
        Generate insights from market data.
        
        Args:
            data: Market data - either a single DataFrame or dict of DataFrames
            symbols: List of symbols to analyze (if data is dict)
            **kwargs: Additional parameters
            
        Returns:
            List of Insight objects
        """
        pass
    
    def score_symbol(
        self,
        symbol: str,
        data: pd.DataFrame,
        **kwargs
    ) -> Insight:
        """
        Generate insight for a single symbol.
        
        Override this for simpler implementation when analyzing single symbols.
        
        Args:
            symbol: Stock symbol
            data: Price data for the symbol
            **kwargs: Additional parameters
            
        Returns:
            Insight object
        """
        # Default implementation - should be overridden
        raise NotImplementedError("Override score_symbol for single-symbol analysis")
    
    def combine_insights(
        self,
        insights_list: List[List[Insight]]
    ) -> List[Insight]:
        """
        Combine insights from multiple alpha models.
        
        Args:
            insights_list: List of insight lists from different models
            
        Returns:
            Combined and weighted insights
        """
        # Group insights by symbol
        symbol_insights: Dict[str, List[Insight]] = {}
        for insights in insights_list:
            for insight in insights:
                if insight.symbol not in symbol_insights:
                    symbol_insights[insight.symbol] = []
                symbol_insights[insight.symbol].append(insight)
        
        # Combine insights for each symbol
        combined = []
        for symbol, insights in symbol_insights.items():
            if len(insights) == 1:
                combined.append(insights[0])
            else:
                # Weighted average of scores
                total_weight = sum(
                    getattr(ins, 'weight', 1.0) * ins.confidence
                    for ins in insights
                )
                if total_weight > 0:
                    weighted_score = sum(
                        ins.score * getattr(ins, 'weight', 1.0) * ins.confidence
                        for ins in insights
                    ) / total_weight
                    
                    avg_confidence = np.mean([ins.confidence for ins in insights])
                    
                    combined.append(Insight(
                        symbol=symbol,
                        direction=1 if weighted_score > 0 else (-1 if weighted_score < 0 else 0),
                        magnitude=abs(weighted_score),
                        confidence=avg_confidence,
                        source='combined',
                        metadata={'source_models': [ins.source for ins in insights]}
                    ))
        
        return combined
    
    def validate_data(self, data: pd.DataFrame) -> bool:
        """
        Validate input data has required columns.
        
        Args:
            data: Input price data
            
        Returns:
            True if valid, False otherwise
        """
        required_columns = ['close']
        return all(col in data.columns for col in required_columns)
