"""Tests for LeadingIndicatorsAnalyzer — mock all external data sources."""

import pandas as pd
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from quant.analysis.indicators.leading_indicators import LeadingIndicatorsAnalyzer


def _make_daily_series(values: list, start: str = "2026-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, index=idx)


class TestAnalyzeVix:
    @patch("quant.analysis.indicators.leading_indicators.yf")
    def test_returns_vix_with_delta(self, mock_yf):
        prices = [18.0 + i * 0.3 for i in range(30)]
        mock_df = pd.DataFrame(
            {"Close": prices},
            index=pd.date_range("2026-01-01", periods=30, freq="D"),
        )
        mock_yf.download.return_value = mock_df

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_vix(lookback_days=30)

        assert "value" in result
        assert "delta" in result
        assert result["delta"]["velocity"] > 0
        assert result["level"] in ("normal", "elevated", "fear", "panic")

    @patch("quant.analysis.indicators.leading_indicators.yf")
    def test_vix_empty_data(self, mock_yf):
        mock_yf.download.return_value = pd.DataFrame()
        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_vix()
        assert "error" in result


class TestAnalyzeCreditSpread:
    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_returns_spread_with_delta(self, mock_get_fred):
        mock_fred = MagicMock()
        hy_values = _make_daily_series([4.5 + i * 0.02 for i in range(30)])
        bbb_values = _make_daily_series([1.5 + i * 0.005 for i in range(30)])
        mock_fred.get_series.side_effect = [hy_values, bbb_values]
        mock_get_fred.return_value = mock_fred

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_credit_spread(lookback_days=30)

        assert "spread" in result
        assert "delta" in result
        assert result["level"] in ("normal", "elevated", "stress", "crisis")

    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_credit_spread_error(self, mock_get_fred):
        mock_get_fred.side_effect = Exception("FRED unavailable")
        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_credit_spread()
        assert "error" in result


class TestAnalyzeMarginBalance:
    def test_returns_margin_with_delta(self):
        dates = pd.date_range("2026-01-01", periods=30, freq="D")
        margin_df = pd.DataFrame({
            "trade_date": [d.strftime("%Y%m%d") for d in dates],
            "rzye": [1.3e12 + i * 1e9 for i in range(30)],
            "rzmre": [5e9] * 30,
            "rzche": [4e9] * 30,
        })

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_margin_balance(margin_df=margin_df)

        assert "balance_yi" in result
        assert "delta" in result
        assert result["delta"]["velocity"] > 0


class TestAnalyzeYieldCurve:
    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_returns_yield_curve_with_delta(self, mock_get_fred):
        mock_fred = MagicMock()
        spread_values = _make_daily_series([0.5 - i * 0.015 for i in range(30)])
        real_yield_values = _make_daily_series([2.0 + i * 0.01 for i in range(30)])
        mock_fred.get_series.side_effect = [spread_values, real_yield_values]
        mock_get_fred.return_value = mock_fred

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_yield_curve(lookback_days=30)

        assert "spread" in result
        assert "level" in result
        assert "level_cn" in result
        assert "emoji" in result
        assert "real_yield" in result
        assert "delta" in result
        assert result["level"] in ("normal", "flattening", "inverted", "deeply_inverted")

    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_inverted_curve(self, mock_get_fred):
        mock_fred = MagicMock()
        spread_values = _make_daily_series([-0.3] * 30)
        real_yield_values = _make_daily_series([2.5] * 30)
        mock_fred.get_series.side_effect = [spread_values, real_yield_values]
        mock_get_fred.return_value = mock_fred

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_yield_curve(lookback_days=30)

        assert result["level"] == "inverted"
        assert result["emoji"] == "🟠"

    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_deeply_inverted_curve(self, mock_get_fred):
        mock_fred = MagicMock()
        spread_values = _make_daily_series([-0.8] * 30)
        real_yield_values = _make_daily_series([2.0] * 30)
        mock_fred.get_series.side_effect = [spread_values, real_yield_values]
        mock_get_fred.return_value = mock_fred

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_yield_curve(lookback_days=30)

        assert result["level"] == "deeply_inverted"
        assert result["emoji"] == "🔴"

    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_normal_curve(self, mock_get_fred):
        mock_fred = MagicMock()
        spread_values = _make_daily_series([1.0] * 30)
        real_yield_values = _make_daily_series([1.5] * 30)
        mock_fred.get_series.side_effect = [spread_values, real_yield_values]
        mock_get_fred.return_value = mock_fred

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_yield_curve(lookback_days=30)

        assert result["level"] == "normal"
        assert result["emoji"] == "🟢"

    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_fred_failure_returns_error(self, mock_get_fred):
        mock_get_fred.side_effect = Exception("FRED unavailable")

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_yield_curve()

        assert "error" in result


class TestAnalyzeAll:
    @patch("quant.analysis.indicators.leading_indicators.yf")
    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_analyze_all_returns_four_indicators(self, mock_get_fred, mock_yf):
        mock_yf.download.return_value = pd.DataFrame(
            {"Close": [20.0] * 30},
            index=pd.date_range("2026-01-01", periods=30, freq="D"),
        )

        mock_fred = MagicMock()
        mock_fred.get_series.return_value = _make_daily_series([3.0] * 30)
        mock_get_fred.return_value = mock_fred

        dates = pd.date_range("2026-01-01", periods=30, freq="D")
        margin_df = pd.DataFrame({
            "trade_date": [d.strftime("%Y%m%d") for d in dates],
            "rzye": [1.3e12] * 30,
        })

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_all(margin_df=margin_df, lookback_days=30)

        assert "vix" in result
        assert "credit_spread" in result
        assert "margin" in result
        assert "yield_curve" in result
