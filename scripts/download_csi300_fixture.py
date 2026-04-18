#!/usr/bin/env python3
"""One-time script to download CSI 300 daily data as test fixture."""
import os
from pathlib import Path

import pandas as pd
import tushare as ts

token = os.environ["TUSHARE_TOKEN"]
ts.set_token(token)
pro = ts.pro_api()

df = pro.index_daily(ts_code="000300.SH", start_date="20210101", end_date="20260401")
if df is None or df.empty:
    raise RuntimeError("No data returned from tushare")

df = df.sort_values("trade_date").reset_index(drop=True)
df["trade_date"] = pd.to_datetime(df["trade_date"])
df = df[["trade_date", "close"]].rename(columns={"trade_date": "date"})

out = Path("tests/fixtures/csi300_daily.csv")
out.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(out, index=False)
print(f"Saved {len(df)} rows to {out}")
print(f"Date range: {df['date'].min().date()} – {df['date'].max().date()}")
