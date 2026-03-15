"""
Core data models for event-driven investment inference.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Event:
    """Normalized event object."""

    event_id: str
    title: str
    source: str
    published_at: str
    event_type: str
    summary: str
    entities: list[str]
    regions: list[str]
    sectors: list[str]
    direction: str
    magnitude: float
    urgency: str
    time_horizon: str
    confidence: float
    evidence: list[str]
    action: str = "unknown"
    canonical_label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class CausalPath:
    """Explainable causal path from event to assets."""

    path_id: str
    event_type: str
    direction: str
    strength: float
    confidence: float
    lag: str
    condition: str
    reliability: float
    nodes: list[str]
    reason_chain: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class Scenario:
    """Bull/Base/Bear scenario output."""

    name: str
    probability: float
    direction: str
    conditions: list[str]
    key_targets: list[str]
    lag: str
    risk_points: list[str]
    support_score: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class AssetImpact:
    """Mapped asset-level impact."""

    asset_name: str
    asset_type: str
    direction: str
    score: float
    confidence: float
    sector: str
    symbol: str = ""
    reason_chain: str = ""
    risk_note: str = ""
    impact_kind: str = "direct"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class EventAnalysisResult:
    """End-to-end result for a single event."""

    event: Event
    causal_paths: list[CausalPath]
    scenarios: list[Scenario]
    asset_impacts: list[AssetImpact]
    graph: dict[str, Any]
    rounds: dict[str, Any]
    markdown_report: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "event": self.event.to_dict(),
            "causal_paths": [path.to_dict() for path in self.causal_paths],
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
            "asset_impacts": [impact.to_dict() for impact in self.asset_impacts],
            "graph": self.graph,
            "rounds": self.rounds,
            "markdown_report": self.markdown_report,
        }
