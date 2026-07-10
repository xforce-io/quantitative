# Rebalance-Frequency-Parametrized Backtest Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `scripts/long_rotation_discovery.py` + `quant/analysis/rotation/*` from hard-coded monthly into a single frequency-parametrized engine that supports `monthly` / `biweekly` / `weekly` rebalancing, with monthly path bit-equivalent to the current run-007 SOTA.

**Architecture:** Introduce `quant/analysis/rotation/frequency.py` as the single source of truth for frequency-related constants (bars/year, resample rule, calendar-window-to-bar conversion). Keep public config field names in months (`lookback_months`, etc.) for backward compatibility — convert to internal `_bars` units at the engine boundary. Daily prices remain the canonical data layer; resample-to-frequency happens once at load time. Golden test (run-007 monthly reproducibility, < 0.01pp tolerance) is the one-vote veto.

**Tech Stack:** Python 3.11, pandas, pytest, existing `quant.services.data_service` for daily price loads.

**Spec:** `docs/superpowers/specs/2026-05-24-rebalance-frequency-engine-design.md` — read this first if you have not.

---

## File Structure

**Create:**
- `quant/analysis/rotation/frequency.py` — `BacktestFrequency` literal, `bars_per_year()`, `resample_rule()`, `months_to_bars()`
- `tests/unit/test_rotation_frequency.py` — pure-function tests of frequency abstraction
- `tests/unit/test_rotation_engine_monthly_golden.py` — golden test for run-007 monthly reproducibility
- `tests/integration/test_rotation_frequency_smoke.py` — biweekly/weekly smoke tests
- `tests/fixtures/run_007_monthly_baseline.json` — frozen expected metrics for golden test

**Modify:**
- `quant/analysis/rotation/ranker.py` — `MomentumRanker` + `MultiFactorRanker`: accept frequency, convert months → bars at `__init__`, rename `monthly_prices` → `prices` in method signatures
- `quant/analysis/rotation/regime_overlay.py` — `PrecomputedRegimeOverlay` analogous changes
- `quant/analysis/rotation/backtest.py` — `RotationBacktester`: `PERIODS_PER_YEAR` becomes frequency-aware; vol/sharpe annualization use `bars_per_year(freq)`
- `scripts/long_rotation_discovery.py` — `MinHoldWrapper` + `RegimeFilteredRanker` + fetch functions + `build_folds` + CLI; add `--frequency` flag

**Petri workspace (`~/lab/petri/quantitative_trading/`):**
- Create: `candidates/frequency-weekly.json`, `candidates/frequency-biweekly.json`, `candidates/frequency-weekly-skip-tightened.json`
- Create: `.petri/branches/rebalance-frequency-search/branch.yaml`

---

## Pre-Implementation Checklist

- [ ] **Step 0.1: Capture current run-007 baseline numbers as fixture**

Read `experiments/history.json`, locate `run-007`, write the 6 metrics into a JSON fixture:

```bash
mkdir -p /Users/xupeng/lab/quantitative_trading/tests/fixtures
```

```python
# Write tests/fixtures/run_007_monthly_baseline.json
{
  "run_id": "run-007",
  "spec_path": "config/strategies/rotation/run_007_production.json",
  "frequency": "monthly",
  "expected_metrics": {
    "index_proxy":     {"annual_return": 0.1211, "mdd": -0.1989},
    "real_etf_full":   {"annual_return": 0.2364, "mdd": -0.1052},
    "real_etf_subset": {"annual_return": 0.0974, "mdd": -0.1874}
  },
  "tolerance_pp": 0.01
}
```

- [ ] **Step 0.2: Confirm run-007 still reproduces on current `main` before refactoring**

Run:
```bash
cd /Users/xupeng/lab/quantitative_trading && \
.venv/bin/python scripts/long_rotation_discovery.py \
  --mode candidate \
  --params-file config/strategies/rotation/run_007_production.json \
  --output /tmp/run_007_preflight.json
```

Expected: `/tmp/run_007_preflight.json` shows `index_proxy.annual_return≈0.1211`, `real_etf_full.annual_return≈0.2364`, `real_etf_subset.annual_return≈0.0974` (within 0.0001).

If these numbers don't match the fixture, **STOP** — the refactoring cannot proceed until current `main` reproduces the baseline. Investigate before writing any code.

- [ ] **Step 0.3: Commit fixture**

```bash
git add tests/fixtures/run_007_monthly_baseline.json
git commit -m "test: freeze run-007 monthly baseline as golden-test fixture"
```

---

### Task 1: Frequency Abstraction Module

**Files:**
- Create: `quant/analysis/rotation/frequency.py`
- Test: `tests/unit/test_rotation_frequency.py`

- [ ] **Step 1.1: Write the failing test**

```python
# tests/unit/test_rotation_frequency.py
"""Tests for backtest frequency abstraction."""
from __future__ import annotations

import pytest

from quant.analysis.rotation.frequency import (
    BacktestFrequency,
    bars_per_year,
    months_to_bars,
    resample_rule,
    validate_frequency,
)


@pytest.mark.parametrize(
    "freq,expected",
    [("monthly", 12), ("biweekly", 26), ("weekly", 52)],
)
def test_bars_per_year(freq: BacktestFrequency, expected: int) -> None:
    assert bars_per_year(freq) == expected


@pytest.mark.parametrize(
    "freq,expected",
    [("monthly", "ME"), ("biweekly", "2W-FRI"), ("weekly", "W-FRI")],
)
def test_resample_rule(freq: BacktestFrequency, expected: str) -> None:
    assert resample_rule(freq) == expected


@pytest.mark.parametrize(
    "freq,months,expected_bars",
    [
        ("monthly", 6, 6),
        ("monthly", 1, 1),
        ("biweekly", 6, 13),   # round(6 * 26 / 12) = 13
        ("biweekly", 1, 2),    # round(1 * 26 / 12) = 2
        ("weekly", 6, 26),     # round(6 * 52 / 12) = 26
        ("weekly", 1, 4),      # round(1 * 52 / 12) = 4
        ("weekly", 0, 0),
    ],
)
def test_months_to_bars(freq: BacktestFrequency, months: int, expected_bars: int) -> None:
    assert months_to_bars(months, freq) == expected_bars


def test_months_to_bars_rejects_negative() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        months_to_bars(-1, "monthly")


def test_validate_frequency_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown frequency"):
        validate_frequency("daily")
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd /Users/xupeng/lab/quantitative_trading && .venv/bin/pytest tests/unit/test_rotation_frequency.py -v
```

