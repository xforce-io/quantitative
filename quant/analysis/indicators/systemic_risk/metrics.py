"""Event-path evaluation metrics for systemic risk states."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence


ACTIVE = frozenset({"building", "confirmed"})


@dataclass
class PathMetrics:
    first_building: Optional[str]
    first_confirmed: Optional[str]
    lead_building: Optional[int]
    lead_confirmed: Optional[int]
    hit: bool
    miss: bool
    flicker: float
    n_days: int
    confirmed_days: int

    def to_dict(self) -> dict:
        return {
            "first_building": self.first_building,
            "first_confirmed": self.first_confirmed,
            "lead_building": self.lead_building,
            "lead_confirmed": self.lead_confirmed,
            "hit": self.hit,
            "miss": self.miss,
            "flicker": self.flicker,
            "n_days": self.n_days,
            "confirmed_days": self.confirmed_days,
        }


def _trading_day_delta(dates: Sequence[str], start: str, end: str) -> Optional[int]:
    """Signed index difference end - start on the provided ordered date list."""
    if start not in dates or end not in dates:
        # fallback: find nearest
        try:
            si = next(i for i, d in enumerate(dates) if d >= start)
            ei = next(i for i, d in enumerate(dates) if d >= end)
            return ei - si
        except StopIteration:
            return None
    return dates.index(end) - dates.index(start)


def evaluate_state_path(
    dates: Sequence[str],
    states: Sequence[str],
    anchor_date: str,
) -> PathMetrics:
    """Compute lead/hit/miss/flicker for one event path.

    ``lead_*`` = first_event_index - anchor_index (negative means lead).
    """
    if len(dates) != len(states):
        raise ValueError("dates and states length mismatch")

    first_building = next((d for d, s in zip(dates, states) if s == "building"), None)
    first_confirmed = next((d for d, s in zip(dates, states) if s == "confirmed"), None)

    lead_b = (
        _trading_day_delta(list(dates), anchor_date, first_building)
        if first_building
        else None
    )
    lead_c = (
        _trading_day_delta(list(dates), anchor_date, first_confirmed)
        if first_confirmed
        else None
    )
    # Convention: lead = first_signal - anchor → negative if signal before anchor.
    # _trading_day_delta(anchor, first) gives first-anchor... wait:
    # We used _trading_day_delta(dates, start=anchor, end=first) = first - anchor. Good.

    hit = any(s in ACTIVE for s in states)
    miss = all(s == "normal" for s in states) or (
        not hit and all(s in ("normal", "releasing", "degraded") for s in states)
    )
    # stricter miss: never building/confirmed
    miss = not hit

    switches = sum(1 for i in range(1, len(states)) if states[i] != states[i - 1])
    flicker = switches / max(len(states), 1)
    confirmed_days = sum(1 for s in states if s == "confirmed")

    return PathMetrics(
        first_building=first_building,
        first_confirmed=first_confirmed,
        lead_building=lead_b,
        lead_confirmed=lead_c,
        hit=hit,
        miss=miss,
        flicker=round(flicker, 4),
        n_days=len(states),
        confirmed_days=confirmed_days,
    )


def false_positive_rate(
    states: Iterable[str],
    quiet_mask: Sequence[bool],
) -> float:
    """Share of quiet days labeled confirmed."""
    states = list(states)
    if len(states) != len(quiet_mask):
        raise ValueError("states/quiet_mask length mismatch")
    quiet_days = [s for s, q in zip(states, quiet_mask) if q]
    if not quiet_days:
        return 0.0
    return sum(1 for s in quiet_days if s == "confirmed") / len(quiet_days)
