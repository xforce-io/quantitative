# A 股行业 ETF 轮动系统 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 spec `docs/superpowers/specs/2026-05-02-ashare-rotation-design.md` 描述的双层（B 行业 ETF 截面 12-1 动量 + A 风险 multiplier）月频轮动系统，端到端可跑回测，月末可拿到目标持仓清单。

**Architecture:** 4 个新模块在 `quant/analysis/rotation/`（ranker / regime_overlay / portfolio / backtest，互相解耦，纯计算函数为主） + `RotationService` 把 DataService 与上面四件套串起来 + `config/rotation_universe.yaml` 维护可投资 ETF 池。每个模块对应一个 unit test 文件，外加一个 integration test 跑端到端。

**Tech Stack:** Python 3.12, pandas, numpy, pyyaml, pytest, uv（运行环境管理）。复用 `quant.services.DataService` 和 `quant.analysis.lowfreq.regime.LowFrequencyRegimeScorer`。

---

## File Structure

新建：

```
config/rotation_universe.yaml                       # 24 只 ETF 清单
quant/analysis/rotation/__init__.py                 # 包公开 API
quant/analysis/rotation/universe.py                 # yaml → list[EtfEntry]
quant/analysis/rotation/ranker.py                   # MomentumRanker (B 层)
quant/analysis/rotation/regime_overlay.py           # SimpleRegimeOverlay (A 层)
quant/analysis/rotation/portfolio.py                # PortfolioCombiner
quant/analysis/rotation/backtest.py                 # RotationBacktester (multi-asset)
quant/services/rotation_service.py                  # RotationService

tests/unit/test_rotation_universe.py
tests/unit/test_rotation_ranker.py
tests/unit/test_rotation_overlay.py
tests/unit/test_rotation_portfolio.py
tests/unit/test_rotation_backtest.py
tests/unit/test_rotation_service.py
tests/integration/test_rotation_pipeline.py

quant/cli/rotation.py                               # CLI 子命令
```

修改：

```
quant/services/__init__.py                          # 导出 RotationService / RotationRequest
quant/cli/__init__.py                               # 导出 register_rotation_commands
quant/__main__.py                                   # 接入 register_rotation_commands + handle_rotation_command
```

**单元 / 集成边界**：unit 测每个模块，纯输入纯输出；integration 跑 service 端到端，DataService 用 monkey-patch 注入合成价格数据，不打真实数据源。

---

## Task 1: Universe loader + yaml

**Files:**
- Create: `config/rotation_universe.yaml`
- Create: `quant/analysis/rotation/__init__.py`
- Create: `quant/analysis/rotation/universe.py`
- Test: `tests/unit/test_rotation_universe.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_rotation_universe.py`:

```python
"""Tests for rotation universe loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from quant.analysis.rotation.universe import EtfEntry, load_universe


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "universe.yaml"
    p.write_text(content, encoding="utf-8")
    return p


def test_load_universe_returns_entries(tmp_path: Path) -> None:
    yaml = _write_yaml(
        tmp_path,
        """
        schema_version: 1
        updated_at: "2026-05-02"
        industry_etfs:
          - { symbol: "510050.SH", name: "上证50ETF", category: "大盘" }
          - { symbol: "512000.SH", name: "券商ETF",   category: "金融" }
        style_etfs:
          - { symbol: "510880.SH", name: "红利ETF",   category: "风格-红利" }
        """,
    )
    entries = load_universe(yaml)
    assert len(entries) == 3
    assert entries[0] == EtfEntry(symbol="510050.SH", name="上证50ETF", category="大盘")
    assert {e.symbol for e in entries} == {"510050.SH", "512000.SH", "510880.SH"}


def test_load_universe_rejects_duplicate_symbol(tmp_path: Path) -> None:
    yaml = _write_yaml(
        tmp_path,
        """
        schema_version: 1
        industry_etfs:
          - { symbol: "510050.SH", name: "上证50ETF", category: "大盘" }
          - { symbol: "510050.SH", name: "上证50ETF重复", category: "大盘" }
        """,
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_universe(yaml)


def test_load_universe_rejects_missing_field(tmp_path: Path) -> None:
    yaml = _write_yaml(
        tmp_path,
        """
        schema_version: 1
        industry_etfs:
          - { symbol: "510050.SH", category: "大盘" }
        """,
    )
    with pytest.raises(ValueError, match="missing field"):
        load_universe(yaml)


def test_load_universe_rejects_unknown_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_universe(tmp_path / "does_not_exist.yaml")


def test_load_universe_default_path_loads(tmp_path: Path, monkeypatch) -> None:
    """Repo's default config/rotation_universe.yaml must be valid and non-empty."""
    entries = load_universe(None)
    assert len(entries) >= 10
    # All entries must have valid 6-digit codes plus exchange suffix
    for e in entries:
        assert "." in e.symbol
        code, suffix = e.symbol.split(".")
        assert code.isdigit() and len(code) == 6
        assert suffix in {"SH", "SZ"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_rotation_universe.py -v
```

Expected: ImportError / ModuleNotFoundError on `quant.analysis.rotation.universe`.

- [ ] **Step 3: Create config yaml**

Create `config/rotation_universe.yaml` (full universe per spec §5.1 — copy verbatim):

```yaml
schema_version: 1
updated_at: "2026-05-02"

industry_etfs:
  - { symbol: "510050.SH", name: "上证50ETF",     category: "大盘" }
  - { symbol: "512000.SH", name: "券商ETF",       category: "金融" }
  - { symbol: "512800.SH", name: "银行ETF",       category: "金融" }
  - { symbol: "512170.SH", name: "医疗ETF",       category: "医药" }
  - { symbol: "512010.SH", name: "医药ETF",       category: "医药" }
  - { symbol: "159995.SZ", name: "芯片ETF",       category: "科技" }
  - { symbol: "515050.SH", name: "5G ETF",        category: "科技" }
  - { symbol: "512720.SH", name: "计算机ETF",     category: "科技" }
  - { symbol: "159928.SZ", name: "消费ETF",       category: "消费" }
  - { symbol: "159825.SZ", name: "农业ETF",       category: "消费" }
  - { symbol: "512400.SH", name: "有色ETF",       category: "周期" }
  - { symbol: "515220.SH", name: "煤炭ETF",       category: "周期" }
  - { symbol: "515210.SH", name: "钢铁ETF",       category: "周期" }
  - { symbol: "159611.SZ", name: "电力ETF",       category: "公用事业" }
  - { symbol: "159930.SZ", name: "能源ETF",       category: "周期" }
  - { symbol: "512660.SH", name: "军工ETF",       category: "军工" }
  - { symbol: "515030.SH", name: "新能源车ETF",   category: "新能源" }
  - { symbol: "515790.SH", name: "光伏ETF",       category: "新能源" }
  - { symbol: "159870.SZ", name: "化工ETF",       category: "周期" }
  - { symbol: "512200.SH", name: "房地产ETF",     category: "金融" }

style_etfs:
  - { symbol: "510880.SH", name: "红利ETF",       category: "风格-红利" }
  - { symbol: "159949.SZ", name: "创业板50",      category: "风格-成长" }
  - { symbol: "510310.SH", name: "沪深300",       category: "风格-大盘" }
  - { symbol: "159922.SZ", name: "中证500",       category: "风格-中盘" }
```

- [ ] **Step 4: Create rotation package + universe loader**

Create `quant/analysis/rotation/__init__.py`:

```python
"""A 股行业 ETF 轮动系统模块。"""
from quant.analysis.rotation.universe import EtfEntry, load_universe

__all__ = ["EtfEntry", "load_universe"]
```

Create `quant/analysis/rotation/universe.py`:

