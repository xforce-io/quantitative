"""Regime overlay (A layer) wrapping the existing LowFrequencyRegimeScorer."""
from __future__ import annotations

from typing import Optional, Protocol

import pandas as pd

from quant.analysis.lowfreq import (
    LowFrequencyRegimeScorer,
    LowFrequencySignalBuilder,
    SignalConfig,
)


class RegimeOverlay(Protocol):
    """Protocol allowing future cockpit-based overlay to drop in."""

    def multiplier_at(self, date: pd.Timestamp) -> float: ...


class PrecomputedRegimeOverlay:
    """Overlay backed by an in-memory precomputed multiplier series."""

    def __init__(self, benchmark_prices: pd.DataFrame) -> None:
        signals = LowFrequencySignalBuilder(SignalConfig()).build(benchmark_prices)
        if signals.empty:
            self.multipliers = pd.Series(dtype=float, name="regime_multiplier")
            return
        scored = LowFrequencyRegimeScorer().apply(signals)
        self.multipliers = scored["regime_multiplier"].astype(float)

    def multiplier_at(self, date: pd.Timestamp) -> float:
        if self.multipliers.empty:
            return 0.0
        if date < self.multipliers.index[0]:
            return 0.0
        idx = self.multipliers.index.searchsorted(date, side="right") - 1
        return float(self.multipliers.iloc[idx])


class SimpleRegimeOverlay:
    """Pull benchmark prices via DataService and wrap them in a precomputed overlay."""

    def __init__(
        self,
        data_service,
        benchmark_symbol: str = "000300.SH",
    ) -> None:
        self.data_service = data_service
        self.benchmark_symbol = benchmark_symbol
        self._inner: Optional[PrecomputedRegimeOverlay] = None

    def precompute(self, start: str, end: str) -> None:
        from quant.services.data_service import PriceRequest

        prices = self.data_service.get_price(
            PriceRequest(
                symbol=self.benchmark_symbol,
                start=start,
                end=end,
                asset_type="index",
            )
        )
        self._inner = PrecomputedRegimeOverlay(prices)

    @property
    def multipliers(self) -> pd.Series:
        if self._inner is None:
            raise RuntimeError("must call precompute(...) before reading multipliers")
        return self._inner.multipliers

    def multiplier_at(self, date: pd.Timestamp) -> float:
        if self._inner is None:
            raise RuntimeError("must call precompute(...) before multiplier_at")
        return self._inner.multiplier_at(date)
