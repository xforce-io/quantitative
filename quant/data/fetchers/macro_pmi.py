"""Fetch monthly PMI data from Tushare into factors.db."""
from __future__ import annotations
import os
import sqlite3
import pandas as pd
import tushare as ts


def _get_pro():
    return ts.pro_api(os.getenv("TUSHARE_TOKEN"))


def _build_month_end_map(pro, months: list[str]) -> dict[str, str]:
    """Build {YYYYMM: YYYY-MM-DD} mapping for last trading day of each month.

    Issues a single trade_cal API call covering the full range, instead of
    one call per month.
    """
    if not months:
        return {}
    months_sorted = sorted(months)
    start = months_sorted[0] + "01"
    year, month = int(months_sorted[-1][:4]), int(months_sorted[-1][4:])
    if month == 12:
        end = f"{year+1}0101"
    else:
        end = f"{year}{month+1:02d}01"
    df = pro.trade_cal(exchange="SSE", start_date=start, end_date=end, is_open="1", fields="cal_date")
    dates = pd.to_datetime(df["cal_date"], format="%Y%m%d")
    result: dict[str, str] = {}
    for period, group in dates.groupby(dates.dt.to_period("M")):
        yyyymm = period.strftime("%Y%m")
        last = group.max()
        if pd.isna(last):
            raise ValueError(f"No trading days found for month {yyyymm}")
        result[yyyymm] = last.strftime("%Y-%m-%d")
    return result


def fetch_pmi(
    start_month: str,
    end_month: str,
    db_path: str = "data/factors.db",
) -> int:
    """
    Fetch monthly PMI and upsert into macro_pmi table.
    date column is the last trading day of the publication month.

    Args:
        start_month: YYYYMM
        end_month:   YYYYMM

    Returns:
        Rows upserted.
    """
    pro = _get_pro()
    df = pro.cn_pmi(start_m=start_month, end_m=end_month)
    if df is None or df.empty:
        return 0

    months = [str(row["MONTH"]) for _, row in df.iterrows()]
    month_end_map = _build_month_end_map(pro, months)

    rows: list[tuple] = []
    for _, row in df.iterrows():
        yyyymm = str(row["MONTH"])
        date_str = month_end_map.get(yyyymm)
        if date_str is None:
            continue
        mfg = float(row["PMI010000"]) if pd.notna(row["PMI010000"]) else None
        non_mfg = float(row["PMI030000"]) if pd.notna(row["PMI030000"]) else None
        rows.append((date_str, mfg, non_mfg))

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO macro_pmi (date, mfg_pmi, non_mfg_pmi) VALUES (?, ?, ?)",
            rows,
        )
    return len(rows)
