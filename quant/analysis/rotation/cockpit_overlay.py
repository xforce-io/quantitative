"""Cockpit-based regime overlay (A layer) for rotation strategy."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from quant.analysis.regime.historical_indicators import AshareHistoricalIndicators
from quant.analysis.regime.regime_detector import RegimeDetector


@dataclass(frozen=True)
class CockpitOverlayConfig:
    """Configuration for CockpitRegimeOverlay."""

    pool: str = "a_shares"
    multiplier_map: dict = field(
        default_factory=lambda: {
            "risk-on": 1.0,
            "transition": 0.5,
            "risk-off": 0.0,
        }
    )


class CockpitRegimeOverlay:
    """Wrap cockpit RegimeDetector into a rotation RegimeOverlay."""

    def __init__(
        self,
        data_service,
        regime_detector: RegimeDetector | None = None,
        indicators: AshareHistoricalIndicators | None = None,
        config: CockpitOverlayConfig | None = None,
    ) -> None:
        self.data_service = data_service
        self.detector = regime_detector or RegimeDetector()
        self.indicators = indicators or AshareHistoricalIndicators(data_service)
        self.config = config or CockpitOverlayConfig()

        self.multipliers: pd.Series = pd.Series(dtype=float, name="cockpit_multiplier")
        self._history_records: list[dict] = []

    def precompute(self, start: str, end: str) -> None:
        panel = self.indicators.build(start, end)
        if panel.empty:
            self.multipliers = pd.Series(dtype=float, name="cockpit_multiplier")
            self._history_records = []
            return

        rows = []
        records = []
        for date, row in panel.iterrows():
            indicator_dict = {k: float(v) for k, v in row.items() if pd.notna(v)}
            state = self.detector.classify_pool(self.config.pool, indicator_dict)
            multiplier = self.config.multiplier_map[state.regime]
            rows.append((date, multiplier))
            records.append(
                {
                    "date": date,
                    "regime": state.regime,
                    "confidence": state.confidence,
                    "multiplier": multiplier,
                    "drivers": "; ".join(state.drivers),
                }
            )

        self.multipliers = pd.Series(
            [m for _, m in rows],
            index=[d for d, _ in rows],
            name="cockpit_multiplier",
        )
        self._history_records = records

    def multiplier_at(self, date: pd.Timestamp) -> float:
        if self.multipliers.empty:
            return 0.0
        if date < self.multipliers.index[0]:
            return 0.0
        idx = self.multipliers.index.searchsorted(date, side="right") - 1
        return float(self.multipliers.iloc[idx])

    @property
    def regime_history(self) -> pd.DataFrame:
        if not self._history_records:
            return pd.DataFrame(columns=["date", "regime", "confidence", "multiplier", "drivers"])
        return pd.DataFrame(self._history_records).set_index("date")