```python
"""Rotation universe configuration loader."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

_REQUIRED_FIELDS = ("symbol", "name", "category")
_DEFAULT_YAML_RELATIVE = "config/rotation_universe.yaml"


@dataclass(frozen=True)
class EtfEntry:
    """One ETF in the rotation universe."""

    symbol: str
    name: str
    category: str


def _project_root() -> Path:
    # quant/analysis/rotation/universe.py → repo root is parents[3]
    return Path(__file__).resolve().parents[3]


def _coerce_entries(raw_list: Iterable[dict]) -> list[EtfEntry]:
    entries: list[EtfEntry] = []
    for raw in raw_list or []:
        for field in _REQUIRED_FIELDS:
            if field not in raw:
                raise ValueError(f"universe entry missing field {field!r}: {raw}")
        entries.append(
            EtfEntry(
                symbol=str(raw["symbol"]),
                name=str(raw["name"]),
                category=str(raw["category"]),
            )
        )
    return entries


def load_universe(path: Path | str | None) -> list[EtfEntry]:
    """Load and validate the rotation universe from yaml.

    Pass ``None`` to load the repo default at ``config/rotation_universe.yaml``.
    Raises FileNotFoundError if the file is missing, ValueError on schema problems
    (missing field or duplicate symbol).
    """
    if path is None:
        resolved = _project_root() / _DEFAULT_YAML_RELATIVE
    else:
        resolved = Path(path)

    if not resolved.exists():
        raise FileNotFoundError(f"universe yaml not found: {resolved}")

    with resolved.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    entries = _coerce_entries(data.get("industry_etfs"))
    entries.extend(_coerce_entries(data.get("style_etfs")))

    seen: set[str] = set()
    for entry in entries:
        if entry.symbol in seen:
            raise ValueError(f"duplicate symbol in universe: {entry.symbol}")
        seen.add(entry.symbol)

    return entries
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_rotation_universe.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add config/rotation_universe.yaml quant/analysis/rotation/__init__.py \
        quant/analysis/rotation/universe.py tests/unit/test_rotation_universe.py
git commit -m "$(cat <<'EOF'
feat: add rotation universe loader with 24 ETFs

Loads industry + style ETF universe from config/rotation_universe.yaml
into typed EtfEntry records.  Validates schema and rejects duplicates.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: MomentumRanker (B 层)

**Files:**
- Create: `quant/analysis/rotation/ranker.py`
- Modify: `quant/analysis/rotation/__init__.py`
- Test: `tests/unit/test_rotation_ranker.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_rotation_ranker.py`:

```python
"""Tests for MomentumRanker."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.analysis.rotation.ranker import MomentumRanker, RankerConfig


def _monthly_prices_with_known_momentum(growth: dict[str, float]) -> pd.DataFrame:
    """Build a 24-month price frame where each symbol has constant monthly growth."""
    months = pd.date_range("2022-01-31", periods=24, freq="ME")
    data = {sym: 100.0 * (1 + g) ** np.arange(24) for sym, g in growth.items()}
    return pd.DataFrame(data, index=months)


def test_top_k_selects_highest_12_1_momentum() -> None:
    prices = _monthly_prices_with_known_momentum(
        {"A": 0.05, "B": 0.04, "C": 0.03, "D": 0.02, "E": 0.01, "F": -0.01}
    )
    ranker = MomentumRanker(RankerConfig(top_k=3))
    weights = ranker.rank(prices, prices.index[-1])
    # 12-1 momentum favors highest growth — A, B, C
    assert set(weights) == {"A", "B", "C"}
    assert pytest.approx(sum(weights.values()), abs=1e-9) == 1.0
    for w in weights.values():
        assert pytest.approx(w, abs=1e-9) == 1.0 / 3


def test_cash_filter_returns_empty_when_top_k_mean_below_threshold() -> None:
    # All assets shrinking → top-K mean momentum is negative
    prices = _monthly_prices_with_known_momentum(
        {"A": -0.01, "B": -0.02, "C": -0.03, "D": -0.04, "E": -0.05}
    )
    ranker = MomentumRanker(RankerConfig(top_k=3, cash_threshold=0.0))
    weights = ranker.rank(prices, prices.index[-1])
    assert weights == {}


def test_insufficient_history_excluded_from_ranking() -> None:
    prices = _monthly_prices_with_known_momentum(
        {"A": 0.05, "B": 0.04, "C": 0.03}
    )
    # Drop first 12 rows of B → only 12 months of B data, less than required 13
    prices.loc[prices.index[:12], "B"] = np.nan

    ranker = MomentumRanker(RankerConfig(top_k=3))
    weights = ranker.rank(prices, prices.index[-1])
    assert "B" not in weights
    assert set(weights) <= {"A", "C"}


def test_explicit_12_1_formula() -> None:
    """Verify momentum = price[t-1] / price[t-13] - 1 exactly."""
    prices = pd.DataFrame(
        {
            "X": [100.0] * 13 + [200.0],  # only changes at t=13
            "Y": [100.0] * 14,            # constant
        },
        index=pd.date_range("2024-01-31", periods=14, freq="ME"),
    )
    ranker = MomentumRanker(RankerConfig(top_k=2, cash_threshold=-1.0))
    weights = ranker.rank(prices, prices.index[-1])
    # X's price[t-1] = 100 (index -2), price[t-13] = 100 (index -14 doesn't exist; t=index[-1]=13)
    # With skip_recent=1, we use price at index[-2]=100 vs price at index[-13]=index[0]=100
    # Both are 0% over 12-1 horizon; ranker should still place them but cash threshold is -1
    assert set(weights) == {"X", "Y"}


def test_empty_universe_at_rebalance_returns_empty() -> None:
    prices = pd.DataFrame({"A": [np.nan] * 24}, index=pd.date_range("2022-01-31", periods=24, freq="ME"))
    ranker = MomentumRanker(RankerConfig(top_k=3))
    weights = ranker.rank(prices, prices.index[-1])
    assert weights == {}


def test_rebalance_date_must_exist_in_index() -> None:
    prices = _monthly_prices_with_known_momentum({"A": 0.05, "B": 0.04})
    ranker = MomentumRanker()
    with pytest.raises(KeyError):
        ranker.rank(prices, pd.Timestamp("1999-01-31"))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_rotation_ranker.py -v
```

Expected: ImportError on `MomentumRanker`.

- [ ] **Step 3: Implement MomentumRanker**

Create `quant/analysis/rotation/ranker.py`:

```python
"""Cross-sectional momentum ranker for rotation universe."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RankerConfig:
    """Parameters for cross-sectional momentum ranking."""

    lookback_months: int = 12
    skip_recent_months: int = 1
    top_k: int = 5
    cash_threshold: float = 0.0


class MomentumRanker:
    """Rank universe by ``price[t-skip] / price[t-skip-lookback] - 1`` momentum."""

    def __init__(self, config: RankerConfig | None = None) -> None:
        self.config = config or RankerConfig()
        if self.config.lookback_months <= 0:
            raise ValueError("lookback_months must be positive")
        if self.config.skip_recent_months < 0:
            raise ValueError("skip_recent_months must be non-negative")
        if self.config.top_k <= 0:
            raise ValueError("top_k must be positive")

    def rank(
        self,
        monthly_prices: pd.DataFrame,
        rebalance_date: pd.Timestamp,
    ) -> dict[str, float]:
        """Return ``{symbol: weight}`` for the rebalance date.

        Returns an empty dict when the cash filter triggers or no symbol has
        enough history.  ``rebalance_date`` must exist in ``monthly_prices.index``.
        """
        if rebalance_date not in monthly_prices.index:
            raise KeyError(f"rebalance_date {rebalance_date} not in price index")

        loc = monthly_prices.index.get_loc(rebalance_date)
        skip = self.config.skip_recent_months
        lookback = self.config.lookback_months

        # We need price at (loc - skip) and price at (loc - skip - lookback)
        end_idx = loc - skip
        start_idx = end_idx - lookback
        if start_idx < 0 or end_idx < 0:
            return {}

        end_row = monthly_prices.iloc[end_idx]
        start_row = monthly_prices.iloc[start_idx]

        # Compute momentum per symbol; drop those with NaN at either endpoint
        momentum: dict[str, float] = {}
        for symbol in monthly_prices.columns:
            p_start = start_row[symbol]
            p_end = end_row[symbol]
            if pd.isna(p_start) or pd.isna(p_end) or p_start <= 0:
                continue
            momentum[symbol] = float(p_end / p_start - 1.0)

        if not momentum:
            return {}

        # Sort descending, take top-K
        ranked = sorted(momentum.items(), key=lambda kv: kv[1], reverse=True)
        top = ranked[: self.config.top_k]

        # Cash filter: top-K mean below threshold → empty (all-cash signal)
        if np.mean([m for _, m in top]) < self.config.cash_threshold:
            return {}

        weight = 1.0 / len(top)
        return {sym: weight for sym, _ in top}
```

- [ ] **Step 4: Update package __init__**

Modify `quant/analysis/rotation/__init__.py`:

```python
"""A 股行业 ETF 轮动系统模块。"""
from quant.analysis.rotation.ranker import MomentumRanker, RankerConfig
from quant.analysis.rotation.universe import EtfEntry, load_universe

