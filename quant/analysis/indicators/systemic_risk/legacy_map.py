"""Map legacy macro scores to pseudo SystemicRiskState labels for evaluation."""

from __future__ import annotations


def risk_score_to_pseudo_state(
    risk_score: float,
    confirmed_threshold: float = 75.0,
    building_threshold: float = 50.0,
) -> str:
    """Map MacroLiquidityAnalyzer risk_score (0–100) to a pseudo state."""
    if risk_score is None:
        return "degraded"
    if risk_score >= confirmed_threshold:
        return "confirmed"
    if risk_score >= building_threshold:
        return "building"
    return "normal"


def confidence_to_pseudo_state(
    confidence: float,
    confirmed_threshold: float = -40.0,
    building_threshold: float = -10.0,
) -> str:
    """Map GlobalUsdLiquidity confidence (-100..+100) to a pseudo state.

    Negative confidence = tighter liquidity = higher systemic risk.
    """
    if confidence is None:
        return "degraded"
    if confidence <= confirmed_threshold:
        return "confirmed"
    if confidence <= building_threshold:
        return "building"
    return "normal"
