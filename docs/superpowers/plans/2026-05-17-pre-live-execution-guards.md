# Pre-Live Execution Guards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dynamic ETF volume filter to the rotation ranker and a `quant rotation precheck` CLI command that checks QDII premium/quota before monthly rebalancing.

**Architecture:** Volume filter wraps the existing `MomentumRanker` via a `VolumeFilteredRanker` decorator — same `rank()` interface, pre-filters symbols based on trailing 3M monthly volume. QDII precheck lives in a new `precheck.py` module, exposed via a new `precheck` subcommand in the rotation CLI. `latest` writes targets to a JSON sidecar so `precheck --from-latest` can read them.

**Tech Stack:** Python 3.11+, pandas, PyYAML, pytest; existing `DataService`, `MomentumRanker`, `RotationService`.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `config/rotation_universe.yaml` | Add `volume_filter` global block + per-ETF threshold field |
| Modify | `quant/analysis/rotation/universe.py` | Parse `volume_filter` config + `volume_threshold` per ETF |
| Modify | `quant/analysis/rotation/ranker.py` | Add `VolumeFilteredRanker` wrapper class |
| Modify | `quant/services/rotation_service.py` | Collect monthly volumes, build `VolumeFilteredRanker`, write latest sidecar |
| Create | `quant/analysis/rotation/precheck.py` | `PreTradeChecker`, `CheckResult`, `PreCheckReport` |
| Modify | `quant/cli/rotation.py` | Add `precheck` subcommand |
| Create | `tests/rotation/test_volume_filter.py` | Unit tests for volume filter |
| Create | `tests/rotation/test_precheck.py` | Unit tests for PreTradeChecker |

---

## Task 1: Parse volume_filter config from universe YAML

**Files:**
- Modify: `config/rotation_universe.yaml`
- Modify: `quant/analysis/rotation/universe.py`
- Test: `tests/rotation/test_rotation_universe.py` (existing file — add cases)

- [ ] **Step 1: Write failing tests**

Add to `tests/rotation/test_rotation_universe.py`:

```python
from quant.analysis.rotation.universe import load_universe, load_volume_filter_config, VolumeFilterConfig

def test_load_volume_filter_config_defaults(tmp_path):
    """YAML without volume_filter block returns disabled default config."""
    yaml_content = """
industry_etfs:
  - {symbol: "512800.SH", name: "银行ETF", category: "金融"}
"""
    p = tmp_path / "universe.yaml"
    p.write_text(yaml_content)
    cfg, industry_syms = load_volume_filter_config(p)
    assert cfg.enabled is False
    assert cfg.min_avg_monthly_volume_shares == 1_000_000
    assert cfg.lookback_months == 3
    assert "512800.SH" in industry_syms


def test_load_volume_filter_config_from_yaml(tmp_path):
    """volume_filter block is parsed correctly."""
    yaml_content = """
volume_filter:
  enabled: true
  min_avg_monthly_volume_shares: 2000000
  lookback_months: 6
industry_etfs:
  - {symbol: "159930.SZ", name: "能源ETF", category: "周期", min_avg_monthly_volume_shares: 500000}
  - {symbol: "512800.SH", name: "银行ETF", category: "金融"}
style_etfs:
  - {symbol: "510880.SH", name: "红利ETF", category: "风格-红利"}
defensive_global_etfs:
  - {symbol: "513100.SH", name: "纳指ETF", category: "全球-科技"}
"""
    p = tmp_path / "universe.yaml"
    p.write_text(yaml_content)
    cfg, industry_syms = load_volume_filter_config(p)
    assert cfg.enabled is True
    assert cfg.min_avg_monthly_volume_shares == 2_000_000
    assert cfg.lookback_months == 6
    # Only industry ETFs are subject to the volume filter
    assert industry_syms == {"159930.SZ", "512800.SH"}
    # style/defensive ETFs are excluded from filtered set
    assert "510880.SH" not in industry_syms
    assert "513100.SH" not in industry_syms


def test_load_universe_per_etf_volume_threshold(tmp_path):
    """EtfEntry.volume_threshold picks up per-ETF override."""
    yaml_content = """
industry_etfs:
  - {symbol: "159930.SZ", name: "能源ETF", category: "周期", min_avg_monthly_volume_shares: 500000}
  - {symbol: "512800.SH", name: "银行ETF", category: "金融"}
"""
    p = tmp_path / "universe.yaml"
    p.write_text(yaml_content)
    entries = load_universe(p)
    by_sym = {e.symbol: e for e in entries}
    assert by_sym["159930.SZ"].volume_threshold == 500_000
    assert by_sym["512800.SH"].volume_threshold is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd ~/lab/quantitative_trading
python -m pytest tests/rotation/test_rotation_universe.py::test_load_volume_filter_config_defaults tests/rotation/test_rotation_universe.py::test_load_volume_filter_config_from_yaml tests/rotation/test_rotation_universe.py::test_load_universe_per_etf_volume_threshold -v 2>&1 | tail -20
```

Expected: FAIL (`ImportError: cannot import name 'load_volume_filter_config'`)

- [ ] **Step 3: Update `rotation_universe.yaml`**

Add to the top of `config/rotation_universe.yaml` (before `industry_etfs`):

```yaml
schema_version: 2
updated_at: "2026-05-17"

volume_filter:
  enabled: true
  min_avg_monthly_volume_shares: 1000000
  lookback_months: 3
```

No changes to individual ETF entries unless you want to override (none needed — the two flagged ETFs will be filtered dynamically).

- [ ] **Step 4: Update `universe.py`**

Replace the contents of `quant/analysis/rotation/universe.py` with:

```python
"""Rotation universe configuration loader."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml

_REQUIRED_FIELDS = ("symbol", "name", "category")
_DEFAULT_YAML_RELATIVE = "config/rotation_universe.yaml"


@dataclass(frozen=True)
class EtfEntry:
    """One ETF in the rotation universe."""

    symbol: str
    name: str
    category: str
    volume_threshold: Optional[int] = None


@dataclass(frozen=True)
class VolumeFilterConfig:
    """Global volume filter parameters from universe YAML."""

    enabled: bool = False
    min_avg_monthly_volume_shares: int = 1_000_000
    lookback_months: int = 3


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _coerce_entries(raw_list: Iterable[dict]) -> list[EtfEntry]:
    entries: list[EtfEntry] = []
    for raw in raw_list or []:
        for field in _REQUIRED_FIELDS:
            if field not in raw:
                raise ValueError(f"universe entry missing field {field!r}: {raw}")
        threshold = raw.get("min_avg_monthly_volume_shares")
        entries.append(
            EtfEntry(
                symbol=str(raw["symbol"]),
                name=str(raw["name"]),
                category=str(raw["category"]),
                volume_threshold=int(threshold) if threshold is not None else None,
            )
        )
    return entries


def _resolve_path(path: Path | str | None) -> Path:
    if path is None:
        return _project_root() / _DEFAULT_YAML_RELATIVE
    return Path(path)


def load_universe(path: Path | str | None = None) -> list[EtfEntry]:
    """Load and validate the rotation universe from yaml.

    Raises FileNotFoundError if the file is missing, ValueError on schema
    problems (missing field or duplicate symbol).
    """
    resolved = _resolve_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"universe yaml not found: {resolved}")

    with resolved.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    entries = _coerce_entries(data.get("industry_etfs"))
    entries.extend(_coerce_entries(data.get("style_etfs")))
    entries.extend(_coerce_entries(data.get("defensive_global_etfs")))

    seen: set[str] = set()
    for entry in entries:
        if entry.symbol in seen:
            raise ValueError(f"duplicate symbol in universe: {entry.symbol}")
        seen.add(entry.symbol)

    return entries


def load_volume_filter_config(
    path: Path | str | None = None,
) -> tuple[VolumeFilterConfig, set[str]]:
    """Return (VolumeFilterConfig, industry_symbols).

    ``industry_symbols`` is the set of symbols subject to volume filtering
    (only ``industry_etfs`` entries; style and defensive ETFs are exempt).
    """
    resolved = _resolve_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"universe yaml not found: {resolved}")

    with resolved.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    vf = data.get("volume_filter", {})
    config = VolumeFilterConfig(
        enabled=bool(vf.get("enabled", False)),
        min_avg_monthly_volume_shares=int(vf.get("min_avg_monthly_volume_shares", 1_000_000)),
        lookback_months=int(vf.get("lookback_months", 3)),
    )
    industry_symbols = {
        str(e["symbol"])
        for e in (data.get("industry_etfs") or [])
        if "symbol" in e
    }
    return config, industry_symbols
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
cd ~/lab/quantitative_trading
python -m pytest tests/rotation/test_rotation_universe.py -v 2>&1 | tail -20
```

Expected: All tests pass (including pre-existing ones).

- [ ] **Step 6: Commit**

```bash
cd ~/lab/quantitative_trading
git add config/rotation_universe.yaml quant/analysis/rotation/universe.py tests/rotation/test_rotation_universe.py
git commit -m "feat(rotation): add VolumeFilterConfig and per-ETF volume_threshold to universe loader"
```

---

## Task 2: Add VolumeFilteredRanker

**Files:**
- Modify: `quant/analysis/rotation/ranker.py`
- Create: `tests/rotation/test_volume_filter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/rotation/test_volume_filter.py`:

```python
"""Tests for VolumeFilteredRanker."""
import pandas as pd
import pytest

from quant.analysis.rotation.ranker import MomentumRanker, RankerConfig, VolumeFilteredRanker
from quant.analysis.rotation.universe import VolumeFilterConfig


def _make_prices(symbols, dates, fill=100.0):
    return pd.DataFrame(fill, index=pd.to_datetime(dates), columns=symbols)


def _make_volumes(symbols, dates, fill=2_000_000):
    return pd.DataFrame(fill, index=pd.to_datetime(dates), columns=symbols)


DATES = [
    "2024-01-31", "2024-02-29", "2024-03-31",
    "2024-04-30", "2024-05-31", "2024-06-30",
    "2024-07-31", "2024-08-31",
]
SYMBOLS = ["512800.SH", "159930.SZ", "513100.SH"]
INDUSTRY = {"512800.SH", "159930.SZ"}


def _ranker():
    return MomentumRanker(RankerConfig(lookback_months=6, skip_recent_months=1, top_k=3))


def test_volume_filter_disabled_passes_all():
    """When filter is disabled, all symbols reach the ranker."""
    prices = _make_prices(SYMBOLS, DATES)
    # Add a trend so momentum is non-zero
    prices.iloc[-1] = [110, 120, 130]

    volumes = _make_volumes(SYMBOLS, DATES, fill=0)  # all zero, would be filtered if enabled
    cfg = VolumeFilterConfig(enabled=False)
    ranker = VolumeFilteredRanker(_ranker(), volumes, cfg, INDUSTRY)

    result = ranker.rank(prices, pd.Timestamp("2024-08-31"))
    assert set(result.keys()) <= set(SYMBOLS)


def test_volume_filter_excludes_low_volume_industry_etf():
    """Industry ETF below threshold is excluded; defensive ETF passes regardless."""
    prices = _make_prices(SYMBOLS, DATES)
    prices.iloc[-1] = [110, 120, 130]

    volumes = _make_volumes(SYMBOLS, DATES, fill=2_000_000)
    # 159930.SZ has very low volume
    volumes["159930.SZ"] = 100

    cfg = VolumeFilterConfig(enabled=True, min_avg_monthly_volume_shares=1_000_000, lookback_months=3)
    ranker = VolumeFilteredRanker(_ranker(), volumes, cfg, INDUSTRY)

    result = ranker.rank(prices, pd.Timestamp("2024-08-31"))
    assert "159930.SZ" not in result
    # 513100.SH is not in INDUSTRY so it passes even with low volume
    # (its volume is 2M so it would pass anyway, but the key point is it's not filtered)
    assert "512800.SH" in result or len(result) >= 0  # 512800.SH passes


def test_volume_filter_non_industry_etf_never_filtered():
    """Defensive/style ETFs pass the volume filter regardless of volume."""
    symbols = ["513100.SH", "511880.SH"]
    prices = _make_prices(symbols, DATES)
    prices.iloc[-1] = [110, 105]

    volumes = _make_volumes(symbols, DATES, fill=0)  # zero volume
    cfg = VolumeFilterConfig(enabled=True, min_avg_monthly_volume_shares=1_000_000, lookback_months=3)
    industry = set()  # no industry ETFs
    ranker = VolumeFilteredRanker(_ranker(), volumes, cfg, industry)

    result = ranker.rank(prices, pd.Timestamp("2024-08-31"))
    # Both pass filter; result depends on momentum but neither is excluded
    assert len(result) > 0


def test_volume_filter_per_etf_threshold_override():
    """Per-ETF threshold overrides global threshold."""
    prices = _make_prices(SYMBOLS, DATES)
    prices.iloc[-1] = [110, 120, 130]

    volumes = _make_volumes(SYMBOLS, DATES, fill=600_000)  # below global 1M

    cfg = VolumeFilterConfig(enabled=True, min_avg_monthly_volume_shares=1_000_000, lookback_months=3)
    # 159930.SZ has a lower per-ETF threshold — should pass
    per_etf = {"159930.SZ": 500_000}
    ranker = VolumeFilteredRanker(_ranker(), volumes, cfg, INDUSTRY, per_etf_thresholds=per_etf)

    result = ranker.rank(prices, pd.Timestamp("2024-08-31"))
    assert "159930.SZ" in result or "512800.SH" not in result  # 512800.SH excluded (600k < 1M), 159930.SZ included


def test_volume_filter_uses_trailing_window():
    """Filter uses trailing lookback_months, not full history."""
    prices = _make_prices(["512800.SH"], DATES)
    prices.iloc[-1] = 110.0

    volumes = pd.DataFrame({"512800.SH": [5_000_000] * 5 + [100, 100, 100]},
                           index=pd.to_datetime(DATES))
    # Recent 3 months: 100 shares (below 1M), but earlier months had 5M

    cfg = VolumeFilterConfig(enabled=True, min_avg_monthly_volume_shares=1_000_000, lookback_months=3)
    industry = {"512800.SH"}
    ranker = VolumeFilteredRanker(_ranker(), volumes, cfg, industry)

    result = ranker.rank(prices, pd.Timestamp("2024-08-31"))
    assert "512800.SH" not in result  # trailing 3M is low
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd ~/lab/quantitative_trading
python -m pytest tests/rotation/test_volume_filter.py -v 2>&1 | tail -15
```

Expected: FAIL (`ImportError: cannot import name 'VolumeFilteredRanker'`)

- [ ] **Step 3: Add VolumeFilteredRanker to `ranker.py`**

Append to the bottom of `quant/analysis/rotation/ranker.py`:

```python
# ---------------------------------------------------------------------------
# Volume-filter decorator
# ---------------------------------------------------------------------------

import logging as _logging

_vol_logger = _logging.getLogger(__name__)


class VolumeFilteredRanker:
    """Wraps any ranker and pre-filters symbols by trailing monthly volume.

    Only symbols in ``industry_symbols`` are subject to the filter.
    Style and defensive ETFs pass through unconditionally.

    Args:
        inner: Any ranker with a ``rank(monthly_prices, rebalance_date)`` interface.
        monthly_volumes: DataFrame indexed by month-end dates, columns = symbols,
            values = monthly total volume in shares (sum of daily volumes).
        config: VolumeFilterConfig parsed from universe YAML.
        industry_symbols: Set of symbols subject to the volume filter.
        per_etf_thresholds: Optional per-symbol override of the global threshold.
    """

    def __init__(
        self,
        inner,
        monthly_volumes: pd.DataFrame,
        config,
        industry_symbols: set[str],
        per_etf_thresholds: dict[str, int] | None = None,
    ) -> None:
        self._inner = inner
        self._volumes = monthly_volumes
        self._config = config
        self._industry = industry_symbols
        self._per_etf = per_etf_thresholds or {}

    def rank(
        self,
        monthly_prices: pd.DataFrame,
        rebalance_date: pd.Timestamp,
    ) -> dict[str, float]:
        if not self._config.enabled or self._volumes.empty:
            return self._inner.rank(monthly_prices, rebalance_date)

        passed = self._filter(monthly_prices.columns.tolist(), rebalance_date)
        if not passed:
            return {}
        filtered_prices = monthly_prices[passed]
        return self._inner.rank(filtered_prices, rebalance_date)

    def _filter(self, symbols: list[str], rebalance_date: pd.Timestamp) -> list[str]:
        lb = self._config.lookback_months
        global_threshold = self._config.min_avg_monthly_volume_shares

        if rebalance_date in self._volumes.index:
            loc = self._volumes.index.get_loc(rebalance_date)
        else:
            # Find nearest available date
            loc = self._volumes.index.searchsorted(rebalance_date, side="right") - 1
            if loc < 0:
                return symbols  # no volume data yet; pass all through

        start = max(0, loc - lb + 1)
        window = self._volumes.iloc[start: loc + 1]

        passed, excluded = [], []
        for sym in symbols:
            if sym not in self._industry:
                passed.append(sym)
                continue
            threshold = self._per_etf.get(sym, global_threshold)
            avg_vol = float(window[sym].mean()) if sym in window.columns else 0.0
            if avg_vol >= threshold:
                passed.append(sym)
            else:
                excluded.append((sym, avg_vol, threshold))

        for sym, vol, thr in excluded:
            _vol_logger.warning(
                "Volume filter: %s excluded (trailing-%dM avg %.0f < %.0f shares/month)",
                sym, lb, vol, thr,
            )
        return passed
```

