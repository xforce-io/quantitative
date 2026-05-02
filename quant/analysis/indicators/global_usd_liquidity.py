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
from datetime import datetime, timedelta

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


def compute_derivatives(
    composite_series: pd.Series,
    window: int = 20,
) -> 'tuple[pd.Series, pd.Series]':
    """Compute first and second derivatives of a confidence time series.

    Parameters
    ----------
    composite_series:
        Daily composite confidence series (output of
        ``GlobalUsdLiquidityAnalyzer._build_composite_series``).
    window:
        Rolling difference window in trading days.  20 ≈ 1 calendar month.

    Returns
    -------
    (velocity, acceleration)
        velocity:     ``composite.diff(window)`` — change in pp over *window* days.
        acceleration: daily change of velocity, smoothed with *window*-day
                      rolling mean.  Needs ≈ ``2*window + 1`` valid input
                      observations before producing non-NaN values.
    """
    velocity = composite_series.diff(window)
    velocity.name = 'velocity'
    acceleration = velocity.diff(1).rolling(window).mean()
    acceleration.name = 'acceleration'
    return velocity, acceleration


def compute_divergence(
    confidence_series: pd.Series,
    gold_series: pd.Series,
    window: int = 60,
) -> 'tuple[pd.Series, str, str]':
    """Compute rolling correlation between liquidity confidence and gold returns.

    Both series are converted to ``diff(1)`` (daily changes) before computing
    the rolling Pearson correlation, so the result captures co-movement of
    *changes* rather than levels.

    Parameters
    ----------
    confidence_series:
        Daily composite confidence (from ``_build_composite_series``).
    gold_series:
        Daily gold price (e.g. GC=F Close).
    window:
        Rolling correlation window in trading days.  60 ≈ 3 months.

    Returns
    -------
    (correlation_series, regime, regime_cn)
        correlation_series: rolling correlation, range [-1, 1].
        regime:    one of 'normal' (r > 0.3), 'divergent' (r < -0.3),
                   'decoupled' (|r| ≤ 0.3), or 'unknown' (insufficient data).
        regime_cn: Chinese label for the regime with interpretation.
    """
    # Align on common dates
    df = pd.DataFrame({
        'conf': confidence_series,
        'gold': gold_series,
    }).dropna()

    if len(df) < window + 1:
        empty = pd.Series(dtype=float, name='correlation')
        return empty, 'unknown', '数据不足'

    # Use daily changes to capture co-movement direction
    conf_diff = df['conf'].diff()
    gold_ret = df['gold'].pct_change()
    correlation = conf_diff.rolling(window).corr(gold_ret)
    correlation.name = 'correlation'

    latest = correlation.dropna()
    if latest.empty:
        return correlation, 'unknown', '数据不足'

    corr_val = float(latest.iloc[-1])

    if corr_val > 0.3:
        regime, regime_cn = 'normal', f'正常同步 (r={corr_val:.2f})：流动性驱动金价'
    elif corr_val < -0.3:
        regime, regime_cn = 'divergent', f'显著背离 (r={corr_val:.2f})：避险/央行买盘主导'
    else:
        regime, regime_cn = 'decoupled', f'弱相关 (r={corr_val:.2f})：多因子混合驱动'

    return correlation, regime, regime_cn


def detect_inflection_points(acceleration_series: pd.Series) -> pd.DatetimeIndex:
    """Find dates where the acceleration series crosses zero.

    A zero-crossing indicates a change in the *direction* of the rate of
    change — i.e., a liquidity inflection point.

    Parameters
    ----------
    acceleration_series:
        Second derivative series (output of :func:`compute_derivatives`).

    Returns
    -------
    pd.DatetimeIndex
        Dates of zero-crossings (sign changes).
    """
    clean = acceleration_series.dropna()
    if len(clean) < 2:
        return pd.DatetimeIndex([])
    signs = np.sign(clean)
    # diff() produces NaN for the first element, which is excluded by > 0
    crossings = signs.diff().abs() > 0
    return clean.index[crossings]


# ---------------------------------------------------------------------------
# FRED-backed analyzer
# ---------------------------------------------------------------------------


