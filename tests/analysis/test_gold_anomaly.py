"""Unit tests for gold anomaly detection dimension."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


class TestGoldAnomalyConstants:
    """Verify weight and threshold constants."""

    def test_dimension_weights_sum_to_one(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import DIMENSION_WEIGHTS
        assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9

    def test_gold_dimension_weight_exists(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import DIMENSION_WEIGHTS
        assert 'gold' in DIMENSION_WEIGHTS
        assert DIMENSION_WEIGHTS['gold'] == 0.08

    def test_copper_gold_dimension_weight_exists(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import DIMENSION_WEIGHTS
        assert 'copper_gold' in DIMENSION_WEIGHTS
        assert DIMENSION_WEIGHTS['copper_gold'] == 0.10

    def test_crude_oil_dimension_weight_exists(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import DIMENSION_WEIGHTS
        assert 'crude_oil' in DIMENSION_WEIGHTS
        assert DIMENSION_WEIGHTS['crude_oil'] == 0.10

    def test_copper_gold_thresholds_exist(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import THRESHOLDS
        assert 'copper_gold_percentile_extreme' in THRESHOLDS
        assert 'copper_gold_percentile_high' in THRESHOLDS
        assert 'copper_gold_percentile_elevated' in THRESHOLDS
        assert 'copper_gold_weekly_drop_pct' in THRESHOLDS

    def test_crude_thresholds_exist(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import THRESHOLDS
        assert 'crude_weekly_surge_pct' in THRESHOLDS
        assert 'crude_weekly_rise_pct' in THRESHOLDS
        assert 'crude_weekly_crash_pct' in THRESHOLDS
        assert 'crude_high_price' in THRESHOLDS
        assert 'crude_elevated_price' in THRESHOLDS

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
        # 10 stable days, 5 sharp falls (drives RSI < 40), 11 recovery days (price back above MA20),
        # then 3 consecutive down days where the last day crosses below MA20 for the first time.
        prices = [100.0] * 10 + [85, 83, 81, 79, 77] + [100.0] * 11 + [99.0, 98.0, 70.0]
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


class TestFetchGoldAnomaly:
    """Test the full _fetch_gold_anomaly method with mocked data."""

    def _make_analyzer(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import MacroLiquidityAnalyzer
        return MacroLiquidityAnalyzer()

    def _make_mock_gold_df(self, prices: list) -> pd.DataFrame:
        """Create a mock yfinance DataFrame."""
        dates = pd.bdate_range(end=datetime.now(), periods=len(prices))
        return pd.DataFrame({
            'Close': prices,
            'High': [p * 1.01 for p in prices],
            'Low': [p * 0.99 for p in prices],
        }, index=dates)

    def _make_mock_usd_df(self, prices: list) -> pd.DataFrame:
        dates = pd.bdate_range(end=datetime.now(), periods=len(prices))
        return pd.DataFrame({'Close': prices}, index=dates)

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_fetch_returns_expected_structure(self, mock_yf):
        """_fetch_gold_anomaly should return dict with required keys."""
        gold_prices = [100.0] * 20 + [99, 98, 97, 96, 95]
        usd_prices = [100.0] * 25

        def download_side_effect(ticker, **kwargs):
            if ticker == 'GC=F':
                return self._make_mock_gold_df(gold_prices)
            elif ticker == 'DX-Y.NYB':
                return self._make_mock_usd_df(usd_prices)
            return pd.DataFrame()

        mock_yf.download.side_effect = download_side_effect

        analyzer = self._make_analyzer()
        analyzer._fred_api_key = 'fake'
        with patch.object(analyzer, '_get_fred') as mock_fred:
            mock_series = pd.Series([1.8, 1.82, 1.85, 1.83, 1.80],
                                     index=pd.bdate_range(end=datetime.now(), periods=5))
            mock_fred.return_value.get_series.return_value = mock_series
            result = analyzer._fetch_gold_anomaly(90)

        assert 'current_price' in result
        assert 'weekly_change_pct' in result
        assert 'early_warning' in result
        assert 'confirmation' in result
        assert 'risk_score' in result
        assert 'signals' in result
        assert 'series' in result
        assert isinstance(result['signals'], list)
        assert 0 <= result['risk_score'] <= 100

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_fetch_handles_gold_data_failure(self, mock_yf):
        """When GC=F returns empty, should return error with risk_score 50."""
        mock_yf.download.return_value = pd.DataFrame()

        analyzer = self._make_analyzer()
        result = analyzer._fetch_gold_anomaly(90)

        assert 'error' in result
        assert result['risk_score'] == 50

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_fetch_stale_data_warning(self, mock_yf):
        """When latest gold data is > 3 days old, should add staleness warning."""
        old_end = datetime.now() - timedelta(days=7)
        prices = [100.0] * 25
        dates = pd.bdate_range(end=old_end, periods=25)
        gold_df = pd.DataFrame({
            'Close': prices,
            'High': [p * 1.01 for p in prices],
            'Low': [p * 0.99 for p in prices],
        }, index=dates)

        mock_yf.download.return_value = gold_df

        analyzer = self._make_analyzer()
        result = analyzer._fetch_gold_anomaly(90)

        assert any('数据延迟' in s or '延迟' in s for s in result.get('signals', []))

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_fetch_usd_failure_skips_divergence(self, mock_yf):
        """When DX-Y.NYB fails but GC=F succeeds, divergence should be skipped."""
        gold_prices = [100.0] * 20 + [99, 98, 97, 96, 95]

        def download_side_effect(ticker, **kwargs):
            if ticker == 'GC=F':
                dates = pd.bdate_range(end=datetime.now(), periods=len(gold_prices))
                return pd.DataFrame({
                    'Close': gold_prices,
                    'High': [p * 1.01 for p in gold_prices],
                    'Low': [p * 0.99 for p in gold_prices],
                }, index=dates)
            return pd.DataFrame()

        mock_yf.download.side_effect = download_side_effect

        analyzer = self._make_analyzer()
        with patch.object(analyzer, '_get_fred', side_effect=Exception("no FRED")):
            result = analyzer._fetch_gold_anomaly(90)

        assert result['confirmation']['gold_usd_divergence'] is False
        assert 'error' not in result


class TestCopperGoldRatio:
    """Test the _fetch_copper_gold_ratio method."""

    def _make_analyzer(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import MacroLiquidityAnalyzer
        return MacroLiquidityAnalyzer()

    def _make_df(self, prices: list) -> pd.DataFrame:
        dates = pd.bdate_range(end=datetime.now(), periods=len(prices))
        return pd.DataFrame({'Close': prices}, index=dates)

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_returns_expected_structure(self, mock_yf):
        """_fetch_copper_gold_ratio should return dict with required keys."""
        copper_prices = [4.0] * 90
        gold_prices = [2000.0] * 90

        def download_side_effect(ticker, **kwargs):
            if ticker == 'HG=F':
                return self._make_df(copper_prices)
            elif ticker == 'GC=F':
                return self._make_df(gold_prices)
            return pd.DataFrame()

        mock_yf.download.side_effect = download_side_effect

        analyzer = self._make_analyzer()
        result = analyzer._fetch_copper_gold_ratio()

        assert 'ratio' in result
        assert 'percentile' in result
        assert 'risk_score' in result
        assert 'signals' in result
        assert 'series' in result
        assert isinstance(result['signals'], list)
        assert 0 <= result['risk_score'] <= 100

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_low_percentile_high_risk(self, mock_yf):
        """When copper declines sharply relative to gold, risk_score should be >= 70."""
        # Copper: stable at 4.5 for 60 days, then drops to 2.2 for 30 days
        # Gold: stable at 2000 throughout
        # The 30-day low ratio (2.2/2000 = 0.0011) will be at a very low percentile
        copper_prices = [4.5] * 60 + [2.2] * 30
        gold_prices = [2000.0] * 90

        def download_side_effect(ticker, **kwargs):
            if ticker == 'HG=F':
                return self._make_df(copper_prices)
            elif ticker == 'GC=F':
                return self._make_df(gold_prices)
            return pd.DataFrame()

        mock_yf.download.side_effect = download_side_effect

        analyzer = self._make_analyzer()
        result = analyzer._fetch_copper_gold_ratio()

        assert result['risk_score'] >= 70

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_empty_data_returns_error(self, mock_yf):
        """When yf.download returns empty DataFrame, result should have 'error' and risk_score == 50."""
        mock_yf.download.return_value = pd.DataFrame()

        analyzer = self._make_analyzer()
        result = analyzer._fetch_copper_gold_ratio()

        assert 'error' in result
        assert result['risk_score'] == 50
