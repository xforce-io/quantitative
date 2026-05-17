"""Fetch monthly proxy prices for extended ETF pool into factors.db."""
from __future__ import annotations
import os
import sqlite3
import pandas as pd
import tushare as ts
import yfinance as yf

EXT_PROXY_MAP: dict[str, dict] = {
    "516220.SH": {"proxy": "399101.SZ", "source": "tushare"},
    "561910.SH": {"proxy": "399006.SZ", "source": "tushare"},
    "159201.SZ": {"proxy": "000922.SH", "source": "tushare"},
    "159732.SZ": {"proxy": "399995.SZ", "source": "tushare"},
    "159992.SZ": {"proxy": "000951.SH", "source": "tushare"},
    "512050.SH": {"proxy": "000510.SH", "source": "tushare"},
    "513180.SH": {"proxy": "^HSTECH",   "source": "yahoo"},
}


def _get_pro():
    return ts.pro_api(os.getenv("TUSHARE_TOKEN"))


def _fetch_tushare_monthly(pro, proxy_symbol: str, start_date: str, end_date: str) -> pd.Series:
    df = pro.index_daily(
        ts_code=proxy_symbol,
        start_date=start_date,
        end_date=end_date,
        fields="trade_date,close",
    )
    if df is None or df.empty:
        return pd.Series(dtype=float)
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    return df.set_index("trade_date")["close"].resample("ME").last().dropna()


def _fetch_yahoo_monthly(proxy_symbol: str, start_date: str, end_date: str) -> pd.Series:
    start = pd.to_datetime(start_date, format="%Y%m%d").strftime("%Y-%m-%d")
    end = pd.to_datetime(end_date, format="%Y%m%d").strftime("%Y-%m-%d")
    df = yf.download(proxy_symbol, start=start, end=end, auto_adjust=True)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    return df["Close"].resample("ME").last().dropna()


def fetch_proxy_ext(
    start_date: str,
    end_date: str,
    db_path: str = "data/factors.db",
) -> int:
    """
    Fetch monthly proxy prices for all 7 extended ETF candidates.

    Stored symbol is the proxy index code (not the ETF code), matching
    the convention used in the main backtest script's PROXY_MAP.

    Returns:
        Total rows upserted.
    """
    pro = _get_pro()
    rows: list[tuple] = []

    for _etf, cfg in EXT_PROXY_MAP.items():
        proxy = cfg["proxy"]
        if cfg["source"] == "tushare":
            monthly = _fetch_tushare_monthly(pro, proxy, start_date, end_date)
        else:
            monthly = _fetch_yahoo_monthly(proxy, start_date, end_date)

        for dt, close in monthly.items():
            rows.append((dt.strftime("%Y-%m-%d"), proxy, float(close)))

    if not rows:
        return 0

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO proxy_prices_ext (date, symbol, close) VALUES (?, ?, ?)",
            rows,
        )
    return len(rows)
