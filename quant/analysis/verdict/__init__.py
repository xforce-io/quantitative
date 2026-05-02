#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Verdict module — synthesizes regime, signals, and transmissions into actionable verdicts.

Provides:
    VerdictEngine    — main synthesis engine
    PoolVerdict      — per-pool action recommendation
    PositionAlert    — per-position actionable alert
    DashboardVerdict — top-level cross-pool summary
"""

from .verdict_engine import (
    DashboardVerdict,
    PoolVerdict,
    PositionAlert,
    VerdictEngine,
)

__all__ = [
    "VerdictEngine",
    "PoolVerdict",
    "PositionAlert",
    "DashboardVerdict",
]
