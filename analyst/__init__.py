#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quantitative Trading Analysis Package
量化交易分析包

提供各种分析工具和脚本
Provides various analysis tools and scripts
"""

__version__ = "1.0.0"
__author__ = "Quantitative Trading Team"

# 只导入存在的模块
try:
    from .strategy_performance_analyzer import StrategyPerformanceAnalyzer
    _has_strategy_analyzer = True
except ImportError:
    _has_strategy_analyzer = False

try:
    from .stock_strategy_analyzer import StockStrategyAnalyzer  
    _has_stock_analyzer = True
except ImportError:
    _has_stock_analyzer = False

__all__ = []
if _has_strategy_analyzer:
    __all__.append('StrategyPerformanceAnalyzer')
if _has_stock_analyzer:
    __all__.append('StockStrategyAnalyzer')
