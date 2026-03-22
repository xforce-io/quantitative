"""
ETF Screening Skill — agent-friendly, side-effect-free wrappers around
the ETFMomentumScreener engine.

Design principles:
  • Every function returns a plain dict (or list / DataFrame) — never prints.
  • Parameters use simple, JSON-serialisable types so that LLM tool-call
    schemas can be generated automatically.
  • Docstrings are kept concise and descriptive for LLM consumption.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy singleton — avoids heavy import cost at module level
# ---------------------------------------------------------------------------

_screener_instance = None


def _get_screener():
    """Return a lazily-initialised ETFMomentumScreener singleton."""
    global _screener_instance
    if _screener_instance is None:
        from quant.analysis.screener.etf_screener import ETFMomentumScreener
        _screener_instance = ETFMomentumScreener()
    return _screener_instance


# ===================================================================
# Public Skill Functions
# ===================================================================


def screen_etfs(
    etf_types: Optional[List[str]] = None,
    max_etfs: Optional[int] = None,
) -> pd.DataFrame:
    """Screen ETFs by momentum, valuation and multi-factor scoring.

    Args:
        etf_types: ETF category filter, e.g. ['broad_market', 'sector'].
            If None, all categories are included.
        max_etfs: Max number of ETFs to analyse.  Useful for quick scans.

    Returns:
        DataFrame sorted by ``overall_score`` descending.  Key columns:
        ts_code, name, category, 1m_return … 12m_return, rsi,
        overall_score, grade, passes_screening, valuation_level,
        risk_warnings, failed_reasons.
    """
    screener = _get_screener()
    return screener.screen_etfs(etf_types, max_etfs)


def screen_symbols(
    symbols: List[str],
    info_map: Optional[Dict[str, Dict[str, str]]] = None,
    max_etfs: Optional[int] = None,
    default_category: str = "config_screen",
) -> pd.DataFrame:
    """Screen a custom list of symbols (ETFs or stocks).

    Args:
        symbols: List of ts_codes, e.g. ['512480.SH', '510300.SH'].
        info_map: Optional metadata per code, e.g.
            {'512480.SH': {'name': '半导体ETF', 'category': 'sector'}}.
        max_etfs: Limit the number of symbols analysed.
        default_category: Fallback category label when info_map is absent.

    Returns:
        DataFrame identical in schema to :func:`screen_etfs`.
    """
    screener = _get_screener()
    return screener.screen_symbols(
        symbols,
        info_map=info_map,
        max_etfs=max_etfs,
        default_category=default_category,
    )


def analyze_etf(
    symbol: str,
    include_valuation: bool = True,
    include_rs: bool = True,
) -> Dict[str, Any]:
    """Analyse a single ETF and return a structured result dict.

    Args:
        symbol: ETF code, e.g. '510300.SH'.
        include_valuation: Whether to include valuation analysis.
        include_rs: Whether to include relative-strength analysis.

    Returns:
        Dict with keys: success, ts_code, data_points, analysis_date,
        momentum (dict), valuation (dict), industry_meta (dict),
        rs_analysis (dict), peg_analysis (dict), fundamentals_analysis (dict),
        screening_result (dict with momentum/overall sub-dicts).
    """
    screener = _get_screener()
    return screener.analyze_etf(
        symbol,
        include_valuation=include_valuation,
        include_rs=include_rs,
    )


def get_screening_config() -> Dict[str, Any]:
    """Return the current screening threshold configuration.

    Returns:
        Dict with keys: momentum, trend, volume, quality — each containing
        the thresholds used during screening.
    """
    screener = _get_screener()
    return dict(screener.screening_config)


def list_etf_pools() -> Dict[str, Dict[str, Any]]:
    """List all available ETF pool names defined in config/screens.yaml.

    Returns:
        Dict mapping pool_name → {count: int, sample_codes: list[str]}.
        Empty dict if configuration is missing.
    """
    from pathlib import Path
    import yaml

    config_path = Path("config") / "screens.yaml"
    if not config_path.exists():
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        screens = data.get("screens", {})
        result: Dict[str, Dict[str, Any]] = {}
        for name, entries in screens.items():
            codes = list((entries or {}).keys())
            result[name] = {
                "count": len(codes),
                "sample_codes": codes[:5],
            }
        return result
    except Exception as e:
        logger.warning("Failed to load ETF pools: %s", e)
        return {}
