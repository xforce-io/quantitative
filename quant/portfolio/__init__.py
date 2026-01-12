#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Portfolio Construction Module
组合构建模块

This module provides portfolio construction and optimization tools.
根据 Alpha 信号构建目标投资组合。

Usage:
    from quant.portfolio import (
        create_portfolio_constructor,
        EqualWeightConstructor,
        RiskParityConstructor,
        PortfolioAnalyzer
    )
    
    # Create constructor
    constructor = create_portfolio_constructor('equal_weight')
    
    # Build portfolio from insights
    target_positions = constructor.construct(insights)
    
    # Calculate rebalance orders
    orders = constructor.rebalance(current_positions, target_positions)
"""

from .base_constructor import BasePortfolioConstructor
from .equal_weight import EqualWeightConstructor
from .risk_parity import RiskParityConstructor
from .rebalancer import Rebalancer
from .portfolio_analyzer import PortfolioAnalyzer


def create_portfolio_constructor(
    method: str = 'equal_weight',
    **kwargs
) -> BasePortfolioConstructor:
    """
    Create a portfolio constructor.
    
    Args:
        method: Construction method, one of:
            - 'equal_weight': Equal weight allocation
            - 'risk_parity': Risk parity allocation
        **kwargs: Constructor-specific parameters
        
    Returns:
        BasePortfolioConstructor instance
    """
    method = method.lower().strip()
    
    if method == 'equal_weight':
        return EqualWeightConstructor(**kwargs)
    elif method == 'risk_parity':
        return RiskParityConstructor(**kwargs)
    else:
        raise ValueError(f"Unknown construction method: {method}")


__all__ = [
    # Factory
    'create_portfolio_constructor',
    
    # Base class
    'BasePortfolioConstructor',
    
    # Implementations
    'EqualWeightConstructor',
    'RiskParityConstructor',
    
    # Utilities
    'Rebalancer',
    'PortfolioAnalyzer',
]
