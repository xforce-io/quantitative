"""
Market evidence calibration hooks for event scenarios.
"""

from __future__ import annotations

from typing import Any

from .event_models import Event, Scenario


class MarketEvidenceCalibrator:
    """Calibrate scenarios with lightweight optional market signals."""

    def calibrate(
        self,
        event: Event,
        scenarios: list[Scenario],
        market_context: dict[str, Any] | None = None,
    ) -> list[Scenario]:
        """Apply simple posterior adjustments while keeping probabilities normalized."""
        market_context = market_context or {}
        confirmation_score = float(market_context.get("confirmation_score", 0.0))
        crowding_score = float(market_context.get("crowding_score", 0.0))
        source_bias = 0.02 if event.source in {"新华社", "公司公告"} else 0.0

        for scenario in scenarios:
            if scenario.name == "Bull":
                scenario.probability += max(0.0, confirmation_score) * 0.08
                scenario.probability -= max(0.0, crowding_score) * 0.05
            elif scenario.name == "Bear":
                scenario.probability += max(0.0, -confirmation_score) * 0.08
            else:
                scenario.probability += source_bias

        total = sum(max(0.0, scenario.probability) for scenario in scenarios) or 1.0
        running = 0.0
        for scenario in scenarios[:-1]:
            scenario.probability = round(max(0.0, scenario.probability) / total, 4)
            running += scenario.probability
        scenarios[-1].probability = round(max(0.0, 1.0 - running), 4)
        return scenarios