Expected: `ImportError` / `ModuleNotFoundError`.

- [ ] **Step 1.3: Implement frequency module**

```python
# quant/analysis/rotation/frequency.py
"""Single source of truth for backtest rebalance frequency.

Public config fields keep month-based names (lookback_months, skip_months) for
backward compatibility with all existing strategy_spec.json candidates. Internal
engine code uses *_bars units converted via months_to_bars().
"""
from __future__ import annotations

from typing import Literal

BacktestFrequency = Literal["monthly", "biweekly", "weekly"]

_BARS_PER_YEAR: dict[str, int] = {
    "monthly": 12,
    "biweekly": 26,
    "weekly": 52,
}

_RESAMPLE_RULE: dict[str, str] = {
    "monthly": "ME",       # month-end
    "biweekly": "2W-FRI",  # every other Friday (period-end aligned)
    "weekly": "W-FRI",     # every Friday
}


def validate_frequency(freq: str) -> BacktestFrequency:
    if freq not in _BARS_PER_YEAR:
        raise ValueError(
            f"unknown frequency {freq!r}; expected one of {sorted(_BARS_PER_YEAR)}"
        )
    return freq  # type: ignore[return-value]


def bars_per_year(freq: BacktestFrequency) -> int:
    return _BARS_PER_YEAR[validate_frequency(freq)]


def resample_rule(freq: BacktestFrequency) -> str:
    return _RESAMPLE_RULE[validate_frequency(freq)]


def months_to_bars(months: int, freq: BacktestFrequency) -> int:
    """Convert calendar months to bars at the given frequency.

    Semantics: a `lookback_months=6` window means 'approximately 6 calendar
    months of history', not '6 bars'. This keeps factor semantics stable
    across frequencies. Rounded to nearest int.
    """
    if months < 0:
        raise ValueError("months must be non-negative")
    return round(months * bars_per_year(freq) / 12)
```

- [ ] **Step 1.4: Run tests to verify pass**

```bash
.venv/bin/pytest tests/unit/test_rotation_frequency.py -v
```

Expected: all 12 cases PASS.

- [ ] **Step 1.5: Commit**

```bash
git add quant/analysis/rotation/frequency.py tests/unit/test_rotation_frequency.py
git commit -m "feat(rotation): add frequency abstraction for monthly/biweekly/weekly rebalancing"
```

---

### Task 2: MomentumRanker Frequency Parameterization

**Files:**
- Modify: `quant/analysis/rotation/ranker.py:14-100` (`RankerConfig` + `MomentumRanker`)
- Test: `tests/unit/test_rotation_ranker.py` (existing — extend), `tests/unit/test_rotation_ranker_frequency.py` (new)

**Approach:** Public config field names (`lookback_months`, `skip_recent_months`, `vol_lookback_months`) stay; `MomentumRanker.__init__` accepts `frequency: BacktestFrequency = "monthly"` and converts to internal `_bars`. Method signature renames `monthly_prices` → `prices`. Vol annualization uses `sqrt(bars_per_year(freq))` instead of `sqrt(12)`.

- [ ] **Step 2.1: Write the failing test**

```python
# tests/unit/test_rotation_ranker_frequency.py
"""MomentumRanker frequency-parameterization tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.analysis.rotation.ranker import MomentumRanker, RankerConfig


def _weekly_prices(growth: dict[str, float]) -> pd.DataFrame:
    """52 weeks of constant weekly growth."""
    weeks = pd.date_range("2024-01-05", periods=52, freq="W-FRI")
    data = {sym: 100.0 * (1 + g) ** np.arange(52) for sym, g in growth.items()}
    return pd.DataFrame(data, index=weeks)


def test_weekly_lookback_uses_26_bars_for_6_months() -> None:
    """lookback_months=6 at frequency=weekly should look back 26 bars."""
    prices = _weekly_prices({"A": 0.01, "B": -0.01})
    ranker = MomentumRanker(
        RankerConfig(lookback_months=6, skip_recent_months=0, top_k=1, cash_threshold=-1.0),
        frequency="weekly",
    )
    weights = ranker.rank(prices, prices.index[-1])
    # A grows, B shrinks — A should be picked.
    assert set(weights) == {"A"}


def test_weekly_insufficient_history_returns_empty() -> None:
    """At rebalance bar < 26 + skip(4), ranker has no history at weekly."""
    prices = _weekly_prices({"A": 0.01})
    ranker = MomentumRanker(
        RankerConfig(lookback_months=6, skip_recent_months=1, top_k=1, cash_threshold=-1.0),
        frequency="weekly",
    )
    # 26 lookback + 4 skip = 30; index 29 (0-based) is borderline
    assert ranker.rank(prices, prices.index[29]) == {}
    # Index 30+ should produce non-empty
    assert ranker.rank(prices, prices.index[30]) != {}


def test_monthly_default_unchanged() -> None:
    """frequency defaults to monthly; existing monthly behavior unchanged."""
    months = pd.date_range("2022-01-31", periods=24, freq="ME")
    prices = pd.DataFrame(
        {"A": 100.0 * 1.05 ** np.arange(24), "B": 100.0 * 0.99 ** np.arange(24)},
        index=months,
    )
    ranker = MomentumRanker(RankerConfig(top_k=1, cash_threshold=-1.0))  # no frequency arg
    weights = ranker.rank(prices, prices.index[-1])
    assert set(weights) == {"A"}
```

