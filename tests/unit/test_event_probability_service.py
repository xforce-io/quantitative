"""
Unit tests for event probability service.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant.analysis.event_investment import EventProbabilityService


class TestEventProbabilityService:
    """Validate the end-to-end event inference pipeline."""

    def test_policy_export_control_flow(self):
        """Export control news should map to the canonical policy event."""
        service = EventProbabilityService()

        result = service.analyze_news(
            title="美国扩大 AI 芯片出口限制",
            source="财联社",
            published_at="2026-03-15 09:30",
            news_text=(
                "美方进一步收紧面向中国市场的高端 AI 芯片出口限制，"
                "并扩大先进制程半导体设备的管制范围。"
            ),
            market_context={"confirmation_score": 0.3, "crowding_score": 0.1},
        )

        assert result.event.event_type == "policy_export_control"
        assert result.event.canonical_label == "policy_export_control"
        assert len(result.causal_paths) >= 2
        assert {scenario.name for scenario in result.scenarios} == {"Bull", "Base", "Bear"}
        assert abs(sum(scenario.probability for scenario in result.scenarios) - 1.0) < 1e-9
        assert any(impact.direction == "positive" for impact in result.asset_impacts)
        assert result.graph["nodes"]
        assert "Scenario Probabilities" in result.markdown_report

    def test_large_order_event_generates_positive_mapping(self):
        """Large order news should map to company_large_order."""
        service = EventProbabilityService()

        result = service.analyze_news(
            title="公司公告重大中标",
            source="公司公告",
            published_at="2026-03-15 18:00",
            news_text="公司公告称已中标大型项目并签订长期合同，订单金额较高。",
        )

        assert result.event.event_type == "company_large_order"
        assert any(impact.asset_name == "订单中标公司" for impact in result.asset_impacts)
