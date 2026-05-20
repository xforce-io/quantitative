# Factor Data Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 multi_sleeve_rotation 策略新增四类因子数据基础设施（ETF份额、行业PE/PB分位、PMI时序、扩展ETF池代理指数），存入 `data/factors.db`（SQLite），通过统一的 `FactorStore` 接口供回测脚本调用。

**Architecture:** 四个独立 Fetcher 各自从 Tushare/Yahoo 拉取数据并写入 SQLite，`FactorStore` 封装查询，`scripts/refresh_factors.py` 是统一刷新入口。所有新因子在 `strategy_spec.json` 中默认 `enabled: false`，现有回测脚本不改动。

**Tech Stack:** Python 3.9+, SQLite（标准库 `sqlite3`）, Tushare Pro, `yfinance`, `pandas`, `pytest`

---

### Task 1: DB Schema 初始化

**Files:**
- Create: `quant/data/db.py`
- Create: `tests/unit/test_db.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_db.py
import sqlite3, tempfile, os, pytest
from quant.data.db import init_db

def test_init_db_creates_four_tables():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    try:
        init_db(db_path)
        with sqlite3.connect(db_path) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        assert tables == {'etf_shares', 'industry_valuation', 'macro_pmi', 'proxy_prices_ext'}
    finally:
        os.unlink(db_path)

def test_init_db_idempotent():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    try:
        init_db(db_path)
        init_db(db_path)  # second call must not raise
        with sqlite3.connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM etf_shares").fetchone()[0]
        assert count == 0
    finally:
        os.unlink(db_path)
```

- [ ] **Step 2: 确认测试失败**

```bash
cd ~/lab/quantitative_trading
python -m pytest tests/unit/test_db.py -v
```

Expected: `ImportError: cannot import name 'init_db'`

- [ ] **Step 3: 实现 `quant/data/db.py`**

```python
"""SQLite schema initialisation for factor data."""
from __future__ import annotations
import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS etf_shares (
    date    TEXT NOT NULL,
    symbol  TEXT NOT NULL,
    shares  REAL NOT NULL,
    PRIMARY KEY (date, symbol)
);

CREATE TABLE IF NOT EXISTS industry_valuation (
    date    TEXT NOT NULL,
    symbol  TEXT NOT NULL,
    pe_ttm  REAL,
    pb_mrq  REAL,
    pe_pct  REAL,
    pb_pct  REAL,
    PRIMARY KEY (date, symbol)
);

CREATE TABLE IF NOT EXISTS macro_pmi (
    date        TEXT PRIMARY KEY,
    mfg_pmi     REAL,
    non_mfg_pmi REAL
);

CREATE TABLE IF NOT EXISTS proxy_prices_ext (
    date    TEXT NOT NULL,
    symbol  TEXT NOT NULL,
    close   REAL NOT NULL,
    PRIMARY KEY (date, symbol)
);
"""

def init_db(db_path: str = "data/factors.db") -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(DDL)
```

- [ ] **Step 4: 确认测试通过**

```bash
python -m pytest tests/unit/test_db.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add quant/data/db.py tests/unit/test_db.py
git commit -m "feat(factors): add SQLite schema init"
```

---

### Task 2: ETF 份额 Fetcher

