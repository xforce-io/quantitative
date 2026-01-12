#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Regression Analysis Module
回归分析模块

This module provides regression analysis tools for price trend analysis.
此模块包装了 bin/regression_analyzer.py 中的核心类。

Usage:
    from quant.analysis.valuation import RegressionAnalyzer
    
    analyzer = RegressionAnalyzer()
    result = analyzer.analyze('000001.SZ', days=120)
    
Features:
    - Linear regression
    - Polynomial regression
    - Exponential regression
    - Logarithmic regression
    - Mean reversion signals
    - Price deviation analysis
"""

import sys
from pathlib import Path

# Add bin/ directory to path to import the original implementation
project_root = Path(__file__).parent.parent.parent.parent
bin_path = project_root / 'bin'
if str(bin_path) not in sys.path:
    sys.path.insert(0, str(bin_path))

# Import the original implementation
# We keep the core class in bin/ for now to avoid breaking CLI functionality
try:
    from regression_analyzer import RegressionAnalyzer as _OriginalRegressionAnalyzer
except ImportError:
    # Fallback: define a minimal implementation if import fails
    _OriginalRegressionAnalyzer = None


if _OriginalRegressionAnalyzer is not None:
    # Use the original implementation
    class RegressionAnalyzer(_OriginalRegressionAnalyzer):
        """
        Regression analyzer for price trend analysis.
        
        This is a wrapper around the original RegressionAnalyzer from bin/.
        All functionality is preserved.
        
        Methods:
            analyze(symbol, days, regression_type, degree, adj):
                Execute regression analysis on a symbol.
            
            backtest_mean_reversion(result, threshold, mode):
                Backtest mean reversion strategy based on regression.
            
            plot_regression(result, show):
                Generate regression analysis plots.
        """
        pass
else:
    # Minimal fallback implementation
    from typing import Dict, Optional
    import numpy as np
    import pandas as pd
    from quant.core.logging_config import get_logger
    
    logger = get_logger(__name__)
    
    class RegressionAnalyzer:
        """
        Minimal regression analyzer (fallback implementation).
        
        Full implementation is in bin/regression_analyzer.py.
        Install dependencies and ensure the file exists for full functionality.
        """
        
        def __init__(self, data_provider: str = 'auto'):
            """Initialize analyzer."""
            from quant.data import create_data_provider
            from quant import get_config
            
            config = get_config()
            self.provider = create_data_provider(data_provider, config.get_providers_config())
            self.results = {}
        
        def analyze(
            self,
            symbol: str,
            days: int = 120,
            regression_type: str = 'all',
            degree: int = 2,
            adj: Optional[str] = None
        ) -> Dict:
            """
            Execute regression analysis.
            
            Args:
                symbol: Stock/ETF symbol
                days: Number of historical days
                regression_type: 'linear', 'poly', 'exp', 'log', or 'all'
                degree: Polynomial degree (for poly regression)
                adj: Adjustment type ('qfq', 'hfq', or None)
                
            Returns:
                Analysis result dictionary
            """
            raise NotImplementedError(
                "Full RegressionAnalyzer not available. "
                "Please run 'python bin/regression_analyzer.py' directly."
            )


__all__ = ['RegressionAnalyzer']
