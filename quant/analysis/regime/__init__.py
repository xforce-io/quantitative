"""
Regime Detection Module

Classifies market regime (risk-on/off, expansion/contraction, etc.)
per asset pool based on configurable indicator thresholds.
"""

from .regime_detector import RegimeDetector, RegimeState
from .continuous_scorer import ContinuousRegimeScorer
from .feature_pipeline import FeaturePipeline
from .scoring_backend import ScoringBackend, WeightedLinearBackend

__all__ = [
    "RegimeDetector",
    "RegimeState",
    "ContinuousRegimeScorer",
    "FeaturePipeline",
    "ScoringBackend",
    "WeightedLinearBackend",
]
