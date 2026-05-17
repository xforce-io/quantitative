"""Fetch monthly ETF share data from Tushare into factors.db."""
from __future__ import annotations
import os
import sqlite3
import pandas as pd
import tushare as ts


def _get_pro():
    return ts.pro_api(os.getenv("TUSHARE_TOKEN"))


def fetch_etf_shares(
    symbols: list[str],
    start_date: str,
    end_date: str,
    db_path: str = "data/factors.db",
) -> int:
    """
    Pull daily ETF share data from Tushare, resample to month-end, upsert into DB.

    Args:
        symbols:    List of ETF codes, e.g. ['512480.SH']
        start_date: YYYYMMDD
        end_date:   YYYYMMDD
        db_path:    Path to factors.db

    Returns:
        Total rows upserted.
    """
    pro = _get_pro()
    rows: list[tuple] = []

    for symbol in symbols:
        df = pro.fund_share(ts_code=symbol, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            continue
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        monthly = (
            df.set_index("trade_date")["fd_share"]
            .resample("ME")
            .last()
            .dropna()
        )
        for dt, shares in monthly.items():
            rows.append((dt.strftime("%Y-%m-%d"), symbol, float(shares)))

    if not rows:
        return 0

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO etf_shares (date, symbol, shares) VALUES (?, ?, ?)",
            rows,
        )
    return len(rows)
