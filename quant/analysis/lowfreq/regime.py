"""Simple A-share market regime multiplier for low-frequency allocation."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RegimeConfig:
    """Configuration for low-frequency A-share regime multiplier."""

    medium_vol_threshold: float = 0.20
    high_vol_threshold: float = 0.35
    drawdown_window_months: int = 12
    drawdown_threshold: float = -0.20
    medium_vol_multiplier: float = 0.70
    high_vol_multiplier: float = 0.50
    drawdown_multiplier: float = 0.50


class LowFrequencyRegimeScorer:
    """Score simple market regime multipliers from low-frequency signal rows."""

    def __init__(self, config: RegimeConfig | None = None) -> None:
        self.config = config or RegimeConfig()
        if not (0 <= self.config.medium_vol_threshold <= self.config.high_vol_threshold):
            raise ValueError("vol thresholds must satisfy 0 <= medium <= high")
        if self.config.drawdown_window_months <= 0:
            raise ValueError("drawdown_window_months must be positive")

    def apply(self, signals: pd.DataFrame) -> pd.DataFrame:
        """Append regime labels, multipliers, and adjusted target positions."""
        data = self._prepare(signals)
        rolling_high = data["close"].rolling(
            self.config.drawdown_window_months,
            min_periods=1,
        ).max()
        drawdown = data["close"] / rolling_high - 1.0

        labels = []
        multipliers = []
        reasons = []

        for _, row in data.iterrows():
            label, multiplier, reason = self._score_row(
                trend_on=bool(row["trend_on"]),
                realized_vol=float(row["realized_vol"]) if pd.notna(row["realized_vol"]) else None,
                drawdown=float(drawdown.loc[row.name]),
            )
            labels.append(label)
            multipliers.append(multiplier)
            reasons.append(reason)

        data["market_drawdown"] = drawdown
        data["regime"] = labels
        data["regime_multiplier"] = multipliers
        data["regime_reason"] = reasons
        data["base_position"] = data["target_position"]
        data["target_position"] = (
            data["base_position"] * data["regime_multiplier"]
        ).clip(0.0, 1.0).round(4)
        return data

    def _prepare(self, signals: pd.DataFrame) -> pd.DataFrame:
        """Validate and normalize signal frame."""
        required = ("close", "trend_on", "realized_vol", "target_position")
        if signals is None or signals.empty:
            raise ValueError("signals must be a non-empty DataFrame")

        missing = [col for col in required if col not in signals.columns]
        if missing:
            raise ValueError(f"signals missing required columns: {', '.join(missing)}")

        data = signals.copy()
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)
        data = data.sort_index()
        data["close"] = pd.to_numeric(data["close"], errors="coerce")
        data["realized_vol"] = pd.to_numeric(data["realized_vol"], errors="coerce")
        data["target_position"] = pd.to_numeric(data["target_position"], errors="coerce")
        data = data.dropna(subset=["close", "target_position"])
        return data

    def _score_row(
        self,
        trend_on: bool,
        realized_vol: float | None,
        drawdown: float,
    ) -> tuple[str, float, str]:
        """Score one signal row."""
        if not trend_on:
            return "bear", 0.0, "trend_off"

        multiplier = 1.0
        label = "bull"
        reason_parts = ["trend_on"]

        if realized_vol is None:
            multiplier = min(multiplier, self.config.medium_vol_multiplier)
            label = "range"
            reason_parts.append("vol_unavailable")
        elif realized_vol > self.config.high_vol_threshold:
            multiplier = min(multiplier, self.config.high_vol_multiplier)
            label = "stress"
            reason_parts.append("high_vol")
        elif realized_vol > self.config.medium_vol_threshold:
            multiplier = min(multiplier, self.config.medium_vol_multiplier)
            label = "range"
            reason_parts.append("medium_vol")
        else:
            reason_parts.append("low_vol")

        if drawdown <= self.config.drawdown_threshold:
            multiplier = min(multiplier, self.config.drawdown_multiplier)
            label = "stress" if multiplier <= self.config.high_vol_multiplier else "range"
            reason_parts.append("deep_drawdown")

        return label, round(multiplier, 4), "+".join(reason_parts)