**Files:**
- Create: `quant/data/fetchers/__init__.py`
- Create: `quant/data/fetchers/etf_shares.py`
- Create: `tests/unit/test_fetcher_etf_shares.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_fetcher_etf_shares.py
import sqlite3, tempfile, os
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from quant.data.db import init_db
from quant.data.fetchers.etf_shares import fetch_etf_shares

def _make_db():
    f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    init_db(f.name)
    return f.name

def _fake_fund_share(ts_code, start_date, end_date):
    """Mock Tushare fund_share response."""
    dates = pd.date_range('2026-01-02', '2026-04-30', freq='B')
    return pd.DataFrame({
        'ts_code': ts_code,
        'trade_date': dates.strftime('%Y%m%d'),
        'fd_share': [100000.0 + i for i in range(len(dates))],
        'fund_type': None,
        'market': 'SH',
    })

def test_fetch_etf_shares_inserts_monthly_rows():
    db = _make_db()
    try:
        mock_pro = MagicMock()
        mock_pro.fund_share.side_effect = _fake_fund_share
        with patch('quant.data.fetchers.etf_shares._get_pro', return_value=mock_pro):
            n = fetch_etf_shares(['512480.SH'], '20260101', '20260430', db_path=db)
        assert n == 4  # Jan, Feb, Mar, Apr month-end rows
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT date, symbol, shares FROM etf_shares ORDER BY date"
            ).fetchall()
        assert len(rows) == 4
        assert rows[0][1] == '512480.SH'
        assert rows[0][2] > 0
    finally:
        os.unlink(db)

def test_fetch_etf_shares_upsert_on_duplicate():
    db = _make_db()
    try:
        mock_pro = MagicMock()
        mock_pro.fund_share.side_effect = _fake_fund_share
        with patch('quant.data.fetchers.etf_shares._get_pro', return_value=mock_pro):
            fetch_etf_shares(['512480.SH'], '20260101', '20260131', db_path=db)
            fetch_etf_shares(['512480.SH'], '20260101', '20260131', db_path=db)
        with sqlite3.connect(db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM etf_shares").fetchone()[0]
        assert count == 1  # upsert, not duplicate
    finally:
        os.unlink(db)
```

- [ ] **Step 2: 确认测试失败**

```bash
python -m pytest tests/unit/test_fetcher_etf_shares.py -v
```

Expected: `ImportError: cannot import name 'fetch_etf_shares'`

- [ ] **Step 3: 创建 `quant/data/fetchers/__init__.py`**

```python
# quant/data/fetchers/__init__.py
```

- [ ] **Step 4: 实现 `quant/data/fetchers/etf_shares.py`**

```python
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
```

- [ ] **Step 5: 确认测试通过**

```bash
python -m pytest tests/unit/test_fetcher_etf_shares.py -v
```

Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add quant/data/fetchers/__init__.py quant/data/fetchers/etf_shares.py tests/unit/test_fetcher_etf_shares.py
git commit -m "feat(factors): add ETF shares fetcher"
```

---

### Task 3: 行业估值 Fetcher

**Files:**
- Create: `quant/data/fetchers/valuation.py`
- Create: `tests/unit/test_fetcher_valuation.py`

背景：`index_dailybasic` 按 `trade_date` 查所有指数，需要先用 `trade_cal` 获取每月最后一个交易日，再逐月查询并过滤目标指数。PE历史分位用过去60个月（5年）滚动计算。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_fetcher_valuation.py
import sqlite3, tempfile, os
import pandas as pd
from unittest.mock import patch, MagicMock
from quant.data.db import init_db
from quant.data.fetchers.valuation import fetch_valuation

SYMBOLS = ['000933.SH', '399986.SZ']

def _make_db():
    f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    init_db(f.name)
    return f.name

def _fake_trade_cal(**kwargs):
    return pd.DataFrame({'cal_date': ['20260130', '20260227', '20260331', '20260430']})

def _fake_dailybasic(trade_date, fields):
    return pd.DataFrame({
        'ts_code':    ['000933.SH', '399986.SZ', '000300.SH'],
        'trade_date': [trade_date] * 3,
        'pe_ttm':     [25.0, 10.0, 15.0],
        'pb':         [3.0,  1.2,  1.8],
    })

def test_fetch_valuation_inserts_rows():
    db = _make_db()
    try:
        mock_pro = MagicMock()
        mock_pro.trade_cal.side_effect = _fake_trade_cal
        mock_pro.index_dailybasic.side_effect = _fake_dailybasic
        with patch('quant.data.fetchers.valuation._get_pro', return_value=mock_pro):
            n = fetch_valuation(SYMBOLS, '20260101', '20260430', db_path=db)
        # 4 months × 2 symbols = 8 rows
        assert n == 8
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT date, symbol, pe_ttm, pe_pct FROM industry_valuation ORDER BY date, symbol"
            ).fetchall()
        assert len(rows) == 8
        # pe_pct must be between 0 and 1
        for _, _, _, pe_pct in rows:
            assert 0.0 <= pe_pct <= 1.0
    finally:
        os.unlink(db)
```

- [ ] **Step 2: 确认测试失败**

```bash
python -m pytest tests/unit/test_fetcher_valuation.py -v
```

