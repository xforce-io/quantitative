#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Risk Parity Portfolio Constructor
风险平价组合构建器

Portfolio construction based on equal risk contribution from each asset.
"""

from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from .base_constructor import BasePortfolioConstructor, Insight
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


class RiskParityConstructor(BasePortfolioConstructor):
    """
    Risk parity portfolio constructor.
    
    Allocates weights such that each asset contributes equally to portfolio risk.
    Uses historical volatility as the risk measure.
    """
    
    def __init__(
        self,
        rebalance_threshold: float = 0.05,
        max_positions: int = 20,
        min_weight: float = 0.02,
        lookback_days: int = 60,
        long_only: bool = True
    ):
        """
        Initialize risk parity constructor.
        
        Args:
            rebalance_threshold: Minimum weight deviation to trigger rebalance
            max_positions: Maximum number of positions
            min_weight: Minimum weight per position
            lookback_days: Days of historical data for volatility calculation
            long_only: If True, only consider long positions
        """
        super().__init__(rebalance_threshold, max_positions, min_weight)
        self.lookback_days = lookback_days
        self.long_only = long_only
        self._volatility_cache: Dict[str, float] = {}
    
    def construct(
        self,
        insights: List[Insight],
        current_positions: Optional[Dict[str, float]] = None,
        returns_data: Optional[Dict[str, pd.Series]] = None,
        **kwargs
    ) -> Dict[str, float]:
        """
        Construct risk-parity weighted portfolio from insights.
        
        Args:
            insights: List of Alpha-generated insights
            current_positions: Current portfolio weights
            returns_data: Historical returns {symbol: returns_series}
            
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
        
        symbols = [ins.symbol for ins in filtered]
        
        # Calculate volatilities
        volatilities = self._calculate_volatilities(symbols, returns_data)
        
        if not volatilities:
            # Fallback to equal weight if no volatility data
            logger.warning("No volatility data available, falling back to equal weight")
            weight = 1.0 / len(symbols)
            return {symbol: weight for symbol in symbols}
        
        # Calculate inverse volatility weights
        weights = self._inverse_volatility_weights(volatilities)
        
        # Apply minimum weight filter and normalize
        return self.normalize_weights(weights)
    
    def _calculate_volatilities(
        self,
        symbols: List[str],
        returns_data: Optional[Dict[str, pd.Series]] = None
    ) -> Dict[str, float]:
        """
        Calculate annualized volatility for each symbol.
        
        Args:
            symbols: List of symbols
            returns_data: Historical returns {symbol: returns_series}
            
        Returns:
            Volatilities {symbol: annualized_volatility}
        """
        volatilities = {}
        
        for symbol in symbols:
            # Try to get from cache
            if symbol in self._volatility_cache:
                volatilities[symbol] = self._volatility_cache[symbol]
                continue
            
            # Calculate from returns data if provided
            if returns_data and symbol in returns_data:
                returns = returns_data[symbol]
                if len(returns) >= 20:
                    vol = returns.std() * np.sqrt(252)  # Annualized
                    volatilities[symbol] = vol
                    self._volatility_cache[symbol] = vol
                    continue
            
            # Default volatility if no data available
            volatilities[symbol] = 0.20  # 20% default
        
        return volatilities
    
    def _inverse_volatility_weights(
        self,
        volatilities: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculate inverse volatility weights.
        
        Lower volatility assets get higher weights.
        
        Args:
            volatilities: {symbol: volatility}
            
        Returns:
            Unnormalized weights {symbol: weight}
        """
        # Inverse volatility
        inverse_vols = {}
        for symbol, vol in volatilities.items():
            if vol > 0:
                inverse_vols[symbol] = 1.0 / vol
            else:
                inverse_vols[symbol] = 1.0  # Default if vol is 0
        
        # Normalize
        total = sum(inverse_vols.values())
        if total > 0:
            return {k: v / total for k, v in inverse_vols.items()}
        return {}
    
    def set_volatility(self, symbol: str, volatility: float):
        """
        Set volatility for a symbol (for testing or manual override).
        
        Args:
            symbol: Stock symbol
            volatility: Annualized volatility
        """
        self._volatility_cache[symbol] = volatility
    
    def clear_cache(self):
        """Clear volatility cache."""
        self._volatility_cache.clear()
