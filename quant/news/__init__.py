#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
News Module
资讯模块

This module provides news collection and analysis capabilities
此模块提供资讯收集和分析功能
"""

from .news_collector import NewsCollector
from .news_analyzer import NewsAnalyzer
from .investment_analyzer import InvestmentAnalyzer
from .news_preprocessor import NewsPreprocessor
from .two_stage_analyzer import TwoStageNewsAnalyzer
from .news_data_interface import NewsDataInterface, StandardNewsFormat
from .unified_news_collector import UnifiedNewsCollector

__all__ = [
    'NewsCollector',
    'NewsAnalyzer', 
    'InvestmentAnalyzer',
    'NewsPreprocessor',
    'TwoStageNewsAnalyzer',
    'NewsDataInterface',
    'StandardNewsFormat',
    'UnifiedNewsCollector'
] 