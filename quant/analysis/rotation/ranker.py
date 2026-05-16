"""Cross-sectional momentum ranker for rotation universe."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RankerConfig:
    """Parameters for cross-sectional momentum ranking."""

    lookback_months: int = 6
    skip_recent_months: int = 1
    top_k: int = 3
    cash_threshold: float = 0.0
    vol_penalty: float = 0.0  # penalty coefficient; see vol_formula for usage
    vol_lookback_months: int = 0  # 0 = same as lookback_months; used for linear_subtract formula
    vol_formula: str = "exponent"  # "exponent": score=mom/vol^penalty; "linear_subtract": score=mom-penalty*vol_annualized


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

        score: dict[str, float] = {}
        for symbol in monthly_prices.columns:
            p_start = start_row[symbol]
            p_end = end_row[symbol]
            if pd.isna(p_start) or pd.isna(p_end) or p_start <= 0:
                continue
            mom = float(p_end / p_start - 1.0)
            if self.config.vol_penalty != 0.0:
                if self.config.vol_formula == "linear_subtract":
                    vol_lb = self.config.vol_lookback_months if self.config.vol_lookback_months > 0 else lookback
                    vol_start_idx = max(0, end_idx - vol_lb)
                    price_slice = monthly_prices[symbol].iloc[vol_start_idx: end_idx + 1].dropna()
                    if len(price_slice) >= 2:
                        monthly_rets = price_slice.pct_change().dropna()
                        vol_monthly = float(monthly_rets.std(ddof=1))
                        vol_adj = vol_monthly * float(np.sqrt(12))
                    else:
                        vol_adj = 0.0
                    score[symbol] = mom - self.config.vol_penalty * vol_adj
                else:
                    # Original exponent formula: score = mom / vol^vol_penalty
                    price_slice = monthly_prices[symbol].iloc[start_idx: end_idx + 1].dropna()
                    if len(price_slice) >= 2:
                        monthly_rets = price_slice.pct_change().dropna()
                        vol = float(monthly_rets.std(ddof=1))
                    else:
                        vol = 0.0
                    adj_vol = max(vol, 1e-6) ** self.config.vol_penalty
                    score[symbol] = mom / adj_vol
            else:
                score[symbol] = mom

        if not score:
            return {}

        ranked = sorted(score.items(), key=lambda kv: kv[1], reverse=True)
        top = ranked[: self.config.top_k]

        if np.mean([s for _, s in top]) < self.config.cash_threshold:
            return {}

        weight = 1.0 / len(top)
        return {sym: weight for sym, _ in top}


# ---------------------------------------------------------------------------
# Multi-factor cross-sectional percentile rank ranker
# ---------------------------------------------------------------------------

def _cross_sectional_percentile_rank(
    scores: dict[str, float],
    higher_is_better: bool = True,
) -> dict[str, float]:
    """Map raw scores to percentile rank in [0, 1]; 1.0 = best for selection."""
    n = len(scores)
    if n == 0:
        return {}
    if n == 1:
        return {k: 1.0 for k in scores}
    symbols = list(scores.keys())
    values = np.array([scores[s] for s in symbols], dtype=float)
    order = np.argsort(values)  # ascending: order[0] = index of smallest
    ranks = np.empty(n, dtype=float)
    for rank_pos, orig_idx in enumerate(order):
        ranks[orig_idx] = rank_pos / (n - 1)
    if not higher_is_better:
        ranks = 1.0 - ranks
    return {symbols[i]: float(ranks[i]) for i in range(n)}


class MultiFactorRanker:
    """Rank universe by weighted composite of cross-sectional percentile ranks.

    Supported factors: momentum, low_volatility, low_crowding.
    When ``monthly_volumes`` is None, low_crowding is silently dropped and
    the remaining factor weights are renormalized (momentum 0.625, vol 0.375).

    ``monthly_benchmark`` enables conditional_gating: when CSI300 3m return
    exceeds the configured threshold, factor weights are temporarily overridden
    by gated_weights (e.g. momentum boosted to 0.9 in strong-trend periods).
    """

    def __init__(
        self,
        risk_on_allocation: dict,
        monthly_volumes: Optional[pd.DataFrame] = None,
        monthly_benchmark: Optional[pd.Series] = None,
    ) -> None:
        self._alloc = risk_on_allocation
        self._volumes = monthly_volumes
        self._benchmark = monthly_benchmark
        cfg = risk_on_allocation.get("multi_factor_config", {})
        self._factors: list[dict] = cfg.get("factors", [])
        self._cg: dict = cfg.get("conditional_gating", {})
        self._top_k: int = int(risk_on_allocation.get("top_k", 3))

    def _effective_weights(self, rebalance_date: pd.Timestamp) -> dict[str, float]:
        """Return per-factor weights, applying conditional_gating if triggered."""
        base = {f["name"]: float(f.get("weight", 0.0)) for f in self._factors}
        if not self._cg.get("enabled") or self._benchmark is None:
            return base
        lb = int(self._cg.get("condition_lookback_months", 3))
        bench = self._benchmark
        if rebalance_date not in bench.index:
            return base
        loc = bench.index.get_loc(rebalance_date)
        start_idx = loc - lb
        if start_idx < 0:
            return base
        p0, p1 = bench.iloc[start_idx], bench.iloc[loc]
        if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
            return base
        ret = float(p1 / p0 - 1.0)
        try:
            threshold = float(self._cg.get("condition", "").split(">")[1].strip())
        except Exception:
            threshold = 0.08
        if ret > threshold:
            gated = self._cg.get("gated_weights", {})
            return {f["name"]: float(gated.get(f["name"], f.get("weight", 0.0))) for f in self._factors}
        return base

    def rank(
        self,
        monthly_prices: pd.DataFrame,
        rebalance_date: pd.Timestamp,
    ) -> dict[str, float]:
        if rebalance_date not in monthly_prices.index:
            raise KeyError(f"rebalance_date {rebalance_date} not in price index")
        loc = monthly_prices.index.get_loc(rebalance_date)

        raw: dict[str, dict[str, float]] = {}
        for factor in self._factors:
            name = factor["name"]
            scores = self._compute_factor(factor, monthly_prices, loc)
            if scores:
                raw[name] = scores

        if not raw:
            return {}

        # Only symbols present in ALL available factors
        valid: set[str] = set(monthly_prices.columns)
        for scores in raw.values():
            valid &= scores.keys()
        if not valid:
            return {}

        weights = self._effective_weights(rebalance_date)
        composite: dict[str, float] = {s: 0.0 for s in valid}
        total_weight = 0.0

        for factor in self._factors:
            name = factor["name"]
            if name not in raw:
                continue
            weight = weights.get(name, 0.0)
            if weight <= 0:
                continue
            higher = factor.get("direction", "higher_is_better") == "higher_is_better"
            filtered = {s: raw[name][s] for s in valid}
            ranked = _cross_sectional_percentile_rank(filtered, higher)
            for s, r in ranked.items():
                composite[s] += weight * r
            total_weight += weight

        if total_weight <= 0:
            return {}
        composite = {s: v / total_weight for s, v in composite.items()}

        top = sorted(composite.items(), key=lambda kv: kv[1], reverse=True)[: self._top_k]
        if not top:
            return {}
        w = 1.0 / len(top)
        return {sym: w for sym, _ in top}

    def _compute_factor(
        self, factor: dict, monthly_prices: pd.DataFrame, loc: int
    ) -> dict[str, float]:
        name = factor["name"]
        if name == "momentum":
            return self._momentum(factor, monthly_prices, loc)
        if name == "low_volatility":
            return self._low_volatility(factor, monthly_prices, loc)
        if name == "low_crowding":
            return self._low_crowding(factor, monthly_prices, loc)
        if name == "relative_strength":
            return self._relative_strength(factor, monthly_prices, loc)
        return {}

    def _momentum(self, factor: dict, prices: pd.DataFrame, loc: int) -> dict[str, float]:
        skip = int(factor.get("skip_months", 1))
        lb = int(factor.get("lookback_months", 6))
        end_idx = loc - skip
        start_idx = end_idx - lb
        if start_idx < 0 or end_idx < 0:
            return {}
        end_row = prices.iloc[end_idx]
        start_row = prices.iloc[start_idx]
        scores: dict[str, float] = {}
        for sym in prices.columns:
            p0, p1 = start_row[sym], end_row[sym]
            if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
                continue
            scores[sym] = float(p1 / p0 - 1.0)
        return scores

    def _low_volatility(self, factor: dict, prices: pd.DataFrame, loc: int) -> dict[str, float]:
        lb = int(factor.get("lookback_months", 3))
        skip = int(factor.get("skip_months", 0))
        end_idx = loc - skip
        start_idx = max(0, end_idx - lb)
        if end_idx <= 0:
            return {}
        scores: dict[str, float] = {}
        for sym in prices.columns:
            sl = prices[sym].iloc[start_idx: end_idx + 1].dropna()
            if len(sl) < 2:
                continue
            rets = sl.pct_change().dropna()
            if len(rets) < 2:
                continue
            scores[sym] = float(rets.std(ddof=1)) * float(np.sqrt(12))
        return scores

    def _relative_strength(self, factor: dict, prices: pd.DataFrame, loc: int) -> dict[str, float]:
        """Excess return vs CSI300 benchmark over the same lookback window."""
        if self._benchmark is None:
            return {}
        skip = int(factor.get("skip_months", 1))
        lb = int(factor.get("lookback_months", 6))
        end_idx = loc - skip
        start_idx = end_idx - lb
        if start_idx < 0 or end_idx < 0:
            return {}

        rebalance_date = prices.index[loc]
        bench = self._benchmark
        if rebalance_date not in bench.index:
            return {}
        bench_loc = bench.index.get_loc(rebalance_date)
        bench_end_idx = bench_loc - skip
        bench_start_idx = bench_end_idx - lb
        if bench_start_idx < 0 or bench_end_idx < 0:
            return {}
        b0, b1 = bench.iloc[bench_start_idx], bench.iloc[bench_end_idx]
        if pd.isna(b0) or pd.isna(b1) or b0 <= 0:
            return {}
        bench_ret = float(b1 / b0 - 1.0)

        end_row = prices.iloc[end_idx]
        start_row = prices.iloc[start_idx]
        scores: dict[str, float] = {}
        for sym in prices.columns:
            p0, p1 = start_row[sym], end_row[sym]
            if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
                continue
            scores[sym] = float(p1 / p0 - 1.0) - bench_ret
        return scores

    def _low_crowding(self, factor: dict, prices: pd.DataFrame, loc: int) -> dict[str, float]:
        if self._volumes is None:
            return {}
        rebalance_date = prices.index[loc]
        if rebalance_date not in self._volumes.index:
            return {}
        vol_loc = self._volumes.index.get_loc(rebalance_date)
        recent_lb = int(factor.get("lookback_months", 1))
        norm_lb = int(factor.get("norm_lookback_months", 12))
        recent_start = max(0, vol_loc - recent_lb + 1)
        norm_start = max(0, vol_loc - norm_lb + 1)
        scores: dict[str, float] = {}
        for sym in prices.columns:
            if sym not in self._volumes.columns:
                continue
            recent_sl = self._volumes[sym].iloc[recent_start: vol_loc + 1].dropna()
            norm_sl = self._volumes[sym].iloc[norm_start: vol_loc + 1].dropna()
            if len(recent_sl) < 1 or len(norm_sl) < 1:
                continue
            norm_mean = float(norm_sl.mean())
            if norm_mean <= 0:
                continue
            scores[sym] = float(recent_sl.mean()) / norm_mean
        return scores


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
