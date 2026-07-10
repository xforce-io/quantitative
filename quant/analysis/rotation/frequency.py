"""Single source of truth for backtest rebalance frequency.

Public config fields keep month-based names (lookback_months, skip_months) for
backward compatibility with all existing strategy_spec.json candidates. Internal
engine code uses *_bars units converted via months_to_bars().
"""
from __future__ import annotations

from typing import Literal

BacktestFrequency = Literal["monthly", "biweekly", "weekly"]

_BARS_PER_YEAR: dict[str, int] = {
    "monthly": 12,
    "biweekly": 26,
    "weekly": 52,
}

_RESAMPLE_RULE: dict[str, str] = {
    "monthly": "ME",
    "biweekly": "2W-FRI",
    "weekly": "W-FRI",
}


def validate_frequency(freq: str) -> BacktestFrequency:
    if freq not in _BARS_PER_YEAR:
        raise ValueError(
            f"unknown frequency {freq!r}; expected one of {sorted(_BARS_PER_YEAR)}"
        )
    return freq  # type: ignore[return-value]


def bars_per_year(freq: BacktestFrequency) -> int:
    return _BARS_PER_YEAR[validate_frequency(freq)]


def resample_rule(freq: BacktestFrequency) -> str:
    return _RESAMPLE_RULE[validate_frequency(freq)]


def months_to_bars(months: int, freq: BacktestFrequency) -> int:
    """Convert calendar months to bars at the given frequency.

    Semantics: lookback_months=6 means 'approximately 6 calendar months of
    history', not '6 bars'. This keeps factor semantics stable across
    frequencies. Rounded to nearest int.
    """
    if months < 0:
        raise ValueError("months must be non-negative")
    return round(months * bars_per_year(freq) / 12)
