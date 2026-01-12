"""
投资顾问模块
Investment Advisor Module

提供投资建议和策略分析功能
"""

try:
    from .investment_advisor import InvestmentAdvisor
except ImportError:
    InvestmentAdvisor = None

try:
    from .unified_advisor import UnifiedAdvisor
except ImportError:
    UnifiedAdvisor = None

__all__ = ['InvestmentAdvisor', 'UnifiedAdvisor']