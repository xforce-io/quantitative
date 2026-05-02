"""End-to-end test of RotationService against synthetic prices."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from quant.analysis.rotation import RankerConfig
from quant.services.rotation_service import RotationRequest, RotationService


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_UNIVERSE = _REPO_ROOT / "config" / "rotation_universe.yaml"


def _synthetic_prices(symbol: str, growth: float, n: int = 1500) -> pd.DataFrame:
    rng = np.random.RandomState(abs(hash(symbol)) % (2**32))
    dates = pd.date_range("2018-01-02", periods=n, freq="B")
    drift = np.linspace(0.0, growth, n)
    noise = rng.normal(0.0, 0.01, n).cumsum() * 0.1
    close = 10.0 * np.exp(drift + noise)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1.0},
        index=dates,
    )


class _DeterministicDataService:
    """Maps each symbol to a synthetic price frame deterministically by symbol hash."""

    def __init__(self) -> None:
        self._growths = {
            "510050.SH": 0.4,
            "512000.SH": 0.6,
            "512800.SH": 0.3,
            "512170.SH": 0.5,
            "512010.SH": 0.45,
            "159995.SZ": 0.7,
            "515050.SH": 0.55,
            "512720.SH": 0.5,
            "159928.SZ": 0.35,
            "159825.SZ": 0.25,
            "512400.SH": 0.4,
            "515220.SH": 0.2,
            "515210.SH": 0.15,
            "159611.SZ": 0.3,
            "159930.SZ": 0.25,
            "512660.SH": 0.4,
            "515030.SH": 0.65,
            "515790.SH": 0.6,
            "159870.SZ": 0.3,
            "512200.SH": 0.1,
            "510880.SH": 0.3,
            "159949.SZ": 0.5,
            "510310.SH": 0.4,
            "159922.SZ": 0.35,
            "000300.SH": 0.4,
        }

    def get_price(self, request):
        return _synthetic_prices(request.symbol, self._growths.get(request.symbol, 0.3))

    def get_trading_days(self, start, end):
        return pd.date_range(start, end, freq="B").strftime("%Y-%m-%d").tolist()


def test_pipeline_runs_against_default_universe() -> None:
    service = RotationService(data_service=_DeterministicDataService())
    request = RotationRequest(
        start="2018-01-01",
        end="2023-12-31",
        universe_path=str(_DEFAULT_UNIVERSE),
        ranker_config=RankerConfig(top_k=5),
        transaction_cost=0.002,
    )
    result = service.run_backtest(request)

    assert len(result.equity_curve) >= 60
    assert {"strategy", "benchmark", "equal_weight"} == set(result.equity_curve.columns)
    assert result.metrics["annual_return_strategy"] is not None

    nonzero_per_row = (result.holdings != 0).sum(axis=1)
    assert nonzero_per_row.max() <= 5


def test_latest_targets_against_default_universe() -> None:
    service = RotationService(data_service=_DeterministicDataService())
    request = RotationRequest(
        start="2018-01-01",
        end="2023-12-31",
        universe_path=str(_DEFAULT_UNIVERSE),
        ranker_config=RankerConfig(top_k=5),
    )
    targets = service.latest_targets(request)

    assert targets["as_of"].startswith("2023-")
    assert 0.0 <= targets["multiplier"] <= 1.0
    assert sum(targets["final_positions"].values()) <= 1.0 + 1e-9
    assert len(targets["top_momentum"]) <= 5
