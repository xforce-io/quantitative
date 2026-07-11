"""Point-in-time feature panel builder for systemic risk."""

from __future__ import annotations

from typing import Dict, Mapping, Optional, Union

import pandas as pd

from quant.analysis.indicators.systemic_risk.features import (
    aggregate_mean_stress,
    compute_feature_point,
    compute_gold_fc_divergence,
)
from quant.analysis.indicators.systemic_risk.types import FeaturePoint, FeatureSnapshot

# Feature registry: name → (group, inverted)
FEATURE_SPEC: Dict[str, dict] = {
    # L1
    "sofr_iorb_spread": {"group": "l1", "inverted": False},
    "effr_iorb_spread": {"group": "l1", "inverted": False},
    "cp_tbill_spread": {"group": "l1", "inverted": False},
    "nfcirisk": {"group": "l1", "inverted": False},
    "stlfsi4": {"group": "l1", "inverted": False},
    "hy_oas": {"group": "l1", "inverted": False},
    # L2
    "net_liquidity": {"group": "l2", "inverted": True},
    # L3 confirm
    "vix": {"group": "confirm", "inverted": False},
    "move": {"group": "confirm", "inverted": False},
    # L4
    "copper_gold": {"group": "l4", "inverted": True},  # low ratio = stress
    "real_yield": {"group": "l4", "inverted": False},
    # L5
    "usdjpy": {"group": "l5", "inverted": True},  # JPY strength (USDJPY down) stress-ish via change
    "dgs2": {"group": "l5", "inverted": True},  # lower yield / narrower carry proxy
}

CRITICAL_L1 = ("hy_oas",)


def _as_timestamp(as_of: Union[str, pd.Timestamp]) -> pd.Timestamp:
    return pd.Timestamp(as_of).normalize()


def build_panel_from_frames(
    frames: Mapping[str, pd.Series],
    as_of: Union[str, pd.Timestamp],
    percentile_window: int = 252,
    zscore_window: int = 60,
    change_window: int = 20,
    divergence_threshold: float = 0.55,
    critical_l1: tuple = CRITICAL_L1,
    freshness_days_daily: int = 3,
) -> FeatureSnapshot:
    """Build a FeatureSnapshot from in-memory series dict (test + offline path).

    Parameters
    ----------
    frames:
        Mapping of series name → full history (DatetimeIndex).
        Optional helper key ``hy_oas_d20_src`` is treated as hy_oas for change feature.
    as_of:
        Inclusive point-in-time cutoff.
    """
    ts = _as_timestamp(as_of)
    as_of_str = ts.strftime("%Y-%m-%d")

    # Normalize: allow hy_oas_d20_src alias
    series_map: Dict[str, pd.Series] = {}
    for k, v in frames.items():
        if k == "hy_oas_d20_src":
            continue
        if v is None or len(v) == 0:
            continue
        s = v.copy()
        s.index = pd.to_datetime(s.index).normalize()
        series_map[k] = s.sort_index()

    if "hy_oas" not in series_map and "hy_oas_d20_src" in frames:
        s = frames["hy_oas_d20_src"].copy()
        s.index = pd.to_datetime(s.index).normalize()
        series_map["hy_oas"] = s.sort_index()

    points: Dict[str, FeaturePoint] = {}
    l1: Dict[str, Optional[float]] = {}
    l2: Dict[str, Optional[float]] = {}
    confirm: Dict[str, Optional[float]] = {}

    for name, spec in FEATURE_SPEC.items():
        raw = series_map.get(name)
        if raw is None:
            fp = FeaturePoint(name=name, value=None, as_of=as_of_str)
        else:
            truncated = raw.loc[:ts]
            fp = compute_feature_point(
                name=name,
                series=truncated,
                inverted=spec["inverted"],
                percentile_window=percentile_window,
                zscore_window=zscore_window,
                change_window=change_window,
            )
            # Freshness
            if not truncated.empty:
                last = pd.Timestamp(truncated.index[-1]).normalize()
                age = (ts - last).days
                fp.stale = age > freshness_days_daily
        points[name] = fp
        group = spec["group"]
        if group == "l1":
            l1[name] = fp.stress
        elif group == "l2":
            l2[name] = fp.stress
        elif group == "confirm":
            confirm[name] = fp.stress

    # hy_oas_d20: stress from 20d change of hy_oas (widening = stress)
    hy = series_map.get("hy_oas")
    if hy is not None:
        hy_t = hy.loc[:ts].dropna()
        if len(hy_t) > change_window:
            chg = hy_t.diff(change_window).dropna()
            fp_chg = compute_feature_point(
                name="hy_oas_d20",
                series=chg,
                inverted=False,
                percentile_window=min(percentile_window, max(len(chg), 20)),
                change_window=0,
            )
            points["hy_oas_d20"] = fp_chg
            l1["hy_oas_d20"] = fp_chg.stress
        else:
            l1["hy_oas_d20"] = None
    else:
        l1["hy_oas_d20"] = None

    # Gold momentum for divergence
    gold = series_map.get("gold")
    gold_mom = None
    if gold is not None:
        g = gold.loc[:ts].dropna()
        if len(g) > 20:
            gold_mom = float(g.iloc[-1] / g.iloc[-21] - 1.0)

    l1_agg = aggregate_mean_stress(l1)
    div = compute_gold_fc_divergence(
        gold_momentum=gold_mom,
        l1_stress=l1_agg,
        divergence_threshold=divergence_threshold,
    )

    missing_critical = []
    stale_critical = False
    for key in critical_l1:
        fp = points.get(key)
        if fp is None or fp.stress is None:
            # also check if series entirely missing
            if key not in series_map or series_map[key].loc[:ts].dropna().empty:
                missing_critical.append(key)
        elif fp.stale:
            stale_critical = True

    return FeatureSnapshot(
        as_of=as_of_str,
        l1_stresses=l1,
        l2_stresses=l2,
        confirm_stresses=confirm,
        divergence_stress=div,
        missing_critical=missing_critical,
        stale_critical=stale_critical,
        feature_points=points,
    )
