#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SignalValidator — walk-forward hit-rate calculation for registered signals.

For each signal definition it replays the entry condition on historical price
data, measures the forward return at the configured horizon, and computes:
  - hit_rate     : fraction of firings that moved in the expected direction
  - avg_return   : mean forward return across all firings
  - sample_size  : number of qualifying signal fires

Conditions that require external / non-price data (e.g. composite scores,
margin data, credit spreads) are marked None and produce empty validations.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Callable, Dict, Optional

import pandas as pd

from quant.core.indicators import add_technical_indicators
from quant.analysis.signals.signal_registry import SignalDefinition, SignalValidation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Condition evaluators
# ---------------------------------------------------------------------------

# Each evaluator receives a DataFrame that already has technical indicators
# pre-computed and returns a boolean Series (True = signal fires on that bar).
# None means the condition cannot be replayed from price data alone.

_ConditionEvaluator = Callable[[pd.DataFrame], pd.Series]

_CONDITION_EVALUATORS: Dict[str, Optional[_ConditionEvaluator]] = {
    "RSI < 30": lambda df: df["RSI"] < 30,
    "RSI < 10": lambda df: df["RSI"] < 10,
    "RSI > 70": lambda df: df["RSI"] > 70,
    "MA20 crosses above MA60": lambda df: (
        (df["MA20"] > df["MA60"])
        & (df["MA20"].shift(1) <= df["MA60"].shift(1))
    ),
    "MA20 crosses below MA60": lambda df: (
        (df["MA20"] < df["MA60"])
        & (df["MA20"].shift(1) >= df["MA60"].shift(1))
    ),
    "breakout_type == 'up' AND volume_confirmed": lambda df: (
        (df["close"] > df["Donchian_High"].shift(1)) & (df["Volume_Ratio"] > 1.5)
    ),
    # Conditions requiring external data → not replayable
    "comprehensive_score > 70": None,
    "comprehensive_score < 30": None,
    "composite_score > 75": None,
    "margin_5d_change_pct > 3.0": None,
    "credit_spread_change_20d > 0.3": None,
    "vix > 25 AND vix_5d_change > 5": None,
    "dxy_20d_roc < -2.0": None,
}

# Keywords in signal names that indicate a bearish signal (hit = negative return).
# Used only as a fallback when ``SignalDefinition.direction`` is not set.  Keep
# the list to terms that are unambiguously bearish in any plausible signal name.
_BEARISH_KEYWORDS = (
    "overbought",
    "death_cross",
    "distribution",
)


def _is_bearish(signal_def: SignalDefinition) -> bool:
    """Decide hit polarity for a signal.

    Prefers the explicit ``direction`` field; falls back to keyword inference
    on the signal name when ``direction`` is unset.
    """
    direction = (signal_def.direction or "").lower()
    if direction == "bearish":
        return True
    if direction == "bullish":
        return False
    name_lower = signal_def.name.lower()
    return any(kw in name_lower for kw in _BEARISH_KEYWORDS)


def _empty_validation() -> SignalValidation:
    return SignalValidation(
        hit_rate=0.0,
        avg_return=0.0,
        sample_size=0,
        validated_date=date.today().isoformat(),
        regime_hit_rates={},
    )


# ---------------------------------------------------------------------------
# SignalValidator
# ---------------------------------------------------------------------------


