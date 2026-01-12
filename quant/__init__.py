"""
统一量化交易包
Unified Quantitative Trading Package

整合所有量化交易功能到统一架构下

Architecture (8-Layer Design):
    Layer 0: core/     - Infrastructure (config, logging, exceptions, utils)
    Layer 1: data/     - Data providers (Yahoo, Tushare)
    Layer 2: analysis/ - Analysis tools (valuation, technical, alpha)
    Layer 3: portfolio/- Portfolio construction (equal weight, risk parity)
    Layer 4: risk/     - Risk management (position limits, VaR, drawdown)
    Layer 5: strategies/- Traditional all-in-one strategies
    Layer 6: engines/  - Execution engines (BacktestEngine, AlgorithmEngine)
    Layer 7: agents/   - Agent coordination (optional)
    Layer 8: bin/cli/  - Entry points
"""

__version__ = "2.2.0"
__author__ = "Quantitative Trading Team"

# =============================================================================
# Layer 0: Core - 基础设施层
# =============================================================================
from .core.config import get_config, get_config_value, get_provider_config
from .core.logging_config import get_logger

# =============================================================================
# Layer 1: Data - 数据层
# =============================================================================
from .data.providers import create_data_provider, DataProvider

# =============================================================================
# Layer 2: Analysis - 分析层 (包含 Alpha)
# =============================================================================

# Valuation Analysis
try:
    from .analysis.valuation import (
        PriceValuationAnalyzer,
        FundamentalValuationAnalyzer,
        PEGValuationAnalyzer,
        RegressionAnalyzer,
    )
except ImportError:
    PriceValuationAnalyzer = None
    FundamentalValuationAnalyzer = None
    PEGValuationAnalyzer = None
    RegressionAnalyzer = None

try:
    from .analysis.valuation import SystemicUndervalueAnalyzer
except ImportError:
    SystemicUndervalueAnalyzer = None

# Alpha Models (NEW)
try:
    from .analysis.alpha import (
        BaseAlpha,
        Insight,
        MomentumAlpha,
        MeanReversionAlpha,
    )
except ImportError:
    BaseAlpha = None
    Insight = None
    MomentumAlpha = None
    MeanReversionAlpha = None

# Advisor
try:
    from .analysis.advisor import InvestmentAdvisor, UnifiedAdvisor
except ImportError:
    InvestmentAdvisor = None
    UnifiedAdvisor = None

# Strategy Comparator
try:
    from .analysis.strategy import StrategyComparator
except ImportError:
    StrategyComparator = None

# Technical Analyzer
try:
    from .analysis.indicators import TechnicalAnalyzer
except ImportError:
    TechnicalAnalyzer = None

# Legacy Portfolio Analyzer (from analysis/)
try:
    from .analysis.portfolio import PortfolioAnalyzer as LegacyPortfolioAnalyzer
except ImportError:
    LegacyPortfolioAnalyzer = None

# =============================================================================
# Layer 3: Portfolio - 组合层 (NEW)
# =============================================================================
try:
    from . import portfolio
    from .portfolio import (
        create_portfolio_constructor,
        BasePortfolioConstructor,
        EqualWeightConstructor,
        RiskParityConstructor,
        Rebalancer,
        PortfolioAnalyzer,
    )
except ImportError:
    portfolio = None
    create_portfolio_constructor = None
    BasePortfolioConstructor = None
    EqualWeightConstructor = None
    RiskParityConstructor = None
    Rebalancer = None
    PortfolioAnalyzer = LegacyPortfolioAnalyzer  # Fallback to legacy

# =============================================================================
# Layer 4: Risk - 风控层 (NEW)
# =============================================================================
try:
    from . import risk
    from .risk import (
        create_risk_model,
        BaseRiskModel,
        RiskCheckResult,
        PositionLimits,
        VaRCalculator,
        DrawdownMonitor,
        CompositeRiskModel,
    )
