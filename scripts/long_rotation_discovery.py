#!/usr/bin/env python3
"""Long-term multi-mode rotation discovery backtest.

Three data modes validated per run:
  index_proxy    -- proxy indices for ETF universe, 2010-2024 (>= 10 yr OOS)
  real_etf_subset -- real ETFs with data from <= 2014-12-31, 2014-2024
  real_etf_full   -- full current ETF pool, 2018-2024

Usage:
  python scripts/long_rotation_discovery.py \
      --mode baseline \
      --output .petri/artifacts/backtest/backtester/backtest_result.json

  python scripts/long_rotation_discovery.py \
      --mode candidate \
      --params-file .petri/artifacts/design/strategy_designer/strategy_spec.json \
      --output .petri/artifacts/backtest/backtester/backtest_result.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import yaml
from calendar import monthrange
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from quant.analysis.rotation import (
    MomentumRanker,
    MultiFactorRanker,
    PortfolioCombiner,
    RankerConfig,
    RotationBacktestConfig,
    RotationBacktester,
    load_universe,
)
from quant.analysis.rotation.frequency import BacktestFrequency, months_to_bars, resample_rule
from quant.analysis.rotation.regime_overlay import PrecomputedRegimeOverlay
from quant.data.factor_store import FactorStore
from quant.services.data_service import DataService, PriceRequest

UNIVERSE_YAML = _ROOT / "config" / "rotation_universe.yaml"

TRAIN_MONTHS = 24
TEST_MONTHS = 6
STEP_MONTHS = 6
WARMUP_MONTHS = 15  # >= lookback(9) + skip(1) + buffer

SUBSET_CUTOFF_TS = pd.Timestamp("2014-12-31")

# Single-day |return| threshold above which an ETF's price series is presumed
# contaminated by a share split / merger that the data provider failed to
# adjustment. Diversified ETFs cannot move > ±25% in one day under any
# real market scenario, so this is a hard data-integrity floor.
# See docs/incidents/2026-05-etf-split-data-anomaly.md for the root cause.
MAX_SINGLE_DAY_ABS_RET = 0.25

BASELINE_PARAMS = {
    "lookback_months": 6,
    "skip_months": 1,
    "top_k": 3,
    "min_hold_months": 1,
    "vol_penalty": 0.0,
}

# Baseline for comparison: pure momentum + simple_threshold 6m regime switching
# (same regime rule as candidate; all three data modes must use this consistently)
SIMPLE_THRESHOLD_BASELINE_MULTI_SLEEVE: dict = {
    "strategy_type": "multi_sleeve_rotation",
    "risk_on_rule": {
        "method": "simple_threshold",
        "benchmark": "000300.SH",
        "lookback_months": 6,
        "min_return": 0.0,
    },
    "risk_on_allocation": {
        "sleeve": "industry",
        "lookback_months": 6,
        "skip_months": 1,
        "top_k": 3,
        "min_hold_months": 1,
        "rebalance_frequency": "monthly",
        "momentum_score_method": "pure_momentum",
    },
    "risk_off_allocation": {
        "sleeve": "defensive_bond",
        "mode": "fixed",
        "weights": {"511880.SH": 1.0},
        "candidates": [
            {"code": "511880.SH", "name": "富国短债ETF", "proxy_index": "H11006.CSI", "list_date": "2013-08-08"}
        ],
    },
}

DEFAULT_REGIME_FILTER = {
    "enabled": False,
    "benchmark_symbol": "000300.SH",
    "benchmark_lookback_months": 6,
    "benchmark_min_return": 0.0,
    "industry_momentum_lookback_months": 6,
    "positive_ratio_threshold": 0.7,
}

MODE_SETUP = {
    "index_proxy":     {"full_start": "20100101", "full_end": "20251231"},
    "real_etf_subset": {"full_start": "20160101", "full_end": "20251231"},
    "real_etf_full":   {"full_start": "20180101", "full_end": "20251231"},
}

# Proxy index mapping: ETF symbol -> (proxy_symbol, display_name)
PROXY_MAP: dict[str, tuple[str, str]] = {
    "510310.SH": ("000300.SH", "沪深300指数"),
    "159922.SZ": ("000905.SH", "中证500指数"),
    "510050.SH": ("000016.SH", "上证50指数"),
    "510880.SH": ("000015.SH", "中证红利指数"),
    "159949.SZ": ("399673.SZ", "创业板50指数"),
    "512000.SH": ("399975.SZ", "证券公司指数"),
    "512800.SH": ("399986.SZ", "中证银行指数"),
    "512200.SH": ("000036.SH", "中证地产指数"),
    "512170.SH": ("399989.SZ", "中证医疗指数"),
    "512010.SH": ("000808.SH", "中证医药指数"),
    "159928.SZ": ("000857.SH", "中证食品饮料指数"),
    "512400.SH": ("000819.SH", "中证有色金属指数"),
    "515220.SH": ("000928.SH", "中证煤炭指数"),
    "159930.SZ": ("399441.SZ", "中证能源指数"),
    "159611.SZ": ("000926.SH", "中证电力指数"),
    "515030.SH": ("399006.SZ", "创业板指(新能源代理)"),
    "159995.SZ": ("399006.SZ", "创业板指(科技代理)"),
    "512720.SH": ("399006.SZ", "创业板指(计算机代理)"),
    "515050.SH": ("399101.SZ", "中小板指(通信代理)"),
    "512660.SH": ("399952.SZ", "中证军工指数"),
    "515790.SH": ("399006.SZ", "创业板指(光伏代理)"),
    "159825.SZ": ("000998.SH", "中证农业主题指数"),
    "515210.SH": ("000825.SH", "中证钢铁指数"),
    "159870.SZ": ("000827.SH", "中证化工指数"),
    "512890.SH": ("000922.SH", "中证红利低波动指数"),
    "518880.SH": ("GC=F", "黄金COMEX期货(Yahoo,USD计价)"),
    "513100.SH": ("NDX", "纳斯达克100(Tushare/Yahoo)"),
    "511260.SH": ("000012.SH", "国债指数"),
    "511010.SH": ("000012.SH", "国债指数"),
    "511880.SH": ("H11006.CSI", "中债综合财富指数"),
    "510300.SH": ("000300.SH", "沪深300指数"),
    "516220.SH": ("399101.SZ", "中证中小板综指(物联网代理)"),
    "561910.SH": ("399006.SZ", "创业板指(储能代理)"),
    "159201.SZ": ("000922.SH", "中证红利低波动(自由现金流代理)"),
    "159732.SZ": ("399995.SZ", "中证消费电子指数"),
    "159992.SZ": ("000951.SH", "中证创新药指数"),
    "512050.SH": ("000905.SH", "中证500指数(A500代理)"),
    "513180.SH": ("^HSTECH",   "恒生科技指数(Yahoo)"),
}

SYMBOL_ALIASES = {
    "159941.SZ": "513100.SH",  # Nasdaq ETF alias used in generated specs
}

try:
    with open(UNIVERSE_YAML) as f:
        _RAW_UNIVERSE = yaml.safe_load(f)
    SLEEVE_MAP = {k.replace("_etfs", ""): [x["symbol"] for x in v] for k, v in _RAW_UNIVERSE.items() if isinstance(v, list)}
except Exception:
    SLEEVE_MAP = {}


# ---------------------------------------------------------------------------
# MinHoldRanker: enforces minimum holding period before switching positions
# ---------------------------------------------------------------------------

class MinHoldRanker:
    """Wraps MomentumRanker with a minimum hold period (months) constraint.

    The hold constraint only applies when the portfolio is non-empty (invested).
    Cash (empty portfolio) can always be exited immediately.
    """

    def __init__(
        self,
        inner: MomentumRanker,
        min_hold_months: int = 1,
        frequency: BacktestFrequency = "monthly",
    ) -> None:
        self.inner = inner
        self.min_hold = max(1, months_to_bars(min_hold_months, frequency))
        self._current: dict[str, float] = {}
        self._last_change_loc: int | None = None

    def rank(self, prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        loc = prices.index.get_loc(rebalance_date)

        # Enforce hold constraint only when currently invested
        if (self._current and self._last_change_loc is not None
                and (loc - self._last_change_loc) < self.min_hold):
            return self._current

        new = self.inner.rank(prices, rebalance_date)
        if new != self._current:
            self._current = new
            self._last_change_loc = loc
        return self._current


class RegimeConditionedRanker:
    """Turn the inner ranker on only in a simple, predeclared risk-on regime.

    defensive_mode: "cash" (empty portfolio) or "broad_index" (hold defensive_asset).
    defensive_asset: ETF symbol to hold in risk-off (e.g. "510310.SH" for CSI300 ETF).
    """

    def __init__(
        self,
        inner,
        benchmark: pd.Series,
        regime_filter: dict,
        defensive_mode: str = "cash",
        defensive_asset: str | None = None,
        frequency: BacktestFrequency = "monthly",
    ) -> None:
        self.inner = inner
        self.benchmark = benchmark.sort_index()
        self.regime_filter = {**DEFAULT_REGIME_FILTER, **(regime_filter or {})}
        self.defensive_mode = defensive_mode
        self.defensive_asset = defensive_asset
        self.frequency = frequency
        self._benchmark_lookback_bars = months_to_bars(
            int(self.regime_filter["benchmark_lookback_months"]), frequency
        )
        self._industry_momentum_lookback_bars = months_to_bars(
            int(self.regime_filter.get(
                "industry_momentum_lookback_months",
                self.regime_filter["benchmark_lookback_months"],
            )),
            frequency,
        )
        self.stats = {"risk_on_periods": 0, "risk_off_periods": 0}

    def rank(self, prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        if not self.regime_filter.get("enabled", False):
            return self.inner.rank(prices, rebalance_date)

        if self._is_risk_on(prices, rebalance_date):
            self.stats["risk_on_periods"] += 1
            return self.inner.rank(prices, rebalance_date)

        self.stats["risk_off_periods"] += 1
        if (self.defensive_mode == "broad_index"
                and self.defensive_asset
                and self.defensive_asset in prices.columns):
            return {self.defensive_asset: 1.0}
        return {}  # cash

    def _is_risk_on(self, prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> bool:
        loc = prices.index.get_loc(rebalance_date)
        benchmark_lookback = self._benchmark_lookback_bars

        bench_ok = self._benchmark_return_ok(rebalance_date, benchmark_lookback)
        if not bench_ok:
            return False

        # positive_ratio_threshold == None means skip this condition entirely
        threshold = self.regime_filter.get("positive_ratio_threshold")
        if threshold is None:
            return True

        momentum_lookback = self._industry_momentum_lookback_bars
        return self._positive_ratio_ok(prices, loc, momentum_lookback, float(threshold))

    def _benchmark_return_ok(self, rebalance_date: pd.Timestamp, lookback_bars: int) -> bool:
        bench = self.benchmark.reindex(self.benchmark.index.union([rebalance_date])).sort_index().ffill()
        if rebalance_date not in bench.index:
            return False
        loc = bench.index.get_loc(rebalance_date)
        start_idx = loc - lookback_bars
        if start_idx < 0:
            return False
        p0 = bench.iloc[start_idx]
        p1 = bench.iloc[loc]
        if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
            return False
        ret = float(p1 / p0 - 1.0)
        return ret > float(self.regime_filter["benchmark_min_return"])

    def _positive_ratio_ok(self, prices: pd.DataFrame, loc: int, lookback_bars: int, threshold: float) -> bool:
        start_idx = loc - lookback_bars
        if start_idx < 0:
            return False
        start_row = prices.iloc[start_idx]
        end_row = prices.iloc[loc]
        valid = 0
        positive = 0
        for symbol in prices.columns:
            p0 = start_row[symbol]
            p1 = end_row[symbol]
            if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
                continue
            valid += 1
            if float(p1 / p0 - 1.0) > 0.0:
                positive += 1
        if valid == 0:
            return False
        ratio = positive / valid
        return ratio >= threshold


class MultiSleeveRanker:
    """Allocates capital to different sleeves based on a risk-on regime rule."""

    def __init__(
        self,
        benchmark: pd.Series,
        risk_on_rule: dict,
        risk_on_allocation: dict,
        risk_off_allocation: dict,
        volumes: "pd.DataFrame | None" = None,
        frequency: BacktestFrequency = "monthly",
    ) -> None:
        self.benchmark = benchmark.sort_index()
        self.risk_on_rule = risk_on_rule
        self.risk_on_allocation = risk_on_allocation
        self.risk_off_allocation = risk_off_allocation
        self.frequency = frequency

        momentum_method = risk_on_allocation.get("momentum_score_method", "pure_momentum")
        try:
            _fs = FactorStore(db_path=str(_ROOT / "data" / "factors.db"))
        except Exception:
            _fs = None
        self._factor_store = _fs
        if momentum_method == "multi_factor_rank":
            inner_ranker = MultiFactorRanker(
                risk_on_allocation,
                volumes,
                monthly_benchmark=self.benchmark,
                factor_store=_fs,
                frequency=frequency,
            )
        else:
            inner_ranker = MomentumRanker(make_ranker_cfg(self.risk_on_allocation), frequency=frequency)
        self.risk_on_ranker = MinHoldRanker(
            inner_ranker,
            self.risk_on_allocation.get("min_hold_months", 1),
            frequency=frequency,
        )
        self.risk_off_ranker = None
        if self.risk_off_allocation.get("mode") not in ("fixed_equal_weight", "cash", "fixed_asset", "fixed"):
            self.risk_off_ranker = MinHoldRanker(
                MomentumRanker(make_ranker_cfg(self.risk_off_allocation), frequency=frequency),
                self.risk_off_allocation.get("min_hold_months", 1),
                frequency=frequency,
            )

        self.stats = {"risk_on_periods": 0, "risk_off_periods": 0, "circuit_breaker_triggers": [],
                      "pmi_veto_periods": 0, "pmi_veto_csi300_returns": []}
        self._regime_state: str | None = None  # stateful for asymmetric_return_threshold
        # Trailing drawdown circuit breaker state (risk_off momentum_rotation only)
        self._cb_forced_hold: int = 0        # remaining bars of CB-forced short-bond hold (converted from months_to_bars)
        self._cb_current_sym: str | None = None  # current risk_off symbol being tracked
        self._cb_peak_price: float | None = None  # trailing peak price since entry
        
    def rank(self, prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        is_risk_on = self._is_risk_on(prices, rebalance_date)

        if is_risk_on:
            self.stats["risk_on_periods"] += 1
            # Reset CB tracking when entering risk_on (risk_off asset no longer held)
            self._cb_current_sym = None
            self._cb_peak_price = None
            sleeve = self.risk_on_allocation.get("sleeve", "industry")
            symbols = SLEEVE_MAP.get(sleeve, list(prices.columns))
            valid_symbols = [c for c in symbols if c in prices.columns]
        else:
            self.stats["risk_off_periods"] += 1
            if self.risk_off_allocation.get("mode") in ("fixed_equal_weight", "fixed_asset", "fixed"):
                return self._fixed_weights(prices)
            # CB forced hold: return short bond without running momentum
            _cb_cfg = self.risk_off_allocation.get("trailing_drawdown_circuit_breaker", {})
            if _cb_cfg.get("enabled") and self._cb_forced_hold > 0:
                self._cb_forced_hold -= 1
                _fb_raw = _cb_cfg.get("fallback_asset", "511880.SH")
                _fb = SYMBOL_ALIASES.get(_fb_raw, _fb_raw)
                if _fb in prices.columns and rebalance_date in prices.index:
                    _p = float(prices.at[rebalance_date, _fb])
                    if not pd.isna(_p) and _p > 0:
                        self._cb_current_sym = _fb
                        self._cb_peak_price = max(self._cb_peak_price or _p, _p)
                return {_fb: 1.0} if _fb in prices.columns else {}
            # momentum_rotation: use explicit candidates list if provided
            candidates_cfg = self.risk_off_allocation.get("candidates", [])
            if candidates_cfg:
                candidate_syms = [SYMBOL_ALIASES.get(c.get("real_etf", ""), c.get("real_etf", ""))
                                  for c in candidates_cfg if c.get("real_etf")]
                valid_symbols = [s for s in candidate_syms if s in prices.columns]
            else:
                sleeve = self.risk_off_allocation.get("sleeve", "defensive_global")
                symbols = SLEEVE_MAP.get(sleeve, list(prices.columns))
                valid_symbols = [c for c in symbols if c in prices.columns]

        if not valid_symbols:
            return {}

        slice_df = prices[valid_symbols]
        if is_risk_on:
            result = self.risk_on_ranker.rank(slice_df, rebalance_date)
            # concentration_guard: add 510300.SH when effective ETF count < min_effective_etfs
            cg = self.risk_on_allocation.get("concentration_guard", {})
            if cg.get("enabled") and result:
                min_etfs = int(cg.get("min_effective_etfs", 3))
                if len(result) < min_etfs:
                    fallback = "510300.SH"
                    if fallback in prices.columns and fallback not in result:
                        result = {**result, fallback: 1.0}
                        w = 1.0 / len(result)
                        result = {k: w for k in result}
            if not result:
                fallback_etf = self.risk_on_allocation.get("fallback_etf")
                if fallback_etf:
                    symbol = SYMBOL_ALIASES.get(fallback_etf, fallback_etf)
                    if symbol in prices.columns:
                        return {symbol: 1.0}
            return result
        if self.risk_off_ranker is None:
            return {}
        result = self.risk_off_ranker.rank(slice_df, rebalance_date)
        # floor_rule: if all candidates had negative momentum, force fallback to short bond
        if not result:
            floor_cfg = self.risk_off_allocation.get("floor_rule", {})
            if floor_cfg.get("enabled"):
                fallback = floor_cfg.get("fallback_asset", "511880.SH")
                fallback_sym = SYMBOL_ALIASES.get(fallback, fallback)
                if fallback_sym in prices.columns:
                    result = {fallback_sym: 1.0}
        if not result:
            return {}
        # Trailing drawdown circuit breaker (momentum_rotation only)
        cb_cfg = self.risk_off_allocation.get("trailing_drawdown_circuit_breaker", {})
        if cb_cfg.get("enabled") and rebalance_date in prices.index:
            sel_sym = next(iter(result))
            if sel_sym in prices.columns:
                curr_p = float(prices.at[rebalance_date, sel_sym])
                if not pd.isna(curr_p) and curr_p > 0:
                    if sel_sym != self._cb_current_sym:
                        # New position: reset peak to entry price
                        self._cb_current_sym = sel_sym
                        self._cb_peak_price = curr_p
                    else:
                        # Same position: update trailing peak
                        self._cb_peak_price = max(self._cb_peak_price or curr_p, curr_p)
                    cb_thr = float(cb_cfg.get("threshold", -0.15))
                    if self._cb_peak_price and self._cb_peak_price > 0:
                        drawdown = curr_p / self._cb_peak_price - 1.0
                        if drawdown < cb_thr:
                            min_hold_after = months_to_bars(int(cb_cfg.get("min_hold_after_trigger_months", 1)), self.frequency)
                            self._cb_forced_hold = max(0, min_hold_after - 1)
                            fb_raw = cb_cfg.get("fallback_asset", "511880.SH")
                            fb = SYMBOL_ALIASES.get(fb_raw, fb_raw)
                            self.stats["circuit_breaker_triggers"].append({
                                "date": str(rebalance_date.date()),
                                "symbol": sel_sym,
                                "drawdown_from_peak": round(drawdown, 4),
                                "peak_price": round(self._cb_peak_price, 4),
                                "current_price": round(curr_p, 4),
                            })
                            if fb in prices.columns:
                                fb_p = float(prices.at[rebalance_date, fb])
                                self._cb_current_sym = fb
                                self._cb_peak_price = fb_p if not pd.isna(fb_p) else None
                                return {fb: 1.0}
                            return {}
        return result

    def _fixed_weights(self, prices: pd.DataFrame) -> dict[str, float]:
        raw_weights = self.risk_off_allocation.get("weights") or {}
        weights: dict[str, float] = {}
        for raw_symbol, raw_weight in raw_weights.items():
            symbol = SYMBOL_ALIASES.get(raw_symbol, raw_symbol)
            if symbol not in prices.columns:
                continue
            weight = float(raw_weight)
            if weight > 0:
                weights[symbol] = weights.get(symbol, 0.0) + weight

        total = sum(weights.values())
        if total <= 0:
            return {}
        return {symbol: weight / total for symbol, weight in weights.items()}
            
    def _is_risk_on(self, prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> bool:
        method = self.risk_on_rule.get("method", "return_threshold")
        bench = self.benchmark.reindex(self.benchmark.index.union([rebalance_date])).sort_index().ffill()
        if rebalance_date not in bench.index:
            return False
        loc = bench.index.get_loc(rebalance_date)

        if method in ("asymmetric_return_threshold", "asymmetric_dual_threshold"):
            return self._asymmetric_is_risk_on(bench, loc)

        if method == "ma_cross":
            ma_period = months_to_bars(int(self.risk_on_rule.get("ma_period", 12)), self.frequency)
            if loc < ma_period:
                return False
            ma = float(bench.iloc[loc - ma_period + 1: loc + 1].mean())
            current = float(bench.iloc[loc])
            return not (pd.isna(current) or pd.isna(ma) or ma <= 0) and current > ma

        if method == "dual_return_threshold":
            # Long-term check
            lookback_long = months_to_bars(int(self.risk_on_rule.get("lookback_months", 6)), self.frequency)
            min_return_long = float(self.risk_on_rule.get("min_return", 0.0))
            start_long = loc - lookback_long
            if start_long < 0:
                return False
            p0_l, p1_l = bench.iloc[start_long], bench.iloc[loc]
            if pd.isna(p0_l) or pd.isna(p1_l) or p0_l <= 0:
                return False
            if float(p1_l / p0_l - 1.0) <= min_return_long:
                return False
            # Short-term check
            lookback_short = months_to_bars(int(self.risk_on_rule.get("lookback_months_short", 3)), self.frequency)
            min_return_short = float(self.risk_on_rule.get("min_return_short", 0.0))
            start_short = loc - lookback_short
            if start_short < 0:
                return False
            p0_s, p1_s = bench.iloc[start_short], bench.iloc[loc]
            if pd.isna(p0_s) or pd.isna(p1_s) or p0_s <= 0:
                return False
            return float(p1_s / p0_s - 1.0) > min_return_short

        # default: return_threshold
        lookback = months_to_bars(int(self.risk_on_rule.get("lookback_months", 6)), self.frequency)
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
        """Stateful asymmetric regime: fast entry (entry_lookback_months > entry_min_return),
        slow exit (exit_lookback_months < exit_max_return). Inertia when neither condition fires."""
        entry_lookback = months_to_bars(int(self.risk_on_rule.get("entry_lookback_months", 3)), self.frequency)
        entry_min_return = float(self.risk_on_rule.get("entry_min_return", 0.0))
        exit_lookback = months_to_bars(int(self.risk_on_rule.get("exit_lookback_months", 6)), self.frequency)
        exit_max_return = float(self.risk_on_rule.get("exit_max_return", -0.03))

        # Initialize state on very first call using entry condition
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
        else:  # risk_off
            start_idx = loc - entry_lookback
            if start_idx >= 0:
                p0, p1 = bench.iloc[start_idx], bench.iloc[loc]
                if not (pd.isna(p0) or pd.isna(p1) or p0 <= 0):
                    if float(p1 / p0 - 1.0) > entry_min_return:
                        self._regime_state = "risk_on"
                        return True
            return False

    def _pmi_veto(self, rebalance_date: pd.Timestamp, bench: pd.Series, loc: int, lookback: int) -> bool:
        """Return True (veto risk-on) when pmi_overlay_enabled and PMI < pmi_threshold.

        PMI data is stored by last business day of month, not strict month-end, so we
        query by year-month prefix to avoid exact-date misses.
        """
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
    """Portfolio-level trailing drawdown circuit breaker wrapper around MultiSleeveRanker.

    Tracks strategy NAV from inception. When NAV / all_time_peak - 1 <= threshold,
    overrides the risk_off sleeve to hold fallback_asset (short bond).
    The peak is never reset on position switches or regime changes.
    CB only fires during risk_off periods; risk_on positions are unaffected.
    """

    def __init__(
        self,
        inner: MultiSleeveRanker,
        threshold: float = -0.25,
        fallback_asset: str = "511880.SH",
        frequency: BacktestFrequency = "monthly",
    ) -> None:
        self.inner = inner
        self.threshold = threshold
        self.fallback_raw = fallback_asset
        self.frequency = frequency
        self._nav: float = 1.0
        self._peak_nav: float = 1.0
        self._prev_positions: dict[str, float] = {}
        self._prev_date: pd.Timestamp | None = None
        self.stats: dict = {"portfolio_cb_triggers": []}

    def rank(self, prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        # Step 1: update approximate NAV using prev positions and price change
        if (self._prev_date is not None and self._prev_positions
                and self._prev_date in prices.index
                and rebalance_date in prices.index):
            period_ret = 0.0
            for sym, w in self._prev_positions.items():
                if sym in prices.columns:
                    p0 = float(prices.at[self._prev_date, sym])
                    p1 = float(prices.at[rebalance_date, sym])
                    if not pd.isna(p0) and not pd.isna(p1) and p0 > 0:
                        period_ret += w * (p1 / p0 - 1.0)
            self._nav *= (1.0 + period_ret)

        # Step 2: update all-time peak
        self._peak_nav = max(self._peak_nav, self._nav)

        # Step 3: compute drawdown and check CB condition
        drawdown = self._nav / self._peak_nav - 1.0 if self._peak_nav > 0 else 0.0
        cb_condition_met = drawdown <= self.threshold

        # Step 4: call inner ranker; detect whether regime is risk_off this period
        risk_off_before = self.inner.stats["risk_off_periods"]
        result = self.inner.rank(prices, rebalance_date)
        is_risk_off = self.inner.stats["risk_off_periods"] > risk_off_before

        # Step 5: apply CB override only in risk_off regime
        if cb_condition_met and is_risk_off:
            fallback = SYMBOL_ALIASES.get(self.fallback_raw, self.fallback_raw)
            if fallback in prices.columns:
                self.stats["portfolio_cb_triggers"].append({
                    "date": str(rebalance_date.date()),
                    "portfolio_drawdown": round(drawdown, 4),
                    "nav": round(self._nav, 4),
                    "peak_nav": round(self._peak_nav, 4),
                    "original_risk_off_result": dict(result),
                })
                result = {fallback: 1.0}

        # Step 6: store state for next period
        self._prev_positions = dict(result)
        self._prev_date = rebalance_date
        return result


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _ts(yyyymmdd: str) -> pd.Timestamp:
    return pd.Timestamp(f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}")


def _add_months(yyyymmdd: str, n: int) -> str:
    ts = _ts(yyyymmdd)
    total_month = ts.month - 1 + n
    year = ts.year + total_month // 12
    month = total_month % 12 + 1
    return f"{year:04d}{month:02d}01"


def _month_end(yyyymmdd: str) -> str:
    ts = _ts(yyyymmdd)
    last_day = monthrange(ts.year, ts.month)[1]
    return f"{ts.year:04d}{ts.month:02d}{last_day:02d}"


def _coverage_years(full_start: str, full_end: str) -> float:
    return round((_ts(full_end) - _ts(full_start)).days / 365.25, 2)


# ---------------------------------------------------------------------------
# Walk-forward helpers
# ---------------------------------------------------------------------------

def build_folds(full_start: str, full_end: str) -> list[dict]:
    folds = []
    cursor = full_start
    end_ts = _ts(full_end)
    while True:
        train_end = _month_end(_add_months(cursor, TRAIN_MONTHS - 1))
        test_start = _add_months(cursor, TRAIN_MONTHS)
        test_end = _month_end(_add_months(cursor, TRAIN_MONTHS + TEST_MONTHS - 1))
        if _ts(test_end) > end_ts:
            break
        folds.append({
            "train_start": cursor,
            "train_end": train_end,
            "test_start": test_start,
            "test_end": test_end,
        })
        cursor = _add_months(cursor, STEP_MONTHS)
    return folds


def slice_fold_metrics(strategy_rets: pd.Series, test_start: str, test_end: str) -> dict:
    ts_s = _ts(test_start)
    ts_e = _ts(test_end)
    sl = strategy_rets.loc[
        (strategy_rets.index >= ts_s) & (strategy_rets.index <= ts_e)
    ]
    if len(sl) < 2:
        nan = float("nan")
        return {"oos_return": nan, "oos_mdd": nan, "oos_sharpe": nan}
    n = len(sl)
    total = float((1.0 + sl).prod())
    annual_return = round(total ** (12.0 / n) - 1.0, 4)
    equity = (1.0 + sl).cumprod()
    mdd = round(float((equity / equity.cummax() - 1.0).min()), 4)
    rf_monthly = (1.0 + 0.03) ** (1.0 / 12) - 1.0
    vol = float(sl.std(ddof=1))
    sharpe = (
        round(float((sl - rf_monthly).mean() / vol * math.sqrt(12)), 3)
        if vol > 1e-9 else 0.0
    )
    return {"oos_return": annual_return, "oos_mdd": mdd, "oos_sharpe": sharpe}


def _apply_monthly_stop_approx(
    strategy_rets: pd.Series,
    holdings: pd.DataFrame,
    stop_threshold: float = -0.05,
) -> pd.Series:
    """Monthly-data approximation of intra-month drawdown stop.

    When the portfolio was invested (non-zero holdings from prior month-end) and
    the observed monthly return < stop_threshold, cap the return at stop_threshold.

    Limitation: overstates benefit if the month recovered after briefly hitting
    the threshold; understates if an opening gap jumps past it.  Directionally
    correct for large continuous-down months (e.g., 2023H1).
    """
    # holdings.loc[T] = positions decided at T (earns return at T+1).
    # Return at T was earned by holdings from T-1.
    prev_invested = holdings.sum(axis=1).shift(1).fillna(0.0) > 0.01
    result = strategy_rets.copy()
    mask = prev_invested & (result < stop_threshold)
    result[mask] = stop_threshold
    return result


def aggregate_folds(fold_results: list[dict]) -> dict:
    valid = [f for f in fold_results if not math.isnan(f["oos_return"])]
    if not valid:
        nan = float("nan")
        return {"oos_annual_return": nan, "oos_max_drawdown": nan, "oos_sharpe": nan}
    sharpe_vals = [f["oos_sharpe"] for f in valid if abs(f["oos_sharpe"]) < 5.0]
    return {
        "oos_annual_return": round(sum(f["oos_return"] for f in valid) / len(valid), 4),
        "oos_max_drawdown": round(min(f["oos_mdd"] for f in valid), 4),
        "oos_sharpe": round(sum(sharpe_vals) / len(sharpe_vals), 3) if sharpe_vals else float("nan"),
    }


# ---------------------------------------------------------------------------
# Global / commodity proxy helpers
# ---------------------------------------------------------------------------

_GLOBAL_INDEX_PROXY_SYMBOLS = frozenset({
    "NDX", "SPX", "DJI", "IXIC", "NKY", "HSI", "DAX", "UKX", "XIN9", "FTSE",
})
_YAHOO_DIRECT_PROXY_SYMBOLS = frozenset({
    "GC=F", "XAUUSD=X", "CL=F", "SI=F", "^HSTECH",
})
_GLOBAL_TO_YAHOO_MAP: dict[str, str] = {
    "NDX": "^NDX",
    "SPX": "^GSPC",
    "DJI": "^DJI",
    "IXIC": "^IXIC",
    "NKY": "^N225",
    "HSI": "^HSI",
}


def _fetch_yahoo_df(symbol: str, full_start: str, full_end: str) -> "pd.DataFrame | None":
    """Return daily OHLCV from Yahoo Finance; None on failure."""
    try:
        from quant.data_providers.yahoo_data_provider import YahooDataProvider
        yahoo = YahooDataProvider()
        df = yahoo.getStockData(symbol, full_start, full_end)
        if df is not None and not df.empty and "close" in df.columns:
            # Normalize timezone-aware index to naive DatetimeIndex
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
            elif df.index.tz is not None:
                df.index = df.index.tz_convert("UTC").tz_localize(None)
            print(f"  [Yahoo] {symbol}: {len(df)} daily rows")
            return df
        print(f"  [WARN] Yahoo empty for {symbol}")
    except Exception as exc:
        print(f"  [WARN] Yahoo failed for {symbol}: {exc}")
    return None


def _fetch_global_proxy_df(
    data_service: DataService, proxy_sym: str, full_start: str, full_end: str
) -> "pd.DataFrame | None":
    """Fetch global index or commodity data; Tushare index_global → Yahoo fallback."""
    # Commodities (GC=F etc.): straight to Yahoo
    if proxy_sym in _YAHOO_DIRECT_PROXY_SYMBOLS:
        return _fetch_yahoo_df(proxy_sym, full_start, full_end)

    # Global indices: try Tushare index_global first
    if proxy_sym in _GLOBAL_INDEX_PROXY_SYMBOLS:
        try:
            prov = data_service._create_provider("auto")
            legacy = getattr(prov, "_legacy", None)
            if legacy and hasattr(legacy, "getGlobalIndexData"):
                df = legacy.getGlobalIndexData(proxy_sym, full_start, full_end)
                if df is not None and not df.empty and "close" in df.columns:
                    df_dropped = df.dropna(subset=["close"])
                    has_five_years = (
                        len(df_dropped) >= 2
                        and (df_dropped.index[-1] - df_dropped.index[0]) >= pd.Timedelta(days=365 * 5 - 30)
                    )
                    if has_five_years:
                        print(f"  [Tushare global] {proxy_sym}: {len(df)} daily rows")
                        return df
                    print(f"  [WARN] Tushare global {proxy_sym}: insufficient history, trying Yahoo")
        except Exception as exc:
            print(f"  [WARN] Tushare global index failed for {proxy_sym}: {exc}")
        yahoo_sym = _GLOBAL_TO_YAHOO_MAP.get(proxy_sym, proxy_sym)
        return _fetch_yahoo_df(yahoo_sym, full_start, full_end)

    return None


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_proxy_prices(
    data_service: DataService,
    full_start: str,
    full_end: str,
    frequency: BacktestFrequency = "monthly",
) -> tuple[pd.DataFrame, list[dict]]:
    """Fetch index proxy prices for all ETFs; returns (resampled_df, proxy_mapping)."""
    universe = load_universe(str(UNIVERSE_YAML))
    frames: dict[str, pd.Series] = {}
    proxy_mapping: list[dict] = []

    for entry in universe:
        etf_sym = entry.symbol
        if etf_sym not in PROXY_MAP:
            print(f"  [SKIP] No proxy defined for {etf_sym}")
            continue
        proxy_sym, proxy_name = PROXY_MAP[etf_sym]
        try:
            is_global = (
                proxy_sym in _GLOBAL_INDEX_PROXY_SYMBOLS
                or proxy_sym in _YAHOO_DIRECT_PROXY_SYMBOLS
            )
            if is_global:
                df = _fetch_global_proxy_df(data_service, proxy_sym, full_start, full_end)
            else:
                df = data_service.get_price(PriceRequest(
                    symbol=proxy_sym,
                    start=full_start,
                    end=full_end,
                    asset_type="index",
                ))
            if df is None or df.empty or "close" not in df.columns:
                print(f"  [WARN] Empty data: {proxy_sym} for {etf_sym}")
                continue
            close = df["close"].astype(float)
            close.name = etf_sym
            resampled = close.resample(resample_rule(frequency)).last().dropna()
            if resampled.empty:
                continue
            frames[etf_sym] = resampled
            start_date = resampled.index[0].strftime("%Y-%m-%d")
            end_date = resampled.index[-1].strftime("%Y-%m-%d")
            cov = round((resampled.index[-1] - resampled.index[0]).days / 365.25, 2)
            proxy_mapping.append({
                "etf_symbol": etf_sym,
                "proxy_symbol": proxy_sym,
                "proxy_name": proxy_name,
                "start_date": start_date,
                "end_date": end_date,
                "coverage_years": cov,
                "status": "ok",
            })
            print(f"  [OK] {etf_sym} -> {proxy_sym}: {start_date} ~ {end_date}")
        except Exception as exc:
            print(f"  [ERROR] {etf_sym} -> {proxy_sym}: {exc}")

    if not frames:
        raise RuntimeError("index_proxy: failed to fetch any proxy data")

    df_all = pd.DataFrame(frames).sort_index()
    return df_all, proxy_mapping


def fetch_proxy_monthly_prices(
    data_service: DataService, full_start: str, full_end: str
) -> tuple[pd.DataFrame, list[dict]]:
    """Deprecated: use fetch_proxy_prices(..., frequency='monthly')."""
    return fetch_proxy_prices(data_service, full_start, full_end, frequency="monthly")


def fetch_etf_prices(
    data_service: DataService,
    full_start: str,
    full_end: str,
    subset: bool = False,
    frequency: BacktestFrequency = "monthly",
) -> tuple[pd.DataFrame, int]:
    """Fetch actual ETF prices resampled to frequency; optionally filter to historical subset."""
    universe = load_universe(str(UNIVERSE_YAML))
    frames: dict[str, pd.Series] = {}

    for entry in universe:
        try:
            df = data_service.get_price(PriceRequest(
                symbol=entry.symbol,
                start=full_start,
                end=full_end,
                asset_type="etf",
            ))
            if df is None or df.empty or "close" not in df.columns:
                continue
            close = df["close"].astype(float)
            close.name = entry.symbol
            # Anomaly filter MUST remain at the DAILY level — do not move below resample.
            daily_ret = close.pct_change()
            max_jump = daily_ret.abs().max()
            if pd.notna(max_jump) and max_jump > MAX_SINGLE_DAY_ABS_RET:
                bad_dt = daily_ret.abs().idxmax()
                print(
                    f"  [SKIP anomaly] {entry.symbol}: |daily ret|={max_jump:.2%} on "
                    f"{bad_dt.date()} — unadjusted split/merger suspected"
                )
                continue
            resampled = close.resample(resample_rule(frequency)).last().dropna()
            if resampled.empty:
                continue
            if subset and resampled.index[0] > SUBSET_CUTOFF_TS:
                print(f"  [SKIP subset] {entry.symbol}: first={resampled.index[0].date()} > cutoff")
                continue
            frames[entry.symbol] = resampled
            tag = "subset" if subset else "full"
            print(f"  [OK {tag}] {entry.symbol}: {resampled.index[0].date()} ~ {resampled.index[-1].date()}")
        except Exception as exc:
            print(f"  [ERROR] {entry.symbol}: {exc}")

    if not frames:
        raise RuntimeError(f"No ETF data for {'subset' if subset else 'full'} mode")

    df_all = pd.DataFrame(frames).sort_index()
    return df_all, len(frames)


def fetch_etf_monthly_prices(
    data_service: DataService, full_start: str, full_end: str, subset: bool = False
) -> tuple[pd.DataFrame, int]:
    """Deprecated: use fetch_etf_prices(..., frequency='monthly')."""
    return fetch_etf_prices(data_service, full_start, full_end, subset=subset, frequency="monthly")


def fetch_volumes(
    data_service: DataService,
    mode: str,
    full_start: str,
    full_end: str,
    frequency: BacktestFrequency = "monthly",
) -> "pd.DataFrame | None":
    """Fetch aggregated trading volumes resampled to frequency. Returns None if data too sparse."""
    universe = load_universe(str(UNIVERSE_YAML))
    frames: dict[str, pd.Series] = {}

    if mode == "index_proxy":
        for entry in universe:
            etf_sym = entry.symbol
            if etf_sym not in PROXY_MAP:
                continue
            proxy_sym, _ = PROXY_MAP[etf_sym]
            try:
                df = data_service.get_price(PriceRequest(
                    symbol=proxy_sym,
                    start=full_start,
                    end=full_end,
                    asset_type="index",
                ))
                if df is None or df.empty or "volume" not in df.columns:
                    continue
                vol = df["volume"].astype(float)
                vol.name = etf_sym
                resampled = vol.resample(resample_rule(frequency)).sum().dropna()
                if resampled.empty:
                    continue
                frames[etf_sym] = resampled
            except Exception as exc:
                print(f"  [WARN vol] {etf_sym}: {exc}")
    else:
        subset = (mode == "real_etf_subset")
        for entry in universe:
            try:
                df = data_service.get_price(PriceRequest(
                    symbol=entry.symbol,
                    start=full_start,
                    end=full_end,
                    asset_type="etf",
                ))
                if df is None or df.empty or "volume" not in df.columns:
                    continue
                vol = df["volume"].astype(float)
                vol.name = entry.symbol
                resampled = vol.resample(resample_rule(frequency)).sum().dropna()
                if resampled.empty:
                    continue
                if subset and resampled.index[0] > SUBSET_CUTOFF_TS:
                    continue
                frames[entry.symbol] = resampled
            except Exception as exc:
                print(f"  [WARN vol] {entry.symbol}: {exc}")

    if not frames:
        print(f"  [WARN] No volume data for mode={mode}, low_crowding factor will be skipped")
        return None

    df_all = pd.DataFrame(frames).sort_index()
    nan_ratio = float(df_all.isna().mean().mean())
    if nan_ratio > 0.5:
        print(f"  [WARN] Volume data too sparse ({nan_ratio:.1%} NaN), low_crowding factor will be skipped")
        return None

    print(f"  [OK vol] {len(df_all.columns)} symbols, {len(df_all)} bars, NaN={nan_ratio:.1%}")
    return df_all


def fetch_monthly_volumes(
    data_service: DataService,
    mode: str,
    full_start: str,
    full_end: str,
) -> "pd.DataFrame | None":
    """Deprecated: use fetch_volumes(..., frequency='monthly')."""
    return fetch_volumes(data_service, mode, full_start, full_end, frequency="monthly")


def build_overlay(data_service: DataService, full_start: str, full_end: str) -> object:
    """Build a PrecomputedRegimeOverlay for the full period."""
    try:
        bench_df = data_service.get_price(PriceRequest(
            symbol="000300.SH",
            start=full_start,
            end=full_end,
            asset_type="index",
        ))
        return PrecomputedRegimeOverlay(bench_df)
    except Exception as exc:
        print(f"  [WARN] overlay failed ({exc}), using pass-through multiplier=1")

        class PassThrough:
            def multiplier_at(self, date: pd.Timestamp) -> float:
                return 1.0

        return PassThrough()


def fetch_benchmark(
    data_service: DataService,
    full_start: str,
    full_end: str,
    frequency: BacktestFrequency = "monthly",
) -> pd.Series:
    """Return CSI 300 close series resampled to the engine frequency."""
    try:
        df = data_service.get_price(PriceRequest(
            symbol="000300.SH",
            start=full_start,
            end=full_end,
            asset_type="index",
        ))
        close = df["close"].astype(float)
        return close.resample(resample_rule(frequency)).last().dropna()
    except Exception as exc:
        print(f"  [WARN] benchmark fetch failed: {exc}")
        return pd.Series(dtype=float)


def fetch_monthly_benchmark(
    data_service: DataService, full_start: str, full_end: str
) -> pd.Series:
    """Deprecated: use fetch_benchmark(..., frequency='monthly')."""
    return fetch_benchmark(data_service, full_start, full_end, frequency="monthly")


def make_ranker_cfg(params: dict) -> RankerConfig:
    raw_vol = params.get("vol_penalty", 0.0)
    vol_penalty = float(raw_vol) if raw_vol is not None and not isinstance(raw_vol, dict) else 0.0
    return RankerConfig(
        lookback_months=params["lookback_months"],
        skip_recent_months=params.get("skip_months", params.get("skip_recent_months", 1)),
        top_k=params["top_k"],
        vol_penalty=vol_penalty,
        vol_lookback_months=params.get("vol_lookback_months", 0),
        vol_formula=params.get("vol_formula", "exponent"),
    )


def _get_vol_adjusted_config(candidate_params: dict) -> dict | None:
    """Return vol_penalty config dict if multi_sleeve uses vol_adjusted momentum."""
    if candidate_params.get("strategy_type") != "multi_sleeve_rotation":
        return None
    risk_on = candidate_params.get("risk_on_allocation", {})
    if risk_on.get("momentum_score_method") != "vol_adjusted":
        return None
    vol_cfg = risk_on.get("vol_penalty", {})
    return vol_cfg if isinstance(vol_cfg, dict) else None


def select_lambda_on_train_window(
    train_prices: pd.DataFrame,
    overlay: object,
    monthly_benchmark: pd.Series,
    train_start: str,
    train_end: str,
    lambda_search_space: list[float],
    base_multi_sleeve_params: dict,
    vol_lookback_months: int = 3,
) -> float:
    """Select best vol_penalty lambda by evaluating strategy Sharpe on training window."""
    best_lambda = lambda_search_space[0]
    best_sharpe = float("-inf")

    train_start_ts = _ts(train_start)
    train_end_ts = _ts(train_end)

    for lam in lambda_search_space:
        modified_alloc = dict(base_multi_sleeve_params.get("risk_on_allocation", {}))
        modified_alloc["vol_penalty"] = lam
        modified_alloc["vol_formula"] = "linear_subtract"
        modified_alloc["vol_lookback_months"] = vol_lookback_months
        modified_params = dict(base_multi_sleeve_params)
        modified_params["risk_on_allocation"] = modified_alloc

        regime_ranker = MultiSleeveRanker(
            monthly_benchmark,
            modified_params.get("risk_on_rule", {}),
            modified_params.get("risk_on_allocation", {}),
            modified_params.get("risk_off_allocation", {}),
        )
        combiner = PortfolioCombiner()
        backtester = RotationBacktester(RotationBacktestConfig(transaction_cost=0.002))

        bench_slice = monthly_benchmark.reindex(train_prices.index).ffill()
        if bench_slice.isna().all():
            bench_slice = train_prices.iloc[:, 0].copy()

        try:
            result = backtester.run(
                universe_prices=train_prices,
                benchmark_prices=bench_slice,
                ranker=regime_ranker,
                overlay=overlay,
                combiner=combiner,
            )
            rets = result.monthly_returns["strategy"]
            train_rets = rets.loc[(rets.index >= train_start_ts) & (rets.index <= train_end_ts)]
            if len(train_rets) < 3:
                continue
            rf_monthly = (1.0 + 0.03) ** (1.0 / 12) - 1.0
            vol = float(train_rets.std(ddof=1))
            sharpe = (
                float((train_rets - rf_monthly).mean() / vol * math.sqrt(12))
                if vol > 1e-9 else 0.0
            )
            print(f"    [LAMBDA] lambda={lam:.1f} train_sharpe={sharpe:.3f}")
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_lambda = lam
        except Exception as exc:
            print(f"    [LAMBDA SELECT] lambda={lam} failed: {exc}")

    print(f"  -> Selected lambda={best_lambda} (train_sharpe={best_sharpe:.3f})")
    return best_lambda


# ---------------------------------------------------------------------------
# Single fold backtest
# ---------------------------------------------------------------------------

def run_fold(
    fold_prices: pd.DataFrame,
    overlay: object,
    monthly_benchmark: pd.Series,
    ranker_cfg: RankerConfig,
    min_hold_months: int,
    test_start: str,
    test_end: str,
    strategy_type: str = "standard_rotation",
    regime_filter: dict | None = None,
    defensive_mode: str = "cash",
    defensive_asset: str | None = None,
    multi_sleeve_params: dict | None = None,
    monthly_volumes: "pd.DataFrame | None" = None,
) -> dict:
    """Run one walk-forward fold; return OOS metrics dict."""
    ranker = MinHoldRanker(MomentumRanker(ranker_cfg), min_hold_months)
    regime_ranker = None
    portfolio_cb_ranker = None

    if strategy_type == "multi_sleeve_rotation" and multi_sleeve_params:
        regime_ranker = MultiSleeveRanker(
            monthly_benchmark,
            multi_sleeve_params.get("risk_on_rule", {}),
            multi_sleeve_params.get("risk_on_allocation", {}),
            multi_sleeve_params.get("risk_off_allocation", {}),
            volumes=monthly_volumes,
        )
        portfolio_cb_cfg = multi_sleeve_params.get("risk_off_allocation", {}).get(
            "portfolio_trailing_drawdown_circuit_breaker", {}
        )
        if portfolio_cb_cfg.get("enabled", False):
            portfolio_cb_ranker = PortfolioLevelCBRanker(
                regime_ranker,
                threshold=float(portfolio_cb_cfg.get("threshold", -0.25)),
                fallback_asset=portfolio_cb_cfg.get("fallback_asset", "511880.SH"),
            )
            ranker_for_backtest = portfolio_cb_ranker
        else:
            ranker_for_backtest = regime_ranker
    elif strategy_type == "regime_conditioned_rotation":
        regime_ranker = RegimeConditionedRanker(
            ranker, monthly_benchmark, regime_filter or {},
            defensive_mode=defensive_mode,
            defensive_asset=defensive_asset,
        )
        ranker_for_backtest = regime_ranker
    else:
        ranker_for_backtest = ranker

    combiner = PortfolioCombiner()
    backtester = RotationBacktester(RotationBacktestConfig(transaction_cost=0.002))

    bench_slice = monthly_benchmark.reindex(fold_prices.index).ffill()
    if bench_slice.isna().all():
        bench_slice = fold_prices.iloc[:, 0].copy()

    try:
        result = backtester.run(
            universe_prices=fold_prices,
            benchmark_prices=bench_slice,
            ranker=ranker_for_backtest,
            overlay=overlay,
            combiner=combiner,
        )
        strategy_rets = result.monthly_returns["strategy"]
        # Apply intra_month_stop approximation if configured in multi_sleeve spec.
        if strategy_type == "multi_sleeve_rotation" and multi_sleeve_params:
            stop_cfg = multi_sleeve_params.get("risk_on_allocation", {}).get("intra_month_stop") or {}
            if stop_cfg.get("enabled"):
                stop_thr = float(stop_cfg.get("drawdown_threshold", -0.05))
                strategy_rets = _apply_monthly_stop_approx(strategy_rets, result.holdings, stop_thr)
                print(f"    [STOP] intra_month_stop applied (thr={stop_thr}); "
                      f"months capped: {int((result.monthly_returns['strategy'] < stop_thr).sum())}")
        metrics = slice_fold_metrics(strategy_rets, test_start, test_end)
        if regime_ranker is not None:
            regime_stats = dict(regime_ranker.stats)
            if portfolio_cb_ranker is not None:
                regime_stats["portfolio_cb_triggers"] = portfolio_cb_ranker.stats["portfolio_cb_triggers"]
            metrics["regime_stats"] = regime_stats
        return metrics
    except Exception as exc:
        print(f"    [FOLD ERROR] {test_start}~{test_end}: {exc}")
        nan = float("nan")
        return {"oos_return": nan, "oos_mdd": nan, "oos_sharpe": nan, "regime_stats": {}}


# ---------------------------------------------------------------------------
# Per-mode walk-forward runner
# ---------------------------------------------------------------------------

def run_mode(
    mode: str,
    candidate_params: dict,
    baseline_params: dict,
    data_service: DataService,
    proxy_mapping_out: list[dict],
    strategy_type: str = "standard_rotation",
    regime_filter: dict | None = None,
    defensive_mode: str = "cash",
    defensive_asset: str | None = None,
) -> dict:
    cfg = MODE_SETUP[mode]
    full_start = cfg["full_start"]
    full_end = cfg["full_end"]
    print(f"\n=== [{mode}] {full_start} ~ {full_end} ===")

    # 1. Fetch price data
    if mode == "index_proxy":
        monthly_prices, mapping = fetch_proxy_monthly_prices(data_service, full_start, full_end)
        existing = {m["etf_symbol"] for m in proxy_mapping_out}
        for m in mapping:
            if m["etf_symbol"] not in existing:
                proxy_mapping_out.append(m)
        n_symbols = len(monthly_prices.columns)
    elif mode == "real_etf_subset":
        # Fetch from 2014 so SUBSET_CUTOFF_TS (2014-12-31) filter sees actual listing dates,
        # then trim to full_start (2016) to exclude 2015 bubble data from walk-forward.
        LISTING_CHECK_START = "20140101"
        monthly_prices_raw, n_symbols = fetch_etf_monthly_prices(
            data_service, LISTING_CHECK_START, full_end, subset=True
        )
        ts_full_start = _ts(full_start)
        monthly_prices = monthly_prices_raw.loc[monthly_prices_raw.index >= ts_full_start]
    else:
        monthly_prices, n_symbols = fetch_etf_monthly_prices(data_service, full_start, full_end, subset=False)

    print(f"  {n_symbols} symbols, {len(monthly_prices)} monthly rows")

    # 2. Volume data for multi_factor_rank (fetched alongside price data)
    monthly_volumes = None
    if (strategy_type == "multi_sleeve_rotation"
            and isinstance(candidate_params, dict)
            and candidate_params.get("risk_on_allocation", {}).get("momentum_score_method") == "multi_factor_rank"):
        print("  Fetching volume data for multi_factor_rank...")
        monthly_volumes = fetch_monthly_volumes(data_service, mode, full_start, full_end)

    # 3. Overlay and benchmark (full period)
    # Default overlay disabled for multi_sleeve_rotation: it owns its own
    # regime_filter, and stacking LowFrequencyRegimeScorer's bear-market
    # zeroing on top causes double-defense (e.g. 2022H1/H2 returning 0%).
    print("  Building overlay...")
    regime_overlay_cfg = candidate_params.get("regime_overlay", {}) if isinstance(candidate_params, dict) else {}
    overlay_default_enabled = strategy_type != "multi_sleeve_rotation"
    if not regime_overlay_cfg.get("enabled", overlay_default_enabled):
        class PassThrough:
            def multiplier_at(self, date: pd.Timestamp) -> float:
                return 1.0
        overlay = PassThrough()
        print("  [INFO] regime_overlay disabled: using PassThrough overlay (multiplier=1.0)")
    else:
        overlay = build_overlay(data_service, full_start, full_end)
    monthly_benchmark = fetch_monthly_benchmark(data_service, full_start, full_end)

    # 3. Build folds and run
    folds = build_folds(full_start, full_end)
    print(f"  {len(folds)} walk-forward folds")

    if strategy_type == "multi_sleeve_rotation":
        cand_cfg = make_ranker_cfg(BASELINE_PARAMS)  # Dummy
        cand_min_hold = 1
    else:
        cand_cfg = make_ranker_cfg(candidate_params)
        cand_min_hold = candidate_params.get("min_hold_months", 1)

    base_cfg = make_ranker_cfg(baseline_params)
    base_min_hold = baseline_params.get("min_hold_months", 1)

    cand_folds: list[dict] = []
    base_folds: list[dict] = []
    vol_adj_cfg = _get_vol_adjusted_config(candidate_params)

    for i, fold in enumerate(folds, 1):
        warmup_raw = _add_months(fold["test_start"], -WARMUP_MONTHS)
        warmup_start = warmup_raw if _ts(warmup_raw) >= _ts(full_start) else full_start

        ts_warmup = _ts(warmup_start)
        ts_end = _ts(fold["test_end"])
        fold_prices = monthly_prices.loc[
            (monthly_prices.index >= ts_warmup) & (monthly_prices.index <= ts_end)
        ].copy()

        if fold_prices.empty or len(fold_prices) < 4:
            print(f"  Fold {i:2d}: too few rows, skip")
            continue

        test_label = (
            f"{fold['test_start'][:4]}{fold['test_start'][4:6]}0"
            f"->>{fold['test_end'][:4]}{fold['test_end'][4:6]}3"
        )

        # Per-fold lambda selection for vol_adjusted multi_sleeve strategies
        selected_lambda = None
        if vol_adj_cfg and strategy_type == "multi_sleeve_rotation":
            warmup_for_train_raw = _add_months(fold["train_start"], -WARMUP_MONTHS)
            warmup_for_train = warmup_for_train_raw if _ts(warmup_for_train_raw) >= _ts(full_start) else full_start
            train_prices_for_lambda = monthly_prices.loc[
                (monthly_prices.index >= _ts(warmup_for_train)) &
                (monthly_prices.index <= _ts(fold["train_end"]))
            ].copy()
            print(f"  Fold {i:2d}: selecting lambda, train={fold['train_start']}~{fold['train_end']}")
            selected_lambda = select_lambda_on_train_window(
                train_prices_for_lambda, overlay, monthly_benchmark,
                fold["train_start"], fold["train_end"],
                vol_adj_cfg.get("lambda_search_space", [0.3, 0.5, 0.7]),
                candidate_params,
                vol_lookback_months=vol_adj_cfg.get("vol_lookback_months", 3),
            )
            modified_alloc = dict(candidate_params.get("risk_on_allocation", {}))
            modified_alloc["vol_penalty"] = selected_lambda
            modified_alloc["vol_formula"] = "linear_subtract"
            modified_alloc["vol_lookback_months"] = vol_adj_cfg.get("vol_lookback_months", 3)
            fold_candidate_params = dict(candidate_params)
            fold_candidate_params["risk_on_allocation"] = modified_alloc
        else:
            fold_candidate_params = candidate_params

        cm = run_fold(fold_prices, overlay, monthly_benchmark, cand_cfg, cand_min_hold,
                      fold["test_start"], fold["test_end"], strategy_type, regime_filter,
                      defensive_mode=defensive_mode, defensive_asset=defensive_asset,
                      multi_sleeve_params=fold_candidate_params if strategy_type == "multi_sleeve_rotation" else None,
                      monthly_volumes=monthly_volumes)
        bm = run_fold(fold_prices, overlay, monthly_benchmark, base_cfg, base_min_hold,
                      fold["test_start"], fold["test_end"],
                      strategy_type="multi_sleeve_rotation",
                      multi_sleeve_params=SIMPLE_THRESHOLD_BASELINE_MULTI_SLEEVE)

        cand_folds.append({
            "fold": i, "test_period": test_label,
            "oos_return": cm["oos_return"], "oos_mdd": cm["oos_mdd"], "oos_sharpe": cm["oos_sharpe"],
            "regime_stats": cm.get("regime_stats", {}),
            "selected_lambda": selected_lambda,
        })
        base_folds.append({
            "fold": i, "test_period": test_label,
            "oos_return": bm["oos_return"], "oos_mdd": bm["oos_mdd"], "oos_sharpe": bm["oos_sharpe"],
        })

        print(
            f"  Fold {i:2d} [{fold['test_start'][:6]}~{fold['test_end'][:6]}]"
            f"  cand={cm['oos_return']:+.2%} mdd={cm['oos_mdd']:.2%}"
            f"  base={bm['oos_return']:+.2%} mdd={bm['oos_mdd']:.2%}"
        )

    cand_agg = aggregate_folds(cand_folds)
    base_agg = aggregate_folds(base_folds)
    cov_years = _coverage_years(full_start, full_end)
    risk_on_periods = sum(int(f.get("regime_stats", {}).get("risk_on_periods", 0)) for f in cand_folds)
    risk_off_periods = sum(int(f.get("regime_stats", {}).get("risk_off_periods", 0)) for f in cand_folds)
    total_regime_periods = risk_on_periods + risk_off_periods
    pmi_veto_periods = sum(int(f.get("regime_stats", {}).get("pmi_veto_periods", 0)) for f in cand_folds)
    pmi_veto_csi300_returns: list = []
    for f in cand_folds:
        pmi_veto_csi300_returns.extend(f.get("regime_stats", {}).get("pmi_veto_csi300_returns", []))

    # Aggregate per-holding circuit breaker stats (legacy, should be 0 for iter30)
    all_cb_triggers = []
    for f in cand_folds:
        all_cb_triggers.extend(f.get("regime_stats", {}).get("circuit_breaker_triggers", []))
    cb_trigger_by_symbol: dict = {}
    for t in all_cb_triggers:
        sym = t.get("symbol", "unknown")
        cb_trigger_by_symbol[sym] = cb_trigger_by_symbol.get(sym, 0) + 1

    # Aggregate portfolio-level circuit breaker stats
    all_portfolio_cb_triggers = []
    for f in cand_folds:
        all_portfolio_cb_triggers.extend(f.get("regime_stats", {}).get("portfolio_cb_triggers", []))

    print(f"  CANDIDATE annual={cand_agg['oos_annual_return']:+.4f}  mdd={cand_agg['oos_max_drawdown']:.4f}")
    print(f"  BASELINE  annual={base_agg['oos_annual_return']:+.4f}  mdd={base_agg['oos_max_drawdown']:.4f}")
    if all_cb_triggers:
        print(f"  Per-holding CB triggers: {len(all_cb_triggers)} total; by symbol: {cb_trigger_by_symbol}")
    if all_portfolio_cb_triggers:
        print(f"  Portfolio CB triggers: {len(all_portfolio_cb_triggers)} total")
        for t in all_portfolio_cb_triggers:
            print(f"    {t['date']}: portfolio_drawdown={t['portfolio_drawdown']:.2%}  nav={t['nav']:.4f}  peak={t['peak_nav']:.4f}")

    return {
        "candidate_oos_annual_return": cand_agg["oos_annual_return"],
        "candidate_oos_max_drawdown": cand_agg["oos_max_drawdown"],
        "candidate_oos_sharpe": cand_agg["oos_sharpe"],
        "baseline_oos_annual_return": base_agg["oos_annual_return"],
        "baseline_oos_max_drawdown": base_agg["oos_max_drawdown"],
        "baseline_oos_sharpe": base_agg["oos_sharpe"],
        "n_folds": len(cand_folds),
        "coverage_years": cov_years,
        "n_symbols": n_symbols,
        "regime_stats": {
            "risk_on_periods": risk_on_periods,
            "risk_off_periods": risk_off_periods,
            "risk_on_ratio": round(risk_on_periods / total_regime_periods, 4) if total_regime_periods else None,
            "pmi_veto_periods": pmi_veto_periods,
            "pmi_veto_csi300_returns": pmi_veto_csi300_returns,
        },
        "circuit_breaker_stats": {
            "total_triggers": len(all_cb_triggers),
            "triggers_by_symbol": cb_trigger_by_symbol,
            "trigger_log": all_cb_triggers,
        },
        "portfolio_circuit_breaker_stats": {
            "total_triggers": len(all_portfolio_cb_triggers),
            "trigger_log": all_portfolio_cb_triggers,
        },
        "fold_details": cand_folds,
        "baseline_fold_details": base_folds,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Long-term multi-mode rotation backtest")
    parser.add_argument("--mode", choices=["baseline", "candidate"], default="baseline")
    parser.add_argument("--params-file", default=None,
                        help="JSON with candidate params (required for --mode=candidate)")
    parser.add_argument("--baseline-file", default=None,
                        help="Path to prior baseline metrics JSON (informational only)")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    if args.mode == "candidate" and args.params_file:
        with open(args.params_file) as f:
            proposal = json.load(f)
        strategy_type = proposal.get("strategy_type", "standard_rotation")
        if strategy_type == "multi_sleeve_rotation":
            candidate_params = proposal
        else:
            candidate_params = proposal.get("params", BASELINE_PARAMS)
        regime_filter = proposal.get("regime_filter", DEFAULT_REGIME_FILTER)
        defensive_mode = proposal.get("defensive_mode", "cash")
        raw_defensive_asset = proposal.get("defensive_asset", None)
    else:
        proposal = {}
        candidate_params = BASELINE_PARAMS
        strategy_type = "standard_rotation"
        regime_filter = DEFAULT_REGIME_FILTER
        defensive_mode = "cash"
        raw_defensive_asset = None

    # Normalize defensive_asset: index symbols -> ETF symbol in universe
    _DEFENSIVE_ASSET_MAP = {"000300.SH": "510310.SH"}
    defensive_asset = _DEFENSIVE_ASSET_MAP.get(raw_defensive_asset, raw_defensive_asset)

    baseline_params = BASELINE_PARAMS

    print(f"Mode:      {args.mode}")
    print(f"Candidate: {candidate_params}")
    print(f"Baseline:  {baseline_params}")
    print(f"Strategy:  {strategy_type}")
    if strategy_type == "regime_conditioned_rotation":
        print(f"Regime:    {regime_filter}")
        print(f"Defensive: {defensive_mode}")
        if defensive_mode == "broad_index":
            print(f"Defensive asset (normalized): {defensive_asset}")
        elif defensive_mode not in ("cash",):
            print(f"FATAL: unsupported defensive_mode={defensive_mode}")
            sys.exit(1)

    data_service = DataService()
    proxy_mapping_out: list[dict] = []
    results: dict[str, dict] = {}
    errors: list[dict] = []

    for mode in ["index_proxy", "real_etf_subset", "real_etf_full"]:
        try:
            results[mode] = run_mode(
                mode,
                candidate_params,
                baseline_params,
                data_service,
                proxy_mapping_out,
                strategy_type,
                regime_filter,
                defensive_mode=defensive_mode,
                defensive_asset=defensive_asset,
            )
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            print(f"[ERROR] Mode {mode} failed: {exc}\n{tb}")
            errors.append({"mode": mode, "error": str(exc)})

    if "index_proxy" not in results:
        print("FATAL: index_proxy mode failed -- cannot satisfy coverage gate.")
        sys.exit(1)

    index_cov = results["index_proxy"].get("coverage_years", 0.0)
    gate_failures: list[str] = []
    if index_cov < 10.0:
        gate_failures.append(f"index_proxy_coverage_years={index_cov} < 10")

    output = {
        "exit_code": 0,
        "mode": args.mode,
        "command": " ".join(sys.argv),
        "data_modes_validated": list(results.keys()),
        "index_proxy_coverage_years": results.get("index_proxy", {}).get("coverage_years", 0.0),
        "real_etf_subset_coverage_years": results.get("real_etf_subset", {}).get("coverage_years", 0.0),
        "real_etf_full_coverage_years": results.get("real_etf_full", {}).get("coverage_years", 0.0),
        "params": candidate_params,
        "baseline_params": baseline_params,
        "strategy_type": strategy_type,
        "regime_filter": regime_filter,
        "defensive_mode": defensive_mode,
        "defensive_asset": defensive_asset,
        "proposal": proposal,
        "regime_stats": {
            mode: mode_result.get("regime_stats", {})
            for mode, mode_result in results.items()
        },
        "proxy_mapping": proxy_mapping_out,
        "results": results,
        "errors": errors,
        "gate_failures": gate_failures,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nOutput written to {out_path}")

    if gate_failures:
        print(f"Gate failures: {gate_failures}")
        sys.exit(1)


if __name__ == "__main__":
    main()
