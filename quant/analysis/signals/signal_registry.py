#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SignalRegistry — YAML-driven signal definitions with validation storage.

Loads signal definitions from config/signals.yaml (or a caller-supplied path)
and provides query helpers to filter signals by asset pool and market regime.
Validations (backtested hit-rate statistics) can be stored in-memory and
optionally bulk-loaded from a directory of JSON files.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SignalDefinition:
    """Descriptor for a tradeable signal loaded from YAML."""

    name: str                    # e.g. "rsi_oversold_bounce"
    asset_pools: list[str]       # e.g. ["a_shares"]
    signal_type: str             # "mean_reversion" | "momentum" | "breakout" | "macro" | …
    source_analyzer: str         # class name of the analyzer that detects this signal
    lookback_days: int           # historical window used to evaluate the condition
    condition: str               # machine-readable condition string
    condition_description: str   # human-readable explanation for UI display
    regime_filter: dict          # {"a_shares": ["risk-on", "transition"]} or {}
    forward_days: int = 5        # evaluation horizon for hit-rate measurement


@dataclass
class SignalValidation:
    """Backtested performance statistics for a signal."""

    hit_rate: float              # fraction of firings that produced a positive return (0–1)
    avg_return: float            # average N-day return after the signal fires
    sample_size: int             # number of historical occurrences
    validated_date: str          # ISO date of the last validation run
    regime_hit_rates: dict       # per-regime hit rates, e.g. {"risk-on": 0.72}

    def is_valid(self, min_hit_rate: float = 0.55) -> bool:
        """Return True when the overall hit_rate meets the minimum threshold."""
        return self.hit_rate >= min_hit_rate

    def hit_rate_for_regime(self, regime: str) -> float:
        """Return the hit rate for a specific regime, falling back to the overall rate."""
        return self.regime_hit_rates.get(regime, self.hit_rate)


@dataclass
class ActiveSignal:
    """A signal that has just fired, with action and reasoning attached."""

    definition: SignalDefinition
    validation: Optional[SignalValidation]
    fired_at: str                # ISO datetime when the signal fired
    symbol: Optional[str]        # specific ticker, or None for pool-level signals
    action: str                  # "add" | "reduce" | "watch" | "avoid"
    reasoning: str               # human-readable rationale


# ---------------------------------------------------------------------------
# SignalRegistry
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__),   # quant/analysis/signals/
    "..", "..", "..",            # → project root
    "config",
    "signals.yaml",
)


class SignalRegistry:
    """
    Loads signal definitions from a YAML config file and provides query
    helpers.  Validations can be stored/retrieved in-memory and bulk-loaded
    from JSON files.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        if config_path is None:
            config_path = os.path.normpath(_DEFAULT_CONFIG_PATH)

        with open(config_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        self.min_hit_rate: float = float(raw.get("min_hit_rate", 0.55))

        self.definitions: List[SignalDefinition] = [
            SignalDefinition(
                name=sig["name"],
                asset_pools=sig["asset_pools"],
                signal_type=sig["signal_type"],
                source_analyzer=sig["source_analyzer"],
                lookback_days=int(sig["lookback_days"]),
                condition=sig["condition"],
                condition_description=sig["condition_description"],
                regime_filter=sig.get("regime_filter") or {},
                forward_days=int(sig.get("forward_days", 5)),
            )
            for sig in raw.get("signals", [])
        ]

        # In-memory store: signal_name → SignalValidation
        self._validations: Dict[str, SignalValidation] = {}

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_signals_for_pool(self, pool: str) -> List[SignalDefinition]:
        """Return all signal definitions that cover the given asset pool."""
        return [s for s in self.definitions if pool in s.asset_pools]

    def get_signals_for_pool_and_regime(
        self, pool: str, regime: str
    ) -> List[SignalDefinition]:
        """
        Return signals that are active for the given pool *and* regime.

        Regime-filter logic:
        - regime_filter is empty dict  → always active (no restriction)
        - regime_filter has an entry for *pool*  → only active when regime is in that list
        - regime_filter has entries but NOT for *pool* → always active for this pool
        """
        result: List[SignalDefinition] = []
        for sig in self.definitions:
            if pool not in sig.asset_pools:
                continue
            pool_regimes = sig.regime_filter.get(pool)
            if pool_regimes is None:
                # No restriction for this pool (empty dict or pool not in filter)
                result.append(sig)
            elif regime in pool_regimes:
                result.append(sig)
        return result

    def get_signal_by_name(self, name: str) -> Optional[SignalDefinition]:
        """Return the signal definition with the given name, or None."""
        for sig in self.definitions:
            if sig.name == name:
                return sig
        return None

    # ------------------------------------------------------------------
    # Validation storage
    # ------------------------------------------------------------------

    def set_validation(self, signal_name: str, validation: SignalValidation) -> None:
        """Store a validation result for the named signal."""
        self._validations[signal_name] = validation

    def get_validation(self, signal_name: str) -> Optional[SignalValidation]:
        """Retrieve a stored validation result, or None if not yet validated."""
        return self._validations.get(signal_name)

    def load_validations_from_dir(self, dir_path: str) -> int:
        """
        Bulk-load validation JSON files from *dir_path*.

        Each file must be a JSON object with keys matching SignalValidation
        fields plus an optional ``signal_name`` key.  The signal name is
        inferred from the filename (stem) when the key is absent.

        Returns the number of validations successfully loaded.
        """
        count = 0
        for filename in os.listdir(dir_path):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(dir_path, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as fh:
                    data = json.load(fh)

                # Derive signal name: prefer explicit key, fall back to filename stem
                signal_name = data.get("signal_name") or os.path.splitext(filename)[0]

                validation = SignalValidation(
                    hit_rate=float(data["hit_rate"]),
                    avg_return=float(data["avg_return"]),
                    sample_size=int(data["sample_size"]),
                    validated_date=str(data["validated_date"]),
                    regime_hit_rates=data.get("regime_hit_rates") or {},
                )
                self._validations[signal_name] = validation
                count += 1
            except (KeyError, ValueError, json.JSONDecodeError):
                # Skip malformed files silently
                continue

        return count
