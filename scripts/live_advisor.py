#!/usr/bin/env python3
"""live_advisor.py — Compute next-month target allocation from a strategy spec.

Reuses MultiSleeveRanker logic from long_rotation_discovery.py to produce
a single rebalance decision at a specified month-end. Optionally diffs against
current holdings to give explicit sell/buy actions.

Usage:
    python scripts/live_advisor.py \\
        --as-of 2026-04-30 \\
        [--current-holdings my_portfolio.csv] \\
        [--output recommendation.json]

    python scripts/live_advisor.py \\
        --spec config/strategies/rotation/run_007_production.json \\
        --as-of 2026-04-30

Holdings CSV format (one of):
    symbol,weight
    512000.SH,0.33
    512170.SH,0.33
    ...
OR
    symbol,shares,price
    512000.SH,1000,1.234
    ...
"""
import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_DEFAULT_SOTA_PATH = _ROOT / "config" / "strategies" / "rotation" / "sota.json"

from quant.services.data_service import DataService  # noqa: E402

from scripts.long_rotation_discovery import (  # noqa: E402
    MultiSleeveRanker,
    PortfolioLevelCBRanker,
    SYMBOL_ALIASES,
    fetch_etf_monthly_prices,
    fetch_monthly_benchmark,
    fetch_monthly_volumes,
)

ETF_NAMES = {
    "510050.SH": "上证50", "512000.SH": "券商", "512800.SH": "银行",
    "512170.SH": "医疗", "512010.SH": "医药", "159995.SZ": "芯片",
    "515050.SH": "5G", "512720.SH": "计算机", "159928.SZ": "消费",
    "159825.SZ": "农业", "512400.SH": "有色", "515220.SH": "煤炭",
    "515210.SH": "钢铁", "159611.SZ": "电力", "159930.SZ": "能源",
    "512660.SH": "军工", "515030.SH": "新能源车", "515790.SH": "光伏",
    "159870.SZ": "化工", "512200.SH": "房地产", "516220.SH": "物联网",
    "561910.SH": "储能", "159201.SZ": "自由现金流", "159732.SZ": "消费电子",
    "159992.SZ": "创新药", "512050.SH": "A500", "513180.SH": "恒生科技",
    "510880.SH": "红利", "159949.SZ": "创业板50", "510310.SH": "沪深300",
    "510300.SH": "沪深300", "159922.SZ": "中证500", "512890.SH": "红利低波",
    "518880.SH": "黄金", "513100.SH": "纳指", "511260.SH": "十年国债",
    "511010.SH": "国债", "511880.SH": "短债",
}


def cn(sym: str) -> str:
    return ETF_NAMES.get(sym, sym)


def load_current_holdings(path: str | None) -> dict[str, float]:
    if not path:
        return {}
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    if "weight" in df.columns:
        out = {}
        for _, row in df.iterrows():
            sym = str(row["symbol"]).strip()
            w = float(row["weight"])
            if w > 0:
                out[sym] = w
        total = sum(out.values())
        if total > 1.5 or total < 0.5:
            print(f"[warn] holdings weights sum to {total:.3f} (expected ~1.0); normalising")
            out = {k: v / total for k, v in out.items()}
        return out
    if {"shares", "price"}.issubset(df.columns):
        df["value"] = df["shares"].astype(float) * df["price"].astype(float)
        total = df["value"].sum()
        if total <= 0:
            return {}
        return {str(r["symbol"]).strip(): float(r["value"] / total)
                for _, r in df.iterrows() if r["value"] > 0}
    raise ValueError("holdings CSV must have either 'weight' or 'shares'+'price' columns")


def spec_needs_volume(spec: dict) -> bool:
    factors = (spec.get("risk_on_allocation", {})
               .get("multi_factor_config", {})
               .get("factors", []))
    names = {f.get("name") for f in factors}
    return bool(names & {"shares_momentum", "low_crowding"})


