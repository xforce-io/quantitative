# Cockpit Rotation Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing cockpit `RegimeDetector` (a_shares pool) into the rotation pipeline as an opt-in overlay, replacing the simpler MA200/drawdown-based `SimpleRegimeOverlay` for users who choose `overlay_type="cockpit"`.

**Architecture:** Bottom-up — extend Tushare provider with two thin wrappers, expose them through `DataService`, build a historical indicator panel layer that feeds `RegimeDetector` per trading day, wrap the result in a `RegimeOverlay`-Protocol-conforming class, then wire the choice into `RotationRequest` + CLI.

**Tech Stack:** Python 3.12, pandas, dataclasses, pytest, existing cockpit `RegimeDetector` and rotation `RegimeOverlay` Protocol.

**Spec:** `docs/superpowers/specs/2026-05-02-cockpit-rotation-overlay-design.md`

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `quant/data/implementations/tushare_provider.py` | modify | Add `get_margin_balance(start, end)` aggregating SSE+SZSE; add `get_northbound_flow(start, end)` normalizing existing `get_hsgt_flow` columns |
| `quant/services/data_service.py` | modify | Add `get_margin_balance` + `get_northbound_flow` delegators following existing `get_money_flow` pattern |
| `tests/unit/test_services.py` | modify | Extend `FakeDataProvider` and add 3 tests for the new DataService methods |
| `quant/analysis/regime/historical_indicators.py` | create | `IndicatorPanelConfig` + `AshareHistoricalIndicators.build(start, end)` — produces 2-column daily panel |
| `tests/unit/test_ashare_historical_indicators.py` | create | 6 tests covering computation, error handling, ffill |
| `quant/analysis/rotation/cockpit_overlay.py` | create | `CockpitOverlayConfig` + `CockpitRegimeOverlay` implementing `RegimeOverlay` Protocol |
| `quant/analysis/rotation/__init__.py` | modify | Export `CockpitRegimeOverlay` and `CockpitOverlayConfig` |
| `tests/unit/test_cockpit_overlay.py` | create | 7 tests covering precompute, regime mapping, multiplier_at semantics |
| `quant/services/rotation_service.py` | modify | Add `overlay_type` field to `RotationRequest`; branch in `_build_overlay` |
| `quant/cli/rotation.py` | modify | Add `--overlay {simple,cockpit}` CLI arg, pass to request |
| `tests/integration/test_rotation_pipeline.py` | modify | Extend `_DeterministicDataService` with margin/northbound stubs; add 1 integration test |

---

## Task 1: TushareProvider.get_margin_balance + get_northbound_flow

These are thin wrappers around existing Tushare API. No unit tests at the provider layer (matches existing pattern — `get_margin_data` and `get_hsgt_flow` are also untested at unit level; real API exercised in integration test layer).

**Files:**
- Modify: `quant/data/implementations/tushare_provider.py`

- [ ] **Step 1: Add `get_margin_balance` method on TushareProvider**

Insert after the existing `get_margin_data` method (around line 470 — right after the existing margin block).

```python
def get_margin_balance(self, start: str, end: str) -> pd.DataFrame:
    """Aggregate margin balance across SSE+SZSE for the given date range.

    Returns DataFrame with columns:
      - trade_date (pd.Timestamp)
      - rzye       (融资余额, 元)
      - rqye       (融券余额, 元)
      - total      (rzye + rqye)
    """
    frames = []
    for exchange in ("SSE", "SZSE"):
        try:
            df = self.pro.margin(
                exchange_id=exchange,
                start_date=start,
                end_date=end,
            )
        except Exception as exc:
            logger.warning(f"margin fetch failed for {exchange}: {exc}")
            continue
        if df is None or df.empty:
            continue
        frames.append(df[["trade_date", "rzye", "rqye"]])

    if not frames:
        return pd.DataFrame(columns=["trade_date", "rzye", "rqye", "total"])

    combined = pd.concat(frames, ignore_index=True)
    grouped = combined.groupby("trade_date", as_index=False).sum()
    grouped["trade_date"] = pd.to_datetime(grouped["trade_date"], format="%Y%m%d")
    grouped["total"] = grouped["rzye"] + grouped["rqye"]
    return grouped.sort_values("trade_date").reset_index(drop=True)
```

- [ ] **Step 2: Add `get_northbound_flow` method on TushareProvider**

Insert after the existing `get_hsgt_top10` method (around line 183).

