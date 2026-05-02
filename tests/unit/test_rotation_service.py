"""Tests for RotationService."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

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


def test_default_universe_path_used_when_omitted() -> None:
    fake = _FakeDataService({})
    service = RotationService(data_service=fake)
    request = RotationRequest(start="2018-01-01", end="2024-12-31")
    result = service.run_backtest(request)
    assert "annual_return_strategy" in result.metrics


def test_unknown_overlay_type_raises():
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
