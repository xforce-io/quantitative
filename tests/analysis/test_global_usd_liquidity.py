#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for global_usd_liquidity pure calculation functions.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from quant.analysis.indicators.global_usd_liquidity import (
    GROUP_WEIGHTS,
    aggregate_group_confidence,
    aggregate_total_confidence,
    compute_rolling_confidence,
    percentile_to_confidence,
)


class TestPercentileToConfidence:
    def test_median_gives_zero(self):
        assert percentile_to_confidence(50.0) == 0.0

    def test_max_gives_positive_100(self):
        assert percentile_to_confidence(100.0) == 100.0

    def test_min_gives_negative_100(self):
        assert percentile_to_confidence(0.0) == -100.0

    def test_75th_percentile(self):
        assert percentile_to_confidence(75.0) == 50.0

    def test_inverted_polarity(self):
        assert percentile_to_confidence(75.0, inverted=True) == -50.0
        assert percentile_to_confidence(25.0, inverted=True) == 50.0


class TestComputeRollingConfidence:
    def test_basic_rolling(self):
        data = pd.Series(
            range(100),
            index=pd.date_range('2024-01-01', periods=100, freq='B'),
        )
        result = compute_rolling_confidence(data, window=50, inverted=False)
        valid = result.dropna()
        # value 50 is the max in the first window (0..50), so it should be near 100
        assert valid.iloc[0] > 90.0
        assert valid.iloc[-1] > 90.0

    def test_inverted_rolling(self):
        data = pd.Series(
            range(100),
            index=pd.date_range('2024-01-01', periods=100, freq='B'),
        )
        result = compute_rolling_confidence(data, window=50, inverted=True)
        assert result.dropna().iloc[-1] < -90.0

    def test_constant_series_gives_zero(self):
        data = pd.Series(
            [5.0] * 100,
            index=pd.date_range('2024-01-01', periods=100, freq='B'),
        )
        result = compute_rolling_confidence(data, window=50, inverted=False)
        assert abs(result.dropna().iloc[-1]) < 1.0

    def test_insufficient_data_returns_nan(self):
        data = pd.Series(
            [1, 2, 3],
            index=pd.date_range('2024-01-01', periods=3, freq='B'),
        )
        result = compute_rolling_confidence(data, window=504, inverted=False)
        assert result.isna().all()


class TestAggregateGroupConfidence:
    def test_simple_average(self):
        result = aggregate_group_confidence({'a': 40.0, 'b': 60.0, 'c': -20.0})
        assert abs(result - 26.67) < 0.1

    def test_single_value(self):
        assert aggregate_group_confidence({'a': -50.0}) == -50.0

    def test_empty_returns_none(self):
        assert aggregate_group_confidence({}) is None

    def test_skips_none_values(self):
        result = aggregate_group_confidence({'a': 40.0, 'b': None, 'c': -20.0})
        assert abs(result - 10.0) < 0.1


class TestAggregateTotalConfidence:
    def test_normal_aggregation(self):
        groups = {'onshore': -42.0, 'offshore': -65.0, 'net_liquidity': -28.0}
        result = aggregate_total_confidence(groups, GROUP_WEIGHTS)
        assert abs(result - (-44.7)) < 0.1

    def test_one_group_failed(self):
        groups = {'onshore': -42.0, 'offshore': None, 'net_liquidity': -28.0}
        result = aggregate_total_confidence(groups, GROUP_WEIGHTS)
        assert abs(result - (-36.0)) < 0.5

    def test_all_groups_failed(self):
        result = aggregate_total_confidence(
            {'onshore': None, 'offshore': None, 'net_liquidity': None},
            GROUP_WEIGHTS,
        )
        assert result is None
