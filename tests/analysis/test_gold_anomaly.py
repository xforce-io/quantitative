"""Unit tests for gold anomaly detection dimension."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


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


class TestEarlyWarningScoring:
    """Test the early warning layer scoring logic using synthetic data."""

    def _make_analyzer(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import MacroLiquidityAnalyzer
        return MacroLiquidityAnalyzer.__new__(MacroLiquidityAnalyzer)

    def _make_gold_series(self, prices: list) -> pd.Series:
        """Create a gold price series with DatetimeIndex."""
        dates = pd.bdate_range(end=datetime.now(), periods=len(prices))
        return pd.Series(prices, index=dates, name='Close')

    def test_consecutive_down_3_days(self):
        """3 consecutive down days should score +15."""
        analyzer = self._make_analyzer()
        prices = [100.0] * 22 + [99.0, 98.0, 97.0]
        gold_close = self._make_gold_series(prices)
        result = analyzer._calc_early_warning(gold_close)
        assert result['consecutive_down'] is True
        assert result['score'] >= 15

    def test_no_consecutive_down(self):
        """Alternating up/down should not trigger consecutive down signal."""
        analyzer = self._make_analyzer()
        prices = [100.0] * 22 + [99.0, 100.0, 99.0]
        gold_close = self._make_gold_series(prices)
        result = analyzer._calc_early_warning(gold_close)
        assert result['consecutive_down'] is False

    def test_ma20_crossover(self):
        """Price crossing below MA20 for the first time should score +15."""
        analyzer = self._make_analyzer()
        prices = [100.0] * 20 + [101.0, 95.0]
        gold_close = self._make_gold_series(prices)
        result = analyzer._calc_early_warning(gold_close)
        assert result['below_ma20'] is True
        assert result['score'] >= 15

    def test_ma20_already_below_no_trigger(self):
        """Already below MA20 for multiple days should NOT trigger MA20 signal."""
        analyzer = self._make_analyzer()
        prices = list(np.linspace(100, 80, 25))
        gold_close = self._make_gold_series(prices)
        result = analyzer._calc_early_warning(gold_close)
        assert result['below_ma20'] is False

    def test_rsi_weak(self):
        """RSI below 40 should score +10."""
        analyzer = self._make_analyzer()
        prices = [100.0] * 10 + [100 - i * 2 for i in range(15)]
        gold_close = self._make_gold_series(prices)
        result = analyzer._calc_early_warning(gold_close)
        assert result['rsi_weak'] is True
        assert result['rsi'] < 40

    def test_triple_resonance(self):
        """All 3 early warning signals should produce triple_resonance=True and score=40."""
        analyzer = self._make_analyzer()
        prices = [100.0] * 20 + [96.0, 92.0, 88.0, 84.0, 80.0]
        gold_close = self._make_gold_series(prices)
        result = analyzer._calc_early_warning(gold_close)
        assert result['triple_resonance'] is True
        assert result['score'] == 40


class TestConfirmationScoring:
    """Test the confirmation layer scoring logic."""

    def _make_analyzer(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import MacroLiquidityAnalyzer
        return MacroLiquidityAnalyzer.__new__(MacroLiquidityAnalyzer)

    def test_weekly_drop_severe(self):
        """Weekly drop > 5% should score 40."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-6.0,
            usd_weekly_change_pct=1.0,
            real_yield_weekly_change_bp=5.0,
        )
        assert result['weekly_drop'] is True
        assert result['score'] >= 40

    def test_weekly_drop_moderate(self):
        """Weekly drop 3-5% should score 25."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-4.0,
            usd_weekly_change_pct=2.0,
            real_yield_weekly_change_bp=0.0,
        )
        assert result['weekly_drop'] is True
        assert result['score'] == 25

    def test_weekly_drop_mild(self):
        """Weekly drop 1-3% should score 10 (no weekly_drop flag)."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-1.5,
            usd_weekly_change_pct=0.0,
            real_yield_weekly_change_bp=0.0,
        )
        assert result['weekly_drop'] is False
        assert result['score'] == 10

    def test_gold_usd_divergence(self):
        """Gold down >2% + USD not up should score +10."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-3.0,
            usd_weekly_change_pct=-0.5,
            real_yield_weekly_change_bp=0.0,
        )
        assert result['gold_usd_divergence'] is True
        assert result['score'] == 25 + 10

    def test_no_divergence_when_usd_strong(self):
        """Gold down but USD up strongly should NOT trigger divergence."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-3.0,
            usd_weekly_change_pct=1.5,
            real_yield_weekly_change_bp=0.0,
        )
        assert result['gold_usd_divergence'] is False

    def test_real_yield_spike(self):
        """Real yield spike > 30bp should score +10."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-1.0,
            usd_weekly_change_pct=0.0,
            real_yield_weekly_change_bp=35.0,
        )
        assert result['real_rate_spike'] is True
        assert result['score'] >= 10

    def test_real_yield_spike_moderate(self):
        """Real yield spike 15-30bp should score +5."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=0.5,
            usd_weekly_change_pct=0.0,
            real_yield_weekly_change_bp=20.0,
        )
        assert result['real_rate_spike'] is True
        assert result['score'] == 5

    def test_risk_score_capped_at_60(self):
        """Confirmation score should be capped at 60."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-6.0,
            usd_weekly_change_pct=-1.0,
            real_yield_weekly_change_bp=35.0,
        )
        assert result['score'] == 60

    def test_no_signals(self):
        """No trigger conditions should score 0."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=0.5,
            usd_weekly_change_pct=0.0,
            real_yield_weekly_change_bp=0.0,
        )
        assert result['score'] == 0

    def test_confirmation_with_none_usd(self):
        """Missing USD data should skip divergence signal."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-4.0,
            usd_weekly_change_pct=None,
            real_yield_weekly_change_bp=None,
        )
        assert result['gold_usd_divergence'] is False
        assert result['real_rate_spike'] is False
        assert result['score'] == 25
