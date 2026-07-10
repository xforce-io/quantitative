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
    build_ranker_from_spec,
    load_strategy_spec,
    load_universe,
)
from quant.analysis.rotation.ranker import VolumeFilteredRanker
from quant.analysis.rotation.universe import load_volume_filter_config
from quant.services.data_service import DataService, PriceRequest

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LATEST_SIDECAR = _PROJECT_ROOT / ".quant_cache" / "latest_targets.json"


class _PassThroughOverlay:
    """Identity overlay used by multi-sleeve strategies (they own regime logic)."""

    def multiplier_at(self, date: pd.Timestamp) -> float:
        return 1.0


@dataclass(frozen=True)
class RotationRequest:
    """Input model for rotation backtest / latest target generation.

    strategy_mode:
      - "sota": multi-sleeve production baseline (default)
      - "simple": legacy pure-momentum + A-layer regime overlay
    strategy_spec:
      path or "sota"; only used when strategy_mode == "sota"
    """

    start: str
    end: str
    universe_path: Optional[str] = None
    ranker_config: Optional[RankerConfig] = None
    overlay_benchmark: str = "000300.SH"
    transaction_cost: float = 0.002
    provider: str = "auto"
    overlay_type: str = "simple"  # "simple" | "cockpit" (simple mode only)
    strategy_mode: str = "sota"  # "sota" | "simple"
    strategy_spec: Optional[str] = None  # path / "sota"; default published SOTA


