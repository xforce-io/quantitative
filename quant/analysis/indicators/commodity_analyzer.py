#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Commodity Analyzer

Computes commodity price indicators for gold, silver, copper, crude oil, and DXY.

Key indicators:
  - gold_silver_ratio:   gold / silver (latest, aligned indices)
  - copper_gold_ratio:   normalized deviation from 60d rolling mean, in %
  - gold_roc_20d:        20-day rate of change for gold, in %
  - crude_oil_roc_20d:   20-day rate of change for crude oil, in %
  - dxy_roc_20d:         20-day rate of change for DXY, in %
  - copper_roc_20d:      20-day rate of change for copper, in %

All values rounded to 2 decimal places. Missing/insufficient data returns None.
"""

from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from quant.core.logging_config import get_logger

logger = get_logger(__name__)


def _roc_20d(series: pd.Series) -> Optional[float]:
    """
    Rate of change over 20 trading days.

    Formula: (latest / value_21_days_ago - 1) * 100

    Requires at least 21 data points. Returns None otherwise.
    """
    if series is None or len(series) < 21:
        return None
    latest = series.iloc[-1]
    prior = series.iloc[-21]
    if prior == 0 or pd.isna(prior) or pd.isna(latest):
        return None
    return round((latest / prior - 1) * 100, 2)


def _align_and_latest(a: pd.Series, b: pd.Series):
    """Align two series on their common index, return the last values of each."""
    common = a.index.intersection(b.index)
    if len(common) == 0:
        return None, None
    a_aligned = a.loc[common]
    b_aligned = b.loc[common]
    return float(a_aligned.iloc[-1]), float(b_aligned.iloc[-1])


class CommodityAnalyzer:
    """
    Commodity indicator calculator.

    Accepts pre-fetched price series (no live data fetching), so it stays
    fully decoupled from data-layer concerns and is easy to unit-test.
    """

    def analyze(self, data: Dict[str, pd.Series]) -> Dict[str, Any]:
        """
        Compute all commodity indicators from price series.

        Args:
            data: Dict with keys 'gold', 'silver', 'copper', 'crude_oil', 'dxy'.
                  Each value is a pd.Series with DatetimeIndex.

        Returns:
            Dict with: gold_silver_ratio, copper_gold_ratio, gold_roc_20d,
            crude_oil_roc_20d, dxy_roc_20d, copper_roc_20d, analyzed_at.
            Returns {"error": "..."} if no data provided.
        """
        if not data:
            return {"error": "No data provided"}

        gold = data.get("gold")
        silver = data.get("silver")
        copper = data.get("copper")
        crude_oil = data.get("crude_oil")
        dxy = data.get("dxy")

        # --- gold/silver ratio ---
        gold_silver_ratio: Optional[float] = None
        if gold is not None and silver is not None:
            try:
                g_last, s_last = _align_and_latest(gold, silver)
                if g_last is not None and s_last is not None and s_last != 0:
                    gold_silver_ratio = round(g_last / s_last, 2)
            except Exception as exc:
                logger.warning(f"gold_silver_ratio computation failed: {exc}")

        # --- copper/gold ratio (normalized) ---
        copper_gold_ratio: Optional[float] = None
        if copper is not None and gold is not None:
            try:
                common = copper.index.intersection(gold.index)
                if len(common) >= 60:
                    cu = copper.loc[common]
                    au = gold.loc[common]
                    raw_ratio = cu / au
                    rolling_mean = raw_ratio.rolling(window=60).mean()
                    current = float(raw_ratio.iloc[-1])
                    mean_60 = float(rolling_mean.iloc[-1])
                    if mean_60 != 0 and not pd.isna(mean_60):
                        copper_gold_ratio = round((current / mean_60 - 1) * 100, 2)
            except Exception as exc:
                logger.warning(f"copper_gold_ratio computation failed: {exc}")

        # --- 20d ROC indicators ---
        gold_roc_20d = _roc_20d(gold) if gold is not None else None
        crude_oil_roc_20d = _roc_20d(crude_oil) if crude_oil is not None else None
        dxy_roc_20d = _roc_20d(dxy) if dxy is not None else None
        copper_roc_20d = _roc_20d(copper) if copper is not None else None

        return {
            "gold_silver_ratio": gold_silver_ratio,
            "copper_gold_ratio": copper_gold_ratio,
            "gold_roc_20d": gold_roc_20d,
            "crude_oil_roc_20d": crude_oil_roc_20d,
            "dxy_roc_20d": dxy_roc_20d,
            "copper_roc_20d": copper_roc_20d,
            "analyzed_at": datetime.now().isoformat(),
        }

    def get_regime_indicators(
        self, pool: str, data: Dict[str, pd.Series]
    ) -> Dict[str, float]:
        """
        Extract indicators formatted for RegimeDetector consumption.

        Args:
            pool: "gold" or "commodities"
            data: Same dict as accepted by analyze()

        Returns:
            For "gold"       → {gold_silver_ratio, dxy_trend}
            For "commodities"→ {copper_gold_ratio, crude_oil_trend, dxy_trend}
            Unknown pool     → {}
        """
        analysis = self.analyze(data)

        if "error" in analysis:
            return {}

        dxy_roc = analysis.get("dxy_roc_20d")
        dxy_trend = float(dxy_roc) if dxy_roc is not None else 0.0

        if pool == "gold":
            gsr = analysis.get("gold_silver_ratio")
            return {
                "gold_silver_ratio": float(gsr) if gsr is not None else 0.0,
                "dxy_trend": dxy_trend,
            }

        if pool == "commodities":
            cgr = analysis.get("copper_gold_ratio")
            crude_roc = analysis.get("crude_oil_roc_20d")
            return {
                "copper_gold_ratio": float(cgr) if cgr is not None else 0.0,
                "crude_oil_trend": float(crude_roc) if crude_roc is not None else 0.0,
                "dxy_trend": dxy_trend,
            }

        logger.warning(f"get_regime_indicators: unknown pool '{pool}'")
        return {}
