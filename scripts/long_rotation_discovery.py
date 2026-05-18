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
      --params-file .petri/artifacts/propose/strategist/proposal.json \
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
    PortfolioCombiner,
    RankerConfig,
    RotationBacktestConfig,
    RotationBacktester,
    load_universe,
)
from quant.analysis.rotation.regime_overlay import PrecomputedRegimeOverlay
from quant.services.data_service import DataService, PriceRequest

UNIVERSE_YAML = _ROOT / "config" / "rotation_universe.yaml"

TRAIN_MONTHS = 24
TEST_MONTHS = 6
STEP_MONTHS = 6
WARMUP_MONTHS = 15  # >= lookback(9) + skip(1) + buffer

SUBSET_CUTOFF_TS = pd.Timestamp("2014-12-31")

# Single-day |return| threshold above which an ETF's price series is presumed
# contaminated by a share split / merger that the data provider failed to
# adjust (前复权). Diversified ETFs cannot move > ±25% in one day under any
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

DEFAULT_REGIME_FILTER = {
    "enabled": False,
    "benchmark_symbol": "000300.SH",
    "benchmark_lookback_months": 6,
    "benchmark_min_return": 0.0,
    "industry_momentum_lookback_months": 6,
    "positive_ratio_threshold": 0.7,
}

