"""
Rule-based parser for raw news events.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from .event_models import Event


class NewsEventParser:
    """Parse raw news text into a structured event candidate."""

    DEFAULT_SOURCE_RELIABILITY = {
        "新华社": 0.9,
        "上证报": 0.82,
        "证券时报": 0.8,
        "财联社": 0.78,
        "公司公告": 0.86,
    }

    def __init__(self, taxonomy: dict[str, Any]):
        self.taxonomy = taxonomy
        self.entity_aliases = taxonomy.get("entity_aliases", {})
        self.action_aliases = taxonomy.get("action_aliases", {})
        self.event_types = taxonomy.get("event_types", {})

    def parse(
        self,
        news_text: str,
        title: str = "",
        source: str = "",
        published_at: str = "",
    ) -> Event:
        """Parse one news item into an initial event object."""
        text = self._clean_text("\n".join(part for part in [title, news_text] if part).strip())
        event_type, matched_keywords = self._detect_event_type(text)
        entities = self._extract_entities(text)
        action = self._detect_action(text)
        direction = self._infer_direction(text, event_type)
        magnitude = self._infer_magnitude(text)
        urgency = self._infer_urgency(text)
        evidence = self._extract_evidence(news_text or title, matched_keywords)
        sectors = self.event_types.get(event_type, {}).get("default_sectors", [])
        regions = [entity for entity in entities if entity in {"US", "China", "Europe"}]
        confidence = self._estimate_confidence(
            source=source,
            matched_keywords=matched_keywords,
            entities=entities,
            evidence=evidence,
        )

        return Event(
            event_id=str(uuid.uuid4())[:12],
            title=title or "Untitled event",
            source=source or "Unknown",
            published_at=published_at or "",
            event_type=event_type,
            summary=self._summarize_text(text),
            entities=entities,
            regions=regions,
            sectors=sectors,
            direction=direction,
            magnitude=magnitude,
            urgency=urgency,
            time_horizon=self.event_types.get(event_type, {}).get("default_time_horizon", "short_term"),
            confidence=confidence,
            evidence=evidence,
            action=action,
            canonical_label=event_type,
            metadata={"matched_keywords": matched_keywords},
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _detect_event_type(self, text: str) -> tuple[str, list[str]]:
        best_type = "generic_market_event"
        best_matches: list[str] = []
        lowered = text.lower()
        for event_type, config in self.event_types.items():
            keywords = config.get("keywords", [])
            matches = [keyword for keyword in keywords if keyword.lower() in lowered]
            if len(matches) > len(best_matches):
                best_type = event_type
                best_matches = matches
        return best_type, best_matches

    def _extract_entities(self, text: str) -> list[str]:
        entities: list[str] = []
        lowered = text.lower()
        for canonical_name, aliases in self.entity_aliases.items():
            if any(alias.lower() in lowered for alias in aliases):
                entities.append(canonical_name)
        return entities

    def _detect_action(self, text: str) -> str:
        lowered = text.lower()
        for canonical_action, aliases in self.action_aliases.items():
            if any(alias.lower() in lowered for alias in aliases):
                return canonical_action
        return "unknown"

    def _infer_direction(self, text: str, event_type: str) -> str:
        event_direction = self.event_types.get(event_type, {}).get("direction", "neutral")
        if event_direction != "mixed":
            return event_direction

        lowered = text.lower()
        positive_words = ["提升", "增长", "受益", "利好", "突破", "上调", "订单"]
        negative_words = ["限制", "下滑", "受损", "利空", "事故", "下调", "处罚"]
        positive_hits = sum(word in lowered for word in positive_words)
        negative_hits = sum(word in lowered for word in negative_words)
        if positive_hits > negative_hits:
            return "positive"
        if negative_hits > positive_hits:
            return "negative"
        return "mixed"

    @staticmethod
    def _infer_magnitude(text: str) -> float:
        strong_words = ["重大", "大幅", "全面", "显著", "创纪录", "超预期"]
        medium_words = ["进一步", "新增", "计划", "上调", "下调"]
        if any(word in text for word in strong_words):
            return 0.85
        if any(word in text for word in medium_words):
            return 0.65
        return 0.5

    @staticmethod
    def _infer_urgency(text: str) -> str:
        if any(word in text for word in ["立即", "本周", "今日", "今晚", "突发"]):
            return "high"
        if any(word in text for word in ["近期", "本月", "将于"]):
            return "medium"
        return "normal"

    @staticmethod
    def _extract_evidence(text: str, matched_keywords: list[str]) -> list[str]:
        if not text:
            return matched_keywords[:3]

        sentences = re.split(r"[。！？;\n]+", text)
        evidence = [
            sentence.strip()
            for sentence in sentences
            if sentence.strip() and any(keyword in sentence for keyword in matched_keywords)
        ]
        return evidence[:3] or matched_keywords[:3]

    def _estimate_confidence(
        self,
        source: str,
        matched_keywords: list[str],
        entities: list[str],
        evidence: list[str],
    ) -> float:
        source_score = self.DEFAULT_SOURCE_RELIABILITY.get(source, 0.68)
        keyword_score = min(len(matched_keywords) * 0.08, 0.2)
        entity_score = min(len(entities) * 0.04, 0.12)
        evidence_score = 0.08 if evidence else 0.0
        return round(min(0.95, source_score * 0.7 + keyword_score + entity_score + evidence_score), 2)

    @staticmethod
    def _summarize_text(text: str, max_length: int = 180) -> str:
        if len(text) <= max_length:
            return text
        return f"{text[: max_length - 3]}..."
