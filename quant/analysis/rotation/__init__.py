"""A 股行业 ETF 轮动系统模块。"""
from quant.analysis.rotation.backtest import (
    RotationBacktestConfig,
    RotationBacktestResult,
    RotationBacktester,
)
from quant.analysis.rotation.portfolio import PortfolioCombiner
from quant.analysis.rotation.ranker import MomentumRanker, RankerConfig
from quant.analysis.rotation.cockpit_overlay import (
    CockpitOverlayConfig,
    CockpitRegimeOverlay,
)
from quant.analysis.rotation.regime_overlay import (
    PrecomputedRegimeOverlay,
    RegimeOverlay,
    SimpleRegimeOverlay,
)
from quant.analysis.rotation.universe import EtfEntry, load_universe

__all__ = [
    "CockpitOverlayConfig",
    "CockpitRegimeOverlay",
    "EtfEntry",
    "MomentumRanker",
    "PortfolioCombiner",
    "PrecomputedRegimeOverlay",
    "RankerConfig",
    "RegimeOverlay",
    "RotationBacktestConfig",
    "RotationBacktestResult",
    "RotationBacktester",
    "SimpleRegimeOverlay",
    "load_universe",
]
