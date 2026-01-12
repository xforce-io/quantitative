#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Alpha Models Module
Alpha 模型模块

This module contains Alpha models that generate trading signals (Insights).
Alpha 模型分析市场数据并生成交易信号。

Usage:
    from quant.analysis.alpha import (
        BaseAlpha,
        Insight,
        MomentumAlpha,
        MeanReversionAlpha
    )
    
    # Create alpha model
    alpha = MomentumAlpha(lookback=20)
    
    # Generate insights from market data
    insights = alpha.generate_insights(price_data)
    
    # Insights can then be passed to Portfolio layer
    positions = portfolio_constructor.construct(insights)
"""

from .base_alpha import BaseAlpha, Insight
from .momentum_alpha import MomentumAlpha
from .mean_reversion_alpha import MeanReversionAlpha


__all__ = [
    # Base class and data structure
    'BaseAlpha',
    'Insight',
    
    # Implementations
    'MomentumAlpha',
    'MeanReversionAlpha',
]
