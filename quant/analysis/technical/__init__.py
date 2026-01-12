#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Technical Analysis Module
技术分析模块

This module provides technical analysis tools:
- Momentum analysis
- Trend analysis
- Relative strength analysis
- Technical indicators

Usage:
    from quant.analysis.technical import MomentumAnalyzer
    from quant.analysis.technical import TechnicalAnalyzer
"""

# Re-export from indicators/ for backward compatibility
# Core classes are in quant/analysis/indicators/

from quant.analysis.indicators.momentum_analyzer import ShortTermMomentumAnalyzer
from quant.analysis.indicators.technical_analyzer import TechnicalAnalyzer as _TechnicalAnalyzer

# Aliases with cleaner names
MomentumAnalyzer = ShortTermMomentumAnalyzer
TechnicalAnalyzer = _TechnicalAnalyzer

__all__ = [
    # New names (recommended)
    'MomentumAnalyzer',
    'TechnicalAnalyzer',
    
    # Original names (backward compatibility)
    'ShortTermMomentumAnalyzer',
]
