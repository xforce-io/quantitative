# Allocation Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI-based discipline tool that monitors portfolio weight drift, QDII premium, suggests new-money allocation, and generates quarterly review reports — all based on the "方案 2" target allocation from `docs/superpowers/specs/2026-04-19-portfolio-reallocation-design.md`.

**Architecture:** New subpackage `quant/portfolio/allocation_monitor/` with 5 focused modules (config / weight_monitor / premium / allocator / review). Each module has a single responsibility; data flows from YAML loaders → monitoring → decision output. Reuses existing `Rebalancer` and `PortfolioAnalyzer`. CLI commands wired into existing `quant/cli/portfolio.py`.

**Tech Stack:** Python 3.10+, PyYAML, pandas, existing `TushareDataProvider` (for fund_daily + fund_nav), pytest.

---

## File Structure

### New files
- `quant/portfolio/allocation_monitor/__init__.py` — package exports
- `quant/portfolio/allocation_monitor/config.py` — YAML schemas + loaders (`AllocationTarget`, `Holdings` dataclasses)
- `quant/portfolio/allocation_monitor/weight_monitor.py` — drift computation (`WeightMonitor`, `DriftRow`, `DriftReport`)
- `quant/portfolio/allocation_monitor/premium.py` — QDII premium radar (`PremiumRadar`, `PremiumRow`)
- `quant/portfolio/allocation_monitor/allocator.py` — new-money allocator (`Allocator`, `AllocationPlan`, `AllocatorOrder`)
- `quant/portfolio/allocation_monitor/review.py` — quarterly report generator (`QuarterlyReview`, `QuarterlyReport`)
- `config/allocation_target.yaml` — target weights per spec §3.1
- `config/allocation_holdings.example.yaml` — example holdings file

### Tests (flat, following repo convention)
- `tests/unit/test_allocation_config.py`
- `tests/unit/test_allocation_weight_monitor.py`
- `tests/unit/test_allocation_premium.py`
- `tests/unit/test_allocation_allocator.py`
- `tests/unit/test_allocation_review.py`

### Modified files
- `quant/cli/portfolio.py` — add `status`, `premium`, `allocate`, `review` subcommands
- `quant/portfolio/__init__.py` — re-export allocation_monitor package

---

## Type Reference (used across tasks)

To avoid inconsistency, all types defined up front:

```python
# config.py
@dataclass
class TargetCategory:
    name: str                          # e.g. "纳指100"
    weight: float                      # 0.25
    instruments: list[str]             # ["513100", "159941"]
    prefer_premium_below: float = 0.03

@dataclass
class AllocationTarget:
    version: str
    categories: list[TargetCategory]
    rebalance_threshold: float         # 0.05
    premium_normal: float              # 0.03
    premium_reduced: float             # 0.05
    premium_switch: float              # 0.10

@dataclass
class Holding:
    code: str
    shares: float = 0.0
    amount_cny: float = 0.0            # used for CASH
    cost_basis: float | None = None
    currency: str = "CNY"

@dataclass
class Holdings:
    as_of: date
    total_value_cny: float | None       # optional; auto-computed if None
    holdings: list[Holding]

# weight_monitor.py
@dataclass
class DriftRow:
    category: str
    target_weight: float
    actual_weight: float
    drift: float                        # actual - target (signed)
    status: str                         # "normal" | "watch" | "trigger"

@dataclass
class DriftReport:
    as_of: date
    total_value_cny: float
    rows: list[DriftRow]
    triggered: list[str]                # category names

# premium.py
@dataclass
class PremiumRow:
    code: str
    name: str
    price: float
    nav: float
    premium: float                      # (price - nav) / nav
    status: str                         # "ok" | "reduce" | "switch" | "skip"

# allocator.py
@dataclass
class AllocatorOrder:
    instrument: str
    amount_cny: float
    reason: str

@dataclass
class AllocationPlan:
    total_amount: float
    orders: list[AllocatorOrder]
    warnings: list[str]

# review.py
@dataclass
class QuarterlyReport:
    quarter: str                        # e.g. "2026Q1"
    start_value: float
    end_value: float
    period_return: float
    drift_start: DriftReport
    drift_end: DriftReport
    category_contributions: dict[str, float]
    rebalance_needed: bool
    markdown: str                       # final report text
```

---

## Task 1: Config Loader + Target YAML

**Files:**
- Create: `quant/portfolio/allocation_monitor/__init__.py`
- Create: `quant/portfolio/allocation_monitor/config.py`
- Create: `config/allocation_target.yaml`
- Create: `config/allocation_holdings.example.yaml`
- Test: `tests/unit/test_allocation_config.py`

- [ ] **Step 1.1: Write the failing test for target loader**

```python
# tests/unit/test_allocation_config.py
from pathlib import Path
import pytest
from quant.portfolio.allocation_monitor.config import load_target, AllocationTarget

FIXTURE = Path(__file__).parent / "fixtures" / "allocation_target_ok.yaml"

def test_load_target_returns_dataclass(tmp_path):
    yaml_text = """
version: "2026-04-19"
total_must_equal: 1.0
categories:
  纳指100:
    weight: 0.25
    instruments: [513100, 159941]
    prefer_premium_below: 0.03
  现金:
    weight: 0.75
    instruments: [CASH]
rebalance:
  threshold: 0.05
  premium_rules:
    normal: 0.03
    reduced: 0.05
    switch: 0.10
"""
    p = tmp_path / "t.yaml"
    p.write_text(yaml_text)
    target = load_target(p)
    assert isinstance(target, AllocationTarget)
    assert target.version == "2026-04-19"
    assert len(target.categories) == 2
    assert target.categories[0].name == "纳指100"
    assert target.categories[0].weight == 0.25
    assert target.rebalance_threshold == 0.05
    assert target.premium_switch == 0.10


def test_load_target_rejects_non_100_percent(tmp_path):
    yaml_text = """
version: "v1"
total_must_equal: 1.0
categories:
  A: {weight: 0.4, instruments: [A1]}
  B: {weight: 0.3, instruments: [B1]}
rebalance:
  threshold: 0.05
  premium_rules: {normal: 0.03, reduced: 0.05, switch: 0.10}
"""
    p = tmp_path / "t.yaml"
    p.write_text(yaml_text)
    with pytest.raises(ValueError, match="sum.*0.7"):
        load_target(p)
```

- [ ] **Step 1.2: Run test to confirm it fails**

Run: `pytest tests/unit/test_allocation_config.py -v`
Expected: FAIL with ImportError on `load_target`.

- [ ] **Step 1.3: Implement config.py with dataclasses and loader**

```python
# quant/portfolio/allocation_monitor/config.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml


@dataclass
class TargetCategory:
    name: str
    weight: float
    instruments: list[str]
    prefer_premium_below: float = 0.03


@dataclass
class AllocationTarget:
    version: str
    categories: list[TargetCategory]
    rebalance_threshold: float
    premium_normal: float
    premium_reduced: float
    premium_switch: float


@dataclass
class Holding:
    code: str
    shares: float = 0.0
    amount_cny: float = 0.0
    cost_basis: float | None = None
    currency: str = "CNY"


@dataclass
class Holdings:
    as_of: date
    total_value_cny: float | None
    holdings: list[Holding] = field(default_factory=list)


def load_target(path: str | Path) -> AllocationTarget:
    raw = yaml.safe_load(Path(path).read_text())
    cats_raw = raw["categories"]
    categories = [
        TargetCategory(
            name=name,
            weight=float(body["weight"]),
            instruments=[str(x) for x in body["instruments"]],
            prefer_premium_below=float(body.get("prefer_premium_below", 0.03)),
        )
        for name, body in cats_raw.items()
    ]
    total = sum(c.weight for c in categories)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Category weights sum to {total}, must equal 1.0")

    rb = raw["rebalance"]
    pr = rb["premium_rules"]
    return AllocationTarget(
        version=str(raw["version"]),
        categories=categories,
        rebalance_threshold=float(rb["threshold"]),
        premium_normal=float(pr["normal"]),
        premium_reduced=float(pr["reduced"]),
        premium_switch=float(pr["switch"]),
    )
```

