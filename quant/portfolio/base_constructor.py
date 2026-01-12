#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Base Portfolio Constructor
组合构建器基类

This module defines the abstract interface for portfolio construction.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd


@dataclass
class Insight:
    """
    Alpha model generated insight.
    Alpha 模型产生的交易洞察。
    """
    symbol: str               # Stock symbol
    direction: int            # Direction: 1=long, -1=short, 0=neutral
    magnitude: float          # Signal strength: 0.0 ~ 1.0
    confidence: float         # Confidence level: 0.0 ~ 1.0
    period: timedelta = timedelta(days=5)  # Expected holding period
    source: str = 'unknown'   # Source alpha model name
    generated_at: datetime = None
    
    def __post_init__(self):
        if self.generated_at is None:
            self.generated_at = datetime.now()
    
    @property
    def score(self) -> float:
        """Combined score = direction * magnitude * confidence"""
        return self.direction * self.magnitude * self.confidence


@dataclass
class Order:
    """
    Rebalance order.
    再平衡订单。
    """
    symbol: str
    direction: str            # 'BUY' or 'SELL'
    weight_change: float      # Weight change amount
    target_weight: float      # Target weight after execution
    
    def __str__(self):
        sign = '+' if self.direction == 'BUY' else '-'
        return f"{self.symbol}: {sign}{self.weight_change:.2%} -> {self.target_weight:.2%}"


class BasePortfolioConstructor(ABC):
    """
    Abstract base class for portfolio construction.
    
    Portfolio constructors convert Alpha signals (Insights) into
    target portfolio weights.
    """
    
    def __init__(
        self,
        rebalance_threshold: float = 0.05,
        max_positions: int = 20,
        min_weight: float = 0.02
    ):
        """
        Initialize portfolio constructor.
        
        Args:
            rebalance_threshold: Minimum weight deviation to trigger rebalance
            max_positions: Maximum number of positions
            min_weight: Minimum weight per position
        """
        self.rebalance_threshold = rebalance_threshold
        self.max_positions = max_positions
        self.min_weight = min_weight
    
    @abstractmethod
    def construct(
        self,
        insights: List[Insight],
        current_positions: Optional[Dict[str, float]] = None,
        **kwargs
    ) -> Dict[str, float]:
        """
        Construct target portfolio from insights.
        
        Args:
            insights: List of Alpha-generated insights
            current_positions: Current portfolio weights {symbol: weight}
            **kwargs: Additional parameters
            
        Returns:
            Target portfolio weights {symbol: target_weight}
        """
        pass
    
    def rebalance(
        self,
        current: Dict[str, float],
        target: Dict[str, float],
        threshold: Optional[float] = None
    ) -> List[Order]:
        """
        Calculate rebalance orders.
        
        Args:
            current: Current portfolio weights
            target: Target portfolio weights
            threshold: Weight deviation threshold (uses self.rebalance_threshold if None)
            
        Returns:
            List of rebalance orders
        """
        if threshold is None:
            threshold = self.rebalance_threshold
        
        orders = []
        all_symbols = set(current.keys()) | set(target.keys())
        
        for symbol in all_symbols:
            curr_weight = current.get(symbol, 0.0)
            tgt_weight = target.get(symbol, 0.0)
            diff = tgt_weight - curr_weight
            
            if abs(diff) >= threshold:
                orders.append(Order(
                    symbol=symbol,
                    direction='BUY' if diff > 0 else 'SELL',
                    weight_change=abs(diff),
                    target_weight=tgt_weight
                ))
        
        # Sort by absolute weight change (largest first)
        orders.sort(key=lambda o: o.weight_change, reverse=True)
        
        return orders
    
    def filter_insights(self, insights: List[Insight]) -> List[Insight]:
        """
        Filter insights based on quality criteria.
        
        Args:
            insights: Raw insights from Alpha models
            
        Returns:
            Filtered insights
        """
        # Filter by confidence and direction
        filtered = [
            ins for ins in insights
            if ins.confidence > 0.3 and ins.direction != 0
        ]
        
        # Sort by score (absolute value)
        filtered.sort(key=lambda x: abs(x.score), reverse=True)
        
        # Limit to max_positions
        return filtered[:self.max_positions]
    
    def normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """
        Normalize weights to sum to 1.0.
        
        Args:
            weights: Unnormalized weights
            
        Returns:
            Normalized weights summing to 1.0
        """
        total = sum(weights.values())
        if total == 0:
            return {}
        
        normalized = {k: v / total for k, v in weights.items()}
        
        # Remove positions below minimum weight
        normalized = {k: v for k, v in normalized.items() if v >= self.min_weight}
        
        # Re-normalize after removing small positions
        total = sum(normalized.values())
        if total > 0:
            normalized = {k: v / total for k, v in normalized.items()}
        
        return normalized
