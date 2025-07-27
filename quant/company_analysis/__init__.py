#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
公司分析模块 (Company Analysis Module)
提供配置化的股票分析功能
"""

from .stock_analyzer import UniversalStockAnalyzer
from .company_configs import (
    CompanyConfig, 
    CompanyConfigManager, 
    getCompanyConfig,
    listAvailableCompanies,
    addCompany,
    companyManager
)

__all__ = [
    'UniversalStockAnalyzer',
    'CompanyConfig',
    'CompanyConfigManager',
    'getCompanyConfig',
    'listAvailableCompanies',
    'addCompany',
    'companyManager'
] 