Also create `__init__.py`:

```python
# quant/portfolio/allocation_monitor/__init__.py
from .config import (
    AllocationTarget,
    TargetCategory,
    Holding,
    Holdings,
    load_target,
)

__all__ = [
    "AllocationTarget",
    "TargetCategory",
    "Holding",
    "Holdings",
    "load_target",
]
```

- [ ] **Step 1.4: Run test to verify pass**

Run: `pytest tests/unit/test_allocation_config.py -v`
Expected: PASS (both tests).

- [ ] **Step 1.5: Write failing test for holdings loader**

```python
# tests/unit/test_allocation_config.py (append)
from datetime import date as _date
from quant.portfolio.allocation_monitor.config import load_holdings, Holdings

def test_load_holdings(tmp_path):
    yaml_text = """
as_of: 2026-04-19
total_value_cny: 1000000
holdings:
  - code: 513100
    shares: 10000
    cost_basis: 1.25
  - code: CASH
    amount_cny: 50000
  - code: 03033.HK
    shares: 2000
    currency: HKD
"""
    p = tmp_path / "h.yaml"
    p.write_text(yaml_text)
    h = load_holdings(p)
    assert isinstance(h, Holdings)
    assert h.as_of == _date(2026, 4, 19)
    assert h.total_value_cny == 1_000_000
    assert len(h.holdings) == 3
    assert h.holdings[1].code == "CASH"
    assert h.holdings[1].amount_cny == 50_000
    assert h.holdings[2].currency == "HKD"
```

- [ ] **Step 1.6: Run test to confirm it fails**

Expected: FAIL on `load_holdings` not defined.

- [ ] **Step 1.7: Implement `load_holdings`**

Append to `config.py`:

```python
def load_holdings(path: str | Path) -> Holdings:
    raw = yaml.safe_load(Path(path).read_text())
    as_of = raw["as_of"]
    if isinstance(as_of, str):
        from datetime import datetime
        as_of = datetime.strptime(as_of, "%Y-%m-%d").date()
    holdings = [
        Holding(
            code=str(h["code"]),
            shares=float(h.get("shares", 0.0)),
            amount_cny=float(h.get("amount_cny", 0.0)),
            cost_basis=float(h["cost_basis"]) if "cost_basis" in h else None,
            currency=str(h.get("currency", "CNY")),
        )
        for h in raw.get("holdings", [])
    ]
    return Holdings(
        as_of=as_of,
        total_value_cny=float(raw["total_value_cny"]) if "total_value_cny" in raw else None,
        holdings=holdings,
    )
```

Add `load_holdings` to `__init__.py` exports.

- [ ] **Step 1.8: Run tests**

Run: `pytest tests/unit/test_allocation_config.py -v`
Expected: PASS all 3 tests.

- [ ] **Step 1.9: Create `config/allocation_target.yaml` from spec §3.1**

```yaml
# config/allocation_target.yaml
version: "2026-04-19"
total_must_equal: 1.0

categories:
  纳指100:
    weight: 0.25
    instruments: [513100, 159941]
    prefer_premium_below: 0.03
  标普500:
    weight: 0.10
    instruments: [513500]
  恒生科技:
    weight: 0.10
    instruments: [03033.HK]
  A股科技成长:
    weight: 0.15
    instruments: [159915, 588000, 512480]
  A股红利现金流:
    weight: 0.15
    instruments: [512890, 563020]
  黄金黄金股:
    weight: 0.15
    instruments: [518880, 517520]
  现金:
    weight: 0.10
    instruments: [CASH]

rebalance:
  threshold: 0.05
  premium_rules:
    normal: 0.03
    reduced: 0.05
    switch: 0.10
```

- [ ] **Step 1.10: Create `config/allocation_holdings.example.yaml`**

```yaml
# Example holdings file. Copy to config/allocation_holdings.yaml and edit.
as_of: 2026-04-19
total_value_cny: 1000000

holdings:
  - code: 513100
    shares: 10000
    cost_basis: 1.25
  - code: CASH
    amount_cny: 100000
```

- [ ] **Step 1.11: Commit**

```bash
git add quant/portfolio/allocation_monitor/__init__.py \
        quant/portfolio/allocation_monitor/config.py \
        config/allocation_target.yaml \
        config/allocation_holdings.example.yaml \
        tests/unit/test_allocation_config.py
git commit -m "feat: add allocation_monitor config loader with target/holdings YAML"
```

---

## Task 2: WeightMonitor + CLI `status`

**Files:**
- Create: `quant/portfolio/allocation_monitor/weight_monitor.py`
- Test: `tests/unit/test_allocation_weight_monitor.py`
- Modify: `quant/cli/portfolio.py` (add `status` subcommand)

- [ ] **Step 2.1: Write failing test for drift computation**

```python
# tests/unit/test_allocation_weight_monitor.py
from datetime import date
from quant.portfolio.allocation_monitor.config import (
    AllocationTarget, TargetCategory, Holdings, Holding,
)
from quant.portfolio.allocation_monitor.weight_monitor import (
    WeightMonitor, DriftReport,
)


def _make_target():
    return AllocationTarget(
        version="test",
        categories=[
            TargetCategory("纳指100", 0.5, ["513100"]),
            TargetCategory("现金", 0.5, ["CASH"]),
        ],
        rebalance_threshold=0.05,
        premium_normal=0.03,
        premium_reduced=0.05,
        premium_switch=0.10,
    )


def test_drift_on_balanced_holdings():
    target = _make_target()
    holdings = Holdings(
        as_of=date(2026, 4, 19),
        total_value_cny=None,
        holdings=[
            Holding(code="513100", shares=10000),
            Holding(code="CASH", amount_cny=16500),
        ],
    )
    prices = {"513100": 1.65}
    monitor = WeightMonitor()
    report = monitor.compute(target, holdings, prices)

    assert isinstance(report, DriftReport)
    assert report.total_value_cny == 33_000  # 10000*1.65 + 16500
    rows = {r.category: r for r in report.rows}
    assert abs(rows["纳指100"].actual_weight - 0.5) < 1e-6
    assert rows["纳指100"].status == "normal"
    assert report.triggered == []


def test_drift_triggers_rebalance():
    target = _make_target()
    holdings = Holdings(
        as_of=date(2026, 4, 19),
        total_value_cny=None,
        holdings=[
            Holding(code="513100", shares=10000),   # 16500
            Holding(code="CASH", amount_cny=3500),
        ],
    )
    prices = {"513100": 1.65}
    monitor = WeightMonitor()
    report = monitor.compute(target, holdings, prices)

    rows = {r.category: r for r in report.rows}
    # 纳指 actual = 16500/20000 = 0.825, drift = +0.325
    assert rows["纳指100"].status == "trigger"
    assert "纳指100" in report.triggered
    assert "现金" in report.triggered


def test_missing_price_raises():
    target = _make_target()
    holdings = Holdings(
        as_of=date(2026, 4, 19),
        total_value_cny=None,
        holdings=[Holding(code="513100", shares=10000)],
    )
    monitor = WeightMonitor()
    import pytest
    with pytest.raises(KeyError, match="513100"):
        monitor.compute(target, holdings, prices={})
```

