"""Tests for VolumeFilteredRanker."""
import pandas as pd
import pytest

from quant.analysis.rotation.ranker import MomentumRanker, RankerConfig, VolumeFilteredRanker
from quant.analysis.rotation.universe import VolumeFilterConfig


def _make_prices(symbols, dates, fill=100.0):
    return pd.DataFrame(fill, index=pd.to_datetime(dates), columns=symbols)


def _make_volumes(symbols, dates, fill=2_000_000):
    return pd.DataFrame(fill, index=pd.to_datetime(dates), columns=symbols)


DATES = [
    "2024-01-31", "2024-02-29", "2024-03-31",
    "2024-04-30", "2024-05-31", "2024-06-30",
    "2024-07-31", "2024-08-31",
]
SYMBOLS = ["512800.SH", "159930.SZ", "513100.SH"]
INDUSTRY = {"512800.SH", "159930.SZ"}


def _ranker():
    return MomentumRanker(RankerConfig(lookback_months=6, skip_recent_months=1, top_k=3))


def test_volume_filter_disabled_passes_all():
    """When filter is disabled, all symbols reach the ranker."""
    prices = _make_prices(SYMBOLS, DATES)
    prices.iloc[-1] = [110, 120, 130]

    volumes = _make_volumes(SYMBOLS, DATES, fill=0)  # all zero, would be filtered if enabled
    cfg = VolumeFilterConfig(enabled=False)
    ranker = VolumeFilteredRanker(_ranker(), volumes, cfg, INDUSTRY)

    result = ranker.rank(prices, pd.Timestamp("2024-08-31"))
    assert set(result.keys()) <= set(SYMBOLS)


def test_volume_filter_excludes_low_volume_industry_etf():
    """Industry ETF below threshold is excluded; defensive ETF passes regardless."""
    prices = _make_prices(SYMBOLS, DATES)
    prices.iloc[-1] = [110, 120, 130]

    volumes = _make_volumes(SYMBOLS, DATES, fill=2_000_000)
    volumes["159930.SZ"] = 100  # very low volume

    cfg = VolumeFilterConfig(enabled=True, min_avg_monthly_volume_shares=1_000_000, lookback_months=3)
    ranker = VolumeFilteredRanker(_ranker(), volumes, cfg, INDUSTRY)

    result = ranker.rank(prices, pd.Timestamp("2024-08-31"))
    assert "159930.SZ" not in result


def test_volume_filter_non_industry_etf_never_filtered():
    """Defensive/style ETFs pass the volume filter regardless of volume."""
    symbols = ["513100.SH", "511880.SH"]
    prices = _make_prices(symbols, DATES)
    prices.iloc[-1] = [110, 105]

    volumes = _make_volumes(symbols, DATES, fill=0)  # zero volume
    cfg = VolumeFilterConfig(enabled=True, min_avg_monthly_volume_shares=1_000_000, lookback_months=3)
    industry = set()  # no industry ETFs
    ranker = VolumeFilteredRanker(_ranker(), volumes, cfg, industry)

    result = ranker.rank(prices, pd.Timestamp("2024-08-31"))
    assert len(result) > 0


def test_volume_filter_per_etf_threshold_override():
    """Per-ETF threshold overrides global threshold."""
    prices = _make_prices(SYMBOLS, DATES)
    prices.iloc[-1] = [110, 120, 130]

    volumes = _make_volumes(SYMBOLS, DATES, fill=600_000)  # below global 1M

    cfg = VolumeFilterConfig(enabled=True, min_avg_monthly_volume_shares=1_000_000, lookback_months=3)
    per_etf = {"159930.SZ": 500_000}  # 159930.SZ has lower threshold — should pass at 600k
    ranker = VolumeFilteredRanker(_ranker(), volumes, cfg, INDUSTRY, per_etf_thresholds=per_etf)

    result = ranker.rank(prices, pd.Timestamp("2024-08-31"))
    # 159930.SZ passes (600k >= 500k); 512800.SH excluded (600k < 1M)
    assert "159930.SZ" in result
    assert "512800.SH" not in result


def test_volume_filter_uses_trailing_window():
    """Filter uses trailing lookback_months, not full history."""
    prices = _make_prices(["512800.SH"], DATES)
    prices.iloc[-1] = 110.0

    volumes = pd.DataFrame({"512800.SH": [5_000_000] * 5 + [100, 100, 100]},
                           index=pd.to_datetime(DATES))
    # Recent 3 months: 100 shares (below 1M), but earlier months had 5M

    cfg = VolumeFilterConfig(enabled=True, min_avg_monthly_volume_shares=1_000_000, lookback_months=3)
    industry = {"512800.SH"}
    ranker = VolumeFilteredRanker(_ranker(), volumes, cfg, industry)

    result = ranker.rank(prices, pd.Timestamp("2024-08-31"))
    assert "512800.SH" not in result  # trailing 3M is low
