#!/usr/bin/env python3
"""Tests for position sizing using real CSI 300 fixture data."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant.analysis.position_sizing.volatility import VolatilityCalculator

FIXTURE = Path(__file__).parent.parent / "fixtures" / "csi300_daily.csv"


def load_prices() -> pd.Series:
    df = pd.read_csv(FIXTURE, parse_dates=["date"])
    return df.set_index("date")["close"]


def prices_for(start: str, end: str) -> pd.Series:
    return load_prices().loc[start:end]


class TestVolatilityCalculator:
    def test_vol_high_during_2022_bear(self):
        # 2022 A-share bear market peak (CSI 300 fell ~30% Jan–Apr 2022)
        # End at 2022-04-29 so realized_vol captures the volatile March–April window
        calc = VolatilityCalculator(window=20)
        prices = prices_for("2021-01-01", "2022-04-29")
        vol = calc.realized_vol(prices)
        assert vol >= 0.25, f"2022 bear vol should be ≥25%, got {vol:.1%}"

    def test_vol_low_during_2024_q1(self):
        # 2024 Q1 was relatively calm before September rally
        calc = VolatilityCalculator(window=20)
        prices = prices_for("2023-07-01", "2024-03-31")
        vol = calc.realized_vol(prices)
        assert vol <= 0.22, f"2024 Q1 vol should be ≤22%, got {vol:.1%}"

    def test_annualization_formula(self):
        # Verify σ_daily × √252 formula using controlled daily returns
        rng = np.random.RandomState(42)
        daily_rets = rng.normal(0, 0.01, 25)
        prices = pd.Series(
            (1 + daily_rets).cumprod() * 100,
            index=pd.date_range("2024-01-01", periods=25, freq="B"),
        )
        calc = VolatilityCalculator(window=20)
        vol = calc.realized_vol(prices)
        expected = float(pd.Series(daily_rets[-20:]).std() * math.sqrt(252))
        assert abs(vol - expected) < 1e-10

    def test_rolling_vol_nan_prefix(self):
        # First `window` values are NaN, rest are valid
        calc = VolatilityCalculator(window=20)
        prices = prices_for("2022-01-01", "2023-12-31")
        rv = calc.rolling_vol(prices)
        assert len(rv) == len(prices)
        assert rv.iloc[:20].isna().all()
        assert rv.iloc[20:].notna().all()

    def test_too_few_points_raises(self):
        calc = VolatilityCalculator(window=20)
        with pytest.raises(ValueError, match="at least 20 returns"):
            calc.realized_vol(pd.Series([100.0] * 10))


from quant.analysis.position_sizing.sizer import PositionSizer, PositionSizing


class TestPositionSizer:
    def test_position_capped_at_100_pct(self):
        sizer = PositionSizer(target_vol=0.20)
        prices = prices_for("2023-07-01", "2024-03-31")
        result = sizer.size(prices)
        assert result.position_pct <= 1.0

    def test_position_never_negative(self):
        sizer = PositionSizer(target_vol=0.20)
        prices = load_prices()
        result = sizer.size(prices)
        assert result.position_pct >= 0.0

    def test_position_below_70_pct_in_2022_bear(self):
        sizer = PositionSizer(target_vol=0.20)
        prices = prices_for("2021-01-01", "2022-04-29")
        result = sizer.size(prices)
        assert result.position_pct < 0.70, (
            f"High-vol period position={result.position_pct:.0%}, expected <70%"
        )

    def test_returns_position_sizing_dataclass(self):
        sizer = PositionSizer(target_vol=0.20)
        result = sizer.size(load_prices())
        assert isinstance(result, PositionSizing)
        assert 0.0 <= result.position_pct <= 1.0
        assert result.target_vol == 0.20
        assert result.realized_vol > 0
        assert result.updated_date != ""

    def test_higher_target_vol_gives_larger_position(self):
        prices = load_prices()
        r_aggressive = PositionSizer(target_vol=0.30).size(prices)
        r_conservative = PositionSizer(target_vol=0.10).size(prices)
        assert r_aggressive.position_pct >= r_conservative.position_pct
