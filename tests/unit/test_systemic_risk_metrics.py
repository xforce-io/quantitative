"""Tests for event-path metrics."""

from quant.analysis.indicators.systemic_risk.metrics import (
    evaluate_state_path,
    false_positive_rate,
)


class TestEvaluateStatePath:
    def test_lead_negative_when_early(self):
        dates = [
            "2020-02-20",
            "2020-02-21",
            "2020-02-24",
            "2020-02-25",
            "2020-03-23",
        ]
        states = ["normal", "building", "building", "confirmed", "confirmed"]
        m = evaluate_state_path(dates, states, anchor_date="2020-03-23")
        assert m.hit is True
        assert m.miss is False
        assert m.first_building == "2020-02-21"
        assert m.first_confirmed == "2020-02-25"
        assert m.lead_confirmed is not None and m.lead_confirmed < 0

    def test_miss_all_normal(self):
        dates = ["2020-01-01", "2020-01-02", "2020-01-03"]
        states = ["normal", "normal", "normal"]
        m = evaluate_state_path(dates, states, anchor_date="2020-01-02")
        assert m.miss is True
        assert m.hit is False
        assert m.first_confirmed is None


class TestFalsePositiveRate:
    def test_fp(self):
        states = ["normal", "confirmed", "normal", "building"]
        quiet = [True, True, True, False]
        assert false_positive_rate(states, quiet) == 1 / 3