- [ ] **Step 2.2: Run test to verify failure**

```bash
.venv/bin/pytest tests/unit/test_rotation_ranker_frequency.py -v
```

Expected: FAIL on first test — `MomentumRanker.__init__()` does not accept `frequency`.

- [ ] **Step 2.3: Modify `MomentumRanker`**

In `quant/analysis/rotation/ranker.py`:

1. Add at top of file:
   ```python
   from quant.analysis.rotation.frequency import BacktestFrequency, bars_per_year, months_to_bars
   ```

2. Replace `MomentumRanker.__init__` (around line 30-37):
   ```python
   def __init__(
       self,
       config: RankerConfig | None = None,
       frequency: BacktestFrequency = "monthly",
   ) -> None:
       self.config = config or RankerConfig()
       self.frequency = frequency
       if self.config.lookback_months <= 0:
           raise ValueError("lookback_months must be positive")
       if self.config.skip_recent_months < 0:
           raise ValueError("skip_recent_months must be non-negative")
       if self.config.top_k <= 0:
           raise ValueError("top_k must be positive")
       self._lookback_bars = months_to_bars(self.config.lookback_months, frequency)
       self._skip_bars = months_to_bars(self.config.skip_recent_months, frequency)
       self._vol_lookback_bars = (
           months_to_bars(self.config.vol_lookback_months, frequency)
           if self.config.vol_lookback_months > 0 else 0
       )
       self._bars_per_year = bars_per_year(frequency)
   ```

3. Replace `MomentumRanker.rank` signature and body — find every `monthly_prices` → `prices`; replace `skip = self.config.skip_recent_months` and `lookback = self.config.lookback_months` with `skip = self._skip_bars` / `lookback = self._lookback_bars`.

4. In the vol-annualization branches, replace `np.sqrt(12)` with `np.sqrt(self._bars_per_year)`. Replace `vol_lb = self.config.vol_lookback_months if self.config.vol_lookback_months > 0 else lookback` with `vol_lb = self._vol_lookback_bars or lookback`.

5. Rename local variable `monthly_rets` → `period_rets` (semantic; helps reviewers spot frequency drift).

- [ ] **Step 2.4: Run all ranker tests**

```bash
.venv/bin/pytest tests/unit/test_rotation_ranker.py tests/unit/test_rotation_ranker_frequency.py -v
```

Expected: all PASS (existing monthly tests + new frequency tests).

- [ ] **Step 2.5: Commit**

```bash
git add quant/analysis/rotation/ranker.py tests/unit/test_rotation_ranker_frequency.py
git commit -m "feat(rotation): parameterize MomentumRanker by frequency (calendar-window semantics)"
```

---

### Task 3: MultiFactorRanker Frequency Parameterization

**Files:**
- Modify: `quant/analysis/rotation/ranker.py:190-468` (`MultiFactorRanker` + factor helpers)
- Test: `tests/unit/test_rotation_ranker_frequency.py` (extend)

**Approach:** Same pattern as Task 2. `MultiFactorRanker` reads `lookback_months` / `skip_months` per-factor from its `factors` config dict; conversion to bars happens at rank-time using `months_to_bars(factor.get("lookback_months", ...), self.frequency)`. Method signature renames `monthly_prices` → `prices`.

- [ ] **Step 3.1: Extend failing test**

Append to `tests/unit/test_rotation_ranker_frequency.py`:

```python
def test_multifactor_weekly_lookback() -> None:
    """MultiFactorRanker honors frequency for per-factor lookback_months."""
    from quant.analysis.rotation.ranker import MultiFactorRanker

    weeks = pd.date_range("2023-01-06", periods=60, freq="W-FRI")
    prices = pd.DataFrame(
        {
            "A": 100.0 * 1.01 ** np.arange(60),
            "B": 100.0 * 1.005 ** np.arange(60),
            "C": 100.0 * 0.995 ** np.arange(60),
        },
        index=weeks,
    )
    cfg = {
        "rank_normalization": "cross_sectional_percentile",
        "composite_score": "weighted_average_of_ranks",
        "factors": [
            {"name": "momentum", "weight": 1.0, "lookback_months": 6, "skip_months": 1},
        ],
    }
    ranker = MultiFactorRanker(cfg, top_k=1, frequency="weekly")
    weights = ranker.rank(prices, prices.index[-1])
    assert set(weights) == {"A"}
```

- [ ] **Step 3.2: Run test to verify failure**

```bash
.venv/bin/pytest tests/unit/test_rotation_ranker_frequency.py::test_multifactor_weekly_lookback -v
```

Expected: FAIL (MultiFactorRanker does not accept `frequency`).

- [ ] **Step 3.3: Modify `MultiFactorRanker`**

In `ranker.py`:

1. Add `frequency: BacktestFrequency = "monthly"` to `MultiFactorRanker.__init__` parameters; store as `self.frequency`; store `self._bars_per_year = bars_per_year(frequency)`.

2. In `_compute_factor` and the `_momentum` / `_low_volatility` / `_relative_strength` / `_low_crowding` methods: replace every occurrence of:
   - `factor.get("lookback_months", N)` → `months_to_bars(factor.get("lookback_months", N), self.frequency)`
   - `factor.get("skip_months", N)` → `months_to_bars(factor.get("skip_months", N), self.frequency)`
   - `np.sqrt(12)` → `np.sqrt(self._bars_per_year)`
   - `monthly_prices` → `prices` (variable name, method signature)

3. For the `relative_strength` factor that uses a benchmark Series, ensure the benchmark `prices` index aligns to the resampled `prices` index — no logic change, just rename.

4. Update `condition_lookback_months` reads at line ~170 (`int(self._cg.get("condition_lookback_months", 3))`) — convert via `months_to_bars`.

- [ ] **Step 3.4: Run all ranker tests**

