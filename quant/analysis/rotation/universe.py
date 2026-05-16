"""Rotation universe configuration loader."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml

_REQUIRED_FIELDS = ("symbol", "name", "category")
_DEFAULT_YAML_RELATIVE = "config/rotation_universe.yaml"


@dataclass(frozen=True)
class EtfEntry:
    """One ETF in the rotation universe."""

    symbol: str
    name: str
    category: str
    volume_threshold: Optional[int] = None


@dataclass(frozen=True)
class VolumeFilterConfig:
    """Global volume filter parameters from universe YAML."""

    enabled: bool = False
    min_avg_monthly_volume_shares: int = 1_000_000
    lookback_months: int = 3


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _coerce_entries(raw_list: Iterable[dict]) -> list[EtfEntry]:
    entries: list[EtfEntry] = []
    for raw in raw_list or []:
        for field in _REQUIRED_FIELDS:
            if field not in raw:
                raise ValueError(f"universe entry missing field {field!r}: {raw}")
        threshold = raw.get("min_avg_monthly_volume_shares")
        entries.append(
            EtfEntry(
                symbol=str(raw["symbol"]),
                name=str(raw["name"]),
                category=str(raw["category"]),
                volume_threshold=int(threshold) if threshold is not None else None,
            )
        )
    return entries


def _resolve_path(path: Path | str | None) -> Path:
    if path is None:
        return _project_root() / _DEFAULT_YAML_RELATIVE
    return Path(path)


def load_universe(path: Path | str | None = None) -> list[EtfEntry]:
    """Load and validate the rotation universe from yaml.

    Raises FileNotFoundError if the file is missing, ValueError on schema
    problems (missing field or duplicate symbol).
    """
    resolved = _resolve_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"universe yaml not found: {resolved}")

    with resolved.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    entries = _coerce_entries(data.get("industry_etfs"))
    entries.extend(_coerce_entries(data.get("style_etfs")))
    entries.extend(_coerce_entries(data.get("defensive_global_etfs")))

    seen: set[str] = set()
    for entry in entries:
        if entry.symbol in seen:
            raise ValueError(f"duplicate symbol in universe: {entry.symbol}")
        seen.add(entry.symbol)

    return entries


def load_volume_filter_config(
    path: Path | str | None = None,
) -> tuple[VolumeFilterConfig, set[str]]:
    """Return (VolumeFilterConfig, industry_symbols).

    industry_symbols is the set of symbols subject to volume filtering
    (only industry_etfs entries; style and defensive ETFs are exempt).
    """
    resolved = _resolve_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"universe yaml not found: {resolved}")

    with resolved.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    vf = data.get("volume_filter", {})
    config = VolumeFilterConfig(
        enabled=bool(vf.get("enabled", False)),
        min_avg_monthly_volume_shares=int(vf.get("min_avg_monthly_volume_shares", 1_000_000)),
        lookback_months=int(vf.get("lookback_months", 3)),
    )
    industry_symbols = {
        str(e["symbol"])
        for e in (data.get("industry_etfs") or [])
        if "symbol" in e
    }
    return config, industry_symbols