- [ ] **Step 2.2: Run test, confirm FAIL**

Run: `pytest tests/unit/test_allocation_weight_monitor.py -v`
Expected: FAIL (module not found).

- [ ] **Step 2.3: Implement `weight_monitor.py`**

```python
# quant/portfolio/allocation_monitor/weight_monitor.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .config import AllocationTarget, Holdings


@dataclass
class DriftRow:
    category: str
    target_weight: float
    actual_weight: float
    drift: float
    status: str  # "normal" | "watch" | "trigger"


@dataclass
class DriftReport:
    as_of: date
    total_value_cny: float
    rows: list[DriftRow]
    triggered: list[str]


class WeightMonitor:
    """Compute current weight drift vs target allocation."""

    WATCH_THRESHOLD = 0.02

    def compute(
        self,
        target: AllocationTarget,
        holdings: Holdings,
        prices: dict[str, float],
    ) -> DriftReport:
        # Map code -> category name
        code_to_cat: dict[str, str] = {}
        for cat in target.categories:
            for instr in cat.instruments:
                code_to_cat[instr] = cat.name

        # Compute per-holding value
        category_values: dict[str, float] = {c.name: 0.0 for c in target.categories}
        total = 0.0
        for h in holdings.holdings:
            if h.code == "CASH":
                value = h.amount_cny
            else:
                if h.code not in prices:
                    raise KeyError(f"price missing for {h.code}")
                value = h.shares * prices[h.code]

            cat_name = code_to_cat.get(h.code)
            if cat_name is None:
                raise KeyError(f"holding {h.code} not in any target category")
            category_values[cat_name] += value
            total += value

        if total <= 0:
            raise ValueError("total portfolio value is zero")

        rows: list[DriftRow] = []
        triggered: list[str] = []
        for cat in target.categories:
            actual = category_values[cat.name] / total
            drift = actual - cat.weight
            adrift = abs(drift)
            if adrift >= target.rebalance_threshold:
                status = "trigger"
                triggered.append(cat.name)
            elif adrift >= self.WATCH_THRESHOLD:
                status = "watch"
            else:
                status = "normal"
            rows.append(DriftRow(
                category=cat.name,
                target_weight=cat.weight,
                actual_weight=actual,
                drift=drift,
                status=status,
            ))

        return DriftReport(
            as_of=holdings.as_of,
            total_value_cny=total,
            rows=rows,
            triggered=triggered,
        )
```

Add to `__init__.py`:

```python
from .weight_monitor import WeightMonitor, DriftReport, DriftRow
```

Append to `__all__`: `"WeightMonitor"`, `"DriftReport"`, `"DriftRow"`.

- [ ] **Step 2.4: Run tests, confirm PASS**

Run: `pytest tests/unit/test_allocation_weight_monitor.py -v`
Expected: 3 PASS.

- [ ] **Step 2.5: Write failing test for CLI `status` rendering**

```python
# tests/unit/test_allocation_weight_monitor.py (append)
from quant.portfolio.allocation_monitor.weight_monitor import render_drift_table

def test_render_drift_table_includes_all_rows():
    target = _make_target()
    holdings = Holdings(
        as_of=date(2026, 4, 19),
        total_value_cny=None,
        holdings=[
            Holding(code="513100", shares=10000),
            Holding(code="CASH", amount_cny=3500),
        ],
    )
    report = WeightMonitor().compute(target, holdings, {"513100": 1.65})
    text = render_drift_table(report)
    assert "纳指100" in text
    assert "现金" in text
    assert "🔴" in text or "trigger" in text
    assert "2026-04-19" in text
```

- [ ] **Step 2.6: Run, confirm FAIL**

Expected: FAIL on `render_drift_table` import.

- [ ] **Step 2.7: Implement `render_drift_table`**

Append to `weight_monitor.py`:

```python
STATUS_ICON = {"normal": "🟢", "watch": "🟡", "trigger": "🔴"}


def render_drift_table(report: DriftReport) -> str:
    lines = [
        f"Portfolio Status (as of {report.as_of})",
        f"Total Value: ¥{report.total_value_cny:,.0f}",
        "",
        f"{'Category':<20}{'Target':>8}{'Actual':>8}{'Drift':>9}  Status",
        "-" * 60,
    ]
    for r in report.rows:
        icon = STATUS_ICON[r.status]
        lines.append(
            f"{r.category:<20}{r.target_weight*100:>7.1f}%{r.actual_weight*100:>7.1f}%"
            f"{r.drift*100:>+8.1f}%  {icon} {r.status}"
        )
    if report.triggered:
        lines.append("")
        lines.append(f"Triggered rebalance: {', '.join(report.triggered)}")
    return "\n".join(lines)
```

Add `render_drift_table` to `__init__.py` exports.

- [ ] **Step 2.8: Run tests, confirm PASS**

Expected: 4 PASS in test_allocation_weight_monitor.py.

- [ ] **Step 2.9: Wire CLI subcommand `quant portfolio status`**

Modify `quant/cli/portfolio.py`:

In `register_portfolio_commands()` (after existing `list` parser), add:

```python
    # status 命令
    status_parser = portfolio_subparsers.add_parser('status', help='显示配置权重偏离')
    status_parser.add_argument('--target', default='config/allocation_target.yaml')
    status_parser.add_argument('--holdings', default='config/allocation_holdings.yaml')
```

In `handle_portfolio_command()`, add branch:

```python
    elif args.portfolio_action == 'status':
        handle_portfolio_status(args)
```

At module end, add:

```python
def handle_portfolio_status(args):
    from pathlib import Path
    from quant.portfolio.allocation_monitor import (
        load_target, load_holdings, WeightMonitor, render_drift_table,
    )
    from quant.data_providers.data_provider import TushareDataProvider

    target = load_target(args.target)
    holdings_path = Path(args.holdings)
    if not holdings_path.exists():
        print(f"❌ holdings file not found: {holdings_path}")
        print(f"   copy config/allocation_holdings.example.yaml and edit")
        sys.exit(1)
    holdings = load_holdings(holdings_path)

    # Fetch latest price for each non-CASH holding
    provider = TushareDataProvider()
    prices: dict[str, float] = {}
    for h in holdings.holdings:
        if h.code == "CASH":
            continue
        # fund_daily returns most-recent; take close of last row
        df = provider.get_etf_daily(h.code, start_date=None, end_date=None)
        if df is None or df.empty:
            print(f"⚠️  no price for {h.code}, skipping")
            continue
        prices[h.code] = float(df.iloc[-1]["close"])

    report = WeightMonitor().compute(target, holdings, prices)
    print(render_drift_table(report))
```

Note: the exact `TushareDataProvider.get_etf_daily(...)` method signature must be verified against `quant/data_providers/data_provider.py` — if it has a different name, substitute the actual fund_daily-wrapping method. If unclear, use `provider.pro.fund_daily(ts_code=...)` directly.

- [ ] **Step 2.10: Smoke-test CLI**

Run: `python -m quant.cli.main portfolio status --help`
Expected: help text listing `--target` and `--holdings`.

If `quant` package uses a different CLI entry, adapt accordingly; check `quant/cli/__init__.py` for the argparse root.

- [ ] **Step 2.11: Commit**

