#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
全球美元流动性置信度指标 (Global USD Liquidity Confidence)

纯计算函数模块 — 不含 FRED API 调用。
提供百分位映射、滚动置信度、分组/总置信度聚合等核心计算能力。

指标分组：
  onshore       — 在岸美元流动性溢价  (权重 40%)
  offshore      — 离岸/资金面压力      (权重 30%)
  net_liquidity — 净流动性基本面       (权重 30%)
"""

import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
from scipy.stats import percentileofscore

project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from quant.core.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

INDICATOR_CONFIG: Dict[str, dict] = {
    'cp_treasury_spread': {
        'fred_series': ['DCPF3M', 'DGS3MO'],
        'compute': 'subtract',
        'inverted': True,
        'group': 'onshore',
        'frequency': 'daily',
        'label': '商票-美债溢价',
    },
    'sofr': {
        'fred_series': ['SOFR'],
        'compute': 'direct',
        'inverted': True,
        'group': 'onshore',
        'frequency': 'daily',
        'label': 'SOFR',
    },
    'effr_iorb_spread': {
        'fred_series': ['EFFR', 'IORB'],
        'compute': 'subtract',
        'inverted': True,
        'group': 'onshore',
        'frequency': 'daily',
        'label': 'EFFR-IORB 溢价',
    },
    'sofr_iorb_spread': {
        'fred_series': ['SOFR', 'IORB'],
        'compute': 'subtract',
        'inverted': True,
        'group': 'onshore',
        'frequency': 'daily',
        'label': 'SOFR-IORB 溢价',
    },
    'nfcirisk': {
        'fred_series': ['NFCIRISK'],
        'compute': 'direct',
        'inverted': True,
        'group': 'offshore',
        'frequency': 'weekly',
        'label': 'NFCI 风险子指数',
    },
    'stlfsi4': {
        'fred_series': ['STLFSI4'],
        'compute': 'direct',
        'inverted': True,
        'group': 'offshore',
        'frequency': 'weekly',
        'label': '金融压力指数',
    },
    'net_liquidity': {
        'fred_series': ['WALCL', 'WTREGEN', 'RRPONTSYD'],
        'compute': 'net_liquidity',
        'inverted': False,
        'group': 'net_liquidity',
        'frequency': 'weekly',
        'label': '净流动性',
    },
}

GROUP_WEIGHTS: Dict[str, float] = {
    'onshore': 0.40,
    'offshore': 0.30,
    'net_liquidity': 0.30,
}

GROUP_LABELS: Dict[str, str] = {
    'onshore': '在岸美元流动性溢价',
    'offshore': '离岸/资金面压力',
    'net_liquidity': '净流动性基本面',
}

PERCENTILE_WINDOW: int = 504

# ---------------------------------------------------------------------------
# Pure calculation functions
# ---------------------------------------------------------------------------


def percentile_to_confidence(percentile: float, inverted: bool = False) -> float:
    """Map a 0-100 percentile to a -100 to +100 confidence value.

    Formula: ``(percentile - 50) * 2``

    Parameters
    ----------
    percentile:
        Rank percentile in the range [0, 100].
    inverted:
        When True the sign of the result is negated (higher percentile means
        lower/more-stressed liquidity).

    Returns
    -------
    float
        Confidence value rounded to 2 decimal places, in [-100, 100].
    """
    result = (percentile - 50.0) * 2.0
    if inverted:
        result = -result
    return round(result, 2)


def compute_rolling_confidence(
    series: pd.Series,
    window: int = PERCENTILE_WINDOW,
    inverted: bool = False,
) -> pd.Series:
    """Compute rolling percentile-based confidence for a time series.

    For each position ``i >= window - 1`` (0-indexed), compute the percentile
    of ``series.iloc[i]`` within the lookback window
    ``series.iloc[i - window + 1 : i + 1]`` (inclusive), then map through
    :func:`percentile_to_confidence`.  Positions with insufficient history are
    left as ``NaN``.

    Parameters
    ----------
    series:
        Input time series (DatetimeIndex recommended).
    window:
        Number of observations in each lookback window.
    inverted:
        Passed directly to :func:`percentile_to_confidence`.

    Returns
    -------
    pd.Series
        Confidence series with the same index as *series*.
    """
    n = len(series)
    values = np.full(n, np.nan)

    for i in range(window - 1, n):
        lookback = series.iloc[i - window + 1 : i + 1].dropna()
        if lookback.empty:
            continue
        current = series.iloc[i]
        if pd.isna(current):
            continue
        pct = percentileofscore(lookback.values, current, kind='mean')
        values[i] = percentile_to_confidence(pct, inverted=inverted)

    return pd.Series(values, index=series.index, name=series.name)


def aggregate_group_confidence(
    values: Dict[str, Optional[float]],
) -> Optional[float]:
    """Equal-weight average of non-None confidence values within a group.

    Parameters
    ----------
    values:
        Mapping of indicator name to its confidence value (or ``None`` if
        the indicator is unavailable).

    Returns
    -------
    float or None
        Average confidence, or ``None`` when *values* is empty or all
        entries are ``None``.
    """
    valid = [v for v in values.values() if v is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 2)


def aggregate_total_confidence(
    groups: Dict[str, Optional[float]],
    weights: Dict[str, float],
) -> Optional[float]:
    """Weighted aggregation of group confidences with weight renormalization.

    When a group value is ``None`` its weight is redistributed proportionally
    among the available groups.

    Parameters
    ----------
    groups:
        Mapping of group name to group confidence (or ``None``).
    weights:
        Nominal weights for each group.  Need not sum to 1 — they are
        renormalized internally.

    Returns
    -------
    float or None
        Total confidence value, or ``None`` if all groups are unavailable.
    """
    available = {k: v for k, v in groups.items() if v is not None}
    if not available:
        return None

    total_weight = sum(weights.get(k, 0.0) for k in available)
    if total_weight == 0.0:
        return None

    result = sum(
        v * weights.get(k, 0.0) / total_weight for k, v in available.items()
    )
    return round(result, 2)
