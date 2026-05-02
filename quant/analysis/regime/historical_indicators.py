"""Historical a_shares indicator panel for cockpit regime overlay."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndicatorPanelConfig:
    """Lookback windows for historical a_shares regime indicators."""

    margin_trend_lookback_days: int = 30
    northbound_flow_window_days: int = 20


class AshareHistoricalIndicators:
    """Build a daily indicator panel for the a_shares regime classifier."""

    def __init__(self, data_service, config: IndicatorPanelConfig | None = None) -> None:
        self.data_service = data_service
        self.config = config or IndicatorPanelConfig()

    def build(self, start: str, end: str) -> pd.DataFrame:
        """Return a DataFrame indexed by natural day with columns
        ['margin_debt_trend', 'northbound_flow']. Empty if both sources fail."""
        margin_series = self._build_margin_trend(start, end)
        nb_series = self._build_northbound_window(start, end)

        if margin_series is None and nb_series is None:
            return pd.DataFrame()

        # Union of available dates, ffilled to natural day.
        # Columns for failed sources are included as NaN so callers can rely on a
        # consistent schema (both columns always present when at least one source worked).
        frames = {
            "margin_debt_trend": margin_series,
            "northbound_flow": nb_series,
        }

        df = pd.DataFrame(frames).sort_index()
        if df.empty:
            return df

        full_index = pd.date_range(df.index.min(), df.index.max(), freq="D")
        return df.reindex(full_index).ffill()

    def _build_margin_trend(self, start: str, end: str) -> pd.Series | None:
        try:
            raw = self.data_service.get_margin_balance(start, end)
        except Exception as exc:
            logger.warning("get_margin_balance failed: %s", exc)
            return None
        if raw is None or raw.empty or "total" not in raw.columns:
            return None

        series = (
            raw[["trade_date", "total"]]
            .dropna()
            .drop_duplicates("trade_date")
            .set_index(pd.to_datetime(raw["trade_date"]))["total"]
            .astype(float)
            .sort_index()
        )
        lookback = self.config.margin_trend_lookback_days
        # Compute pct change on the trading-day series (so `lookback` counts trading days,
        # not calendar days), then reindex to a natural-day grid and ffill for weekends.
        trend = (series / series.shift(lookback) - 1.0) * 100.0
        natural = trend.reindex(pd.date_range(series.index.min(), series.index.max(), freq="D")).ffill()
        return natural

    def _build_northbound_window(self, start: str, end: str) -> pd.Series | None:
        try:
            raw = self.data_service.get_northbound_flow(start, end)
        except Exception as exc:
            logger.warning("get_northbound_flow failed: %s", exc)
            return None
        if raw is None or raw.empty or "total_net" not in raw.columns:
            return None

        series = (
            raw[["trade_date", "total_net"]]
            .dropna()
            .drop_duplicates("trade_date")
            .set_index(pd.to_datetime(raw["trade_date"]))["total_net"]
            .astype(float)
            .sort_index()
        )
        window = self.config.northbound_flow_window_days
        # min_periods=1 so sparse inputs (e.g. only a few dates) still produce values;
        # the full window is only required once there are enough data points.
        rolled = series.rolling(window=window, min_periods=1).sum()
        return rolled
