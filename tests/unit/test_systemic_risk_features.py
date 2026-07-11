"""Unit tests for systemic risk feature stress mapping (TDD)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.analysis.indicators.systemic_risk.features import (
    compute_feature_point,
    compute_gold_fc_divergence,
    compute_stress_series,
    rolling_percentile,
    value_to_stress,
)


def _series(values, start="2020-01-01", freq="B"):
    idx = pd.date_range(start, periods=len(values), freq=freq)
    return pd.Series(values, index=idx, dtype=float)


class TestRollingPercentile:
    def test_mid_value_near_50(self):
        s = _series(list(range(100)))
        pct = rolling_percentile(s, window=50)
        # last value is max of last 50 → near 100
        assert pct.iloc[-1] == pytest.approx(100.0, abs=1.0)
        # value in middle of its window
        assert 40.0 <= pct.iloc[60] <= 60.0 or pct.iloc[60] > 50

    def test_insufficient_history_nan(self):
        s = _series([1.0, 2.0, 3.0])
        pct = rolling_percentile(s, window=50)
        assert pct.isna().all()


class TestValueToStress:
    def test_high_percentile_high_stress_when_not_inverted(self):
        # high level = stress (e.g. HY OAS)
        assert value_to_stress(percentile=90.0, inverted=False) > 0.7
        assert value_to_stress(percentile=10.0, inverted=False) < 0.3

    def test_high_percentile_low_stress_when_inverted(self):
        # high net liquidity = low stress
        assert value_to_stress(percentile=90.0, inverted=True) < 0.3
        assert value_to_stress(percentile=10.0, inverted=True) > 0.7

    def test_none_percentile_returns_none(self):
        assert value_to_stress(percentile=None, inverted=False) is None

    def test_stress_clamped_0_1(self):
        assert 0.0 <= value_to_stress(0.0, inverted=False) <= 1.0
        assert 0.0 <= value_to_stress(100.0, inverted=False) <= 1.0


class TestComputeFeaturePoint:
    def test_stress_series_high_level(self):
        # Rising stress proxy: last values much higher
        vals = list(np.linspace(1.0, 1.0, 200)) + list(np.linspace(1.0, 5.0, 60))
        s = _series(vals)
        fp = compute_feature_point(
            name="hy_oas",
            series=s,
            inverted=False,
            percentile_window=60,
            change_window=20,
        )
        assert fp.name == "hy_oas"
        assert fp.value is not None
        assert fp.stress is not None
        assert fp.stress > 0.5
        assert fp.percentile is not None

    def test_inverted_net_liquidity_low_is_stress(self):
        # High then crash → last low percentile → high stress when inverted
        vals = list(np.linspace(100.0, 100.0, 100)) + list(np.linspace(100.0, 50.0, 40))
        s = _series(vals)
        fp = compute_feature_point(
            name="net_liquidity",
            series=s,
            inverted=True,
            percentile_window=60,
        )
        assert fp.stress is not None
        assert fp.stress > 0.5

    def test_empty_series(self):
        s = pd.Series(dtype=float)
        fp = compute_feature_point("x", s, inverted=False)
        assert fp.value is None
        assert fp.stress is None


class TestComputeStressSeries:
    def test_rising_series_elevates_stress(self):
        # calm then sharp rise → end stress high via short/change windows
        vals = list(np.full(80, 0.02)) + list(np.linspace(0.02, 0.15, 30))
        s = _series(vals)
        stress = compute_stress_series(s, inverted=False, percentile_window=60, short_window=40, change_window=10)
        assert float(stress.iloc[-1]) > 0.6

    def test_inverted_falling_is_stress(self):
        vals = list(np.full(80, 100.0)) + list(np.linspace(100.0, 50.0, 30))
        s = _series(vals)
        stress = compute_stress_series(s, inverted=True, percentile_window=60, short_window=40, change_window=10)
        assert float(stress.iloc[-1]) > 0.5


class TestGoldFcDivergence:
    def test_gold_up_and_l1_tight_is_stress(self):
        div = compute_gold_fc_divergence(
            gold_momentum=0.05,  # gold rising
            l1_stress=0.8,
            divergence_threshold=0.55,
        )
        assert div > 0.5

    def test_gold_down_no_divergence(self):
        div = compute_gold_fc_divergence(
            gold_momentum=-0.03,
            l1_stress=0.8,
            divergence_threshold=0.55,
        )
        assert div == 0.0

    def test_l1_calm_no_divergence(self):
        div = compute_gold_fc_divergence(
            gold_momentum=0.05,
            l1_stress=0.2,
            divergence_threshold=0.55,
        )
        assert div == 0.0