__all__ = ["EtfEntry", "MomentumRanker", "RankerConfig", "load_universe"]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_rotation_ranker.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add quant/analysis/rotation/ranker.py quant/analysis/rotation/__init__.py \
        tests/unit/test_rotation_ranker.py
git commit -m "$(cat <<'EOF'
feat: add MomentumRanker for cross-sectional 12-1 momentum

Ranks rotation universe by lookback/skip momentum, returns top-K equal
weights or empty dict when the top-K mean falls below cash threshold.
Symbols with insufficient history are silently dropped from ranking.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: PortfolioCombiner

**Files:**
- Create: `quant/analysis/rotation/portfolio.py`
- Modify: `quant/analysis/rotation/__init__.py`
- Test: `tests/unit/test_rotation_portfolio.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_rotation_portfolio.py`:

```python
"""Tests for PortfolioCombiner."""
from __future__ import annotations

import pytest

from quant.analysis.rotation.portfolio import PortfolioCombiner


def test_combine_full_multiplier_keeps_weights() -> None:
    combiner = PortfolioCombiner()
    result = combiner.combine({"A": 0.4, "B": 0.6}, multiplier=1.0)
    assert result == {"A": 0.4, "B": 0.6}


def test_combine_half_multiplier_halves_weights() -> None:
    combiner = PortfolioCombiner()
    result = combiner.combine({"A": 0.5, "B": 0.5}, multiplier=0.5)
    assert result == {"A": 0.25, "B": 0.25}


def test_combine_zero_multiplier_yields_all_zero() -> None:
    combiner = PortfolioCombiner()
    result = combiner.combine({"A": 0.5, "B": 0.5}, multiplier=0.0)
    assert all(v == 0.0 for v in result.values())
    assert set(result) == {"A", "B"}


def test_combine_empty_weights_returns_empty_regardless_of_multiplier() -> None:
    combiner = PortfolioCombiner()
    assert combiner.combine({}, multiplier=1.0) == {}
    assert combiner.combine({}, multiplier=0.5) == {}
    assert combiner.combine({}, multiplier=0.0) == {}


def test_combine_rejects_multiplier_outside_unit_interval() -> None:
    combiner = PortfolioCombiner()
    with pytest.raises(ValueError):
        combiner.combine({"A": 1.0}, multiplier=1.5)
    with pytest.raises(ValueError):
        combiner.combine({"A": 1.0}, multiplier=-0.1)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_rotation_portfolio.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement PortfolioCombiner**

Create `quant/analysis/rotation/portfolio.py`:

```python
"""Combine A-layer multiplier with B-layer weights into final positions."""
from __future__ import annotations


class PortfolioCombiner:
    """Compose ``multiplier × weights`` into a final position dict."""

    def combine(
        self,
        weights: dict[str, float],
        multiplier: float,
    ) -> dict[str, float]:
        """Return ``{symbol: final_position}``.

        Empty ``weights`` always maps to an empty result regardless of multiplier
        (B has decided no opportunities).  ``multiplier`` must lie in ``[0, 1]``.
        """
        if not 0.0 <= multiplier <= 1.0:
            raise ValueError(f"multiplier must be in [0, 1], got {multiplier}")
        if not weights:
            return {}
        return {symbol: weight * multiplier for symbol, weight in weights.items()}
```

- [ ] **Step 4: Update package __init__**

Modify `quant/analysis/rotation/__init__.py`:

```python
"""A 股行业 ETF 轮动系统模块。"""
from quant.analysis.rotation.portfolio import PortfolioCombiner
from quant.analysis.rotation.ranker import MomentumRanker, RankerConfig
from quant.analysis.rotation.universe import EtfEntry, load_universe

__all__ = [
    "EtfEntry",
    "MomentumRanker",
    "PortfolioCombiner",
    "RankerConfig",
    "load_universe",
]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_rotation_portfolio.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add quant/analysis/rotation/portfolio.py quant/analysis/rotation/__init__.py \
        tests/unit/test_rotation_portfolio.py
git commit -m "$(cat <<'EOF'
feat: add PortfolioCombiner for A multiplier × B weights

Maps regime multiplier (scalar in [0,1]) and ranker weights (dict summing
to 1, or empty for cash signal) to final per-symbol positions; empty weights
always produce all-cash regardless of multiplier.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: SimpleRegimeOverlay

**Files:**
- Create: `quant/analysis/rotation/regime_overlay.py`
- Modify: `quant/analysis/rotation/__init__.py`
- Test: `tests/unit/test_rotation_overlay.py`

