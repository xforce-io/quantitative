#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Undervalue × cycle screening pipeline (thin candidate generator).

Combines price/fundamental undervaluation scores with industry cycle stage
to reject value traps in bad cycle positions and re-rank survivors.

This is an Analysis-layer filter, not a replacement for industry rotation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Iterable, Optional

import pandas as pd

from quant.analysis.screener.industry_fundamentals_analyzer import (
    IndustryFundamentalsAnalyzer,
)

# Stages treated as hard-veto defaults for "must not be in a bad cycle".
BAD_CYCLE_STAGES: FrozenSet[str] = frozenset({"decline"})

# Map static Chinese cycle_stage labels → English buckets used in screening.
_STAGE_NORMALIZE = {
    "衰退": "decline",
    "下行": "decline",
    "周期下行": "decline",
    "调整": "decline",
    # Pharma etc. often labeled 结构调整 in static DB — treat as early trough, not hard decline
    "结构调整": "trough_early",
    "扩张": "late_cycle",
    "成熟前期": "late_cycle",
    "周期": "mid_cycle",
    "稳定增长": "mid_cycle",
    "稳定": "mature_defensive",
    "成熟": "mature_defensive",
    "成长": "structural_growth",
    "早期成长": "trough_early",
    # English passthrough / dynamic labels
    "decline": "decline",
    "late_cycle": "late_cycle",
    "mid_cycle": "mid_cycle",
    "mature_defensive": "mature_defensive",
    "recovery": "recovery",
    "trough_early": "trough_early",
    "structural_growth": "structural_growth",
}

# Candidate-file industry aliases → IFA keys
_INDUSTRY_ALIASES = {
    "资源": "有色金属",
    "家电零售": "消费",
    "家电": "消费",
    "汽车相关": "新能源车",
    "新能源汽车": "新能源车",
    "养殖农产品": "食品饮料",
    "农业": "食品饮料",
    "金融": "银行",
    "保险": "银行",
    "券商": "券商",
    "证券": "券商",
    "计算机及软件": "科技",
    "消费电子": "科技",
    "科创": "科技",
    "能源": "煤炭",
    "稀土": "有色金属",
    "建材": "基建",
    "水泥": "基建",
    "钢铁": "钢铁",
    "化工": "机械",
    "交通运输": "基建",
    "交运": "基建",
    "公用事业": "基建",
    "电力": "基建",
    "食品饮料": "食品饮料",
    "白酒": "白酒",
    "医药": "医药",
    "房地产": "房地产",
    "地产": "房地产",
    "光伏": "光伏",
    "半导体": "半导体",
    "军工": "军工",
    "新能源": "新能源车",
    "储能": "储能",
    "风电": "风电",
    "基建": "基建",
    "机械": "机械",
    "消费": "消费",
    "科技": "科技",
    "银行": "银行",
    "有色金属": "有色金属",
    "煤炭": "煤炭",
    "REITs": "REITs",
}

_STAGE_LABELS = {
    "decline": "下行/出清 — 价值陷阱风险高",
    "late_cycle": "景气后段 — 防周期顶点",
    "mid_cycle": "景气中段 — 中性偏多",
    "mature_defensive": "成熟防御 — 高安全边际、低突破",
    "recovery": "复苏确认 — 突破优先",
    "trough_early": "周期底部/早复苏 — 安全边际与突破双优",
    "structural_growth": "结构成长 — 看质量与估值",
    "unknown": "未知周期 — 中性",
}

# Multipliers applied to undervalue_score (safety-oriented default).
_STAGE_SAFETY_MULT = {
    "decline": 0.65,
    "late_cycle": 0.85,
    "mid_cycle": 1.00,
    "mature_defensive": 1.20,
    "recovery": 1.10,
    "trough_early": 1.15,
    "structural_growth": 0.95,
    "unknown": 1.00,
}


@dataclass(frozen=True)
class UndervalueCycleConfig:
    """Screening rules for undervalue × cycle filter."""

    exclude_stages: FrozenSet[str] = field(default_factory=lambda: BAD_CYCLE_STAGES)
    min_undervalue_score: float = 0.0
    hard_veto_trap_flags: FrozenSet[str] = field(
        default_factory=lambda: frozenset({"revenue_decline", "profit_collapse"})
    )
    # If True, late_cycle is also hard-vetoed (stricter).
    exclude_late_cycle: bool = False


@dataclass(frozen=True)
class CycleInfo:
    """Resolved industry cycle metadata."""

    industry_key: str
    raw_stage: str
    stage: str
    safety_mult: float
    label: str
    source: str  # fundamentals | alias | unknown


def normalize_cycle_stage(raw: Optional[str]) -> str:
    """Normalize Chinese/English cycle stage labels to English buckets."""
    if raw is None:
        return "unknown"
    text = str(raw).strip()
    if not text:
        return "unknown"
    return _STAGE_NORMALIZE.get(text, "unknown")


