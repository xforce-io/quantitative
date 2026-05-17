#!/usr/bin/env python3
"""Refresh all factor data in data/factors.db.

Usage:
    python scripts/refresh_factors.py           # full history from 2010
    python scripts/refresh_factors.py --update  # last 6 months only
"""
from __future__ import annotations
import argparse
import sqlite3
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from quant.data.db import init_db
from quant.data.fetchers.etf_shares import fetch_etf_shares
from quant.data.fetchers.valuation import fetch_valuation
from quant.data.fetchers.macro_pmi import fetch_pmi
from quant.data.fetchers.proxy_ext import fetch_proxy_ext

DB_PATH = str(_ROOT / "data" / "factors.db")

# All ETF candidates: existing 15 + 7 extended
ALL_ETF_SYMBOLS = [
    "512010.SH", "512660.SH", "512800.SH", "510880.SH", "159869.SZ",
    "512980.SH", "515050.SH", "159995.SZ", "159776.SZ", "512480.SH",
    "159605.SZ", "516160.SH", "512880.SH", "510050.SH", "510300.SH",
    "516220.SH", "561910.SH", "159201.SZ", "159732.SZ", "159992.SZ",
    "512050.SH", "513180.SH",
]

# Industry index proxies for valuation (from existing PROXY_MAP + new)
VALUATION_SYMBOLS = [
    "000933.SH", "399959.SZ", "399986.SZ", "000015.SH", "000807.SH",
    "399971.SZ", "399812.SZ", "399673.SZ", "399976.SZ", "000685.SH",
    "000794.SH", "000952.SH", "399975.SZ", "000016.SH", "000300.SH",
    "399101.SZ", "399006.SZ", "000922.SH", "399995.SZ", "000951.SH",
    "000510.SH",
]


def _print_status(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        for table in ["etf_shares", "industry_valuation", "macro_pmi", "proxy_prices_ext"]:
            row = conn.execute(
                f"SELECT COUNT(*), MAX(date) FROM {table}"
            ).fetchone()
            print(f"  {table:<25} rows={row[0]:>6}  latest={row[1]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true",
                        help="Incremental: fetch last 6 months only")
    args = parser.parse_args()

    init_db(DB_PATH)

    if args.update:
        today = date.today()
        # Go back 6 months using timedelta approximation (6*30 days)
        six_months_ago = today - timedelta(days=180)
        start_yyyymm = six_months_ago.strftime("%Y%m")
        start_date = six_months_ago.strftime("%Y%m%d")
        end_date = today.strftime("%Y%m%d")
    else:
        start_date = "20100101"
        end_date = date.today().strftime("%Y%m%d")
        start_yyyymm = "201001"

    end_yyyymm = date.today().strftime("%Y%m")
    print(f"Refreshing factors: {start_date} → {end_date}\n")

    fetchers = [
        ("ETF shares",   lambda: fetch_etf_shares(ALL_ETF_SYMBOLS, start_date, end_date, DB_PATH)),
        ("Valuation",    lambda: fetch_valuation(VALUATION_SYMBOLS, start_date, end_date, DB_PATH)),
        ("PMI",          lambda: fetch_pmi(start_yyyymm, end_yyyymm, DB_PATH)),
        ("Proxy ext",    lambda: fetch_proxy_ext(start_date, end_date, DB_PATH)),
    ]

    for name, fn in fetchers:
        try:
            n = fn()
            print(f"  ✓ {name}: {n} rows upserted")
        except Exception:
            print(f"  ✗ {name}: FAILED")
            traceback.print_exc()

    print("\nDB status:")
    _print_status(DB_PATH)


if __name__ == "__main__":
    main()