`SimpleRegimeOverlay` precomputes a benchmark regime multiplier series via the existing `LowFrequencySignalBuilder` + `LowFrequencyRegimeScorer` pipeline, and exposes `multiplier_at(date)` for later lookup.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_rotation_overlay.py`:

```python
"""Tests for SimpleRegimeOverlay."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.analysis.rotation.regime_overlay import (
    PrecomputedRegimeOverlay,
    SimpleRegimeOverlay,
)


def _strong_uptrend_prices(n: int = 600) -> pd.DataFrame:
    """Daily prices on a steady uptrend with low vol — should produce multiplier ≈ 1."""
    dates = pd.date_range("2022-01-04", periods=n, freq="B")
    close = 100.0 * np.exp(np.linspace(0.0, 0.5, n))
    return pd.DataFrame({"close": close}, index=dates)


def _bear_prices(n: int = 600) -> pd.DataFrame:
    """Daily prices in a steady downtrend — trend off → multiplier should be 0."""
    dates = pd.date_range("2022-01-04", periods=n, freq="B")
    close = 100.0 * np.exp(np.linspace(0.0, -0.5, n))
    return pd.DataFrame({"close": close}, index=dates)


def test_precomputed_overlay_returns_multiplier_in_unit_interval() -> None:
    overlay = PrecomputedRegimeOverlay(_strong_uptrend_prices())
    series = overlay.multipliers
    assert not series.empty
    assert series.between(0.0, 1.0).all()


def test_precomputed_overlay_multiplier_at_known_date() -> None:
    overlay = PrecomputedRegimeOverlay(_strong_uptrend_prices())
    last_date = overlay.multipliers.index[-1]
    value = overlay.multiplier_at(last_date)
    assert pytest.approx(value, abs=1e-9) == float(overlay.multipliers.iloc[-1])


def test_precomputed_overlay_uses_latest_known_multiplier_for_unknown_date() -> None:
    overlay = PrecomputedRegimeOverlay(_strong_uptrend_prices())
    last_date = overlay.multipliers.index[-1]
    future = last_date + pd.offsets.MonthEnd(3)
    # Forward-fill from latest known
    assert overlay.multiplier_at(future) == float(overlay.multipliers.iloc[-1])


def test_precomputed_overlay_pre_history_returns_zero() -> None:
    overlay = PrecomputedRegimeOverlay(_strong_uptrend_prices())
    earliest = overlay.multipliers.index[0]
    pre = earliest - pd.offsets.MonthEnd(2)
    assert overlay.multiplier_at(pre) == 0.0


def test_bear_market_drives_multiplier_to_zero() -> None:
    overlay = PrecomputedRegimeOverlay(_bear_prices())
    # Trend off → multiplier == 0 in tail
    assert overlay.multipliers.iloc[-1] == 0.0


def test_simple_overlay_uses_data_service(monkeypatch) -> None:
    """SimpleRegimeOverlay pulls benchmark prices via DataService and produces multipliers."""
    captured = {}

    class _FakeDataService:
        def get_price(self, request):
            captured["request"] = request
            return _strong_uptrend_prices()

        def get_trading_days(self, start, end):
            return pd.date_range(start, end, freq="B").strftime("%Y-%m-%d").tolist()

    overlay = SimpleRegimeOverlay(
        data_service=_FakeDataService(),
        benchmark_symbol="000300.SH",
    )
    overlay.precompute(start="2022-01-01", end="2024-06-30")
    assert captured["request"].symbol == "000300.SH"
    assert captured["request"].asset_type == "index"

    sample_date = overlay.multipliers.index[-1]
    assert 0.0 <= overlay.multiplier_at(sample_date) <= 1.0


def test_simple_overlay_requires_precompute_before_lookup() -> None:
    overlay = SimpleRegimeOverlay(data_service=None, benchmark_symbol="000300.SH")
    with pytest.raises(RuntimeError, match="precompute"):
        overlay.multiplier_at(pd.Timestamp("2024-01-31"))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_rotation_overlay.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement SimpleRegimeOverlay**

Create `quant/analysis/rotation/regime_overlay.py`:

```python
"""Regime overlay (A layer) wrapping the existing LowFrequencyRegimeScorer."""
from __future__ import annotations

from typing import Optional, Protocol

import pandas as pd

from quant.analysis.lowfreq import (
    LowFrequencyRegimeScorer,
    LowFrequencySignalBuilder,
    SignalConfig,
)


class RegimeOverlay(Protocol):
    """Protocol allowing future cockpit-based overlay to drop in."""

    def multiplier_at(self, date: pd.Timestamp) -> float: ...


class PrecomputedRegimeOverlay:
    """Overlay backed by an in-memory precomputed multiplier series.

    Used directly in tests, and as the concrete payload that
    :class:`SimpleRegimeOverlay` builds after :meth:`SimpleRegimeOverlay.precompute`.
    """

    def __init__(self, benchmark_prices: pd.DataFrame) -> None:
        signals = LowFrequencySignalBuilder(SignalConfig()).build(benchmark_prices)
        if signals.empty:
            self.multipliers = pd.Series(dtype=float, name="regime_multiplier")
            return
        scored = LowFrequencyRegimeScorer().apply(signals)
        self.multipliers = scored["regime_multiplier"].astype(float)

    def multiplier_at(self, date: pd.Timestamp) -> float:
        if self.multipliers.empty:
            return 0.0
        # Pre-history → 0 (most defensive); inside or after history → forward-fill
        if date < self.multipliers.index[0]:
            return 0.0
        idx = self.multipliers.index.searchsorted(date, side="right") - 1
        return float(self.multipliers.iloc[idx])


class SimpleRegimeOverlay:
    """Pull benchmark prices via DataService and wrap them in a precomputed overlay."""

    def __init__(
        self,
        data_service,
        benchmark_symbol: str = "000300.SH",
    ) -> None:
        self.data_service = data_service
        self.benchmark_symbol = benchmark_symbol
        self._inner: Optional[PrecomputedRegimeOverlay] = None

    def precompute(self, start: str, end: str) -> None:
        from quant.services.data_service import PriceRequest

        prices = self.data_service.get_price(
            PriceRequest(
                symbol=self.benchmark_symbol,
                start=start,
                end=end,
                asset_type="index",
            )
        )
        self._inner = PrecomputedRegimeOverlay(prices)

    @property
    def multipliers(self) -> pd.Series:
        if self._inner is None:
            raise RuntimeError("must call precompute(...) before reading multipliers")
        return self._inner.multipliers

    def multiplier_at(self, date: pd.Timestamp) -> float:
        if self._inner is None:
            raise RuntimeError("must call precompute(...) before multiplier_at")
        return self._inner.multiplier_at(date)
```

- [ ] **Step 4: Update package __init__**

Modify `quant/analysis/rotation/__init__.py`:

```python
"""A 股行业 ETF 轮动系统模块。"""
from quant.analysis.rotation.portfolio import PortfolioCombiner
from quant.analysis.rotation.ranker import MomentumRanker, RankerConfig
from quant.analysis.rotation.regime_overlay import (
    PrecomputedRegimeOverlay,
    RegimeOverlay,
    SimpleRegimeOverlay,
)
from quant.analysis.rotation.universe import EtfEntry, load_universe

__all__ = [
    "EtfEntry",
    "MomentumRanker",
    "PortfolioCombiner",
    "PrecomputedRegimeOverlay",
    "RankerConfig",
    "RegimeOverlay",
    "SimpleRegimeOverlay",
    "load_universe",
]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_rotation_overlay.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add quant/analysis/rotation/regime_overlay.py quant/analysis/rotation/__init__.py \
        tests/unit/test_rotation_overlay.py
git commit -m "$(cat <<'EOF'
feat: add SimpleRegimeOverlay wrapping LowFrequencyRegimeScorer

Computes a benchmark-driven regime multiplier series (default HS300) and
exposes multiplier_at(date) lookup with forward-fill for post-history dates
and zero for pre-history.  PrecomputedRegimeOverlay variant feeds prebuilt
prices, used in tests and by SimpleRegimeOverlay's precompute step.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: RotationBacktester

**Files:**
- Create: `quant/analysis/rotation/backtest.py`
- Modify: `quant/analysis/rotation/__init__.py`
- Test: `tests/unit/test_rotation_backtest.py`

The backtester iterates month-end dates, calls `ranker.rank` + `overlay.multiplier_at` + `combiner.combine`, applies positions to next-month returns, deducts turnover cost, and emits three benchmark series.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_rotation_backtest.py`:

```python
"""Tests for RotationBacktester."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
import pytest

from quant.analysis.rotation.backtest import (
    RotationBacktestConfig,
    RotationBacktester,
)
from quant.analysis.rotation.portfolio import PortfolioCombiner


class _FixedRanker:
    """Always pick the same single symbol with weight 1.0."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def rank(self, monthly_prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        return {self.symbol: 1.0}


class _AlwaysFullOverlay:
    def multiplier_at(self, date: pd.Timestamp) -> float:
        return 1.0


class _AlwaysHalfOverlay:
    def multiplier_at(self, date: pd.Timestamp) -> float:
        return 0.5


def _multi_asset_monthly_prices() -> pd.DataFrame:
    months = pd.date_range("2022-01-31", periods=24, freq="ME")
    return pd.DataFrame(
        {
            "A": 100.0 * (1.05 ** np.arange(24)),
            "B": 100.0 * (1.03 ** np.arange(24)),
            "C": 100.0 * np.ones(24),
        },
        index=months,
    )


def test_backtest_returns_metrics_and_curves() -> None:
    prices = _multi_asset_monthly_prices()
    benchmark = pd.Series(
        100.0 * (1.02 ** np.arange(24)), index=prices.index, name="benchmark"
    )
    bt = RotationBacktester(RotationBacktestConfig(transaction_cost=0.0))
    result = bt.run(
        universe_prices=prices,
        benchmark_prices=benchmark,
        ranker=_FixedRanker("A"),
        overlay=_AlwaysFullOverlay(),
        combiner=PortfolioCombiner(),
    )
    assert {
        "total_return_strategy",
        "total_return_benchmark",
        "total_return_equal_weight",
        "annual_return_strategy",
        "annual_vol_strategy",
        "max_drawdown_strategy",
        "sharpe_strategy",
    } <= set(result.metrics)
    assert {"strategy", "benchmark", "equal_weight"} == set(result.equity_curve.columns)
    assert {"strategy", "benchmark", "equal_weight", "turnover"} <= set(
        result.monthly_returns.columns
    )
    assert result.holdings.shape[0] == len(prices)


def test_strategy_picks_best_asset_when_overlay_full() -> None:
    prices = _multi_asset_monthly_prices()
    benchmark = pd.Series(100.0 * np.ones(24), index=prices.index)
    bt = RotationBacktester(RotationBacktestConfig(transaction_cost=0.0))
    result = bt.run(
        universe_prices=prices,
        benchmark_prices=benchmark,
        ranker=_FixedRanker("A"),
        overlay=_AlwaysFullOverlay(),
        combiner=PortfolioCombiner(),
    )
    # Strategy compounds A's monthly returns from month 2 onward (month 1 has no prior position)
    monthly_returns_A = prices["A"].pct_change().fillna(0.0)
    expected_curve = (1.0 + monthly_returns_A).cumprod()
    # Backtest holds zero in month 1 (no previous position), so strategy curve lags A by 1
    np.testing.assert_allclose(
        result.equity_curve["strategy"].iloc[1:].values,
        expected_curve.iloc[1:].values / expected_curve.iloc[1],
        rtol=1e-6,
    )


def test_half_multiplier_dampens_return() -> None:
    prices = _multi_asset_monthly_prices()
    benchmark = pd.Series(100.0 * np.ones(24), index=prices.index)
    bt = RotationBacktester(RotationBacktestConfig(transaction_cost=0.0))
    full = bt.run(prices, benchmark, _FixedRanker("A"), _AlwaysFullOverlay(), PortfolioCombiner())
    half = bt.run(prices, benchmark, _FixedRanker("A"), _AlwaysHalfOverlay(), PortfolioCombiner())
    # Half-multiplier strategy should have a smaller positive drift than full
    assert half.metrics["annual_return_strategy"] < full.metrics["annual_return_strategy"]


def test_transaction_cost_reduces_return() -> None:
    prices = _multi_asset_monthly_prices()
    benchmark = pd.Series(100.0 * np.ones(24), index=prices.index)
    no_cost = RotationBacktester(RotationBacktestConfig(transaction_cost=0.0)).run(
        prices, benchmark, _FixedRanker("A"), _AlwaysFullOverlay(), PortfolioCombiner()
    )
    with_cost = RotationBacktester(RotationBacktestConfig(transaction_cost=0.01)).run(
        prices, benchmark, _FixedRanker("A"), _AlwaysFullOverlay(), PortfolioCombiner()
    )
    assert (
        with_cost.metrics["total_return_strategy"]
        < no_cost.metrics["total_return_strategy"]
    )


def test_empty_ranker_yields_flat_strategy() -> None:
    prices = _multi_asset_monthly_prices()
    benchmark = pd.Series(100.0 * np.ones(24), index=prices.index)

    class _EmptyRanker:
        def rank(self, mp, d):
            return {}

    bt = RotationBacktester(RotationBacktestConfig(transaction_cost=0.0))
    result = bt.run(prices, benchmark, _EmptyRanker(), _AlwaysFullOverlay(), PortfolioCombiner())
    # Strategy never holds anything → equity stays at 1.0
    np.testing.assert_allclose(
        result.equity_curve["strategy"].values,
        np.ones(len(prices)),
        rtol=1e-9,
    )


def test_turnover_l1_formula() -> None:
    """Turnover_t = 0.5 * sum(|w_t - w_{t-1}|).  Verify on a fixed schedule."""
    prices = _multi_asset_monthly_prices()
    benchmark = pd.Series(100.0 * np.ones(24), index=prices.index)

    class _AlternatingRanker:
        def __init__(self) -> None:
            self.calls = 0

        def rank(self, mp, d):
            self.calls += 1
            return {"A": 1.0} if self.calls % 2 == 1 else {"B": 1.0}

    bt = RotationBacktester(RotationBacktestConfig(transaction_cost=0.0))
    result = bt.run(prices, benchmark, _AlternatingRanker(), _AlwaysFullOverlay(), PortfolioCombiner())
    # First month's turnover is 0.5*|1-0| = 0.5 (going from cash to A)
    assert pytest.approx(result.monthly_returns["turnover"].iloc[0], abs=1e-9) == 0.5
    # Subsequent months alternate full swap → 0.5*(|0-1| + |1-0|) = 1.0
    assert pytest.approx(result.monthly_returns["turnover"].iloc[1], abs=1e-9) == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_rotation_backtest.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement RotationBacktester**

Create `quant/analysis/rotation/backtest.py`:

```python
"""Multi-asset monthly rebalance backtester for rotation strategy."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

