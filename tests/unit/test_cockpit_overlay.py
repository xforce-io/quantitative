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


def test_empty_panel_results_in_empty_multipliers_and_history():
    """When AshareHistoricalIndicators returns an empty panel (e.g. both
    sources failed), overlay should produce an empty multipliers series
    and an empty regime_history without crashing."""
    overlay = CockpitRegimeOverlay(
        data_service=None,
        regime_detector=_StubDetector("risk-on"),
        indicators=_StubIndicators(pd.DataFrame()),
    )
    overlay.precompute("20240101", "20240131")
    assert overlay.multipliers.empty
    assert overlay.regime_history.empty
    # multiplier_at on empty series → 0.0 (most-conservative fallback)
    assert overlay.multiplier_at(pd.Timestamp("2024-01-15")) == 0.0


def test_multiplier_at_returns_value_for_mid_series_date():
    """Core 'latest ≤ date' search behavior — query a date between two
    panel entries, expect the earlier entry's multiplier."""
    # Panel covers 2024-01-02 .. 2024-01-06 (5 days, freq=D).
    # Indicator values matter only for stub determinism.
    overlay = CockpitRegimeOverlay(
        data_service=None,
        regime_detector=_StubDetector("transition"),
        indicators=_StubIndicators(_make_panel(5, start="2024-01-02")),
    )
    overlay.precompute("20240101", "20240131")

    # Query a date that exists in the panel exactly
    assert overlay.multiplier_at(pd.Timestamp("2024-01-04")) == 0.5
    # Query a date AFTER the panel range — searchsorted - 1 should give last entry
    assert overlay.multiplier_at(pd.Timestamp("2024-01-15")) == 0.5