```python
def get_northbound_flow(self, start: str, end: str) -> pd.DataFrame:
    """Daily HK→A net inflow via Stock Connect, normalized columns.

    Returns DataFrame with columns:
      - trade_date (pd.Timestamp)
      - hgt_net    (沪股通净买入, 亿元)
      - sgt_net    (深股通净买入, 亿元)
      - total_net  (hgt_net + sgt_net)
    """
    raw = self._legacy.getHSGTFlow(start, end)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["trade_date", "hgt_net", "sgt_net", "total_net"])

    df = raw.copy()
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"])
    elif df.index.name == "trade_date":
        df = df.reset_index()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
    else:
        df["trade_date"] = pd.to_datetime(df.index)

    # tushare returns north_money / south_money or hgt / sgt depending on version;
    # normalize whichever is present. Values come back in 万元 — convert to 亿元.
    hgt_col = "hgt" if "hgt" in df.columns else ("north_money" if "north_money" in df.columns else None)
    sgt_col = "sgt" if "sgt" in df.columns else None

    df["hgt_net"] = (df[hgt_col].astype(float) / 10000.0) if hgt_col else 0.0
    df["sgt_net"] = (df[sgt_col].astype(float) / 10000.0) if sgt_col else 0.0
    df["total_net"] = df["hgt_net"] + df["sgt_net"]

    return df[["trade_date", "hgt_net", "sgt_net", "total_net"]].sort_values("trade_date").reset_index(drop=True)
```

- [ ] **Step 3: Smoke-check provider methods import**

Run: `uv run python -c "from quant.data.implementations.tushare_provider import TushareProvider; print('get_margin_balance' in dir(TushareProvider), 'get_northbound_flow' in dir(TushareProvider))"`

Expected: `True True`

- [ ] **Step 4: Commit**

```bash
git add quant/data/implementations/tushare_provider.py
git commit -m "$(cat <<'EOF'
feat: add tushare get_margin_balance and get_northbound_flow

Thin wrappers with normalized column schemas needed by the upcoming
cockpit rotation overlay. Aggregates margin across SSE+SZSE and
converts northbound flow values to 亿元.
EOF
)"
```

---

## Task 2: DataService delegators + tests

**Files:**
- Modify: `quant/services/data_service.py`
- Modify: `tests/unit/test_services.py`

- [ ] **Step 1: Add stub methods to FakeDataProvider in test_services.py**

Locate `class FakeDataProvider` (line ~8). Add these two methods alongside existing `get_money_flow`:

```python
    def get_margin_balance(self, start, end):
        self.calls.append(("margin_balance", start, end))
        return pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "rzye": [1.0e12, 1.05e12],
                "rqye": [1.0e10, 1.1e10],
                "total": [1.01e12, 1.061e12],
            }
        )

    def get_northbound_flow(self, start, end):
        self.calls.append(("northbound_flow", start, end))
        return pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "hgt_net": [10.0, -5.0],
                "sgt_net": [3.0, 2.0],
                "total_net": [13.0, -3.0],
            }
        )
```

- [ ] **Step 2: Write the failing tests in test_services.py**

Append after `test_get_fundamental_money_flow_and_calendar` (around line 124), inside `class TestDataService`:

```python
    def test_get_margin_balance_delegates_to_provider(self):
        provider = FakeDataProvider()
        service = DataService()

        df = service.get_margin_balance("20240101", "20240131", provider)

        assert provider.calls[-1] == ("margin_balance", "20240101", "20240131")
        assert df.iloc[0]["total"] == 1.01e12

    def test_get_northbound_flow_delegates_to_provider(self):
        provider = FakeDataProvider()
        service = DataService()

        df = service.get_northbound_flow("20240101", "20240131", provider)

        assert provider.calls[-1] == ("northbound_flow", "20240101", "20240131")
        assert df.iloc[0]["total_net"] == 13.0

    def test_get_margin_balance_raises_when_provider_missing_method(self):
        class BareProvider:
            pass

        service = DataService()
        try:
            service.get_margin_balance("20240101", "20240131", BareProvider())
        except NotImplementedError as exc:
            assert "Margin balance" in str(exc)
        else:
            raise AssertionError("Expected NotImplementedError")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_services.py -v -k "margin_balance or northbound" 2>&1 | tail -15`

Expected: 3 failures (DataService doesn't have these methods yet).

- [ ] **Step 4: Add the delegator methods to DataService**

Insert in `quant/services/data_service.py` after the existing `get_money_flow` method (around line 130, before `get_trading_days`):

```python
    def get_margin_balance(
        self,
        start: str,
        end: str,
        provider: Any | None = None,
        provider_name: str = "tushare",
    ) -> pd.DataFrame:
        """Return aggregated A-share margin balance through the canonical data service path."""
        data_provider = provider or self._create_provider(provider_name)

        if not hasattr(data_provider, "get_margin_balance"):
            raise NotImplementedError("Margin balance is not supported by this provider")
        return data_provider.get_margin_balance(start, end)

    def get_northbound_flow(
        self,
        start: str,
        end: str,
        provider: Any | None = None,
        provider_name: str = "tushare",
    ) -> pd.DataFrame:
        """Return daily northbound (HK→A) net inflow through the canonical data service path."""
        data_provider = provider or self._create_provider(provider_name)

        if not hasattr(data_provider, "get_northbound_flow"):
            raise NotImplementedError("Northbound flow is not supported by this provider")
        return data_provider.get_northbound_flow(start, end)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_services.py -v -k "margin_balance or northbound" 2>&1 | tail -10`

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add quant/services/data_service.py tests/unit/test_services.py
git commit -m "$(cat <<'EOF'
feat: add DataService.get_margin_balance and get_northbound_flow

Mirrors the existing get_money_flow delegator pattern; raises
NotImplementedError when the underlying provider doesn't support
the method, with unit tests via FakeDataProvider.
EOF
)"
```

---

## Task 3: AshareHistoricalIndicators

**Files:**
- Create: `quant/analysis/regime/historical_indicators.py`
- Create: `tests/unit/test_ashare_historical_indicators.py`

- [ ] **Step 1: Write the failing test file**

Create `tests/unit/test_ashare_historical_indicators.py`:

```python
"""Tests for AshareHistoricalIndicators."""
from __future__ import annotations