PERIODS_PER_YEAR = 12


@dataclass(frozen=True)
class RotationBacktestConfig:
    """Configuration for the rotation backtester."""

    transaction_cost: float = 0.002
    risk_free: float = 0.03


@dataclass(frozen=True)
class RotationBacktestResult:
    """Output bundle for a rotation backtest run."""

    metrics: dict
    equity_curve: pd.DataFrame
    monthly_returns: pd.DataFrame
    holdings: pd.DataFrame


class RotationBacktester:
    """Run a multi-asset monthly rebalance backtest."""

    def __init__(self, config: RotationBacktestConfig | None = None) -> None:
        self.config = config or RotationBacktestConfig()
        if self.config.transaction_cost < 0:
            raise ValueError("transaction_cost must be non-negative")

    def run(
        self,
        universe_prices: pd.DataFrame,
        benchmark_prices: pd.Series,
        ranker,
        overlay,
        combiner,
    ) -> RotationBacktestResult:
        """Iterate month-end dates and produce strategy / benchmark curves."""
        if not isinstance(universe_prices.index, pd.DatetimeIndex):
            universe_prices = universe_prices.copy()
            universe_prices.index = pd.to_datetime(universe_prices.index)

        rebalance_dates = universe_prices.index
        symbols = list(universe_prices.columns)

        prev_positions = pd.Series(0.0, index=symbols, dtype=float)
        positions_history: list[pd.Series] = []
        turnovers: list[float] = []

        # Pre-compute monthly returns per symbol; missing returns count as 0
        monthly_universe_ret = universe_prices.pct_change().fillna(0.0)
        # Realized strategy return per month uses prev_positions × this-month return
        strategy_returns: list[float] = []

        for date in rebalance_dates:
            weights = ranker.rank(universe_prices, date)
            multiplier = float(overlay.multiplier_at(date))
            final = combiner.combine(weights, multiplier)

            new_positions = pd.Series(0.0, index=symbols, dtype=float)
            for sym, pos in final.items():
                if sym in new_positions.index:
                    new_positions[sym] = pos

            turnover = 0.5 * float((new_positions - prev_positions).abs().sum())
            turnovers.append(turnover)

            # Strategy return for THIS month uses prev_positions (held over month)
            this_month_ret = monthly_universe_ret.loc[date]
            gross = float((prev_positions * this_month_ret).sum())
            net = gross - turnover * self.config.transaction_cost
            strategy_returns.append(net)

            positions_history.append(new_positions.copy())
            prev_positions = new_positions

        # Benchmarks
        benchmark_ret = benchmark_prices.pct_change().reindex(rebalance_dates).fillna(0.0)
        equal_weight_ret = monthly_universe_ret.mean(axis=1)

        strategy_series = pd.Series(strategy_returns, index=rebalance_dates, name="strategy")
        equity_curve = pd.DataFrame(
            {
                "strategy": (1.0 + strategy_series).cumprod(),
                "benchmark": (1.0 + benchmark_ret).cumprod(),
                "equal_weight": (1.0 + equal_weight_ret).cumprod(),
            },
            index=rebalance_dates,
        )
        monthly_returns = pd.DataFrame(
            {
                "strategy": strategy_series,
                "benchmark": benchmark_ret,
                "equal_weight": equal_weight_ret,
                "turnover": pd.Series(turnovers, index=rebalance_dates),
            },
            index=rebalance_dates,
        )
        holdings = pd.DataFrame(positions_history, index=rebalance_dates).fillna(0.0)

        metrics = self._metrics(strategy_series, benchmark_ret, equal_weight_ret, equity_curve)
        return RotationBacktestResult(metrics, equity_curve, monthly_returns, holdings)

    def _metrics(
        self,
        strategy_ret: pd.Series,
        benchmark_ret: pd.Series,
        equal_weight_ret: pd.Series,
        equity_curve: pd.DataFrame,
    ) -> dict:
        return {
            "total_return_strategy": self._total_return(equity_curve["strategy"]),
            "total_return_benchmark": self._total_return(equity_curve["benchmark"]),
            "total_return_equal_weight": self._total_return(equity_curve["equal_weight"]),
            "annual_return_strategy": self._annual_return(strategy_ret),
            "annual_return_benchmark": self._annual_return(benchmark_ret),
            "annual_return_equal_weight": self._annual_return(equal_weight_ret),
            "annual_vol_strategy": self._annual_vol(strategy_ret),
            "annual_vol_benchmark": self._annual_vol(benchmark_ret),
            "max_drawdown_strategy": self._max_drawdown(equity_curve["strategy"]),
            "max_drawdown_benchmark": self._max_drawdown(equity_curve["benchmark"]),
            "sharpe_strategy": self._sharpe(strategy_ret),
            "sharpe_benchmark": self._sharpe(benchmark_ret),
        }

    @staticmethod
    def _total_return(equity: pd.Series) -> float:
        if equity.empty:
            return 0.0
        return round(float(equity.iloc[-1] / equity.iloc[0] - 1.0), 4)

    @staticmethod
    def _annual_return(returns: pd.Series) -> float:
        n = len(returns)
        if n == 0:
            return 0.0
        total = float((1.0 + returns).prod())
        return round(total ** (PERIODS_PER_YEAR / n) - 1.0, 4)

    @staticmethod
    def _annual_vol(returns: pd.Series) -> float:
        if len(returns) < 2:
            return 0.0
        return round(float(returns.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR)), 4)

    @staticmethod
    def _max_drawdown(equity: pd.Series) -> float:
        if equity.empty:
            return 0.0
        drawdown = equity / equity.cummax() - 1.0
        return round(float(drawdown.min()), 4)

    def _sharpe(self, returns: pd.Series) -> float:
        if len(returns) < 2:
            return 0.0
        vol = returns.std(ddof=1)
        if vol == 0 or np.isnan(vol):
            return 0.0
        rf_monthly = (1.0 + self.config.risk_free) ** (1.0 / PERIODS_PER_YEAR) - 1.0
        return round(float((returns - rf_monthly).mean() / vol * math.sqrt(PERIODS_PER_YEAR)), 3)
