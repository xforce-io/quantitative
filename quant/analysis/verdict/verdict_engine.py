#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VerdictEngine — synthesizes regime + signals + transmissions into actionable verdicts.

Consumes:
  - RegimeState per pool (from RegimeDetector)
  - List[ActiveSignal] per pool (from signal analyzers)
  - List[ActiveTransmission] per pool / globally (from TransmissionGraph)

Produces:
  - PoolVerdict    per asset pool
  - PositionAlert  per held position
  - DashboardVerdict  combining all of the above
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from quant.analysis.regime.regime_detector import (
    NEGATIVE_REGIMES as _NEGATIVE_REGIMES,
    POSITIVE_REGIMES as _POSITIVE_REGIMES,
    RegimeState,
)
from quant.analysis.signals.signal_registry import ActiveSignal
from quant.analysis.transmission.transmission_graph import ActiveTransmission


# ---------------------------------------------------------------------------
# Regime classification helpers
# ---------------------------------------------------------------------------

# Sort order for position alert urgency
_ALERT_URGENCY = {"consider selling": 0, "add on dip": 1, "watch": 2, "hold": 3}


def _is_negative_regime(regime: str) -> bool:
    return regime in _NEGATIVE_REGIMES


def _is_positive_regime(regime: str) -> bool:
    return regime in _POSITIVE_REGIMES


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PoolVerdict:
    """Actionable verdict for a single asset pool."""

    pool: str
    action: str                                # "add" | "hold" | "reduce" | "avoid"
    confidence: str                            # "high" | "medium" | "low"
    reasoning: List[str]
    active_signals: List[ActiveSignal]
    active_transmissions: List[ActiveTransmission]
    regime: RegimeState


@dataclass
class PositionAlert:
    """Actionable alert for a specific held position."""

    symbol: str
    name: str
    pool: str
    action: str                                # "consider selling" | "add on dip" | "watch" | "hold"
    signals: List[ActiveSignal]
    reasoning: str


@dataclass
class DashboardVerdict:
    """Top-level synthesized verdict across all pools."""

    overall_stance: str                        # "aggressive" | "neutral" | "cautious" | "defensive"
    pool_verdicts: List[PoolVerdict]
    position_alerts: List[PositionAlert]
    transmission_alerts: List[ActiveTransmission]
    updated_at: str


# ---------------------------------------------------------------------------
# VerdictEngine
# ---------------------------------------------------------------------------

_POOLS = ("a_shares", "us_stocks", "gold", "commodities")


