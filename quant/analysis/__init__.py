#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一分析模块
Unified Analysis Module

This module integrates all analysis tools under a unified architecture.

Submodules:
    - valuation/: Price, fundamental, PEG, and regression valuation
    - technical/: Momentum, trend, and relative strength analysis
    - fundamental/: Financial and industry analysis
    - alpha/: Alpha models for signal generation (future)
    - advisor/: Investment advisors
    - screener/: Stock/ETF screening
    - portfolio/: Portfolio analysis
    - strategy/: Strategy comparison and performance analysis
"""

# Core analyzers
from .basic_analyzer import BasicAnalyzer

# Sub-modules (new structure)
from . import valuation
from . import technical
from . import alpha

# Alpha model exports
try:
    from .alpha import BaseAlpha, Insight, MomentumAlpha, MeanReversionAlpha
except ImportError:
    BaseAlpha = None
    Insight = None
    MomentumAlpha = None
    MeanReversionAlpha = None

# Legacy module imports (backward compatibility)
try:
    from .portfolio import PortfolioAnalyzer
except ImportError:
    PortfolioAnalyzer = None

try:
    from .advisor import InvestmentAdvisor, UnifiedAdvisor
except ImportError:
    InvestmentAdvisor = None
    UnifiedAdvisor = None

try:
    from .strategy import StrategyComparator
except ImportError:
    StrategyComparator = None

try:
    from .indicators import TechnicalAnalyzer
except ImportError:
    TechnicalAnalyzer = None

# Existing valuation analyzers (backward compatibility - now in valuation/)
try:
    from .etf_valuation_analyzer import ETFValuationAnalyzer
except ImportError:
    try:
        from .valuation import ETFValuationAnalyzer
    except ImportError:
        ETFValuationAnalyzer = None

try:
    from .etf_fundamental_analyzer import ETFFundamentalAnalyzer
except ImportError:
    try:
        from .valuation import ETFFundamentalAnalyzer
    except ImportError:
        ETFFundamentalAnalyzer = None

__all__ = [
    # Core
    'BasicAnalyzer',
    
    # Submodules
    'valuation',
    'technical',
    'alpha',
    
    # Alpha models
    'BaseAlpha',
    'Insight',
    'MomentumAlpha',
    'MeanReversionAlpha',
    
    # Legacy (backward compatibility)
    'PortfolioAnalyzer',
    'InvestmentAdvisor',
    'UnifiedAdvisor',
    'StrategyComparator',
    'TechnicalAnalyzer',
    'ETFValuationAnalyzer',
    'ETFFundamentalAnalyzer',
]
