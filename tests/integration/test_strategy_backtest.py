"""
Integration tests for strategy + backtest pipeline.

Validates: strategy.reset() -> feed market data -> get metrics.
No network calls — uses synthetic data from fixtures.
"""

import pytest
import pandas as pd
import numpy as np

from quant.strategies.base_strategy import MarketState, TradingDecision
from quant.strategies.ma_crossover_strategy import MACrossoverStrategy


class TestMACrossoverFullCycle:
    """Run MACrossoverStrategy through a complete backtest cycle."""

    @pytest.fixture
    def strategy(self):
        return MACrossoverStrategy(
            "000001.SZ",
            {
                "ma_short": 5,
                "ma_long": 10,
                "commission": 0.0003,
                "slippage": 0.001,
                "position_size": 0.9,
                "verbose_logging": False,
            },
        )

    def test_full_backtest_cycle(self, strategy, realistic_stock_data):
        """Strategy should process all bars and produce valid metrics."""
        strategy.reset(100_000.0)

        for timestamp, row in realistic_stock_data.iterrows():
            strategy.on_market_data(timestamp, row["close"], row["volume"])

        metrics = strategy.get_performance_metrics()

        # Basic sanity checks on metrics
        assert "totalReturn" in metrics
        assert "totalTrades" in metrics
        assert "totalValue" in metrics
        assert metrics["totalValue"] > 0
        assert isinstance(metrics["totalReturn"], float)

    def test_strategy_generates_trades(self, strategy, realistic_stock_data):
        """With 6 months of data, MA crossover should generate at least some trades."""
        strategy.reset(100_000.0)

        for timestamp, row in realistic_stock_data.iterrows():
            strategy.on_market_data(timestamp, row["close"], row["volume"])

        assert len(strategy.trades) > 0, "Strategy should generate at least one trade over 6 months"

    def test_cash_plus_position_equals_total_value(self, strategy, realistic_stock_data):
        """Portfolio accounting: cash + position * price == total_value."""
        strategy.reset(100_000.0)

        last_price = None
        for timestamp, row in realistic_stock_data.iterrows():
            strategy.on_market_data(timestamp, row["close"], row["volume"])
            last_price = row["close"]

        expected_total = strategy.current_cash + strategy.current_position * last_price
        assert abs(strategy.total_value - expected_total) < 0.01

    def test_no_negative_cash(self, strategy, realistic_stock_data):
        """Cash should never go negative during a backtest run."""
        strategy.reset(100_000.0)

        for timestamp, row in realistic_stock_data.iterrows():
            strategy.on_market_data(timestamp, row["close"], row["volume"])
            assert strategy.current_cash >= 0, (
                f"Negative cash {strategy.current_cash} at {timestamp}"
            )


class TestStrategyReset:
    """Test that strategy reset properly clears all state."""

    def test_reset_clears_state(self, realistic_stock_data):
        strategy = MACrossoverStrategy(
            "000001.SZ",
            {"ma_short": 5, "ma_long": 10, "verbose_logging": False},
        )

        # Run first time
        strategy.reset(100_000.0)
        for timestamp, row in realistic_stock_data.iterrows():
            strategy.on_market_data(timestamp, row["close"], row["volume"])
        trades_first = len(strategy.trades)
        assert trades_first > 0

        # Reset and run again — should produce identical results (same seed data)
        strategy.reset(100_000.0)
        assert len(strategy.trades) == 0
        assert strategy.current_cash == 100_000.0
        assert strategy.current_position == 0

        for timestamp, row in realistic_stock_data.iterrows():
            strategy.on_market_data(timestamp, row["close"], row["volume"])
        trades_second = len(strategy.trades)
        assert trades_second == trades_first


class TestMakeDecisionInterface:
    """Test the BaseStrategy.makeDecision() interface."""

    def test_make_decision_returns_trading_decision(self, realistic_stock_data):
        strategy = MACrossoverStrategy(
            "000001.SZ",
            {"ma_short": 5, "ma_long": 10, "verbose_logging": False},
        )
        strategy.reset(100_000.0)

        for timestamp, row in realistic_stock_data.iterrows():
            market_state = MarketState(
                timestamp=timestamp,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
            decision = strategy.makeDecision(market_state)

            assert isinstance(decision, TradingDecision)
            assert decision.action in ("buy", "sell", "hold")
            assert isinstance(decision.amount, (int, float))
            assert isinstance(decision.reason, str)