```bash
git add quant/portfolio/allocation_monitor/weight_monitor.py \
        quant/portfolio/allocation_monitor/__init__.py \
        quant/cli/portfolio.py \
        tests/unit/test_allocation_weight_monitor.py
git commit -m "feat: add WeightMonitor and 'portfolio status' CLI"
```

---

## Task 3: QDII Premium Radar + CLI `premium`

**Files:**
- Create: `quant/portfolio/allocation_monitor/premium.py`
- Test: `tests/unit/test_allocation_premium.py`
- Modify: `quant/cli/portfolio.py`

- [ ] **Step 3.1: Write failing test for premium classification**

```python
# tests/unit/test_allocation_premium.py
from quant.portfolio.allocation_monitor.premium import (
    classify_premium, PremiumRow,
)


def test_classify_normal():
    assert classify_premium(0.0, 0.03, 0.05, 0.10) == "ok"
    assert classify_premium(0.025, 0.03, 0.05, 0.10) == "ok"


def test_classify_reduce():
    assert classify_premium(0.035, 0.03, 0.05, 0.10) == "reduce"
    assert classify_premium(0.049, 0.03, 0.05, 0.10) == "reduce"


def test_classify_switch():
    assert classify_premium(0.05, 0.03, 0.05, 0.10) == "switch"
    assert classify_premium(0.09, 0.03, 0.05, 0.10) == "switch"


def test_classify_skip():
    assert classify_premium(0.10, 0.03, 0.05, 0.10) == "skip"
    assert classify_premium(0.15, 0.03, 0.05, 0.10) == "skip"


def test_classify_negative_premium_is_ok():
    # Discount (negative premium) is even better than normal buy
    assert classify_premium(-0.02, 0.03, 0.05, 0.10) == "ok"
```

- [ ] **Step 3.2: Run, confirm FAIL**

Run: `pytest tests/unit/test_allocation_premium.py -v`
Expected: FAIL.

- [ ] **Step 3.3: Implement `classify_premium` and `PremiumRow`**

```python
# quant/portfolio/allocation_monitor/premium.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PremiumRow:
    code: str
    name: str
    price: float
    nav: float
    premium: float
    status: str   # "ok" | "reduce" | "switch" | "skip"


def classify_premium(
    premium: float,
    normal: float,
    reduced: float,
    switch: float,
) -> str:
    if premium >= switch:
        return "skip"
    if premium >= reduced:
        return "switch"
    if premium >= normal:
        return "reduce"
    return "ok"


def compute_premium(price: float, nav: float) -> float:
    if nav <= 0:
        raise ValueError(f"invalid nav {nav}")
    return (price - nav) / nav
```

Add exports to `__init__.py`:

```python
from .premium import PremiumRow, classify_premium, compute_premium
```

- [ ] **Step 3.4: Run, confirm PASS**

Run: `pytest tests/unit/test_allocation_premium.py -v`
Expected: 5 PASS.

- [ ] **Step 3.5: Write failing test for PremiumRadar end-to-end**

```python
# tests/unit/test_allocation_premium.py (append)
from quant.portfolio.allocation_monitor.premium import PremiumRadar


class _StubProvider:
    def __init__(self, data):
        self._data = data

    def get_latest_price_and_nav(self, code):
        return self._data[code]   # returns dict {"price": X, "nav": Y, "name": Z}


def test_premium_radar_scan():
    provider = _StubProvider({
        "513100": {"price": 1.65, "nav": 1.54, "name": "纳指100 ETF"},   # 7.1%
        "159941": {"price": 1.58, "nav": 1.555, "name": "纳指100 ETF"},  # 1.6%
        "513500": {"price": 2.12, "nav": 2.085, "name": "标普500"},       # 1.7%
    })
    radar = PremiumRadar(provider=provider, normal=0.03, reduced=0.05, switch=0.10)
    rows = radar.scan(["513100", "159941", "513500"])
    assert len(rows) == 3
    by_code = {r.code: r for r in rows}
    assert by_code["513100"].status == "switch"
    assert by_code["159941"].status == "ok"
    assert by_code["513500"].status == "ok"
    assert abs(by_code["513100"].premium - 0.0714) < 0.001


def test_premium_radar_handles_missing_data(caplog):
    class _FailProvider:
        def get_latest_price_and_nav(self, code):
            raise RuntimeError("API down")
    radar = PremiumRadar(provider=_FailProvider(), normal=0.03, reduced=0.05, switch=0.10)
    rows = radar.scan(["513100"])
    assert rows == []   # skipped, not raised
```

- [ ] **Step 3.6: Run, confirm FAIL**

- [ ] **Step 3.7: Implement `PremiumRadar`**

Append to `premium.py`:

```python
import logging

logger = logging.getLogger(__name__)


class PremiumRadar:
    """Scan a list of QDII ETFs for premium status."""

    def __init__(self, provider, normal: float, reduced: float, switch: float):
        self.provider = provider
        self.normal = normal
        self.reduced = reduced
        self.switch = switch

    def scan(self, codes: list[str]) -> list[PremiumRow]:
        rows: list[PremiumRow] = []
        for code in codes:
            try:
                data = self.provider.get_latest_price_and_nav(code)
            except Exception as e:
                logger.warning(f"skip {code}: {e}")
                continue
            price = float(data["price"])
            nav = float(data["nav"])
            if nav <= 0:
                logger.warning(f"skip {code}: invalid nav {nav}")
                continue
            premium = (price - nav) / nav
            status = classify_premium(premium, self.normal, self.reduced, self.switch)
            rows.append(PremiumRow(
                code=code,
                name=str(data.get("name", code)),
                price=price,
                nav=nav,
                premium=premium,
                status=status,
            ))
        return rows
```

Add `PremiumRadar` to `__init__.py` exports.

- [ ] **Step 3.8: Run tests, confirm PASS**

Run: `pytest tests/unit/test_allocation_premium.py -v`
Expected: 7 PASS.

- [ ] **Step 3.9: Write the Tushare-backed provider adapter**

Create inside `premium.py` (same file, separate class):

```python
class TusharePremiumProvider:
    """Adapter: fetches latest price from fund_daily and nav from fund_nav."""

    def __init__(self, tushare_provider=None):
        if tushare_provider is None:
            from quant.data_providers.data_provider import TushareDataProvider
            tushare_provider = TushareDataProvider()
        self._ts = tushare_provider

    def get_latest_price_and_nav(self, code: str) -> dict:
        # Convert domestic ETF code to ts_code format if needed
        ts_code = self._to_ts_code(code)
        # Price: fund_daily last row
        df_price = self._ts.pro.fund_daily(ts_code=ts_code)
        if df_price is None or df_price.empty:
            raise RuntimeError(f"fund_daily empty for {code}")
        price = float(df_price.iloc[0]["close"])     # tushare returns desc by default

        # NAV: fund_nav last row
        df_nav = self._ts.pro.fund_nav(ts_code=ts_code)
        if df_nav is None or df_nav.empty:
            raise RuntimeError(f"fund_nav empty for {code}")
        nav = float(df_nav.iloc[0]["unit_nav"])

        # Name
        name = code
        try:
            df_basic = self._ts.pro.fund_basic(ts_code=ts_code)
            if df_basic is not None and not df_basic.empty:
                name = str(df_basic.iloc[0]["name"])
        except Exception:
            pass

        return {"price": price, "nav": nav, "name": name}

    @staticmethod
    def _to_ts_code(code: str) -> str:
        # Already suffixed (e.g. "513100.SH") -> pass through
        if "." in code:
            return code
        # HK codes like "03033.HK" — fund_daily doesn't cover; caller should handle
        if code.startswith("0") and len(code) == 5:
            raise RuntimeError(f"HK code {code} not supported by tushare fund_daily")
        # Domestic ETF: 5XXXXX -> SH, 1XXXXX -> SZ
        if code.startswith("5"):
            return f"{code}.SH"
        if code.startswith("1"):
            return f"{code}.SZ"
        raise RuntimeError(f"unknown code format: {code}")
```

