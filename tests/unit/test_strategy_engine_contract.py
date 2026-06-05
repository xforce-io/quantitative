"""Contract tests: every makeDecision strategy must expose engine-facing
``cash``/``position`` and actually execute trades inside ``makeDecision``.

BacktestEngine/BacktestExecutor never apply the returned decision themselves;
they read ``strategy.cash`` / ``strategy.position`` after each bar, so a
strategy that only emits a signal without mutating its own ledger silently
produces a 0-trade, 0-return backtest (or crashes with AttributeError).
"""

import numpy as np
import pytest

from quant.strategies.base_strategy import MarketState
from quant.strategies.ma_crossover_strategy import MACrossoverStrategy
from quant.strategies.momentum_strategy import MomentumStrategy
from quant.strategies.seykota_ma_strategy import SeyKotaMAStrategy

STRATEGIES = [
    (MACrossoverStrategy, {"ma_short": 2, "ma_long": 3, "verbose_logging": False}),
    (MomentumStrategy, {"momentum_period": 3}),
    (SeyKotaMAStrategy, {"ma_short": 2, "ma_long": 3, "atr_period": 3, "trend_strength": 3}),
]


@pytest.mark.parametrize("cls,config", STRATEGIES)
def test_exposes_cash_position_contract(cls, config):
    strategy = cls("688525.SH", config)
    strategy.reset(100000.0)
    assert strategy.cash == strategy.current_cash == 100000.0
    assert strategy.position == strategy.current_position == 0


def _drive(strategy, prices):
    """Feed a price path through makeDecision (mirrors the engine loop)."""
    import pandas as pd

    ts = pd.Timestamp("2024-01-01")
    for i, px in enumerate(prices):
        ms = MarketState(
            timestamp=ts + pd.Timedelta(days=i),
            open=px, high=px * 1.02, low=px * 0.98, close=px,
            volume=1_000_000.0,
        )
        strategy.makeDecision(ms)
    return strategy


@pytest.mark.parametrize("cls,config", STRATEGIES)
def test_makedecision_self_executes(cls, config):
    """An oscillating series produces MA crossings; makeDecision must execute
    them against the ledger (regression: it only emitted signals before)."""
    strategy = cls("688525.SH", config)
    strategy.reset(100000.0)
    # Sine oscillation guarantees repeated crossings for every strategy's signal.
    prices = 20.0 + 8.0 * np.sin(2 * np.pi * np.arange(96) / 12)
    _drive(strategy, list(prices))
    assert len(strategy.trades) > 0, "makeDecision did not execute any trade"
