#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for SignalRegistry module.
Tests written first (TDD), covering all classes and edge cases.
"""

import json
import os
import tempfile
from typing import Optional

import pytest

from quant.analysis.signals.signal_registry import (
    ActiveSignal,
    SignalDefinition,
    SignalRegistry,
    SignalValidation,
)


class TestSignalDefinition:
    def test_creation(self):
        sig = SignalDefinition(
            name="rsi_oversold_bounce",
            asset_pools=["a_shares"],
            signal_type="mean_reversion",
            source_analyzer="TechnicalAnalyzer",
            lookback_days=60,
            condition="RSI < 30",
            condition_description="RSI drops below 30 (oversold territory)",
            regime_filter={"a_shares": ["risk-on", "transition"]},
            forward_days=5,
        )
        assert sig.name == "rsi_oversold_bounce"
        assert sig.asset_pools == ["a_shares"]
        assert sig.signal_type == "mean_reversion"
        assert sig.source_analyzer == "TechnicalAnalyzer"
        assert sig.lookback_days == 60
        assert sig.condition == "RSI < 30"
        assert sig.condition_description == "RSI drops below 30 (oversold territory)"
        assert sig.regime_filter == {"a_shares": ["risk-on", "transition"]}
        assert sig.forward_days == 5

    def test_forward_days_default(self):
        sig = SignalDefinition(
            name="test",
            asset_pools=["a_shares"],
            signal_type="macro",
            source_analyzer="SomeAnalyzer",
            lookback_days=30,
            condition="x > 1",
            condition_description="x is above 1",
            regime_filter={},
        )
        assert sig.forward_days == 5


class TestSignalValidation:
    def test_is_valid_above_threshold(self):
        val = SignalValidation(
            hit_rate=0.65,
            avg_return=0.03,
            sample_size=100,
            validated_date="2026-04-01",
            regime_hit_rates={"risk-on": 0.72, "risk-off": 0.38},
        )
        assert val.is_valid() is True
        assert val.is_valid(min_hit_rate=0.55) is True

    def test_is_valid_below_threshold(self):
        val = SignalValidation(
            hit_rate=0.45,
            avg_return=-0.01,
            sample_size=50,
            validated_date="2026-04-01",
            regime_hit_rates={},
        )
        assert val.is_valid() is False
        assert val.is_valid(min_hit_rate=0.55) is False

    def test_is_valid_at_threshold(self):
        val = SignalValidation(
            hit_rate=0.55,
            avg_return=0.0,
            sample_size=80,
            validated_date="2026-04-01",
            regime_hit_rates={},
        )
        assert val.is_valid() is True

    def test_hit_rate_for_regime_known(self):
        val = SignalValidation(
            hit_rate=0.60,
            avg_return=0.02,
            sample_size=100,
            validated_date="2026-04-01",
            regime_hit_rates={"risk-on": 0.72, "risk-off": 0.38},
        )
        assert val.hit_rate_for_regime("risk-on") == 0.72
        assert val.hit_rate_for_regime("risk-off") == 0.38

    def test_hit_rate_for_regime_unknown_falls_back(self):
        val = SignalValidation(
            hit_rate=0.60,
            avg_return=0.02,
            sample_size=100,
            validated_date="2026-04-01",
            regime_hit_rates={"risk-on": 0.72},
        )
        # Unknown regime "transition" → fall back to overall hit_rate
        assert val.hit_rate_for_regime("transition") == 0.60
        assert val.hit_rate_for_regime("nonexistent") == 0.60

    def test_hit_rate_for_regime_empty_dict_fallback(self):
        val = SignalValidation(
            hit_rate=0.58,
            avg_return=0.01,
            sample_size=40,
            validated_date="2026-04-01",
            regime_hit_rates={},
        )
        assert val.hit_rate_for_regime("risk-on") == 0.58


class TestSignalRegistry:
    def setup_method(self):
        self.registry = SignalRegistry()

    def test_loads_signals_from_config(self):
        assert len(self.registry.definitions) > 0
        names = [s.name for s in self.registry.definitions]
        assert "rsi_oversold_bounce" in names

    def test_definitions_are_signal_definition_instances(self):
        for defn in self.registry.definitions:
            assert isinstance(defn, SignalDefinition)

    def test_all_12_signals_loaded(self):
        assert len(self.registry.definitions) == 12

    def test_get_signals_for_pool_a_shares(self):
        signals = self.registry.get_signals_for_pool("a_shares")
        assert len(signals) > 0
        for sig in signals:
            assert "a_shares" in sig.asset_pools

    def test_get_signals_for_pool_us_stocks(self):
        signals = self.registry.get_signals_for_pool("us_stocks")
        assert len(signals) > 0
        for sig in signals:
            assert "us_stocks" in sig.asset_pools

    def test_get_signals_for_pool_unknown(self):
        signals = self.registry.get_signals_for_pool("crypto")
        assert signals == []

    def test_get_signals_for_pool_and_regime_risk_off(self):
        # In risk-off for a_shares:
        # - rsi_oversold_bounce has regime_filter {"a_shares": ["risk-on", "transition"]} → excluded
        # - rsi_overbought_warning has regime_filter {"a_shares": ["risk-on", "transition", "risk-off"]} → included
        signals = self.registry.get_signals_for_pool_and_regime("a_shares", "risk-off")
        names = [s.name for s in signals]
        assert "rsi_overbought_warning" in names
        assert "rsi_oversold_bounce" not in names

    def test_get_signals_for_pool_and_regime_empty_filter_always_included(self):
        # margin_debt_acceleration has regime_filter: {} → always active for a_shares
        signals = self.registry.get_signals_for_pool_and_regime("a_shares", "risk-off")
        names = [s.name for s in signals]
        assert "margin_debt_acceleration" in names

    def test_get_signals_for_pool_and_regime_filter_not_for_pool(self):
        # vix_spike has asset_pools: [us_stocks, gold], regime_filter: {}
        # For us_stocks risk-off regime → should be included (no regime restriction)
        signals = self.registry.get_signals_for_pool_and_regime("us_stocks", "risk-off")
        names = [s.name for s in signals]
        assert "vix_spike" in names

    def test_get_signals_for_pool_and_regime_risk_on(self):
        # rsi_oversold_bounce: regime_filter {"a_shares": ["risk-on", "transition"]}
        # In risk-on for a_shares → should be included
        signals = self.registry.get_signals_for_pool_and_regime("a_shares", "risk-on")
        names = [s.name for s in signals]
        assert "rsi_oversold_bounce" in names

    def test_get_signal_by_name_found(self):
        sig = self.registry.get_signal_by_name("vix_spike")
        assert sig is not None
        assert sig.name == "vix_spike"
        assert sig.signal_type == "macro"

    def test_get_signal_by_name_not_found(self):
        sig = self.registry.get_signal_by_name("nonexistent_signal")
        assert sig is None

    def test_set_and_get_validation(self):
        val = SignalValidation(
            hit_rate=0.68,
            avg_return=0.025,
            sample_size=150,
            validated_date="2026-04-10",
            regime_hit_rates={"risk-on": 0.75, "risk-off": 0.42},
        )
        self.registry.set_validation("rsi_oversold_bounce", val)
        retrieved = self.registry.get_validation("rsi_oversold_bounce")
        assert retrieved is not None
        assert retrieved.hit_rate == 0.68
        assert retrieved.sample_size == 150

    def test_get_validation_not_set_returns_none(self):
        result = self.registry.get_validation("rsi_oversold_bounce")
        assert result is None

    def test_min_hit_rate_from_config(self):
        assert self.registry.min_hit_rate == 0.55

    def test_load_validations_from_dir(self):
        val_data = {
            "signal_name": "rsi_oversold_bounce",
            "hit_rate": 0.65,
            "avg_return": 0.03,
            "sample_size": 120,
            "validated_date": "2026-04-01",
            "regime_hit_rates": {"risk-on": 0.72, "risk-off": 0.38},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "rsi_oversold_bounce.json")
            with open(filepath, "w") as f:
                json.dump(val_data, f)

            count = self.registry.load_validations_from_dir(tmpdir)

        assert count == 1
        retrieved = self.registry.get_validation("rsi_oversold_bounce")
        assert retrieved is not None
        assert retrieved.hit_rate == 0.65

    def test_load_validations_from_dir_skips_non_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a non-JSON file
            with open(os.path.join(tmpdir, "readme.txt"), "w") as f:
                f.write("not json")

            count = self.registry.load_validations_from_dir(tmpdir)

        assert count == 0

    def test_load_validations_from_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            count = self.registry.load_validations_from_dir(tmpdir)
        assert count == 0

    def test_custom_config_path(self):
        """Registry can be pointed at an explicit config path."""
        default_config = os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "signals.yaml"
        )
        registry2 = SignalRegistry(config_path=os.path.abspath(default_config))
        assert len(registry2.definitions) == 12


class TestActiveSignal:
    def test_creation(self):
        defn = SignalDefinition(
            name="vix_spike",
            asset_pools=["us_stocks", "gold"],
            signal_type="macro",
            source_analyzer="LeadingIndicatorsAnalyzer",
            lookback_days=30,
            condition="vix > 25 AND vix_5d_change > 5",
            condition_description="VIX spikes above 25 with rapid increase",
            regime_filter={},
            forward_days=5,
        )
        active = ActiveSignal(
            definition=defn,
            validation=None,
            fired_at="2026-04-12T10:00:00",
            symbol="SPY",
            action="reduce",
            reasoning="VIX spiked to 35, high volatility regime",
        )
        assert active.definition.name == "vix_spike"
        assert active.validation is None
        assert active.fired_at == "2026-04-12T10:00:00"
        assert active.symbol == "SPY"
        assert active.action == "reduce"
        assert "VIX spiked" in active.reasoning

    def test_creation_without_symbol(self):
        defn = SignalDefinition(
            name="vix_spike",
            asset_pools=["us_stocks"],
            signal_type="macro",
            source_analyzer="LeadingIndicatorsAnalyzer",
            lookback_days=30,
            condition="vix > 25",
            condition_description="VIX spikes",
            regime_filter={},
        )
        active = ActiveSignal(
            definition=defn,
            validation=None,
            fired_at="2026-04-12T10:00:00",
            symbol=None,
            action="watch",
            reasoning="Market risk elevated",
        )
        assert active.symbol is None
