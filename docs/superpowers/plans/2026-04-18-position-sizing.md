# A-Share Position Sizing Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a weekly-updated position sizing tool for A-shares that outputs a position percentage (0–100%) based on CSI 300 realized volatility, with a backtest comparing strategy vs buy-and-hold.

**Architecture:** Three focused modules — `VolatilityCalculator` fetches CSI 300 data via tushare and computes 20-day annualized vol; `PositionSizer` applies `min(1, target_vol / realized_vol)` to produce a position percentage; `PositionSizingBacktest` simulates weekly rebalancing vs buy-and-hold and reports Sharpe, max drawdown, and vol. Tests use a committed CSV fixture of real CSI 300 data (no network required).

**Tech Stack:** Python 3.12, tushare>=1.2.89, numpy, pandas, existing `quant.core.logging_config`

**Spec:** `docs/superpowers/specs/2026-04-18-position-sizing-design.md`

---

## File Map

| File | Change |
|------|--------|
| `scripts/download_csi300_fixture.py` | Create: one-time script to download fixture |
| `tests/fixtures/csi300_daily.csv` | Create: real CSI 300 daily close 2021–2026 |
| `quant/analysis/position_sizing/__init__.py` | Create: package exports |
| `quant/analysis/position_sizing/volatility.py` | Create: `VolatilityCalculator` |
| `quant/analysis/position_sizing/sizer.py` | Create: `PositionSizer`, `PositionSizing` |
| `quant/analysis/position_sizing/backtest.py` | Create: `PositionSizingBacktest`, `BacktestResult` |
| `tests/unit/test_position_sizing.py` | Create: tests using fixture data |

---

### Task 1: Download CSI 300 fixture

**Files:**
- Create: `scripts/download_csi300_fixture.py`
- Create: `tests/fixtures/csi300_daily.csv`

- [ ] **Step 1: Create download script**

Create `scripts/download_csi300_fixture.py`:

```python
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
```

- [ ] **Step 2: Run the download script**

```bash
cd $PROJECT_ROOT && python scripts/download_csi300_fixture.py
```

Expected output:
```
Saved ~1200 rows to tests/fixtures/csi300_daily.csv
Date range: 2021-01-04 – 2026-04-01
```

- [ ] **Step 3: Verify fixture**

```bash
head -5 tests/fixtures/csi300_daily.csv
wc -l tests/fixtures/csi300_daily.csv
```

Expected: header + ~1200 data rows, date format `YYYY-MM-DD`, close prices in 3000–6000 range.

- [ ] **Step 4: Commit**

```bash
git add scripts/download_csi300_fixture.py tests/fixtures/csi300_daily.csv
git commit -m "feat: add CSI 300 daily fixture and download script"
```

---

### Task 2: VolatilityCalculator with tests

**Files:**
- Create: `quant/analysis/position_sizing/volatility.py`
- Create: `tests/unit/test_position_sizing.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_position_sizing.py`:

```python
#!/usr/bin/env python3
"""Tests for position sizing using real CSI 300 fixture data."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant.analysis.position_sizing.volatility import VolatilityCalculator

FIXTURE = Path("tests/fixtures/csi300_daily.csv")


def load_prices() -> pd.Series:
    df = pd.read_csv(FIXTURE, parse_dates=["date"])
    return df.set_index("date")["close"]


def prices_for(start: str, end: str) -> pd.Series:
    return load_prices().loc[start:end]


class TestVolatilityCalculator:
    def test_vol_high_during_2022_bear(self):
        # 2022 A-share bear market — vol should be elevated
        calc = VolatilityCalculator(window=20)
        prices = prices_for("2021-01-01", "2022-10-31")
        vol = calc.realized_vol(prices)
        assert vol >= 0.25, f"2022 bear vol should be ≥25%, got {vol:.1%}"

    def test_vol_low_during_2024_q1(self):
        # 2024 Q1 was relatively calm before September rally
        calc = VolatilityCalculator(window=20)
        prices = prices_for("2023-07-01", "2024-03-31")
        vol = calc.realized_vol(prices)
        assert vol <= 0.22, f"2024 Q1 vol should be ≤22%, got {vol:.1%}"

    def test_annualization_formula(self):
        # Verify σ_daily × √252 formula using controlled daily returns
        rng = np.random.RandomState(42)
        daily_rets = rng.normal(0, 0.01, 25)
        prices = pd.Series(
            (1 + daily_rets).cumprod() * 100,
            index=pd.date_range("2024-01-01", periods=25, freq="B"),
        )
        calc = VolatilityCalculator(window=20)
        vol = calc.realized_vol(prices)
        expected = float(pd.Series(daily_rets[-20:]).std() * math.sqrt(252))
        assert abs(vol - expected) < 1e-10

    def test_rolling_vol_nan_prefix(self):
        # First `window` values are NaN, rest are valid
        calc = VolatilityCalculator(window=20)
        prices = prices_for("2022-01-01", "2023-12-31")
        rv = calc.rolling_vol(prices)
        assert len(rv) == len(prices)
        assert rv.iloc[:20].isna().all()
        assert rv.iloc[20:].notna().all()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd $PROJECT_ROOT && python -m pytest tests/unit/test_position_sizing.py -v 2>&1 | tail -10
```