class RotationService:
    """Wire DataService + universe yaml + rotation pipeline."""

    def __init__(self, data_service: DataService | None = None) -> None:
        self.data_service = data_service or DataService()

    def run_backtest(self, request: RotationRequest) -> RotationBacktestResult:
        """Run the full backtest with the requested configuration."""
        if request.strategy_mode == "simple":
            return self._run_simple_backtest(request)
        return self._run_multisleeve_backtest(request)

    def latest_targets(self, request: RotationRequest) -> dict:
        """Return the decision payload for the most recent month-end <= request.end.

        Also writes the result to .quant_cache/latest_targets.json for
        quant rotation precheck --from-latest.
        """
        if request.strategy_mode == "simple":
            result = self._latest_simple(request)
        else:
            result = self._latest_multisleeve(request)
        self._write_latest_sidecar(result)
        return result

    # ------------------------------------------------------------------
    # Multi-sleeve (production / SOTA) path
    # ------------------------------------------------------------------

    def _run_multisleeve_backtest(self, request: RotationRequest) -> RotationBacktestResult:
        spec = load_strategy_spec(request.strategy_spec)
        universe = load_universe(request.universe_path)
        monthly_prices, monthly_volumes = self._collect_monthly_prices_and_volumes(
            universe, request
        )
        if monthly_prices.empty:
            raise ValueError("no monthly prices available; check date range and universe")

        benchmark_prices = self._fetch_benchmark_close(request)
        ranker = build_ranker_from_spec(
            spec,
            monthly_benchmark=benchmark_prices,
            monthly_volumes=monthly_volumes if self._spec_needs_volume(spec) else None,
            enable_portfolio_cb=True,
        )
        combiner = PortfolioCombiner()
        backtester = RotationBacktester(
            RotationBacktestConfig(transaction_cost=request.transaction_cost)
        )
        return backtester.run(
            universe_prices=monthly_prices,
            benchmark_prices=benchmark_prices.reindex(monthly_prices.index).ffill(),
            ranker=ranker,
            overlay=_PassThroughOverlay(),
            combiner=combiner,
        )

    def _latest_multisleeve(self, request: RotationRequest) -> dict:
        spec = load_strategy_spec(request.strategy_spec)
        universe = load_universe(request.universe_path)
        monthly_prices, monthly_volumes = self._collect_monthly_prices_and_volumes(
            universe, request
        )
        if monthly_prices.empty:
            raise ValueError("no monthly prices available; check date range and universe")

        rebalance_date = monthly_prices.index[-1]
        benchmark_prices = self._fetch_benchmark_close(request)

        # Live path: portfolio CB needs full NAV history; disable with explicit note.
        portfolio_cb_cfg = (spec.get("risk_off_allocation", {}) or {}).get(
            "portfolio_trailing_drawdown_circuit_breaker", {}
        )
        portfolio_cb_enabled = bool(portfolio_cb_cfg.get("enabled", False))
        ranker = build_ranker_from_spec(
            spec,
            monthly_benchmark=benchmark_prices,
            monthly_volumes=monthly_volumes if self._spec_needs_volume(spec) else None,
            enable_portfolio_cb=False,
        )

        method = (spec.get("risk_on_rule", {}) or {}).get("method", "simple_threshold")
        needs_warmup = method not in ("simple_threshold", "return_threshold", None)
        if needs_warmup:
            for date in monthly_prices.index:
                if date > rebalance_date:
                    break
                try:
                    ranker.rank(monthly_prices, date)
                except Exception:
                    continue

        weights = ranker.rank(monthly_prices, rebalance_date)

        # Prefer MultiSleeveRanker._is_risk_on when available.
        is_risk_on = None
        inner = getattr(ranker, "inner", ranker)
        if hasattr(inner, "_is_risk_on"):
            try:
                is_risk_on = bool(inner._is_risk_on(monthly_prices, rebalance_date))
            except Exception:
                is_risk_on = None

        csi6m = self._csi300_return(benchmark_prices, rebalance_date, months=6)
        top_n = int((spec.get("risk_on_allocation", {}) or {}).get("top_k", 3))
        top_momentum = self._top_momentum(
            monthly_prices,
            rebalance_date,
            top_n,
            RankerConfig(
                lookback_months=int(
                    (spec.get("risk_on_allocation", {}) or {}).get("lookback_months", 6)
                ),
                skip_recent_months=int(
                    (spec.get("risk_on_allocation", {}) or {}).get("skip_months", 1)
                ),
                top_k=top_n,
            ),
        )

        return {
            "as_of": rebalance_date.strftime("%Y-%m-%d"),
            "strategy_id": spec.get("strategy_id") or spec.get("iteration"),
            "strategy_mode": "sota",
            "regime": "risk_on" if is_risk_on else ("risk_off" if is_risk_on is not None else None),
            "csi300_6m_return": csi6m,
            "multiplier": 1.0,
            "weights": dict(weights),
            "final_positions": dict(weights),
            "top_momentum": top_momentum,
            "portfolio_cb_active": False,
            "portfolio_cb_note": (
                "portfolio circuit breaker disabled in latest mode (no live NAV history)"
                if portfolio_cb_enabled
                else None
            ),
        }

    # ------------------------------------------------------------------
    # Simple (legacy) path
    # ------------------------------------------------------------------

    def _run_simple_backtest(self, request: RotationRequest) -> RotationBacktestResult:
        universe = load_universe(request.universe_path)
        vol_config, industry_syms = load_volume_filter_config(request.universe_path)
        monthly_prices, monthly_volumes = self._collect_monthly_prices_and_volumes(
            universe, request
        )
        benchmark_prices = self._fetch_benchmark_close(request)
        overlay = self._build_overlay(request)

        inner_ranker = MomentumRanker(request.ranker_config or RankerConfig())
        ranker = VolumeFilteredRanker(
            inner_ranker,
            monthly_volumes,
            vol_config,
            industry_syms,
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

    def _latest_simple(self, request: RotationRequest) -> dict:
        universe = load_universe(request.universe_path)
        vol_config, industry_syms = load_volume_filter_config(request.universe_path)
        monthly_prices, monthly_volumes = self._collect_monthly_prices_and_volumes(
            universe, request
        )
        if monthly_prices.empty:
            raise ValueError("no monthly prices available; check date range and universe")

        rebalance_date = monthly_prices.index[-1]
        inner_ranker = MomentumRanker(request.ranker_config or RankerConfig())
        ranker = VolumeFilteredRanker(
            inner_ranker,
            monthly_volumes,
            vol_config,
            industry_syms,
            per_etf_thresholds=self._per_etf_thresholds(universe),
        )
        weights = ranker.rank(monthly_prices, rebalance_date)

        overlay = self._build_overlay(request)
        multiplier = float(overlay.multiplier_at(rebalance_date))
        combiner = PortfolioCombiner()
        final_positions = combiner.combine(weights, multiplier)

        top_n = max(len(weights), (request.ranker_config or RankerConfig()).top_k)
        top_momentum = self._top_momentum(
            monthly_prices, rebalance_date, top_n, request.ranker_config or RankerConfig()
        )

        return {
            "as_of": rebalance_date.strftime("%Y-%m-%d"),
            "strategy_mode": "simple",
            "multiplier": multiplier,
            "weights": dict(weights),
            "final_positions": dict(final_positions),
            "top_momentum": top_momentum,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _spec_needs_volume(spec: dict) -> bool:
        factors = (
            (spec.get("risk_on_allocation", {}) or {})
            .get("multi_factor_config", {})
            .get("factors", [])
        )
        names = {f.get("name") for f in factors}
        return bool(names & {"shares_momentum", "low_crowding"})

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
        start_ts = pd.to_datetime(request.start)
        end_ts = pd.to_datetime(request.end)
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
            df = self._bound_price_frame(df, start_ts, end_ts)
            if df.empty:
                continue
            if "close" in df.columns:
                close = df["close"].astype(float)
                close.name = entry.symbol
                monthly_close = close.resample("ME").last().dropna()
                monthly_close = monthly_close[monthly_close.index <= end_ts]
                if not monthly_close.empty:
                    price_frames[entry.symbol] = monthly_close
            if "volume" in df.columns:
                vol = df["volume"].astype(float)
                vol.name = entry.symbol
                monthly_vol = vol.resample("ME").sum().dropna()
                monthly_vol = monthly_vol[monthly_vol.index <= end_ts]
                if not monthly_vol.empty:
                    vol_frames[entry.symbol] = monthly_vol

        monthly_prices = (
            pd.DataFrame(price_frames).sort_index() if price_frames else pd.DataFrame()
        )
        monthly_volumes = (
            pd.DataFrame(vol_frames).sort_index() if vol_frames else pd.DataFrame()
        )
        return monthly_prices, monthly_volumes

    def _per_etf_thresholds(self, universe) -> dict[str, int]:
        return {
            e.symbol: e.volume_threshold
            for e in universe
            if e.volume_threshold is not None
        }

    @staticmethod
    def _bound_price_frame(
        df: pd.DataFrame,
        start_ts: pd.Timestamp,
        end_ts: pd.Timestamp,
    ) -> pd.DataFrame:
        bounded = df.copy()
        if not isinstance(bounded.index, pd.DatetimeIndex):
            if "trade_date" in bounded.columns:
                bounded.index = pd.to_datetime(bounded["trade_date"])
            else:
                bounded.index = pd.to_datetime(bounded.index)
        bounded = bounded.sort_index()
        return bounded[(bounded.index >= start_ts) & (bounded.index <= end_ts)]

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
        start_ts = pd.to_datetime(request.start)
        end_ts = pd.to_datetime(request.end)
        df = self._bound_price_frame(df, start_ts, end_ts)
        close = df["close"].astype(float).resample("ME").last().dropna()
        return close[close.index <= end_ts]

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

    @staticmethod
    def _csi300_return(
        benchmark: pd.Series, rebalance_date: pd.Timestamp, months: int = 6
    ) -> float | None:
        if benchmark.empty or rebalance_date not in benchmark.index:
            return None
        loc = benchmark.index.get_loc(rebalance_date)
        start_idx = loc - months
        if start_idx < 0:
            return None
        p0, p1 = benchmark.iloc[start_idx], benchmark.iloc[loc]
        if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
            return None
        return float(p1 / p0 - 1.0)

    def _top_momentum(
        self,
        monthly_prices: pd.DataFrame,
        rebalance_date: pd.Timestamp,
        top_n: int,
        cfg: RankerConfig,
    ) -> list[dict]:
        loc = monthly_prices.index.get_loc(rebalance_date)
        end_idx = loc - cfg.skip_recent_months
        start_idx = end_idx - cfg.lookback_months
        if start_idx < 0:
            return []
        end_row = monthly_prices.iloc[end_idx]
        start_row = monthly_prices.iloc[start_idx]
        records = []
        for symbol in monthly_prices.columns:
            if (
                pd.isna(start_row[symbol])
                or pd.isna(end_row[symbol])
                or start_row[symbol] <= 0
            ):
                continue
            records.append(
                {
                    "symbol": symbol,
                    "momentum": float(end_row[symbol] / start_row[symbol] - 1.0),
                }
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
