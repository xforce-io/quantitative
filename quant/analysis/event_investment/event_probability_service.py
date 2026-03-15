"""
Orchestration service for event-driven investment probability graph.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .causal_graph_engine import CausalGraphEngine
from .event_models import EventAnalysisResult
from .event_normalizer import EventNormalizer
from .investment_mapper import InvestmentMapper
from .market_evidence_calibrator import MarketEvidenceCalibrator
from .news_event_parser import NewsEventParser
from .scenario_probability_engine import ScenarioProbabilityEngine


class EventProbabilityService:
    """End-to-end event probability graph service."""

    EVENT_TYPE_LABELS = {
        "policy_export_control": "政策出口管制",
        "policy_subsidy": "政策补贴支持",
        "industry_price_increase": "行业提价",
        "industry_capacity_cut": "行业限产减产",
        "company_large_order": "公司重大订单",
        "company_accident": "公司事故事件",
        "geopolitical_conflict": "地缘冲突升级",
        "generic_market_event": "一般市场事件",
    }
    DIRECTION_LABELS = {
        "positive": "利多",
        "negative": "利空",
        "mixed": "中性偏分歧",
        "neutral": "中性",
        "watch": "观察",
        "event": "事件",
    }

    def __init__(self, knowledge_dir: Path | None = None):
        base_dir = knowledge_dir or (
            Path(__file__).resolve().parents[2] / "knowledge" / "event_graph"
        )
        self.taxonomy = self._load_yaml(base_dir / "event_taxonomy.yaml")
        self.causal_edges = self._load_yaml(base_dir / "causal_edges.yaml")
        self.asset_mapping = self._load_yaml(base_dir / "sector_asset_mapping.yaml")
        self.parser = NewsEventParser(self.taxonomy)
        self.normalizer = EventNormalizer(self.taxonomy)
        self.graph_engine = CausalGraphEngine(self.causal_edges)
        self.scenario_engine = ScenarioProbabilityEngine()
        self.calibrator = MarketEvidenceCalibrator()
        self.mapper = InvestmentMapper(self.asset_mapping)

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    def analyze_news(
        self,
        news_text: str,
        title: str = "",
        source: str = "",
        published_at: str = "",
        market_context: dict[str, Any] | None = None,
    ) -> EventAnalysisResult:
        """Run the full event inference pipeline."""
        raw_event = self.parser.parse(
            news_text=news_text,
            title=title,
            source=source,
            published_at=published_at,
        )
        canonical_event = self.normalizer.normalize(raw_event)
        causal_paths = self.graph_engine.rollout(canonical_event)
        scenarios = self.scenario_engine.infer(canonical_event, causal_paths)
        round_6_scenarios = [deepcopy(scenario).to_dict() for scenario in scenarios]
        calibrated_scenarios = self.calibrator.calibrate(
            canonical_event,
            scenarios,
            market_context=market_context,
        )
        asset_impacts = self.mapper.map_assets(canonical_event, calibrated_scenarios)
        graph = self._build_graph(canonical_event, causal_paths, calibrated_scenarios, asset_impacts)
        rounds = {
            "round_1_event_candidates": [raw_event.to_dict()],
            "round_2_canonical_event": canonical_event.to_dict(),
            "round_3_rollout_causal_chains": [path.to_dict() for path in causal_paths],
            "round_4_normalized_chains": [path.to_dict() for path in causal_paths],
            "round_5_scored_paths": [path.to_dict() for path in causal_paths],
            "round_6_scenarios": round_6_scenarios,
            "round_7_calibrated_scenarios": [scenario.to_dict() for scenario in calibrated_scenarios],
            "round_8_asset_impacts": [impact.to_dict() for impact in asset_impacts],
            "round_9_risk_notes": [impact.risk_note for impact in asset_impacts[:5]],
        }
        markdown_report = self._render_markdown_report(
            canonical_event,
            causal_paths,
            calibrated_scenarios,
            asset_impacts,
        )
        return EventAnalysisResult(
            event=canonical_event,
            causal_paths=causal_paths,
            scenarios=calibrated_scenarios,
            asset_impacts=asset_impacts,
            graph=graph,
            rounds=rounds,
            markdown_report=markdown_report,
        )

    @staticmethod
    def _build_graph(event, causal_paths, scenarios, asset_impacts) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()

        def add_node(
            node_id: str,
            label: str,
            node_type: str,
            group: str,
            lane: int | None = None,
            level: int | None = None,
        ) -> None:
            if node_id in seen_nodes:
                return
            seen_nodes.add(node_id)
            nodes.append(
                {
                    "id": node_id,
                    "label": label,
                    "type": node_type,
                    "group": group,
                    "lane": lane,
                    "level": level,
                }
            )

        event_label = f"{event.title}\n[{EventProbabilityService.EVENT_TYPE_LABELS.get(event.event_type, event.event_type)}]"
        add_node(event.event_id, event_label, "event", "event", lane=0, level=0)
        for lane_index, path in enumerate(causal_paths, start=1):
            previous_id = event.event_id
            path_probability = round(max(0.01, min(0.99, path.strength * path.confidence)), 4)
            for index, label in enumerate(path.nodes[1:], start=1):
                node_id = f"{path.path_id}-node-{index}"
                add_node(
                    node_id,
                    label,
                    "factor" if index < len(path.nodes) - 1 else "asset_group",
                    path.direction,
                    lane=lane_index,
                    level=index,
                )
                edges.append(
                    {
                        "source": previous_id,
                        "target": node_id,
                        "direction": path.direction,
                        "weight": path.strength,
                        "probability": path_probability,
                        "confidence": path.confidence,
                        "strength": path.strength,
                        "lane": lane_index,
                        "level": index,
                        "kind": "causal",
                        "label": (
                            f"{EventProbabilityService.DIRECTION_LABELS.get(path.direction, path.direction)}"
                            f" | 传导概率 {path_probability:.0%}"
                        ),
                    }
                )
                previous_id = node_id

        return {
            "nodes": nodes,
            "edges": edges,
            "scenarios": [scenario.to_dict() for scenario in scenarios],
            "assets": [impact.to_dict() for impact in asset_impacts],
        }

    @staticmethod
    def _render_markdown_report(event, causal_paths, scenarios, asset_impacts) -> str:
        scenario_lines = "\n".join(
            f"- {scenario.name}: {scenario.probability:.0%} | Conditions: {', '.join(scenario.conditions)}"
            for scenario in scenarios
        )
        path_lines = "\n".join(
            f"{index}. {path.reason_chain} | score={path.strength:.2f} | confidence={path.confidence:.2f}"
            for index, path in enumerate(causal_paths, start=1)
        )
        positive = [impact.asset_name for impact in asset_impacts if impact.direction == "positive"][:5]
        negative = [impact.asset_name for impact in asset_impacts if impact.direction == "negative"][:5]
        watchlist = [impact.asset_name for impact in asset_impacts if impact.direction == "watch"][:5]
        return (
            "## Event Summary\n\n"
            f"- Event Type: {event.event_type}\n"
            f"- Direction: {event.direction}\n"
            f"- Confidence: {event.confidence:.2f}\n\n"
            "## Causal Paths\n\n"
            f"{path_lines}\n\n"
            "## Scenario Probabilities\n\n"
            f"{scenario_lines}\n\n"
            "## Asset Mapping\n\n"
            f"- Positive: {', '.join(positive) if positive else 'N/A'}\n"
            f"- Negative: {', '.join(negative) if negative else 'N/A'}\n"
            f"- Watchlist: {', '.join(watchlist) if watchlist else 'N/A'}\n"
        )