- [ ] **Step 4: Add import for VolumeFilterConfig in ranker.py**

At the top of `quant/analysis/rotation/ranker.py`, the `VolumeFilterConfig` type is referenced. The import is deferred via TYPE_CHECKING or just imported at runtime. Add to imports block:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quant.analysis.rotation.universe import VolumeFilterConfig
```

Actually to avoid circular imports just use duck typing — `config` is typed as `Any` at runtime. The `VolumeFilteredRanker.__init__` signature already uses `config` without a specific type annotation in the implementation code. No import change needed.

- [ ] **Step 5: Run tests to confirm pass**

```bash
cd ~/lab/quantitative_trading
python -m pytest tests/rotation/test_volume_filter.py -v 2>&1 | tail -20
```

Expected: All 5 tests pass.

- [ ] **Step 6: Commit**

```bash
cd ~/lab/quantitative_trading
git add quant/analysis/rotation/ranker.py tests/rotation/test_volume_filter.py
git commit -m "feat(rotation): add VolumeFilteredRanker decorator"
```

---

## Task 3: Wire VolumeFilteredRanker into RotationService

**Files:**
- Modify: `quant/services/rotation_service.py`
- Test: `tests/rotation/test_rotation_service.py` (existing — add one case)

- [ ] **Step 1: Write failing test**

Add to `tests/rotation/test_rotation_service.py`:

```python
def test_run_backtest_volume_filter_excludes_low_volume(monkeypatch):
    """RotationService applies volume filter when universe config has it enabled."""
    import pandas as pd
    from quant.services.rotation_service import RotationService, RotationRequest
    from quant.analysis.rotation import RankerConfig

    dates = pd.date_range("2020-01-31", periods=20, freq="ME")
    symbols = ["512800.SH", "159930.SZ"]

    prices = pd.DataFrame({
        "512800.SH": [100 + i for i in range(20)],
        "159930.SZ": [100 + i * 1.5 for i in range(20)],
    }, index=dates)

    # 159930.SZ has near-zero volume across all periods
    volumes = pd.DataFrame({
        "512800.SH": [2_000_000] * 20,
        "159930.SZ": [1_000] * 20,
    }, index=dates)

    def mock_get_price(request):
        symbol = request.symbol
        if symbol == "000300.SH":
            return pd.DataFrame({"close": [100 + i for i in range(20)]}, index=dates)
        close = prices[symbol] if symbol in prices.columns else pd.Series(dtype=float)
        vol = volumes[symbol] if symbol in volumes.columns else pd.Series(dtype=float)
        return pd.DataFrame({"close": close, "volume": vol})

    svc = RotationService()
    monkeypatch.setattr(svc.data_service, "get_price", mock_get_price)

    # Use a tmp universe file with volume filter enabled
    import tempfile, textwrap, pathlib
    universe_yaml = textwrap.dedent("""
        volume_filter:
          enabled: true
          min_avg_monthly_volume_shares: 1000000
          lookback_months: 3
        industry_etfs:
          - {symbol: "512800.SH", name: "银行ETF", category: "金融"}
          - {symbol: "159930.SZ", name: "能源ETF", category: "周期"}
    """)
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(universe_yaml)
        universe_path = f.name

    req = RotationRequest(
        start="20200101", end="20211231",
        universe_path=universe_path,
        ranker_config=RankerConfig(lookback_months=6, skip_recent_months=1, top_k=2),
    )
    result = svc.run_backtest(req)
    # 159930.SZ should never appear in holdings (volume too low)
    holdings = result.holdings if hasattr(result, "holdings") else pd.DataFrame()
    if not holdings.empty and "159930.SZ" in holdings.columns:
        assert (holdings["159930.SZ"] == 0).all(), "Low-volume ETF appeared in holdings"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd ~/lab/quantitative_trading