Expected: `ImportError: cannot import name 'fetch_valuation'`

- [ ] **Step 3: 实现 `quant/data/fetchers/valuation.py`**

```python
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
```

- [ ] **Step 4: 确认测试通过**

```bash
python -m pytest tests/unit/test_fetcher_valuation.py -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add quant/data/fetchers/valuation.py tests/unit/test_fetcher_valuation.py
git commit -m "feat(factors): add industry valuation fetcher with rolling PE/PB percentile"
```

---

### Task 4: PMI Fetcher

**Files:**
- Create: `quant/data/fetchers/macro_pmi.py`
- Create: `tests/unit/test_fetcher_macro_pmi.py`

背景：`cn_pmi` 返回 `MONTH`（YYYYMM）、`PMI010000`（制造业）、`PMI030000`（非制造业）。月末日期取该月最后一个交易日。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_fetcher_macro_pmi.py
import sqlite3, tempfile, os
import pandas as pd
from unittest.mock import patch, MagicMock
from quant.data.db import init_db
from quant.data.fetchers.macro_pmi import fetch_pmi

def _make_db():
    f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    init_db(f.name)
    return f.name

def _fake_cn_pmi(start_m, end_m):
    return pd.DataFrame({
        'MONTH':      ['202604', '202603', '202602', '202601'],
        'PMI010000':  [49.0, 50.5, 50.2, 49.1],
        'PMI030000':  [50.2, 51.4, 51.1, 50.1],
    })

def _fake_trade_cal(**kwargs):
    return pd.DataFrame({'cal_date': ['20260130', '20260227', '20260331', '20260430']})

def test_fetch_pmi_inserts_rows():
    db = _make_db()
    try:
        mock_pro = MagicMock()
        mock_pro.cn_pmi.side_effect = _fake_cn_pmi
        mock_pro.trade_cal.side_effect = _fake_trade_cal
        with patch('quant.data.fetchers.macro_pmi._get_pro', return_value=mock_pro):
            n = fetch_pmi('202601', '202604', db_path=db)
        assert n == 4
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT date, mfg_pmi, non_mfg_pmi FROM macro_pmi ORDER BY date"
            ).fetchall()
        assert len(rows) == 4
        assert rows[0][1] == 49.1   # Jan mfg PMI
        assert rows[3][1] == 49.0   # Apr mfg PMI
    finally:
        os.unlink(db)
```

- [ ] **Step 2: 确认测试失败**

```bash
python -m pytest tests/unit/test_fetcher_macro_pmi.py -v
```

Expected: `ImportError: cannot import name 'fetch_pmi'`

- [ ] **Step 3: 实现 `quant/data/fetchers/macro_pmi.py`**

```python
"""Fetch monthly PMI data from Tushare into factors.db."""
from __future__ import annotations
import os
import sqlite3
import pandas as pd
import tushare as ts


def _get_pro():
    return ts.pro_api(os.getenv("TUSHARE_TOKEN"))


def _month_end_trading_date(pro, yyyymm: str) -> str:
    """Return last trading day of the given month as YYYY-MM-DD."""
    start = yyyymm + "01"
    year, month = int(yyyymm[:4]), int(yyyymm[4:])
    if month == 12:
        end = f"{year+1}0101"
    else:
        end = f"{year}{month+1:02d}01"
    df = pro.trade_cal(exchange="SSE", start_date=start, end_date=end, is_open="1", fields="cal_date")
    dates = pd.to_datetime(df["cal_date"], format="%Y%m%d")
    last = dates[dates.dt.strftime("%Y%m") == yyyymm].max()
    return last.strftime("%Y-%m-%d")


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

    rows: list[tuple] = []
    for _, row in df.iterrows():
        yyyymm = str(row["MONTH"])
        date_str = _month_end_trading_date(pro, yyyymm)
        mfg = float(row["PMI010000"]) if pd.notna(row["PMI010000"]) else None
        non_mfg = float(row["PMI030000"]) if pd.notna(row["PMI030000"]) else None
        rows.append((date_str, mfg, non_mfg))

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO macro_pmi (date, mfg_pmi, non_mfg_pmi) VALUES (?, ?, ?)",
            rows,
        )
    return len(rows)