def map_industry_to_cycle(
    industry: Optional[str],
    analyzer: Optional[IndustryFundamentalsAnalyzer] = None,
) -> CycleInfo:
    """Map an industry name to cycle stage via fundamentals DB + aliases."""
    if not industry or not str(industry).strip():
        return CycleInfo(
            industry_key="",
            raw_stage="",
            stage="unknown",
            safety_mult=1.0,
            label=_STAGE_LABELS["unknown"],
            source="unknown",
        )

    industry = str(industry).strip()
    analyzer = analyzer or IndustryFundamentalsAnalyzer()

    key = _INDUSTRY_ALIASES.get(industry, industry)
    metrics = analyzer.get_industry_metrics(key)
    source = "fundamentals" if metrics else "unknown"

    if metrics is None and key != industry:
        metrics = analyzer.get_industry_metrics(industry)
        if metrics:
            key = industry
            source = "fundamentals"

    if metrics is None:
        # Fuzzy via analyzer
        metrics = analyzer.get_industry_metrics(industry)
        if metrics:
            source = "fundamentals"
            key = industry

    if not metrics:
        return CycleInfo(
            industry_key=key,
            raw_stage="",
            stage="unknown",
            safety_mult=1.0,
            label=_STAGE_LABELS["unknown"],
            source="unknown",
        )

    raw_stage = str(metrics.get("cycle_stage", ""))
    stage = normalize_cycle_stage(raw_stage)
    mult = _STAGE_SAFETY_MULT.get(stage, 1.0)
    return CycleInfo(
        industry_key=key,
        raw_stage=raw_stage,
        stage=stage,
        safety_mult=mult,
        label=_STAGE_LABELS.get(stage, _STAGE_LABELS["unknown"]),
        source=source,
    )


def _parse_trap_flags(value) -> set[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return set()
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return set()
    return {part.strip() for part in text.replace(";", ",").split(",") if part.strip()}


def apply_undervalue_cycle_screen(
    df: pd.DataFrame,
    config: Optional[UndervalueCycleConfig] = None,
    analyzer: Optional[IndustryFundamentalsAnalyzer] = None,
) -> pd.DataFrame:
    """Apply cycle veto + score adjustment to a candidate table.

    Required columns:
      - industry
      - undervalue_score (0-100, higher = cheaper)

    Optional:
      - symbol, name, price_position, value_trap_flags
      - cycle_stage (if already present, skip industry mapping)

    Returns a copy with columns:
      cycle_stage, cycle_label, safety_mult, cycle_adjusted_score,
      passed, reject_reason
    """
    config = config or UndervalueCycleConfig()
    if df is None or df.empty:
        return pd.DataFrame()

    if "industry" not in df.columns:
        raise ValueError("input DataFrame must include 'industry' column")
    if "undervalue_score" not in df.columns:
        raise ValueError("input DataFrame must include 'undervalue_score' column")

    exclude = set(config.exclude_stages)
    if config.exclude_late_cycle:
        exclude.add("late_cycle")

    analyzer = analyzer or IndustryFundamentalsAnalyzer()
    rows = []
    for _, row in df.iterrows():
        out = row.to_dict()
        uv = float(row["undervalue_score"]) if pd.notna(row["undervalue_score"]) else 0.0

        if "cycle_stage" in df.columns and pd.notna(row.get("cycle_stage")) and str(
            row.get("cycle_stage")
        ).strip():
            stage = normalize_cycle_stage(row.get("cycle_stage"))
            mult = _STAGE_SAFETY_MULT.get(stage, 1.0)
            label = _STAGE_LABELS.get(stage, _STAGE_LABELS["unknown"])
            industry_key = str(row.get("industry_mapped") or row.get("industry") or "")
            raw_stage = str(row.get("cycle_stage"))
            source = "input"
        else:
            info = map_industry_to_cycle(row.get("industry"), analyzer=analyzer)
            stage = info.stage
            mult = info.safety_mult
            label = info.label
            industry_key = info.industry_key
            raw_stage = info.raw_stage
            source = info.source

        traps = _parse_trap_flags(row.get("value_trap_flags"))
        hit_traps = traps & set(config.hard_veto_trap_flags)

        reasons: list[str] = []
        passed = True
        if stage in exclude:
            passed = False
            reasons.append(f"bad_cycle:{stage}")
        if uv < config.min_undervalue_score:
            passed = False
            reasons.append(f"undervalue<{config.min_undervalue_score}")
        if hit_traps:
            passed = False
            reasons.append("trap:" + ",".join(sorted(hit_traps)))

        adjusted = round(uv * mult, 4)

        out.update(
            {
                "industry_mapped": industry_key,
                "cycle_stage_raw": raw_stage,
                "cycle_stage": stage,
                "cycle_label": label,
                "safety_mult": mult,
                "cycle_source": source,
                "cycle_adjusted_score": adjusted,
                "passed": bool(passed),
                "reject_reason": "|".join(reasons),
            }
        )
        rows.append(out)

    result = pd.DataFrame(rows)
    # Stable rank: passed first, then cycle_adjusted_score desc
    result["_pass_rank"] = result["passed"].map({True: 0, False: 1})
    result = result.sort_values(
        by=["_pass_rank", "cycle_adjusted_score"],
        ascending=[True, False],
    ).drop(columns=["_pass_rank"])
    result = result.reset_index(drop=True)
    return result


def stages_from_csv_list(text: str) -> FrozenSet[str]:
    """Parse comma-separated stage list for CLI."""
    if not text or not str(text).strip():
        return frozenset()
    parts = [p.strip() for p in str(text).split(",") if p.strip()]
    return frozenset(normalize_cycle_stage(p) if p not in _STAGE_SAFETY_MULT else p for p in parts)


__all__ = [
    "BAD_CYCLE_STAGES",
    "CycleInfo",
    "UndervalueCycleConfig",
    "apply_undervalue_cycle_screen",
    "map_industry_to_cycle",
    "normalize_cycle_stage",
    "stages_from_csv_list",
]