class SignalValidator:
    """Walk-forward validator for signal definitions."""

    # Expose the evaluator map as a class attribute so callers can inspect it.
    _CONDITION_EVALUATORS = _CONDITION_EVALUATORS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_signal(
        self,
        signal_def: SignalDefinition,
        price_data: pd.DataFrame,
        regime_series: Optional[pd.Series] = None,
    ) -> SignalValidation:
        """
        Walk-forward validation: replay condition, compute forward returns and
        hit-rate.

        Parameters
        ----------
        signal_def   : signal definition to validate
        price_data   : OHLCV DataFrame with a DatetimeIndex
        regime_series: optional Series (same index as price_data) with regime labels

        Returns
        -------
        SignalValidation with statistics, or an empty validation when the
        condition cannot be replayed from price data.
        """
        # Normalise whitespace so trivial yaml formatting differences don't
        # silently disable validation.
        condition = " ".join(signal_def.condition.split())
        if condition in _CONDITION_EVALUATORS:
            evaluator = _CONDITION_EVALUATORS[condition]
        else:
            logger.debug(
                "SignalValidator: no evaluator registered for condition %r "
                "(signal=%s) — returning empty validation",
                condition,
                signal_def.name,
            )
            return _empty_validation()

        # Non-replayable condition (registered as None) → return empty validation
        if evaluator is None:
            return _empty_validation()

        # Add technical indicators
        df = add_technical_indicators(price_data.copy())

        # Drop rows where essential indicators are NaN
        essential_cols = [c for c in ("RSI", "MA20", "MA60") if c in df.columns]
        if essential_cols:
            df = df.dropna(subset=essential_cols)

        if df.empty:
            return _empty_validation()

        # Evaluate the condition to produce a boolean fire series
        try:
            fire_mask: pd.Series = evaluator(df).fillna(False)
        except (KeyError, TypeError):
            return _empty_validation()

        fire_dates = df.index[fire_mask]
        forward_days = signal_def.forward_days
        bearish = _is_bearish(signal_def)

        returns: list[float] = []
        fire_regimes: list[str] = []

        for fire_date in fire_dates:
            # Find the row index and look ahead by forward_days
            loc = df.index.get_loc(fire_date)
            target_loc = loc + forward_days
            if target_loc >= len(df):
                continue  # not enough future data

            entry_price = df["close"].iloc[loc]
            exit_price = df["close"].iloc[target_loc]
            if entry_price == 0:
                continue

            fwd_return = (exit_price - entry_price) / entry_price
            returns.append(fwd_return)

            if regime_series is not None:
                regime = regime_series.get(fire_date)
                if regime is not None:
                    fire_regimes.append(str(regime))
                else:
                    fire_regimes.append("")

        sample_size = len(returns)
        if sample_size == 0:
            return _empty_validation()

        returns_series = pd.Series(returns)

        if bearish:
            hits = (returns_series < 0).sum()
        else:
            hits = (returns_series > 0).sum()

        hit_rate = float(hits) / sample_size
        avg_return = float(returns_series.mean())

        # Compute regime-conditional hit rates when regime data provided
        regime_hit_rates: Dict[str, float] = {}
        if regime_series is not None and fire_regimes:
            regime_returns: Dict[str, list[float]] = {}
            for ret, regime in zip(returns, fire_regimes):
                if regime:
                    regime_returns.setdefault(regime, []).append(ret)

            for regime, reg_rets in regime_returns.items():
                reg_series = pd.Series(reg_rets)
                if bearish:
                    reg_hits = (reg_series < 0).sum()
                else:
                    reg_hits = (reg_series > 0).sum()
                regime_hit_rates[regime] = float(reg_hits) / len(reg_rets)

        return SignalValidation(
            hit_rate=hit_rate,
            avg_return=avg_return,
            sample_size=sample_size,
            validated_date=date.today().isoformat(),
            regime_hit_rates=regime_hit_rates,
        )

    def save_validation(
        self,
        signal_name: str,
        validation: SignalValidation,
        dir_path: str,
    ) -> None:
        """
        Save validation result to a JSON file.

        The file is written to ``{dir_path}/{signal_name}.json``.
        """
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, f"{signal_name}.json")
        payload = {
            "signal_name": signal_name,
            "hit_rate": validation.hit_rate,
            "avg_return": validation.avg_return,
            "sample_size": validation.sample_size,
            "validated_date": validation.validated_date,
            "regime_hit_rates": validation.regime_hit_rates,
        }
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
