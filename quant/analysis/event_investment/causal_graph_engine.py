"""
Causal graph rollout engine backed by YAML knowledge.
"""

from __future__ import annotations

from typing import Any

from .event_models import CausalPath, Event


class CausalGraphEngine:
    """Generate explainable causal paths for one event."""

    def __init__(self, causal_edges: dict[str, Any]):
        self.causal_edges = causal_edges

    def rollout(self, event: Event) -> list[CausalPath]:
        """Generate causal paths for the normalized event."""
        edge_configs = self.causal_edges.get(event.event_type, [])
        if not edge_configs:
            edge_configs = self.causal_edges.get("generic_market_event", [])

        paths: list[CausalPath] = []
        for index, config in enumerate(edge_configs, start=1):
            strength = round(config.get("strength", 0.5) * event.magnitude, 2)
            confidence = round(min(0.95, event.confidence * config.get("reliability", 0.7)), 2)
            nodes = [event.title] + config.get("nodes", [])
            paths.append(
                CausalPath(
                    path_id=f"{event.event_id}-path-{index}",
                    event_type=event.event_type,
                    direction=config.get("direction", event.direction),
                    strength=strength,
                    confidence=confidence,
                    lag=config.get("lag", "short_term"),
                    condition=config.get("condition", "Event transmission remains valid"),
                    reliability=config.get("reliability", 0.7),
                    nodes=nodes,
                    reason_chain=" -> ".join(nodes),
                )
            )
        return paths
