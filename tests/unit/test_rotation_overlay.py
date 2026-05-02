"""Tests for SimpleRegimeOverlay."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.analysis.rotation.regime_overlay import (
    PrecomputedRegimeOverlay,
    SimpleRegimeOverlay,
)


def _strong_uptrend_prices(n: int = 600) -> pd.DataFrame:
    dates = pd.date_range("2022-01-04", periods=n, freq="B")
    close = 100.0 * np.exp(np.linspace(0.0, 0.5, n))
    return pd.DataFrame({"close": close}, index=dates)


def _bear_prices(n: int = 600) -> pd.DataFrame:
    dates = pd.date_range("2022-01-04", periods=n, freq="B")
    close = 100.0 * np.exp(np.linspace(0.0, -0.5, n))
    return pd.DataFrame({"close": close}, index=dates)


def test_precomputed_overlay_returns_multiplier_in_unit_interval() -> None:
    overlay = PrecomputedRegimeOverlay(_strong_uptrend_prices())
    series = overlay.multipliers
    assert not series.empty
    assert series.between(0.0, 1.0).all()


def test_precomputed_overlay_multiplier_at_known_date() -> None:
    overlay = PrecomputedRegimeOverlay(_strong_uptrend_prices())
    last_date = overlay.multipliers.index[-1]
    value = overlay.multiplier_at(last_date)
    assert pytest.approx(value, abs=1e-9) == float(overlay.multipliers.iloc[-1])


def test_precomputed_overlay_uses_latest_known_multiplier_for_unknown_date() -> None:
    overlay = PrecomputedRegimeOverlay(_strong_uptrend_prices())
    last_date = overlay.multipliers.index[-1]
    future = last_date + pd.offsets.MonthEnd(3)
    assert overlay.multiplier_at(future) == float(overlay.multipliers.iloc[-1])


def test_precomputed_overlay_pre_history_returns_zero() -> None:
    overlay = PrecomputedRegimeOverlay(_strong_uptrend_prices())
    earliest = overlay.multipliers.index[0]
    pre = earliest - pd.offsets.MonthEnd(2)
    assert overlay.multiplier_at(pre) == 0.0


def test_bear_market_drives_multiplier_to_zero() -> None:
    overlay = PrecomputedRegimeOverlay(_bear_prices())
    assert overlay.multipliers.iloc[-1] == 0.0


def test_simple_overlay_uses_data_service() -> None:
    captured = {}

    class _FakeDataService:
        def get_price(self, request):
            captured["request"] = request
            return _strong_uptrend_prices()

        def get_trading_days(self, start, end):
            return pd.date_range(start, end, freq="B").strftime("%Y-%m-%d").tolist()

    overlay = SimpleRegimeOverlay(
        data_service=_FakeDataService(),
        benchmark_symbol="000300.SH",
    )
    overlay.precompute(start="2022-01-01", end="2024-06-30")
    assert captured["request"].symbol == "000300.SH"
    assert captured["request"].asset_type == "index"

    sample_date = overlay.multipliers.index[-1]
    assert 0.0 <= overlay.multiplier_at(sample_date) <= 1.0


def test_simple_overlay_requires_precompute_before_lookup() -> None:
    overlay = SimpleRegimeOverlay(data_service=None, benchmark_symbol="000300.SH")
    with pytest.raises(RuntimeError, match="precompute"):
        overlay.multiplier_at(pd.Timestamp("2024-01-31"))