Add to `__init__.py`:

```python
from .premium import TusharePremiumProvider
```

Note: HK codes (03033.HK for 恒生科技) are NOT in tushare's fund_daily. The adapter raises for them, and `PremiumRadar.scan` logs-and-skips. This is acceptable — HK premium tracking is a known gap (§10.1 of spec).

- [ ] **Step 3.10: Write test for _to_ts_code conversion**

```python
# tests/unit/test_allocation_premium.py (append)
from quant.portfolio.allocation_monitor.premium import TusharePremiumProvider

def test_to_ts_code_sh():
    assert TusharePremiumProvider._to_ts_code("513100") == "513100.SH"
def test_to_ts_code_sz():
    assert TusharePremiumProvider._to_ts_code("159941") == "159941.SZ"
def test_to_ts_code_passthrough():
    assert TusharePremiumProvider._to_ts_code("513100.SH") == "513100.SH"
def test_to_ts_code_hk_rejected():
    import pytest
    with pytest.raises(RuntimeError, match="HK"):
        TusharePremiumProvider._to_ts_code("03033")
```

- [ ] **Step 3.11: Run, confirm PASS**

- [ ] **Step 3.12: Wire CLI `quant portfolio premium`**

Modify `quant/cli/portfolio.py`:

```python
    # premium 命令
    premium_parser = portfolio_subparsers.add_parser('premium', help='QDII 溢价雷达')
    premium_parser.add_argument('--target', default='config/allocation_target.yaml')
    premium_parser.add_argument('--code', help='仅扫描指定代码，逗号分隔')
```

Add to dispatcher:

```python
    elif args.portfolio_action == 'premium':
        handle_portfolio_premium(args)
```

Add handler:

```python
def handle_portfolio_premium(args):
    from quant.portfolio.allocation_monitor import (
        load_target, PremiumRadar, TusharePremiumProvider,
    )

    target = load_target(args.target)

    if args.code:
        codes = [c.strip() for c in args.code.split(",")]
    else:
        # All non-CASH instruments across all categories
        codes = []
        for cat in target.categories:
            for instr in cat.instruments:
                if instr != "CASH":
                    codes.append(instr)

    radar = PremiumRadar(
        provider=TusharePremiumProvider(),
        normal=target.premium_normal,
        reduced=target.premium_reduced,
        switch=target.premium_switch,
    )
    rows = radar.scan(codes)

    print(f"QDII Premium Radar ({len(rows)} 只)")
    print(f"{'Code':<12}{'Name':<18}{'Price':>8}{'NAV':>8}{'Premium':>10}  Status")
    print("-" * 66)
    icon = {"ok": "🟢", "reduce": "🟡", "switch": "🔴", "skip": "⛔"}
    for r in rows:
        print(
            f"{r.code:<12}{r.name[:16]:<18}{r.price:>8.3f}{r.nav:>8.3f}"
            f"{r.premium*100:>+9.1f}%  {icon[r.status]} {r.status}"
        )
```

- [ ] **Step 3.13: Commit**

```bash
git add quant/portfolio/allocation_monitor/premium.py \
        quant/portfolio/allocation_monitor/__init__.py \
        quant/cli/portfolio.py \
        tests/unit/test_allocation_premium.py
git commit -m "feat: add PremiumRadar + 'portfolio premium' CLI with tushare adapter"
```

---

## Task 4: Allocator + CLI `allocate`

**Files:**
- Create: `quant/portfolio/allocation_monitor/allocator.py`
- Test: `tests/unit/test_allocation_allocator.py`
- Modify: `quant/cli/portfolio.py`

- [ ] **Step 4.1: Write failing test for allocator core logic**

```python
# tests/unit/test_allocation_allocator.py
from datetime import date
from quant.portfolio.allocation_monitor.config import (
    AllocationTarget, TargetCategory,
)
from quant.portfolio.allocation_monitor.weight_monitor import (
    DriftReport, DriftRow,
)
from quant.portfolio.allocation_monitor.premium import PremiumRow
from quant.portfolio.allocation_monitor.allocator import (
    Allocator, AllocationPlan,
)


def _target():
    return AllocationTarget(
        version="t",
        categories=[
            TargetCategory("纳指100", 0.5, ["513100", "159941"]),
            TargetCategory("黄金", 0.3, ["518880"]),
            TargetCategory("现金", 0.2, ["CASH"]),
        ],
        rebalance_threshold=0.05,
        premium_normal=0.03,
        premium_reduced=0.05,
        premium_switch=0.10,
    )


def _drift_report(**overrides):
    rows = [
        DriftRow("纳指100", 0.5, 0.30, -0.20, "trigger"),
        DriftRow("黄金",    0.3, 0.45, +0.15, "trigger"),
        DriftRow("现金",    0.2, 0.25, +0.05, "trigger"),
    ]
    return DriftReport(
        as_of=date(2026, 4, 19),
        total_value_cny=overrides.get("total", 100000),
        rows=rows,
        triggered=["纳指100", "黄金", "现金"],
    )


def test_allocator_prefers_underweight_category():
    plan = Allocator().allocate(
        amount=10000,
        target=_target(),
        drift=_drift_report(total=100000),
        premiums=[
            PremiumRow("513100", "N100", 1.65, 1.63, 0.012, "ok"),
            PremiumRow("159941", "N100", 1.58, 1.57, 0.006, "ok"),
            PremiumRow("518880", "GOLD", 4.5, 4.5, 0.0, "ok"),
        ],
    )
    assert isinstance(plan, AllocationPlan)
    assert plan.total_amount == 10000
    # First order should target 纳指100 (most underweight)
    assert any(o.instrument in {"513100", "159941"} for o in plan.orders)
    # 纳指 should get highest allocation (up to 40% cap)
    nasdaq_alloc = sum(o.amount_cny for o in plan.orders if o.instrument in {"513100", "159941"})
    assert nasdaq_alloc == 4000   # 40% cap of 10000


def test_allocator_skips_high_premium():
    plan = Allocator().allocate(
        amount=10000,
        target=_target(),
        drift=_drift_report(total=100000),
        premiums=[
            PremiumRow("513100", "N100", 1.75, 1.54, 0.136, "skip"),
            PremiumRow("159941", "N100", 1.58, 1.57, 0.006, "ok"),
            PremiumRow("518880", "GOLD", 4.5, 4.5, 0.0, "ok"),
        ],
    )
    nasdaq_orders = [o for o in plan.orders if o.instrument in {"513100", "159941"}]
    # Should route all nasdaq allocation to 159941
    assert all(o.instrument == "159941" for o in nasdaq_orders)
    assert any("513100" in w for w in plan.warnings)


def test_allocator_reduces_on_reduce_status():
    plan = Allocator().allocate(
        amount=10000,
        target=_target(),
        drift=_drift_report(total=100000),
        premiums=[
            PremiumRow("513100", "N100", 1.7, 1.63, 0.042, "reduce"),
            PremiumRow("159941", "N100", 1.7, 1.63, 0.042, "reduce"),
            PremiumRow("518880", "GOLD", 4.5, 4.5, 0.0, "ok"),
        ],
    )
    nasdaq_alloc = sum(o.amount_cny for o in plan.orders if o.instrument in {"513100", "159941"})
    assert nasdaq_alloc == 2000   # 40% cap * 50% reduce = 20% of 10000


def test_allocator_routes_leftover_to_cash():
    # All categories overweight except cash; expect most allocation into underweight only
    rows = [
        DriftRow("纳指100", 0.5, 0.60, +0.10, "trigger"),
        DriftRow("黄金",    0.3, 0.35, +0.05, "trigger"),
        DriftRow("现金",    0.2, 0.05, -0.15, "trigger"),
    ]
    report = DriftReport(
        as_of=date(2026, 4, 19),
        total_value_cny=100000,
        rows=rows,
        triggered=["纳指100", "黄金", "现金"],
    )
    plan = Allocator().allocate(
        amount=10000,
        target=_target(),
        drift=report,
        premiums=[
            PremiumRow("513100", "N100", 1.65, 1.63, 0.012, "ok"),
            PremiumRow("159941", "N100", 1.58, 1.57, 0.006, "ok"),
            PremiumRow("518880", "GOLD", 4.5, 4.5, 0.0, "ok"),
        ],
    )
    # Only 现金 is underweight → everything goes there
    cash_alloc = sum(o.amount_cny for o in plan.orders if o.instrument == "CASH")
    assert cash_alloc == 10000
```