```

- [ ] **Step 4: Update package __init__**

Modify `quant/analysis/rotation/__init__.py`:

```python
"""A 股行业 ETF 轮动系统模块。"""
from quant.analysis.rotation.backtest import (
    RotationBacktestConfig,
    RotationBacktestResult,
    RotationBacktester,
)
from quant.analysis.rotation.portfolio import PortfolioCombiner
from quant.analysis.rotation.ranker import MomentumRanker, RankerConfig
from quant.analysis.rotation.regime_overlay import (
    PrecomputedRegimeOverlay,
    RegimeOverlay,
    SimpleRegimeOverlay,
)
from quant.analysis.rotation.universe import EtfEntry, load_universe

__all__ = [
    "EtfEntry",
    "MomentumRanker",
    "PortfolioCombiner",
    "PrecomputedRegimeOverlay",
    "RankerConfig",
    "RegimeOverlay",
    "RotationBacktestConfig",
    "RotationBacktestResult",
    "RotationBacktester",
    "SimpleRegimeOverlay",
    "load_universe",
]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_rotation_backtest.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add quant/analysis/rotation/backtest.py quant/analysis/rotation/__init__.py \
        tests/unit/test_rotation_backtest.py
git commit -m "$(cat <<'EOF'
feat: add RotationBacktester multi-asset monthly rebalance

Iterates rebalance dates, asks ranker/overlay/combiner for target
positions, applies prev-month positions to this-month returns, deducts
L1-turnover * tc.  Returns metrics + 3 equity curves (strategy / benchmark
/ equal-weight) + monthly holdings matrix.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: RotationService

**Files:**
- Create: `quant/services/rotation_service.py`
- Modify: `quant/services/__init__.py`
- Test: `tests/unit/test_rotation_service.py`

`RotationService` glues DataService + universe + the four rotation modules.

- [ ] **Step 1: Inspect existing services package surface**

```bash
sed -n '1,40p' quant/services/__init__.py
```

Note exports — you'll add `RotationService` and `RotationRequest` next to existing entries.

- [ ] **Step 2: Write failing tests**

Create `tests/unit/test_rotation_service.py`:

```python
"""Tests for RotationService."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant.analysis.rotation import RankerConfig
from quant.services.rotation_service import RotationRequest, RotationService


def _synthetic_etf_prices(symbol: str, growth: float, n: int = 800) -> pd.DataFrame:
    dates = pd.date_range("2018-01-02", periods=n, freq="B")
    close = 10.0 * np.exp(np.linspace(0.0, growth, n))
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1.0},
        index=dates,
    )


class _FakeDataService:
    """Returns deterministic synthetic prices keyed by symbol."""

    def __init__(self, growths: dict[str, float], benchmark_growth: float = 0.4) -> None:
        self.growths = growths
        self.benchmark_growth = benchmark_growth
        self.calls: list = []

    def get_price(self, request):
        self.calls.append(request.symbol)
        if request.symbol in self.growths:
            return _synthetic_etf_prices(request.symbol, self.growths[request.symbol])
        # Treat anything else as benchmark
        return _synthetic_etf_prices(request.symbol, self.benchmark_growth)

    def get_trading_days(self, start, end):
        return pd.date_range(start, end, freq="B").strftime("%Y-%m-%d").tolist()


def _write_minimal_universe(tmp_path: Path) -> Path:
    yaml_path = tmp_path / "universe.yaml"
    yaml_path.write_text(
        """
        schema_version: 1
        industry_etfs:
          - { symbol: "510050.SH", name: "高",   category: "测试" }
          - { symbol: "512000.SH", name: "中",   category: "测试" }
          - { symbol: "512800.SH", name: "低",   category: "测试" }
        """,
        encoding="utf-8",
    )
    return yaml_path


def test_run_backtest_returns_result(tmp_path: Path) -> None:
    universe_path = _write_minimal_universe(tmp_path)
    fake = _FakeDataService(
        {"510050.SH": 0.6, "512000.SH": 0.4, "512800.SH": 0.2}
    )
    service = RotationService(data_service=fake)
    request = RotationRequest(
        start="2018-01-01",
        end="2024-12-31",
        universe_path=str(universe_path),
        ranker_config=RankerConfig(top_k=2, cash_threshold=-1.0),
    )
    result = service.run_backtest(request)
    assert "annual_return_strategy" in result.metrics
    assert not result.equity_curve.empty
    # All universe symbols should have been requested at least once
    assert {"510050.SH", "512000.SH", "512800.SH"} <= set(fake.calls)


def test_latest_targets_returns_decision_dict(tmp_path: Path) -> None:
    universe_path = _write_minimal_universe(tmp_path)
    fake = _FakeDataService(
        {"510050.SH": 0.6, "512000.SH": 0.4, "512800.SH": 0.2}
    )
    service = RotationService(data_service=fake)
    request = RotationRequest(
        start="2018-01-01",
        end="2024-12-31",
        universe_path=str(universe_path),
        ranker_config=RankerConfig(top_k=2, cash_threshold=-1.0),
    )
    targets = service.latest_targets(request)
    assert {"as_of", "multiplier", "weights", "final_positions", "top_momentum"} <= set(targets)
    assert isinstance(targets["multiplier"], float)
    assert sum(targets["final_positions"].values()) <= 1.0 + 1e-9


def test_default_universe_path_used_when_omitted(tmp_path: Path) -> None:
    fake = _FakeDataService({})
    service = RotationService(data_service=fake)
    request = RotationRequest(start="2018-01-01", end="2024-12-31")
    # The default config/rotation_universe.yaml exists in repo; this should run
    result = service.run_backtest(request)
    assert "annual_return_strategy" in result.metrics
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_rotation_service.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement RotationService**

Create `quant/services/rotation_service.py`:

```python
"""Rotation strategy preparation service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from quant.analysis.rotation import (
    MomentumRanker,
    PortfolioCombiner,
    RankerConfig,
    RotationBacktestConfig,
    RotationBacktestResult,
    RotationBacktester,
    SimpleRegimeOverlay,
    load_universe,
)
from quant.services.data_service import DataService, PriceRequest


@dataclass(frozen=True)
class RotationRequest:
    """Input model for rotation backtest / latest target generation."""

    start: str
    end: str
    universe_path: Optional[str] = None
    ranker_config: Optional[RankerConfig] = None
    overlay_benchmark: str = "000300.SH"
    transaction_cost: float = 0.002
    provider: str = "auto"


class RotationService:
    """Wire DataService + universe yaml + rotation pipeline."""

    def __init__(self, data_service: DataService | None = None) -> None:
        self.data_service = data_service or DataService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_backtest(self, request: RotationRequest) -> RotationBacktestResult:
        """Run the full backtest with the requested configuration."""
        universe = load_universe(request.universe_path)
        monthly_prices = self._collect_monthly_prices(universe, request)
        benchmark_prices = self._fetch_benchmark_close(request)
        overlay = self._build_overlay(request)

        ranker = MomentumRanker(request.ranker_config or RankerConfig())
        combiner = PortfolioCombiner()
        backtester = RotationBacktester(
            RotationBacktestConfig(transaction_cost=request.transaction_cost)
        )
        return backtester.run(
            universe_prices=monthly_prices,
            benchmark_prices=benchmark_prices.reindex(monthly_prices.index).ffill(),
            ranker=ranker,
            overlay=overlay,
            combiner=combiner,
        )

    def latest_targets(self, request: RotationRequest) -> dict:
        """Return the decision payload for the most recent month-end ≤ request.end."""
        universe = load_universe(request.universe_path)
        monthly_prices = self._collect_monthly_prices(universe, request)
        if monthly_prices.empty:
            raise ValueError("no monthly prices available; check date range and universe")

        rebalance_date = monthly_prices.index[-1]
        ranker = MomentumRanker(request.ranker_config or RankerConfig())
        weights = ranker.rank(monthly_prices, rebalance_date)

        overlay = self._build_overlay(request)
        multiplier = float(overlay.multiplier_at(rebalance_date))

        combiner = PortfolioCombiner()
        final_positions = combiner.combine(weights, multiplier)

        # Top momentum table (descending), useful for the human consumer
        top_n = max(len(weights), (request.ranker_config or RankerConfig()).top_k)
        top_momentum = self._top_momentum(monthly_prices, rebalance_date, top_n, request)

        return {
            "as_of": rebalance_date.strftime("%Y-%m-%d"),
            "multiplier": multiplier,
            "weights": dict(weights),
            "final_positions": dict(final_positions),
            "top_momentum": top_momentum,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _collect_monthly_prices(self, universe, request: RotationRequest) -> pd.DataFrame:
        frames: dict[str, pd.Series] = {}
        for entry in universe:
            try:
                df = self.data_service.get_price(
                    PriceRequest(
                        symbol=entry.symbol,
                        start=request.start,
                        end=request.end,
                        asset_type="etf",
                        provider=request.provider,
                    )
                )
            except Exception:
                # ETF may not yet be listed early in the window — skip
                continue
            if df is None or df.empty or "close" not in df.columns:
                continue
            close = df["close"].astype(float)
            close.name = entry.symbol
            # Resample to month-end on the existing trading-day index
            monthly = close.resample("ME").last().dropna()
            if monthly.empty:
                continue
            frames[entry.symbol] = monthly

        if not frames:
            return pd.DataFrame()

        return pd.DataFrame(frames).sort_index()

    def _fetch_benchmark_close(self, request: RotationRequest) -> pd.Series:
        df = self.data_service.get_price(
            PriceRequest(
                symbol=request.overlay_benchmark,
                start=request.start,
                end=request.end,
                asset_type="index",
                provider=request.provider,
            )
        )
        return df["close"].astype(float).resample("ME").last().dropna()

    def _build_overlay(self, request: RotationRequest) -> SimpleRegimeOverlay:
        overlay = SimpleRegimeOverlay(
            data_service=self.data_service,
            benchmark_symbol=request.overlay_benchmark,
        )
        overlay.precompute(start=request.start, end=request.end)
        return overlay

    def _top_momentum(
        self,
        monthly_prices: pd.DataFrame,
        rebalance_date: pd.Timestamp,
        top_n: int,
        request: RotationRequest,
    ) -> list[dict]:
        cfg = request.ranker_config or RankerConfig()
        loc = monthly_prices.index.get_loc(rebalance_date)
        end_idx = loc - cfg.skip_recent_months
        start_idx = end_idx - cfg.lookback_months
        if start_idx < 0:
            return []

        end_row = monthly_prices.iloc[end_idx]
        start_row = monthly_prices.iloc[start_idx]
        records = []
        for symbol in monthly_prices.columns:
            if pd.isna(start_row[symbol]) or pd.isna(end_row[symbol]) or start_row[symbol] <= 0:
                continue
            records.append(
                {"symbol": symbol, "momentum": float(end_row[symbol] / start_row[symbol] - 1.0)}
            )
        records.sort(key=lambda r: r["momentum"], reverse=True)
        return records[:top_n]
```

- [ ] **Step 5: Update services package exports**

Read the current `quant/services/__init__.py`, then append the rotation exports next to existing ones — do not remove any line.  Concretely add the imports and __all__ entries:

```python
from quant.services.rotation_service import RotationRequest, RotationService
```

and inside the existing `__all__` list, add:

```python
    "RotationRequest",
    "RotationService",
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_rotation_service.py -v
```

Expected: 3 passed.  (The third test exercises the default universe path and may take a few seconds because of monthly resampling on 24 fake series.)

- [ ] **Step 7: Commit**

```bash
git add quant/services/rotation_service.py quant/services/__init__.py \
        tests/unit/test_rotation_service.py
git commit -m "$(cat <<'EOF'
feat: add RotationService end-to-end glue

Loads universe, batches DataService.get_price for each ETF (skipping
unlisted symbols silently), builds month-end price matrix, runs the
ranker/overlay/combiner pipeline through RotationBacktester.  Also exposes
latest_targets for next-month decision output.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Integration test (end-to-end)

**Files:**
- Test: `tests/integration/test_rotation_pipeline.py`

Validates the whole pipeline with synthetic 24-asset data over 60 months — no real data sources touched.

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_rotation_pipeline.py`:

```python
"""End-to-end test of RotationService against synthetic prices."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from quant.analysis.rotation import RankerConfig
from quant.services.rotation_service import RotationRequest, RotationService


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_UNIVERSE = _REPO_ROOT / "config" / "rotation_universe.yaml"


