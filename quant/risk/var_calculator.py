#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Value at Risk (VaR) Calculator
VaR 风控计算器

Calculates and enforces VaR limits on portfolio.
"""

from typing import Dict, Optional
import numpy as np
import pandas as pd
from .base_risk_model import BaseRiskModel, RiskCheckResult
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


class VaRCalculator(BaseRiskModel):
    """
    Value at Risk calculator and risk model.
    
    Calculates portfolio VaR and adjusts positions if VaR exceeds limit.
    """
    
    def __init__(
        self,
        var_limit: float = 0.05,
        confidence: float = 0.95,
        lookback_days: int = 60,
        name: Optional[str] = None
    ):
        """
        Initialize VaR calculator.
        
        Args:
            var_limit: Maximum daily VaR as fraction (default 5%)
            confidence: VaR confidence level (default 95%)
            lookback_days: Days of history for VaR calculation
        """
        super().__init__(name)
        self.var_limit = var_limit
        self.confidence = confidence
        self.lookback_days = lookback_days
        
        # Cache for returns data
        self._returns_cache: Dict[str, pd.Series] = {}
    
    def check(
        self,
        positions: Dict[str, float],
        market_data: Optional[pd.DataFrame] = None,
        returns_data: Optional[Dict[str, pd.Series]] = None,
        **kwargs
    ) -> RiskCheckResult:
        """
        Check portfolio VaR against limit.
        
        Args:
            positions: Target positions {symbol: weight}
            market_data: Price data for VaR calculation
            returns_data: Pre-computed returns {symbol: returns_series}
            
        Returns:
            RiskCheckResult with VaR metrics
        """
        result = RiskCheckResult(
            passed=True,
            adjusted_positions=positions.copy(),
            violations=[],
            risk_metrics={}
        )
        
        # Calculate portfolio VaR
        var = self._calculate_portfolio_var(positions, returns_data or self._returns_cache)
        
        result.risk_metrics = {
            'portfolio_var': var,
            'var_limit': self.var_limit,
            'confidence': self.confidence,
            'var_utilization': var / self.var_limit if self.var_limit > 0 else 0,
        }
        
        # Check if VaR exceeds limit
        if var > self.var_limit:
            result.add_violation(
                f"Portfolio VaR {var:.2%} > limit {self.var_limit:.2%}"
            )
            
            # Scale down positions to meet VaR limit
            if var > 0:
                scale = self.var_limit / var * 0.95  # 5% buffer
                result.adjusted_positions = {
                    k: v * scale for k, v in positions.items()
                }
                
                # Recalculate VaR after adjustment
                new_var = self._calculate_portfolio_var(
                    result.adjusted_positions, 
                    returns_data or self._returns_cache
                )
                result.risk_metrics['adjusted_var'] = new_var
        
        return result
    
    def _calculate_portfolio_var(
        self,
        positions: Dict[str, float],
        returns_data: Dict[str, pd.Series]
    ) -> float:
        """
        Calculate portfolio VaR using historical simulation.
        
        Args:
            positions: Portfolio weights
            returns_data: Historical returns {symbol: returns_series}
            
        Returns:
            Portfolio VaR as positive number
        """
        if not positions or not returns_data:
            return 0.0
        
        # Get common date range
        all_returns = []
        weights = []
        
        for symbol, weight in positions.items():
            if symbol in returns_data:
                returns = returns_data[symbol]
                if len(returns) >= 20:
                    all_returns.append(returns.values)
                    weights.append(weight)
        
        if not all_returns:
            # No returns data, estimate VaR from position sizes
            # Assume 20% annual volatility
            total_weight = sum(abs(w) for w in positions.values())
            daily_vol = 0.20 / np.sqrt(252)
            return total_weight * daily_vol * 1.65  # 95% VaR ≈ 1.65σ
        
        # Align return series lengths
        min_len = min(len(r) for r in all_returns)
        all_returns = [r[-min_len:] for r in all_returns]
        
        # Calculate portfolio returns
        returns_matrix = np.column_stack(all_returns)
        weights_array = np.array(weights)
        portfolio_returns = returns_matrix @ weights_array
        
        # Calculate VaR using percentile
        var = np.percentile(portfolio_returns, (1 - self.confidence) * 100)
        
        return abs(var)
    
    def set_returns(self, symbol: str, returns: pd.Series):
        """
        Set returns data for a symbol.
        
        Args:
            symbol: Stock symbol
            returns: Returns series
        """
        self._returns_cache[symbol] = returns
    
    def clear_cache(self):
        """Clear returns cache."""
        self._returns_cache.clear()
