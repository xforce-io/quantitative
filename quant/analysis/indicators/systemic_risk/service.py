"""High-level systemic risk analysis service."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd
import yaml

from quant.analysis.indicators.systemic_risk.data_fetcher import SystemicRiskDataFetcher
from quant.analysis.indicators.systemic_risk.panel import build_panel_from_frames
from quant.analysis.indicators.systemic_risk.state_machine import (
    StateMachineConfig,
    SystemicRiskStateMachine,
    evaluate_path,
)
from quant.analysis.indicators.systemic_risk.types import FeatureSnapshot, SystemicRiskState
from quant.core.logging_config import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_CONFIG = _PROJECT_ROOT / "config" / "systemic_risk.yaml"


def load_state_machine_config(path: Optional[Union[str, Path]] = None) -> StateMachineConfig:
    path = Path(path) if path else _DEFAULT_CONFIG
    if not path.exists():
        return StateMachineConfig()
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    sm = raw.get("state_machine") or {}
    return StateMachineConfig(
        l1_stress_threshold=float(sm.get("l1_stress_threshold", 0.58)),
        l1_min_features=int(sm.get("l1_min_features", 2)),
        l1_persist_days=int(sm.get("l1_persist_days", 2)),
        confirm_stress_threshold=float(sm.get("confirm_stress_threshold", 0.55)),
        confirm_min_features=int(sm.get("confirm_min_features", 1)),
        releasing_persist_days=int(sm.get("releasing_persist_days", 5)),
        divergence_threshold=float(sm.get("divergence_threshold", 0.55)),
        critical_l1=tuple(sm.get("critical_l1") or ("hy_oas",)),
        critical_funding_keys=tuple(
            sm.get("critical_funding_keys")
            or ("sofr_iorb_spread", "cp_tbill_spread", "effr_iorb_spread")
        ),
        critical_credit_keys=tuple(
            sm.get("critical_credit_keys") or ("hy_oas", "hy_oas_d20")
        ),
        soft_l1_threshold=float(sm.get("soft_l1_threshold", 0.50)),
        quiet_funding_min=int(sm.get("quiet_funding_min", 2)),
        funding_alone_threshold=float(sm.get("funding_alone_threshold", 0.68)),
    )


def load_window_config(path: Optional[Union[str, Path]] = None) -> dict:
    path = Path(path) if path else _DEFAULT_CONFIG
    if not path.exists():
        return {"percentile": 252, "zscore": 60, "change": 20, "velocity": 5}
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("windows") or {
        "percentile": 252,
        "zscore": 60,
        "change": 20,
        "velocity": 5,
    }


class SystemicRiskAnalyzer:
    """Fetch → panel → state machine for current or historical as_of."""

    def __init__(
        self,
        fred_api_key: Optional[str] = None,
        config_path: Optional[Union[str, Path]] = None,
        frames: Optional[Dict[str, pd.Series]] = None,
    ):
        self._fetcher = SystemicRiskDataFetcher(fred_api_key=fred_api_key)
        self._config_path = config_path
        self._sm_config = load_state_machine_config(config_path)
        self._windows = load_window_config(config_path)
        self._frames = frames  # optional preloaded

    def ensure_frames(
        self,
        lookback_days: int = 1200,
        start: Optional[str] = None,
        end: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, pd.Series]:
        if self._frames is not None and not force:
            return self._frames
        self._frames = self._fetcher.fetch_all(
            start=start, end=end, lookback_days=lookback_days
        )
        return self._frames

    def panel_at(
        self, as_of: Optional[Union[str, pd.Timestamp]] = None
    ) -> FeatureSnapshot:
        frames = self.ensure_frames()
        if as_of is None:
            # latest common-ish date from hy_oas or any series
            as_of = self._latest_as_of(frames)
        return build_panel_from_frames(
            frames,
            as_of=as_of,
            percentile_window=int(self._windows.get("percentile", 252)),
            zscore_window=int(self._windows.get("zscore", 60)),
            change_window=int(self._windows.get("change", 20)),
            divergence_threshold=float(self._sm_config.divergence_threshold),
            critical_l1=self._sm_config.critical_l1,
        )

    def analyze(
        self,
        as_of: Optional[Union[str, pd.Timestamp]] = None,
        warm_days: int = 30,
    ) -> SystemicRiskState:
        """Return state at as_of after warming the machine on prior days.

        Warm-up avoids cold-start (persist_days) bias on a single snapshot.
        """
        frames = self.ensure_frames()
        if as_of is None:
            as_of = self._latest_as_of(frames)
        as_of_ts = pd.Timestamp(as_of).normalize()

        # Build calendar from a liquid series
        cal = self._business_calendar(frames, end=as_of_ts)
        if not cal:
            snap = self.panel_at(as_of_ts)
            return SystemicRiskStateMachine(self._sm_config).step(snap)

        # Warm path: last warm_days including as_of
        use = cal[-max(warm_days, self._sm_config.l1_persist_days + 5) :]
        snaps = [self.panel_at(d) for d in use]
        states = evaluate_path(snaps, self._sm_config)
        return states[-1]

    def walk_forward(
        self,
        start: str,
        end: str,
        step: int = 1,
    ) -> List[SystemicRiskState]:
        """Daily walk-forward states over [start, end].

        Uses precomputed stress paths (one pass per series) instead of
        rebuilding full panels every day — required for multi-event eval.
        """
        from quant.analysis.indicators.systemic_risk.features import (
            compute_gold_fc_divergence,
            compute_stress_series,
            rolling_percentile,
        )
        from quant.analysis.indicators.systemic_risk.panel import FEATURE_SPEC
        from quant.analysis.indicators.systemic_risk.types import FeatureSnapshot

        frames = self.ensure_frames(start=start, end=end)
        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize()
        cal = self._business_calendar(frames, end=end_ts)
        cal = [d for d in cal if start_ts <= d <= end_ts]
        if step > 1:
            cal = cal[::step]
        if not cal:
            return []

        pct_w = int(self._windows.get("percentile", 126))
        short_w = int(self._windows.get("percentile_short", 60))
        chg_w = int(self._windows.get("change", 10))

        # Precompute multi-horizon stress series once
        stress_paths: Dict[str, pd.Series] = {}
        for name, spec in FEATURE_SPEC.items():
            s = frames.get(name)
            if s is None or s.empty:
                continue
            s = s.sort_index()
            stress_paths[name] = compute_stress_series(
                s,
                inverted=bool(spec.get("inverted")),
                percentile_window=pct_w,
                short_window=short_w,
                change_window=chg_w,
            )

        # hy_oas_d20 from changes (widening = stress)
        hy = frames.get("hy_oas")
        if hy is not None and len(hy.dropna()) > chg_w:
            chg = hy.sort_index().diff(chg_w).dropna()
            stress_paths["hy_oas_d20"] = compute_stress_series(
                chg,
                inverted=False,
                percentile_window=min(pct_w, max(len(chg), 40)),
                short_window=min(short_w, 40),
                change_window=max(5, chg_w // 2),
            )

        gold = frames.get("gold")
        gold_ret = None
        if gold is not None and len(gold.dropna()) > 21:
            g = gold.sort_index()
            gold_ret = g / g.shift(20) - 1.0

        snaps: List[FeatureSnapshot] = []
        for d in cal:
            l1: Dict[str, Optional[float]] = {}
            l2: Dict[str, Optional[float]] = {}
            confirm: Dict[str, Optional[float]] = {}
            for name, spec in FEATURE_SPEC.items():
                sp = stress_paths.get(name)
                val = None
                if sp is not None:
                    sub = sp.loc[:d].dropna()
                    if not sub.empty:
                        val = float(sub.iloc[-1])
                        if np.isnan(val):
                            val = None
                group = spec["group"]
                if group == "l1":
                    l1[name] = val
                elif group == "l2":
                    l2[name] = val
                elif group == "confirm":
                    confirm[name] = val

            # hy_oas_d20
            sp = stress_paths.get("hy_oas_d20")
            if sp is not None:
                sub = sp.loc[:d].dropna()
                l1["hy_oas_d20"] = float(sub.iloc[-1]) if not sub.empty else None
            else:
                l1["hy_oas_d20"] = None

            l1_vals = [v for v in l1.values() if v is not None]
            l1_agg = float(sum(l1_vals) / len(l1_vals)) if l1_vals else 0.0
            g_mom = None
            if gold_ret is not None:
                gsub = gold_ret.loc[:d].dropna()
                if not gsub.empty:
                    g_mom = float(gsub.iloc[-1])
            div = compute_gold_fc_divergence(
                g_mom, l1_agg, self._sm_config.divergence_threshold
            )

            missing = []
            for key in self._sm_config.critical_l1:
                if l1.get(key) is None and (
                    key not in frames or frames[key].loc[:d].dropna().empty
                ):
                    missing.append(key)

            snaps.append(
                FeatureSnapshot(
                    as_of=pd.Timestamp(d).strftime("%Y-%m-%d"),
                    l1_stresses=l1,
                    l2_stresses=l2,
                    confirm_stresses=confirm,
                    divergence_stress=div,
                    missing_critical=missing,
                    stale_critical=False,
                )
            )

        return evaluate_path(snaps, self._sm_config)

    @staticmethod
    def _latest_as_of(frames: Dict[str, pd.Series]) -> pd.Timestamp:
        ends = []
        for s in frames.values():
            if s is not None and not s.empty:
                ends.append(pd.Timestamp(s.index.max()).normalize())
        if not ends:
            return pd.Timestamp(datetime.now().date())
        return min(ends)  # conservative: avoid series that already updated alone

    @staticmethod
    def _business_calendar(
        frames: Dict[str, pd.Series], end: pd.Timestamp
    ) -> List[pd.Timestamp]:
        prefer = None
        # Prefer liquid long-history calendars (vix/gold) over short credit series
        for key in ("vix", "gold", "hy_oas", "sofr_iorb_spread"):
            s = frames.get(key)
            if s is not None and not s.empty:
                prefer = s
                break
        if prefer is None:
            for s in frames.values():
                if s is not None and not s.empty:
                    prefer = s
                    break
        if prefer is None or prefer.empty:
            return []
        idx = pd.DatetimeIndex(prefer.index).normalize().unique().sort_values()
        idx = idx[idx <= end]
        return list(idx)

    def analyze_dict(self, **kwargs) -> Dict[str, Any]:
        try:
            state = self.analyze(**kwargs)
            return state.to_dict()
        except Exception as e:
            logger.error(f"Systemic risk analyze failed: {e}")
            return {
                "state": "degraded",
                "as_of": datetime.now().strftime("%Y-%m-%d"),
                "confidence": 0.0,
                "days_in_state": 1,
                "l1_stress": 0.0,
                "confirm_stress": 0.0,
                "divergence_stress": 0.0,
                "drivers": [f"Analysis failed: {e}"],
                "feature_snapshot": {},
                "display_score": None,
                "data_quality": "degraded",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
            }