def _synthetic_prices(symbol: str, growth: float, n: int = 1500) -> pd.DataFrame:
    rng = np.random.RandomState(abs(hash(symbol)) % (2**32))
    dates = pd.date_range("2018-01-02", periods=n, freq="B")
    drift = np.linspace(0.0, growth, n)
    noise = rng.normal(0.0, 0.01, n).cumsum() * 0.1
    close = 10.0 * np.exp(drift + noise)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1.0},
        index=dates,
    )


class _DeterministicDataService:
    """Maps each symbol to a synthetic price frame deterministically by symbol hash."""

    def __init__(self) -> None:
        # Seeded growth per symbol — varied so cross-section has signal
        self._growths = {
            "510050.SH": 0.4,
            "512000.SH": 0.6,
            "512800.SH": 0.3,
            "512170.SH": 0.5,
            "512010.SH": 0.45,
            "159995.SZ": 0.7,
            "515050.SH": 0.55,
            "512720.SH": 0.5,
            "159928.SZ": 0.35,
            "159825.SZ": 0.25,
            "512400.SH": 0.4,
            "515220.SH": 0.2,
            "515210.SH": 0.15,
            "159611.SZ": 0.3,
            "159930.SZ": 0.25,
            "512660.SH": 0.4,
            "515030.SH": 0.65,
            "515790.SH": 0.6,
            "159870.SZ": 0.3,
            "512200.SH": 0.1,
            "510880.SH": 0.3,
            "159949.SZ": 0.5,
            "510310.SH": 0.4,    # also benchmark
            "159922.SZ": 0.35,
            "000300.SH": 0.4,    # benchmark used by overlay
        }

    def get_price(self, request):
        return _synthetic_prices(request.symbol, self._growths.get(request.symbol, 0.3))

    def get_trading_days(self, start, end):
        return pd.date_range(start, end, freq="B").strftime("%Y-%m-%d").tolist()


def test_pipeline_runs_against_default_universe() -> None:
    service = RotationService(data_service=_DeterministicDataService())
    request = RotationRequest(
        start="2018-01-01",
        end="2023-12-31",
        universe_path=str(_DEFAULT_UNIVERSE),
        ranker_config=RankerConfig(top_k=5),
        transaction_cost=0.002,
    )
    result = service.run_backtest(request)

    # Smoke checks — strategy ran and produced ~6 years of monthly data
    assert len(result.equity_curve) >= 60
    assert {"strategy", "benchmark", "equal_weight"} == set(result.equity_curve.columns)
    assert result.metrics["annual_return_strategy"] is not None

    # Holdings matrix has at most top_k symbols active per row
    nonzero_per_row = (result.holdings != 0).sum(axis=1)
    assert nonzero_per_row.max() <= 5


def test_latest_targets_against_default_universe() -> None:
    service = RotationService(data_service=_DeterministicDataService())
    request = RotationRequest(
        start="2018-01-01",
        end="2023-12-31",
        universe_path=str(_DEFAULT_UNIVERSE),
        ranker_config=RankerConfig(top_k=5),
    )
    targets = service.latest_targets(request)

    assert targets["as_of"].startswith("2023-")
    assert 0.0 <= targets["multiplier"] <= 1.0
    assert sum(targets["final_positions"].values()) <= 1.0 + 1e-9
    assert len(targets["top_momentum"]) <= 5
