#!/usr/bin/env python3
"""Tests for position sizing using real CSI 300 fixture data."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant.analysis.position_sizing.volatility import VolatilityCalculator

FIXTURE = Path("tests/fixtures/csi300_daily.csv")


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