Expected: `ImportError: cannot import name 'VolatilityCalculator'`

- [ ] **Step 3: Create package directory and implement VolatilityCalculator**

```bash
mkdir -p quant/analysis/position_sizing
touch quant/analysis/position_sizing/__init__.py
```

Create `quant/analysis/position_sizing/volatility.py`:

```python
#!/usr/bin/env python3
"""VolatilityCalculator — compute rolling annualized vol from CSI 300 prices."""
from __future__ import annotations

import math
import os

import pandas as pd
import tushare as ts

from quant.core.logging_config import get_logger

logger = get_logger(__name__)

TRADING_DAYS = 252
INDEX_CODE = "000300.SH"


class VolatilityCalculator:
    """Computes rolling annualized volatility from CSI 300 daily prices."""

    def __init__(self, window: int = 20) -> None:
        self._window = window

    def fetch(self, start_date: str, end_date: str) -> pd.Series:
        """
        Fetch CSI 300 daily close from tushare.

        Parameters
        ----------
        start_date, end_date : str  YYYYMMDD format, e.g. "20210101"

        Returns
        -------
        pd.Series with DatetimeIndex, values = daily close prices, sorted ascending.
        """
        token = os.environ.get("TUSHARE_TOKEN")
        if not token:
            raise ValueError("TUSHARE_TOKEN environment variable not set")
        ts.set_token(token)
        pro = ts.pro_api()

        df = pro.index_daily(ts_code=INDEX_CODE, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            raise ValueError(f"No data returned for {INDEX_CODE} [{start_date}, {end_date}]")

        df = df.sort_values("trade_date").reset_index(drop=True)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        logger.info(f"Fetched {len(df)} days of {INDEX_CODE} data")
        return df.set_index("trade_date")["close"]

    def realized_vol(self, prices: pd.Series) -> float:
        """Annualized vol from the most recent `window` daily returns: std × √252."""
        returns = prices.pct_change().dropna()
        if len(returns) < self._window:
            raise ValueError(
                f"Need at least {self._window} returns (got {len(returns)}). "
                f"Provide at least {self._window + 1} price points."
            )
        recent = returns.iloc[-self._window :]
        return float(recent.std() * math.sqrt(TRADING_DAYS))

    def rolling_vol(self, prices: pd.Series) -> pd.Series:
        """Rolling annualized vol series aligned to price index (for backtest)."""
        returns = prices.pct_change()
        return returns.rolling(self._window).std() * math.sqrt(TRADING_DAYS)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd $PROJECT_ROOT && python -m pytest tests/unit/test_position_sizing.py::TestVolatilityCalculator -v 2>&1 | tail -10
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/position_sizing/ tests/unit/test_position_sizing.py
git commit -m "feat: implement VolatilityCalculator with real-data tests"
```

---

### Task 3: PositionSizer with tests

**Files:**
- Create: `quant/analysis/position_sizing/sizer.py`
- Modify: `tests/unit/test_position_sizing.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/unit/test_position_sizing.py`:

```python
from quant.analysis.position_sizing.sizer import PositionSizer, PositionSizing


class TestPositionSizer:
    def test_position_capped_at_100_pct(self):
        sizer = PositionSizer(target_vol=0.20)
        prices = prices_for("2023-07-01", "2024-03-31")
        result = sizer.size(prices)
        assert result.position_pct <= 1.0

    def test_position_never_negative(self):
        sizer = PositionSizer(target_vol=0.20)
        prices = load_prices()
        result = sizer.size(prices)
        assert result.position_pct >= 0.0

    def test_position_below_70_pct_in_2022_bear(self):
        sizer = PositionSizer(target_vol=0.20)
        prices = prices_for("2021-01-01", "2022-10-31")
        result = sizer.size(prices)
        assert result.position_pct < 0.70, (
            f"High-vol period position={result.position_pct:.0%}, expected <70%"
        )

    def test_returns_position_sizing_dataclass(self):
        sizer = PositionSizer(target_vol=0.20)
        result = sizer.size(load_prices())
        assert isinstance(result, PositionSizing)
        assert 0.0 <= result.position_pct <= 1.0
        assert result.target_vol == 0.20
        assert result.realized_vol > 0
        assert result.updated_date != ""

    def test_higher_target_vol_gives_larger_position(self):
        prices = load_prices()
        r_aggressive = PositionSizer(target_vol=0.30).size(prices)
        r_conservative = PositionSizer(target_vol=0.10).size(prices)
        assert r_aggressive.position_pct >= r_conservative.position_pct
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd $PROJECT_ROOT && python -m pytest tests/unit/test_position_sizing.py::TestPositionSizer -v 2>&1 | tail -10
```

Expected: `ImportError: cannot import name 'PositionSizer'`

- [ ] **Step 3: Implement PositionSizer**

Create `quant/analysis/position_sizing/sizer.py`:

```python
#!/usr/bin/env python3
"""PositionSizer — volatility-targeting position size calculator."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant.analysis.position_sizing.volatility import VolatilityCalculator


@dataclass
class PositionSizing:
    """Result of a position size calculation."""

    position_pct: float    # 0.0 – 1.0 (e.g. 0.73 = 73%)
    realized_vol: float    # annualized, e.g. 0.274
    target_vol: float      # e.g. 0.20
    updated_date: str      # ISO date string of last price

    def __str__(self) -> str:
        return (
            f"当前建议仓位: {self.position_pct:.0%}\n"
            f"当前20日年化波动率: {self.realized_vol:.1%}  (目标: {self.target_vol:.0%})\n"
            f"上次更新: {self.updated_date}"
        )


class PositionSizer:
    """Computes position size via: position = min(1, target_vol / realized_vol)."""

    def __init__(self, target_vol: float = 0.20) -> None:
        self._target_vol = target_vol
        self._calc = VolatilityCalculator()

    def size(self, prices: pd.Series) -> PositionSizing:
        """Compute current recommended position from a price series."""
        vol = self._calc.realized_vol(prices)
        position = min(1.0, self._target_vol / vol) if vol > 0 else 1.0
        last_date = prices.index[-1]
        updated = last_date.date().isoformat() if hasattr(last_date, "date") else str(last_date)
        return PositionSizing(
            position_pct=round(position, 4),
            realized_vol=round(vol, 4),
            target_vol=self._target_vol,
            updated_date=updated,
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd $PROJECT_ROOT && python -m pytest tests/unit/test_position_sizing.py::TestPositionSizer -v 2>&1 | tail -10
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/position_sizing/sizer.py tests/unit/test_position_sizing.py
git commit -m "feat: implement PositionSizer with volatility targeting"
```

---

### Task 4: PositionSizingBacktest with tests

**Files:**
- Create: `quant/analysis/position_sizing/backtest.py`
- Modify: `tests/unit/test_position_sizing.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/unit/test_position_sizing.py`:

