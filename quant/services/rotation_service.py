"""Rotation strategy preparation service."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from quant.analysis.rotation import (
    MomentumRanker,
    PortfolioCombiner,
    RankerConfig,
    RotationBacktestConfig,
    RotationBacktestResult,
    RotationBacktester,
    SimpleRegimeOverlay,
    load_universe,
)
from quant.analysis.rotation.ranker import VolumeFilteredRanker
from quant.analysis.rotation.universe import load_volume_filter_config
from quant.services.data_service import DataService, PriceRequest

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LATEST_SIDECAR = _PROJECT_ROOT / ".quant_cache" / "latest_targets.json"


@dataclass(frozen=True)
class RotationRequest:
    """Input model for rotation backtest / latest target generation."""

    start: str
    end: str
    universe_path: Optional[str] = None
    ranker_config: Optional[RankerConfig] = None
    overlay_benchmark: str = "000300.SH"
    transaction_cost: float = 0.002
    provider: str = "auto"
    overlay_type: str = "simple"   # "simple" | "cockpit"


class RotationService:
    """Wire DataService + universe yaml + rotation pipeline."""

    def __init__(self, data_service: DataService | None = None) -> None:
        self.data_service = data_service or DataService()

    def run_backtest(self, request: RotationRequest) -> RotationBacktestResult:
        """Run the full backtest with the requested configuration."""
        universe = load_universe(request.universe_path)
        vol_config, industry_syms = load_volume_filter_config(request.universe_path)
        monthly_prices, monthly_volumes = self._collect_monthly_prices_and_volumes(universe, request)
        benchmark_prices = self._fetch_benchmark_close(request)
        overlay = self._build_overlay(request)

        inner_ranker = MomentumRanker(request.ranker_config or RankerConfig())
        ranker = VolumeFilteredRanker(
            inner_ranker, monthly_volumes, vol_config, industry_syms,
            per_etf_thresholds=self._per_etf_thresholds(universe),
        )
        combiner = PortfolioCombiner()
        backtester = RotationBacktester(
            RotationBacktestConfig(transaction_cost=request.transaction_cost)
        )
        return backtester.run(
            universe_prices=monthly_prices,
            benchmark_prices=benchmark_prices.reindex(monthly_prices.index).ffill(),
            ranker=ranker,
            overlay=overlay,
            combiner=combiner,
        )

    def latest_targets(self, request: RotationRequest) -> dict:
        """Return the decision payload for the most recent month-end <= request.end.

        Also writes the result to .quant_cache/latest_targets.json for
        quant rotation precheck --from-latest.
        """
        universe = load_universe(request.universe_path)
        vol_config, industry_syms = load_volume_filter_config(request.universe_path)
        monthly_prices, monthly_volumes = self._collect_monthly_prices_and_volumes(universe, request)
        if monthly_prices.empty:
            raise ValueError("no monthly prices available; check date range and universe")

        rebalance_date = monthly_prices.index[-1]
        inner_ranker = MomentumRanker(request.ranker_config or RankerConfig())
        ranker = VolumeFilteredRanker(
            inner_ranker, monthly_volumes, vol_config, industry_syms,
            per_etf_thresholds=self._per_etf_thresholds(universe),
        )
        weights = ranker.rank(monthly_prices, rebalance_date)

        overlay = self._build_overlay(request)
        multiplier = float(overlay.multiplier_at(rebalance_date))

        combiner = PortfolioCombiner()
        final_positions = combiner.combine(weights, multiplier)

        top_n = max(len(weights), (request.ranker_config or RankerConfig()).top_k)
        top_momentum = self._top_momentum(monthly_prices, rebalance_date, top_n, request)

        result = {
            "as_of": rebalance_date.strftime("%Y-%m-%d"),
            "multiplier": multiplier,
            "weights": dict(weights),
            "final_positions": dict(final_positions),
            "top_momentum": top_momentum,
        }
        self._write_latest_sidecar(result)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_monthly_prices_and_volumes(
        self, universe, request: RotationRequest
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Fetch price and volume data in a single pass per symbol.

        Returns (monthly_prices, monthly_volumes) where:
        - monthly_prices: month-end close prices (resample last)
        - monthly_volumes: monthly total volume (resample sum)
        """
        price_frames: dict[str, pd.Series] = {}
        vol_frames: dict[str, pd.Series] = {}
        for entry in universe:
            try:
                df = self.data_service.get_price(
                    PriceRequest(
                        symbol=entry.symbol,
                        start=request.start,
                        end=request.end,
                        asset_type="etf",
                        provider=request.provider,
                    )
                )
            except Exception:
                continue
            if df is None or df.empty:
                continue
            if "close" in df.columns:
                close = df["close"].astype(float)
                close.name = entry.symbol
                monthly_close = close.resample("ME").last().dropna()
                if not monthly_close.empty:
                    price_frames[entry.symbol] = monthly_close
            if "volume" in df.columns:
                vol = df["volume"].astype(float)
                vol.name = entry.symbol
                monthly_vol = vol.resample("ME").sum().dropna()
                if not monthly_vol.empty:
                    vol_frames[entry.symbol] = monthly_vol

        monthly_prices = pd.DataFrame(price_frames).sort_index() if price_frames else pd.DataFrame()
        monthly_volumes = pd.DataFrame(vol_frames).sort_index() if vol_frames else pd.DataFrame()
        return monthly_prices, monthly_volumes

    def _per_etf_thresholds(self, universe) -> dict[str, int]:
        return {
            e.symbol: e.volume_threshold
            for e in universe
            if e.volume_threshold is not None
        }

    def _fetch_benchmark_close(self, request: RotationRequest) -> pd.Series:
        df = self.data_service.get_price(
            PriceRequest(
                symbol=request.overlay_benchmark,
                start=request.start,
                end=request.end,
                asset_type="index",
                provider=request.provider,
            )
        )
        return df["close"].astype(float).resample("ME").last().dropna()

    def _build_overlay(self, request: RotationRequest):
        if request.overlay_type == "simple":
            overlay = SimpleRegimeOverlay(
                data_service=self.data_service,
                benchmark_symbol=request.overlay_benchmark,
            )
        elif request.overlay_type == "cockpit":
            from quant.analysis.rotation import CockpitRegimeOverlay
            overlay = CockpitRegimeOverlay(data_service=self.data_service)
        else:
            raise ValueError(f"unknown overlay_type: {request.overlay_type}")
        overlay.precompute(start=request.start, end=request.end)
        return overlay

    def _top_momentum(
        self,
        monthly_prices: pd.DataFrame,
        rebalance_date: pd.Timestamp,
        top_n: int,
        request: RotationRequest,
    ) -> list[dict]:
        cfg = request.ranker_config or RankerConfig()
        loc = monthly_prices.index.get_loc(rebalance_date)
        end_idx = loc - cfg.skip_recent_months
        start_idx = end_idx - cfg.lookback_months
        if start_idx < 0:
            return []
        end_row = monthly_prices.iloc[end_idx]
        start_row = monthly_prices.iloc[start_idx]
        records = []
        for symbol in monthly_prices.columns:
            if pd.isna(start_row[symbol]) or pd.isna(end_row[symbol]) or start_row[symbol] <= 0:
                continue
            records.append(
                {"symbol": symbol, "momentum": float(end_row[symbol] / start_row[symbol] - 1.0)}
            )
        records.sort(key=lambda r: r["momentum"], reverse=True)
        return records[:top_n]

    @staticmethod
    def _write_latest_sidecar(result: dict) -> None:
        """Write latest_targets to .quant_cache/latest_targets.json (best-effort)."""
        try:
            _LATEST_SIDECAR.parent.mkdir(parents=True, exist_ok=True)
            with _LATEST_SIDECAR.open("w", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Could not write latest sidecar: %s", exc)
