#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Undervalue × cycle candidate screener (MVP entry).

Examples:
  # Live: price undervalue + static industry cycle on candidate pool
  python bin/undervalue_cycle_screen.py \\
      --from-candidates config/candidates/top_ashare_stocks.txt

  # Offline: re-rank an existing value CSV with cycle veto
  python bin/undervalue_cycle_screen.py \\
      --from-csv reports/ashare_value_breakout_20260711.csv

  # Stricter: also veto late_cycle
  python bin/undervalue_cycle_screen.py \\
      --from-candidates config/candidates/top_ashare_stocks.txt \\
      --exclude-stages decline,late_cycle
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

# Project root on path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from quant.analysis.screener.undervalue_cycle import (
    BAD_CYCLE_STAGES,
    UndervalueCycleConfig,
    apply_undervalue_cycle_screen,
    stages_from_csv_list,
)
from quant.core.logging_config import get_logger
from quant.core.symbol_resolver import SymbolResolver

logger = get_logger(__name__)


def load_candidates(path: Path) -> List[Tuple[str, str, str]]:
    """Load candidates: industry,name,code[,note] per line."""
    rows: List[Tuple[str, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        industry, name, code = parts[0], parts[1], parts[2]
        symbol = SymbolResolver.format_symbol(code)
        rows.append((symbol, name, industry))
    return rows


def price_undervalue_score(close: np.ndarray, high: np.ndarray, low: np.ndarray) -> dict:
    """Compute simple price-based undervalue metrics (0-100 higher=cheaper)."""
    current = float(close[-1])
    high_p = float(np.max(high))
    low_p = float(np.min(low))
    avg_p = float(np.mean(close))
    price_range = high_p - low_p
    if price_range > 0:
        price_position = (current - low_p) / price_range * 100.0
    else:
        price_position = 50.0

    deviation_pct = (current - avg_p) / avg_p * 100.0 if avg_p else 0.0

    x = np.arange(len(close))
    try:
        coeffs = np.polyfit(x, close, 2)
        y_fitted = np.polyval(coeffs, x)
        deviations = (close - y_fitted) / np.where(y_fitted == 0, np.nan, y_fitted) * 100.0
        deviation_std = float(np.nanstd(deviations))
        current_dev = float(deviations[-1]) if not np.isnan(deviations[-1]) else 0.0
        z_score = current_dev / deviation_std if deviation_std > 0 else 0.0
    except Exception:
        z_score = 0.0

    position_score = 100.0 - price_position
    deviation_score = max(0.0, min(100.0, 50.0 - deviation_pct * 2.0))
    z_score_score = max(0.0, min(100.0, 50.0 - z_score * 25.0))
    undervalue_score = position_score * 0.4 + deviation_score * 0.3 + z_score_score * 0.3

    return {
        "current_price": current,
        "price_position": round(price_position, 4),
        "deviation_pct": round(deviation_pct, 4),
        "z_score": round(float(z_score), 4),
        "undervalue_score": round(float(undervalue_score), 2),
    }


def build_live_table(
    stocks: List[Tuple[str, str, str]],
    days: int = 756,
    provider_name: str = "tushare",
) -> pd.DataFrame:
    """Fetch prices and build undervalue table for candidates."""
    from quant import create_data_provider, get_config

    config = get_config()
    provider = create_data_provider(provider_name, config.get_providers_config())
    end = datetime.now()
    start = end - timedelta(days=days)
    start_s, end_s = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    rows = []
    total = len(stocks)
    for i, (symbol, name, industry) in enumerate(stocks, 1):
        print(f"  [{i}/{total}] {symbol} {name} ...", flush=True)
        row = {
            "symbol": symbol,
            "name": name,
            "industry": industry,
            "status": "success",
            "error": "",
            "undervalue_score": np.nan,
            "price_position": np.nan,
            "current_price": np.nan,
        }
        try:
            data = provider.get_stock_data(symbol, start_s, end_s, "D")
            if data is None or data.empty or len(data) < 20:
                row["status"] = "no_data"
                row["error"] = "insufficient price data"
            else:
                close = data["close"].astype(float).values
                high = data["high"].astype(float).values if "high" in data.columns else close
                low = data["low"].astype(float).values if "low" in data.columns else close
                metrics = price_undervalue_score(close, high, low)
                row.update(metrics)
        except Exception as e:
            row["status"] = "error"
            row["error"] = str(e)
            logger.warning("Failed undervalue for %s: %s", symbol, e)
        rows.append(row)

    df = pd.DataFrame(rows)
    ok = df[df["status"] == "success"].copy()
    if ok.empty:
        return df
    return ok


def load_value_csv(path: Path) -> pd.DataFrame:
    """Load an existing value table; normalize undervalue column name."""
    df = pd.read_csv(path)
    if "undervalue_score" not in df.columns:
        for alt in ("price_underval_score", "combined", "safety_margin_score"):
            if alt in df.columns:
                df = df.rename(columns={alt: "undervalue_score"})
                break
    if "undervalue_score" not in df.columns:
        raise ValueError(
            f"{path} missing undervalue_score (or price_underval_score/combined)"
        )
    if "industry" not in df.columns:
        raise ValueError(f"{path} missing industry column")
    return df


def print_report(result: pd.DataFrame, top_n: int = 20) -> None:
    """Print passed / rejected summary to stdout."""
    if result.empty:
        print("\nNo results.\n")
        return

    passed = result[result["passed"]]
    rejected = result[~result["passed"]]
    print("\n" + "=" * 72)
    print("Undervalue × Cycle Screen")
    print("=" * 72)
    print(f"Total: {len(result)}  |  Passed: {len(passed)}  |  Rejected: {len(rejected)}")

    show_cols = [
        c
        for c in [
            "symbol",
            "name",
            "industry",
            "cycle_stage",
            "undervalue_score",
            "cycle_adjusted_score",
            "price_position",
            "reject_reason",
        ]
        if c in result.columns
    ]

    print(f"\n--- PASSED top {min(top_n, len(passed))} (by cycle_adjusted_score) ---")
    if passed.empty:
        print("(none)")
    else:
        print(passed.head(top_n)[show_cols].to_string(index=False))

    print(f"\n--- REJECTED sample (up to {top_n}) ---")
    if rejected.empty:
        print("(none)")
    else:
        # Prefer high undervalue rejects (classic value traps)
        rej = rejected.sort_values("undervalue_score", ascending=False)
        print(rej.head(top_n)[show_cols].to_string(index=False))
    print()


def build_config(args: argparse.Namespace) -> UndervalueCycleConfig:
    if args.exclude_stages:
        exclude = stages_from_csv_list(args.exclude_stages)
    else:
        exclude = BAD_CYCLE_STAGES
        if args.exclude_late_cycle:
            exclude = frozenset(set(exclude) | {"late_cycle"})
    if args.trap_flags is not None:
        trap_set = frozenset(
            p.strip() for p in args.trap_flags.split(",") if p.strip()
        )
    else:
        trap_set = frozenset({"revenue_decline", "profit_collapse"})
    return UndervalueCycleConfig(
        exclude_stages=exclude,
        min_undervalue_score=args.min_undervalue,
        hard_veto_trap_flags=trap_set,
        exclude_late_cycle=args.exclude_late_cycle,
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Undervalue × cycle candidate screen")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--from-candidates",
        type=Path,
        help="Candidate file (industry,name,code,...)",
    )
    src.add_argument(
        "--from-csv",
        type=Path,
        help="Existing value CSV to re-rank with cycle filter",
    )
    parser.add_argument("--days", type=int, default=756, help="Price lookback days")
    parser.add_argument("--provider", default="tushare", help="Data provider")
    parser.add_argument(
        "--exclude-stages",
        default="",
        help="Comma stages to hard-veto (default: decline)",
    )
    parser.add_argument(
        "--exclude-late-cycle",
        action="store_true",
        help="Also hard-veto late_cycle",
    )
    parser.add_argument(
        "--min-undervalue",
        type=float,
        default=0.0,
        help="Minimum undervalue_score to pass",
    )
    parser.add_argument(
        "--trap-flags",
        default=None,
        help="Comma trap flags to hard-veto (default: revenue_decline,profit_collapse)",
    )
    parser.add_argument("--top", type=int, default=20, help="Rows to print")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: reports/undervalue_cycle_YYYYMMDD.csv)",
    )
    args = parser.parse_args(argv)

    cfg = build_config(args)

    if args.from_csv:
        print(f"Loading value CSV: {args.from_csv}")
        table = load_value_csv(args.from_csv)
    else:
        print(f"Loading candidates: {args.from_candidates}")
        stocks = load_candidates(args.from_candidates)
        if not stocks:
            print("No candidates loaded.")
            return 1
        print(f"Computing price undervalue for {len(stocks)} symbols (days={args.days})...")
        table = build_live_table(stocks, days=args.days, provider_name=args.provider)
        # Keep only rows with scores for screening; still write full later
        if "status" in table.columns:
            scored = table[table["status"] == "success"].copy()
        else:
            scored = table
        if scored.empty:
            print("No successful undervalue rows; abort.")
            out = args.output or (
                _ROOT / "reports" / f"undervalue_cycle_{datetime.now():%Y%m%d}.csv"
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(out, index=False, encoding="utf-8-sig")
            print(f"Wrote raw table: {out}")
            return 2
        table = scored

    print(
        f"Applying cycle screen (exclude={sorted(cfg.exclude_stages)}, "
        f"min_uv={cfg.min_undervalue_score})..."
    )
    result = apply_undervalue_cycle_screen(table, cfg)
    print_report(result, top_n=args.top)

    out = args.output or (
        _ROOT / "reports" / f"undervalue_cycle_{datetime.now():%Y%m%d}.csv"
    )
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
