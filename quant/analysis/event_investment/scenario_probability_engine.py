"""
Scenario probability inference from scored causal paths.
"""

from __future__ import annotations

from collections import defaultdict

from .event_models import CausalPath, Event, Scenario


class ScenarioProbabilityEngine:
    """Convert causal paths into Bull/Base/Bear scenarios."""

    DIRECTION_TO_SCENARIO = {
        "positive": "Bull",
        "negative": "Bear",
        "mixed": "Base",
        "neutral": "Base",
    }

    def infer(self, event: Event, paths: list[CausalPath]) -> list[Scenario]:
        """Infer three scenarios from path distribution."""
        grouped_paths: dict[str, list[CausalPath]] = defaultdict(list)
        for path in paths:
            scenario_name = self.DIRECTION_TO_SCENARIO.get(path.direction, "Base")
            grouped_paths[scenario_name].append(path)

        support = {
            "Bull": self._support_score(grouped_paths.get("Bull", [])),
            "Base": self._support_score(grouped_paths.get("Base", [])),
            "Bear": self._support_score(grouped_paths.get("Bear", [])),
        }
        total_support = sum(support.values()) or 1.0

        scenario_direction = {
            "Bull": "positive",
            "Base": "mixed" if event.direction == "mixed" else "neutral",
            "Bear": "negative",
        }
        default_conditions = {
            "Bull": ["Transmission to beneficiary sectors remains intact"],
            "Base": ["Market partly prices in the event and waits for confirmation"],
            "Bear": ["Negative transmission dominates or follow-up evidence deteriorates"],
        }

        scenarios: list[Scenario] = []
        for name in ["Bull", "Base", "Bear"]:
            probability = round(support[name] / total_support, 4)
            scenario_paths = grouped_paths.get(name, [])
            key_targets = self._collect_targets(scenario_paths)
            lag = scenario_paths[0].lag if scenario_paths else event.time_horizon
            scenarios.append(
                Scenario(
                    name=name,
                    probability=probability,
                    direction=scenario_direction[name],
                    conditions=default_conditions[name],
                    key_targets=key_targets,
                    lag=lag,
                    risk_points=self._build_risk_points(name, event),
                    support_score=round(support[name], 4),
                )
            )
        self._normalize_probabilities(scenarios)
        return scenarios

    @staticmethod
    def _support_score(paths: list[CausalPath]) -> float:
        if not paths:
            return 0.01
        avg_score = sum(path.strength * path.confidence for path in paths) / len(paths)
        return max(0.01, len(paths) * avg_score)

    @staticmethod
    def _collect_targets(paths: list[CausalPath]) -> list[str]:
        targets: list[str] = []
        for path in paths:
            if path.nodes:
                target = path.nodes[-1]
                if target not in targets:
                    targets.append(target)
        return targets[:4]

    @staticmethod
    def _build_risk_points(name: str, event: Event) -> list[str]:
        generic_risk = "Market confirmation may diverge from textual inference"
        if name == "Bull":
            return [generic_risk, "Beneficiary trades may already be crowded"]
        if name == "Bear":
            return [generic_risk, "Policy or company follow-up may soften the downside"]
        return [generic_risk, f"Event classification uncertainty remains at {1 - event.confidence:.0%}"]

    @staticmethod
    def _normalize_probabilities(scenarios: list[Scenario]) -> None:
        total = sum(scenario.probability for scenario in scenarios) or 1.0
        running = 0.0
        for scenario in scenarios[:-1]:
            scenario.probability = round(scenario.probability / total, 4)
            running += scenario.probability
        scenarios[-1].probability = round(max(0.0, 1.0 - running), 4)