```python
from quant.analysis.position_sizing.backtest import BacktestResult, PositionSizingBacktest


class TestPositionSizingBacktest:
    def test_backtest_output_fields(self):
        bt = PositionSizingBacktest(target_vol=0.20)
        result = bt.run(load_prices())
        for field in [
            "annual_return_strategy", "annual_return_benchmark",
            "annual_vol_strategy", "annual_vol_benchmark",
            "max_drawdown_strategy", "max_drawdown_benchmark",
            "sharpe_strategy", "sharpe_benchmark",
        ]:
            assert hasattr(result, field), f"Missing field: {field}"

    def test_strategy_vol_near_target(self):
        bt = PositionSizingBacktest(target_vol=0.20)
        result = bt.run(load_prices())
        # Realized strategy vol should be within 8pp of 20% target
        assert abs(result.annual_vol_strategy - 0.20) < 0.08, (
            f"Strategy vol {result.annual_vol_strategy:.1%} too far from 20% target"
        )

    def test_drawdown_improved_vs_benchmark(self):
        # Strategy max drawdown (negative number) should be less severe (closer to 0)
        bt = PositionSizingBacktest(target_vol=0.20)
        result = bt.run(load_prices())
        assert result.max_drawdown_strategy > result.max_drawdown_benchmark, (
            f"Strategy drawdown {result.max_drawdown_strategy:.1%} should be better than "
            f"benchmark {result.max_drawdown_benchmark:.1%}"
        )

    def test_max_drawdown_is_negative(self):
        bt = PositionSizingBacktest(target_vol=0.20)
        result = bt.run(load_prices())
        assert result.max_drawdown_strategy <= 0
        assert result.max_drawdown_benchmark <= 0

    def test_str_output_contains_key_fields(self):
        bt = PositionSizingBacktest(target_vol=0.20)
        result = bt.run(load_prices())
        s = str(result)
        assert "年化收益" in s
        assert "最大回撤" in s
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd $PROJECT_ROOT && python -m pytest tests/unit/test_position_sizing.py::TestPositionSizingBacktest -v 2>&1 | tail -10
```

Expected: `ImportError: cannot import name 'PositionSizingBacktest'`

- [ ] **Step 3: Implement PositionSizingBacktest**

Create `quant/analysis/position_sizing/backtest.py`:

```python
#!/usr/bin/env python3
"""PositionSizingBacktest — weekly rebalancing simulation vs buy-and-hold."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant.analysis.position_sizing.volatility import VolatilityCalculator

WEEKS_PER_YEAR = 52


@dataclass
class BacktestResult:
    """Summary statistics comparing strategy vs buy-and-hold."""

    annual_return_strategy: float
    annual_return_benchmark: float
    annual_vol_strategy: float
    annual_vol_benchmark: float
    max_drawdown_strategy: float    # negative, e.g. -0.21
    max_drawdown_benchmark: float   # negative, e.g. -0.33
    sharpe_strategy: float
    sharpe_benchmark: float

    def __str__(self) -> str:
        return (
            f"{'':22} {'满仓':>10} {'动态仓位':>10}\n"
            f"{'年化收益':22} {self.annual_return_benchmark:>+10.1%}"
            f" {self.annual_return_strategy:>+10.1%}\n"
            f"{'年化波动率':22} {self.annual_vol_benchmark:>10.1%}"
            f" {self.annual_vol_strategy:>10.1%}\n"
            f"{'最大回撤':22} {self.max_drawdown_benchmark:>10.1%}"
            f" {self.max_drawdown_strategy:>10.1%}\n"
            f"{'夏普比率':22} {self.sharpe_benchmark:>10.2f}"
            f" {self.sharpe_strategy:>10.2f}"
        )


class PositionSizingBacktest:
    """
    Weekly-rebalanced volatility targeting backtest.

    Every Friday: recompute position from trailing 20-day vol.
    Strategy weekly return = position × index weekly return.
    Benchmark: 100% invested throughout.
    """

    def __init__(self, target_vol: float = 0.20, risk_free: float = 0.03) -> None:
        self._target_vol = target_vol
        self._risk_free = risk_free
        self._calc = VolatilityCalculator()

    def run(self, prices: pd.Series) -> BacktestResult:
        """Run the backtest on a daily price series."""
        weekly = prices.resample("W-FRI").last().dropna()
        daily_vol = self._calc.rolling_vol(prices)

        strategy_rets, benchmark_rets = [], []

        for i in range(1, len(weekly)):
            prev_date = weekly.index[i - 1]
            vol_series = daily_vol.loc[:prev_date].dropna()
            if len(vol_series) < 1:
                continue
            vol = float(vol_series.iloc[-1])
            position = min(1.0, self._target_vol / vol) if vol > 0 else 1.0

            weekly_ret = float(weekly.iloc[i] / weekly.iloc[i - 1] - 1)
            strategy_rets.append(position * weekly_ret)
            benchmark_rets.append(weekly_ret)

        s = np.array(strategy_rets)
        b = np.array(benchmark_rets)
        n = len(s)

        ann_ret_s = float((1 + s).prod() ** (WEEKS_PER_YEAR / n) - 1)
        ann_ret_b = float((1 + b).prod() ** (WEEKS_PER_YEAR / n) - 1)
        ann_vol_s = float(s.std() * math.sqrt(WEEKS_PER_YEAR))
        ann_vol_b = float(b.std() * math.sqrt(WEEKS_PER_YEAR))

        rf_weekly = (1 + self._risk_free) ** (1 / WEEKS_PER_YEAR) - 1
        sharpe_s = float((s - rf_weekly).mean() / s.std() * math.sqrt(WEEKS_PER_YEAR)) if s.std() > 0 else 0.0
        sharpe_b = float((b - rf_weekly).mean() / b.std() * math.sqrt(WEEKS_PER_YEAR)) if b.std() > 0 else 0.0

        return BacktestResult(
            annual_return_strategy=round(ann_ret_s, 4),
            annual_return_benchmark=round(ann_ret_b, 4),
            annual_vol_strategy=round(ann_vol_s, 4),
            annual_vol_benchmark=round(ann_vol_b, 4),
            max_drawdown_strategy=round(self._max_drawdown(s), 4),
            max_drawdown_benchmark=round(self._max_drawdown(b), 4),
            sharpe_strategy=round(sharpe_s, 3),
            sharpe_benchmark=round(sharpe_b, 3),
        )

    @staticmethod
    def _max_drawdown(returns: np.ndarray) -> float:
        cumulative = np.cumprod(1 + returns)
        rolling_max = np.maximum.accumulate(cumulative)
        return float((cumulative / rolling_max - 1).min())
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd $PROJECT_ROOT && python -m pytest tests/unit/test_position_sizing.py::TestPositionSizingBacktest -v 2>&1 | tail -10
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/position_sizing/backtest.py tests/unit/test_position_sizing.py
git commit -m "feat: implement PositionSizingBacktest with weekly rebalancing"
```

---

### Task 5: Package exports and end-to-end smoke test

**Files:**
- Modify: `quant/analysis/position_sizing/__init__.py`

- [ ] **Step 1: Write __init__.py**

```python
"""Position sizing module — volatility-targeting position size for A-shares."""

from .backtest import BacktestResult, PositionSizingBacktest
from .sizer import PositionSizer, PositionSizing
from .volatility import VolatilityCalculator

__all__ = [
    "VolatilityCalculator",
    "PositionSizer",
    "PositionSizing",
    "PositionSizingBacktest",
    "BacktestResult",
]
```

- [ ] **Step 2: Run full test suite**

```bash
cd $PROJECT_ROOT && python -m pytest tests/unit/test_position_sizing.py -v 2>&1 | tail -20
```

Expected: all 14 tests pass

- [ ] **Step 3: Run end-to-end smoke test**

```bash
cd $PROJECT_ROOT && python -c "
import pandas as pd
from quant.analysis.position_sizing import PositionSizer, PositionSizingBacktest

df = pd.read_csv('tests/fixtures/csi300_daily.csv', parse_dates=['date'])
prices = df.set_index('date')['close']

# Current position
sizer = PositionSizer(target_vol=0.20)
result = sizer.size(prices)
print(result)
print()

# Backtest
bt = PositionSizingBacktest(target_vol=0.20)
backtest = bt.run(prices)
print(backtest)
"
```

Expected: prints current position % and backtest table with both columns.

- [ ] **Step 4: Commit**

```bash
git add quant/analysis/position_sizing/__init__.py
git commit -m "feat: export position sizing package and verify end-to-end"
```