import pandas as pd
import pytest

from quant.analysis.regime.historical_indicators import (
    AshareHistoricalIndicators,
    IndicatorPanelConfig,
)


class _StubDataService:
    """Fake DataService — supplies deterministic margin / northbound frames."""

    def __init__(self, margin=None, northbound=None, margin_exc=None, northbound_exc=None):
        self._margin = margin
        self._northbound = northbound
        self._margin_exc = margin_exc
        self._northbound_exc = northbound_exc

    def get_margin_balance(self, start, end):
        if self._margin_exc:
            raise self._margin_exc
        return self._margin if self._margin is not None else pd.DataFrame()

    def get_northbound_flow(self, start, end):
        if self._northbound_exc:
            raise self._northbound_exc
        return self._northbound if self._northbound is not None else pd.DataFrame()


def _trading_dates(n: int, start: str = "2024-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def _margin_frame(values: list[float], dates: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": dates,
        "rzye": values,
        "rqye": [v * 0.01 for v in values],
        "total": [v * 1.01 for v in values],
    })


def _northbound_frame(net_values: list[float], dates: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": dates,
        "hgt_net": [v * 0.6 for v in net_values],
        "sgt_net": [v * 0.4 for v in net_values],
        "total_net": net_values,
    })


def test_margin_debt_trend_computes_30day_pct_change():
    dates = _trading_dates(45)
    # margin total grows 1% per trading day — 30 trading days back is roughly day 14
    values = [1.0e12 * (1.01 ** i) for i in range(45)]
    margin = _margin_frame(values, dates)
    nb = _northbound_frame([0.0] * 45, dates)
    indicators = AshareHistoricalIndicators(
        _StubDataService(margin=margin, northbound=nb),
        IndicatorPanelConfig(margin_trend_lookback_days=30),
    )

    panel = indicators.build("20240101", "20240331")
    last_value = panel["margin_debt_trend"].dropna().iloc[-1]
    # Expect roughly 1.01**30 - 1 ≈ 34.78%, allow tolerance for natural-day vs trading-day window
    assert 25.0 < last_value < 45.0


def test_northbound_flow_rolls_20_trading_days():
    dates = _trading_dates(40)
    nb_values = [5.0] * 40   # constant 5 亿 net buy per day
    nb = _northbound_frame(nb_values, dates)
    margin = _margin_frame([1.0e12] * 40, dates)
    indicators = AshareHistoricalIndicators(
        _StubDataService(margin=margin, northbound=nb),
        IndicatorPanelConfig(northbound_flow_window_days=20),
    )

    panel = indicators.build("20240101", "20240301")
    last_value = panel["northbound_flow"].dropna().iloc[-1]
    assert last_value == pytest.approx(100.0, abs=1e-6)


def test_missing_margin_data_results_in_nan_column():
    dates = _trading_dates(30)
    nb = _northbound_frame([1.0] * 30, dates)
    indicators = AshareHistoricalIndicators(
        _StubDataService(northbound=nb, margin_exc=RuntimeError("tushare 503")),
    )

    panel = indicators.build("20240101", "20240301")
    assert panel["margin_debt_trend"].isna().all()
    assert panel["northbound_flow"].notna().any()


def test_both_sources_fail_returns_empty_dataframe():
    indicators = AshareHistoricalIndicators(
        _StubDataService(
            margin_exc=RuntimeError("err1"),
            northbound_exc=RuntimeError("err2"),
        ),
    )
    panel = indicators.build("20240101", "20240301")
    assert panel.empty


def test_natural_day_index_with_ffill():
    # Two trading dates separated by a weekend
    dates = pd.to_datetime(["2024-01-05", "2024-01-08"])  # Fri, Mon
    margin = _margin_frame([1.0e12, 1.05e12], dates)
    nb = _northbound_frame([10.0, 12.0], dates)
    indicators = AshareHistoricalIndicators(_StubDataService(margin=margin, northbound=nb))

    panel = indicators.build("20240105", "20240108")
    # Saturday (2024-01-06) and Sunday (2024-01-07) should appear with ffilled values
    assert pd.Timestamp("2024-01-06") in panel.index
    assert pd.Timestamp("2024-01-07") in panel.index
    assert panel.loc[pd.Timestamp("2024-01-06"), "northbound_flow"] == panel.loc[pd.Timestamp("2024-01-05"), "northbound_flow"]


