#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RegimeDetector — classifies market regime per asset pool.

Loads thresholds from config/regime_thresholds.yaml and votes each
available indicator positive/negative/neutral. When 60%+ of votes are
positive the pool gets its "positive" regime label; 60%+ negative →
negative label; otherwise → neutral/transition.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import yaml

# ---------------------------------------------------------------------------
# Per-pool regime label triples: (positive_regime, negative_regime, neutral_regime)
# ---------------------------------------------------------------------------
_POOL_LABELS: Dict[str, tuple[str, str, str]] = {
    "a_shares":    ("risk-on",   "risk-off",    "transition"),
    "us_stocks":   ("expansion", "contraction", "transition"),
    "gold":        ("bullish",   "bearish",     "neutral"),
    "commodities": ("reflation", "deflation",   "neutral"),
}

# Public label sets — single source of truth for downstream consumers
# (e.g. VerdictEngine) so they don't have to copy these strings.
POSITIVE_REGIMES: frozenset[str] = frozenset(pos for pos, _, _ in _POOL_LABELS.values())
NEGATIVE_REGIMES: frozenset[str] = frozenset(neg for _, neg, _ in _POOL_LABELS.values())
NEUTRAL_REGIMES: frozenset[str] = frozenset(neu for _, _, neu in _POOL_LABELS.values())

# ---------------------------------------------------------------------------
# Threshold key patterns per pool
# The config uses different key names per pool; we normalise them here.
# Each entry: (positive_threshold_key, negative_threshold_key)
# ---------------------------------------------------------------------------
_THRESHOLD_KEY_PAIRS: Dict[str, Dict[str, tuple[str, str]]] = {
    "a_shares": {
        "margin_debt_trend":  ("risk_on_above",  "risk_off_below"),
        "northbound_flow":    ("risk_on_above",  "risk_off_below"),
        "market_breadth":     ("risk_on_above",  "risk_off_below"),
        "china_risk_score":   ("risk_on_below",  "risk_off_above"),
    },
    "us_stocks": {
        "yield_curve_2s10s":  ("expansion_above", "contraction_below"),
        "credit_spread":      ("expansion_below",  "contraction_above"),
        "vix":                ("expansion_below",  "contraction_above"),
        "macro_risk_score":   ("expansion_below",  "contraction_above"),
    },
    "gold": {
        "real_rate_10y":      ("bullish_below",  "bearish_above"),
        "dxy_trend":          ("bullish_below",  "bearish_above"),
        "gold_silver_ratio":  ("bullish_above",  "bearish_below"),
    },
    "commodities": {
        "copper_gold_ratio":  ("reflation_above", "deflation_below"),
        "crude_oil_trend":    ("reflation_above", "deflation_below"),
        "dxy_trend":          ("reflation_below", "deflation_above"),
    },
}


@dataclass
class RegimeState:
    """Snapshot of a pool's regime at a point in time."""

    pool: str
    regime: str
    confidence: float                  # 0-1: fraction of votes on winning side
    days_since_change: Optional[int]   # None when unknown; 0 means just transitioned
    drivers: List[str]                 # human-readable reasons
    updated_at: str                    # ISO 8601 timestamp


