"""A-share industry ETF rotation module."""
from quant.analysis.rotation.backtest import (
    RotationBacktestConfig,
    RotationBacktestResult,
    RotationBacktester,
)
from quant.analysis.rotation.frequency import BacktestFrequency
from quant.analysis.rotation.portfolio import PortfolioCombiner
from quant.analysis.rotation.ranker import MomentumRanker, MultiFactorRanker, RankerConfig
from quant.analysis.rotation.cockpit_overlay import (
    CockpitOverlayConfig,
    CockpitRegimeOverlay,
)
from quant.analysis.rotation.multi_sleeve import (
    MinHoldRanker,
    MultiSleeveRanker,
    PortfolioLevelCBRanker,
    RegimeConditionedRanker,
    SYMBOL_ALIASES,
    build_ranker_from_spec,
    load_sleeve_map,
    load_strategy_spec,
    make_ranker_cfg,
    resolve_sota_spec_path,
)
from quant.analysis.rotation.regime_overlay import (
    PrecomputedRegimeOverlay,
    RegimeOverlay,
    SimpleRegimeOverlay,
)
from quant.analysis.rotation.universe import EtfEntry, load_universe

__all__ = [
    "BacktestFrequency",
    "CockpitOverlayConfig",
    "CockpitRegimeOverlay",
    "EtfEntry",
    "MinHoldRanker",
    "MomentumRanker",
    "MultiFactorRanker",
    "MultiSleeveRanker",
    "PortfolioCombiner",
    "PortfolioLevelCBRanker",
    "PrecomputedRegimeOverlay",
    "RankerConfig",
    "RegimeConditionedRanker",
    "RegimeOverlay",
    "RotationBacktestConfig",
    "RotationBacktestResult",
    "RotationBacktester",
    "SYMBOL_ALIASES",
    "SimpleRegimeOverlay",
    "build_ranker_from_spec",
    "load_sleeve_map",
    "load_strategy_spec",
    "load_universe",
    "make_ranker_cfg",
    "resolve_sota_spec_path",
]
