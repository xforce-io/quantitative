#!/usr/bin/env python3
"""ContinuousRegimeScorer — weighted continuous scoring for regime classification."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd

from quant.analysis.regime.feature_pipeline import FeaturePipeline
from quant.analysis.regime.regime_detector import RegimeState
from quant.analysis.regime.scoring_backend import ScoringBackend, WeightedLinearBackend


# Default score-to-regime thresholds (can be overridden via config)
_DEFAULT_EXPANSION_THRESHOLD = 0.2
_DEFAULT_CONTRACTION_THRESHOLD = -0.2

# Pool label mapping (same as RegimeDetector)
_POOL_LABELS = {
    "us_stocks": ("expansion", "contraction", "transition"),
}


class ContinuousRegimeScorer:
    """
    Continuous-score-based regime classifier.

    Replaces discrete voting with weighted continuous scoring.
    Outputs a standard RegimeState compatible with VerdictEngine and Dashboard.

    Parameters
    ----------
    pool : str
        Asset pool (currently only "us_stocks").
    backend : ScoringBackend, optional
        Scoring backend. Defaults to WeightedLinearBackend loaded from
        config/regime_weights.json.
    pipeline : FeaturePipeline, optional
        Feature pipeline. Defaults to FeaturePipeline(pool).
    expansion_threshold : float, optional
        Score above this -> positive regime. Default 0.2.
    contraction_threshold : float, optional
        Score below this -> negative regime. Default -0.2.
    """

    def __init__(
        self,
        pool: str = "us_stocks",
        backend: Optional[ScoringBackend] = None,
        pipeline: Optional[FeaturePipeline] = None,
        expansion_threshold: Optional[float] = None,
        contraction_threshold: Optional[float] = None,
    ) -> None:
        self._pool = pool
        self._pipeline = pipeline or FeaturePipeline(pool=pool)

        if backend is None:
            here = os.path.dirname(os.path.abspath(__file__))
            repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
            weights_path = os.path.join(repo_root, "config", "regime_weights.json")
            backend = WeightedLinearBackend.from_json(weights_path)
        self._backend = backend

        pos_label, neg_label, neutral_label = _POOL_LABELS[pool]
        self._pos_label = pos_label
        self._neg_label = neg_label
        self._neutral_label = neutral_label

        self._expansion_th = expansion_threshold or _DEFAULT_EXPANSION_THRESHOLD
        self._contraction_th = contraction_threshold or _DEFAULT_CONTRACTION_THRESHOLD

    def score(
        self,
        series: Dict[str, pd.Series],
        eval_idx: int = -1,
    ) -> float:
        """
        Compute raw continuous score in [-1, +1].

        Positive = bullish, negative = bearish, near zero = transition.
        """
        features = self._pipeline.compute(series, eval_idx=eval_idx)
        if not features:
            return 0.0
        return self._backend.score(features)

    def classify(
        self,
        series: Dict[str, pd.Series],
        eval_idx: int = -1,
    ) -> RegimeState:
        """
        Classify regime from time-series data.

        Returns a RegimeState compatible with existing RegimeDetector output.
        """
        features = self._pipeline.compute(series, eval_idx=eval_idx)
        if not features:
            return RegimeState(
                pool=self._pool,
                regime=self._neutral_label,
                confidence=0.0,
                days_since_change=0,
                drivers=["Insufficient data for continuous scoring"],
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

        raw_score = self._backend.score(features)

        regime, confidence = self._map_score(raw_score)

        drivers = self._build_drivers(features, raw_score)

        return RegimeState(
            pool=self._pool,
            regime=regime,
            confidence=round(confidence, 4),
            days_since_change=0,
            drivers=drivers,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _map_score(self, score: float) -> tuple[str, float]:
        """Map continuous score to (regime_label, confidence)."""
        if score > self._expansion_th:
            return self._pos_label, score
        elif score < self._contraction_th:
            return self._neg_label, abs(score)
        else:
            # Transition: confidence = how far from the edges
            confidence = 1.0 - abs(score) / self._expansion_th
            return self._neutral_label, max(0.0, confidence)

    @staticmethod
    def _build_drivers(features: Dict[str, float], score: float) -> List[str]:
        """Build human-readable driver list from feature contributions."""
        drivers: List[str] = []

        # Sort features by absolute contribution (descending)
        sorted_features = sorted(
            features.items(), key=lambda x: abs(x[1]), reverse=True,
        )

        for name, val in sorted_features[:5]:
            direction = "bullish" if val > 0 else "bearish"
            drivers.append(f"{name}: {val:+.3f} ({direction})")

        drivers.append(f"composite score: {score:+.3f}")
        return drivers
