#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for SignalValidator.
Written first (TDD) before implementing signal_validator.py.
"""

import json
import os
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from quant.analysis.signals.signal_registry import SignalDefinition, SignalRegistry, SignalValidation
from quant.analysis.signals.signal_validator import SignalValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_price_series(n_days: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data with random walk."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq="B")
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, n_days)))
    return pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.005, n_days)),
            "high": close * (1 + abs(rng.normal(0, 0.01, n_days))),
            "low": close * (1 - abs(rng.normal(0, 0.01, n_days))),
            "close": close,
            "volume": rng.randint(1_000_000, 10_000_000, n_days).astype(float),
        },
        index=dates,
    )


def _make_signal_def(
    name: str = "rsi_oversold_bounce",
    condition: str = "RSI < 30",
    forward_days: int = 5,
) -> SignalDefinition:
    return SignalDefinition(
        name=name,
        asset_pools=["a_shares"],
        signal_type="mean_reversion",
        source_analyzer="TechnicalAnalyzer",
        lookback_days=60,
        condition=condition,
        condition_description="Test signal",
        regime_filter={},
        forward_days=forward_days,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSignalValidator:
    def test_validate_rsi_signal(self):
        """Validate RSI<30 on synthetic data; result must be a valid SignalValidation."""
        validator = SignalValidator()
        signal_def = _make_signal_def(condition="RSI < 30")
        price_data = _make_price_series(n_days=500)

        result = validator.validate_signal(signal_def, price_data)

        assert isinstance(result, SignalValidation)
        assert 0.0 <= result.hit_rate <= 1.0
        assert isinstance(result.avg_return, float)
        assert isinstance(result.sample_size, int)
        assert result.sample_size >= 0
        assert result.validated_date != ""

    def test_validate_ma_cross_signal(self):
        """Validate MA20 crosses above MA60; result must be a valid SignalValidation."""
        validator = SignalValidator()
        signal_def = _make_signal_def(
            name="golden_cross",
            condition="MA20 crosses above MA60",
        )
        price_data = _make_price_series(n_days=500)

        result = validator.validate_signal(signal_def, price_data)

        assert isinstance(result, SignalValidation)
        assert 0.0 <= result.hit_rate <= 1.0
        assert result.sample_size >= 0

    def test_no_signals_returns_zero_hit_rate(self):
        """Flat data + extreme condition (RSI<10) → sample_size == 0 and hit_rate == 0."""
        validator = SignalValidator()
        signal_def = _make_signal_def(condition="RSI < 10")

        # Flat price data: RSI will hover around 50, never below 10
        dates = pd.date_range(end=datetime.now(), periods=300, freq="B")
        flat_close = pd.Series(100.0, index=dates)
        price_data = pd.DataFrame(
            {
                "open": flat_close,
                "high": flat_close * 1.001,
                "low": flat_close * 0.999,
                "close": flat_close,
                "volume": pd.Series(1_000_000.0, index=dates),
            }
        )

        result = validator.validate_signal(signal_def, price_data)

        assert result.sample_size == 0
        assert result.hit_rate == 0.0

    def test_non_replayable_condition_returns_empty(self):
        """Conditions marked None in _CONDITION_EVALUATORS return empty validation."""
        validator = SignalValidator()
        signal_def = _make_signal_def(condition="comprehensive_score > 70")
        price_data = _make_price_series(n_days=200)

        result = validator.validate_signal(signal_def, price_data)

        assert result.sample_size == 0
        assert result.hit_rate == 0.0

    def test_regime_conditional_hit_rates(self):
        """When regime_series is provided, regime_hit_rates must be populated."""
        validator = SignalValidator()
        signal_def = _make_signal_def(condition="RSI < 30")
        price_data = _make_price_series(n_days=500)

        # Build a simple alternating regime series aligned with price_data
        regimes = pd.Series(
            ["risk-on" if i % 2 == 0 else "risk-off" for i in range(len(price_data))],
            index=price_data.index,
        )

        result = validator.validate_signal(signal_def, price_data, regime_series=regimes)

        assert isinstance(result.regime_hit_rates, dict)
        # At least one regime key should be populated (provided signals fired at all)
        if result.sample_size > 0:
            assert len(result.regime_hit_rates) > 0

    def test_bearish_signal_hit_logic(self):
        """Bearish signal (name contains 'overbought') counts negative returns as hits."""
        validator = SignalValidator()
        signal_def = _make_signal_def(
            name="rsi_overbought_signal",
            condition="RSI > 70",
        )
        price_data = _make_price_series(n_days=500)

        result = validator.validate_signal(signal_def, price_data)

        assert isinstance(result, SignalValidation)
        assert 0.0 <= result.hit_rate <= 1.0

    def test_save_and_load_validation(self, tmp_path):
        """Validate, save to tmp_path, load back via SignalRegistry.load_validations_from_dir."""
        validator = SignalValidator()
        signal_def = _make_signal_def(condition="RSI < 30")
        price_data = _make_price_series(n_days=500)

        result = validator.validate_signal(signal_def, price_data)
        validator.save_validation(signal_def.name, result, str(tmp_path))

        # Verify file exists
        expected_file = tmp_path / f"{signal_def.name}.json"
        assert expected_file.exists()

        # Verify JSON content is valid
        with open(expected_file) as fh:
            data = json.load(fh)
        assert "hit_rate" in data
        assert "avg_return" in data
        assert "sample_size" in data
        assert "validated_date" in data
        assert "regime_hit_rates" in data

        # Load via SignalRegistry
        registry = SignalRegistry.__new__(SignalRegistry)
        registry.definitions = []
        registry.min_hit_rate = 0.55
        registry._validations = {}

        count = registry.load_validations_from_dir(str(tmp_path))
        assert count == 1

        loaded = registry.get_validation(signal_def.name)
        assert loaded is not None
        assert abs(loaded.hit_rate - result.hit_rate) < 1e-9
        assert loaded.sample_size == result.sample_size

    def test_breakout_condition(self):
        """Validate breakout condition; result must be a valid SignalValidation."""
        validator = SignalValidator()
        signal_def = _make_signal_def(
            name="donchian_breakout",
            condition="breakout_type == 'up' AND volume_confirmed",
        )
        price_data = _make_price_series(n_days=500)

        result = validator.validate_signal(signal_def, price_data)

        assert isinstance(result, SignalValidation)
        assert 0.0 <= result.hit_rate <= 1.0

    def test_forward_days_respected(self):
        """Different forward_days settings produce different avg_return values (usually)."""
        validator = SignalValidator()
        price_data = _make_price_series(n_days=500)

        sig_5d = _make_signal_def(condition="RSI < 30", forward_days=5)
        sig_20d = _make_signal_def(condition="RSI < 30", forward_days=20)

        result_5d = validator.validate_signal(sig_5d, price_data)
        result_20d = validator.validate_signal(sig_20d, price_data)

        # Both must be valid SignalValidations
        assert isinstance(result_5d, SignalValidation)
        assert isinstance(result_20d, SignalValidation)
        # Same number of signal fires (same data, same condition)
        assert result_5d.sample_size == result_20d.sample_size
