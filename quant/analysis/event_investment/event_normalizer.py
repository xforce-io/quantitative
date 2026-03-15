"""
Canonical normalization for parsed events.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .event_models import Event


class EventNormalizer:
    """Normalize event types, sectors, and entities."""

    def __init__(self, taxonomy: dict[str, Any]):
        self.taxonomy = taxonomy
        self.event_types = taxonomy.get("event_types", {})
        self.entity_alias_to_canonical = self._build_entity_alias_map(
            taxonomy.get("entity_aliases", {})
        )

    @staticmethod
    def _build_entity_alias_map(entity_aliases: dict[str, list[str]]) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        for canonical_name, aliases in entity_aliases.items():
            alias_map[canonical_name.lower()] = canonical_name
            for alias in aliases:
                alias_map[alias.lower()] = canonical_name
        return alias_map

    def normalize(self, event: Event) -> Event:
        """Return a normalized event object."""
        normalized = deepcopy(event)
        normalized.event_type = self._normalize_event_type(event)
        normalized.canonical_label = normalized.event_type
        normalized.entities = self._normalize_entities(event.entities)
        event_config = self.event_types.get(normalized.event_type, {})
        normalized.sectors = event_config.get("default_sectors", normalized.sectors)
        normalized.time_horizon = event_config.get(
            "default_time_horizon",
            normalized.time_horizon,
        )
        if not normalized.regions:
            normalized.regions = [
                entity for entity in normalized.entities if entity in {"US", "China", "Europe"}
            ]
        return normalized

    def _normalize_event_type(self, event: Event) -> str:
        if event.event_type in self.event_types:
            return event.event_type

        matched_keywords = event.metadata.get("matched_keywords", [])
        for event_type, config in self.event_types.items():
            aliases = config.get("aliases", [])
            if event.event_type in aliases:
                return event_type
            if any(keyword in aliases for keyword in matched_keywords):
                return event_type
        return "generic_market_event"

    def _normalize_entities(self, entities: list[str]) -> list[str]:
        canonical_entities: list[str] = []
        for entity in entities:
            canonical_name = self.entity_alias_to_canonical.get(entity.lower(), entity)
            if canonical_name not in canonical_entities:
                canonical_entities.append(canonical_name)
        return canonical_entities
