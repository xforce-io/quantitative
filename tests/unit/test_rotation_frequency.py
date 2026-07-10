"""Tests for backtest frequency abstraction."""
from __future__ import annotations

import pytest

from quant.analysis.rotation.frequency import (
    BacktestFrequency,
    bars_per_year,
    months_to_bars,
    resample_rule,
    validate_frequency,
)


@pytest.mark.parametrize(
    "freq,expected",
    [("monthly", 12), ("biweekly", 26), ("weekly", 52)],
)
def test_bars_per_year(freq: BacktestFrequency, expected: int) -> None:
    assert bars_per_year(freq) == expected


@pytest.mark.parametrize(
    "freq,expected",
    [("monthly", "ME"), ("biweekly", "2W-FRI"), ("weekly", "W-FRI")],
)
def test_resample_rule(freq: BacktestFrequency, expected: str) -> None:
    assert resample_rule(freq) == expected


@pytest.mark.parametrize(
    "freq,months,expected_bars",
    [
        ("monthly", 6, 6),
        ("monthly", 1, 1),
        ("biweekly", 6, 13),
        ("biweekly", 1, 2),
        ("weekly", 6, 26),
        ("weekly", 1, 4),
        ("weekly", 0, 0),
    ],
)
def test_months_to_bars(freq: BacktestFrequency, months: int, expected_bars: int) -> None:
    assert months_to_bars(months, freq) == expected_bars


def test_months_to_bars_rejects_negative() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        months_to_bars(-1, "monthly")


def test_validate_frequency_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown frequency"):
        validate_frequency("daily")