- [ ] **Step 4.2: Run, confirm FAIL**

- [ ] **Step 4.3: Implement `allocator.py`**

```python
# quant/portfolio/allocation_monitor/allocator.py
from __future__ import annotations

from dataclasses import dataclass, field

from .config import AllocationTarget
from .premium import PremiumRow
from .weight_monitor import DriftReport


@dataclass
class AllocatorOrder:
    instrument: str
    amount_cny: float
    reason: str


@dataclass
class AllocationPlan:
    total_amount: float
    orders: list[AllocatorOrder] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Allocator:
    """Allocate new money across underweight categories, honoring premium rules."""

    SINGLE_CATEGORY_MAX = 0.40    # no single category receives > 40% of new money
    MIN_ORDER_CNY = 100           # skip tiny leftovers

    def allocate(
        self,
        amount: float,
        target: AllocationTarget,
        drift: DriftReport,
        premiums: list[PremiumRow],
    ) -> AllocationPlan:
        if amount <= 0:
            raise ValueError(f"amount must be positive, got {amount}")

        plan = AllocationPlan(total_amount=amount)
        premium_by_code = {p.code: p for p in premiums}
        category_by_name = {c.name: c for c in target.categories}

        # Underweight candidates sorted by |drift| desc (most underweight first)
        candidates = sorted(
            [r for r in drift.rows if r.drift < 0],
            key=lambda r: r.drift,   # ascending = most negative first
        )

        remaining = amount
        for row in candidates:
            if remaining < self.MIN_ORDER_CNY:
                break

            cat = category_by_name[row.category]

            # How much to bring this category back to target (in CNY)
            needed = abs(row.drift) * drift.total_value_cny
            # Cap single-category allocation
            max_for_this = amount * self.SINGLE_CATEGORY_MAX
            alloc = min(needed, max_for_this, remaining)

            # Pick instrument: CASH straight through; otherwise lowest-premium ok/reduce instrument
            if cat.instruments == ["CASH"]:
                plan.orders.append(AllocatorOrder(
                    instrument="CASH",
                    amount_cny=alloc,
                    reason=f"低配 {row.drift*100:+.1f}%",
                ))
                remaining -= alloc
                continue

            instrument, premium_status, premium_pct = self._pick_instrument(
                cat.instruments, premium_by_code, plan,
            )
            if instrument is None:
                plan.warnings.append(
                    f"{row.category}: 所有标的溢价过高，跳过"
                )
                continue

            if premium_status == "reduce":
                alloc *= 0.5

            plan.orders.append(AllocatorOrder(
                instrument=instrument,
                amount_cny=alloc,
                reason=f"低配 {row.drift*100:+.1f}%，溢价 {premium_pct*100:+.1f}%",
            ))
            remaining -= alloc

        # Any leftover into CASH as safe sink
        if remaining >= self.MIN_ORDER_CNY:
            # Only add CASH catch-all if not already present
            if not any(o.instrument == "CASH" for o in plan.orders):
                plan.orders.append(AllocatorOrder(
                    instrument="CASH",
                    amount_cny=remaining,
                    reason="剩余入货币基金",
                ))
            else:
                # Add to existing CASH order
                for o in plan.orders:
                    if o.instrument == "CASH":
                        o.amount_cny += remaining
                        break

        return plan

    def _pick_instrument(
        self,
        instruments: list[str],
        premium_by_code: dict,
        plan: AllocationPlan,
    ) -> tuple[str | None, str, float]:
        """Return (instrument, status, premium) or (None, ...) if all unusable."""
        # Filter: premium data present and status != "skip"/"switch"
        usable: list[tuple[str, PremiumRow]] = []
        for code in instruments:
            p = premium_by_code.get(code)
            if p is None:
                # No premium data (e.g., HK ETFs or tushare miss) → assume ok
                usable.append((code, None))
                continue
            if p.status == "skip":
                plan.warnings.append(f"{code} 溢价 {p.premium*100:+.1f}% 超过 10%，跳过")
                continue
            if p.status == "switch":
                plan.warnings.append(f"{code} 溢价 {p.premium*100:+.1f}% 过高，换同类低溢价")
                continue
            usable.append((code, p))

        if not usable:
            return None, "", 0.0

        # Prefer "ok" over "reduce"; tie-break by lowest premium
        def key(item):
            code, p = item
            if p is None:
                return (0, 0.0)
            priority = 0 if p.status == "ok" else 1
            return (priority, p.premium)

        usable.sort(key=key)
        code, p = usable[0]
        status = "ok" if p is None else p.status
        pct = 0.0 if p is None else p.premium
        return code, status, pct
```

Add to `__init__.py`:

```python
from .allocator import Allocator, AllocationPlan, AllocatorOrder
```

- [ ] **Step 4.4: Run tests, confirm PASS**

Run: `pytest tests/unit/test_allocation_allocator.py -v`
Expected: 4 PASS.

- [ ] **Step 4.5: Wire CLI `quant portfolio allocate AMOUNT`**

Modify `quant/cli/portfolio.py`:

```python
    # allocate 命令
    alloc_parser = portfolio_subparsers.add_parser('allocate', help='新增资金分配建议')
    alloc_parser.add_argument('amount', type=float, help='金额（人民币元）')
    alloc_parser.add_argument('--target', default='config/allocation_target.yaml')
    alloc_parser.add_argument('--holdings', default='config/allocation_holdings.yaml')
```

Dispatcher:

```python
    elif args.portfolio_action == 'allocate':
        handle_portfolio_allocate(args)
```

Handler:

```python
def handle_portfolio_allocate(args):
    from pathlib import Path
    from quant.portfolio.allocation_monitor import (
        load_target, load_holdings, WeightMonitor,
        PremiumRadar, TusharePremiumProvider, Allocator,
    )
    from quant.data_providers.data_provider import TushareDataProvider

    target = load_target(args.target)
    if not Path(args.holdings).exists():
        print(f"❌ holdings file not found: {args.holdings}")
        sys.exit(1)
    holdings = load_holdings(args.holdings)

    # Prices for weight calculation
    ts = TushareDataProvider()
    prices = {}
    for h in holdings.holdings:
        if h.code == "CASH":
            continue
        try:
            df = ts.get_etf_daily(h.code)
            prices[h.code] = float(df.iloc[-1]["close"])
        except Exception as e:
            print(f"⚠️  {h.code} 无价格: {e}")

    drift = WeightMonitor().compute(target, holdings, prices)

    # Premium scan for all non-CASH instruments in target
    codes = [i for c in target.categories for i in c.instruments if i != "CASH"]
    radar = PremiumRadar(
        provider=TusharePremiumProvider(),
        normal=target.premium_normal,
        reduced=target.premium_reduced,
        switch=target.premium_switch,
    )
    premiums = radar.scan(codes)

    plan = Allocator().allocate(args.amount, target, drift, premiums)
    print(f"Allocation Plan for ¥{args.amount:,.0f} (as of {drift.as_of})")
    print(f"{'#':<4}{'Instrument':<14}{'Amount':>10}  Reason")
    print("-" * 60)
    for i, o in enumerate(plan.orders, 1):
        print(f"{i:<4}{o.instrument:<14}{o.amount_cny:>10,.0f}  {o.reason}")
    if plan.warnings:
        print()
        for w in plan.warnings:
            print(f"⚠️  {w}")
```

- [ ] **Step 4.6: Commit**

```bash
git add quant/portfolio/allocation_monitor/allocator.py \
        quant/portfolio/allocation_monitor/__init__.py \
        quant/cli/portfolio.py \
        tests/unit/test_allocation_allocator.py
git commit -m "feat: add Allocator + 'portfolio allocate' CLI"
```

---

## Task 5: Quarterly Review + CLI `review`

**Files:**
- Create: `quant/portfolio/allocation_monitor/review.py`
- Test: `tests/unit/test_allocation_review.py`
- Modify: `quant/cli/portfolio.py`

- [ ] **Step 5.1: Write failing test for quarter parsing**

```python
# tests/unit/test_allocation_review.py
from datetime import date
from quant.portfolio.allocation_monitor.review import parse_quarter


def test_parse_quarter_q1():
    assert parse_quarter("2026Q1") == (date(2026, 1, 1), date(2026, 3, 31))


def test_parse_quarter_q4():
    assert parse_quarter("2025Q4") == (date(2025, 10, 1), date(2025, 12, 31))


def test_parse_quarter_invalid():
    import pytest
    with pytest.raises(ValueError):
        parse_quarter("2026Q5")
    with pytest.raises(ValueError):
        parse_quarter("abcd")
```

- [ ] **Step 5.2: Run, confirm FAIL**

- [ ] **Step 5.3: Implement `parse_quarter` and review skeleton**

```python
# quant/portfolio/allocation_monitor/review.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .config import AllocationTarget, Holdings
from .weight_monitor import DriftReport, WeightMonitor


_QUARTER_RE = re.compile(r"^(\d{4})Q([1-4])$")


def parse_quarter(label: str) -> tuple[date, date]:
    m = _QUARTER_RE.match(label)
    if not m:
        raise ValueError(f"invalid quarter label: {label!r}")
    year = int(m.group(1))
    q = int(m.group(2))
    starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    return date(year, *starts[q]), date(year, *ends[q])
```

- [ ] **Step 5.4: Run tests, confirm PASS**

- [ ] **Step 5.5: Write failing test for contribution + report skeleton**

```python
# tests/unit/test_allocation_review.py (append)
from quant.portfolio.allocation_monitor.config import (
    AllocationTarget, TargetCategory, Holdings, Holding,
)
from quant.portfolio.allocation_monitor.review import (
    QuarterlyReview, QuarterlyReport,
)

def _target():
    return AllocationTarget(
        version="t",
        categories=[
            TargetCategory("纳指", 0.5, ["513100"]),
            TargetCategory("现金", 0.5, ["CASH"]),
        ],
        rebalance_threshold=0.05,
        premium_normal=0.03,
        premium_reduced=0.05,
        premium_switch=0.10,
    )


def test_quarterly_review_generates_report():
    target = _target()
    h_start = Holdings(
        as_of=date(2026, 1, 1),
        total_value_cny=None,
        holdings=[
            Holding(code="513100", shares=10000),   # price 1.5 = 15000
            Holding(code="CASH", amount_cny=15000),
        ],
    )
    h_end = Holdings(
        as_of=date(2026, 3, 31),
        total_value_cny=None,
        holdings=[
            Holding(code="513100", shares=10000),   # price 1.65 = 16500
            Holding(code="CASH", amount_cny=15000),
        ],
    )
    report = QuarterlyReview().generate(
        quarter="2026Q1",
        target=target,
        holdings_start=h_start,
        holdings_end=h_end,
        prices_start={"513100": 1.50},
        prices_end={"513100": 1.65},
    )
    assert isinstance(report, QuarterlyReport)
    assert report.quarter == "2026Q1"
    assert report.start_value == 30000
    assert report.end_value == 31500
    assert abs(report.period_return - 0.05) < 1e-6
    assert "2026Q1" in report.markdown
    assert "纳指" in report.markdown
    # 纳指 contribution: started at 50% weight * 10% gain = +5.0%
    assert abs(report.category_contributions["纳指"] - 0.05) < 1e-6
    assert abs(report.category_contributions["现金"]) < 1e-6
```

- [ ] **Step 5.6: Run, confirm FAIL**

- [ ] **Step 5.7: Implement `QuarterlyReview`**

Append to `review.py`:

```python
@dataclass
class QuarterlyReport:
    quarter: str
    start_value: float
    end_value: float
    period_return: float
    drift_start: DriftReport
    drift_end: DriftReport
    category_contributions: dict
    rebalance_needed: bool
    markdown: str


class QuarterlyReview:
    """Generate a quarterly review report combining drift + returns + rebalance call."""

    def generate(
        self,
        quarter: str,
        target: AllocationTarget,
        holdings_start: Holdings,
        holdings_end: Holdings,
        prices_start: dict,
        prices_end: dict,
    ) -> QuarterlyReport:
        monitor = WeightMonitor()
        drift_start = monitor.compute(target, holdings_start, prices_start)
        drift_end = monitor.compute(target, holdings_end, prices_end)

        period_return = (drift_end.total_value_cny / drift_start.total_value_cny) - 1

        # Category contribution: start_weight * category_return_over_period
        # Compute each category's per-unit return: (value_end - value_start_constant_shares) / value_start
        # Simplification: start_weight × (end_actual_weight / start_actual_weight × (1 + period_return) - 1)
        # Easier: direct per-category value change (holdings assumed unchanged intra-quarter)
        contributions: dict[str, float] = {}
        start_rows = {r.category: r for r in drift_start.rows}
        end_rows = {r.category: r for r in drift_end.rows}
        for cat in target.categories:
            sv = start_rows[cat.name].actual_weight * drift_start.total_value_cny
            ev = end_rows[cat.name].actual_weight * drift_end.total_value_cny
            if sv <= 0:
                contributions[cat.name] = 0.0
                continue
            cat_return = (ev - sv) / sv
            # Contribution to portfolio = start_weight × cat_return
            contributions[cat.name] = start_rows[cat.name].actual_weight * cat_return

        rebalance_needed = bool(drift_end.triggered)

        md_lines = [
            f"# Portfolio Review: {quarter}",
            "",
            "## 1. 季度表现",
            f"- 期初总值：¥{drift_start.total_value_cny:,.0f}",
            f"- 期末总值：¥{drift_end.total_value_cny:,.0f}",
            f"- 区间收益：{period_return*100:+.2f}%",
            "",
            "## 2. 各类别贡献度",
            "| 类别 | 起始权重 | 期末权重 | 对组合贡献 |",
            "|---|---|---|---|",
        ]
        for cat in target.categories:
            md_lines.append(
                f"| {cat.name} | {start_rows[cat.name].actual_weight*100:.1f}% "
                f"| {end_rows[cat.name].actual_weight*100:.1f}% "
                f"| {contributions[cat.name]*100:+.2f}% |"
            )
        md_lines += [
            "",
            "## 3. 再平衡判断",
            f"- 触发阈值：±{target.rebalance_threshold*100:.0f}%",
            f"- 触发类别：{', '.join(drift_end.triggered) if drift_end.triggered else '无'}",
            f"- 建议：{'需要再平衡' if rebalance_needed else '维持现状'}",
            "",
        ]

        return QuarterlyReport(
            quarter=quarter,
            start_value=drift_start.total_value_cny,
            end_value=drift_end.total_value_cny,
            period_return=period_return,
            drift_start=drift_start,
            drift_end=drift_end,
            category_contributions=contributions,
            rebalance_needed=rebalance_needed,
            markdown="\n".join(md_lines),
        )
```

