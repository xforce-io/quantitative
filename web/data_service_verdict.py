#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Verdict Data Service Layer

Wraps the signal-foundation analysis modules (RegimeDetector, VerdictEngine,
TransmissionGraph, SignalRegistry, CommodityAnalyzer) with Streamlit caching
so the UI can call them efficiently without circular-import issues.

All st.cache_data functions return JSON-serialisable dicts (no dataclass
instances).  st.cache_resource functions return singleton objects.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

# Ensure project root is on the path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

logger = logging.getLogger(__name__)

_VALIDATION_DIR = str(Path(__file__).parent.parent / "data" / "signal_validations")

# ---------------------------------------------------------------------------
# Singleton getters (cached with @st.cache_resource)
# ---------------------------------------------------------------------------


@st.cache_resource
def _get_regime_detector():
    """Return a singleton RegimeDetector."""
    from quant.analysis.regime.regime_detector import RegimeDetector

    return RegimeDetector()


@st.cache_resource
def _get_signal_registry():
    """
    Return a singleton SignalRegistry with validations bulk-loaded from
    data/signal_validations/ (if the directory exists).
    """
    from quant.analysis.signals.signal_registry import SignalRegistry

    registry = SignalRegistry()
    try:
        validation_dir = Path(_VALIDATION_DIR)
        if validation_dir.exists() and validation_dir.is_dir():
            count = registry.load_validations_from_dir(_VALIDATION_DIR)
            logger.debug("Loaded %d signal validations from %s", count, _VALIDATION_DIR)
    except Exception as exc:
        logger.warning("Failed to load signal validations: %s", exc)
    return registry


@st.cache_resource
def _get_transmission_graph():
    """Return a singleton TransmissionGraph."""
    from quant.analysis.transmission.transmission_graph import TransmissionGraph

    return TransmissionGraph()


@st.cache_resource
def _get_verdict_engine():
    """Return a singleton VerdictEngine."""
    from quant.analysis.verdict.verdict_engine import VerdictEngine

    return VerdictEngine()


@st.cache_resource
def _get_commodity_analyzer():
    """Return a singleton CommodityAnalyzer."""
    from quant.analysis.indicators.commodity_analyzer import CommodityAnalyzer

    return CommodityAnalyzer()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _regime_state_to_dict(state) -> Dict[str, Any]:
    """Convert a RegimeState dataclass to a JSON-serialisable dict."""
    return {
        "pool": state.pool,
        "regime": state.regime,
        "confidence": state.confidence,
        "days_since_change": state.days_since_change,
        "drivers": list(state.drivers),
        "updated_at": state.updated_at,
    }


def _pool_verdict_to_dict(verdict) -> Dict[str, Any]:
    """Convert a PoolVerdict dataclass to a JSON-serialisable dict."""
    return {
        "pool": verdict.pool,
        "action": verdict.action,
        "confidence": verdict.confidence,
        "reasoning": list(verdict.reasoning),
        "regime": _regime_state_to_dict(verdict.regime),
    }


def _active_transmission_to_dict(tx) -> Dict[str, Any]:
    """Convert an ActiveTransmission dataclass to a JSON-serialisable dict."""
    edge = tx.edge
    return {
        "source": edge.source,
        "target": edge.target,
        "direction": edge.direction,
        "lag_min_days": edge.lag_min_days,
        "lag_max_days": edge.lag_max_days,
        "threshold": edge.threshold,
        "strength": edge.strength,
        "source_ticker": edge.source_ticker,
        "target_ticker": edge.target_ticker,
        "triggered_at": tx.triggered_at,
        "source_move": tx.source_move,
        "expected_target": tx.expected_target,
        "days_remaining": tx.days_remaining,
        "status": tx.status,
    }


# ---------------------------------------------------------------------------
# Data getters (cached with @st.cache_data)
# ---------------------------------------------------------------------------


