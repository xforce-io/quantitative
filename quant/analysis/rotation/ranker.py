"""Cross-sectional momentum ranker for rotation universe."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RankerConfig:
    """Parameters for cross-sectional momentum ranking."""

    lookback_months: int = 6
    skip_recent_months: int = 1
    top_k: int = 3
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

        end_idx = loc - skip
        start_idx = end_idx - lookback
        if start_idx < 0 or end_idx < 0:
            return {}

        end_row = monthly_prices.iloc[end_idx]
        start_row = monthly_prices.iloc[start_idx]

        momentum: dict[str, float] = {}
        for symbol in monthly_prices.columns:
            p_start = start_row[symbol]
            p_end = end_row[symbol]
            if pd.isna(p_start) or pd.isna(p_end) or p_start <= 0:
                continue
            momentum[symbol] = float(p_end / p_start - 1.0)

        if not momentum:
            return {}

        ranked = sorted(momentum.items(), key=lambda kv: kv[1], reverse=True)
        top = ranked[: self.config.top_k]

        if np.mean([m for _, m in top]) < self.config.cash_threshold:
            return {}

        weight = 1.0 / len(top)
        return {sym: weight for sym, _ in top}
