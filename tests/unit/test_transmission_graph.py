#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for TransmissionGraph — cross-asset causal edge monitoring.
Follows TDD: tests written before implementation.
"""

import pytest
from pathlib import Path

# Path to config used by the graph
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "transmission_edges.yaml"


class TestTransmissionEdge:
    def test_creation(self):
        from quant.analysis.transmission import TransmissionEdge

        edge = TransmissionEdge(
            source="DXY",
            target="gold",
            direction="inverse",
            lag_min_days=0,
            lag_max_days=1,
            threshold=0.8,
            strength=0.72,
            source_ticker="DX-Y.NYB",
            target_ticker="GC=F",
        )

        assert edge.source == "DXY"
        assert edge.target == "gold"
        assert edge.direction == "inverse"
        assert edge.lag_min_days == 0
        assert edge.lag_max_days == 1
        assert edge.threshold == 0.8
        assert edge.strength == 0.72
        assert edge.source_ticker == "DX-Y.NYB"
        assert edge.target_ticker == "GC=F"

    def test_creation_optional_tickers_default_none(self):
        from quant.analysis.transmission import TransmissionEdge

        edge = TransmissionEdge(
            source="VIX",
            target="risk_assets",
            direction="inverse",
            lag_min_days=0,
            lag_max_days=1,
            threshold=3.0,
            strength=0.70,
        )
        assert edge.source_ticker is None
        assert edge.target_ticker is None


class TestTransmissionGraph:
    def test_loads_edges_from_config(self):
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        assert len(graph.edges) > 0
        sources = [e.source for e in graph.edges]
        assert "DXY" in sources

    def test_all_edges_have_threshold(self):
        """Ensures different threshold key names are all mapped to .threshold."""
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        for edge in graph.edges:
            assert edge.threshold is not None
            assert edge.threshold > 0

    def test_check_triggers_with_significant_move(self):
        """DXY +1.43% (105 -> 106.5) should trigger gold (threshold 0.8%) and copper (threshold 1.0%)."""
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        previous = {"DXY": 105.0}
        current = {"DXY": 106.5}  # +1.43%

        transmissions = graph.check_triggers(current, previous)

        triggered_targets = [t.edge.target for t in transmissions]
        assert "gold" in triggered_targets
        assert "copper" in triggered_targets

    def test_no_trigger_below_threshold(self):
        """DXY +0.19% (105 -> 105.2) is below all DXY thresholds — nothing triggered."""
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        previous = {"DXY": 105.0}
        current = {"DXY": 105.2}  # +0.19%

        transmissions = graph.check_triggers(current, previous)

        dxy_triggers = [t for t in transmissions if t.edge.source == "DXY"]
        assert len(dxy_triggers) == 0

    def test_active_transmission_has_countdown(self):
        """Triggered transmission should have days_remaining >= 0 and status 'triggered'."""
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        previous = {"DXY": 105.0}
        current = {"DXY": 106.5}

        transmissions = graph.check_triggers(current, previous)

        assert len(transmissions) > 0
        for t in transmissions:
            assert t.days_remaining >= 0
            assert t.status == "triggered"

    def test_update_transmission_confirmed(self):
        """DXY -> gold (inverse), source_move=+1.5%, target_move=-1.2% → 'confirmed'."""
        from quant.analysis.transmission import TransmissionGraph, ActiveTransmission

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        # Get the DXY->gold edge
        dxy_gold_edges = [e for e in graph.edges if e.source == "DXY" and e.target == "gold"]
        assert len(dxy_gold_edges) >= 1
        edge = dxy_gold_edges[0]

        transmission = ActiveTransmission(
            edge=edge,
            triggered_at="2026-04-12",
            source_move=1.5,
            expected_target="down",
            days_remaining=1,
            status="triggered",
        )

        updated = graph.update_status(transmission, target_move=-1.2)
        assert updated.status == "confirmed"

    def test_update_transmission_failed(self):
        """DXY -> gold (inverse), source_move=+1.5%, target_move=+0.8% → 'failed'."""
        from quant.analysis.transmission import TransmissionGraph, ActiveTransmission

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        dxy_gold_edges = [e for e in graph.edges if e.source == "DXY" and e.target == "gold"]
        assert len(dxy_gold_edges) >= 1
        edge = dxy_gold_edges[0]

        transmission = ActiveTransmission(
            edge=edge,
            triggered_at="2026-04-12",
            source_move=1.5,
            expected_target="down",
            days_remaining=1,
            status="triggered",
        )

        updated = graph.update_status(transmission, target_move=0.8)
        assert updated.status == "failed"

    def test_get_edges_by_source(self):
        """DXY should have >= 2 edges (gold, copper, a_share_northbound)."""
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        dxy_edges = graph.get_edges_by_source("DXY")
        assert len(dxy_edges) >= 2
        targets = [e.target for e in dxy_edges]
        assert "gold" in targets
        assert "copper" in targets

    def test_get_edges_by_target(self):
        """gold should have >= 1 edge."""
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        gold_edges = graph.get_edges_by_target("gold")
        assert len(gold_edges) >= 1

    def test_get_active_transmissions_filters_status(self):
        """Only 'triggered' and 'propagating' transmissions are active."""
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        previous = {"DXY": 105.0}
        current = {"DXY": 106.5}
        transmissions = graph.check_triggers(current, previous)

        # All newly triggered should appear in active
        active = graph.get_active_transmissions()
        assert len(active) >= len(transmissions)
        for t in active:
            assert t.status in ("triggered", "propagating")

    def test_tick_day_decrements_countdown(self):
        """tick_day should decrement days_remaining and return expired ones."""
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        previous = {"DXY": 105.0}
        current = {"DXY": 106.5}
        graph.check_triggers(current, previous)

        # Find an edge with lag_max_days == 1 (DXY->gold)
        initial_active = graph.get_active_transmissions()
        day1_active_count = len(initial_active)
        assert day1_active_count > 0

        expired = graph.tick_day()

        # Expired ones should have days_remaining == 0 (or were at 0 before tick)
        for t in expired:
            assert t.days_remaining == 0

    def test_check_triggers_direct_edge(self):
        """crude_oil +6% should trigger inflation_expectations (threshold 5%, direct)."""
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        previous = {"crude_oil": 70.0}
        current = {"crude_oil": 74.2}  # +6%

        transmissions = graph.check_triggers(current, previous)

        targets = [t.edge.target for t in transmissions]
        assert "inflation_expectations" in targets

    def test_inverse_positive_move_expects_down(self):
        """For an inverse edge, a positive source move should set expected_target to 'down'."""
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        previous = {"DXY": 105.0}
        current = {"DXY": 106.5}  # positive move

        transmissions = graph.check_triggers(current, previous)

        gold_transmissions = [t for t in transmissions if t.edge.target == "gold"]
        assert len(gold_transmissions) >= 1
        assert gold_transmissions[0].expected_target == "down"

    def test_inverse_negative_move_expects_up(self):
        """For an inverse edge, a negative source move should set expected_target to 'up'."""
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        previous = {"DXY": 105.0}
        current = {"DXY": 103.5}  # -1.43%, exceeds 0.8% threshold

        transmissions = graph.check_triggers(current, previous)

        gold_transmissions = [t for t in transmissions if t.edge.target == "gold"]
        assert len(gold_transmissions) >= 1
        assert gold_transmissions[0].expected_target == "up"

    def test_direct_positive_move_expects_up(self):
        """For a direct edge, a positive source move should set expected_target to 'up'."""
        from quant.analysis.transmission import TransmissionGraph

        graph = TransmissionGraph(config_path=CONFIG_PATH)

        previous = {"gold": 2000.0}
        current = {"gold": 2031.0}  # +1.55%, exceeds 1.5% threshold

        transmissions = graph.check_triggers(current, previous)

        sector_transmissions = [t for t in transmissions if t.edge.target == "a_share_gold_sector"]
        assert len(sector_transmissions) >= 1
        assert sector_transmissions[0].expected_target == "up"