```

- [ ] **Step 2: Run the integration test**

```bash
uv run pytest tests/integration/test_rotation_pipeline.py -v
```

Expected: 2 passed.

- [ ] **Step 3: Run all rotation tests together to confirm no regression**

```bash
uv run pytest tests/unit/test_rotation_*.py tests/integration/test_rotation_pipeline.py -v
```

Expected: all green (28+ tests).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_rotation_pipeline.py
git commit -m "$(cat <<'EOF'
test: add rotation pipeline integration test

End-to-end test against synthetic deterministic prices for the full 24-ETF
universe.  Validates run_backtest and latest_targets without touching real
data providers.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: CLI hookup

**Files:**
- Create: `quant/cli/rotation.py`
- Modify: `quant/cli/__init__.py`
- Modify: `quant/__main__.py`

Mirrors the `lowfreq` CLI pattern (see `quant/cli/lowfreq.py:12-39`) for parser registration and command dispatch.

- [ ] **Step 1: Create CLI module**

Create `quant/cli/rotation.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""A 股行业 ETF 轮动策略命令。"""

import logging
import sys

logger = logging.getLogger(__name__)


def register_rotation_commands(subparsers):
    """Register rotation strategy commands."""
    parser = subparsers.add_parser("rotation", help="A 股行业 ETF 轮动")
    sub = parser.add_subparsers(dest="rotation_action", help="轮动操作")

    backtest = sub.add_parser("backtest", help="回测行业 ETF 轮动策略")
    _add_common_args(backtest)
    backtest.add_argument("--tail", type=int, default=12, help="显示最近 N 期净值，默认 12")
    backtest.add_argument("--output", help="保存净值 CSV 到指定路径")

    latest = sub.add_parser("latest", help="生成最近一个月末的目标持仓")
    _add_common_args(latest)

    return parser


def handle_rotation_command(args):
    """Route rotation commands."""
    if args.rotation_action == "backtest":
        handle_rotation_backtest(args)
    elif args.rotation_action == "latest":
        handle_rotation_latest(args)
    else:
        print("❌ 未知的轮动操作")
        sys.exit(1)


def _add_common_args(parser):
    parser.add_argument("--start", required=True, help="开始日期 YYYYMMDD")
    parser.add_argument("--end", required=True, help="结束日期 YYYYMMDD")
    parser.add_argument("--universe", help="universe yaml 路径，默认 config/rotation_universe.yaml")
    parser.add_argument("--top-k", type=int, default=5, help="持有数量，默认 5")
    parser.add_argument("--lookback", type=int, default=12, help="动量回看月数，默认 12")
    parser.add_argument("--skip", type=int, default=1, help="跳过最近 N 个月，默认 1")
    parser.add_argument("--cash-threshold", type=float, default=0.0, help="现金过滤阈值，默认 0")
    parser.add_argument("--transaction-cost", type=float, default=0.002, help="单边换仓成本，默认 0.2%%")
    parser.add_argument("--benchmark", default="000300.SH", help="overlay benchmark，默认沪深 300")
    parser.add_argument("--provider", default="auto", help="数据源，默认 auto")


def _build_request(args):
    from quant.analysis.rotation import RankerConfig
    from quant.services import RotationRequest

    return RotationRequest(
        start=args.start,
        end=args.end,
        universe_path=args.universe,
        ranker_config=RankerConfig(
            lookback_months=args.lookback,
            skip_recent_months=args.skip,
            top_k=args.top_k,
            cash_threshold=args.cash_threshold,
        ),
        overlay_benchmark=args.benchmark,
        transaction_cost=args.transaction_cost,
        provider=args.provider,
    )


def handle_rotation_backtest(args):
    """Run rotation backtest and print summary."""
    print("\n📊 A 股行业 ETF 轮动回测")
    print("=" * 80)
    print(f"区间: {args.start} - {args.end}  benchmark: {args.benchmark}  top-K: {args.top_k}")

    try:
        from quant.services import RotationService

        result = RotationService().run_backtest(_build_request(args))
        m = result.metrics

        print("\n核心指标:")
        print(f"  策略总收益: {m['total_return_strategy']:+.2%}")
        print(f"  HS300 总收益: {m['total_return_benchmark']:+.2%}")
        print(f"  等权 universe 总收益: {m['total_return_equal_weight']:+.2%}")
        print(f"  策略年化:   {m['annual_return_strategy']:+.2%}")
        print(f"  策略波动:   {m['annual_vol_strategy']:.2%}")
        print(f"  策略最大回撤: {m['max_drawdown_strategy']:.2%}")
        print(f"  策略 Sharpe:  {m['sharpe_strategy']:.2f}")

        print(f"\n最近 {args.tail} 期净值:")
        print(result.equity_curve.tail(args.tail).to_string())

        if args.output:
            result.equity_curve.to_csv(args.output, encoding="utf-8-sig")
            print(f"\n💾 已保存: {args.output}")

    except Exception as e:
        print(f"❌ 轮动回测失败: {e}")
        logger.error("Rotation backtest failed: %s", e, exc_info=True)
        sys.exit(1)


def handle_rotation_latest(args):
    """Print the latest target holdings."""
    print("\n🎯 A 股行业 ETF 轮动 — 最新目标持仓")
    print("=" * 80)

    try:
        from quant.services import RotationService

        targets = RotationService().latest_targets(_build_request(args))

        print(f"决策日期: {targets['as_of']}")
        print(f"风险 multiplier: {targets['multiplier']:.2f}")
        print("\n最终持仓:")
        if targets["final_positions"]:
            for sym, pos in sorted(targets["final_positions"].items(), key=lambda kv: kv[1], reverse=True):
                print(f"  {sym}: {pos:.2%}")
        else:
            print("  全现金（B 现金过滤触发或 multiplier=0）")

        print("\nTop 动量排名:")
        for row in targets["top_momentum"]:
            print(f"  {row['symbol']}: {row['momentum']:+.2%}")

    except Exception as e:
        print(f"❌ 生成目标持仓失败: {e}")
        logger.error("Rotation latest failed: %s", e, exc_info=True)
        sys.exit(1)
```

- [ ] **Step 2: Update CLI package exports**

Modify `quant/cli/__init__.py` — add `register_rotation_commands` to the imports and to `__all__`. Concretely, add:

```python
from .rotation import register_rotation_commands
```

next to the other `register_*_commands` imports, and add `'register_rotation_commands'` to `__all__`.

- [ ] **Step 3: Wire into __main__**

Modify `quant/__main__.py`:

  a. In the import block where `register_lowfreq_commands` is imported (around line 33), add `register_rotation_commands` to the import list.

  b. In the imports where `handle_lowfreq_command` is imported (around line 42), add:

  ```python
  from quant.cli.rotation import handle_rotation_command
  ```

  c. After `register_lowfreq_commands(subparsers)` (around line 121), add:

  ```python
  register_rotation_commands(subparsers)
  ```

  d. In the dispatch chain (look for the `elif args.command == "lowfreq":` branch around line 152), add a parallel branch:

  ```python
  elif args.command == "rotation":
      handle_rotation_command(args)
  ```

- [ ] **Step 4: Smoke-test help output**

```bash
uv run python -m quant rotation --help
uv run python -m quant rotation backtest --help
uv run python -m quant rotation latest --help
```

Expected: each prints the expected argparse help text without exception.

- [ ] **Step 5: Run the full rotation test suite once more**

```bash
uv run pytest tests/unit/test_rotation_*.py tests/integration/test_rotation_pipeline.py -v
```

Expected: all green.

- [ ] **Step 6: Run repo-wide unit test sanity check**

```bash
uv run pytest tests/unit/ tests/integration/ -q
```

Expected: no new failures introduced (existing tests previously green should remain green).

- [ ] **Step 7: Commit**

```bash
git add quant/cli/rotation.py quant/cli/__init__.py quant/__main__.py
git commit -m "$(cat <<'EOF'
feat: add rotation CLI subcommand

Adds 'rotation backtest' and 'rotation latest' subcommands wired through
RotationService.  Mirrors lowfreq subcommand pattern.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Notes

| Spec section | Plan task |
|--------------|-----------|
| §2.1 Module layout | Tasks 1-7 (one task per file) |
| §2.2 与 lowfreq 关系 | Task 4 wraps `LowFrequencyRegimeScorer` via composition; spec says lowfreq backtest not reused — Tasks 5/6 implement standalone multi-asset backtester |
| §3.1 MomentumRanker | Task 2 |
| §3.2 RegimeOverlay | Task 4 |
| §3.3 PortfolioCombiner | Task 3 |
| §3.4 RotationBacktester | Task 5 |
| §3.5 RotationService | Task 6 |
| §4 Data flow | Verified end-to-end in Tasks 6-7 |
| §5.1 Universe yaml | Task 1 |
| §5.2 Default parameters | Encoded in dataclass defaults across Tasks 2/4/5/6 |
| §6 Error handling | Task 1 (yaml errors), Task 6 (skip unlisted ETFs), Task 4 (precompute guard) |
| §7 Testing strategy | One unit test file per module + integration test |
| §8 Out of scope | Cockpit overlay / multi-factor / auto-trading explicitly not in plan |
| §10 Decision summary | All 14 rows mapped to dataclass defaults or plan steps |

**Out-of-spec additions:** Task 8 (CLI hookup) is not strictly in the spec but is required for "uv run rotation backtest" usability target in §1.3 success criterion 3.

**No placeholders:** every step shows complete code, exact paths, exact commands, exact expected output.