def test_config_overrides_lookback_windows():
    dates = _trading_dates(40)
    values = [1.0e12 * (1.005 ** i) for i in range(40)]
    margin = _margin_frame(values, dates)
    nb = _northbound_frame([2.0] * 40, dates)

    short_cfg = IndicatorPanelConfig(margin_trend_lookback_days=5, northbound_flow_window_days=5)
    indicators = AshareHistoricalIndicators(
        _StubDataService(margin=margin, northbound=nb), short_cfg,
    )
    panel = indicators.build("20240101", "20240301")

    # 5-day window of 2 亿 each = 10
    assert panel["northbound_flow"].dropna().iloc[-1] == pytest.approx(10.0, abs=1e-6)
    # 5-day pct change at 0.5%/day ≈ 2.52%
    assert 1.5 < panel["margin_debt_trend"].dropna().iloc[-1] < 3.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_ashare_historical_indicators.py -v 2>&1 | tail -10`

Expected: collection error (module does not exist).

- [ ] **Step 3: Implement the module**

Create `quant/analysis/regime/historical_indicators.py`:

```python
"""Historical a_shares indicator panel for cockpit regime overlay."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndicatorPanelConfig:
    """Lookback windows for historical a_shares regime indicators."""

    margin_trend_lookback_days: int = 30
    northbound_flow_window_days: int = 20


class AshareHistoricalIndicators:
    """Build a daily indicator panel for the a_shares regime classifier."""

    def __init__(self, data_service, config: IndicatorPanelConfig | None = None) -> None:
        self.data_service = data_service
        self.config = config or IndicatorPanelConfig()

    def build(self, start: str, end: str) -> pd.DataFrame:
        """Return a DataFrame indexed by natural day with columns
        ['margin_debt_trend', 'northbound_flow']. Empty if both sources fail."""
        margin_series = self._build_margin_trend(start, end)
        nb_series = self._build_northbound_window(start, end)

        if margin_series is None and nb_series is None:
            return pd.DataFrame()

        # Union of available dates, ffilled to natural day
        frames = {}
        if margin_series is not None:
            frames["margin_debt_trend"] = margin_series
        if nb_series is not None:
            frames["northbound_flow"] = nb_series

        df = pd.DataFrame(frames).sort_index()
        if df.empty:
            return df

        full_index = pd.date_range(df.index.min(), df.index.max(), freq="D")
        return df.reindex(full_index).ffill()

    def _build_margin_trend(self, start: str, end: str) -> pd.Series | None:
        try:
            raw = self.data_service.get_margin_balance(start, end)
        except Exception as exc:
            logger.warning("get_margin_balance failed: %s", exc)
            return None
        if raw is None or raw.empty or "total" not in raw.columns:
            return None

        series = (
            raw[["trade_date", "total"]]
            .dropna()
            .drop_duplicates("trade_date")
            .set_index(pd.to_datetime(raw["trade_date"]))["total"]
            .astype(float)
            .sort_index()
        )
        lookback = self.config.margin_trend_lookback_days
        # pct change over `lookback` natural days using ffill-aware shift
        # Reindex to natural days first to get day-based shift
        natural = series.reindex(pd.date_range(series.index.min(), series.index.max(), freq="D")).ffill()
        trend = (natural / natural.shift(lookback) - 1.0) * 100.0
        return trend

    def _build_northbound_window(self, start: str, end: str) -> pd.Series | None:
        try:
            raw = self.data_service.get_northbound_flow(start, end)
        except Exception as exc:
            logger.warning("get_northbound_flow failed: %s", exc)
            return None
        if raw is None or raw.empty or "total_net" not in raw.columns:
            return None

        series = (
            raw[["trade_date", "total_net"]]
            .dropna()
            .drop_duplicates("trade_date")
            .set_index(pd.to_datetime(raw["trade_date"]))["total_net"]
            .astype(float)
            .sort_index()
        )
        window = self.config.northbound_flow_window_days
        rolled = series.rolling(window=window, min_periods=window).sum()
        return rolled
```

Also create the `__init__.py` if it doesn't exist:

```bash
touch quant/analysis/regime/__init__.py 2>/dev/null || true
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_ashare_historical_indicators.py -v 2>&1 | tail -15`

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/regime/historical_indicators.py quant/analysis/regime/__init__.py tests/unit/test_ashare_historical_indicators.py
git commit -m "$(cat <<'EOF'
feat: add AshareHistoricalIndicators panel builder

Pulls margin balance + northbound flow through DataService and produces
a daily-indexed panel with margin_debt_trend (30d pct change) and
northbound_flow (20d cumulative). Source failures degrade gracefully:
missing column → NaN; both sources failing → empty DataFrame.
EOF
)"
```

---

## Task 4: CockpitRegimeOverlay

**Files:**
- Create: `quant/analysis/rotation/cockpit_overlay.py`
- Create: `tests/unit/test_cockpit_overlay.py`
- Modify: `quant/analysis/rotation/__init__.py`

- [ ] **Step 1: Write the failing test file**

Create `tests/unit/test_cockpit_overlay.py`:

```python
"""Tests for CockpitRegimeOverlay."""
from __future__ import annotations

import pandas as pd
import pytest

from quant.analysis.regime.regime_detector import RegimeDetector, RegimeState
from quant.analysis.rotation.cockpit_overlay import (
    CockpitOverlayConfig,
    CockpitRegimeOverlay,
)


class _StubIndicators:
    """Returns a pre-built panel; doesn't touch any DataService."""

    def __init__(self, panel: pd.DataFrame) -> None:
        self._panel = panel

    def build(self, start: str, end: str) -> pd.DataFrame:
        return self._panel


