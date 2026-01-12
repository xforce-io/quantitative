#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Risk Management Module
风控管理模块

This module provides risk management and position control tools.
对组合层输出的目标仓位进行约束检查和调整。

Usage:
    from quant.risk import (
        create_risk_model,
        PositionLimits,
        VaRCalculator,
        DrawdownMonitor,
        CompositeRiskModel
    )
    
    # Create single risk model
    risk = PositionLimits(max_single_position=0.10)
    
    # Check positions
    result = risk.check(target_positions)
    adjusted = result.adjusted_positions
    
    # Combine multiple risk models
    composite = CompositeRiskModel([
        PositionLimits(max_single_position=0.10),
        VaRCalculator(var_limit=0.05),
        DrawdownMonitor(max_drawdown=0.20)
    ])
"""

from .base_risk_model import BaseRiskModel, RiskCheckResult
from .position_limits import PositionLimits
from .var_calculator import VaRCalculator
from .drawdown_monitor import DrawdownMonitor
from .composite_risk import CompositeRiskModel


def create_risk_model(
    model_type: str = 'position_limits',
    **kwargs
) -> BaseRiskModel:
    """
    Create a risk model.
    
    Args:
        model_type: Risk model type, one of:
            - 'position_limits': Position size limits
            - 'var': Value at Risk limits
            - 'drawdown': Drawdown monitoring
            - 'composite': Combination of models
        **kwargs: Model-specific parameters
        
    Returns:
        BaseRiskModel instance
    """
    model_type = model_type.lower().strip()
    
    if model_type == 'position_limits':
        return PositionLimits(**kwargs)
    elif model_type == 'var':
        return VaRCalculator(**kwargs)
    elif model_type == 'drawdown':
        return DrawdownMonitor(**kwargs)
    elif model_type == 'composite':
        models = kwargs.get('models', [])
        return CompositeRiskModel(models)
    else:
        raise ValueError(f"Unknown risk model type: {model_type}")


__all__ = [
    # Factory
    'create_risk_model',
    
    # Base class and result
    'BaseRiskModel',
    'RiskCheckResult',
    
    # Implementations
    'PositionLimits',
    'VaRCalculator',
    'DrawdownMonitor',
    'CompositeRiskModel',
]
