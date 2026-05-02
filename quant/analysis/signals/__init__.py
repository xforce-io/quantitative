#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Signals module — YAML-driven signal definitions and registry.

Provides:
    SignalDefinition  — descriptor for a tradeable signal
    SignalValidation  — backtested hit-rate statistics
    ActiveSignal      — a fired signal with context
    SignalRegistry    — loads and queries signal definitions from config
    SignalValidator   — walk-forward hit-rate calculation for registered signals
"""

from .signal_registry import (
    ActiveSignal,
    SignalDefinition,
    SignalRegistry,
    SignalValidation,
)
from .signal_validator import SignalValidator

__all__ = [
    "SignalDefinition",
    "SignalValidation",
    "ActiveSignal",
    "SignalRegistry",
    "SignalValidator",
]
