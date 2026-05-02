"""Rotation universe configuration loader."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

_REQUIRED_FIELDS = ("symbol", "name", "category")
_DEFAULT_YAML_RELATIVE = "config/rotation_universe.yaml"


@dataclass(frozen=True)
class EtfEntry:
    """One ETF in the rotation universe."""

    symbol: str
    name: str
    category: str


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _coerce_entries(raw_list: Iterable[dict]) -> list[EtfEntry]:
    entries: list[EtfEntry] = []
    for raw in raw_list or []:
        for field in _REQUIRED_FIELDS:
            if field not in raw:
                raise ValueError(f"universe entry missing field {field!r}: {raw}")
        entries.append(
            EtfEntry(
                symbol=str(raw["symbol"]),
                name=str(raw["name"]),
                category=str(raw["category"]),
            )
        )
    return entries


def load_universe(path: Path | str | None) -> list[EtfEntry]:
    """Load and validate the rotation universe from yaml.

    Pass ``None`` to load the repo default at ``config/rotation_universe.yaml``.
    Raises FileNotFoundError if the file is missing, ValueError on schema problems
    (missing field or duplicate symbol).
    """
    if path is None:
        resolved = _project_root() / _DEFAULT_YAML_RELATIVE
    else:
        resolved = Path(path)

    if not resolved.exists():
        raise FileNotFoundError(f"universe yaml not found: {resolved}")

    with resolved.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    entries = _coerce_entries(data.get("industry_etfs"))
    entries.extend(_coerce_entries(data.get("style_etfs")))

    seen: set[str] = set()
    for entry in entries:
        if entry.symbol in seen:
            raise ValueError(f"duplicate symbol in universe: {entry.symbol}")
        seen.add(entry.symbol)

    return entries
