"""Low-frequency strategy preparation service."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant.analysis.lowfreq import (
    LowFrequencyBacktester,
    LowFrequencyRegimeScorer,
    LowFrequencySignalBuilder,
    SignalConfig,
)
from quant.services.data_service import DataService, PriceRequest


@dataclass(frozen=True)
class LowFrequencySignalRequest:
    """Input model for low-frequency signal generation."""

    symbol: str
    start: str
    end: str
    asset_type: str = "index"
    provider: str = "auto"
    ma_months: int = 10
    vol_window: int = 20
    target_vol: float = 0.20
    max_position: float = 1.0
    transaction_cost: float = 0.0
    regime: str = "none"


class LowFrequencyService:
    """Prepare low-frequency A-share signal frames."""

    def __init__(self, data_service: DataService | None = None) -> None:
        self.data_service = data_service or DataService()

    def build_signals(self, request: LowFrequencySignalRequest) -> pd.DataFrame:
        """Build monthly trend and volatility target signals."""
        prices = self.data_service.get_price(
            PriceRequest(
                symbol=request.symbol,
                start=request.start,
                end=request.end,
                asset_type=request.asset_type,  # type: ignore[arg-type]
                provider=request.provider,
            )
        )
        trading_days = self.data_service.get_trading_days(request.start, request.end)
        builder = LowFrequencySignalBuilder(
            SignalConfig(
                ma_months=request.ma_months,
                vol_window=request.vol_window,
                target_vol=request.target_vol,
                max_position=request.max_position,
            )
        )
        signals = builder.build(prices, trading_days)
        if request.regime == "simple":
            return LowFrequencyRegimeScorer().apply(signals)
        if request.regime != "none":
            raise ValueError(f"Unsupported regime mode: {request.regime}")
        return signals

    def run_backtest(self, request: LowFrequencySignalRequest) -> dict:
        """Build signals and run the benchmark low-frequency backtest."""
        signals = self.build_signals(request)
        backtester = LowFrequencyBacktester(transaction_cost=request.transaction_cost)
        result = backtester.run(signals)
        return {
            "signals": signals,
            "metrics": result.metrics,
            "equity_curve": result.equity_curve,
            "monthly_returns": result.monthly_returns,
        }