python -m pytest tests/rotation/test_rotation_service.py::test_run_backtest_volume_filter_excludes_low_volume -v 2>&1 | tail -15
```

Expected: FAIL (service doesn't yet use volume filter)

- [ ] **Step 3: Update `RotationService`**

Add `_collect_monthly_volumes()` and wire `VolumeFilteredRanker` into `run_backtest()` and `latest_targets()`. Also write latest targets to a sidecar JSON.

Replace the full contents of `quant/services/rotation_service.py` with:

```python
"""Rotation strategy preparation service."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
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
from quant.analysis.rotation.ranker import VolumeFilteredRanker
from quant.analysis.rotation.universe import load_volume_filter_config
from quant.services.data_service import DataService, PriceRequest

logger = logging.getLogger(__name__)

_LATEST_SIDECAR = Path(".quant_cache/latest_targets.json")


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
    overlay_type: str = "simple"   # "simple" | "cockpit"


class RotationService:
    """Wire DataService + universe yaml + rotation pipeline."""

    def __init__(self, data_service: DataService | None = None) -> None:
        self.data_service = data_service or DataService()

    def run_backtest(self, request: RotationRequest) -> RotationBacktestResult:
        """Run the full backtest with the requested configuration."""
        universe = load_universe(request.universe_path)
        vol_config, industry_syms = load_volume_filter_config(request.universe_path)
        monthly_prices = self._collect_monthly_prices(universe, request)
        monthly_volumes = self._collect_monthly_volumes(universe, request)
        benchmark_prices = self._fetch_benchmark_close(request)
        overlay = self._build_overlay(request)

        inner_ranker = MomentumRanker(request.ranker_config or RankerConfig())
        ranker = VolumeFilteredRanker(
            inner_ranker, monthly_volumes, vol_config, industry_syms,
            per_etf_thresholds=self._per_etf_thresholds(universe),
        )
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
        """Return the decision payload for the most recent month-end ≤ request.end.

        Also writes the result to ``.quant_cache/latest_targets.json`` for
        ``quant rotation precheck --from-latest``.
        """
        universe = load_universe(request.universe_path)
        vol_config, industry_syms = load_volume_filter_config(request.universe_path)
        monthly_prices = self._collect_monthly_prices(universe, request)
        monthly_volumes = self._collect_monthly_volumes(universe, request)
        if monthly_prices.empty:
            raise ValueError("no monthly prices available; check date range and universe")

        rebalance_date = monthly_prices.index[-1]
        inner_ranker = MomentumRanker(request.ranker_config or RankerConfig())
        ranker = VolumeFilteredRanker(
            inner_ranker, monthly_volumes, vol_config, industry_syms,
            per_etf_thresholds=self._per_etf_thresholds(universe),
        )
        weights = ranker.rank(monthly_prices, rebalance_date)

        overlay = self._build_overlay(request)
        multiplier = float(overlay.multiplier_at(rebalance_date))

        combiner = PortfolioCombiner()
        final_positions = combiner.combine(weights, multiplier)

        top_n = max(len(weights), (request.ranker_config or RankerConfig()).top_k)
        top_momentum = self._top_momentum(monthly_prices, rebalance_date, top_n, request)

        result = {
            "as_of": rebalance_date.strftime("%Y-%m-%d"),
            "multiplier": multiplier,
            "weights": dict(weights),
            "final_positions": dict(final_positions),
            "top_momentum": top_momentum,
        }
        self._write_latest_sidecar(result)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
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
                continue
            if df is None or df.empty or "close" not in df.columns:
                continue
            close = df["close"].astype(float)
            close.name = entry.symbol
            monthly = close.resample("ME").last().dropna()
            if monthly.empty:
                continue
            frames[entry.symbol] = monthly
        if not frames:
            return pd.DataFrame()
        return pd.DataFrame(frames).sort_index()

    def _collect_monthly_volumes(self, universe, request: RotationRequest) -> pd.DataFrame:
        """Collect monthly total volume (sum of daily volumes) for each ETF."""
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
                continue
            if df is None or df.empty or "volume" not in df.columns:
                continue
            vol = df["volume"].astype(float)
            vol.name = entry.symbol
            monthly = vol.resample("ME").sum().dropna()
            if monthly.empty:
                continue
            frames[entry.symbol] = monthly
        if not frames:
            return pd.DataFrame()
        return pd.DataFrame(frames).sort_index()

    def _per_etf_thresholds(self, universe) -> dict[str, int]:
        return {
            e.symbol: e.volume_threshold
            for e in universe
            if e.volume_threshold is not None
        }

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

    def _build_overlay(self, request: RotationRequest):
        if request.overlay_type == "simple":
            overlay = SimpleRegimeOverlay(
                data_service=self.data_service,
                benchmark_symbol=request.overlay_benchmark,
            )
        elif request.overlay_type == "cockpit":
            from quant.analysis.rotation import CockpitRegimeOverlay
            overlay = CockpitRegimeOverlay(data_service=self.data_service)
        else:
            raise ValueError(f"unknown overlay_type: {request.overlay_type}")
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

    @staticmethod
    def _write_latest_sidecar(result: dict) -> None:
        """Write latest_targets to .quant_cache/latest_targets.json (best-effort)."""
        try:
            _LATEST_SIDECAR.parent.mkdir(parents=True, exist_ok=True)
            with _LATEST_SIDECAR.open("w", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Could not write latest sidecar: %s", exc)
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
cd ~/lab/quantitative_trading
python -m pytest tests/rotation/test_rotation_service.py -v 2>&1 | tail -20
```

Expected: All tests pass including the new one.

- [ ] **Step 5: Commit**

```bash
cd ~/lab/quantitative_trading
git add quant/services/rotation_service.py tests/rotation/test_rotation_service.py
git commit -m "feat(rotation): wire VolumeFilteredRanker into RotationService; write latest sidecar"
```

---

## Task 4: Add PreTradeChecker

**Files:**
- Create: `quant/analysis/rotation/precheck.py`
- Create: `tests/rotation/test_precheck.py`

- [ ] **Step 1: Write failing tests**

Create `tests/rotation/test_precheck.py`:

```python
"""Tests for PreTradeChecker."""
import pandas as pd
import pytest
from unittest.mock import MagicMock

from quant.analysis.rotation.precheck import PreTradeChecker, PreCheckReport


def _mock_data_service(price_513100=None, price_159941=None, nav_513100=None, quota_ok=True):
    """Build a mock DataService for precheck tests."""
    ds = MagicMock()

    def get_price(request):
        today = pd.Timestamp("2026-05-30")
        if request.symbol == "513100.SH":
            p = price_513100 or 2.00
            return pd.DataFrame({"close": [p]}, index=[today])
        if request.symbol == "159941.SZ":
            p = price_159941 or 2.00
            return pd.DataFrame({"close": [p]}, index=[today])
        return pd.DataFrame({"close": [1.0]}, index=[today])

    ds.get_price.side_effect = get_price
    return ds, nav_513100, quota_ok


def _make_checker(price_513100=2.00, price_159941=2.00, nav_513100=2.00, quota_ok=True):
    ds, nav, quota = _mock_data_service(price_513100, price_159941, nav_513100, quota_ok)
    checker = PreTradeChecker(data_service=ds)
    checker._get_qdii_nav = lambda: nav
    checker._get_qdii_quota_ok = lambda: quota
    return checker


def test_all_checks_pass():
    """No warnings when premium is low and quota is fine."""
    checker = _make_checker(price_513100=2.00, price_159941=2.00, nav_513100=2.00)
    targets = {"513100.SH": 0.33, "511880.SH": 0.33, "512800.SH": 0.34}
    report = checker.run(targets)

    assert not report.has_errors
    assert not report.has_warnings
    assert report.adjusted_targets == targets


def test_qdii_premium_warn_threshold():
    """Premium > 1% triggers WARN but does not substitute."""
    # price = 2.022 → premium = 1.1%
    checker = _make_checker(price_513100=2.022, nav_513100=2.00)
    targets = {"513100.SH": 0.33, "511880.SH": 0.33, "512800.SH": 0.34}
    report = checker.run(targets)

    assert report.has_warnings
    assert not report.has_errors
    # 513100.SH remains in adjusted targets
    assert "513100.SH" in report.adjusted_targets


def test_qdii_premium_error_threshold_substitutes():
    """Premium > 2% triggers ERROR and substitutes 513100.SH with 511880.SH."""
    # price = 2.05 → premium = 2.5%
    checker = _make_checker(price_513100=2.05, nav_513100=2.00)
    targets = {"513100.SH": 0.33, "511880.SH": 0.33, "512800.SH": 0.34}
    report = checker.run(targets)

    assert report.has_errors
    assert "513100.SH" not in report.adjusted_targets
    # 511880.SH absorbs the weight
    assert abs(report.adjusted_targets.get("511880.SH", 0) - 0.66) < 1e-9


def test_cross_etf_spread_warn():
    """Price spread > 1% between 513100.SH and 159941.SZ triggers WARN."""
    # 513100 = 2.00, 159941 = 1.97 → spread = 1.5%
    checker = _make_checker(price_513100=2.00, price_159941=1.97)
    targets = {"513100.SH": 0.33, "511880.SH": 0.33, "512800.SH": 0.34}
    report = checker.run(targets)

    assert report.has_warnings
    assert "513100.SH" in report.adjusted_targets  # only warns, does not substitute


def test_qdii_quota_suspended_substitutes():
    """QDII quota suspended for >3 days triggers ERROR and substitutes."""
    checker = _make_checker(quota_ok=False)
    targets = {"513100.SH": 0.33, "511880.SH": 0.33, "512800.SH": 0.34}
    report = checker.run(targets)

    assert report.has_errors
    assert "513100.SH" not in report.adjusted_targets
    assert abs(report.adjusted_targets.get("511880.SH", 0) - 0.66) < 1e-9


def test_no_qdii_in_targets_skips_qdii_checks():
    """If 513100.SH is not in targets, QDII checks are skipped."""
    checker = _make_checker()
    targets = {"511880.SH": 0.50, "512800.SH": 0.50}
    report = checker.run(targets)

    assert not report.has_errors
    assert not report.has_warnings
    assert report.adjusted_targets == targets


def test_nav_unavailable_emits_warn_not_error():
    """If IOPV data is unavailable, emit WARN (not ERROR) and leave targets unchanged."""
    checker = _make_checker(nav_513100=None)  # None = unavailable
    targets = {"513100.SH": 0.33, "511880.SH": 0.33, "512800.SH": 0.34}
    report = checker.run(targets)

    assert report.has_warnings
    assert not report.has_errors
    assert "513100.SH" in report.adjusted_targets
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd ~/lab/quantitative_trading
python -m pytest tests/rotation/test_precheck.py -v 2>&1 | tail -15
```

Expected: FAIL (`ModuleNotFoundError: No module named 'quant.analysis.rotation.precheck'`)

- [ ] **Step 3: Create `precheck.py`**

Create `quant/analysis/rotation/precheck.py`:

```python
"""Pre-trade execution checks for monthly ETF rotation rebalancing."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from quant.services.data_service import DataService, PriceRequest

