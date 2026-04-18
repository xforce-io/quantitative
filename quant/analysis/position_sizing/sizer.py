#!/usr/bin/env python3
"""PositionSizer — volatility-targeting position size calculator."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant.analysis.position_sizing.volatility import VolatilityCalculator
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PositionSizing:
    """Result of a position size calculation."""

    position_pct: float    # 0.0 – 1.0 (e.g. 0.73 = 73%)
    realized_vol: float    # annualized, e.g. 0.274
    target_vol: float      # e.g. 0.20
    updated_date: str      # ISO date string of last price

    def __str__(self) -> str:
        return (
            f"当前建议仓位: {self.position_pct:.0%}\n"
            f"当前20日年化波动率: {self.realized_vol:.1%}  (目标: {self.target_vol:.0%})\n"
            f"上次更新: {self.updated_date}"
        )


class PositionSizer:
    """Computes position size via: position = min(1, target_vol / realized_vol)."""

    def __init__(self, target_vol: float = 0.20) -> None:
        self._target_vol = target_vol
        if not (0 < target_vol <= 1.0):
            raise ValueError(f"target_vol must be in (0, 1], got {target_vol}")
        self._calc = VolatilityCalculator()

    def size(self, prices: pd.Series) -> PositionSizing:
        """Compute current recommended position from a price series."""
        if prices is None or prices.empty:
            raise ValueError("prices must be a non-empty Series")
        vol = self._calc.realized_vol(prices)
        if vol == 0:
            logger.warning("realized_vol is 0.0 — prices may be constant. Defaulting to full position.")
            position = 1.0
        else:
            position = min(1.0, self._target_vol / vol)
        last_date = prices.index[-1]
        updated = last_date.date().isoformat() if hasattr(last_date, "date") else str(last_date)
        return PositionSizing(
            position_pct=round(position, 4),
            realized_vol=round(vol, 4),
            target_vol=self._target_vol,
            updated_date=updated,
        )
