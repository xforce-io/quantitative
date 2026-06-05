"""Unit tests for UnifiedGridTradingStrategy lifecycle.

These guard the print->logging migration: the strategy must construct and
run its grid setup without referencing an undefined module-level ``logger``.
"""

import pandas as pd
import pytest

from quant.strategies.unified_grid_strategy import UnifiedGridTradingStrategy


def test_strategy_constructs_without_logger_nameerror():
    """Constructing the strategy must not raise (regression: bare ``logger``)."""
    strategy = UnifiedGridTradingStrategy(
        "688525.SH",
        {"gridLevels": 5, "maxPosition": 100000},
    )
    assert strategy.symbol == "688525.SH"
    assert strategy.gridLevels == 5


def test_exposes_engine_cash_position_contract():
    """Grid strategy must expose ``cash``/``position`` like other makeDecision
    strategies, so BacktestEngine's new-interface branch can read them."""
    strategy = UnifiedGridTradingStrategy("688525.SH", {"gridLevels": 5})
    strategy.reset(100000.0)
    assert strategy.cash == strategy.currentCash == 100000.0
    assert strategy.position == strategy.currentPosition == 0


def test_grid_setup_runs_through_logging_paths():
    """Grid initialization should execute its logging branches cleanly.

    Exercises the setup path that contains the ``end=" "`` kwarg defect and
    the missing f-string interpolations.
    """
    strategy = UnifiedGridTradingStrategy(
        "688525.SH",
        {"gridLevels": 5, "maxPosition": 100000, "baseRatio": 0.3},
    )
    prices = pd.Series([10.0 + (i % 5) * 0.1 for i in range(30)])
    # Exercises _establishBasePosition / _setupGridsAroundCenter, which hold
    # the f-string and `end=" "` defects left by the print->logging migration.
    strategy.setupGrids(float(prices.iloc[-1]))


def test_zero_trades_still_reports_base_position_return():
    """With 0 grid trades, an appreciated base position must still yield a
    non-zero totalReturn (regression: ``not self.trades`` zeroed real gains)."""
    strategy = UnifiedGridTradingStrategy("688525.SH", {"gridLevels": 5})
    strategy.reset(100000.0)
    # Base position rode the trend up; no grid round-trips executed.
    strategy.totalValue = 178255.20
    strategy.trades = []
    metrics = strategy.getPerformanceMetrics(100000.0)
    assert metrics["totalTrades"] == 0
    assert metrics["totalReturn"] == pytest.approx(0.7825520, rel=1e-6)
