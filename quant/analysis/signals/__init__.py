#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Signals module — YAML-driven signal definitions and registry.

Provides:
    SignalDefinition  — descriptor for a tradeable signal
    SignalValidation  — backtested hit-rate statistics
    ActiveSignal      — a fired signal with context
    SignalRegistry    — loads and queries signal definitions from config
"""

from .signal_registry import (
    ActiveSignal,
    SignalDefinition,
    SignalRegistry,
    SignalValidation,
)

__all__ = [
    "SignalDefinition",
    "SignalValidation",
    "ActiveSignal",
    "SignalRegistry",
]