def resolve_spec_path(spec_arg: str | None) -> Path:
    """Resolve the requested strategy spec or the published SOTA spec."""
    if spec_arg:
        path = Path(spec_arg).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path

    sota = json.loads(_DEFAULT_SOTA_PATH.read_text(encoding="utf-8"))
    path = _ROOT / sota["strategy_path"]
    return path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--spec",
        help="strategy spec JSON; defaults to config/strategies/rotation/sota.json target",
    )
    p.add_argument("--as-of", required=True, help="Decision date (month-end, YYYY-MM-DD)")
    p.add_argument("--current-holdings", help="CSV of current portfolio (optional)")
    p.add_argument("--output", help="Save recommendation as JSON (optional)")
    p.add_argument("--start-date", default="20180101", help="Earliest data fetch date (YYYYMMDD)")
    args = p.parse_args()

    spec_path = resolve_spec_path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    as_of_requested = pd.Timestamp(args.as_of)
    fetch_end = (as_of_requested + pd.offsets.MonthEnd(1)).strftime("%Y%m%d")

    print(f"=== Live Advisor ===")
    print(f"Spec:      {spec_path}")
    print(f"Strategy:  {spec.get('iteration', '(unnamed)')}")
    print(f"As of:     {as_of_requested.date()}")
    print()

    ds = DataService()
    print(f"[info] fetching ETF prices ({args.start_date}~{fetch_end}) ...")
    monthly_prices, n_syms = fetch_etf_monthly_prices(ds, args.start_date, fetch_end, subset=False)
    print(f"[info] {n_syms} ETFs loaded; latest row = {monthly_prices.index[-1].date()}")
    monthly_benchmark = fetch_monthly_benchmark(ds, args.start_date, fetch_end)

    monthly_volumes = None
    if spec_needs_volume(spec):
        print(f"[info] spec uses shares_momentum or low_crowding; fetching volume data ...")
        monthly_volumes = fetch_monthly_volumes(ds, "real_etf_full", args.start_date, fetch_end)

    # Snap as_of to nearest available month-end
    if as_of_requested not in monthly_prices.index:
        avail = monthly_prices.index[monthly_prices.index <= as_of_requested]
        if len(avail) == 0:
            print(f"FATAL: no price data on or before {as_of_requested.date()}")
            return 1
        as_of = avail[-1]
        if as_of != as_of_requested:
            print(f"[warn] snapped as_of {as_of_requested.date()} -> {as_of.date()}")
    else:
        as_of = as_of_requested

    # Build ranker stack matching backtest logic
    sleeve_ranker = MultiSleeveRanker(
        monthly_benchmark,
        spec.get("risk_on_rule", {}),
        spec.get("risk_on_allocation", {}),
        spec.get("risk_off_allocation", {}),
        monthly_volumes=monthly_volumes,
    )

    portfolio_cb_cfg = (spec.get("risk_off_allocation", {})
                       .get("portfolio_trailing_drawdown_circuit_breaker", {}))
    cb_enabled = portfolio_cb_cfg.get("enabled", False)
    if cb_enabled:
        print("[warn] spec has portfolio_circuit_breaker but live mode lacks NAV history;")
        print("       running without CB. Track NAV separately to enforce manually.")

    method = spec.get("risk_on_rule", {}).get("method", "simple_threshold")
    if method != "simple_threshold":
        # Stateful regime methods need warm-up replay
        print(f"[info] warming up ranker through history (method={method}) ...")
        for d in monthly_prices.index:
            if d > as_of:
                break
            try:
                sleeve_ranker.rank(monthly_prices, d)
            except Exception:
                pass
        # Now reset and call at as_of? No — keep state. Pull from history.
        # The last call result IS the as_of decision since loop hits d == as_of.
        # But we want the explicit result, so re-rank at as_of:
        # (For simple_threshold, no state, fresh call is fine)

    result = sleeve_ranker.rank(monthly_prices, as_of)

    is_on = sleeve_ranker._is_risk_on(monthly_prices, as_of)
    csi6m = None
    try:
        bench_aligned = monthly_benchmark.reindex(
            monthly_benchmark.index.union([as_of])).sort_index().ffill()
        loc = bench_aligned.index.get_loc(as_of)
        if loc >= 6:
            csi6m = float(bench_aligned.iloc[loc] / bench_aligned.iloc[loc - 6] - 1)
    except Exception:
        pass

    regime_label = "🚀 risk_on" if is_on else "🛡️  risk_off"
    csi_str = f" (CSI300 6m = {csi6m:+.2%})" if csi6m is not None else ""
    print(f"Regime:    {regime_label}{csi_str}")
    print()

    print(f"=== 下月目标持仓 ===")
    if not result:
        print("  (空 / cash) — 信号未触发且无 fallback")
    else:
        for sym, w in sorted(result.items(), key=lambda kv: -kv[1]):
            print(f"  {sym:<11} {cn(sym):<10}  {w:>6.1%}")

    # Diff
    current = load_current_holdings(args.current_holdings)
    if current:
        print()
        print(f"=== 当前持仓 ===")
        for sym, w in sorted(current.items(), key=lambda kv: -kv[1]):
            print(f"  {sym:<11} {cn(sym):<10}  {w:>6.1%}")

        print()
        print(f"=== 调仓操作 ===")
        all_syms = set(current.keys()) | set(result.keys())
        actions = []
        for sym in sorted(all_syms):
            old = current.get(sym, 0.0)
            new = result.get(sym, 0.0)
            delta = new - old
            if abs(delta) > 0.005:
                actions.append((sym, old, new, delta))
        if not actions:
            print("  无需调仓 (持仓与目标一致)")
        else:
            for sym, old, new, delta in actions:
                tag = "🟢 买入" if delta > 0 else "🔴 卖出"
                print(f"  {tag} {sym:<11} {cn(sym):<10}  {old:>5.1%} → {new:>5.1%}  (Δ {delta:+.1%})")

    if args.output:
        out = {
            "as_of": str(as_of.date()),
            "spec_iteration": spec.get("iteration"),
            "regime": "risk_on" if is_on else "risk_off",
            "csi300_6m_return": csi6m,
            "target_weights": {sym: float(w) for sym, w in result.items()},
            "current_weights": {sym: float(w) for sym, w in current.items()} if current else None,
        }
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        json.dump(out, open(args.output, "w"), indent=2, ensure_ascii=False)
        print(f"\n[ok] saved to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