```

- [ ] **Step 4: 确认测试通过**

```bash
python -m pytest tests/unit/test_fetcher_macro_pmi.py -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add quant/data/fetchers/macro_pmi.py tests/unit/test_fetcher_macro_pmi.py
git commit -m "feat(factors): add PMI fetcher"
```

---

### Task 5: 扩展 ETF 池代理指数 Fetcher

**Files:**
- Create: `quant/data/fetchers/proxy_ext.py`
- Create: `tests/unit/test_fetcher_proxy_ext.py`

扩展池7只ETF及代理映射（`proxy_data_from` 为实际可用起始日期，需在首次拉取后更新）：

```python
EXT_PROXY_MAP = {
    "516220.SH": {"proxy": "399101.SZ", "source": "tushare"},  # 物联网→中小板通信
    "561910.SH": {"proxy": "399006.SZ", "source": "tushare"},  # 储能→创业板代理
    "159201.SZ": {"proxy": "000922.SH", "source": "tushare"},  # 自由现金流→红利低波
    "159732.SZ": {"proxy": "399995.SZ", "source": "tushare"},  # 消费电子→中证TMT
    "159992.SZ": {"proxy": "000951.SH", "source": "tushare"},  # 创新药→中证医药
    "512050.SH": {"proxy": "000510.SH", "source": "tushare"},  # A500→中证A500
    "513180.SH": {"proxy": "^HSTECH",   "source": "yahoo"},    # 恒生科技→Yahoo
}
```

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_fetcher_proxy_ext.py
import sqlite3, tempfile, os
import pandas as pd
from unittest.mock import patch, MagicMock
from quant.data.db import init_db
from quant.data.fetchers.proxy_ext import fetch_proxy_ext, EXT_PROXY_MAP

def _make_db():
    f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    init_db(f.name)
    return f.name

def _fake_index_daily(ts_code, start_date, end_date, fields):
    dates = pd.date_range('2026-01-02', '2026-04-30', freq='B')
    return pd.DataFrame({
        'trade_date': dates.strftime('%Y%m%d'),
        'close': [4500.0 + i for i in range(len(dates))],
    })

def _fake_yfinance_download(tickers, start, end, auto_adjust):
    dates = pd.date_range('2026-01-02', '2026-04-30', freq='B')
    closes = pd.Series([200.0 + i for i in range(len(dates))], index=dates)
    return pd.DataFrame({'Close': closes})

def test_fetch_proxy_ext_inserts_tushare_rows():
    db = _make_db()
    try:
        mock_pro = MagicMock()
        mock_pro.index_daily.side_effect = _fake_index_daily
        with patch('quant.data.fetchers.proxy_ext._get_pro', return_value=mock_pro), \
             patch('quant.data.fetchers.proxy_ext.yf.download', side_effect=_fake_yfinance_download):
            n = fetch_proxy_ext('20260101', '20260430', db_path=db)
        assert n > 0
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM proxy_prices_ext"
            ).fetchall()
        symbols = {r[0] for r in rows}
        # All 7 proxy symbols should be present
        assert len(symbols) == 7
    finally:
        os.unlink(db)

def test_ext_proxy_map_has_seven_entries():
    assert len(EXT_PROXY_MAP) == 7
```

- [ ] **Step 2: 确认测试失败**

```bash
python -m pytest tests/unit/test_fetcher_proxy_ext.py -v
```

Expected: `ImportError: cannot import name 'fetch_proxy_ext'`

- [ ] **Step 3: 安装 yfinance（如未安装）**

```bash
pip install yfinance
```

- [ ] **Step 4: 实现 `quant/data/fetchers/proxy_ext.py`**

```python
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
```

- [ ] **Step 5: 确认测试通过**

```bash
python -m pytest tests/unit/test_fetcher_proxy_ext.py -v
```

Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add quant/data/fetchers/proxy_ext.py tests/unit/test_fetcher_proxy_ext.py
git commit -m "feat(factors): add extended ETF pool proxy fetcher"
```

---

### Task 6: FactorStore 查询接口

**Files:**
- Create: `quant/data/factor_store.py`
- Create: `tests/unit/test_factor_store.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_factor_store.py
import sqlite3, tempfile, os
import pandas as pd
from quant.data.db import init_db
from quant.data.factor_store import FactorStore

