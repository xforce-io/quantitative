"""
技术指标分析模块
Technical Indicators Analysis Module

提供技术指标计算和分析功能
"""

try:
    from .technical_analyzer import TechnicalAnalyzer
except ImportError:
    TechnicalAnalyzer = None

try:
    from .capital_flow_analyzer import CapitalFlowAnalyzer
except ImportError:
    CapitalFlowAnalyzer = None

try:
    from .momentum_analyzer import MomentumAnalyzer
except ImportError:
    MomentumAnalyzer = None

try:
    from .box_breakout_analyzer import BoxBreakoutAnalyzer
except ImportError:
    BoxBreakoutAnalyzer = None

try:
    from .value_investing_analyzer import ValueInvestingAnalyzer
except ImportError:
    ValueInvestingAnalyzer = None

try:
    from .macro_liquidity_analyzer import MacroLiquidityAnalyzer
except ImportError:
    MacroLiquidityAnalyzer = None

try:
    from .china_market_signal_analyzer import ChinaMarketSignalAnalyzer
except ImportError:
    ChinaMarketSignalAnalyzer = None

__all__ = [
    'TechnicalAnalyzer', 'CapitalFlowAnalyzer', 'MomentumAnalyzer',
    'BoxBreakoutAnalyzer', 'ValueInvestingAnalyzer', 'MacroLiquidityAnalyzer',
    'ChinaMarketSignalAnalyzer',
]