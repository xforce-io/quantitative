#!/usr/bin/env python3
"""VolatilityCalculator — compute rolling annualized vol from CSI 300 prices."""
from __future__ import annotations

import math
import os

import pandas as pd
import tushare as ts

from quant.core.logging_config import get_logger

logger = get_logger(__name__)

TRADING_DAYS = 252
INDEX_CODE = "000300.SH"


class VolatilityCalculator:
    """Computes rolling annualized volatility from CSI 300 daily prices."""

    def __init__(self, window: int = 20) -> None:
        self._window = window

    def fetch(self, start_date: str, end_date: str) -> pd.Series:
        """
        Fetch CSI 300 daily close from tushare.

        Parameters
        ----------
        start_date, end_date : str  YYYYMMDD format, e.g. "20210101"

        Returns
        -------
        pd.Series with DatetimeIndex, values = daily close prices, sorted ascending.
        """
        token = os.environ.get("TUSHARE_TOKEN")
        if not token:
            raise ValueError("TUSHARE_TOKEN environment variable not set")
        ts.set_token(token)
        pro = ts.pro_api()

        df = pro.index_daily(ts_code=INDEX_CODE, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            raise ValueError(f"No data returned for {INDEX_CODE} [{start_date}, {end_date}]")

        df = df.sort_values("trade_date").reset_index(drop=True)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        logger.info(f"Fetched {len(df)} days of {INDEX_CODE} data")
        return df.set_index("trade_date")["close"]

    def realized_vol(self, prices: pd.Series) -> float:
        """Annualized vol from the most recent `window` daily returns: std × √252."""
        returns = prices.pct_change().dropna()
        if len(returns) < self._window:
            raise ValueError(
                f"Need at least {self._window} returns (got {len(returns)}). "
                f"Provide at least {self._window + 1} price points."
            )
        recent = returns.iloc[-self._window :]
        return float(recent.std() * math.sqrt(TRADING_DAYS))

    def rolling_vol(self, prices: pd.Series) -> pd.Series:
        """Rolling annualized vol series aligned to price index (for backtest)."""
        returns = prices.pct_change()
        return returns.rolling(self._window).std() * math.sqrt(TRADING_DAYS)