class _StubDetector:
    """Returns a fixed RegimeState regardless of input."""

    def __init__(self, regime: str, confidence: float = 1.0) -> None:
        self._regime = regime
        self._confidence = confidence

    def classify_pool(self, pool, indicators):
        return RegimeState(
            pool=pool,
            regime=self._regime,
            confidence=self._confidence,
            days_since_change=None,
            drivers=[f"stub regime={self._regime}"],
            updated_at="2024-01-02T00:00:00+00:00",
        )


def _make_panel(n: int = 5, start: str = "2024-01-02") -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=n, freq="D")
    return pd.DataFrame(
        {"margin_debt_trend": [3.0] * n, "northbound_flow": [60.0] * n},
        index=idx,
    )


def test_precompute_classifies_each_trading_day():
    panel = _make_panel(n=5)
    overlay = CockpitRegimeOverlay(
        data_service=None,
        regime_detector=_StubDetector("transition", 0.5),
        indicators=_StubIndicators(panel),
    )
    overlay.precompute("20240101", "20240131")
    assert len(overlay.multipliers) == 5


def test_risk_on_maps_to_1_0():
    overlay = CockpitRegimeOverlay(
        data_service=None,
        regime_detector=_StubDetector("risk-on", 0.8),
        indicators=_StubIndicators(_make_panel(3)),
    )
    overlay.precompute("20240101", "20240131")
    assert (overlay.multipliers == 1.0).all()


def test_risk_off_maps_to_0_0():
    overlay = CockpitRegimeOverlay(
        data_service=None,
        regime_detector=_StubDetector("risk-off", 0.7),
        indicators=_StubIndicators(_make_panel(3)),
    )
    overlay.precompute("20240101", "20240131")
    assert (overlay.multipliers == 0.0).all()


def test_transition_maps_to_0_5():
    overlay = CockpitRegimeOverlay(
        data_service=None,
        regime_detector=_StubDetector("transition", 0.4),
        indicators=_StubIndicators(_make_panel(3)),
    )
    overlay.precompute("20240101", "20240131")
    assert (overlay.multipliers == 0.5).all()


def test_multiplier_at_returns_latest_le_date():
    overlay = CockpitRegimeOverlay(
        data_service=None,
        regime_detector=_StubDetector("risk-on"),
        indicators=_StubIndicators(_make_panel(5, start="2024-01-02")),
    )
    overlay.precompute("20240101", "20240131")

    # 2024-01-04 (Thursday) exists; query 2024-01-05 (Friday) — index has it because
    # _make_panel uses freq=D. Test below queries an out-of-range future date.
    far_future = pd.Timestamp("2024-12-31")
    assert overlay.multiplier_at(far_future) == 1.0


def test_multiplier_at_before_series_returns_zero():
    overlay = CockpitRegimeOverlay(
        data_service=None,
        regime_detector=_StubDetector("risk-on"),
        indicators=_StubIndicators(_make_panel(3, start="2024-06-01")),
    )
    overlay.precompute("20240601", "20240630")
    assert overlay.multiplier_at(pd.Timestamp("2024-01-01")) == 0.0