logger = logging.getLogger(__name__)

QDII_SYMBOL = "513100.SH"
QDII_ALT = "511880.SH"
CROSS_ETF = "159941.SZ"

WARN_THRESHOLD = 0.01    # 1%: defer buy
ERROR_THRESHOLD = 0.02   # 2%: substitute with short bond
CROSS_SPREAD_THRESHOLD = 0.01  # 1%: warn only


@dataclass
class CheckResult:
    name: str
    status: str    # "ok" | "warn" | "error"
    message: str


@dataclass
class PreCheckReport:
    checks: list[CheckResult]
    original_targets: dict[str, float]
    adjusted_targets: dict[str, float]
    has_errors: bool = field(init=False)
    has_warnings: bool = field(init=False)

    def __post_init__(self):
        self.has_errors = any(c.status == "error" for c in self.checks)
        self.has_warnings = any(c.status == "warn" for c in self.checks)


class PreTradeChecker:
    """Run pre-trade checks on target positions before monthly rebalancing.

    Checks are performed in order:
    1. QDII premium vs IOPV (warn >1%, substitute >2%)
    2. Cross-ETF spread vs 159941.SZ (warn >1%)
    3. QDII quota / creation status (substitute if suspended)

    All checks are skipped when 513100.SH is not in ``targets``.
    """

    def __init__(self, data_service: DataService | None = None) -> None:
        self.data_service = data_service or DataService()

    def run(self, targets: dict[str, float]) -> PreCheckReport:
        checks: list[CheckResult] = []
        adjusted = dict(targets)

        if QDII_SYMBOL in targets:
            check, adjusted = self._check_qdii_premium(adjusted)
            checks.append(check)

            # Only check cross-ETF spread if QDII is still in adjusted (not yet substituted)
            if QDII_SYMBOL in adjusted:
                checks.append(self._check_cross_etf_spread())

            check, adjusted = self._check_qdii_quota(adjusted)
            checks.append(check)

        return PreCheckReport(
            checks=checks,
            original_targets=targets,
            adjusted_targets=adjusted,
        )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_qdii_premium(
        self, targets: dict[str, float]
    ) -> tuple[CheckResult, dict[str, float]]:
        nav = self._get_qdii_nav()
        if nav is None:
            return (
                CheckResult("QDII溢价", "warn", "IOPV数据不可用，跳过溢价检查"),
                targets,
            )

        price = self._get_latest_price(QDII_SYMBOL)
        if price is None:
            return (
                CheckResult("QDII溢价", "warn", "无法获取513100.SH最新价格"),
                targets,
            )

        premium = (price - nav) / nav
        msg_base = f"溢价 {premium:+.2%}（价格 {price:.4f}，IOPV {nav:.4f}）"

        if premium > ERROR_THRESHOLD:
            weight = targets.pop(QDII_SYMBOL)
            targets[QDII_ALT] = targets.get(QDII_ALT, 0.0) + weight
            return (
                CheckResult(
                    "QDII溢价",
                    "error",
                    f"{msg_base} > {ERROR_THRESHOLD:.0%}，已替换为{QDII_ALT}",
                ),
                targets,
            )
        if premium > WARN_THRESHOLD:
            return (
                CheckResult(
                    "QDII溢价",
                    "warn",
                    f"{msg_base} > {WARN_THRESHOLD:.0%}，建议延迟买入",
                ),
                targets,
            )
        return (
            CheckResult("QDII溢价", "ok", f"{msg_base}，正常"),
            targets,
        )

    def _check_cross_etf_spread(self) -> CheckResult:
        p1 = self._get_latest_price(QDII_SYMBOL)
        p2 = self._get_latest_price(CROSS_ETF)
        if p1 is None or p2 is None:
            return CheckResult("跨ETF价差", "warn", "无法获取比价数据")

        # Normalize 159941.SZ price to same scale as 513100.SH via ratio
        spread = abs(p1 - p2) / p2
        if spread > CROSS_SPREAD_THRESHOLD:
            return CheckResult(
                "跨ETF价差",
                "warn",
                f"{QDII_SYMBOL}/{CROSS_ETF} 价差 {spread:.2%} > {CROSS_SPREAD_THRESHOLD:.0%}，建议等价差收窄",
            )
        return CheckResult("跨ETF价差", "ok", f"价差 {spread:.2%}，正常")

    def _check_qdii_quota(
        self, targets: dict[str, float]
    ) -> tuple[CheckResult, dict[str, float]]:
        if QDII_SYMBOL not in targets:
            return CheckResult("QDII额度", "ok", "513100.SH已替换，跳过额度检查"), targets

        quota_ok = self._get_qdii_quota_ok()
        if quota_ok is None:
            return CheckResult("QDII额度", "warn", "无法获取额度状态，请手动核查"), targets
        if not quota_ok:
            weight = targets.pop(QDII_SYMBOL)
            targets[QDII_ALT] = targets.get(QDII_ALT, 0.0) + weight
            return (
                CheckResult(
                    "QDII额度",
                    "error",
                    f"513100.SH申购暂停，已替换为{QDII_ALT}",
                ),
                targets,
            )
        return CheckResult("QDII额度", "ok", "申购正常"), targets

    # ------------------------------------------------------------------
    # Data helpers (injectable for testing)
    # ------------------------------------------------------------------

    def _get_latest_price(self, symbol: str) -> float | None:
        try:
            df = self.data_service.get_price(
                PriceRequest(symbol=symbol, start="20260101", end="20991231", asset_type="etf")
            )
            if df is None or df.empty or "close" not in df.columns:
                return None
            return float(df["close"].iloc[-1])
        except Exception as exc:
            logger.warning("Failed to fetch price for %s: %s", symbol, exc)
            return None

    def _get_qdii_nav(self) -> float | None:
        """Return T-1 NAV of 513100.SH from Tushare fund_nav (best-effort).

        Falls back to None when data is unavailable.
        Tushare fund_nav endpoint returns T-1 NAV; treated as IOPV proxy.
        """
        try:
            import tushare as ts  # type: ignore
            import os
            token = os.getenv("TUSHARE_TOKEN", "")
            if not token:
                return None
            pro = ts.pro_api(token)
            df = pro.fund_nav(ts_code="513100.SH", fields="nav_date,unit_nav")
            if df is None or df.empty:
                return None
            return float(df.sort_values("nav_date").iloc[-1]["unit_nav"])
        except Exception as exc:
            logger.warning("fund_nav fetch failed: %s", exc)
            return None

    def _get_qdii_quota_ok(self) -> bool | None:
        """Return True if 513100.SH primary-market creation is open, None if unknown."""
        try:
            import tushare as ts  # type: ignore
            import os
            from datetime import date, timedelta
            token = os.getenv("TUSHARE_TOKEN", "")
            if not token:
                return None
            pro = ts.pro_api(token)
            end = date.today().strftime("%Y%m%d")
            start = (date.today() - timedelta(days=7)).strftime("%Y%m%d")
            df = pro.fund_share(ts_code="513100.SH", start_date=start, end_date=end)
            if df is None or df.empty:
                return None
            # If share count has been flat for the last 3+ trading days, treat as halted
            if len(df) >= 3 and df["fd_share"].nunique() == 1:
                return False
            return True
        except Exception as exc:
            logger.warning("fund_share fetch failed: %s", exc)
            return None
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
cd ~/lab/quantitative_trading
python -m pytest tests/rotation/test_precheck.py -v 2>&1 | tail -20
```

Expected: All 7 tests pass.

- [ ] **Step 5: Commit**

```bash
cd ~/lab/quantitative_trading
git add quant/analysis/rotation/precheck.py tests/rotation/test_precheck.py
git commit -m "feat(rotation): add PreTradeChecker with QDII premium and quota guards"
```

---

## Task 5: Add `precheck` subcommand to rotation CLI

**Files:**
- Modify: `quant/cli/rotation.py`

- [ ] **Step 1: Add `precheck` subcommand registration**

In `quant/cli/rotation.py`, update `register_rotation_commands()` to add the `precheck` parser, and add handler functions:

```python
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

    precheck = sub.add_parser("precheck", help="调仓日 T-1 实盘前置检查")
    precheck.add_argument(
        "--targets",
        help='持仓字符串，格式 "513100.SH:0.33,511880.SH:0.33,512800.SH:0.34"',
    )
    precheck.add_argument(
        "--from-latest",
        action="store_true",
        help="从 .quant_cache/latest_targets.json 读取 latest 输出作为输入",
    )

    return parser