```bash
.venv/bin/pytest tests/unit/test_rotation_ranker.py tests/unit/test_rotation_ranker_frequency.py -v
```

Expected: all PASS.

- [ ] **Step 3.5: Commit**

```bash
git add quant/analysis/rotation/ranker.py tests/unit/test_rotation_ranker_frequency.py
git commit -m "feat(rotation): parameterize MultiFactorRanker by frequency"
```

---

### Task 4: RegimeOverlay & MinHoldWrapper & RegimeFilteredRanker

**Files:**
- Modify: `quant/analysis/rotation/regime_overlay.py` (full file, 75 lines)
- Modify: `scripts/long_rotation_discovery.py:174-280` (`MinHoldWrapper` + `RegimeFilteredRanker`)
- Test: `tests/unit/test_rotation_overlay.py` (existing — verify still pass)

- [ ] **Step 4.1: Update `PrecomputedRegimeOverlay`**

In `quant/analysis/rotation/regime_overlay.py`: read the file, identify any month-based locals. The class accepts a precomputed multiplier DataFrame indexed by date, so frequency-awareness needed only if internal lookback windows exist. If none — no changes; just add a docstring note that the `index` of multiplier must already be aligned with the engine's price index.

- [ ] **Step 4.2: Update `MinHoldWrapper`**

In `scripts/long_rotation_discovery.py:174-195`:

1. Change `__init__` to accept `frequency: BacktestFrequency = "monthly"`:
   ```python
   def __init__(
       self,
       inner: MomentumRanker,
       min_hold_months: int = 1,
       frequency: BacktestFrequency = "monthly",
   ) -> None:
       from quant.analysis.rotation.frequency import months_to_bars
       self.inner = inner
       self.min_hold = max(1, months_to_bars(min_hold_months, frequency))
       self._prev_weights: dict[str, float] = {}
       self._held_for: dict[str, int] = {}
   ```

2. In `rank()`: rename `monthly_prices` → `prices`. The `min_hold` counter increments per-rebalance — semantically correct because each rebalance is one bar at the engine's frequency.

- [ ] **Step 4.3: Update `RegimeFilteredRanker`**

In `scripts/long_rotation_discovery.py:208-280`:

1. Add `frequency` param; convert `benchmark_lookback_months` + `industry_momentum_lookback_months` via `months_to_bars` at `__init__`.

2. Method signature `_benchmark_return_ok(rebalance_date, lookback_months)` → `_benchmark_return_ok(rebalance_date, lookback_bars)`. Same for `_positive_ratio_ok`.

3. Method signature renames `monthly_prices` → `prices`. Use `self._benchmark_lookback_bars` etc. internally.

- [ ] **Step 4.4: Run overlay + regime tests**

```bash
.venv/bin/pytest tests/unit/test_rotation_overlay.py -v
```

Expected: all PASS (no behavior change at monthly).

- [ ] **Step 4.5: Commit**

```bash
git add quant/analysis/rotation/regime_overlay.py scripts/long_rotation_discovery.py
git commit -m "feat(rotation): parameterize MinHoldWrapper/RegimeFilteredRanker by frequency"
```

---

### Task 5: RotationBacktester Frequency-Aware Annualization

**Files:**
- Modify: `quant/analysis/rotation/backtest.py` (full file, 165 lines)
- Test: `tests/unit/test_rotation_backtest.py` (existing — extend)

**Approach:** `PERIODS_PER_YEAR = 12` becomes instance-derived. `RotationBacktestConfig` gains `frequency` field. All `_annual_return`, `_annual_vol`, `_sharpe` use `self._bars_per_year` instead of module-level `PERIODS_PER_YEAR`. `monthly_returns` DataFrame keyword renamed to `period_returns` (with backward-compat alias).

- [ ] **Step 5.1: Write extension to existing test**

Append to `tests/unit/test_rotation_backtest.py`:

```python
def test_backtester_weekly_annualization() -> None:
    """Annual return formula uses bars_per_year(freq), not hardcoded 12."""
    import numpy as np
    import pandas as pd
    from quant.analysis.rotation.backtest import RotationBacktester, RotationBacktestConfig

    # Build a 52-week price series with constant 1% weekly return on A only.
    weeks = pd.date_range("2024-01-05", periods=52, freq="W-FRI")
    universe = pd.DataFrame({"A": 100.0 * 1.01 ** np.arange(52)}, index=weeks)
    benchmark = pd.Series(100.0 * 1.005 ** np.arange(52), index=weeks)

    class _Ranker:
        def rank(self, prices, date): return {"A": 1.0}
    class _Overlay:
        def multiplier_at(self, date): return 1.0
    class _Combiner:
        def combine(self, weights, mult): return {k: v * mult for k, v in weights.items()}

    cfg = RotationBacktestConfig(frequency="weekly", transaction_cost=0.0)
    bt = RotationBacktester(cfg)
    result = bt.run(universe, benchmark, _Ranker(), _Overlay(), _Combiner())
    # 1% weekly compounded 52 weeks ≈ (1.01)^52 - 1 ≈ 0.6777
    assert 0.65 < result.metrics["annual_return_strategy"] < 0.71
```

- [ ] **Step 5.2: Run test to verify failure**

```bash
.venv/bin/pytest tests/unit/test_rotation_backtest.py::test_backtester_weekly_annualization -v
```

Expected: FAIL — `RotationBacktestConfig` does not accept `frequency`.

- [ ] **Step 5.3: Modify `RotationBacktester`**

In `quant/analysis/rotation/backtest.py`:

1. Remove module-level `PERIODS_PER_YEAR = 12`.

2. Change `RotationBacktestConfig`:
   ```python
   @dataclass(frozen=True)
   class RotationBacktestConfig:
       transaction_cost: float = 0.002
       risk_free: float = 0.03
       frequency: BacktestFrequency = "monthly"
   ```
   Add `from quant.analysis.rotation.frequency import BacktestFrequency, bars_per_year` at the top.

