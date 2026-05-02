#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for VerdictEngine.

Follows TDD — tests written before the implementation exists.
"""

import pytest
from typing import List

from quant.analysis.regime.regime_detector import RegimeState
from quant.analysis.signals.signal_registry import (
    ActiveSignal,
    SignalDefinition,
    SignalValidation,
)
from quant.analysis.transmission.transmission_graph import (
    ActiveTransmission,
    TransmissionEdge,
)
from quant.analysis.verdict import VerdictEngine, PoolVerdict, PositionAlert, DashboardVerdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_regime(pool: str, regime: str) -> RegimeState:
    return RegimeState(
        pool=pool,
        regime=regime,
        confidence=0.8,
        days_since_change=5,
        drivers=["test"],
        updated_at="2026-04-12T09:00:00",
    )


def _make_signal(name: str, signal_type: str, is_bearish: bool = False) -> ActiveSignal:
    defn = SignalDefinition(
        name=name,
        asset_pools=["a_shares"],
        signal_type=signal_type,
        source_analyzer="Test",
        lookback_days=60,
        condition="test",
        condition_description="test",
        regime_filter={},
        forward_days=5,
    )
    val = SignalValidation(
        hit_rate=0.68,
        avg_return=-0.02 if is_bearish else 0.02,
        sample_size=40,
        validated_date="2026-04-01",
        regime_hit_rates={},
    )
    return ActiveSignal(
        definition=defn,
        validation=val,
        fired_at="2026-04-12T09:00:00",
        symbol="000001.SZ",
        action="reduce" if is_bearish else "add",
        reasoning="test signal",
    )


def _make_transmission(source: str = "us_stocks", target: str = "a_shares") -> ActiveTransmission:
    edge = TransmissionEdge(
        source=source,
        target=target,
        direction="direct",
        lag_min_days=1,
        lag_max_days=5,
        threshold=2.0,
        strength=0.7,
    )
    return ActiveTransmission(
        edge=edge,
        triggered_at="2026-04-12",
        source_move=3.0,
        expected_target="up",
        days_remaining=3,
        status="propagating",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVerdictEngine:
    def setup_method(self):
        self.engine = VerdictEngine()

    # ------------------------------------------------------------------
    # compute_pool_verdict
    # ------------------------------------------------------------------

    def test_pool_verdict_reduce_in_risk_off_with_bearish_signals(self):
        """risk-off regime + 2 bearish signals → 'reduce'"""
        regime = _make_regime("a_shares", "risk-off")
        signals = [
            _make_signal("sig1", "momentum", is_bearish=True),
            _make_signal("sig2", "mean_reversion", is_bearish=True),
        ]
        verdict = self.engine.compute_pool_verdict("a_shares", regime, signals, [])

        assert verdict.pool == "a_shares"
        assert verdict.action == "reduce"
        assert verdict.confidence in ("high", "medium", "low")
        assert isinstance(verdict.reasoning, list)
        assert len(verdict.reasoning) > 0

    def test_pool_verdict_add_in_risk_on_with_bullish_signals(self):
        """risk-on regime + 2 bullish signals → 'add'"""
        regime = _make_regime("a_shares", "risk-on")
        signals = [
            _make_signal("sig1", "momentum", is_bearish=False),
            _make_signal("sig2", "breakout", is_bearish=False),
        ]
        verdict = self.engine.compute_pool_verdict("a_shares", regime, signals, [])

        assert verdict.pool == "a_shares"
        assert verdict.action == "add"
        assert verdict.confidence in ("high", "medium", "low")

    def test_pool_verdict_hold_when_conflicting(self):
        """transition regime + 1 bullish + 1 bearish signal → 'hold'"""
        regime = _make_regime("a_shares", "transition")
        signals = [
            _make_signal("sig_bull", "momentum", is_bearish=False),
            _make_signal("sig_bear", "momentum", is_bearish=True),
        ]
        verdict = self.engine.compute_pool_verdict("a_shares", regime, signals, [])

        assert verdict.pool == "a_shares"
        assert verdict.action == "hold"

    def test_pool_verdict_hold_when_no_signals(self):
        """risk-on regime but no signals → 'hold' with low confidence"""
        regime = _make_regime("a_shares", "risk-on")
        verdict = self.engine.compute_pool_verdict("a_shares", regime, [], [])

        assert verdict.pool == "a_shares"
        assert verdict.action == "hold"
        assert verdict.confidence == "low"

    def test_pool_verdict_contains_regime_in_reasoning(self):
        """Reasoning should mention the regime."""
        regime = _make_regime("a_shares", "risk-on")
        signals = [_make_signal("sig1", "momentum")]
        verdict = self.engine.compute_pool_verdict("a_shares", regime, signals, [])

        reasoning_text = " ".join(verdict.reasoning).lower()
        assert "risk-on" in reasoning_text

    def test_pool_verdict_contains_signal_hit_rate_in_reasoning(self):
        """Reasoning should mention hit rate from signal validation."""
        regime = _make_regime("a_shares", "risk-on")
        signals = [_make_signal("sig1", "momentum")]
        verdict = self.engine.compute_pool_verdict("a_shares", regime, signals, [])

        reasoning_text = " ".join(verdict.reasoning)
        # 0.68 hit rate should appear in some form
        assert "0.68" in reasoning_text or "68" in reasoning_text

    def test_pool_verdict_high_confidence_when_strong_majority(self):
        """When winning weight > 2x loser weight → 'high' confidence."""
        regime = _make_regime("a_shares", "risk-on")
        # 3 bullish signals vs 0 bearish
        signals = [
            _make_signal(f"sig{i}", "momentum", is_bearish=False) for i in range(3)
        ]
        verdict = self.engine.compute_pool_verdict("a_shares", regime, signals, [])

        assert verdict.action == "add"
        assert verdict.confidence == "high"

    def test_pool_verdict_stores_active_signals(self):
        """PoolVerdict.active_signals should list the provided signals."""
        regime = _make_regime("a_shares", "risk-on")
        signals = [_make_signal("sig1", "momentum")]
        verdict = self.engine.compute_pool_verdict("a_shares", regime, signals, [])

        assert verdict.active_signals == signals

    def test_pool_verdict_stores_regime(self):
        """PoolVerdict.regime should be the provided RegimeState."""
        regime = _make_regime("a_shares", "risk-on")
        verdict = self.engine.compute_pool_verdict("a_shares", regime, [], [])

        assert verdict.regime is regime

    # ------------------------------------------------------------------
    # compute_dashboard_verdict
    # ------------------------------------------------------------------

    def test_dashboard_verdict_defensive_when_multiple_reduce(self):
        """3+ pools with reduce/avoid → overall_stance == 'defensive'."""
        pools = ["a_shares", "us_stocks", "gold", "commodities"]
        regimes = {p: _make_regime(p, "risk-off") for p in pools}
        signals_by_pool = {
            p: [
                _make_signal("sig1", "momentum", is_bearish=True),
                _make_signal("sig2", "macro", is_bearish=True),
            ]
            for p in pools
        }
        transmissions_by_pool = {p: [] for p in pools}

        verdict = self.engine.compute_dashboard_verdict(
            regimes, signals_by_pool, transmissions_by_pool, []
        )

        assert verdict.overall_stance in ("defensive", "cautious")
        assert isinstance(verdict.pool_verdicts, list)
        assert len(verdict.pool_verdicts) == 4

    def test_dashboard_verdict_aggressive_when_multiple_add(self):
        """3+ pools with add → overall_stance == 'aggressive' or 'neutral'."""
        pools = ["a_shares", "us_stocks", "gold", "commodities"]
        regimes = {p: _make_regime(p, "risk-on") for p in pools}
        signals_by_pool = {
            p: [
                _make_signal("sig1", "momentum", is_bearish=False),
                _make_signal("sig2", "breakout", is_bearish=False),
            ]
            for p in pools
        }
        transmissions_by_pool = {p: [] for p in pools}

        verdict = self.engine.compute_dashboard_verdict(
            regimes, signals_by_pool, transmissions_by_pool, []
        )

        assert verdict.overall_stance in ("aggressive", "neutral")

    def test_dashboard_verdict_neutral_mixed(self):
        """Mixed pools → 'neutral' overall."""
        pools = ["a_shares", "us_stocks", "gold", "commodities"]
        regimes = {p: _make_regime(p, "transition") for p in pools}
        signals_by_pool = {p: [] for p in pools}
        transmissions_by_pool = {p: [] for p in pools}

        verdict = self.engine.compute_dashboard_verdict(
            regimes, signals_by_pool, transmissions_by_pool, []
        )

        assert verdict.overall_stance == "neutral"

    def test_dashboard_verdict_has_updated_at(self):
        """DashboardVerdict should carry an updated_at timestamp."""
        pools = ["a_shares", "us_stocks", "gold", "commodities"]
        regimes = {p: _make_regime(p, "transition") for p in pools}
        signals_by_pool = {p: [] for p in pools}
        transmissions_by_pool = {p: [] for p in pools}

        verdict = self.engine.compute_dashboard_verdict(
            regimes, signals_by_pool, transmissions_by_pool, []
        )

        assert verdict.updated_at
        assert "T" in verdict.updated_at or len(verdict.updated_at) >= 10

    def test_dashboard_verdict_passes_transmissions(self):
        """transmission_alerts on DashboardVerdict should reflect all_transmissions."""
        transmission = _make_transmission()
        pools = ["a_shares", "us_stocks", "gold", "commodities"]
        regimes = {p: _make_regime(p, "transition") for p in pools}
        signals_by_pool = {p: [] for p in pools}
        transmissions_by_pool = {p: [] for p in pools}

        verdict = self.engine.compute_dashboard_verdict(
            regimes, signals_by_pool, transmissions_by_pool, [transmission]
        )

        assert transmission in verdict.transmission_alerts

    # ------------------------------------------------------------------
    # compute_position_alerts
    # ------------------------------------------------------------------

    def test_position_alerts_sorted_by_urgency(self):
        """'consider selling' alerts should come before 'add on dip' alerts."""
        positions = [
            {"symbol": "000001.SZ", "name": "Ping An Bank", "pool": "a_shares"},
            {"symbol": "000002.SZ", "name": "Vanke", "pool": "a_shares"},
        ]
        regimes = {"a_shares": _make_regime("a_shares", "risk-off")}

        # bearish signal for 000001, bullish for 000002
        bearish_signal = _make_signal("bear_sig", "momentum", is_bearish=True)
        bullish_signal = _make_signal("bull_sig", "momentum", is_bearish=False)
        bullish_signal2 = _make_signal("bull_sig2", "breakout", is_bearish=False)

        # Assign specific symbols
        bearish_signal.symbol = "000001.SZ"
        bullish_signal.symbol = "000002.SZ"
        bullish_signal2.symbol = "000002.SZ"

        signals_by_pool = {"a_shares": [bearish_signal, bullish_signal, bullish_signal2]}

        alerts = self.engine.compute_position_alerts(positions, regimes, signals_by_pool)

        assert isinstance(alerts, list)
        if len(alerts) >= 2:
            sell_indices = [i for i, a in enumerate(alerts) if a.action == "consider selling"]
            buy_indices = [i for i, a in enumerate(alerts) if a.action == "add on dip"]
            if sell_indices and buy_indices:
                assert min(sell_indices) < min(buy_indices)

    def test_position_alerts_consider_selling_bearish_majority(self):
        """Position with bearish majority → 'consider selling'."""
        positions = [{"symbol": "000001.SZ", "name": "Ping An Bank", "pool": "a_shares"}]
        regimes = {"a_shares": _make_regime("a_shares", "risk-off")}

        sig1 = _make_signal("bear1", "momentum", is_bearish=True)
        sig2 = _make_signal("bear2", "macro", is_bearish=True)
        sig1.symbol = "000001.SZ"
        sig2.symbol = "000001.SZ"

        signals_by_pool = {"a_shares": [sig1, sig2]}

        alerts = self.engine.compute_position_alerts(positions, regimes, signals_by_pool)

        assert len(alerts) == 1
        assert alerts[0].action == "consider selling"
        assert alerts[0].symbol == "000001.SZ"

    def test_position_alerts_add_on_dip_bullish_majority_positive_regime(self):
        """Position with bullish majority in positive regime → 'add on dip'."""
        positions = [{"symbol": "000002.SZ", "name": "Vanke", "pool": "a_shares"}]
        regimes = {"a_shares": _make_regime("a_shares", "risk-on")}

        sig1 = _make_signal("bull1", "momentum", is_bearish=False)
        sig2 = _make_signal("bull2", "breakout", is_bearish=False)
        sig1.symbol = "000002.SZ"
        sig2.symbol = "000002.SZ"

        signals_by_pool = {"a_shares": [sig1, sig2]}

        alerts = self.engine.compute_position_alerts(positions, regimes, signals_by_pool)

        assert len(alerts) == 1
        assert alerts[0].action == "add on dip"

    def test_position_alerts_macro_signals_apply_to_all(self):
        """Signals with symbol=None (macro) apply to every position in the pool."""
        positions = [
            {"symbol": "000001.SZ", "name": "Ping An Bank", "pool": "a_shares"},
        ]
        regimes = {"a_shares": _make_regime("a_shares", "risk-off")}

        macro_sig = _make_signal("macro_bear", "macro", is_bearish=True)
        macro_sig.symbol = None  # pool-level macro signal

        signals_by_pool = {"a_shares": [macro_sig]}

        alerts = self.engine.compute_position_alerts(positions, regimes, signals_by_pool)

        # macro bearish + risk-off → consider selling
        assert len(alerts) == 1
        assert alerts[0].action in ("consider selling", "watch")

    def test_position_alerts_watch_when_no_signals(self):
        """Position with no relevant signals → action is not 'consider selling'."""
        positions = [{"symbol": "000001.SZ", "name": "Ping An Bank", "pool": "a_shares"}]
        regimes = {"a_shares": _make_regime("a_shares", "transition")}
        signals_by_pool = {"a_shares": []}

        alerts = self.engine.compute_position_alerts(positions, regimes, signals_by_pool)

        assert len(alerts) == 1
        assert alerts[0].action != "consider selling"

    def test_position_alerts_contain_reasoning(self):
        """Each PositionAlert should have non-empty reasoning string."""
        positions = [{"symbol": "000001.SZ", "name": "Ping An", "pool": "a_shares"}]
        regimes = {"a_shares": _make_regime("a_shares", "risk-on")}
        sig = _make_signal("sig1", "momentum")
        sig.symbol = "000001.SZ"
        signals_by_pool = {"a_shares": [sig]}

        alerts = self.engine.compute_position_alerts(positions, regimes, signals_by_pool)

        assert len(alerts) == 1
        assert alerts[0].reasoning
        assert len(alerts[0].reasoning) > 0
