#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for undervalue × cycle screening pipeline."""

from __future__ import annotations

import pandas as pd
import pytest

from quant.analysis.screener.undervalue_cycle import (
    BAD_CYCLE_STAGES,
    UndervalueCycleConfig,
    apply_undervalue_cycle_screen,
    map_industry_to_cycle,
    normalize_cycle_stage,
)


class TestNormalizeCycleStage:
    def test_chinese_decline_variants(self):
        for raw in ("衰退", "下行", "周期下行", "调整"):
            assert normalize_cycle_stage(raw) == "decline"

    def test_english_passthrough(self):
        assert normalize_cycle_stage("recovery") == "recovery"
        assert normalize_cycle_stage("late_cycle") == "late_cycle"

    def test_unknown(self):
        assert normalize_cycle_stage("") == "unknown"
        assert normalize_cycle_stage(None) == "unknown"
        assert normalize_cycle_stage("完全没听过") == "unknown"


class TestMapIndustryToCycle:
    def test_known_industry_from_fundamentals(self):
        info = map_industry_to_cycle("房地产")
        assert info.stage == "decline"
        assert info.safety_mult < 1.0
        assert info.source == "fundamentals"

    def test_alias_resource_to_metals(self):
        info = map_industry_to_cycle("资源")
        assert info.stage in {"mid_cycle", "recovery", "unknown"} or info.raw_stage
        assert info.industry_key  # resolved somehow

    def test_unknown_industry(self):
        info = map_industry_to_cycle("火星矿业")
        assert info.stage == "unknown"
        assert info.safety_mult == 1.0


class TestApplyScreen:
    def _rows(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "symbol": "000002.SZ",
                    "name": "万科A",
                    "industry": "房地产",
                    "undervalue_score": 99.0,
                    "price_position": 1.5,
                },
                {
                    "symbol": "601600.SH",
                    "name": "中国铝业",
                    "industry": "有色金属",
                    "undervalue_score": 70.0,
                    "price_position": 30.0,
                },
                {
                    "symbol": "601899.SH",
                    "name": "紫金矿业",
                    "industry": "资源",
                    "undervalue_score": 65.0,
                    "price_position": 50.0,
                },
                {
                    "symbol": "000858.SZ",
                    "name": "五粮液",
                    "industry": "白酒",
                    "undervalue_score": 95.0,
                    "price_position": 2.0,
                    "value_trap_flags": "",
                },
                {
                    "symbol": "600048.SH",
                    "name": "保利发展",
                    "industry": "房地产",
                    "undervalue_score": 98.0,
                    "price_position": 3.0,
                    "value_trap_flags": "revenue_decline,low_roe",
                },
            ]
        )

    def test_hard_veto_decline_and_traps(self):
        cfg = UndervalueCycleConfig(
            exclude_stages=frozenset({"decline"}),
            hard_veto_trap_flags=frozenset({"revenue_decline", "profit_collapse"}),
        )
        result = apply_undervalue_cycle_screen(self._rows(), cfg)
        passed = result[result["passed"]]
        rejected = result[~result["passed"]]

        assert "000002.SZ" in set(rejected["symbol"])
        assert "600048.SH" in set(rejected["symbol"])
        # 白酒 maps to mature (not decline) under static IFA — should pass unless excluded
        assert not passed.empty
        assert "000002.SZ" not in set(passed["symbol"])

    def test_exclude_late_cycle_optional(self):
        df = pd.DataFrame(
            [
                {
                    "symbol": "601012.SH",
                    "name": "隆基",
                    "industry": "光伏",
                    "undervalue_score": 99.0,
                    "price_position": 1.5,
                },
                {
                    "symbol": "601600.SH",
                    "name": "中国铝业",
                    "industry": "有色金属",
                    "undervalue_score": 70.0,
                    "price_position": 30.0,
                },
            ]
        )
        cfg = UndervalueCycleConfig(
            exclude_stages=frozenset({"decline", "late_cycle"}),
        )
        result = apply_undervalue_cycle_screen(df, cfg)
        # 光伏 static stage 扩张 → late_cycle
        longi = result.loc[result["symbol"] == "601012.SH"].iloc[0]
        assert longi["cycle_stage"] == "late_cycle"
        assert longi["passed"] is False or longi["passed"] == False

    def test_cycle_adjusted_score_orders_recovery_above_raw_undervalue_trap(self):
        cfg = UndervalueCycleConfig(exclude_stages=frozenset({"decline"}))
        result = apply_undervalue_cycle_screen(self._rows(), cfg)
        passed = result[result["passed"]].sort_values(
            "cycle_adjusted_score", ascending=False
        )
        # Real estate must not top the list after filter
        assert passed.iloc[0]["symbol"] != "000002.SZ"
        assert "cycle_stage" in result.columns
        assert "cycle_label" in result.columns
        assert "reject_reason" in result.columns

    def test_min_undervalue_threshold(self):
        cfg = UndervalueCycleConfig(
            exclude_stages=frozenset(),
            min_undervalue_score=80.0,
        )
        result = apply_undervalue_cycle_screen(self._rows(), cfg)
        passed_syms = set(result.loc[result["passed"], "symbol"])
        assert "601600.SH" not in passed_syms  # 70 < 80
        assert "000858.SZ" in passed_syms

    def test_empty_input(self):
        result = apply_undervalue_cycle_screen(pd.DataFrame(), UndervalueCycleConfig())
        assert result.empty

    def test_missing_industry_column_raises(self):
        with pytest.raises(ValueError, match="industry"):
            apply_undervalue_cycle_screen(
                pd.DataFrame([{"symbol": "x", "undervalue_score": 1}]),
                UndervalueCycleConfig(),
            )


class TestBadStagesConstant:
    def test_default_bad_stages_include_decline(self):
        assert "decline" in BAD_CYCLE_STAGES