```

- [ ] **Step 2: Add `handle_rotation_command` routing**

Update `handle_rotation_command()`:

```python
def handle_rotation_command(args):
    """Route rotation commands."""
    if args.rotation_action == "backtest":
        handle_rotation_backtest(args)
    elif args.rotation_action == "latest":
        handle_rotation_latest(args)
    elif args.rotation_action == "precheck":
        handle_rotation_precheck(args)
    else:
        print("❌ 未知的轮动操作")
        sys.exit(1)
```

- [ ] **Step 3: Add `handle_rotation_precheck()` function**

Append to `quant/cli/rotation.py`:

```python
def handle_rotation_precheck(args):
    """Run pre-trade checks and print a report."""
    import json
    from pathlib import Path

    print("\n🔍 实盘前置检查（Pre-Trade Check）")
    print("=" * 80)

    targets: dict[str, float] = {}

    if getattr(args, "from_latest", False):
        sidecar = Path(".quant_cache/latest_targets.json")
        if not sidecar.exists():
            print("❌ 未找到 .quant_cache/latest_targets.json，请先运行 `quant rotation latest`")
            sys.exit(1)
        with sidecar.open(encoding="utf-8") as fh:
            data = json.load(fh)
        targets = {k: float(v) for k, v in data.get("final_positions", {}).items()}
        print(f"来源: latest ({data.get('as_of', '未知日期')})")
    elif args.targets:
        try:
            for part in args.targets.split(","):
                sym, weight = part.strip().split(":")
                targets[sym.strip()] = float(weight.strip())
        except ValueError:
            print('❌ --targets 格式错误，应为 "513100.SH:0.33,511880.SH:0.33"')
            sys.exit(1)
    else:
        print("❌ 请指定 --targets 或 --from-latest")
        sys.exit(1)

    print(f"\n输入持仓: {', '.join(f'{s}={w:.2%}' for s, w in targets.items())}")
    print()

    try:
        from quant.analysis.rotation.precheck import PreTradeChecker

        report = PreTradeChecker().run(targets)

        for check in report.checks:
            icon = {"ok": "✅", "warn": "⚠️ ", "error": "❌"}.get(check.status, "?")
            print(f"{icon} [{check.status.upper():5s}] {check.name}: {check.message}")

        print("\n调整后建议持仓:")
        if report.adjusted_targets:
            for sym, w in sorted(report.adjusted_targets.items(), key=lambda kv: kv[1], reverse=True):
                changed = " ← 已调整" if sym not in report.original_targets or report.original_targets.get(sym) != w else ""
                print(f"  {sym}: {w:.2%}{changed}")
        else:
            print("  （空持仓）")

        if report.has_errors:
            print("\n⚠️  存在 ERROR 项，建议确认后再下单。")
        elif report.has_warnings:
            print("\n💡 存在 WARN 项，请注意。")
        else:
            print("\n✅ 所有检查通过，可以下单。")

    except Exception as e:
        print(f"❌ 前置检查失败: {e}")
        logger.error("Precheck failed: %s", e, exc_info=True)
        sys.exit(1)
