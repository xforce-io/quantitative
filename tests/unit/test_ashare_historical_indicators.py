"""Tests for AshareHistoricalIndicators."""
from __future__ import annotations

import pandas as pd
import pytest

from quant.analysis.regime.historical_indicators import (
    AshareHistoricalIndicators,
    IndicatorPanelConfig,
)


class _StubDataService:
    """Fake DataService — supplies deterministic margin / northbound frames."""

    def __init__(self, margin=None, northbound=None, margin_exc=None, northbound_exc=None):
        self._margin = margin
        self._northbound = northbound
        self._margin_exc = margin_exc
        self._northbound_exc = northbound_exc

    def get_margin_balance(self, start, end):
        if self._margin_exc:
            raise self._margin_exc
        return self._margin if self._margin is not None else pd.DataFrame()

    def get_northbound_flow(self, start, end):
        if self._northbound_exc:
            raise self._northbound_exc
        return self._northbound if self._northbound is not None else pd.DataFrame()


def _trading_dates(n: int, start: str = "2024-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def _margin_frame(values: list[float], dates: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": dates,
        "rzye": values,
        "rqye": [v * 0.01 for v in values],
        "total": [v * 1.01 for v in values],
    })


def _northbound_frame(net_values: list[float], dates: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": dates,
        "hgt_net": [v * 0.6 for v in net_values],
        "sgt_net": [v * 0.4 for v in net_values],
        "total_net": net_values,
    })


def test_margin_debt_trend_computes_30day_pct_change():
    dates = _trading_dates(45)
    # margin total grows 1% per trading day — 30 trading days back is roughly day 14
    values = [1.0e12 * (1.01 ** i) for i in range(45)]
    margin = _margin_frame(values, dates)
    nb = _northbound_frame([0.0] * 45, dates)
    indicators = AshareHistoricalIndicators(
        _StubDataService(margin=margin, northbound=nb),
        IndicatorPanelConfig(margin_trend_lookback_days=30),
    )

    panel = indicators.build("20240101", "20240331")
    last_value = panel["margin_debt_trend"].dropna().iloc[-1]
    # Expect roughly 1.01**30 - 1 ≈ 34.78%, allow tolerance for natural-day vs trading-day window
    assert 25.0 < last_value < 45.0


def test_northbound_flow_rolls_20_trading_days():
    dates = _trading_dates(40)
    nb_values = [5.0] * 40   # constant 5 亿 net buy per day
    nb = _northbound_frame(nb_values, dates)
    margin = _margin_frame([1.0e12] * 40, dates)
    indicators = AshareHistoricalIndicators(
        _StubDataService(margin=margin, northbound=nb),
        IndicatorPanelConfig(northbound_flow_window_days=20),
    )

    panel = indicators.build("20240101", "20240301")
    last_value = panel["northbound_flow"].dropna().iloc[-1]
    assert last_value == pytest.approx(100.0, abs=1e-6)


def test_missing_margin_data_results_in_nan_column():
    dates = _trading_dates(30)
    nb = _northbound_frame([1.0] * 30, dates)
    indicators = AshareHistoricalIndicators(
        _StubDataService(northbound=nb, margin_exc=RuntimeError("tushare 503")),
    )

    panel = indicators.build("20240101", "20240301")
    assert panel["margin_debt_trend"].isna().all()
    assert panel["northbound_flow"].notna().any()
    assert panel["margin_debt_trend"].dtype == float
    assert panel["northbound_flow"].dtype == float


def test_both_sources_fail_returns_empty_dataframe():
    indicators = AshareHistoricalIndicators(
        _StubDataService(
            margin_exc=RuntimeError("err1"),
            northbound_exc=RuntimeError("err2"),
        ),
    )
    panel = indicators.build("20240101", "20240301")
    assert panel.empty


def test_natural_day_index_with_ffill():
    # Two trading dates separated by a weekend
    dates = pd.to_datetime(["2024-01-05", "2024-01-08"])  # Fri, Mon
    margin = _margin_frame([1.0e12, 1.05e12], dates)
    nb = _northbound_frame([10.0, 12.0], dates)
    # Use window=1 so strict rolling semantics produce a real value (not NaN) with only
    # 2 data points.  The test is about ffill on natural days, not rolling-sum leniency.
    indicators = AshareHistoricalIndicators(
        _StubDataService(margin=margin, northbound=nb),
        IndicatorPanelConfig(margin_trend_lookback_days=1, northbound_flow_window_days=1),
    )

    panel = indicators.build("20240105", "20240108")
    # Saturday (2024-01-06) and Sunday (2024-01-07) should appear with ffilled values
    assert pd.Timestamp("2024-01-06") in panel.index
    assert pd.Timestamp("2024-01-07") in panel.index
    assert panel.loc[pd.Timestamp("2024-01-06"), "northbound_flow"] == panel.loc[pd.Timestamp("2024-01-05"), "northbound_flow"]


def test_config_overrides_lookback_windows():
    dates = _trading_dates(40)
    values = [1.0e12 * (1.005 ** i) for i in range(40)]
    margin = _margin_frame(values, dates)
    nb = _northbound_frame([2.0] * 40, dates)

    short_cfg = IndicatorPanelConfig(margin_trend_lookback_days=5, northbound_flow_window_days=5)
    indicators = AshareHistoricalIndicators(
        _StubDataService(margin=margin, northbound=nb), short_cfg,
    )
    panel = indicators.build("20240101", "20240301")

    # 5-day window of 2 亿 each = 10
    assert panel["northbound_flow"].dropna().iloc[-1] == pytest.approx(10.0, abs=1e-6)
    # 5-day pct change at 0.5%/day ≈ 2.52%
    assert 1.5 < panel["margin_debt_trend"].dropna().iloc[-1] < 3.5


def test_handles_duplicate_dates_in_provider_response():
    """Real-world Tushare data sometimes contains duplicate trade_date rows
    (e.g. from cross-exchange aggregation). Verify build() doesn't crash."""
    dates = _trading_dates(35)
    values = [1.0e12 * (1.005 ** i) for i in range(35)]
    margin = _margin_frame(values, dates)
    # Duplicate the last row to simulate a duplicate-date provider response
    margin = pd.concat([margin, margin.tail(1)], ignore_index=True)
    nb = _northbound_frame([1.0] * 35, dates)

    indicators = AshareHistoricalIndicators(
        _StubDataService(margin=margin, northbound=nb),
        IndicatorPanelConfig(margin_trend_lookback_days=10, northbound_flow_window_days=5),
    )
    panel = indicators.build("20240101", "20240301")

    assert not panel.empty
    assert panel["margin_debt_trend"].notna().any()
