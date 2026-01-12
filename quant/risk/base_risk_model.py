#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Base Risk Model
风控模型基类

This module defines the abstract interface for risk management models.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import pandas as pd


@dataclass
class RiskCheckResult:
    """
    Result of risk check.
    风控检查结果。
    """
    passed: bool                              # Whether all checks passed
    adjusted_positions: Dict[str, float]      # Adjusted positions after risk controls
    violations: List[str] = field(default_factory=list)  # List of violated rules
    risk_metrics: Dict = field(default_factory=dict)     # Computed risk metrics
    
    def __str__(self):
        status = "✅ PASSED" if self.passed else "❌ FAILED"
        if self.violations:
            return f"{status} - Violations: {', '.join(self.violations)}"
        return status
    
    def add_violation(self, message: str):
        """Add a violation message."""
        self.violations.append(message)
        self.passed = False


class BaseRiskModel(ABC):
    """
    Abstract base class for risk models.
    
    Risk models check and optionally adjust portfolio positions
    to ensure they meet risk constraints.
    """
    
    def __init__(self, name: Optional[str] = None):
        """
        Initialize risk model.
        
        Args:
            name: Model name (defaults to class name)
        """
        self.name = name or self.__class__.__name__
    
    @abstractmethod
    def check(
        self,
        positions: Dict[str, float],
        market_data: Optional[pd.DataFrame] = None,
        **kwargs
    ) -> RiskCheckResult:
        """
        Check if positions meet risk constraints.
        
        Args:
            positions: Target positions {symbol: weight}
            market_data: Market data for risk calculations (optional)
            **kwargs: Additional parameters
            
        Returns:
            RiskCheckResult with pass/fail status and adjusted positions
        """
        pass
    
    def validate(self, positions: Dict[str, float]) -> bool:
        """
        Quick validation without adjustments.
        
        Args:
            positions: Target positions {symbol: weight}
            
        Returns:
            True if positions pass all checks
        """
        result = self.check(positions)
        return result.passed
    
    def get_risk_metrics(
        self,
        positions: Dict[str, float],
        market_data: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        Get risk metrics without adjusting positions.
        
        Args:
            positions: Current positions
            market_data: Market data for calculations
            
        Returns:
            Risk metrics dictionary
        """
        result = self.check(positions, market_data)
        return result.risk_metrics
