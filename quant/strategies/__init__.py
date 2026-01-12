"""
Quantitative trading strategies package
"""

# Import base strategy and shared data structures
from .base_strategy import BaseStrategy, MarketState, TradingDecision

# Import concrete strategy implementations
from .unified_grid_strategy import UnifiedGridTradingStrategy, GridLevel, Trade
from .momentum_strategy import MomentumStrategy, MomentumTrade
from .ma_crossover_strategy import MACrossoverStrategy, MACrossoverTrade
from .seykota_ma_strategy import SeyKotaMAStrategy, SeyKotaTrade
from .hold_strategy import HoldStrategy
from .dca_strategy import DCAStrategy
from .pyramid_dca_strategy import PyramidDCAStrategy

# For backward compatibility, create alias
GridTradingStrategy = UnifiedGridTradingStrategy

__all__ = [
    # Base classes
    'BaseStrategy',
    'MarketState', 
    'TradingDecision',
    
    # Concrete strategies
    'GridTradingStrategy',  # Alias for backward compatibility
    'UnifiedGridTradingStrategy',  # Unified grid strategy
    'MomentumStrategy',  # Momentum strategy
    'MACrossoverStrategy',  # MA crossover strategy
    'SeyKotaMAStrategy',  # Seykota-style MA strategy
    'HoldStrategy',  # Buy and hold strategy
    'DCAStrategy',  # Dollar cost averaging strategy
    'PyramidDCAStrategy',  # Pyramid DCA strategy
    
    # Data structures
    'GridLevel', 
    'Trade',
    'MomentumTrade',
    'MACrossoverTrade',
    'SeyKotaTrade'
]

# Recommended strategy for new implementations
RecommendedGridStrategy = UnifiedGridTradingStrategy

# Strategy registry for easy access
STRATEGY_REGISTRY = {
    'grid': UnifiedGridTradingStrategy,
    'momentum': MomentumStrategy,
    'ma_crossover': MACrossoverStrategy,
    'seykota_ma': SeyKotaMAStrategy,
    'hold': HoldStrategy,
    'dca': DCAStrategy,
    'pyramid_dca': PyramidDCAStrategy,
    # Aliases
    'unified_grid': UnifiedGridTradingStrategy,
    'ma_cross': MACrossoverStrategy,
    'crossover': MACrossoverStrategy,
    'seykota': SeyKotaMAStrategy,
    'seykota_crossover': SeyKotaMAStrategy,
    'pyramid': PyramidDCAStrategy
}