except ImportError:
    risk = None
    create_risk_model = None
    BaseRiskModel = None
    RiskCheckResult = None
    PositionLimits = None
    VaRCalculator = None
    DrawdownMonitor = None
    CompositeRiskModel = None

# =============================================================================
# Layer 5: Strategies - 策略层
# =============================================================================
from .strategies import STRATEGY_REGISTRY

try:
    from .strategies import (
        GridTradingStrategy,
        UnifiedGridTradingStrategy,
        GridLevel,
        Trade
    )
except ImportError:
    GridTradingStrategy = None
    UnifiedGridTradingStrategy = None
    GridLevel = None
    Trade = None

try:
    from .strategies import DCAStrategy
except ImportError:
    DCAStrategy = None

try:
    from .strategies import MomentumStrategy
except ImportError:
    MomentumStrategy = None

try:
    from .strategies import MeanReversionStrategy
except ImportError:
    MeanReversionStrategy = None

# =============================================================================
# Layer 6: Engines - 执行引擎层
# =============================================================================
from .engines.backtest_engine import BacktestEngine

try:
    from .engines.algorithm_engine import AlgorithmEngine
except ImportError:
    AlgorithmEngine = None

try:
    from .engines.backtest_executor import BacktestExecutor
except ImportError:
    BacktestExecutor = None

try:
    from .engines.backtest_analyzer import BacktestAnalyzer
except ImportError:
    BacktestAnalyzer = None

try:
    from .engines.strategy_optimizer import StrategyOptimizer
except ImportError:
    StrategyOptimizer = None

# =============================================================================
# Core Utilities - 工具函数
# =============================================================================
try:
    from .core import TechnicalIndicators, PerformanceMetrics, add_technical_indicators
except ImportError:
    TechnicalIndicators = None
    PerformanceMetrics = None
    add_technical_indicators = None


# =============================================================================
# Public API Export
# =============================================================================
__all__ = [
    # Version
    '__version__',
    '__author__',
    
    # Layer 0: Core
    'get_config',
    'get_config_value',
    'get_provider_config',
    'get_logger',
    
    # Layer 1: Data
    'create_data_provider',
    'DataProvider',
    
    # Layer 2: Analysis - Valuation
    'PriceValuationAnalyzer',
    'FundamentalValuationAnalyzer',
    'PEGValuationAnalyzer',
    'RegressionAnalyzer',
    'SystemicUndervalueAnalyzer',
    
    # Layer 2: Analysis - Alpha (NEW)
    'BaseAlpha',
    'Insight',
    'MomentumAlpha',
    'MeanReversionAlpha',
    
    # Layer 2: Analysis - Advisor
    'InvestmentAdvisor',
    'UnifiedAdvisor',
    'StrategyComparator',
    'TechnicalAnalyzer',
    
    # Layer 3: Portfolio (NEW)
    'portfolio',
    'create_portfolio_constructor',
    'BasePortfolioConstructor',
    'EqualWeightConstructor',
    'RiskParityConstructor',
    'Rebalancer',
    'PortfolioAnalyzer',
    
    # Layer 4: Risk (NEW)
    'risk',
    'create_risk_model',
    'BaseRiskModel',
    'RiskCheckResult',
    'PositionLimits',
    'VaRCalculator',
    'DrawdownMonitor',
    'CompositeRiskModel',
    
    # Layer 5: Strategies
    'STRATEGY_REGISTRY',
    'GridTradingStrategy',
    'UnifiedGridTradingStrategy',
    'GridLevel',
    'Trade',
    'DCAStrategy',
    'MomentumStrategy',
    'MeanReversionStrategy',
    
    # Layer 6: Engines
    'BacktestEngine',
    'AlgorithmEngine',
    'BacktestExecutor',
    'BacktestAnalyzer',
    'StrategyOptimizer',
    
    # Utilities
    'TechnicalIndicators',
    'PerformanceMetrics',
    'add_technical_indicators',
]
