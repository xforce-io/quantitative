"""Unit tests for systemic risk data fetcher (mocked network)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from quant.analysis.indicators.systemic_risk.data_fetcher import (
    SystemicRiskDataFetcher,
    series_from_fred_map,
)


def _idx(n=100):
    return pd.date_range("2020-01-01", periods=n, freq="B")


class TestSeriesFromFredMap:
    def test_subtract(self):
        idx = _idx(10)
        raw = {
            "DCPF3M": pd.Series(np.linspace(2, 3, 10), index=idx),
            "DGS3MO": pd.Series(np.linspace(1, 1.5, 10), index=idx),
        }
        out = series_from_fred_map(raw, ["DCPF3M", "DGS3MO"], compute="subtract")
        assert out is not None
        assert len(out) > 0
        assert out.iloc[-1] == pytest.approx(3 - 1.5, abs=0.01)

    def test_net_liquidity(self):
        idx = _idx(10)
        raw = {
            "WALCL": pd.Series([100.0] * 10, index=idx),
            "WTREGEN": pd.Series([20.0] * 10, index=idx),
            "RRPONTSYD": pd.Series([10.0] * 10, index=idx),
        }
        out = series_from_fred_map(
            raw, ["WALCL", "WTREGEN", "RRPONTSYD"], compute="net_liquidity"
        )
        assert out.iloc[-1] == pytest.approx(70.0)


class TestFetcherMocked:
    def test_fetch_all_builds_expected_keys(self):
        idx = _idx(80)

        def fake_fred_series(sid, observation_start=None, observation_end=None):
            return pd.Series(np.linspace(1, 2, 80), index=idx)

        def fake_yf(ticker, start=None, end=None, progress=False):
            return pd.DataFrame({"Close": np.linspace(100, 110, 80)}, index=idx)

        fetcher = SystemicRiskDataFetcher(fred_api_key="dummy")
        with patch.object(fetcher, "_get_fred") as mock_fred:
            fred = MagicMock()
            fred.get_series.side_effect = fake_fred_series
            mock_fred.return_value = fred
            with patch(
                "quant.analysis.indicators.systemic_risk.data_fetcher.yf_download",
                side_effect=fake_yf,
            ):
                frames = fetcher.fetch_all(start="2020-01-01", end="2020-05-01")

        assert "sofr_iorb_spread" in frames
        assert "hy_oas" in frames
        assert "vix" in frames
        assert "gold" in frames
        assert "net_liquidity" in frames
