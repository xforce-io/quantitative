"""Fetch monthly industry index PE/PB and rolling percentile into factors.db."""
from __future__ import annotations
import os
import sqlite3
import pandas as pd
import tushare as ts

ROLLING_MONTHS = 60  # 5-year window for percentile


def _get_pro():
    return ts.pro_api(os.getenv("TUSHARE_TOKEN"))


def _month_end_trading_dates(pro, start_date: str, end_date: str) -> list[str]:
    """Return last trading day of each month in YYYYMMDD format."""
    df = pro.trade_cal(
        exchange="SSE",
        start_date=start_date,
        end_date=end_date,
        is_open="1",
        fields="cal_date",
    )
    dates = pd.to_datetime(df["cal_date"], format="%Y%m%d")
    return (
        dates.groupby(dates.dt.to_period("M"))
        .max()
        .dt.strftime("%Y%m%d")
        .tolist()
    )


def fetch_valuation(
    symbols: list[str],
    start_date: str,
    end_date: str,
    db_path: str = "data/factors.db",
) -> int:
    """
    Fetch month-end PE/PB for industry indices. Compute 5-year rolling percentile.
    Requires existing rows in DB for percentile window; extend start_date back 5 years
    when calling for the first time.

    Returns:
        Total rows upserted.
    """
    pro = _get_pro()
    month_ends = _month_end_trading_dates(pro, start_date, end_date)

    # Collect raw PE/PB per symbol per month
    records: dict[str, list[tuple]] = {s: [] for s in symbols}
    for trade_date in month_ends:
        df = pro.index_dailybasic(
            trade_date=trade_date,
            fields="ts_code,trade_date,pe_ttm,pb",
        )
        if df is None or df.empty:
            continue
        dt_str = pd.to_datetime(trade_date, format="%Y%m%d").strftime("%Y-%m-%d")
        for symbol in symbols:
            row = df[df["ts_code"] == symbol]
            if row.empty:
                continue
            records[symbol].append((dt_str, float(row["pe_ttm"].iloc[0]), float(row["pb"].iloc[0])))

    # Compute rolling percentile per symbol
    rows: list[tuple] = []
    for symbol, data in records.items():
        if not data:
            continue
        df_sym = pd.DataFrame(data, columns=["date", "pe_ttm", "pb_mrq"])
        df_sym = df_sym.sort_values("date").reset_index(drop=True)
        df_sym["pe_pct"] = df_sym["pe_ttm"].rolling(ROLLING_MONTHS, min_periods=12).apply(
            lambda x: (x.iloc[-1] > x[:-1]).mean() if len(x) > 1 else 0.5
        )
        df_sym["pb_pct"] = df_sym["pb_mrq"].rolling(ROLLING_MONTHS, min_periods=12).apply(
            lambda x: (x.iloc[-1] > x[:-1]).mean() if len(x) > 1 else 0.5
        )
        for _, r in df_sym.iterrows():
            pe_pct = float(r["pe_pct"]) if pd.notna(r["pe_pct"]) else 0.5
            pb_pct = float(r["pb_pct"]) if pd.notna(r["pb_pct"]) else 0.5
            rows.append((r["date"], symbol, r["pe_ttm"], r["pb_mrq"], pe_pct, pb_pct))

    if not rows:
        return 0

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO industry_valuation
               (date, symbol, pe_ttm, pb_mrq, pe_pct, pb_pct)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
    return len(rows)
