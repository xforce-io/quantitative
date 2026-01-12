#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Portfolio Analyzer
投资组合分析器

Provides portfolio performance analysis, risk metrics, and attribution.
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from dataclasses import dataclass
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PortfolioMetrics:
    """Portfolio performance metrics."""
    total_return: float           # Total return
    annualized_return: float      # Annualized return
    volatility: float             # Annualized volatility
    sharpe_ratio: float           # Sharpe ratio
    max_drawdown: float           # Maximum drawdown
    calmar_ratio: float           # Calmar ratio (return / max drawdown)
    win_rate: float               # Win rate (positive days / total days)
    
    def __str__(self):
        return (
            f"Return: {self.annualized_return:.1%}, "
            f"Vol: {self.volatility:.1%}, "
            f"Sharpe: {self.sharpe_ratio:.2f}, "
            f"MaxDD: {self.max_drawdown:.1%}"
        )


class PortfolioAnalyzer:
    """
    Analyze portfolio performance and risk.
    
    Provides:
    - Performance metrics (return, volatility, Sharpe, etc.)
    - Risk metrics (VaR, max drawdown, etc.)
    - Position analysis
    - Attribution analysis
    """
    
    def __init__(self, risk_free_rate: float = 0.02):
        """
        Initialize analyzer.
        
        Args:
            risk_free_rate: Annual risk-free rate for Sharpe calculation
        """
        self.risk_free_rate = risk_free_rate
    
    def calculate_metrics(
        self,
        returns: pd.Series,
        periods_per_year: int = 252
    ) -> PortfolioMetrics:
        """
        Calculate portfolio performance metrics.
        
        Args:
            returns: Daily returns series
            periods_per_year: Trading periods per year (252 for daily)
            
        Returns:
            PortfolioMetrics dataclass
        """
        if len(returns) < 2:
            return PortfolioMetrics(
                total_return=0.0,
                annualized_return=0.0,
                volatility=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                calmar_ratio=0.0,
                win_rate=0.0
            )
        
        # Total return
        total_return = (1 + returns).prod() - 1
        
        # Annualized return
        n_periods = len(returns)
        years = n_periods / periods_per_year
        if years > 0:
            annualized_return = (1 + total_return) ** (1 / years) - 1
        else:
            annualized_return = 0.0
        
        # Volatility
        volatility = returns.std() * np.sqrt(periods_per_year)
        
        # Sharpe ratio
        excess_return = annualized_return - self.risk_free_rate
        if volatility > 0:
            sharpe_ratio = excess_return / volatility
        else:
            sharpe_ratio = 0.0
        
        # Maximum drawdown
        cumulative = (1 + returns).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdowns = cumulative / rolling_max - 1
        max_drawdown = abs(drawdowns.min())
        
        # Calmar ratio
        if max_drawdown > 0:
            calmar_ratio = annualized_return / max_drawdown
        else:
            calmar_ratio = 0.0
        
        # Win rate
        win_rate = (returns > 0).mean()
        
        return PortfolioMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            calmar_ratio=calmar_ratio,
            win_rate=win_rate
        )
    
    def calculate_var(
        self,
        returns: pd.Series,
        confidence: float = 0.95
    ) -> float:
        """
        Calculate Value at Risk (VaR).
        
        Args:
            returns: Daily returns series
            confidence: Confidence level (default 95%)
            
        Returns:
            VaR as positive number (potential loss)
        """
        if len(returns) < 20:
            return 0.0
        
        var = np.percentile(returns, (1 - confidence) * 100)
        return abs(var)
    
    def calculate_cvar(
        self,
        returns: pd.Series,
        confidence: float = 0.95
    ) -> float:
        """
        Calculate Conditional Value at Risk (CVaR / Expected Shortfall).
        
        Args:
            returns: Daily returns series
            confidence: Confidence level (default 95%)
            
        Returns:
            CVaR as positive number (expected loss beyond VaR)
        """
        if len(returns) < 20:
            return 0.0
        
        var = self.calculate_var(returns, confidence)
        # CVaR is the average of returns below VaR
        tail_returns = returns[returns <= -var]
        if len(tail_returns) > 0:
            return abs(tail_returns.mean())
        return var
    
    def analyze_positions(
        self,
        weights: Dict[str, float],
        prices: Optional[Dict[str, float]] = None
    ) -> Dict:
        """
        Analyze portfolio positions.
        
        Args:
            weights: Position weights {symbol: weight}
            prices: Current prices {symbol: price} (optional)
            
        Returns:
            Position analysis dictionary
        """
        n_positions = len(weights)
        total_weight = sum(weights.values())
        
        # Concentration metrics
        weights_list = list(weights.values())
        max_weight = max(weights_list) if weights_list else 0
        top3_weight = sum(sorted(weights_list, reverse=True)[:3])
        hhi = sum(w ** 2 for w in weights_list)  # Herfindahl-Hirschman Index
        
        return {
            'n_positions': n_positions,
            'total_weight': total_weight,
            'max_single_weight': max_weight,
            'top3_concentration': top3_weight,
            'hhi': hhi,
            'effective_n': 1 / hhi if hhi > 0 else 0,  # Effective number of positions
        }
    
    def attribution(
        self,
        weights: Dict[str, float],
        returns: Dict[str, float]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculate return attribution by position.
        
        Args:
            weights: Position weights {symbol: weight}
            returns: Position returns {symbol: return}
            
        Returns:
            Tuple of (total_return, {symbol: contribution})
        """
        contributions = {}
        total_return = 0.0
        
        for symbol, weight in weights.items():
            ret = returns.get(symbol, 0.0)
            contribution = weight * ret
            contributions[symbol] = contribution
            total_return += contribution
        
        return total_return, contributions
