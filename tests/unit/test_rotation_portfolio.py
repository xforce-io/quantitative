"""Tests for PortfolioCombiner."""
from __future__ import annotations

import pytest

from quant.analysis.rotation.portfolio import PortfolioCombiner


def test_combine_full_multiplier_keeps_weights() -> None:
    combiner = PortfolioCombiner()
    result = combiner.combine({"A": 0.4, "B": 0.6}, multiplier=1.0)
    assert result == {"A": 0.4, "B": 0.6}


def test_combine_half_multiplier_halves_weights() -> None:
    combiner = PortfolioCombiner()
    result = combiner.combine({"A": 0.5, "B": 0.5}, multiplier=0.5)
    assert result == {"A": 0.25, "B": 0.25}


def test_combine_zero_multiplier_yields_all_zero() -> None:
    combiner = PortfolioCombiner()
    result = combiner.combine({"A": 0.5, "B": 0.5}, multiplier=0.0)
    assert all(v == 0.0 for v in result.values())
    assert set(result) == {"A", "B"}


def test_combine_empty_weights_returns_empty_regardless_of_multiplier() -> None:
    combiner = PortfolioCombiner()
    assert combiner.combine({}, multiplier=1.0) == {}
    assert combiner.combine({}, multiplier=0.5) == {}
    assert combiner.combine({}, multiplier=0.0) == {}


def test_combine_rejects_multiplier_outside_unit_interval() -> None:
    combiner = PortfolioCombiner()
    with pytest.raises(ValueError):
        combiner.combine({"A": 1.0}, multiplier=1.5)
    with pytest.raises(ValueError):
        combiner.combine({"A": 1.0}, multiplier=-0.1)
