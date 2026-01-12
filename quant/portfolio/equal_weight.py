#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Equal Weight Portfolio Constructor
等权重组合构建器

Simple portfolio construction that assigns equal weights to all selected assets.
"""

from typing import Dict, List, Optional
from .base_constructor import BasePortfolioConstructor, Insight


class EqualWeightConstructor(BasePortfolioConstructor):
    """
    Equal weight portfolio constructor.
    
    Assigns equal weights to all assets with positive direction signals.
    Simple but effective baseline strategy.
    """
    
    def __init__(
        self,
        rebalance_threshold: float = 0.05,
        max_positions: int = 20,
        min_weight: float = 0.02,
        long_only: bool = True
    ):
        """
        Initialize equal weight constructor.
        
        Args:
            rebalance_threshold: Minimum weight deviation to trigger rebalance
            max_positions: Maximum number of positions
            min_weight: Minimum weight per position
            long_only: If True, only consider long positions
        """
        super().__init__(rebalance_threshold, max_positions, min_weight)
        self.long_only = long_only
    
    def construct(
        self,
        insights: List[Insight],
        current_positions: Optional[Dict[str, float]] = None,
        **kwargs
    ) -> Dict[str, float]:
        """
        Construct equal-weighted portfolio from insights.
        
        Args:
            insights: List of Alpha-generated insights
            current_positions: Current portfolio weights (not used for equal weight)
            
        Returns:
            Target portfolio weights {symbol: target_weight}
        """
        # Filter insights
        filtered = self.filter_insights(insights)
        
        # Filter by direction if long_only
        if self.long_only:
            filtered = [ins for ins in filtered if ins.direction > 0]
        
        if not filtered:
            return {}
        
        # Assign equal weights
        weight = 1.0 / len(filtered)
        weights = {ins.symbol: weight for ins in filtered}
        
        # Apply minimum weight filter and normalize
        return self.normalize_weights(weights)