3. In `__init__`:
   ```python
   self._bars_per_year = bars_per_year(self.config.frequency)
   ```

4. In `_annual_return`, `_annual_vol`, `_sharpe`: replace `PERIODS_PER_YEAR` with `self._bars_per_year`. `_annual_return` and `_annual_vol` are `@staticmethod` — convert to instance methods.

5. Rename `monthly_returns` field in `RotationBacktestResult` → `period_returns`. Add deprecation-safe property:
   ```python
   @property
   def monthly_returns(self) -> pd.DataFrame:
       return self.period_returns
   ```

6. In `run()`: rename `monthly_universe_ret` → `period_universe_ret`; rename `this_month_ret` → `this_bar_ret`. Update the `RotationBacktestResult` constructor call to pass `period_returns=...`.

- [ ] **Step 5.4: Run all backtest tests**

```bash
.venv/bin/pytest tests/unit/test_rotation_backtest.py -v
```

Expected: all PASS.

- [ ] **Step 5.5: Commit**

```bash
git add quant/analysis/rotation/backtest.py tests/unit/test_rotation_backtest.py
git commit -m "feat(rotation): make RotationBacktester annualization frequency-aware"
```

---

### Task 6: Data Loader Refactoring

**Files:**
- Modify: `scripts/long_rotation_discovery.py:844-1000` (`fetch_proxy_monthly_prices`, `fetch_etf_monthly_prices`, `fetch_monthly_volumes`)
- Test: `tests/integration/test_rotation_data_resample.py` (new, opt-in marker so it doesn't run in default CI)

**Approach:** Each fetch function gains a `frequency: BacktestFrequency = "monthly"` kwarg. Daily-load + anomaly filter stays at daily level (do not regress the existing `MAX_SINGLE_DAY_ABS_RET` check). Resample switches from hard-coded `"ME"` to `resample_rule(frequency)`. Rename function to drop `_monthly_`; keep old names as thin wrappers calling new ones with `frequency="monthly"`.

- [ ] **Step 6.1: Write the failing test**

```python
# tests/integration/test_rotation_data_resample.py
"""Integration test for frequency-aware data loaders.

Marked slow because it touches the data service; skip in default test run.
"""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.mark.slow
def test_fetch_proxy_prices_weekly_returns_weekly_bars() -> None:
    from scripts.long_rotation_discovery import fetch_proxy_prices
    from quant.services.data_service import DataService

    ds = DataService()  # uses repo's default config
    df, _ = fetch_proxy_prices(ds, "20240101", "20240630", frequency="weekly")

    # Weekly bars should be roughly 26 (6 months × ~4.3 weeks/mo); allow ±3 for holidays.
    assert 22 <= len(df.index) <= 30
    # Friday alignment.
    weekdays = df.index.weekday.unique().tolist()
    assert weekdays == [4], f"Expected Friday-only index, got {weekdays}"


@pytest.mark.slow
def test_fetch_etf_prices_monthly_unchanged() -> None:
    """Backward-compat: fetch_etf_monthly_prices wrapper still works."""
    from scripts.long_rotation_discovery import fetch_etf_monthly_prices
    from quant.services.data_service import DataService

    ds = DataService()
    df, n = fetch_etf_monthly_prices(ds, "20240101", "20240630", subset=False)
    assert len(df.index) >= 5
    assert df.index.is_monotonic_increasing
```

Add the `slow` marker to `pytest.ini` if it doesn't exist:
```ini
[pytest]
markers =
    slow: data-touching integration test; opt-in via -m slow
```

- [ ] **Step 6.2: Run test to verify failure**

```bash
.venv/bin/pytest tests/integration/test_rotation_data_resample.py -v -m slow
```

Expected: FAIL — `fetch_proxy_prices` does not exist.

- [ ] **Step 6.3: Refactor `fetch_proxy_monthly_prices`**

In `scripts/long_rotation_discovery.py`:

1. Add import at top:
   ```python
   from quant.analysis.rotation.frequency import BacktestFrequency, resample_rule
   ```

2. Rename `fetch_proxy_monthly_prices` → `fetch_proxy_prices`; add `frequency: BacktestFrequency = "monthly"` parameter. Replace `close.resample("ME").last()` with `close.resample(resample_rule(frequency)).last()`. Rename local var `monthly` → `resampled`.

3. Append a thin wrapper for backward compat:
   ```python
   def fetch_proxy_monthly_prices(
       data_service: DataService, full_start: str, full_end: str
   ) -> tuple[pd.DataFrame, list[dict]]:
       """Deprecated: use fetch_proxy_prices(..., frequency='monthly')."""
       return fetch_proxy_prices(data_service, full_start, full_end, frequency="monthly")
   ```

- [ ] **Step 6.4: Refactor `fetch_etf_monthly_prices` and `fetch_monthly_volumes`**

Same pattern. **Critical**: in `fetch_etf_monthly_prices`, the `MAX_SINGLE_DAY_ABS_RET` filter at lines 923-931 operates on `daily_ret = close.pct_change()` (daily). Do NOT move this after resample — it must stay at daily level. Replace only the `monthly = close.resample("ME").last()` line.

For `fetch_monthly_volumes`: same resample swap. Add backward-compat wrappers for both old names.

- [ ] **Step 6.5: Run integration tests**

```bash
.venv/bin/pytest tests/integration/test_rotation_data_resample.py -v -m slow
```

Expected: both PASS.

- [ ] **Step 6.6: Commit**

```bash
git add scripts/long_rotation_discovery.py tests/integration/test_rotation_data_resample.py pytest.ini
git commit -m "feat(rotation): frequency-parameterize data loaders (daily→resample)"
```

---

### Task 7: Fold Loop, CLI, and Candidate-JSON Wiring

**Files:**
- Modify: `scripts/long_rotation_discovery.py` (fold-building section ~line 692, main function, CLI argparse)

**Approach:**
1. `build_folds` converts month-based constants via `months_to_bars(freq)`
2. `argparse` gains `--frequency` (default `monthly`)
3. Candidate JSON's `risk_on_allocation.rebalance_frequency` field is read at strategy-spec parse time; if present and not `monthly`, it overrides `--frequency`. CLI flag is fallback default only.
4. Plumb `frequency` through all ranker/overlay/backtester construction sites in main.

- [ ] **Step 7.1: Refactor `build_folds`**

In `scripts/long_rotation_discovery.py`:

1. Rename module constants:
   ```python
   TRAIN_CAL_MONTHS = 24
   TEST_CAL_MONTHS = 6
   STEP_CAL_MONTHS = 6
   WARMUP_CAL_MONTHS = 15
   ```
   (Old names removed; calendar-months semantics is now explicit.)

2. `build_folds` signature: `build_folds(full_start: str, full_end: str, frequency: BacktestFrequency = "monthly") -> list[dict]`. Inside, derive bars:
   ```python
   from quant.analysis.rotation.frequency import months_to_bars
   train_bars = months_to_bars(TRAIN_CAL_MONTHS, frequency)
   test_bars = months_to_bars(TEST_CAL_MONTHS, frequency)
   step_bars = months_to_bars(STEP_CAL_MONTHS, frequency)
   warmup_bars = months_to_bars(WARMUP_CAL_MONTHS, frequency)
   ```
   Replace any `iloc` slicing that used month counts with the new bar counts.

- [ ] **Step 7.2: Add CLI flag and JSON precedence**

In `scripts/long_rotation_discovery.py` `main()`:

```python
parser.add_argument(
    "--frequency",
    choices=["monthly", "biweekly", "weekly"],
    default="monthly",
    help="Rebalance frequency. Overridden by candidate JSON's risk_on_allocation.rebalance_frequency if present.",
)
```

In the spec-loading block (where the candidate `--params-file` is parsed), after loading `spec`:

```python
spec_freq = spec.get("risk_on_allocation", {}).get("rebalance_frequency")
if spec_freq and spec_freq != "monthly":
    frequency = spec_freq  # JSON wins over CLI default
elif spec_freq == "monthly":
    frequency = "monthly"
else:
    frequency = args.frequency  # CLI fallback
from quant.analysis.rotation.frequency import validate_frequency
frequency = validate_frequency(frequency)
print(f"  [INFO] Using rebalance frequency: {frequency}")
```

- [ ] **Step 7.3: Plumb `frequency` through construction sites**

Grep the file for `MomentumRanker(`, `MultiFactorRanker(`, `RegimeFilteredRanker(`, `MinHoldWrapper(`, `RotationBacktester(`, `RotationBacktestConfig(` — pass `frequency=frequency` to each. Similarly for `fetch_proxy_prices`, `fetch_etf_prices`, `fetch_volumes`.

- [ ] **Step 7.4: Run unit tests as smoke check**

```bash
.venv/bin/pytest tests/unit/ -v
```

Expected: all PASS — no behavior change at `frequency=monthly` (default).

- [ ] **Step 7.5: Commit**

```bash
git add scripts/long_rotation_discovery.py
git commit -m "feat(rotation): plumb frequency through CLI, candidate JSON, and fold builder"
```

---

### Task 8: Golden Test — run-007 Monthly Reproducibility (One-Vote Veto)

**Files:**
- Create: `tests/unit/test_rotation_engine_monthly_golden.py`

**Approach:** Run the actual `long_rotation_discovery.py --mode candidate --params-file run_007_production.json --frequency monthly`, parse result, compare to the frozen fixture. Tolerance is **0.0001** absolute (0.01pp). If ANY of the 6 metrics breaks tolerance, the refactor fails.

This test is **the one-vote veto** specified in the spec. Subagent-driven workflow MUST stop and surface the failure if this test fails.

- [ ] **Step 8.1: Write the golden test**

```python
# tests/unit/test_rotation_engine_monthly_golden.py
"""Golden test: run-007 production spec at frequency=monthly must reproduce
the published SOTA metrics within 0.01pp.

This is the one-vote-veto for the frequency-parameterized engine refactor.
If this test fails, the refactor has changed monthly-path behavior and is
considered broken.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = _ROOT / "tests" / "fixtures" / "run_007_monthly_baseline.json"
_SPEC = _ROOT / "config" / "strategies" / "rotation" / "run_007_production.json"


@pytest.mark.slow
def test_run_007_monthly_reproduces_baseline(tmp_path: Path) -> None:
    output_path = tmp_path / "run_007_golden.json"

    cmd = [
        ".venv/bin/python",
        "scripts/long_rotation_discovery.py",
        "--mode", "candidate",
        "--params-file", str(_SPEC),
        "--frequency", "monthly",
        "--output", str(output_path),
    ]
    result = subprocess.run(cmd, cwd=str(_ROOT), capture_output=True, text=True)
    assert result.returncode == 0, (
        f"Backtest failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    with output_path.open() as f:
        actual = json.load(f)
    with _FIXTURE.open() as f:
        baseline = json.load(f)

    tolerance = baseline["tolerance_pp"] / 100.0
    failures: list[str] = []
    for universe, metrics in baseline["expected_metrics"].items():
        actual_ar = actual[universe]["annual_return"]
        actual_mdd = actual[universe]["max_drawdown"]
        expected_ar = metrics["annual_return"]
        expected_mdd = metrics["mdd"]
        if abs(actual_ar - expected_ar) > tolerance:
            failures.append(
                f"{universe}.annual_return: expected {expected_ar}, got {actual_ar} "
                f"(diff {actual_ar - expected_ar:+.4f}, tolerance {tolerance})"
            )
        if abs(actual_mdd - expected_mdd) > tolerance:
            failures.append(
                f"{universe}.max_drawdown: expected {expected_mdd}, got {actual_mdd} "
                f"(diff {actual_mdd - expected_mdd:+.4f}, tolerance {tolerance})"
            )

    assert not failures, "Golden test failed:\n" + "\n".join(failures)
```

- [ ] **Step 8.2: Run the golden test**

```bash
.venv/bin/pytest tests/unit/test_rotation_engine_monthly_golden.py -v -m slow -s
```

Expected: PASS. If FAIL — **stop**. Investigate which metric drifted and why (likely candidates: vol annualization sqrt swap, off-by-one in bar conversion, fold-bar rounding). Do not proceed to Task 9 until this passes.

- [ ] **Step 8.3: Commit**

```bash
git add tests/unit/test_rotation_engine_monthly_golden.py
git commit -m "test(rotation): add golden test for run-007 monthly reproducibility"
```

---

### Task 9: Multi-Frequency Smoke Test

**Files:**
- Create: `tests/integration/test_rotation_frequency_smoke.py`

**Approach:** Run run-007 spec at `biweekly` and `weekly`. Assert no exception, all three universes produce finite metrics, basic sanity bounds (annual return within ±50pp of monthly, MDD > -50%).

These tests intentionally do NOT compare against a fixture — we don't know what the "right" weekly numbers are yet. They only assert the engine runs end-to-end.

- [ ] **Step 9.1: Write the smoke test**

```python
# tests/integration/test_rotation_frequency_smoke.py
"""Smoke tests: engine runs at biweekly and weekly without exceptions."""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SPEC = _ROOT / "config" / "strategies" / "rotation" / "run_007_production.json"


@pytest.mark.slow
@pytest.mark.parametrize("frequency", ["biweekly", "weekly"])
def test_engine_runs_at_higher_frequency(frequency: str, tmp_path: Path) -> None:
    output_path = tmp_path / f"smoke_{frequency}.json"
    cmd = [
        ".venv/bin/python",
        "scripts/long_rotation_discovery.py",
        "--mode", "candidate",
        "--params-file", str(_SPEC),
        "--frequency", frequency,
        "--output", str(output_path),
    ]
    result = subprocess.run(cmd, cwd=str(_ROOT), capture_output=True, text=True)
    assert result.returncode == 0, (
        f"{frequency} run failed:\n{result.stderr}"
    )

    with output_path.open() as f:
        data = json.load(f)

    for universe in ("index_proxy", "real_etf_full", "real_etf_subset"):
        ar = data[universe]["annual_return"]
        mdd = data[universe]["max_drawdown"]
        assert math.isfinite(ar), f"{frequency}/{universe}: annual_return not finite"
        assert math.isfinite(mdd), f"{frequency}/{universe}: mdd not finite"
        # Sanity bands.
        assert -0.50 < ar < 1.00, f"{frequency}/{universe}: ar={ar} outside sanity band"
        assert -0.60 < mdd <= 0.0, f"{frequency}/{universe}: mdd={mdd} outside sanity band"
```

- [ ] **Step 9.2: Run smoke tests**

```bash
.venv/bin/pytest tests/integration/test_rotation_frequency_smoke.py -v -m slow -s
```

Expected: 2 cases PASS (biweekly + weekly). If FAIL, capture the result JSON and diagnose — common failures: insufficient history in early folds at weekly frequency (warmup_bars too small), or symbol drop-outs.

- [ ] **Step 9.3: Commit**

```bash
git add tests/integration/test_rotation_frequency_smoke.py
git commit -m "test(rotation): add biweekly/weekly smoke tests"
```

---

### Task 10: Petri Workspace — Candidates + Branch

**Files (in `~/lab/petri/quantitative_trading/`):**
- Create: `candidates/frequency-weekly.json`
- Create: `candidates/frequency-biweekly.json`
- Create: `candidates/frequency-weekly-skip-tightened.json`
- Create: `.petri/branches/rebalance-frequency-search/branch.yaml`

**Approach:** Clone `run_007_production.json` three times, vary only `rebalance_frequency` (and `skip_months` for one variant). Branch metadata declares objective + baseline + gate criteria identical to factor-weight-search (real_etf_full ≥ +1.0pp, MDD ≥ -12.52%, subset ≥ 9.74%).

- [ ] **Step 10.1: Create `frequency-weekly.json`**

```bash
cp /Users/xupeng/lab/quantitative_trading/config/strategies/rotation/run_007_production.json \
   ~/lab/petri/quantitative_trading/candidates/frequency-weekly.json
```

Then edit the file: change `strategy_id` → `"rebalance_freq_search_weekly"`, add a `source.branch_id: "rebalance-frequency-search"` block (mirror `top-k-2.json` structure), and set `risk_on_allocation.rebalance_frequency: "weekly"`. Add a `hypothesis` field:

```json
"hypothesis": "Higher rebalance frequency captures industry rotation shifts faster. Weekly = 4× the decision points vs monthly; if industry momentum reversals cluster within calendar months, weekly should improve real_etf_full annual return. Risk: factor signal-to-noise at weekly is unproven."
```

- [ ] **Step 10.2: Create `frequency-biweekly.json`**

Same as above with `rebalance_frequency: "biweekly"`, `strategy_id: "rebalance_freq_search_biweekly"`, and hypothesis:

```json
"hypothesis": "Biweekly trades off monthly's lag against weekly's noise. If industry rotation events have a ~10-15 trading-day cadence, biweekly should capture them while keeping turnover bounded."
```

- [ ] **Step 10.3: Create `frequency-weekly-skip-tightened.json`**

Same as `frequency-weekly.json` but additionally set `risk_on_allocation.multi_factor_config.factors[0].skip_months: 0` (momentum factor; remove the 1-month skip). Hypothesis:

```json
"hypothesis": "The 1-month reversal-avoidance skip was tuned for monthly bars (1 bar = full month). At weekly frequency, skip_months=1 still translates to 4 weeks, but the original noise structure that motivated it may not exist at weekly granularity. Test removing it."
```

- [ ] **Step 10.4: Create branch metadata**

```bash
mkdir -p ~/lab/petri/quantitative_trading/.petri/branches/rebalance-frequency-search
```

Write `~/lab/petri/quantitative_trading/.petri/branches/rebalance-frequency-search/branch.yaml`:

```yaml
schema_version: 1
branch_id: rebalance-frequency-search
status: active
objective: >-
  Test whether higher rebalance frequencies (biweekly, weekly) improve
  real_etf_full annual return vs run_007's monthly baseline, now that the
  backtest engine supports parameterized frequencies.
baseline: run_007_production
created_at: 2026-05-24T00:00:00.000Z
seeded_from:
  type: external_strategy
  project: quantitative_trading
  strategy_id: run_007_production
  strategy_path: /Users/xupeng/lab/quantitative_trading/config/strategies/rotation/run_007_production.json
  reason: >-
    Parameter axes (factor weights, top_k) exhausted by factor-weight-search and
    risk-on-structure-search. Rebalance frequency is the next-most-actionable
    axis; the 2026-05-24 engine refactor made it a live parameter.
  seeded_at: 2026-05-24T00:00:00.000Z
notes:
  - "Open with three candidates: frequency-weekly, frequency-biweekly, frequency-weekly-skip-tightened."
  - "Gate criteria match factor-weight-search: real_etf_full annual return improvement >= 1.0pp without breaching MDD floor -0.1252 or subset annual return floor 0.0974."
  - "Negative result is valuable: if all three REJECT, the rebalance-frequency axis is also exhausted, freeing iteration capacity for structural changes (new factors / new universe / new regime model)."
```

- [ ] **Step 10.5: Update petri pipeline.yaml to support new candidates**

Read `~/lab/petri/quantitative_trading/pipeline.yaml`. The `--params-file` is currently hardcoded to `top-k-2.json`. To run a candidate, the user passes the candidate name; document this expected usage in the branch notes (do not change pipeline.yaml hardcoding for now — the petri CLI workflow specifies the candidate at run-time via the branch+params combination, mirroring the factor-weight-search workflow).

- [ ] **Step 10.6: Commit petri changes**

```bash
cd ~/lab/petri/quantitative_trading
git add candidates/frequency-weekly.json candidates/frequency-biweekly.json \
        candidates/frequency-weekly-skip-tightened.json \
        .petri/branches/rebalance-frequency-search/branch.yaml
git commit -m "feat(petri): open rebalance-frequency-search branch with 3 candidates"
```

---

### Task 11: Final Verification & History Update

- [ ] **Step 11.1: Re-run golden + smoke + all unit tests**

```bash
cd /Users/xupeng/lab/quantitative_trading && \
.venv/bin/pytest tests/unit -v && \
.venv/bin/pytest tests/integration/test_rotation_frequency_smoke.py \
                 tests/unit/test_rotation_engine_monthly_golden.py \
                 tests/integration/test_rotation_data_resample.py \
                 -v -m slow
```

Expected: 100% PASS across the board.

- [ ] **Step 11.2: Manual sanity run**

```bash
.venv/bin/python scripts/long_rotation_discovery.py \
  --mode candidate \
  --params-file config/strategies/rotation/run_007_production.json \
  --frequency monthly \
  --output /tmp/run_007_post_refactor.json
```

Open `/tmp/run_007_post_refactor.json` and confirm visually:
- `index_proxy.annual_return ≈ 0.1211`
- `real_etf_full.annual_return ≈ 0.2364`
- `real_etf_subset.annual_return ≈ 0.0974`

- [ ] **Step 11.3: Update `experiments/history.json` with engine-refactor note**

Add a top-level metadata block (sibling to `_cleanliness_boundary` and `_determinism_fix`):

```json
"_engine_refactor": {
  "refactored_at": "2026-05-24",
  "refactor_commit": "<fill in after merge>",
  "reason": "Backtest engine generalized from hardcoded monthly to frequency-parametrized (monthly/biweekly/weekly). run-007 monthly golden test (< 0.01pp diff) passes.",
  "new_branches_opened": ["rebalance-frequency-search"]
}
```

- [ ] **Step 11.4: Final commit**

```bash
git add experiments/history.json
git commit -m "docs(experiments): record engine refactor for rebalance-frequency parameterization"
```

---

## Done-Definition Checklist

The plan is complete when ALL of the following are true:

- [ ] `pytest tests/unit/` is green
- [ ] `pytest -m slow` is green (data-touching + golden + smoke)
- [ ] `tests/unit/test_rotation_engine_monthly_golden.py` PASSES (one-vote veto)
- [ ] Manual `--frequency biweekly` and `--frequency weekly` runs produce finite, sane metrics for all 3 universes
- [ ] Petri branch `rebalance-frequency-search` has 3 candidate JSONs and a `branch.yaml`
- [ ] `experiments/history.json` documents the refactor
- [ ] No occurrences of `monthly_prices` or `monthly_rets` left in `quant/analysis/rotation/*` (grep should return empty)

---

## Failure Modes & Diagnostic Hints

If the golden test fails, here is where to look first:

| Symptom                                                | Likely cause                                                                 |
|--------------------------------------------------------|------------------------------------------------------------------------------|
| All 3 universes drift by same percentage               | Vol annualization formula — `np.sqrt(12)` not all replaced with `sqrt(bpy)` |
| real_etf_full only drifts                              | Anomaly filter moved past resample (must stay daily-level)                  |
| Drift only at fold boundaries                          | `build_folds` train/test bar rounding off-by-one                            |
| MDD identical but annual returns drift                 | `_annual_return` uses wrong `bars_per_year`                                 |
| Subset drifts much more than full                      | `SUBSET_CUTOFF_TS` comparison happens after resample (must use daily index) |

If the smoke test fails on weekly with "insufficient history":
- Bump `WARMUP_CAL_MONTHS` if early folds lack `lookback_months + skip_months` of pre-train history
- Check `MultiFactorRanker` returns empty dict for an early rebalance — should not crash, just produce empty weights → 100% cash for that bar