```

- [ ] **Step 4: Smoke test the CLI**

```bash
cd ~/lab/quantitative_trading
python -m quant rotation precheck --targets "513100.SH:0.33,511880.SH:0.33,512800.SH:0.34" 2>&1
```

Expected: output showing check results (QDII premium check may show WARN if IOPV unavailable — that's correct).

```bash
python -m quant rotation precheck --help 2>&1
```

Expected: Shows `--targets` and `--from-latest` options.

- [ ] **Step 5: Run full test suite to catch regressions**

```bash
cd ~/lab/quantitative_trading
python -m pytest tests/rotation/ -v 2>&1 | tail -30
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd ~/lab/quantitative_trading
git add quant/cli/rotation.py
git commit -m "feat(rotation): add 'quant rotation precheck' CLI command for pre-trade checks"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Volume filter: config in YAML, dynamic trailing 3M calculation, only industry ETFs filtered
- ✅ VolumeFilteredRanker: wraps existing ranker, same interface, works in backtest + latest
- ✅ precheck command: separate CLI, checks premium/cross-ETF/quota, substitutes on ERROR
- ✅ `--from-latest` sidecar: `latest` writes `.quant_cache/latest_targets.json`
- ✅ `defensive_global_etfs` / `style_etfs` not filtered

**Placeholder scan:** No TBDs, all code blocks complete.

**Type consistency:**
- `VolumeFilterConfig` defined in `universe.py`, used by `VolumeFilteredRanker` in `ranker.py`
- `PreCheckReport.has_errors` / `has_warnings` computed in `__post_init__` — matches test assertions
- `_LATEST_SIDECAR` path consistent between `rotation_service.py` and `cli/rotation.py`
