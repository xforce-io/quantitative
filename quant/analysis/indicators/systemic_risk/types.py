"""Data types for the systemic risk state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FeaturePoint:
    """Single standardized feature observation."""

    name: str
    value: Optional[float]
    percentile: Optional[float] = None
    zscore: Optional[float] = None
    velocity: Optional[float] = None
    acceleration: Optional[float] = None
    stress: Optional[float] = None
    as_of: Optional[str] = None
    stale: bool = False


@dataclass
class FeatureSnapshot:
    """Aligned feature stresses at a single as-of date (state-machine input)."""

    as_of: str
    l1_stresses: Dict[str, Optional[float]] = field(default_factory=dict)
    l2_stresses: Dict[str, Optional[float]] = field(default_factory=dict)
    confirm_stresses: Dict[str, Optional[float]] = field(default_factory=dict)
    divergence_stress: float = 0.0
    missing_critical: List[str] = field(default_factory=list)
    stale_critical: bool = False
    feature_points: Dict[str, FeaturePoint] = field(default_factory=dict)

    @property
    def data_quality(self) -> str:
        if self.missing_critical or self.stale_critical:
            return "degraded"
        if any(v is None for v in self.l1_stresses.values()):
            return "partial"
        return "ok"


@dataclass
class SystemicRiskState:
    """Single semantic outlet for global systemic risk."""

    state: str  # normal|building|confirmed|releasing|degraded
    as_of: str
    confidence: float = 0.0
    days_in_state: int = 1
    l1_stress: float = 0.0
    confirm_stress: float = 0.0
    divergence_stress: float = 0.0
    drivers: List[str] = field(default_factory=list)
    feature_snapshot: Dict[str, float] = field(default_factory=dict)
    display_score: Optional[float] = None
    data_quality: str = "ok"
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "as_of": self.as_of,
            "confidence": self.confidence,
            "days_in_state": self.days_in_state,
            "l1_stress": self.l1_stress,
            "confirm_stress": self.confirm_stress,
            "divergence_stress": self.divergence_stress,
            "drivers": list(self.drivers),
            "feature_snapshot": dict(self.feature_snapshot),
            "display_score": self.display_score,
            "data_quality": self.data_quality,
            "updated_at": self.updated_at,
        }