class VerdictEngine:
    """Synthesizes regime, signals, and transmissions into actionable verdicts."""

    # ------------------------------------------------------------------
    # Pool-level verdict
    # ------------------------------------------------------------------

    def compute_pool_verdict(
        self,
        pool: str,
        regime: RegimeState,
        signals: List[ActiveSignal],
        transmissions: List[ActiveTransmission],
    ) -> PoolVerdict:
        """
        Compute an actionable verdict for a single asset pool.

        Logic:
        1. Accumulate weighted bullish / bearish scores from signals.
           Weight = signal.validation.hit_rate (or 0.5 if no validation).
        2. Apply regime influence:
           - Negative regime  → add 0.3 * regime.confidence to bearish_weight
           - Positive regime  → add 0.3 * regime.confidence to bullish_weight
        3. Determine action:
           - No signals at all (before regime boost) → "hold", confidence "low"
           - bullish_weight > bearish_weight * 1.3   → "add"
           - bearish_weight > bullish_weight * 1.3   → "reduce"
           - Otherwise                               → "hold"
        4. Determine confidence:
           - "high"   if winning weight > 2x loser weight
           - "medium" if clear winner (any directional action)
           - "low"    for hold / no signals
        5. Build human-readable reasoning lines.
        """
        reasoning: List[str] = []

        # --- Step 1: raw signal weights ---
        raw_bullish = 0.0
        raw_bearish = 0.0
        has_signals = bool(signals)

        for sig in signals:
            hit_rate = sig.validation.hit_rate if sig.validation else 0.5
            if sig.action in ("add", "watch"):
                raw_bullish += hit_rate
            elif sig.action in ("reduce", "avoid"):
                raw_bearish += hit_rate

        bullish_weight = raw_bullish
        bearish_weight = raw_bearish

        # --- Step 2: regime influence ---
        regime_label = regime.regime
        regime_conf = regime.confidence

        if _is_negative_regime(regime_label):
            bearish_weight += 0.3 * regime_conf
            reasoning.append(
                f"Regime is {regime_label} (confidence {regime_conf:.0%}), biasing bearish"
            )
        elif _is_positive_regime(regime_label):
            bullish_weight += 0.3 * regime_conf
            reasoning.append(
                f"Regime is {regime_label} (confidence {regime_conf:.0%}), biasing bullish"
            )
        else:
            reasoning.append(f"Regime is {regime_label} (confidence {regime_conf:.0%}), neutral")

        # --- Step 3: signal reasoning ---
        for sig in signals:
            hr = sig.validation.hit_rate if sig.validation else None
            hr_str = f"{hr:.2f}" if hr is not None else "n/a"
            direction = "bearish" if sig.action in ("reduce", "avoid") else "bullish"
            reasoning.append(
                f"Signal '{sig.definition.name}' ({direction}, hit rate {hr_str}): {sig.reasoning}"
            )

        # --- Step 4: transmission reasoning ---
        for tx in transmissions:
            reasoning.append(
                f"Active transmission: {tx.edge.source} → {tx.edge.target} "
                f"({tx.expected_target}, {tx.days_remaining}d remaining)"
            )

        # --- Step 5: determine action & confidence ---
        if not has_signals:
            # No raw signals → hold with low confidence regardless of regime boost
            action = "hold"
            confidence = "low"
        elif bullish_weight > bearish_weight * 1.3:
            action = "add"
            if bullish_weight > bearish_weight * 2 or bearish_weight == 0:
                confidence = "high"
            else:
                confidence = "medium"
        elif bearish_weight > bullish_weight * 1.3:
            action = "reduce"
            if bearish_weight > bullish_weight * 2 or bullish_weight == 0:
                confidence = "high"
            else:
                confidence = "medium"
        else:
            action = "hold"
            confidence = "low"

        return PoolVerdict(
            pool=pool,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            active_signals=signals,
            active_transmissions=transmissions,
            regime=regime,
        )

    # ------------------------------------------------------------------
    # Dashboard verdict
    # ------------------------------------------------------------------

    def compute_dashboard_verdict(
        self,
        regimes: Dict[str, RegimeState],
        signals_by_pool: Dict[str, List[ActiveSignal]],
        transmissions_by_pool: Dict[str, List[ActiveTransmission]],
        all_transmissions: List[ActiveTransmission],
    ) -> DashboardVerdict:
        """
        Compute a full dashboard verdict covering all four asset pools.

        Overall stance:
          - 3+ pools "reduce" / "avoid"  → "defensive"
          - 2+ pools "reduce"            → "cautious"
          - 3+ pools "add"               → "aggressive"
          - Otherwise                    → "neutral"
        """
        pool_verdicts: List[PoolVerdict] = []

        for pool in _POOLS:
            regime = regimes.get(pool)
            if regime is None:
                # Synthesise a neutral fallback so we always produce 4 verdicts
                regime = RegimeState(
                    pool=pool,
                    regime="transition",
                    confidence=0.0,
                    days_since_change=0,
                    drivers=[],
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
            signals = signals_by_pool.get(pool, [])
            transmissions = transmissions_by_pool.get(pool, [])
            verdict = self.compute_pool_verdict(pool, regime, signals, transmissions)
            pool_verdicts.append(verdict)

        # Overall stance logic
        reduce_count = sum(
            1 for v in pool_verdicts if v.action in ("reduce", "avoid")
        )
        add_count = sum(1 for v in pool_verdicts if v.action == "add")

        if reduce_count >= 3:
            overall_stance = "defensive"
        elif reduce_count >= 2:
            overall_stance = "cautious"
        elif add_count >= 3:
            overall_stance = "aggressive"
        else:
            overall_stance = "neutral"

        return DashboardVerdict(
            overall_stance=overall_stance,
            pool_verdicts=pool_verdicts,
            position_alerts=[],          # filled by caller via compute_position_alerts
            transmission_alerts=all_transmissions,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Position alerts
    # ------------------------------------------------------------------

    def compute_position_alerts(
        self,
        positions: List[Dict],
        regimes: Dict[str, RegimeState],
        signals_by_pool: Dict[str, List[ActiveSignal]],
    ) -> List[PositionAlert]:
        """
        Generate actionable alerts for a list of held positions.

        Each position dict must have keys: symbol, name, pool.

        Signal matching:
          - A signal matches a position if signal.symbol == position["symbol"]
            OR signal.symbol is None (pool-level macro signal).

        Action logic per position:
          - Bearish majority (or bearish + negative regime) → "consider selling"
          - Bullish majority and regime NOT negative         → "add on dip"
          - Otherwise                                        → "watch"

        Returns alerts sorted by urgency:
          "consider selling" → "add on dip" → "watch"
        """
        alerts: List[PositionAlert] = []

        for pos in positions:
            symbol: str = pos["symbol"]
            name: str = pos["name"]
            pool: str = pos["pool"]

            pool_signals = signals_by_pool.get(pool, [])
            regime = regimes.get(pool)

            # Filter signals relevant to this position
            relevant_signals = [
                s for s in pool_signals
                if s.symbol is None or s.symbol == symbol
            ]

            bullish_count = sum(
                1 for s in relevant_signals if s.action in ("add", "watch")
            )
            bearish_count = sum(
                1 for s in relevant_signals if s.action in ("reduce", "avoid")
            )
            regime_negative = regime is not None and _is_negative_regime(regime.regime)

            # Determine action
            if (bearish_count > bullish_count) or (bearish_count > 0 and regime_negative):
                action = "consider selling"
            elif bullish_count > bearish_count and not regime_negative:
                action = "add on dip"
            else:
                action = "watch"

            # Build reasoning
            reasoning_parts: List[str] = []
            if regime:
                reasoning_parts.append(f"Regime: {regime.regime}")
            for sig in relevant_signals:
                direction = "bearish" if sig.action in ("reduce", "avoid") else "bullish"
                reasoning_parts.append(
                    f"{direction.capitalize()} signal '{sig.definition.name}': {sig.reasoning}"
                )
            if not reasoning_parts:
                reasoning_parts.append("No active signals for this position")

            alerts.append(
                PositionAlert(
                    symbol=symbol,
                    name=name,
                    pool=pool,
                    action=action,
                    signals=relevant_signals,
                    reasoning="; ".join(reasoning_parts),
                )
            )

        # Sort by urgency: consider selling → add on dip → watch
        alerts.sort(key=lambda a: _ALERT_URGENCY.get(a.action, 99))

        return alerts
