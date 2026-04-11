"""Tests for MomentumDelta — pure computation, no API calls."""

import pandas as pd
import numpy as np
import pytest

from quant.analysis.indicators.momentum_delta import MomentumDelta


def _make_series(values: list, name: str = "test") -> pd.Series:
    """Helper: build a DatetimeIndex series from a list of values."""
    idx = pd.date_range("2026-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx, name=name)


class TestCompute:
    def test_rising_series_positive_velocity(self):
        s = _make_series([50 + 2 * i for i in range(10)])
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=5)
        assert result["velocity"] > 0
        assert result["status"] in ("accelerating_up", "decelerating_up", "stable")

    def test_falling_series_negative_velocity(self):
        s = _make_series([80 - 3 * i for i in range(10)])
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=5)
        assert result["velocity"] < 0

    def test_constant_series_stable(self):
        s = _make_series([50.0] * 20)
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=10)
        assert result["status"] == "stable"
        assert result["alert"] is None

    def test_acceleration_detects_speedup(self):
        s = _make_series([50 + i**2 * 0.5 for i in range(15)])
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=10)
        assert result["acceleration"] > 0

    def test_streak_counts_consecutive_days(self):
        values = [50.0] * 5 + [51, 52, 53, 54, 55]
        s = _make_series(values)
        result = MomentumDelta.compute(s, velocity_window=3, zscore_window=5)
        assert result["streak"] > 0

    def test_zscore_anomaly_generates_alert(self):
        values = [50.0] * 60 + [50, 52, 58, 70, 85]
        s = _make_series(values)
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=60)
        assert result["alert"] is not None
        assert "标准差" in result["alert"]

    def test_short_series_returns_safe_defaults(self):
        s = _make_series([50, 51])
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=60)
        assert result["velocity"] == 0.0
        assert result["status"] == "stable"

    def test_velocity_series_returned(self):
        s = _make_series([50 + i for i in range(20)])
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=10)
        assert isinstance(result["velocity_series"], pd.Series)
        assert len(result["velocity_series"]) == len(s)

    def test_status_accelerating_down(self):
        values = [80, 79, 77, 74, 70, 65, 59, 52, 44, 35]
        s = _make_series(values)
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=5)
        assert result["velocity"] < 0
        assert result["acceleration"] < 0


class TestComputeBatch:
    def test_batch_returns_dict_per_key(self):
        data = {
            "rsi": _make_series([50 + i for i in range(20)]),
            "volume": _make_series([1000 + i * 100 for i in range(20)]),
        }
        results = MomentumDelta.compute_batch(data)
        assert set(results.keys()) == {"rsi", "volume"}
        assert results["rsi"]["velocity"] > 0