def _make_store():
    f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    init_db(f.name)
    # Seed data
    with sqlite3.connect(f.name) as conn:
        conn.execute("INSERT INTO etf_shares VALUES ('2026-04-30','512480.SH',100000.0)")
        conn.execute("INSERT INTO etf_shares VALUES ('2026-03-31','512480.SH',90000.0)")
        conn.execute("INSERT INTO industry_valuation VALUES ('2026-04-30','000933.SH',25.0,3.0,0.75,0.60)")
        conn.execute("INSERT INTO macro_pmi VALUES ('2026-04-30',49.0,50.2)")
        conn.execute("INSERT INTO proxy_prices_ext VALUES ('2026-04-30','399101.SZ',1200.0)")
        conn.execute("INSERT INTO proxy_prices_ext VALUES ('2026-03-31','399101.SZ',1150.0)")
    return FactorStore(f.name), f.name

def test_get_etf_shares():
    store, db = _make_store()
    try:
        result = store.get_etf_shares(['512480.SH'], '2026-04-30')
        assert result == {'512480.SH': 100000.0}
    finally:
        os.unlink(db)

def test_get_etf_shares_missing_returns_empty():
    store, db = _make_store()
    try:
        result = store.get_etf_shares(['999999.SH'], '2026-04-30')
        assert result == {}
    finally:
        os.unlink(db)

def test_get_valuation_pct():
    store, db = _make_store()
    try:
        result = store.get_valuation_pct(['000933.SH'], '2026-04-30')
        assert result['000933.SH']['pe_pct'] == 0.75
        assert result['000933.SH']['pb_pct'] == 0.60
    finally:
        os.unlink(db)

def test_get_pmi():
    store, db = _make_store()
    try:
        assert store.get_pmi('2026-04-30') == 49.0
        assert store.get_pmi('2020-01-31') is None
    finally:
        os.unlink(db)

def test_get_proxy_prices_ext():
    store, db = _make_store()
    try:
        df = store.get_proxy_prices_ext(['399101.SZ'], '2026-01-01', '2026-04-30')
        assert '399101.SZ' in df.columns
        assert len(df) == 2
        assert df['399101.SZ'].iloc[-1] == 1200.0
    finally:
        os.unlink(db)
```

- [ ] **Step 2: 确认测试失败**

```bash
python -m pytest tests/unit/test_factor_store.py -v
```

Expected: `ImportError: cannot import name 'FactorStore'`

- [ ] **Step 3: 实现 `quant/data/factor_store.py`**

```python
"""Unified read interface for factor data in factors.db."""
from __future__ import annotations
import sqlite3
import pandas as pd


