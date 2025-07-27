"""
Quantitative trading strategies package
"""

# Import the unified strategy and shared data structures
from .unified_grid_strategy import UnifiedGridTradingStrategy, GridLevel, Trade

# For backward compatibility, create alias
GridTradingStrategy = UnifiedGridTradingStrategy

__all__ = [
    'GridTradingStrategy',  # Alias for backward compatibility
    'UnifiedGridTradingStrategy',  # Main unified strategy
    'GridLevel', 
    'Trade'
]

# Recommended strategy for new implementations (same as the alias now)
RecommendedGridStrategy = UnifiedGridTradingStrategy 