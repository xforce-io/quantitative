"""Integration test for frequency-aware data loaders.

Marked slow because it touches the data service; skip in default test run.
"""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.mark.slow
def test_fetch_proxy_prices_weekly_returns_friday_bars() -> None:
    from scripts.long_rotation_discovery import fetch_proxy_prices
    from quant.services.data_service import DataService

    ds = DataService()
    df, _ = fetch_proxy_prices(ds, "20240101", "20240630", frequency="weekly")

    # Weekly bars should be roughly 26 (6 months × ~4.3 weeks/mo); allow ±3 for holidays.
    assert 22 <= len(df.index) <= 30, f"Expected ~26 weekly bars, got {len(df.index)}"
    # Friday alignment.
    weekdays = df.index.weekday.unique().tolist()
    assert weekdays == [4], f"Expected Friday-only index, got {weekdays}"


@pytest.mark.slow
def test_fetch_etf_monthly_prices_wrapper_unchanged() -> None:
    """Backward-compat: old function name still works at monthly."""
    from scripts.long_rotation_discovery import fetch_etf_monthly_prices
    from quant.services.data_service import DataService

    ds = DataService()
    df, n = fetch_etf_monthly_prices(ds, "20240101", "20240630", subset=False)
    assert len(df.index) >= 4
    assert df.index.is_monotonic_increasing


@pytest.mark.slow
def test_fetch_volumes_weekly_keeps_anomaly_filter_at_daily() -> None:
    """Sanity: weekly volume fetch still produces valid data; anomaly filter is at daily level (proxy: no symbols dropped that aren't dropped at monthly)."""
    from scripts.long_rotation_discovery import fetch_volumes, fetch_monthly_volumes
    from quant.services.data_service import DataService

    ds = DataService()
    monthly = fetch_monthly_volumes(ds, "real_etf_full", "20240101", "20240630")
    weekly = fetch_volumes(ds, "real_etf_full", "20240101", "20240630", frequency="weekly")
    if monthly is None or weekly is None:
        pytest.skip("data service unavailable")
    # Same set of symbols should survive (daily-level anomaly filter shouldn't change between freqs)
    assert set(monthly.columns) == set(weekly.columns)