class GlobalUsdLiquidityAnalyzer:
    def __init__(self, fred_api_key=None):
        self._fred = None
        self._fred_api_key = fred_api_key

    def _get_fred(self):
        """Lazy-load FRED client."""
        if self._fred is None:
            from fredapi import Fred
            import os
            from dotenv import load_dotenv
            load_dotenv()
            api_key = self._fred_api_key or os.environ.get('FRED_API_KEY')
            if not api_key:
                raise ValueError("需要 FRED API Key")
            self._fred = Fred(api_key=api_key)
        return self._fred

    def _fetch_indicator_series(self, indicator_name, lookback_days=1095):
        """Fetch raw time series for one indicator from FRED.

        Handles 3 compute types:
        - 'direct': single series, use as-is
        - 'subtract': two series, s1 - s2
        - 'net_liquidity': WALCL - WTREGEN - RRPONTSYD

        All results forward-filled to daily frequency.
        """
        config = INDICATOR_CONFIG[indicator_name]
        fred = self._get_fred()
        start_date = datetime.now() - timedelta(days=lookback_days)

        series_list = []
        for series_id in config['fred_series']:
            data = fred.get_series(series_id, observation_start=start_date)
            if data is not None:
                data = data.dropna()
            series_list.append(data)

        compute = config['compute']
        if compute == 'direct':
            result = series_list[0]
        elif compute == 'subtract':
            s1, s2 = series_list
            combined = pd.DataFrame({'s1': s1, 's2': s2}).ffill().dropna()
            result = combined['s1'] - combined['s2']
        elif compute == 'net_liquidity':
            walcl, wtregen, rrp = series_list
            combined = pd.DataFrame({'walcl': walcl, 'wtregen': wtregen, 'rrp': rrp}).ffill().dropna()
            result = combined['walcl'] - combined['wtregen'] - combined['rrp']
        else:
            raise ValueError(f"Unknown compute type: {compute}")

        # Forward-fill to daily
        result = result.asfreq('D').ffill()
        return result.dropna()

    def analyze(self, lookback_days=1095, display_days=365):
        """Full analysis: fetch all indicators, compute confidence, aggregate.

        Returns dict with:
        - confidence: total composite confidence (-100 to 100)
        - wow_change: week-over-week change (5 trading days)
        - groups: per-group details with confidence, weight, indicators
        - indicators: per-indicator details with current_value, percentile, confidence, series
        - composite_series: time series of total confidence for charting
        - analyzed_at: timestamp
        """
        indicator_results = {}
        indicator_series = {}
        confidence_series = {}

        # Phase 1: Fetch all indicator series
        for name, config in INDICATOR_CONFIG.items():
            try:
                series = self._fetch_indicator_series(name, lookback_days)
                indicator_series[name] = series
            except Exception as e:
                logger.error(f"❌ {config['label']} 获取失败: {e}")
                indicator_results[name] = {'error': str(e), 'label': config['label'], 'group': config['group']}

        # Phase 2: Compute rolling confidence
        for name, series in indicator_series.items():
            config = INDICATOR_CONFIG[name]
            conf_series = compute_rolling_confidence(series, window=PERCENTILE_WINDOW, inverted=config['inverted'])
            confidence_series[name] = conf_series

            latest_conf = conf_series.dropna()
            if not latest_conf.empty:
                current_value = series.iloc[-1]
                pctile = percentileofscore(series.iloc[-PERCENTILE_WINDOW:].dropna().values, current_value, kind='mean')
                indicator_results[name] = {
                    'label': config['label'],
                    'group': config['group'],
                    'current_value': round(float(current_value), 4),
                    'percentile': round(pctile, 1),
                    'confidence': float(latest_conf.iloc[-1]),
                    'series': conf_series,
                }
            else:
                indicator_results[name] = {'label': config['label'], 'group': config['group'], 'error': '数据不足'}

        # Phase 3: Group aggregation
        group_confidences = {}
        group_details = {}
        for group_name in GROUP_WEIGHTS:
            group_indicators = {k: v.get('confidence') for k, v in indicator_results.items() if v.get('group') == group_name and 'confidence' in v}
            group_conf = aggregate_group_confidence(group_indicators)
            group_confidences[group_name] = group_conf
            group_details[group_name] = {
                'label': GROUP_LABELS[group_name],
                'confidence': group_conf,
                'weight': GROUP_WEIGHTS[group_name],
                'indicators': {k: v for k, v in indicator_results.items() if v.get('group') == group_name},
            }

        # Phase 4: Total + composite series
        total_confidence = aggregate_total_confidence(group_confidences, GROUP_WEIGHTS)
        composite_series = self._build_composite_series(confidence_series, display_days)

        wow_change = None
        velocity = None
        acceleration = None
        velocity_series = None
        acceleration_series = None
        inflection_points = []

        if composite_series is not None and len(composite_series.dropna()) > 5:
            valid = composite_series.dropna()
            wow_change = round(float(valid.iloc[-1] - valid.iloc[-6]), 2)

            # Compute derivatives — needs ≈ 2*window+1 valid points to produce
            # non-NaN acceleration (velocity = diff(window), then a window-day
            # rolling mean over its first difference).
            derivative_window = 20
            if len(valid) > 2 * derivative_window:
                vel_s, acc_s = compute_derivatives(
                    composite_series, window=derivative_window
                )
                velocity_series = vel_s
                acceleration_series = acc_s
                inflection_points = detect_inflection_points(acc_s).tolist()

                vel_clean = vel_s.dropna()
                acc_clean = acc_s.dropna()
                if not vel_clean.empty:
                    velocity = round(float(vel_clean.iloc[-1]), 2)
                if not acc_clean.empty:
                    acceleration = round(float(acc_clean.iloc[-1]), 2)

        # Phase 5: Gold-liquidity divergence
        correlation_series = None
        divergence_regime = None
        divergence_regime_cn = None
        if composite_series is not None:
            try:
                gold_series = self._fetch_gold_price(display_days)
            except ImportError:
                logger.warning("黄金背离计算跳过：未安装 yfinance")
                gold_series = None
            except Exception:
                logger.warning("黄金价格获取失败", exc_info=True)
                gold_series = None

            if gold_series is not None:
                try:
                    correlation_series, divergence_regime, divergence_regime_cn = (
                        compute_divergence(composite_series, gold_series)
                    )
                except Exception:
                    logger.warning("黄金背离相关性计算失败", exc_info=True)

        return {
            'confidence': total_confidence,
            'wow_change': wow_change,
            'velocity': velocity,
            'acceleration': acceleration,
            'velocity_series': velocity_series,
            'acceleration_series': acceleration_series,
            'inflection_points': inflection_points,
            'correlation_series': correlation_series,
            'divergence_regime': divergence_regime,
            'divergence_regime_cn': divergence_regime_cn,
            'groups': group_details,
            'indicators': indicator_results,
            'composite_series': composite_series,
            'analyzed_at': datetime.now().isoformat(),
        }

    @staticmethod
    def _fetch_gold_price(display_days: int = 365) -> 'pd.Series | None':
        """Fetch gold futures close price from Yahoo Finance."""
        import yfinance as yf
        end = datetime.now()
        start = end - timedelta(days=display_days + 90)  # extra buffer for correlation window
        gold = yf.download('GC=F', start=start, end=end, progress=False)
        if gold is None or gold.empty:
            return None
        if isinstance(gold.columns, pd.MultiIndex):
            gold.columns = gold.columns.get_level_values(0)
        col = 'Close' if 'Close' in gold.columns else 'close'
        if col not in gold.columns:
            return None
        return gold[col].dropna()

    def _build_composite_series(self, confidence_series, display_days=365):
        """Build composite confidence time series by day-by-day aggregation."""
        if not confidence_series:
            return None

        df = pd.DataFrame(confidence_series)
        group_cols = {}
        for name, config in INDICATOR_CONFIG.items():
            if name in df.columns:
                group_cols.setdefault(config['group'], []).append(name)

        group_means = pd.DataFrame()
        for group_name, cols in group_cols.items():
            group_means[group_name] = df[cols].mean(axis=1)

        def weighted_row(row):
            valid = {k: v for k, v in row.items() if pd.notna(v)}
            if not valid:
                return np.nan
            total_w = sum(GROUP_WEIGHTS[k] for k in valid)
            return sum(v * GROUP_WEIGHTS[k] / total_w for k, v in valid.items())

        composite = group_means.apply(weighted_row, axis=1)
        cutoff = datetime.now() - timedelta(days=display_days)
        return composite[composite.index >= cutoff]
