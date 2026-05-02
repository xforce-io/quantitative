"""A 股行业 ETF 轮动系统模块。"""
from quant.analysis.rotation.ranker import MomentumRanker, RankerConfig
from quant.analysis.rotation.universe import EtfEntry, load_universe

__all__ = ["EtfEntry", "MomentumRanker", "RankerConfig", "load_universe"]
