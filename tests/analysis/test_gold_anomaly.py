"""Unit tests for gold anomaly detection dimension."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestGoldAnomalyConstants:
    """Verify weight and threshold constants."""

    def test_dimension_weights_sum_to_one(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import DIMENSION_WEIGHTS
        assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9

    def test_gold_dimension_weight_exists(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import DIMENSION_WEIGHTS
        assert 'gold' in DIMENSION_WEIGHTS
        assert DIMENSION_WEIGHTS['gold'] == 0.15

    def test_gold_thresholds_exist(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import THRESHOLDS
        assert 'gold_weekly_drop_pct' in THRESHOLDS
        assert 'gold_weekly_drop_severe_pct' in THRESHOLDS
        assert 'gold_consecutive_down_days' in THRESHOLDS
        assert 'gold_rsi_weak' in THRESHOLDS
        assert 'gold_usd_divergence_gold_drop' in THRESHOLDS
        assert 'gold_usd_divergence_usd_max' in THRESHOLDS
        assert 'real_yield_spike_bp' in THRESHOLDS
        assert 'real_yield_spike_moderate_bp' in THRESHOLDS
