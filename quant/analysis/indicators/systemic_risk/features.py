"""Pure feature stress mapping for systemic risk (no network I/O)."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import percentileofscore

from quant.analysis.indicators.momentum_delta import MomentumDelta
from quant.analysis.indicators.systemic_risk.types import FeaturePoint


def rolling_percentile(
    series: pd.Series,
    window: int = 252,
    min_periods: Optional[int] = None,
) -> pd.Series:
    """Rolling percentile rank of the current value within ``window`` observations.

    When history is shorter than ``window``, uses all available history once
    ``min_periods`` observations exist (default: min(60, window)).
    """
    n = len(series)
    out = np.full(n, np.nan)
    values = series.to_numpy(dtype=float)
    if min_periods is None:
        min_periods = min(60, window)
    min_periods = max(5, int(min_periods))
    for i in range(n):
        if np.isnan(values[i]):
            continue
        start = max(0, i - window + 1)
        window_vals = values[start : i + 1]
        mask = ~np.isnan(window_vals)
        if mask.sum() < min_periods:
            continue
        lookback = window_vals[mask]
        out[i] = float(percentileofscore(lookback, values[i], kind="mean"))
    return pd.Series(out, index=series.index, name=series.name)


def value_to_stress(
    percentile: Optional[float],
    inverted: bool = False,
) -> Optional[float]:
    """Map 0–100 percentile to stress in [0, 1].

    By default high percentile → high stress. When ``inverted`` is True
    (e.g. net liquidity), high percentile → low stress.
    """
    if percentile is None or (isinstance(percentile, float) and np.isnan(percentile)):
        return None
    p = float(np.clip(percentile, 0.0, 100.0))
    raw = p / 100.0
    stress = 1.0 - raw if inverted else raw
    return float(np.clip(stress, 0.0, 1.0))


def _rolling_zscore(series: pd.Series, window: int = 60) -> pd.Series:
    mean = series.rolling(window, min_periods=max(10, window // 3)).mean()
    std = series.rolling(window, min_periods=max(10, window // 3)).std()
    z = (series - mean) / std.replace(0.0, np.nan)
    return z


def compute_feature_point(
    name: str,
    series: pd.Series,
    inverted: bool = False,
    percentile_window: int = 252,
    zscore_window: int = 60,
    change_window: int = 20,
    velocity_window: int = 5,
    as_of: Optional[pd.Timestamp] = None,
) -> FeaturePoint:
    """Compute a FeaturePoint from a full history series (optionally truncated by as_of)."""
    if series is None or series.empty:
        return FeaturePoint(name=name, value=None)

    s = series.dropna().sort_index()
    if as_of is not None:
        s = s.loc[:as_of]
    if s.empty:
        return FeaturePoint(name=name, value=None)

    value = float(s.iloc[-1])
    as_of_str = pd.Timestamp(s.index[-1]).strftime("%Y-%m-%d")

    pct_series = rolling_percentile(s, window=min(percentile_window, max(len(s), 1)))
    percentile = (
        float(pct_series.iloc[-1]) if not pd.isna(pct_series.iloc[-1]) else None
    )
    # Fallback: if window too long for history, use expanding percentile of available data
    if percentile is None and len(s) >= 10:
        percentile = float(percentileofscore(s.values, value, kind="mean"))

    stress = value_to_stress(percentile, inverted=inverted)

    z_series = _rolling_zscore(s, window=min(zscore_window, max(len(s), 1)))
    zscore = float(z_series.iloc[-1]) if not pd.isna(z_series.iloc[-1]) else None

    delta = MomentumDelta.compute(
        s, velocity_window=velocity_window, zscore_window=zscore_window
    )

    # Blend level with multi-horizon stress (quiet-tightening sensitive)
    if len(s) >= 20:
        path = compute_stress_series(
            s,
            inverted=inverted,
            percentile_window=percentile_window,
            short_window=min(60, percentile_window),
            change_window=max(5, min(change_window, 10)),
        )
        if not path.empty and not pd.isna(path.iloc[-1]):
            stress = float(path.iloc[-1])

    return FeaturePoint(
        name=name,
        value=value,
        percentile=round(percentile, 2) if percentile is not None else None,
        zscore=round(zscore, 3) if zscore is not None else None,
        velocity=float(delta.get("velocity") or 0.0),
        acceleration=float(delta.get("acceleration") or 0.0),
        stress=round(stress, 4) if stress is not None else None,
        as_of=as_of_str,
        stale=False,
    )


def compute_gold_fc_divergence(
    gold_momentum: Optional[float],
    l1_stress: Optional[float],
    divergence_threshold: float = 0.55,
) -> float:
    """Surface asset strength + tight financial conditions → divergence stress.

    Parameters
    ----------
    gold_momentum:
        Positive when gold is rising (e.g. 20d return or velocity).
    l1_stress:
        Aggregate L1 stress in [0, 1].
    divergence_threshold:
        Minimum L1 stress required for divergence to register.
    """
    if gold_momentum is None or l1_stress is None:
        return 0.0
    if gold_momentum <= 0:
        return 0.0
    if l1_stress < divergence_threshold:
        return 0.0
    # Scale by how far above threshold and gold momentum strength
    excess = (l1_stress - divergence_threshold) / max(1e-6, 1.0 - divergence_threshold)
    mom = float(np.clip(abs(gold_momentum) / 0.05, 0.0, 1.0))  # ~5% move saturates
    return float(np.clip(0.5 * excess + 0.5 * min(1.0, l1_stress) * (0.5 + 0.5 * mom), 0.0, 1.0))


def aggregate_mean_stress(stresses: dict) -> float:
    """Mean of non-None stress values; 0.0 if empty."""
    vals = [float(v) for v in stresses.values() if v is not None]
    if not vals:
        return 0.0
    return float(sum(vals) / len(vals))


def compute_stress_series(
    series: pd.Series,
    inverted: bool = False,
    percentile_window: int = 126,
    short_window: int = 60,
    change_window: int = 10,
) -> pd.Series:
    """Level + short-window + change blended stress path in [0, 1].

    Designed to catch quiet tightening: spreads may not be at multi-year
    extremes but are rising sharply vs recent history.
    """
    s = series.dropna().sort_index()
    if s.empty:
        return s

    long_pct = rolling_percentile(s, window=percentile_window)
    short_pct = rolling_percentile(s, window=min(short_window, percentile_window))

    long_s = long_pct / 100.0
    short_s = short_pct / 100.0
    if inverted:
        long_s = 1.0 - long_s
        short_s = 1.0 - short_s

    # Change stress: for non-inverted, rising = more stress; inverted opposite
    chg = s.diff(change_window)
    chg_pct = rolling_percentile(chg.dropna(), window=min(short_window, max(len(chg.dropna()), 20)))
    chg_s = chg_pct.reindex(s.index) / 100.0
    if inverted:
        # rising net liquidity → less stress
        chg_s = 1.0 - chg_s

    # max(level, short, blend) — sensitive to recent moves without discarding level
    blend = 0.45 * short_s + 0.35 * long_s + 0.20 * chg_s
    stress = pd.concat([long_s, short_s, chg_s, blend], axis=1).max(axis=1)
    return stress.clip(0.0, 1.0)
