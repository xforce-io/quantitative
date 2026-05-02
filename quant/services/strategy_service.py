"""Strategy application service shared by CLI and web entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from quant.core.config import get_config
from quant.engines.backtest_engine import BacktestEngine
from quant.strategies import STRATEGY_REGISTRY


@dataclass(frozen=True)
class StrategyBacktestRequest:
    """Input model for a strategy backtest run."""

    strategy_name: str
    symbol: str
    start: str = "20230101"
    end: str = "20241201"
    initial_capital: float = 100000.0
    strategy_config: Dict[str, Any] | None = None


class StrategyService:
    """Provide strategy discovery and backtest orchestration."""

    def list_strategies(self) -> List[Dict[str, str]]:
        """Return registered strategy metadata."""
        strategies = []
        for name, strategy_class in STRATEGY_REGISTRY.items():
            doc = strategy_class.__doc__ or ""
            description = doc.strip().splitlines()[0] if doc.strip() else "No description"
            strategies.append(
                {
                    "name": name,
                    "class": strategy_class.__name__,
                    "description": description,
                }
            )
        return strategies

    def get_strategy_config(self, strategy_name: str) -> Dict[str, Any] | None:
        """Return configured defaults for a registered strategy."""
        config = get_config()
        strategy_config = config.get_strategy_config(strategy_name)
        if strategy_config is None:
            return None
        return dict(strategy_config)

    def run_backtest(self, request: StrategyBacktestRequest) -> Dict[str, Any]:
        """Run a backtest through the current canonical CLI strategy path."""
        if request.strategy_name not in STRATEGY_REGISTRY:
            available = ", ".join(STRATEGY_REGISTRY.keys())
            raise ValueError(
                f"Unknown strategy '{request.strategy_name}'. Available strategies: {available}"
            )

        strategy_class = STRATEGY_REGISTRY[request.strategy_name]
        strategy_config = (
            dict(request.strategy_config)
            if request.strategy_config is not None
            else self.get_strategy_config(request.strategy_name)
        )
        strategy = strategy_class(request.symbol, strategy_config)

        engine = BacktestEngine("auto")
        return engine.runBacktest(
            request.symbol,
            request.start,
            request.end,
            initialCapital=request.initial_capital,
            strategyConfig=strategy_config,
            strategy=strategy,
        )