def test_regime_history_property_exposes_drivers():
    overlay = CockpitRegimeOverlay(
        data_service=None,
        regime_detector=_StubDetector("risk-on", 0.9),
        indicators=_StubIndicators(_make_panel(2)),
    )
    overlay.precompute("20240101", "20240131")
    history = overlay.regime_history

    assert {"regime", "confidence", "multiplier", "drivers"}.issubset(history.columns)
    assert (history["regime"] == "risk-on").all()
    assert (history["multiplier"] == 1.0).all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cockpit_overlay.py -v 2>&1 | tail -10`

Expected: collection error (module does not exist).

- [ ] **Step 3: Implement the overlay**

Create `quant/analysis/rotation/cockpit_overlay.py`:

```python
"""Cockpit-based regime overlay (A layer) for rotation strategy."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from quant.analysis.regime.historical_indicators import AshareHistoricalIndicators
from quant.analysis.regime.regime_detector import RegimeDetector


@dataclass(frozen=True)
class CockpitOverlayConfig:
    """Configuration for CockpitRegimeOverlay."""

    pool: str = "a_shares"
    multiplier_map: dict = field(
        default_factory=lambda: {
            "risk-on": 1.0,
            "transition": 0.5,
            "risk-off": 0.0,
        }
    )


class CockpitRegimeOverlay:
    """Wrap cockpit RegimeDetector into a rotation RegimeOverlay."""

    def __init__(
        self,
        data_service,
        regime_detector: RegimeDetector | None = None,
        indicators: AshareHistoricalIndicators | None = None,
        config: CockpitOverlayConfig | None = None,
    ) -> None:
        self.data_service = data_service
        self.detector = regime_detector or RegimeDetector()
        self.indicators = indicators or AshareHistoricalIndicators(data_service)
        self.config = config or CockpitOverlayConfig()

        self.multipliers: pd.Series = pd.Series(dtype=float, name="cockpit_multiplier")
        self._history_records: list[dict] = []

    def precompute(self, start: str, end: str) -> None:
        panel = self.indicators.build(start, end)
        if panel.empty:
            self.multipliers = pd.Series(dtype=float, name="cockpit_multiplier")
            self._history_records = []
            return

        rows = []
        records = []
        for date, row in panel.iterrows():
            indicator_dict = {k: float(v) for k, v in row.items() if pd.notna(v)}
            state = self.detector.classify_pool(self.config.pool, indicator_dict)
            multiplier = self.config.multiplier_map[state.regime]
            rows.append((date, multiplier))
            records.append(
                {
                    "date": date,
                    "regime": state.regime,
                    "confidence": state.confidence,
                    "multiplier": multiplier,
                    "drivers": "; ".join(state.drivers),
                }
            )

        self.multipliers = pd.Series(
            [m for _, m in rows],
            index=[d for d, _ in rows],
            name="cockpit_multiplier",
        )
        self._history_records = records

    def multiplier_at(self, date: pd.Timestamp) -> float:
        if self.multipliers.empty:
            return 0.0
        if date < self.multipliers.index[0]:
            return 0.0
        idx = self.multipliers.index.searchsorted(date, side="right") - 1
        return float(self.multipliers.iloc[idx])

    @property
    def regime_history(self) -> pd.DataFrame:
        if not self._history_records:
            return pd.DataFrame(columns=["date", "regime", "confidence", "multiplier", "drivers"])
        return pd.DataFrame(self._history_records).set_index("date")
```

- [ ] **Step 4: Export from rotation package**

Edit `quant/analysis/rotation/__init__.py` — add to existing imports/exports:

```python
from quant.analysis.rotation.cockpit_overlay import (
    CockpitOverlayConfig,
    CockpitRegimeOverlay,
)
```

And add `"CockpitOverlayConfig"`, `"CockpitRegimeOverlay"` to `__all__` if it exists.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cockpit_overlay.py -v 2>&1 | tail -15`

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add quant/analysis/rotation/cockpit_overlay.py quant/analysis/rotation/__init__.py tests/unit/test_cockpit_overlay.py
git commit -m "$(cat <<'EOF'
feat: add CockpitRegimeOverlay

Wraps cockpit RegimeDetector(a_shares) into a RegimeOverlay-Protocol-
conforming class. Maps regime → multiplier as discrete 3-tier
{risk-on:1.0, transition:0.5, risk-off:0.0}; exposes regime_history
DataFrame for debugging and validation.
EOF
)"
```

---

## Task 5: RotationService overlay_type wiring

**Files:**
- Modify: `quant/services/rotation_service.py`
- Modify: `tests/unit/test_rotation_service.py`

- [ ] **Step 1: Write the failing test in test_rotation_service.py**

Append to existing test file (whichever class group fits):

```python
def test_unknown_overlay_type_raises():
    from quant.analysis.rotation import RankerConfig
    from quant.services.rotation_service import RotationRequest, RotationService

    service = RotationService(data_service=None)
    bad = RotationRequest(
        start="20240101",
        end="20240301",
        overlay_type="bogus",
    )
    try:
        service._build_overlay(bad)
    except ValueError as exc:
        assert "bogus" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown overlay_type")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_rotation_service.py::test_unknown_overlay_type_raises -v 2>&1 | tail -10`

Expected: AttributeError or AssertionError (no overlay_type field yet).

- [ ] **Step 3: Update RotationRequest dataclass**

Edit `quant/services/rotation_service.py` — add field to `RotationRequest`:

```python
@dataclass(frozen=True)
class RotationRequest:
    start: str
    end: str
    universe_path: Optional[str] = None
    ranker_config: Optional[RankerConfig] = None
    overlay_benchmark: str = "000300.SH"
    transaction_cost: float = 0.002
    provider: str = "auto"
    overlay_type: str = "simple"   # "simple" | "cockpit"
```

- [ ] **Step 4: Replace `_build_overlay` body to branch**

In the same file, replace the existing `_build_overlay` method:

```python
    def _build_overlay(self, request: RotationRequest):
        if request.overlay_type == "simple":
            from quant.analysis.rotation import SimpleRegimeOverlay
            overlay = SimpleRegimeOverlay(
                data_service=self.data_service,
                benchmark_symbol=request.overlay_benchmark,
            )
        elif request.overlay_type == "cockpit":
            from quant.analysis.rotation import CockpitRegimeOverlay
            # overlay_benchmark is unused in cockpit mode (no benchmark dependency)
            overlay = CockpitRegimeOverlay(data_service=self.data_service)
        else:
            raise ValueError(f"unknown overlay_type: {request.overlay_type}")
        overlay.precompute(start=request.start, end=request.end)
        return overlay
```

- [ ] **Step 5: Run rotation tests to verify nothing regressed**

Run: `uv run pytest tests/unit/test_rotation_service.py -v 2>&1 | tail -10`

Expected: all tests pass (existing 3 + new 1 = 4).

- [ ] **Step 6: Commit**

```bash
git add quant/services/rotation_service.py tests/unit/test_rotation_service.py
git commit -m "$(cat <<'EOF'
feat: route RotationRequest.overlay_type to simple or cockpit overlay

Adds overlay_type field defaulting to "simple" so existing callers
keep current behavior; cockpit is opt-in. Unknown overlay_type raises
ValueError instead of silently degrading.
EOF
)"
```

---

## Task 6: CLI --overlay flag

**Files:**
- Modify: `quant/cli/rotation.py`

- [ ] **Step 1: Add the CLI argument**

In `_add_common_args` function (around line 39), add:

```python
    parser.add_argument(
        "--overlay",
        choices=["simple", "cockpit"],
        default="simple",
        help="风险 overlay 选择，默认 simple；cockpit 用 RegimeDetector(a_shares)",
    )
```

- [ ] **Step 2: Pass through to RotationRequest in `_build_request`**

In `_build_request` function, add `overlay_type=args.overlay,` to the `RotationRequest(...)` constructor call:

```python
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
        overlay_type=args.overlay,
    )
```

- [ ] **Step 3: Update the print line in handle_rotation_backtest**

Update the `print(f"区间: ...")` line (around line 76) to include overlay info:

```python
    print(f"区间: {args.start} - {args.end}  benchmark: {args.benchmark}  top-K: {args.top_k}  overlay: {args.overlay}")
```

- [ ] **Step 4: Smoke-test that --help shows the new flag**

Run: `uv run python -m quant rotation backtest --help 2>&1 | grep -i overlay`

Expected: lines mentioning `--overlay` and choices.

- [ ] **Step 5: Commit**

```bash
git add quant/cli/rotation.py
git commit -m "$(cat <<'EOF'
feat: add --overlay {simple,cockpit} flag to rotation CLI

Defaults to "simple" so existing usage is unchanged; cockpit selects
the new CockpitRegimeOverlay via RotationRequest.overlay_type.
EOF
)"
```

---

## Task 7: Integration test — rotation pipeline with cockpit overlay

**Files:**
- Modify: `tests/integration/test_rotation_pipeline.py`

- [ ] **Step 1: Extend the deterministic data service stub**

In `tests/integration/test_rotation_pipeline.py`, add to `_DeterministicDataService` class (after `get_trading_days`):

```python
    def get_margin_balance(self, start, end):
        dates = pd.date_range("2018-01-02", "2024-12-31", freq="B")
        # Slowly rising margin → margin_debt_trend stays positive (risk-on bias)
        values = [1.0e12 * (1.0001 ** i) for i in range(len(dates))]
        return pd.DataFrame({
            "trade_date": dates,
            "rzye": values,
            "rqye": [v * 0.01 for v in values],
            "total": [v * 1.01 for v in values],
        })

    def get_northbound_flow(self, start, end):
        dates = pd.date_range("2018-01-02", "2024-12-31", freq="B")
        # Constant 3 亿 net buy/day → 20-day window = 60 → above risk_on_above=50.0
        return pd.DataFrame({
            "trade_date": dates,
            "hgt_net": [2.0] * len(dates),
            "sgt_net": [1.0] * len(dates),
            "total_net": [3.0] * len(dates),
        })
```

- [ ] **Step 2: Add the integration test**

Append to the test file:

```python
def test_pipeline_runs_with_cockpit_overlay() -> None:
    service = RotationService(data_service=_DeterministicDataService())
    request = RotationRequest(
        start="2018-01-01",
        end="2023-12-31",
        universe_path=str(_DEFAULT_UNIVERSE),
        ranker_config=RankerConfig(top_k=5),
        transaction_cost=0.002,
        overlay_type="cockpit",
    )
    result = service.run_backtest(request)

    assert len(result.equity_curve) >= 60
    assert {"strategy", "benchmark", "equal_weight"} == set(result.equity_curve.columns)
    nonzero_per_row = (result.holdings != 0).sum(axis=1)
    assert nonzero_per_row.max() <= 5
```

- [ ] **Step 3: Run full rotation test suite**

Run: `uv run pytest tests/unit/test_rotation_*.py tests/unit/test_ashare_historical_indicators.py tests/unit/test_cockpit_overlay.py tests/integration/test_rotation_pipeline.py -q 2>&1 | tail -15`

Expected: all pass (34 existing rotation + 6 indicators + 7 cockpit + 1 new integration = 48).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_rotation_pipeline.py
git commit -m "$(cat <<'EOF'
test: add cockpit overlay integration test for rotation pipeline

Extends _DeterministicDataService with synthetic margin/northbound
series so RotationService.run_backtest(overlay_type="cockpit")
runs end-to-end without external data dependencies.
EOF
)"
```

---

## Task 8: Real-data validation script (one-off, not committed)

This step is a manual validation per spec §7.3 — output is a `/tmp/cockpit_overlay_validation.py` script and a one-paragraph findings note. The script does not enter the repo.

**Files:**
- Create: `/tmp/cockpit_overlay_validation.py` (NOT committed)

- [ ] **Step 1: Write the validation script**

Create `/tmp/cockpit_overlay_validation.py`:

```python
"""Validate CockpitRegimeOverlay vs SimpleRegimeOverlay on 2018-2024 real data.