class FactorStore:
    def __init__(self, db_path: str = "data/factors.db") -> None:
        self._db = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db)

    def get_etf_shares(self, symbols: list[str], date: str) -> dict[str, float]:
        """Return {symbol: shares(万份)} for the given month-end date."""
        if not symbols:
            return {}
        placeholders = ",".join("?" * len(symbols))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT symbol, shares FROM etf_shares WHERE date=? AND symbol IN ({placeholders})",
                [date] + symbols,
            ).fetchall()
        return {sym: shares for sym, shares in rows}

    def get_valuation_pct(self, symbols: list[str], date: str) -> dict[str, dict]:
        """Return {symbol: {pe_pct, pb_pct}} for the given month-end date."""
        if not symbols:
            return {}
        placeholders = ",".join("?" * len(symbols))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT symbol, pe_pct, pb_pct FROM industry_valuation "
                f"WHERE date=? AND symbol IN ({placeholders})",
                [date] + symbols,
            ).fetchall()
        return {sym: {"pe_pct": pe_pct, "pb_pct": pb_pct} for sym, pe_pct, pb_pct in rows}

    def get_pmi(self, date: str) -> float | None:
        """Return manufacturing PMI for the given month-end date, or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT mfg_pmi FROM macro_pmi WHERE date=?", [date]
            ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def get_proxy_prices_ext(
        self, symbols: list[str], start: str, end: str
    ) -> pd.DataFrame:
        """
        Return monthly close prices for extended proxy symbols.
        Index: DatetimeIndex (month-end), columns: symbol codes.
        """
        if not symbols:
            return pd.DataFrame()
        placeholders = ",".join("?" * len(symbols))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT date, symbol, close FROM proxy_prices_ext "
                f"WHERE date>=? AND date<=? AND symbol IN ({placeholders})",
                [start, end] + symbols,
            ).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["date", "symbol", "close"])
        df["date"] = pd.to_datetime(df["date"])
        return df.pivot(index="date", columns="symbol", values="close").sort_index()
```

- [ ] **Step 4: 确认测试通过**

```bash
python -m pytest tests/unit/test_factor_store.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add quant/data/factor_store.py tests/unit/test_factor_store.py
git commit -m "feat(factors): add FactorStore query interface"
```

---

### Task 7: 统一刷新脚本

**Files:**
- Create: `scripts/refresh_factors.py`

- [ ] **Step 1: 实现 `scripts/refresh_factors.py`**

```python
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
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from quant.data.db import init_db
from quant.data.fetchers.etf_shares import fetch_etf_shares
from quant.data.fetchers.valuation import fetch_valuation
from quant.data.fetchers.macro_pmi import fetch_pmi
from quant.data.fetchers.proxy_ext import fetch_proxy_ext, EXT_PROXY_MAP

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
        start_yyyymm = f"{today.year - (0 if today.month > 6 else 1)}{(today.month - 6) % 12 + 1 if today.month <= 6 else today.month - 6:02d}"
        start_date = start_yyyymm + "01"
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
```

- [ ] **Step 2: 运行全量初始化（首次）**

```bash
cd ~/lab/quantitative_trading
python scripts/refresh_factors.py
```

Expected output（示例）：
```
Refreshing factors: 20100101 → 20260517

  ✓ ETF shares:   1320 rows upserted
  ✓ Valuation:    2520 rows upserted
  ✓ PMI:           196 rows upserted
  ✓ Proxy ext:     980 rows upserted

DB status:
  etf_shares                rows=  1320  latest=2026-04-30
  industry_valuation        rows=  2520  latest=2026-04-30
  macro_pmi                 rows=   196  latest=2026-04-30
  proxy_prices_ext          rows=   980  latest=2026-04-30
```

如有某个 Fetcher 报错，单独排查，不影响其他表。

- [ ] **Step 3: 确认全部测试仍然通过**

```bash
python -m pytest tests/unit/test_db.py tests/unit/test_fetcher_etf_shares.py tests/unit/test_fetcher_valuation.py tests/unit/test_fetcher_macro_pmi.py tests/unit/test_fetcher_proxy_ext.py tests/unit/test_factor_store.py -v
```

Expected: `All passed`

- [ ] **Step 4: Commit**

```bash
git add scripts/refresh_factors.py
git commit -m "feat(factors): add unified refresh script"
```

---

### Task 8: 集成验证

- [ ] **Step 1: 确认 FactorStore 能查到真实数据**

```python
# 在项目根目录运行
cd ~/lab/quantitative_trading
python3 -c "
import sys; sys.path.insert(0, '.')
from quant.data.factor_store import FactorStore
fs = FactorStore()

print('ETF shares (半导体, Apr-26):', fs.get_etf_shares(['512480.SH'], '2026-04-30'))
print('Valuation (医疗, Apr-26):',    fs.get_valuation_pct(['000933.SH'], '2026-04-30'))
print('PMI (Apr-26):',               fs.get_pmi('2026-04-30'))
df = fs.get_proxy_prices_ext(['399101.SZ'], '2026-01-01', '2026-04-30')
print('Proxy ext rows:', len(df))
"
```

Expected: 四个查询都返回有效数据（非空 dict / 非 None / 非空 DataFrame）。

- [ ] **Step 2: 确认现有回测脚本不受影响**

```bash
cd ~/lab/quantitative_trading
python scripts/long_rotation_discovery.py \
    --mode baseline \
    --output /tmp/smoke_test.json
echo "exit code: $?"
```

Expected: `exit code: 0`，输出与之前完全一致。

- [ ] **Step 3: 最终 Commit**

```bash
git add -A
git commit -m "feat(factors): complete data infrastructure — ETF shares, valuation, PMI, extended pool"
```
