#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Valuation Analysis Module
估值分析模块

This module provides various valuation analysis tools:
- Price percentile valuation
- Fundamental valuation (PE/PB/ROE)
- PEG valuation
- Regression analysis

Usage:
    from quant.analysis.valuation import PriceValuationAnalyzer
    from quant.analysis.valuation import PEGValuationAnalyzer
    from quant.analysis.valuation import RegressionAnalyzer
"""

# Price-based valuation (from etf_valuation_analyzer.py)
from .price_valuation import ETFValuationAnalyzer, PriceValuationAnalyzer

# Fundamental valuation (from etf_fundamental_analyzer.py)
from .fundamental_valuation import ETFFundamentalAnalyzer, FundamentalValuationAnalyzer

# PEG valuation (from screener/peg_valuation_analyzer.py)
from .peg_valuation import PEGValuationAnalyzer, ConsensusDataProvider

# Regression analysis (from bin/regression_analyzer.py)
from .regression_analyzer import RegressionAnalyzer

# Stock valuation (percentile-based for A-share individual stocks)
from .stock_valuation import StockValuationAnalyzer

# Systemic undervaluation detection (if exists)
try:
    from .systemic_undervalue import SystemicUndervalueAnalyzer, ValuationScore, UndervalueResult
except ImportError:
    pass

__all__ = [
    # New names (recommended, snake_case style)
    'PriceValuationAnalyzer',
    'FundamentalValuationAnalyzer',
    'PEGValuationAnalyzer',
    'RegressionAnalyzer',
    'ConsensusDataProvider',
    
    'StockValuationAnalyzer',

    # Backward compatibility aliases (original names)
    'ETFValuationAnalyzer',
    'ETFFundamentalAnalyzer',
]
