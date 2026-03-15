"""
Map causal scenarios to sectors, ETFs, and symbols.
"""

from __future__ import annotations

from typing import Any

from .event_models import AssetImpact, Event, Scenario


class InvestmentMapper:
    """Map normalized events and scenarios into asset impacts."""

    def __init__(self, asset_mapping: dict[str, Any]):
        self.asset_mapping = asset_mapping

    def map_assets(self, event: Event, scenarios: list[Scenario]) -> list[AssetImpact]:
        """Generate explainable asset impacts."""
        impacts: list[AssetImpact] = []
        mapping = self.asset_mapping.get(event.event_type, {})
        positive_assets = mapping.get("positive", [])
        negative_assets = mapping.get("negative", [])
        watch_assets = mapping.get("watchlist", [])

        bull_probability = self._get_probability(scenarios, "Bull")
        bear_probability = self._get_probability(scenarios, "Bear")
        base_probability = self._get_probability(scenarios, "Base")

        impacts.extend(
            self._build_impacts(
                assets=positive_assets,
                direction="positive",
                score_base=0.62 + bull_probability * 0.3,
                confidence=event.confidence,
                impact_kind="direct",
            )
        )
        impacts.extend(
            self._build_impacts(
                assets=negative_assets,
                direction="negative",
                score_base=0.55 + bear_probability * 0.3,
                confidence=event.confidence * 0.95,
                impact_kind="direct",
            )
        )
        impacts.extend(
            self._build_impacts(
                assets=watch_assets,
                direction="watch",
                score_base=0.45 + base_probability * 0.2,
                confidence=event.confidence * 0.85,
                impact_kind="indirect",
            )
        )
        impacts.sort(key=lambda item: item.score, reverse=True)
        return impacts

    @staticmethod
    def _get_probability(scenarios: list[Scenario], name: str) -> float:
        for scenario in scenarios:
            if scenario.name == name:
                return scenario.probability
        return 0.0

    def _build_impacts(
        self,
        assets: list[dict[str, Any]],
        direction: str,
        score_base: float,
        confidence: float,
        impact_kind: str,
    ) -> list[AssetImpact]:
        results: list[AssetImpact] = []
        for asset in assets:
            results.append(
                AssetImpact(
                    asset_name=asset["name"],
                    asset_type=asset.get("type", "sector"),
                    symbol=asset.get("symbol", ""),
                    direction=direction,
                    score=round(min(0.98, score_base + asset.get("score_boost", 0.0)), 2),
                    confidence=round(min(0.95, confidence * asset.get("confidence", 1.0)), 2),
                    sector=asset.get("sector", ""),
                    reason_chain=asset.get("reason_chain", ""),
                    risk_note=asset.get("risk_note", "Follow-up evidence must confirm the transmission path"),
                    impact_kind=impact_kind,
                )
            )
        return results