Goals:
  1. Confirm cockpit overlay actually runs on real Tushare data
  2. Look at indicator distribution vs configured thresholds (per spec §9 risk)
  3. Compare backtest metrics vs simple overlay
"""
from __future__ import annotations

import pandas as pd

from quant.analysis.regime.historical_indicators import AshareHistoricalIndicators
from quant.analysis.rotation.cockpit_overlay import CockpitRegimeOverlay
from quant.services.data_service import DataService
from quant.services.rotation_service import RotationRequest, RotationService

START = "20180101"
END = "20241231"


def inspect_indicator_distribution():
    print("\n=== INDICATOR DISTRIBUTION (vs yaml thresholds) ===")
    panel = AshareHistoricalIndicators(DataService()).build(START, END)
    print(panel.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).to_string())
    print("\nyaml thresholds:")
    print("  margin_debt_trend  risk_on_above=2.0   risk_off_below=-3.0")
    print("  northbound_flow    risk_on_above=50.0  risk_off_below=-80.0")


def overlay_regime_breakdown():
    print("\n=== REGIME BREAKDOWN (cockpit overlay, full period) ===")
    overlay = CockpitRegimeOverlay(DataService())
    overlay.precompute(START, END)
    if overlay.regime_history.empty:
        print("  EMPTY history — investigate before continuing")
        return
    print(overlay.regime_history["regime"].value_counts(normalize=True).to_string())
    print(f"\n  multiplier mean: {overlay.multipliers.mean():.3f}")
    print(f"  multiplier std:  {overlay.multipliers.std():.3f}")


def compare_backtests():
    print("\n=== BACKTEST COMPARE (simple vs cockpit, K=3, lookback=6) ===")
    svc = RotationService()
    rows = []
    for kind in ("simple", "cockpit"):
        req = RotationRequest(start=START, end=END, overlay_type=kind)
        result = svc.run_backtest(req)
        m = result.metrics
        rows.append({
            "overlay": kind,
            "total_return": f"{m['total_return_strategy']*100:+.2f}%",
            "annual": f"{m['annual_return_strategy']*100:+.2f}%",
            "MDD": f"{m['max_drawdown_strategy']*100:+.2f}%",
            "Sharpe": m["sharpe_strategy"],
        })
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    inspect_indicator_distribution()
    overlay_regime_breakdown()
    compare_backtests()
```

- [ ] **Step 2: Run the validation script**

Run: `uv run python /tmp/cockpit_overlay_validation.py 2>&1 | grep -v "INFO" | tail -40`

Expected: 3 sections of output. Look for:
- Indicator distribution: do the percentiles bracket the yaml thresholds reasonably, or are they all on one side (suggesting threshold recalibration needed)?
- Regime breakdown: should NOT be 100% transition. If it is, thresholds need adjustment.
- Backtest compare: is cockpit Sharpe ≥ simple Sharpe? If significantly worse, document and decide whether to keep or revert default.

- [ ] **Step 3: Document findings**

If cockpit beats simple cleanly: report and consider flipping the default in a follow-up commit (separate decision).

If cockpit underperforms or thresholds need recalibration: open a follow-up note in `docs/superpowers/specs/2026-05-02-cockpit-rotation-overlay-design.md` §9 with the actual distribution data; do NOT change defaults.

Either way, no commit at this step — the validation output goes back to the user as a summary.

---

## Self-Review Checklist

**Spec coverage:**
- §3.1 DataService extension → Task 2 ✓
- §3.2 TushareProvider methods → Task 1 ✓
- §3.3 AshareHistoricalIndicators → Task 3 ✓
- §3.4 CockpitRegimeOverlay → Task 4 ✓
- §3.5 RotationService + CLI → Tasks 5, 6 ✓
- §6 Error handling → covered in Task 3 (NaN/empty) and Task 4 (empty multipliers/risk-off=0) and Task 5 (ValueError) ✓
- §7.1 Unit tests → Tasks 2/3/4/5 ✓
- §7.2 Integration test → Task 7 ✓
- §7.3 Manual validation → Task 8 ✓
- §9 Risk #2 (threshold distribution) → Task 8 step 2 explicitly inspects this ✓

**Type/name consistency:**
- `IndicatorPanelConfig`, `AshareHistoricalIndicators`, `CockpitOverlayConfig`, `CockpitRegimeOverlay` — same names everywhere ✓
- `multiplier_map` keys `risk-on/transition/risk-off` match `_POOL_LABELS["a_shares"]` in regime_detector.py ✓
- DataService method signatures `(start, end, provider=None, provider_name="tushare")` consistent across both new methods + match existing `get_money_flow` ✓
- Column schemas: margin frame `(trade_date, rzye, rqye, total)`, northbound frame `(trade_date, hgt_net, sgt_net, total_net)` consistent across provider, service, and stub ✓

**Placeholder scan:**
- No TBD/TODO ✓
- All test code is concrete ✓
- All commands are runnable as written ✓
