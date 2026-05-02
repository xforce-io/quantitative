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
        strategy_returns: list[float] = []

        monthly_universe_ret = universe_prices.pct_change().fillna(0.0)

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

            this_month_ret = monthly_universe_ret.loc[date]
            gross = float((prev_positions * this_month_ret).sum())
            net = gross - turnover * self.config.transaction_cost
            strategy_returns.append(net)

            positions_history.append(new_positions.copy())
            prev_positions = new_positions

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
