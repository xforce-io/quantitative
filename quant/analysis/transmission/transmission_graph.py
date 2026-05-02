#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TransmissionGraph — cross-asset causal edge monitoring.

Loads edge definitions from config/transmission_edges.yaml and:
  - checks whether source assets have moved enough to trigger a transmission
  - tracks active transmissions with a day countdown
  - updates transmission status when target moves are observed
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class TransmissionEdge:
    source: str
    target: str
    direction: str          # "inverse" | "direct"
    lag_min_days: int
    lag_max_days: int
    threshold: float        # minimum move to trigger (%)
    strength: float         # backtested correlation (0-1)
    source_ticker: Optional[str] = None
    target_ticker: Optional[str] = None


@dataclass
class ActiveTransmission:
    edge: TransmissionEdge
    triggered_at: str
    source_move: float
    expected_target: str    # "up" | "down"
    days_remaining: int
    # "triggered"   — just fired, lag window has not yet elapsed
    # "propagating" — within lag window, target move not yet observed
    # "confirmed"   — target moved in the expected direction (set via update_status)
    # "failed"      — target moved against the expected direction (set via update_status)
    # "expired"     — lag window elapsed without an update_status call
    status: str


_THRESHOLD_KEYS = ("threshold_pct", "threshold_pp", "threshold_points")


def _load_edges_from_yaml(path: Path) -> List[TransmissionEdge]:
    with open(path, "r") as fh:
        data = yaml.safe_load(fh)

    edges: List[TransmissionEdge] = []
    for raw in data.get("edges", []):
        # Resolve threshold from any of the supported key names
        threshold: Optional[float] = None
        for key in _THRESHOLD_KEYS:
            if key in raw:
                threshold = float(raw[key])
                break

        if threshold is None:
            raise ValueError(f"No threshold key found in edge: {raw}")

        edges.append(
            TransmissionEdge(
                source=raw["source"],
                target=raw["target"],
                direction=raw["direction"],
                lag_min_days=int(raw["lag_min_days"]),
                lag_max_days=int(raw["lag_max_days"]),
                threshold=threshold,
                strength=float(raw.get("initial_strength", raw.get("strength", 0.0))),
                source_ticker=raw.get("source_ticker") or None,
                target_ticker=raw.get("target_ticker") or None,
            )
        )
    return edges


def _expected_direction(edge: TransmissionEdge, pct_move: float) -> str:
    """Return 'up' or 'down' for the expected target direction."""
    positive_move = pct_move > 0
    if edge.direction == "inverse":
        return "down" if positive_move else "up"
    else:  # "direct"
        return "up" if positive_move else "down"


class TransmissionGraph:
    """Cross-asset causal edge graph with trigger detection and status tracking."""

    _DEFAULT_CONFIG = Path(__file__).parent.parent.parent.parent / "config" / "transmission_edges.yaml"

    def __init__(self, config_path: Optional[Path] = None) -> None:
        path = Path(config_path) if config_path is not None else self._DEFAULT_CONFIG
        self.edges: List[TransmissionEdge] = _load_edges_from_yaml(path)
        self._active: List[ActiveTransmission] = []

    # ------------------------------------------------------------------
    # Trigger detection
    # ------------------------------------------------------------------

    def check_triggers(
        self,
        current_values: Dict[str, float],
        previous_values: Dict[str, float],
    ) -> List[ActiveTransmission]:
        """Check if any source moved beyond its threshold.

        Returns newly triggered ActiveTransmission objects (also stored internally).
        """
        triggered: List[ActiveTransmission] = []
        today = str(date.today())

        for edge in self.edges:
            prev = previous_values.get(edge.source)
            curr = current_values.get(edge.source)
            if prev is None or curr is None:
                continue

            pct_move = (curr - prev) / abs(prev) * 100

            if abs(pct_move) >= edge.threshold:
                transmission = ActiveTransmission(
                    edge=edge,
                    triggered_at=today,
                    source_move=pct_move,
                    expected_target=_expected_direction(edge, pct_move),
                    days_remaining=edge.lag_max_days,
                    status="triggered",
                )
                triggered.append(transmission)
                self._active.append(transmission)

        return triggered

    # ------------------------------------------------------------------
    # Status updates
    # ------------------------------------------------------------------

    def update_status(
        self, transmission: ActiveTransmission, target_move: float
    ) -> ActiveTransmission:
        """Update status based on observed target move.

        "confirmed" if the target moved in the expected direction, "failed" otherwise.
        """
        expected = transmission.expected_target  # "up" or "down"
        moved_up = target_move > 0

        if (expected == "up" and moved_up) or (expected == "down" and not moved_up):
            transmission.status = "confirmed"
        else:
            transmission.status = "failed"

        return transmission

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active_transmissions(self) -> List[ActiveTransmission]:
        """Return transmissions with status in ('triggered', 'propagating')."""
        return [t for t in self._active if t.status in ("triggered", "propagating")]

    def get_edges_by_source(self, source: str) -> List[TransmissionEdge]:
        return [e for e in self.edges if e.source == source]

    def get_edges_by_target(self, target: str) -> List[TransmissionEdge]:
        return [e for e in self.edges if e.target == target]

    # ------------------------------------------------------------------
    # Time advancement
    # ------------------------------------------------------------------

    def tick_day(self) -> List[ActiveTransmission]:
        """Advance all active transmissions by one day.

        Decrements ``days_remaining`` for each active (triggered/propagating)
        transmission.  Transmissions that hit ``0`` are marked ``"expired"``
        so :meth:`get_active_transmissions` no longer returns them.

        Returns the list of transmissions that expired on this tick.
        """
        expired: List[ActiveTransmission] = []

        for transmission in self._active:
            if transmission.status not in ("triggered", "propagating"):
                continue

            transmission.days_remaining -= 1

            if transmission.days_remaining <= 0:
                transmission.days_remaining = 0
                transmission.status = "expired"
                expired.append(transmission)
            elif transmission.status == "triggered":
                transmission.status = "propagating"

        return expired
