#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Position Limits Risk Model
仓位限制风控模型

Enforces limits on individual position sizes and total exposure.
"""

from typing import Dict, Optional
import pandas as pd
from .base_risk_model import BaseRiskModel, RiskCheckResult


class PositionLimits(BaseRiskModel):
    """
    Position limits risk model.
    
    Enforces:
    - Maximum single position size
    - Maximum sector exposure
    - Maximum total exposure (leverage)
    - Minimum position size (filters out tiny positions)
    """
    
    def __init__(
        self,
        max_single_position: float = 0.10,
        max_sector_exposure: float = 0.30,
        max_total_exposure: float = 1.00,
        min_position_size: float = 0.01,
        sector_mapping: Optional[Dict[str, str]] = None,
        name: Optional[str] = None
    ):
        """
        Initialize position limits.
        
        Args:
            max_single_position: Maximum weight for single position (default 10%)
            max_sector_exposure: Maximum weight for single sector (default 30%)
            max_total_exposure: Maximum total exposure / leverage (default 100%)
            min_position_size: Minimum position size, smaller positions removed
            sector_mapping: {symbol: sector} mapping for sector limits
        """
        super().__init__(name)
        self.max_single_position = max_single_position
        self.max_sector_exposure = max_sector_exposure
        self.max_total_exposure = max_total_exposure
        self.min_position_size = min_position_size
        self.sector_mapping = sector_mapping or {}
    
    def check(
        self,
        positions: Dict[str, float],
        market_data: Optional[pd.DataFrame] = None,
        **kwargs
    ) -> RiskCheckResult:
        """
        Check positions against limits and adjust if needed.
        
        Args:
            positions: Target positions {symbol: weight}
            market_data: Not used for position limits
            
        Returns:
            RiskCheckResult with adjusted positions
        """
        result = RiskCheckResult(
            passed=True,
            adjusted_positions=positions.copy(),
            violations=[],
            risk_metrics={}
        )
        
        adjusted = positions.copy()
        
        # 1. Remove positions below minimum size
        adjusted = {k: v for k, v in adjusted.items() if abs(v) >= self.min_position_size}
        
        # 2. Check and adjust single position limits
        for symbol, weight in list(adjusted.items()):
            if abs(weight) > self.max_single_position:
                result.add_violation(
                    f"{symbol}: {abs(weight):.1%} > max {self.max_single_position:.1%}"
                )
                # Cap at maximum
                adjusted[symbol] = self.max_single_position * (1 if weight > 0 else -1)
        
        # 3. Check sector limits
        if self.sector_mapping:
            sector_weights = {}
            for symbol, weight in adjusted.items():
                sector = self.sector_mapping.get(symbol, 'Unknown')
                sector_weights[sector] = sector_weights.get(sector, 0) + abs(weight)
            
            for sector, weight in sector_weights.items():
                if weight > self.max_sector_exposure:
                    result.add_violation(
                        f"Sector {sector}: {weight:.1%} > max {self.max_sector_exposure:.1%}"
                    )
                    # Scale down sector positions
                    scale = self.max_sector_exposure / weight
                    for symbol in adjusted:
                        if self.sector_mapping.get(symbol, 'Unknown') == sector:
                            adjusted[symbol] *= scale
        
        # 4. Check total exposure
        total_exposure = sum(abs(w) for w in adjusted.values())
        if total_exposure > self.max_total_exposure:
            result.add_violation(
                f"Total exposure: {total_exposure:.1%} > max {self.max_total_exposure:.1%}"
            )
            # Scale down all positions
            scale = self.max_total_exposure / total_exposure
            adjusted = {k: v * scale for k, v in adjusted.items()}
        
        # Update result
        result.adjusted_positions = adjusted
        result.risk_metrics = {
            'total_exposure': sum(abs(w) for w in adjusted.values()),
            'max_position': max(abs(w) for w in adjusted.values()) if adjusted else 0,
            'n_positions': len(adjusted),
        }
        
        return result
    
    def set_sector_mapping(self, mapping: Dict[str, str]):
        """
        Set sector mapping for sector limit checks.
        
        Args:
            mapping: {symbol: sector} dictionary
        """
        self.sector_mapping = mapping
