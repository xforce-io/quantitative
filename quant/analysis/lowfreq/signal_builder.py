"""Build low-frequency trend and position signals from daily prices."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import pandas as pd


TRADING_DAYS = 252


@dataclass(frozen=True)
class SignalConfig:
    """Configuration for low-frequency trend and volatility signals."""

    ma_months: int = 10
    vol_window: int = 20
    target_vol: float = 0.20
    max_position: float = 1.0


class LowFrequencySignalBuilder:
    """Build monthly low-frequency signals from normalized OHLCV data."""

    REQUIRED_COLUMNS = ("close",)

    def __init__(self, config: SignalConfig | None = None) -> None:
        self.config = config or SignalConfig()
        if self.config.ma_months <= 0:
            raise ValueError("ma_months must be positive")
        if self.config.vol_window <= 1:
            raise ValueError("vol_window must be greater than 1")
        if not (0 < self.config.target_vol <= 1.0):
            raise ValueError("target_vol must be in (0, 1]")
        if not (0 <= self.config.max_position <= 1.0):
            raise ValueError("max_position must be in [0, 1]")

    def build(self, prices: pd.DataFrame, trading_days: Iterable[str] | None = None) -> pd.DataFrame:
        """Build a month-end signal frame from daily price data."""
        daily = self._prepare_prices(prices)
        rebalance_index = self._rebalance_index(daily, trading_days)
        month_end_dates = daily.groupby(daily.index.to_period("M")).tail(1).index
        monthly_close = daily.loc[month_end_dates, "close"].dropna()
        monthly_ma = monthly_close.rolling(self.config.ma_months).mean()
        daily_vol = self._rolling_vol(daily["close"])

        rows = []
        for date in rebalance_index:
            month_key = monthly_close.index[monthly_close.index <= date]
            if month_key.empty:
                continue

            month_end = month_key[-1]
            close = float(daily.loc[:date, "close"].iloc[-1])
            ma_value = monthly_ma.loc[month_end]
            realized_vol = daily_vol.loc[:date].dropna()
            vol_value = float(realized_vol.iloc[-1]) if not realized_vol.empty else math.nan
            trend_on = bool(pd.notna(ma_value) and close > float(ma_value))
            vol_position = self._vol_position(vol_value)
            target_position = vol_position if trend_on else 0.0

            rows.append(
                {
                    "rebalance_date": date,
                    "close": close,
                    "monthly_ma": float(ma_value) if pd.notna(ma_value) else math.nan,
                    "realized_vol": vol_value,
                    "trend_on": trend_on,
                    "vol_position": vol_position,
                    "target_position": target_position,
                }
            )

        if not rows:
            return pd.DataFrame(
                columns=[
                    "close",
                    "monthly_ma",
                    "realized_vol",
                    "trend_on",
                    "vol_position",
                    "target_position",
                ]
            )

        result = pd.DataFrame(rows).set_index("rebalance_date")
        result.index.name = "rebalance_date"
        return result

    def _prepare_prices(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Validate and normalize daily price input."""
        if prices is None or prices.empty:
            raise ValueError("prices must be a non-empty DataFrame")

        missing = [col for col in self.REQUIRED_COLUMNS if col not in prices.columns]
        if missing:
            raise ValueError(f"prices missing required columns: {', '.join(missing)}")

        daily = prices.copy()
        if "date" in daily.columns:
            daily["date"] = pd.to_datetime(daily["date"])
            daily = daily.set_index("date")
        elif not isinstance(daily.index, pd.DatetimeIndex):
            daily.index = pd.to_datetime(daily.index)

        daily = daily.sort_index()
        daily["close"] = pd.to_numeric(daily["close"], errors="coerce")
        daily = daily.dropna(subset=["close"])
        if daily.empty:
            raise ValueError("prices close column has no valid values")
        return daily

    def _rebalance_index(
        self,
        daily: pd.DataFrame,
        trading_days: Iterable[str] | None,
    ) -> pd.DatetimeIndex:
        """Return month-end rebalance dates constrained to available prices."""
        if trading_days is None:
            return pd.DatetimeIndex(daily.resample("ME").last().dropna().index)

        calendar = pd.DatetimeIndex(pd.to_datetime(list(trading_days))).sort_values()
        calendar = calendar[(calendar >= daily.index.min()) & (calendar <= daily.index.max())]
        if calendar.empty:
            return pd.DatetimeIndex([])

        return pd.DatetimeIndex(
            pd.Series(calendar, index=calendar).groupby(calendar.to_period("M")).max().values
        )

    def _rolling_vol(self, closes: pd.Series) -> pd.Series:
        """Compute annualized rolling realized volatility."""
        returns = closes.pct_change()
        return returns.rolling(self.config.vol_window).std() * math.sqrt(TRADING_DAYS)

    def _vol_position(self, realized_vol: float) -> float:
        """Convert realized volatility into a clipped position size."""
        if pd.isna(realized_vol):
            return 0.0
        if realized_vol <= 0:
            return self.config.max_position
        return round(min(self.config.max_position, self.config.target_vol / realized_vol), 4)