MODE_SETUP = {
    "index_proxy":     {"full_start": "20100101", "full_end": "20241231"},
    "real_etf_subset": {"full_start": "20140101", "full_end": "20241231"},
    "real_etf_full":   {"full_start": "20180101", "full_end": "20241231"},
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
    "518880.SH": ("AU9999.SGE", "黄金现货"),
    "513100.SH": ("NDX.GI", "纳斯达克100"),
    "511260.SH": ("000012.SH", "国债指数"),
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

    def __init__(self, inner: MomentumRanker, min_hold_months: int = 1) -> None:
        self.inner = inner
        self.min_hold = max(1, min_hold_months)
        self._current: dict[str, float] = {}
        self._last_change_loc: int | None = None

    def rank(self, monthly_prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        loc = monthly_prices.index.get_loc(rebalance_date)

        # Enforce hold constraint only when currently invested
        if (self._current and self._last_change_loc is not None
                and (loc - self._last_change_loc) < self.min_hold):
            return self._current

        new = self.inner.rank(monthly_prices, rebalance_date)
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
        monthly_benchmark: pd.Series,
        regime_filter: dict,
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
        if (self.defensive_mode == "broad_index"
                and self.defensive_asset
                and self.defensive_asset in monthly_prices.columns):
            return {self.defensive_asset: 1.0}
        return {}  # cash

    def _is_risk_on(self, monthly_prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> bool:
        loc = monthly_prices.index.get_loc(rebalance_date)
        benchmark_lookback = int(self.regime_filter["benchmark_lookback_months"])

        bench_ok = self._benchmark_return_ok(rebalance_date, benchmark_lookback)
        if not bench_ok:
            return False

        # positive_ratio_threshold == None means skip this condition entirely
        threshold = self.regime_filter.get("positive_ratio_threshold")
        if threshold is None:
            return True

        momentum_lookback = int(self.regime_filter.get("industry_momentum_lookback_months", benchmark_lookback))
        return self._positive_ratio_ok(monthly_prices, loc, momentum_lookback, float(threshold))

    def _benchmark_return_ok(self, rebalance_date: pd.Timestamp, lookback_months: int) -> bool:
        bench = self.monthly_benchmark.reindex(self.monthly_benchmark.index.union([rebalance_date])).sort_index().ffill()
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

    def _positive_ratio_ok(self, monthly_prices: pd.DataFrame, loc: int, lookback_months: int, threshold: float) -> bool:
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
        ratio = positive / valid
        return ratio >= threshold


class MultiSleeveRanker:
    """Allocates capital to different sleeves based on a risk-on regime rule."""

    def __init__(
        self,
        monthly_benchmark: pd.Series,
        risk_on_rule: dict,
        risk_on_allocation: dict,
        risk_off_allocation: dict,
    ) -> None:
        self.monthly_benchmark = monthly_benchmark.sort_index()
        self.risk_on_rule = risk_on_rule
        self.risk_on_allocation = risk_on_allocation
        self.risk_off_allocation = risk_off_allocation
        
        self.risk_on_ranker = MinHoldRanker(
            MomentumRanker(make_ranker_cfg(self.risk_on_allocation)),
            self.risk_on_allocation.get("min_hold_months", 1)
        )
        self.risk_off_ranker = MinHoldRanker(
            MomentumRanker(make_ranker_cfg(self.risk_off_allocation)),
            self.risk_off_allocation.get("min_hold_months", 1)
        )
        
        self.stats = {"risk_on_periods": 0, "risk_off_periods": 0}
        
    def rank(self, monthly_prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        is_risk_on = self._is_risk_on(monthly_prices, rebalance_date)
        
        if is_risk_on:
            self.stats["risk_on_periods"] += 1
            sleeve = self.risk_on_allocation.get("sleeve", "industry")
        else:
            self.stats["risk_off_periods"] += 1
            sleeve = self.risk_off_allocation.get("sleeve", "defensive_global")
            
        symbols = SLEEVE_MAP.get(sleeve, list(monthly_prices.columns))
        valid_symbols = [c for c in symbols if c in monthly_prices.columns]
        
        if not valid_symbols:
            return {}
            
        slice_df = monthly_prices[valid_symbols]
        if is_risk_on:
            return self.risk_on_ranker.rank(slice_df, rebalance_date)
        else:
            return self.risk_off_ranker.rank(slice_df, rebalance_date)
            
    def _is_risk_on(self, monthly_prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> bool:
        lookback = int(self.risk_on_rule.get("lookback_months", 6))
        min_return = float(self.risk_on_rule.get("min_return", 0.0))
        
        bench = self.monthly_benchmark.reindex(self.monthly_benchmark.index.union([rebalance_date])).sort_index().ffill()
        if rebalance_date not in bench.index:
            return False
        loc = bench.index.get_loc(rebalance_date)
        start_idx = loc - lookback
        if start_idx < 0:
            return False
        p0 = bench.iloc[start_idx]
        p1 = bench.iloc[loc]
        if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
            return False
        ret = float(p1 / p0 - 1.0)
        return ret > min_return


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
# Data fetching
# ---------------------------------------------------------------------------

def fetch_proxy_monthly_prices(
    data_service: DataService, full_start: str, full_end: str
) -> tuple[pd.DataFrame, list[dict]]:
    """Fetch index proxy prices for all ETFs; returns (monthly_df, proxy_mapping)."""
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
            monthly = close.resample("ME").last().dropna()
            if monthly.empty:
                continue
            frames[etf_sym] = monthly
            start_date = monthly.index[0].strftime("%Y-%m-%d")
            end_date = monthly.index[-1].strftime("%Y-%m-%d")
            cov = round((monthly.index[-1] - monthly.index[0]).days / 365.25, 2)
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


def fetch_etf_monthly_prices(
    data_service: DataService, full_start: str, full_end: str, subset: bool = False
) -> tuple[pd.DataFrame, int]:
    """Fetch actual ETF monthly prices; optionally filter to historical subset."""
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
            daily_ret = close.pct_change()
            max_jump = daily_ret.abs().max()
            if pd.notna(max_jump) and max_jump > MAX_SINGLE_DAY_ABS_RET:
                bad_dt = daily_ret.abs().idxmax()
                print(
                    f"  [SKIP anomaly] {entry.symbol}: |daily ret|={max_jump:.2%} on "
                    f"{bad_dt.date()} — unadjusted split/merger suspected"
                )
                continue
            monthly = close.resample("ME").last().dropna()
            if monthly.empty:
                continue
            if subset and monthly.index[0] > SUBSET_CUTOFF_TS:
                print(f"  [SKIP subset] {entry.symbol}: first={monthly.index[0].date()} > cutoff")
                continue
            frames[entry.symbol] = monthly
            tag = "subset" if subset else "full"
            print(f"  [OK {tag}] {entry.symbol}: {monthly.index[0].date()} ~ {monthly.index[-1].date()}")
        except Exception as exc:
            print(f"  [ERROR] {entry.symbol}: {exc}")

    if not frames:
        raise RuntimeError(f"No ETF data for {'subset' if subset else 'full'} mode")

    df_all = pd.DataFrame(frames).sort_index()
    return df_all, len(frames)


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


def fetch_monthly_benchmark(
    data_service: DataService, full_start: str, full_end: str
) -> pd.Series:
    """Return monthly close prices for CSI 300 as benchmark series."""
    try:
        df = data_service.get_price(PriceRequest(
            symbol="000300.SH",
            start=full_start,
            end=full_end,
            asset_type="index",
        ))
        close = df["close"].astype(float)
        return close.resample("ME").last().dropna()
    except Exception as exc:
        print(f"  [WARN] benchmark fetch failed: {exc}")
        return pd.Series(dtype=float)


def make_ranker_cfg(params: dict) -> RankerConfig:
    return RankerConfig(
        lookback_months=params["lookback_months"],
        skip_recent_months=params.get("skip_months", params.get("skip_recent_months", 1)),
        top_k=params["top_k"],
        vol_penalty=params.get("vol_penalty", 0.0),
    )


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
) -> dict:
    """Run one walk-forward fold; return OOS metrics dict."""
    ranker = MinHoldRanker(MomentumRanker(ranker_cfg), min_hold_months)
    regime_ranker = None
    
    if strategy_type == "multi_sleeve_rotation" and multi_sleeve_params:
        regime_ranker = MultiSleeveRanker(
            monthly_benchmark,
            multi_sleeve_params.get("risk_on_rule", {}),
            multi_sleeve_params.get("risk_on_allocation", {}),
            multi_sleeve_params.get("risk_off_allocation", {}),
        )
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
        metrics = slice_fold_metrics(result.monthly_returns["strategy"], test_start, test_end)
        if regime_ranker is not None:
            metrics["regime_stats"] = dict(regime_ranker.stats)
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
        monthly_prices, n_symbols = fetch_etf_monthly_prices(data_service, full_start, full_end, subset=True)
    else:
        monthly_prices, n_symbols = fetch_etf_monthly_prices(data_service, full_start, full_end, subset=False)

    print(f"  {n_symbols} symbols, {len(monthly_prices)} monthly rows")

    # 2. Overlay and benchmark (full period)
    print("  Building overlay...")
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

        cm = run_fold(fold_prices, overlay, monthly_benchmark, cand_cfg, cand_min_hold,
                      fold["test_start"], fold["test_end"], strategy_type, regime_filter,
                      defensive_mode=defensive_mode, defensive_asset=defensive_asset,
                      multi_sleeve_params=candidate_params if strategy_type == "multi_sleeve_rotation" else None)
        bm = run_fold(fold_prices, overlay, monthly_benchmark, base_cfg, base_min_hold,
                      fold["test_start"], fold["test_end"])

        cand_folds.append({
            "fold": i, "test_period": test_label,
            "oos_return": cm["oos_return"], "oos_mdd": cm["oos_mdd"], "oos_sharpe": cm["oos_sharpe"],
            "regime_stats": cm.get("regime_stats", {}),
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

    print(f"  CANDIDATE annual={cand_agg['oos_annual_return']:+.4f}  mdd={cand_agg['oos_max_drawdown']:.4f}")
    print(f"  BASELINE  annual={base_agg['oos_annual_return']:+.4f}  mdd={base_agg['oos_max_drawdown']:.4f}")

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