Add exports to `__init__.py`:

```python
from .review import QuarterlyReview, QuarterlyReport, parse_quarter
```

- [ ] **Step 5.8: Run tests, confirm PASS**

Run: `pytest tests/unit/test_allocation_review.py -v`
Expected: 4 PASS.

- [ ] **Step 5.9: Write test for rebalance-needed path using Rebalancer**

```python
# tests/unit/test_allocation_review.py (append)

def test_quarterly_review_flags_rebalance_when_drift_exceeds_threshold():
    target = _target()
    h_start = Holdings(
        as_of=date(2026, 1, 1), total_value_cny=None,
        holdings=[Holding("513100", shares=10000), Holding("CASH", amount_cny=15000)],
    )
    h_end = Holdings(
        as_of=date(2026, 3, 31), total_value_cny=None,
        holdings=[Holding("513100", shares=10000), Holding("CASH", amount_cny=15000)],
    )
    # Nasdaq doubles → 纳指 actual weight ~67%, drift +17% exceeds 5% threshold
    report = QuarterlyReview().generate(
        quarter="2026Q1",
        target=target,
        holdings_start=h_start,
        holdings_end=h_end,
        prices_start={"513100": 1.5},
        prices_end={"513100": 3.0},
    )
    assert report.rebalance_needed is True
    assert "需要再平衡" in report.markdown
```

- [ ] **Step 5.10: Run, confirm PASS**

- [ ] **Step 5.11: Wire CLI `quant portfolio review`**

Modify `quant/cli/portfolio.py`:

```python
    # review 命令
    review_parser = portfolio_subparsers.add_parser('review', help='季度 review 报告')
    review_parser.add_argument('--quarter', required=True, help='如 2026Q1')
    review_parser.add_argument('--target', default='config/allocation_target.yaml')
    review_parser.add_argument('--holdings-start', required=True, help='期初持仓 YAML')
    review_parser.add_argument('--holdings-end', required=True, help='期末持仓 YAML')
    review_parser.add_argument('--out', default=None, help='输出 markdown 路径（默认打印到终端）')
```

Dispatcher:

```python
    elif args.portfolio_action == 'review':
        handle_portfolio_review(args)
```

Handler:

```python
def handle_portfolio_review(args):
    from pathlib import Path
    from quant.portfolio.allocation_monitor import (
        load_target, load_holdings, QuarterlyReview, parse_quarter,
    )
    from quant.data_providers.data_provider import TushareDataProvider

    target = load_target(args.target)
    h_start = load_holdings(args.holdings_start)
    h_end = load_holdings(args.holdings_end)

    start_date, end_date = parse_quarter(args.quarter)

    ts = TushareDataProvider()

    def _fetch_price_on(code: str, on: date) -> float:
        df = ts.get_etf_daily(
            code,
            start_date=on.strftime("%Y%m%d"),
            end_date=on.strftime("%Y%m%d"),
        )
        # Tushare may return empty on weekends → walk back up to 7 days
        for i in range(7):
            if df is not None and not df.empty:
                return float(df.iloc[-1]["close"])
            off = on.replace(day=max(1, on.day - 1 - i))
            df = ts.get_etf_daily(code, start_date=off.strftime("%Y%m%d"),
                                  end_date=off.strftime("%Y%m%d"))
        raise RuntimeError(f"no price for {code} near {on}")

    prices_start = {h.code: _fetch_price_on(h.code, start_date)
                    for h in h_start.holdings if h.code != "CASH"}
    prices_end = {h.code: _fetch_price_on(h.code, end_date)
                  for h in h_end.holdings if h.code != "CASH"}

    report = QuarterlyReview().generate(
        quarter=args.quarter,
        target=target,
        holdings_start=h_start,
        holdings_end=h_end,
        prices_start=prices_start,
        prices_end=prices_end,
    )

    if args.out:
        Path(args.out).write_text(report.markdown)
        print(f"✅ saved to {args.out}")
    else:
        print(report.markdown)
```

- [ ] **Step 5.12: Final commit**

```bash
git add quant/portfolio/allocation_monitor/review.py \
        quant/portfolio/allocation_monitor/__init__.py \
        quant/cli/portfolio.py \
        tests/unit/test_allocation_review.py
git commit -m "feat: add QuarterlyReview + 'portfolio review' CLI"
```

---

## Task 6: End-to-end smoke + docs

**Files:**
- Modify: `quant/portfolio/__init__.py` (re-export)
- Create: small README section or CLI help verification

- [ ] **Step 6.1: Verify `quant/portfolio/__init__.py` re-exports the new package**

Append:

```python
# quant/portfolio/__init__.py
from . import allocation_monitor  # noqa: F401
```

- [ ] **Step 6.2: Run full test suite to verify no regressions**

Run: `pytest tests/unit/test_allocation_*.py -v`
Expected: all allocation tests pass.

Run: `pytest tests/unit/ -x -q`
Expected: no regressions in the broader unit suite.

- [ ] **Step 6.3: Smoke test CLI entry points**

```bash
python -m quant.cli.main portfolio status --help
python -m quant.cli.main portfolio premium --help
python -m quant.cli.main portfolio allocate --help
python -m quant.cli.main portfolio review --help
```

Expected: each help prints without error.

- [ ] **Step 6.4: Manual end-to-end with real tushare (optional, requires TUSHARE_TOKEN)**

Create `config/allocation_holdings.yaml` by copying the example, then:

```bash
python -m quant.cli.main portfolio status
python -m quant.cli.main portfolio premium
python -m quant.cli.main portfolio allocate 20000
```

Expected: each prints its report. If tushare fails, warnings log but commands don't crash.

- [ ] **Step 6.5: Commit**

```bash
git add quant/portfolio/__init__.py
git commit -m "chore: re-export allocation_monitor from quant.portfolio"
```

---

## Notes

- **CLI entry path**: This plan assumes `python -m quant.cli.main` is the CLI entry. Verify by checking `quant/cli/__init__.py` or `quant/cli/main.py` and adapt if it uses a different entrypoint (e.g., `quant.main`).
- **Tushare method name**: The plan uses `TushareDataProvider.get_etf_daily(...)`. If the actual method is `get_fund_daily`, `fetch_etf`, or similar, substitute. Inspect `quant/data_providers/data_provider.py` for the real name.
- **HK ETFs (03033.HK)**: Deliberately unsupported by the tushare adapter. `PremiumRadar` logs-and-skips. For Task 5 review, HK holdings need a manual price fallback — if this comes up in real use, add an akshare adapter as follow-up (out of scope for this plan).