class RegimeDetector:
    """
    Classifies market regime per asset pool using indicator voting.

    Parameters
    ----------
    config_path : str, optional
        Path to regime_thresholds.yaml.  Defaults to
        ``<repo_root>/config/regime_thresholds.yaml``.
    """

    POSITIVE_THRESHOLD = 0.60   # 60%+ votes positive → positive regime
    NEGATIVE_THRESHOLD = 0.60   # 60%+ votes negative → negative regime

    def __init__(self, config_path: Optional[str] = None) -> None:
        if config_path is None:
            # Resolve relative to this file: ../../.. -> repo root
            here = os.path.dirname(os.path.abspath(__file__))
            repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
            config_path = os.path.join(repo_root, "config", "regime_thresholds.yaml")

        with open(config_path, "r", encoding="utf-8") as fh:
            self._config: Dict = yaml.safe_load(fh)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_pool(
        self, pool: str, indicators: Dict[str, float]
    ) -> RegimeState:
        """
        Classify regime for a single asset pool.

        Parameters
        ----------
        pool : str
            One of "a_shares", "us_stocks", "gold", "commodities".
        indicators : dict
            Mapping of indicator name → current value.  Unknown or
            missing indicators are silently skipped.

        Returns
        -------
        RegimeState

        Raises
        ------
        ValueError
            If *pool* is not a recognised pool name.
        """
        if pool not in _POOL_LABELS:
            raise ValueError(
                f"Unknown pool '{pool}'. "
                f"Must be one of: {sorted(_POOL_LABELS)}"
            )

        pool_cfg = self._config.get(pool, {})
        indicator_cfg = pool_cfg.get("indicators", {})
        threshold_keys = _THRESHOLD_KEY_PAIRS[pool]

        pos_votes: int = 0
        neg_votes: int = 0
        drivers: List[str] = []

        for indicator_name, value in indicators.items():
            if indicator_name not in threshold_keys:
                # Indicator not configured for this pool; skip
                continue
            if indicator_name not in indicator_cfg:
                continue

            thresholds = indicator_cfg[indicator_name]
            pos_key, neg_key = threshold_keys[indicator_name]

            pos_threshold = thresholds.get(pos_key)
            neg_threshold = thresholds.get(neg_key)

            # Determine polarity from the threshold key name itself:
            # "above" in pos_key means higher-is-positive;
            # "below" in pos_key means lower-is-positive.
            higher_is_positive = "above" in pos_key

            vote = self._cast_vote(
                value, pos_threshold, neg_threshold, higher_is_positive
            )

            if vote == 1:
                pos_votes += 1
                drivers.append(f"{indicator_name} is bullish ({value:.2f})")
            elif vote == -1:
                neg_votes += 1
                drivers.append(f"{indicator_name} is bearish ({value:.2f})")

        # Aggregate votes
        total_votes = pos_votes + neg_votes
        pos_label, neg_label, neutral_label = _POOL_LABELS[pool]

        if total_votes == 0:
            regime = neutral_label
            confidence = 0.0
        else:
            pos_ratio = pos_votes / total_votes
            neg_ratio = neg_votes / total_votes

            if pos_ratio >= self.POSITIVE_THRESHOLD:
                regime = pos_label
                confidence = pos_ratio
            elif neg_ratio >= self.NEGATIVE_THRESHOLD:
                regime = neg_label
                confidence = neg_ratio
            else:
                regime = neutral_label
                # Confidence = majority ratio even if below threshold
                confidence = max(pos_ratio, neg_ratio) if total_votes > 0 else 0.0

        return RegimeState(
            pool=pool,
            regime=regime,
            confidence=round(confidence, 4),
            days_since_change=None,
            drivers=drivers,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def classify_all(
        self, all_indicators: Dict[str, Dict[str, float]]
    ) -> Dict[str, RegimeState]:
        """
        Classify regime for all pools in *all_indicators*.

        Parameters
        ----------
        all_indicators : dict
            Mapping of pool_name → {indicator_name: value}.

        Returns
        -------
        dict
            Mapping of pool_name → RegimeState.
        """
        return {
            pool: self.classify_pool(pool, indicators)
            for pool, indicators in all_indicators.items()
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cast_vote(
        value: float,
        pos_threshold: Optional[float],
        neg_threshold: Optional[float],
        higher_is_positive: bool,
    ) -> int:
        """
        Return +1 (positive), -1 (negative), or 0 (neutral/abstain).
        """
        if higher_is_positive:
            if pos_threshold is not None and value >= pos_threshold:
                return 1
            if neg_threshold is not None and value <= neg_threshold:
                return -1
        else:
            # lower is positive (inverted indicator)
            if pos_threshold is not None and value <= pos_threshold:
                return 1
            if neg_threshold is not None and value >= neg_threshold:
                return -1
        return 0
