"""
Integration tests for data pipeline.

Validates the full flow: provider selection -> data fetch -> cache -> normalize.
Uses mocked network calls to stay fast and offline.
"""

import pytest
import pickle
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock

from quant.data.providers import DataProvider
from quant.core.exceptions import (
    DataNotFoundError,
    InvalidSymbolError,
    ProviderNotAvailableError,
)


class TestProviderSelection:
    """Test automatic provider selection logic."""

    @patch("quant.data.providers.YAHOO_AVAILABLE", True)
    @patch("quant.data.providers.TUSHARE_AVAILABLE", False)
    def test_auto_selects_yahoo_when_tushare_unavailable(self, tmp_cache_dir):
        """When tushare is not installed, auto mode should pick yahoo."""
        with patch("quant.data.providers.yf"):
            provider = DataProvider(
                "auto", {"cache_enabled": False, "cache_dir": str(tmp_cache_dir)}
            )
            assert provider.provider_name == "yahoo"

    @patch("quant.data.providers.YAHOO_AVAILABLE", False)
    @patch("quant.data.providers.TUSHARE_AVAILABLE", False)
    def test_auto_raises_when_no_provider_available(self, tmp_cache_dir):
        """When no providers are installed, should raise."""
        with pytest.raises(ProviderNotAvailableError):
            DataProvider(
                "auto", {"cache_enabled": False, "cache_dir": str(tmp_cache_dir)}
            )


class TestCachePipeline:
    """Test cache write -> read round-trip across get_stock_data calls."""

    @patch("quant.data.providers.YAHOO_AVAILABLE", True)
    @patch("quant.data.providers.TUSHARE_AVAILABLE", False)
    def test_cache_round_trip(self, tmp_cache_dir, realistic_stock_data):
        """Data fetched once should be served from cache on second call."""
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = realistic_stock_data.rename(
            columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
        )
        mock_yf.Ticker.return_value = mock_ticker

        with patch("quant.data.providers.yf", mock_yf):
            provider = DataProvider(
                "yahoo",
                {"cache_enabled": True, "cache_dir": str(tmp_cache_dir), "cache_ttl_hours": 24},
            )

            # First call — fetches from provider
            df1 = provider.get_stock_data("000001.SZ", "20240101", "20240630")
            assert not df1.empty
            assert mock_yf.Ticker.call_count == 1

            # Second call — should come from cache, no new Ticker call
            df2 = provider.get_stock_data("000001.SZ", "20240101", "20240630")
            assert mock_yf.Ticker.call_count == 1  # still 1
            pd.testing.assert_frame_equal(df1, df2)


class TestDataNormalization:
    """Test that data from different providers gets normalized consistently."""

    @patch("quant.data.providers.YAHOO_AVAILABLE", True)
    @patch("quant.data.providers.TUSHARE_AVAILABLE", False)
    def test_yahoo_data_normalized_to_standard_columns(self, tmp_cache_dir, realistic_stock_data):
        """Yahoo data (capitalized columns) should be normalized to lowercase."""
        yahoo_df = realistic_stock_data.rename(
            columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
        )
        mock_yf = MagicMock()
        mock_yf.Ticker.return_value.history.return_value = yahoo_df

        with patch("quant.data.providers.yf", mock_yf):
            provider = DataProvider(
                "yahoo",
                {"cache_enabled": False, "cache_dir": str(tmp_cache_dir)},
            )
            df = provider.get_stock_data("000001.SZ", "20240101", "20240630")

            assert list(df.columns) == ["open", "high", "low", "close", "volume"]
            assert isinstance(df.index, pd.DatetimeIndex)
            assert df.index.is_monotonic_increasing

    @patch("quant.data.providers.YAHOO_AVAILABLE", True)
    @patch("quant.data.providers.TUSHARE_AVAILABLE", False)
    def test_empty_fetch_raises_data_not_found(self, tmp_cache_dir):
        """Provider returning empty DataFrame should raise DataNotFoundError."""
        mock_yf = MagicMock()
        mock_yf.Ticker.return_value.history.return_value = pd.DataFrame()

        with patch("quant.data.providers.yf", mock_yf):
            provider = DataProvider(
                "yahoo",
                {"cache_enabled": False, "cache_dir": str(tmp_cache_dir)},
            )
            with pytest.raises(DataNotFoundError):
                provider.get_stock_data("999999.SZ", "20240101", "20240630")
