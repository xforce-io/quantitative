"""Multi-sleeve rotation strategy rankers (production path).

This module owns the strategy-level rankers used by the published SOTA
rotation baseline (see config/strategies/rotation/sota.json):

- MinHoldRanker
- MultiSleeveRanker
- PortfolioLevelCBRanker
- RegimeConditionedRanker

Discovery/research scripts and live advisor should import from here rather
than re-implementing the stack in scripts/.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

from quant.analysis.rotation.ranker import MomentumRanker, MultiFactorRanker, RankerConfig

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_UNIVERSE_YAML = _PROJECT_ROOT / "config" / "rotation_universe.yaml"
_DEFAULT_FACTORS_DB = _PROJECT_ROOT / "data" / "factors.db"

# Alias map used by generated strategy specs.
SYMBOL_ALIASES: dict[str, str] = {
    "159941.SZ": "513100.SH",  # Nasdaq ETF alias used in generated specs
}

DEFAULT_REGIME_FILTER: dict = {
    "enabled": False,
    "benchmark_symbol": "000300.SH",
    "benchmark_lookback_months": 6,
    "benchmark_min_return": 0.0,
    "industry_momentum_lookback_months": 6,
    "positive_ratio_threshold": 0.7,
}


def make_ranker_cfg(params: dict) -> RankerConfig:
    """Build RankerConfig from a multi-sleeve allocation / param dict."""
    raw_vol = params.get("vol_penalty", 0.0)
    vol_penalty = float(raw_vol) if raw_vol is not None and not isinstance(raw_vol, dict) else 0.0
    return RankerConfig(
        lookback_months=int(params.get("lookback_months", 6)),
        skip_recent_months=int(params.get("skip_months", params.get("skip_recent_months", 1))),
        top_k=int(params.get("top_k", 3)),
        vol_penalty=vol_penalty,
        vol_lookback_months=int(params.get("vol_lookback_months", 0) or 0),
        vol_formula=str(params.get("vol_formula", "exponent")),
    )


def load_sleeve_map(universe_path: Path | str | None = None) -> dict[str, list[str]]:
    """Load sleeve name -> symbol list mapping from rotation_universe.yaml."""
    path = Path(universe_path) if universe_path is not None else _DEFAULT_UNIVERSE_YAML
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except Exception:
        return {}
    return {
        key.replace("_etfs", ""): [str(item["symbol"]) for item in values if "symbol" in item]
        for key, values in raw.items()
        if isinstance(values, list)
    }


def resolve_sota_spec_path(project_root: Path | None = None) -> Path:
    """Resolve the strategy spec path referenced by sota.json."""
    root = project_root or _PROJECT_ROOT
    sota_path = root / "config" / "strategies" / "rotation" / "sota.json"
    import json

    sota = json.loads(sota_path.read_text(encoding="utf-8"))
    return root / sota["strategy_path"]


def load_strategy_spec(path: Path | str | None = None) -> dict:
    """Load a multi-sleeve strategy spec JSON (defaults to published SOTA)."""
    import json

    if path is None or path == "" or path == "sota":
        resolved = resolve_sota_spec_path()
    else:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = _PROJECT_ROOT / resolved
    return json.loads(resolved.read_text(encoding="utf-8"))


class MinHoldRanker:
    """Wrap an inner ranker with a minimum hold period (months) constraint.

    The hold constraint only applies when the portfolio is non-empty (invested).
    Cash (empty portfolio) can always be exited immediately.
    """

    def __init__(self, inner, min_hold_months: int = 1) -> None:
        self.inner = inner
        self.min_hold = max(1, int(min_hold_months))
        self._current: dict[str, float] = {}
        self._last_change_loc: int | None = None

    def rank(self, monthly_prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        loc = monthly_prices.index.get_loc(rebalance_date)

        if (
            self._current
            and self._last_change_loc is not None
            and (loc - self._last_change_loc) < self.min_hold
        ):
            return self._current

        new = self.inner.rank(monthly_prices, rebalance_date)
        if new != self._current:
            self._current = new
            self._last_change_loc = loc
        return self._current


class RegimeConditionedRanker:
    """Turn the inner ranker on only in a simple, predeclared risk-on regime.

    defensive_mode: "cash" (empty portfolio) or "broad_index" (hold defensive_asset).
    """

    def __init__(
        self,
        inner,
        monthly_benchmark: pd.Series,
        regime_filter: dict | None = None,
        defensive_mode: str = "cash",
        defensive_asset: str | None = None,
    ) -> None:
        self.inner = inner
        self.monthly_benchmark = monthly_benchmark.sort_index()
        self.regime_filter = {**DEFAULT_REGIME_FILTER, **(regime_filter or {})}
        self.defensive_mode = defensive_mode
        self.defensive_asset = defensive_asset
        self.stats = {"risk_on_periods": 0, "risk_off_periods": 0}

    def rank(self, monthly_prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        if not self.regime_filter.get("enabled", False):
            return self.inner.rank(monthly_prices, rebalance_date)

        if self._is_risk_on(monthly_prices, rebalance_date):
            self.stats["risk_on_periods"] += 1
            return self.inner.rank(monthly_prices, rebalance_date)

        self.stats["risk_off_periods"] += 1
        if (
            self.defensive_mode == "broad_index"
            and self.defensive_asset
            and self.defensive_asset in monthly_prices.columns
        ):
            return {self.defensive_asset: 1.0}
        return {}

    def _is_risk_on(self, monthly_prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> bool:
        loc = monthly_prices.index.get_loc(rebalance_date)
        benchmark_lookback = int(self.regime_filter["benchmark_lookback_months"])

        if not self._benchmark_return_ok(rebalance_date, benchmark_lookback):
            return False

        threshold = self.regime_filter.get("positive_ratio_threshold")
        if threshold is None:
            return True

        momentum_lookback = int(
            self.regime_filter.get("industry_momentum_lookback_months", benchmark_lookback)
        )
        return self._positive_ratio_ok(monthly_prices, loc, momentum_lookback, float(threshold))

    def _benchmark_return_ok(self, rebalance_date: pd.Timestamp, lookback_months: int) -> bool:
        bench = (
            self.monthly_benchmark.reindex(self.monthly_benchmark.index.union([rebalance_date]))
            .sort_index()
            .ffill()
        )
        if rebalance_date not in bench.index:
            return False
        loc = bench.index.get_loc(rebalance_date)
        start_idx = loc - lookback_months
        if start_idx < 0:
            return False
        p0 = bench.iloc[start_idx]
        p1 = bench.iloc[loc]
        if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
            return False
        ret = float(p1 / p0 - 1.0)
        return ret > float(self.regime_filter["benchmark_min_return"])

    def _positive_ratio_ok(
        self, monthly_prices: pd.DataFrame, loc: int, lookback_months: int, threshold: float
    ) -> bool:
        start_idx = loc - lookback_months
        if start_idx < 0:
            return False
        start_row = monthly_prices.iloc[start_idx]
        end_row = monthly_prices.iloc[loc]
        valid = 0
        positive = 0
        for symbol in monthly_prices.columns:
            p0 = start_row[symbol]
            p1 = end_row[symbol]
            if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
                continue
            valid += 1
            if float(p1 / p0 - 1.0) > 0.0:
                positive += 1
        if valid == 0:
            return False
        return (positive / valid) >= threshold


class MultiSleeveRanker:
    """Allocate capital across risk-on / risk-off sleeves based on a regime rule."""

    def __init__(
        self,
        monthly_benchmark: pd.Series,
        risk_on_rule: dict,
        risk_on_allocation: dict,
        risk_off_allocation: dict,
        monthly_volumes: Optional[pd.DataFrame] = None,
        sleeve_map: Optional[dict[str, list[str]]] = None,
        factor_store=None,
        symbol_aliases: Optional[dict[str, str]] = None,
    ) -> None:
        self.monthly_benchmark = monthly_benchmark.sort_index()
        self.risk_on_rule = risk_on_rule or {}
        self.risk_on_allocation = risk_on_allocation or {}
        self.risk_off_allocation = risk_off_allocation or {}
        self.sleeve_map = sleeve_map if sleeve_map is not None else load_sleeve_map()
        self.symbol_aliases = symbol_aliases if symbol_aliases is not None else dict(SYMBOL_ALIASES)

        if factor_store is not None:
            self._factor_store = factor_store
        else:
            try:
                from quant.data.factor_store import FactorStore

                self._factor_store = FactorStore(db_path=str(_DEFAULT_FACTORS_DB))
            except Exception:
                self._factor_store = None

        momentum_method = self.risk_on_allocation.get("momentum_score_method", "pure_momentum")
        if momentum_method == "multi_factor_rank":
            inner_ranker = MultiFactorRanker(
                self.risk_on_allocation,
                monthly_volumes,
                monthly_benchmark=self.monthly_benchmark,
                factor_store=self._factor_store,
            )
        else:
            inner_ranker = MomentumRanker(make_ranker_cfg(self.risk_on_allocation))

        self.risk_on_ranker = MinHoldRanker(
            inner_ranker,
            self.risk_on_allocation.get("min_hold_months", 1),
        )
        self.risk_off_ranker = None
        if self.risk_off_allocation.get("mode") not in (
            "fixed_equal_weight",
            "cash",
            "fixed_asset",
            "fixed",
        ):
            self.risk_off_ranker = MinHoldRanker(
                MomentumRanker(make_ranker_cfg(self.risk_off_allocation)),
                self.risk_off_allocation.get("min_hold_months", 1),
            )

        self.stats = {
            "risk_on_periods": 0,
            "risk_off_periods": 0,
            "circuit_breaker_triggers": [],
            "pmi_veto_periods": 0,
            "pmi_veto_csi300_returns": [],
        }
        self._regime_state: str | None = None
        self._cb_forced_hold: int = 0
        self._cb_current_sym: str | None = None
        self._cb_peak_price: float | None = None

    def _alias(self, symbol: str) -> str:
        return self.symbol_aliases.get(symbol, symbol)

    def rank(self, monthly_prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        is_risk_on = self._is_risk_on(monthly_prices, rebalance_date)

        if is_risk_on:
            self.stats["risk_on_periods"] += 1
            self._cb_current_sym = None
            self._cb_peak_price = None
            sleeve = self.risk_on_allocation.get("sleeve", "industry")
            symbols = self.sleeve_map.get(sleeve, list(monthly_prices.columns))
            valid_symbols = [c for c in symbols if c in monthly_prices.columns]
        else:
            self.stats["risk_off_periods"] += 1
            if self.risk_off_allocation.get("mode") in (
                "fixed_equal_weight",
                "fixed_asset",
                "fixed",
            ):
                return self._fixed_weights(monthly_prices)

            cb_cfg = self.risk_off_allocation.get("trailing_drawdown_circuit_breaker", {})
            if cb_cfg.get("enabled") and self._cb_forced_hold > 0:
                self._cb_forced_hold -= 1
                fb_raw = cb_cfg.get("fallback_asset", "511880.SH")
                fb = self._alias(fb_raw)
                if fb in monthly_prices.columns and rebalance_date in monthly_prices.index:
                    price = float(monthly_prices.at[rebalance_date, fb])
                    if not pd.isna(price) and price > 0:
                        self._cb_current_sym = fb
                        self._cb_peak_price = max(self._cb_peak_price or price, price)
                return {fb: 1.0} if fb in monthly_prices.columns else {}

            candidates_cfg = self.risk_off_allocation.get("candidates", [])
            if candidates_cfg:
                candidate_syms = [
                    self._alias(c.get("real_etf", ""))
                    for c in candidates_cfg
                    if c.get("real_etf")
                ]
                valid_symbols = [s for s in candidate_syms if s in monthly_prices.columns]
            else:
                sleeve = self.risk_off_allocation.get("sleeve", "defensive_global")
                symbols = self.sleeve_map.get(sleeve, list(monthly_prices.columns))
                valid_symbols = [c for c in symbols if c in monthly_prices.columns]

        if not valid_symbols:
            return {}

        slice_df = monthly_prices[valid_symbols]
        if is_risk_on:
            result = self.risk_on_ranker.rank(slice_df, rebalance_date)
            cg = self.risk_on_allocation.get("concentration_guard", {})
            if cg.get("enabled") and result:
                min_etfs = int(cg.get("min_effective_etfs", 3))
                if len(result) < min_etfs:
                    fallback = "510300.SH"
                    if fallback in monthly_prices.columns and fallback not in result:
                        result = {**result, fallback: 1.0}
                        weight = 1.0 / len(result)
                        result = {k: weight for k in result}
            if not result:
                fallback_etf = self.risk_on_allocation.get("fallback_etf")
                if fallback_etf:
                    symbol = self._alias(fallback_etf)
                    if symbol in monthly_prices.columns:
                        return {symbol: 1.0}
            return result

        if self.risk_off_ranker is None:
            return {}
        result = self.risk_off_ranker.rank(slice_df, rebalance_date)
        if not result:
            floor_cfg = self.risk_off_allocation.get("floor_rule", {})
            if floor_cfg.get("enabled"):
                fallback = floor_cfg.get("fallback_asset", "511880.SH")
                fallback_sym = self._alias(fallback)
                if fallback_sym in monthly_prices.columns:
                    result = {fallback_sym: 1.0}
        if not result:
            return {}

        cb_cfg = self.risk_off_allocation.get("trailing_drawdown_circuit_breaker", {})
        if cb_cfg.get("enabled") and rebalance_date in monthly_prices.index:
            sel_sym = next(iter(result))
            if sel_sym in monthly_prices.columns:
                curr_p = float(monthly_prices.at[rebalance_date, sel_sym])
                if not pd.isna(curr_p) and curr_p > 0:
                    if sel_sym != self._cb_current_sym:
                        self._cb_current_sym = sel_sym
                        self._cb_peak_price = curr_p
                    else:
                        self._cb_peak_price = max(self._cb_peak_price or curr_p, curr_p)
                    cb_thr = float(cb_cfg.get("threshold", -0.15))
                    if self._cb_peak_price and self._cb_peak_price > 0:
                        drawdown = curr_p / self._cb_peak_price - 1.0
                        if drawdown < cb_thr:
                            min_hold_after = int(cb_cfg.get("min_hold_after_trigger_months", 1))
                            self._cb_forced_hold = max(0, min_hold_after - 1)
                            fb_raw = cb_cfg.get("fallback_asset", "511880.SH")
                            fb = self._alias(fb_raw)
                            self.stats["circuit_breaker_triggers"].append(
                                {
                                    "date": str(rebalance_date.date()),
                                    "symbol": sel_sym,
                                    "drawdown_from_peak": round(drawdown, 4),
                                    "peak_price": round(self._cb_peak_price, 4),
                                    "current_price": round(curr_p, 4),
                                }
                            )
                            if fb in monthly_prices.columns:
                                fb_p = float(monthly_prices.at[rebalance_date, fb])
                                self._cb_current_sym = fb
                                self._cb_peak_price = fb_p if not pd.isna(fb_p) else None
                                return {fb: 1.0}
                            return {}
        return result

    def _fixed_weights(self, monthly_prices: pd.DataFrame) -> dict[str, float]:
        raw_weights = self.risk_off_allocation.get("weights") or {}
        weights: dict[str, float] = {}
        for raw_symbol, raw_weight in raw_weights.items():
            symbol = self._alias(raw_symbol)
            if symbol not in monthly_prices.columns:
                continue
            weight = float(raw_weight)
            if weight > 0:
                weights[symbol] = weights.get(symbol, 0.0) + weight

        total = sum(weights.values())
        if total <= 0:
            return {}
        return {symbol: weight / total for symbol, weight in weights.items()}

    def _is_risk_on(self, monthly_prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> bool:
        method = self.risk_on_rule.get("method", "return_threshold")
        bench = (
            self.monthly_benchmark.reindex(self.monthly_benchmark.index.union([rebalance_date]))
            .sort_index()
            .ffill()
        )
        if rebalance_date not in bench.index:
            return False
        loc = bench.index.get_loc(rebalance_date)

        if method in ("asymmetric_return_threshold", "asymmetric_dual_threshold"):
            return self._asymmetric_is_risk_on(bench, loc)

        if method == "ma_cross":
            ma_period = int(self.risk_on_rule.get("ma_period", 12))
            if loc < ma_period:
                return False
            ma = float(bench.iloc[loc - ma_period + 1 : loc + 1].mean())
            current = float(bench.iloc[loc])
            return not (pd.isna(current) or pd.isna(ma) or ma <= 0) and current > ma

        if method == "dual_return_threshold":
            lookback_long = int(self.risk_on_rule.get("lookback_months", 6))
            min_return_long = float(self.risk_on_rule.get("min_return", 0.0))
            start_long = loc - lookback_long
            if start_long < 0:
                return False
            p0_l, p1_l = bench.iloc[start_long], bench.iloc[loc]
            if pd.isna(p0_l) or pd.isna(p1_l) or p0_l <= 0:
                return False
            if float(p1_l / p0_l - 1.0) <= min_return_long:
                return False
            lookback_short = int(self.risk_on_rule.get("lookback_months_short", 3))
            min_return_short = float(self.risk_on_rule.get("min_return_short", 0.0))
            start_short = loc - lookback_short
            if start_short < 0:
                return False
            p0_s, p1_s = bench.iloc[start_short], bench.iloc[loc]
            if pd.isna(p0_s) or pd.isna(p1_s) or p0_s <= 0:
                return False
            return float(p1_s / p0_s - 1.0) > min_return_short

        # default / simple_threshold / return_threshold
        lookback = int(self.risk_on_rule.get("lookback_months", 6))
        raw_min_return = self.risk_on_rule.get("min_return")
        min_return = float(raw_min_return) if raw_min_return is not None else 0.0
        start_idx = loc - lookback
        if start_idx < 0:
            return False
        p0 = bench.iloc[start_idx]
        p1 = bench.iloc[loc]
        if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
            return False
        ret = float(p1 / p0 - 1.0)
        if ret <= min_return:
            return False
        return not self._pmi_veto(rebalance_date, bench, loc, lookback)

    def _asymmetric_is_risk_on(self, bench: pd.Series, loc: int) -> bool:
        entry_lookback = int(self.risk_on_rule.get("entry_lookback_months", 3))
        entry_min_return = float(self.risk_on_rule.get("entry_min_return", 0.0))
        exit_lookback = int(self.risk_on_rule.get("exit_lookback_months", 6))
        exit_max_return = float(self.risk_on_rule.get("exit_max_return", -0.03))

        if self._regime_state is None:
            start_idx = loc - entry_lookback
            if start_idx < 0:
                self._regime_state = "risk_off"
            else:
                p0, p1 = bench.iloc[start_idx], bench.iloc[loc]
                if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
                    self._regime_state = "risk_off"
                else:
                    ret = float(p1 / p0 - 1.0)
                    self._regime_state = "risk_on" if ret > entry_min_return else "risk_off"

        if self._regime_state == "risk_on":
            start_idx = loc - exit_lookback
            if start_idx >= 0:
                p0, p1 = bench.iloc[start_idx], bench.iloc[loc]
                if not (pd.isna(p0) or pd.isna(p1) or p0 <= 0):
                    if float(p1 / p0 - 1.0) < exit_max_return:
                        self._regime_state = "risk_off"
                        return False
            return True

        start_idx = loc - entry_lookback
        if start_idx >= 0:
            p0, p1 = bench.iloc[start_idx], bench.iloc[loc]
            if not (pd.isna(p0) or pd.isna(p1) or p0 <= 0):
                if float(p1 / p0 - 1.0) > entry_min_return:
                    self._regime_state = "risk_on"
                    return True
        return False

    def _pmi_veto(
        self, rebalance_date: pd.Timestamp, bench: pd.Series, loc: int, lookback: int
    ) -> bool:
        if not self.risk_on_rule.get("pmi_overlay_enabled", False):
            return False
        if self._factor_store is None:
            return False
        ym_prefix = rebalance_date.strftime("%Y-%m")
        pmi_val = self._factor_store.get_pmi_by_month(ym_prefix)
        if pmi_val is None:
            return False
        threshold = float(self.risk_on_rule.get("pmi_threshold", 49.0))
        if pmi_val < threshold:
            bench_ret = float("nan")
            start_idx = loc - lookback
            if start_idx >= 0 and loc < len(bench):
                p0, p1 = bench.iloc[start_idx], bench.iloc[loc]
                if not pd.isna(p0) and not pd.isna(p1) and p0 > 0:
                    bench_ret = float(p1 / p0 - 1.0)
            self.stats["pmi_veto_periods"] += 1
            self.stats["pmi_veto_csi300_returns"].append(bench_ret)
            return True
        return False


class PortfolioLevelCBRanker:
    """Portfolio-level trailing drawdown circuit breaker around MultiSleeveRanker.

    Tracks strategy NAV from inception. When NAV / all_time_peak - 1 <= threshold,
    overrides the risk_off sleeve to hold fallback_asset. CB only fires during
    risk_off periods; risk_on positions are unaffected.
    """

    def __init__(
        self,
        inner: MultiSleeveRanker,
        threshold: float = -0.25,
        fallback_asset: str = "511880.SH",
        symbol_aliases: Optional[dict[str, str]] = None,
    ) -> None:
        self.inner = inner
        self.threshold = threshold
        self.fallback_raw = fallback_asset
        self.symbol_aliases = symbol_aliases if symbol_aliases is not None else dict(SYMBOL_ALIASES)
        self._nav: float = 1.0
        self._peak_nav: float = 1.0
        self._prev_positions: dict[str, float] = {}
        self._prev_date: pd.Timestamp | None = None
        self.stats: dict = {"portfolio_cb_triggers": []}

    def rank(self, monthly_prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        if (
            self._prev_date is not None
            and self._prev_positions
            and self._prev_date in monthly_prices.index
            and rebalance_date in monthly_prices.index
        ):
            period_ret = 0.0
            for sym, weight in self._prev_positions.items():
                if sym in monthly_prices.columns:
                    p0 = float(monthly_prices.at[self._prev_date, sym])
                    p1 = float(monthly_prices.at[rebalance_date, sym])
                    if not pd.isna(p0) and not pd.isna(p1) and p0 > 0:
                        period_ret += weight * (p1 / p0 - 1.0)
            self._nav *= 1.0 + period_ret

        self._peak_nav = max(self._peak_nav, self._nav)
        drawdown = self._nav / self._peak_nav - 1.0 if self._peak_nav > 0 else 0.0
        cb_condition_met = drawdown <= self.threshold

        risk_off_before = self.inner.stats["risk_off_periods"]
        result = self.inner.rank(monthly_prices, rebalance_date)
        is_risk_off = self.inner.stats["risk_off_periods"] > risk_off_before

        if cb_condition_met and is_risk_off:
            fallback = self.symbol_aliases.get(self.fallback_raw, self.fallback_raw)
            if fallback in monthly_prices.columns:
                self.stats["portfolio_cb_triggers"].append(
                    {
                        "date": str(rebalance_date.date()),
                        "portfolio_drawdown": round(drawdown, 4),
                        "nav": round(self._nav, 4),
                        "peak_nav": round(self._peak_nav, 4),
                        "original_risk_off_result": dict(result),
                    }
                )
                result = {fallback: 1.0}

        self._prev_positions = dict(result)
        self._prev_date = rebalance_date
        return result


def build_ranker_from_spec(
    spec: dict,
    monthly_benchmark: pd.Series,
    monthly_volumes: Optional[pd.DataFrame] = None,
    sleeve_map: Optional[dict[str, list[str]]] = None,
    factor_store=None,
    enable_portfolio_cb: bool = True,
):
    """Build MultiSleeveRanker (optionally wrapped with portfolio CB) from a strategy spec."""
    sleeve_ranker = MultiSleeveRanker(
        monthly_benchmark=monthly_benchmark,
        risk_on_rule=spec.get("risk_on_rule", {}),
        risk_on_allocation=spec.get("risk_on_allocation", {}),
        risk_off_allocation=spec.get("risk_off_allocation", {}),
        monthly_volumes=monthly_volumes,
        sleeve_map=sleeve_map,
        factor_store=factor_store,
    )
    portfolio_cb_cfg = (spec.get("risk_off_allocation", {}) or {}).get(
        "portfolio_trailing_drawdown_circuit_breaker", {}
    )
    if enable_portfolio_cb and portfolio_cb_cfg.get("enabled", False):
        return PortfolioLevelCBRanker(
            sleeve_ranker,
            threshold=float(portfolio_cb_cfg.get("threshold", -0.25)),
            fallback_asset=portfolio_cb_cfg.get("fallback_asset", "511880.SH"),
        )
    return sleeve_ranker
