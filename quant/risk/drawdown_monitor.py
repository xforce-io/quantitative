#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Drawdown Monitor Risk Model
回撤监控风控模型

Monitors portfolio drawdown and takes action when limits are breached.
"""

from typing import Dict, Optional, List
from enum import Enum
import pandas as pd
from .base_risk_model import BaseRiskModel, RiskCheckResult
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


class DrawdownAction(Enum):
    """Action to take when drawdown limit is breached."""
    ALERT = 'alert'           # Only alert, no position change
    REDUCE = 'reduce'         # Reduce position sizes
    CLOSE_ALL = 'close_all'   # Close all positions


class DrawdownMonitor(BaseRiskModel):
    """
    Drawdown monitoring risk model.
    
    Tracks portfolio drawdown and takes action when limits are breached.
    """
    
    def __init__(
        self,
        max_drawdown: float = 0.20,
        warning_threshold: float = 0.15,
        action: DrawdownAction = DrawdownAction.REDUCE,
        reduce_factor: float = 0.5,
        name: Optional[str] = None
    ):
        """
        Initialize drawdown monitor.
        
        Args:
            max_drawdown: Maximum allowed drawdown (default 20%)
            warning_threshold: Drawdown level to trigger warning (default 15%)
            action: Action to take when max_drawdown is breached
            reduce_factor: Factor to reduce positions by when action is REDUCE
        """
        super().__init__(name)
        self.max_drawdown = max_drawdown
        self.warning_threshold = warning_threshold
        self.action = action
        self.reduce_factor = reduce_factor
        
        # State tracking
        self._peak_value: float = 1.0
        self._current_value: float = 1.0
        self._drawdown_history: List[float] = []
    
    def check(
        self,
        positions: Dict[str, float],
        market_data: Optional[pd.DataFrame] = None,
        current_value: Optional[float] = None,
        peak_value: Optional[float] = None,
        **kwargs
    ) -> RiskCheckResult:
        """
        Check drawdown against limits.
        
        Args:
            positions: Current positions {symbol: weight}
            market_data: Not used directly
            current_value: Current portfolio value
            peak_value: Peak portfolio value
            
        Returns:
            RiskCheckResult with drawdown metrics
        """
        result = RiskCheckResult(
            passed=True,
            adjusted_positions=positions.copy(),
            violations=[],
            risk_metrics={}
        )
        
        # Update state if values provided
        if current_value is not None:
            self._current_value = current_value
        if peak_value is not None:
            self._peak_value = peak_value
        
        # Update peak
        if self._current_value > self._peak_value:
            self._peak_value = self._current_value
        
        # Calculate drawdown
        if self._peak_value > 0:
            drawdown = (self._peak_value - self._current_value) / self._peak_value
        else:
            drawdown = 0.0
        
        self._drawdown_history.append(drawdown)
        
        result.risk_metrics = {
            'current_drawdown': drawdown,
            'max_drawdown_limit': self.max_drawdown,
            'peak_value': self._peak_value,
            'current_value': self._current_value,
            'drawdown_utilization': drawdown / self.max_drawdown if self.max_drawdown > 0 else 0,
        }
        
        # Check warning threshold
        if drawdown >= self.warning_threshold:
            result.risk_metrics['warning'] = True
            logger.warning(
                f"Drawdown warning: {drawdown:.1%} >= {self.warning_threshold:.1%}"
            )
        
        # Check max drawdown
        if drawdown >= self.max_drawdown:
            result.add_violation(
                f"Drawdown {drawdown:.1%} >= max {self.max_drawdown:.1%}"
            )
            
            # Take action based on configuration
            if self.action == DrawdownAction.CLOSE_ALL:
                result.adjusted_positions = {}
                result.risk_metrics['action_taken'] = 'close_all'
                
            elif self.action == DrawdownAction.REDUCE:
                result.adjusted_positions = {
                    k: v * self.reduce_factor
                    for k, v in positions.items()
                }
                result.risk_metrics['action_taken'] = f'reduce_{self.reduce_factor}'
                
            else:  # ALERT only
                result.risk_metrics['action_taken'] = 'alert'
        
        return result
    
    def update_value(self, value: float):
        """
        Update current portfolio value.
        
        Args:
            value: Current portfolio value
        """
        self._current_value = value
        if value > self._peak_value:
            self._peak_value = value
    
    def reset(self, initial_value: float = 1.0):
        """
        Reset drawdown tracking.
        
        Args:
            initial_value: Initial portfolio value
        """
        self._peak_value = initial_value
        self._current_value = initial_value
        self._drawdown_history.clear()
    
    @property
    def current_drawdown(self) -> float:
        """Get current drawdown."""
        if self._peak_value > 0:
            return (self._peak_value - self._current_value) / self._peak_value
        return 0.0
    
    @property
    def max_historical_drawdown(self) -> float:
        """Get maximum historical drawdown."""
        if self._drawdown_history:
            return max(self._drawdown_history)
        return 0.0