@st.cache_data(ttl=3600, show_spinner=False)
def get_regime(pool: str) -> Dict[str, Any]:
    """
    Classify the market regime for a single asset pool.

    Gathers indicators from existing data_service analyzers, then calls
    RegimeDetector.classify_pool().  Returns a dict of RegimeState fields.

    Parameters
    ----------
    pool : str
        One of "a_shares", "us_stocks", "gold", "commodities".
    """
    # Lazy import to avoid circular dependency
    from web.data_service import (
        get_china_market_signals,
        get_global_usd_liquidity,
        get_leading_indicators,
        get_macro_liquidity,
    )

    indicators: Dict[str, float] = {}

    try:
        if pool == "a_shares":
            china = get_china_market_signals()
            risk_score = china.get("risk_score")
            if risk_score is not None:
                indicators["china_risk_score"] = float(risk_score)

        elif pool == "us_stocks":
            macro = get_macro_liquidity()
            risk_score = macro.get("risk_score")
            if risk_score is not None:
                indicators["macro_risk_score"] = float(risk_score)

            leading = get_leading_indicators()

            yc = leading.get("yield_curve", {})
            spread_2s10s = yc.get("spread")
            if spread_2s10s is not None:
                indicators["yield_curve_2s10s"] = float(spread_2s10s)

            cs = leading.get("credit_spread", {})
            spread_credit = cs.get("spread")
            if spread_credit is not None:
                indicators["credit_spread"] = float(spread_credit)

            vix_data = leading.get("vix", {})
            vix_value = vix_data.get("value")
            if vix_value is not None:
                indicators["vix"] = float(vix_value)

        elif pool == "gold":
            usd_liq = get_global_usd_liquidity()
            confidence = usd_liq.get("confidence")
            if confidence is not None:
                # confidence is a 0-1 score; treat as proxy for dxy_trend
                # higher USD liquidity confidence → lower DXY pressure (gold bullish)
                # map to a signed value: confidence > 0.5 → negative dxy_trend
                indicators["dxy_trend"] = float(confidence - 0.5)

        elif pool == "commodities":
            macro = get_macro_liquidity()
            dim_scores = macro.get("dimension_scores", {})
            copper_gold_score = dim_scores.get("copper_gold")
            crude_oil_score = dim_scores.get("crude_oil")
            # dimension_scores are risk scores (0=safe, 100=danger)
            # invert to a -50..+50 range for directional indicator
            if copper_gold_score is not None:
                indicators["copper_gold_ratio"] = float(50 - copper_gold_score)
            if crude_oil_score is not None:
                indicators["crude_oil_trend"] = float(50 - crude_oil_score)

    except Exception as exc:
        logger.warning("get_regime(%s): indicator fetch failed — %s", pool, exc)

    # Classify using RegimeDetector
    try:
        detector = _get_regime_detector()
        state = detector.classify_pool(pool, indicators)
        return _regime_state_to_dict(state)
    except Exception as exc:
        logger.error("get_regime(%s): classify_pool failed — %s", pool, exc)
        # Return a neutral fallback
        return {
            "pool": pool,
            "regime": "transition",
            "confidence": 0.0,
            "days_since_change": 0,
            "drivers": [f"Classification error: {exc}"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


@st.cache_data(ttl=3600, show_spinner=False)
def get_all_regimes() -> Dict[str, Dict[str, Any]]:
    """
    Classify regimes for all four asset pools.

    Returns
    -------
    dict
        Mapping of pool name → regime dict (same schema as get_regime()).
    """
    pools = ("a_shares", "us_stocks", "gold", "commodities")
    return {pool: get_regime(pool) for pool in pools}


@st.cache_data(ttl=3600, show_spinner=False)
def get_dashboard_verdict() -> Dict[str, Any]:
    """
    Compute the full dashboard verdict across all four asset pools.

    Gets all regimes, converts them to RegimeState objects, then calls
    VerdictEngine.compute_dashboard_verdict() with empty signals for now.

    Returns
    -------
    dict with keys: overall_stance, pool_verdicts (list), updated_at
    """
    from quant.analysis.regime.regime_detector import RegimeState

    all_regimes = get_all_regimes()

    # Convert dicts back to RegimeState objects for VerdictEngine
    regime_states: Dict[str, RegimeState] = {}
    for pool, regime_dict in all_regimes.items():
        try:
            regime_states[pool] = RegimeState(
                pool=regime_dict["pool"],
                regime=regime_dict["regime"],
                confidence=float(regime_dict["confidence"]),
                days_since_change=int(regime_dict["days_since_change"]),
                drivers=list(regime_dict["drivers"]),
                updated_at=regime_dict["updated_at"],
            )
        except Exception as exc:
            logger.warning(
                "get_dashboard_verdict: could not reconstruct RegimeState for %s — %s",
                pool,
                exc,
            )

    try:
        engine = _get_verdict_engine()
        dashboard = engine.compute_dashboard_verdict(
            regimes=regime_states,
            signals_by_pool={},
            transmissions_by_pool={},
            all_transmissions=[],
        )

        return {
            "overall_stance": dashboard.overall_stance,
            "pool_verdicts": [_pool_verdict_to_dict(v) for v in dashboard.pool_verdicts],
            "updated_at": dashboard.updated_at,
        }
    except Exception as exc:
        logger.error("get_dashboard_verdict: VerdictEngine failed — %s", exc)
        return {
            "overall_stance": "neutral",
            "pool_verdicts": [
                {
                    "pool": pool,
                    "action": "hold",
                    "confidence": "low",
                    "reasoning": [f"Verdict engine error: {exc}"],
                    "regime": all_regimes.get(
                        pool,
                        {
                            "pool": pool,
                            "regime": "transition",
                            "confidence": 0.0,
                            "days_since_change": 0,
                            "drivers": [],
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        },
                    ),
                }
                for pool in ("a_shares", "us_stocks", "gold", "commodities")
            ],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


@st.cache_data(ttl=1800, show_spinner=False)
def get_active_transmissions() -> List[Dict[str, Any]]:
    """
    Return currently active cross-asset transmissions.

    Queries TransmissionGraph.get_active_transmissions() and converts each
    ActiveTransmission to a JSON-serialisable dict.

    Returns
    -------
    list of dicts, each containing edge info plus transmission state
    """
    try:
        graph = _get_transmission_graph()
        transmissions = graph.get_active_transmissions()
        return [_active_transmission_to_dict(tx) for tx in transmissions]
    except Exception as exc:
        logger.error("get_active_transmissions: failed — %s", exc)
        return []
