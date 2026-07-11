"""Non-compensatory systemic risk state machine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from quant.analysis.indicators.systemic_risk.features import aggregate_mean_stress
from quant.analysis.indicators.systemic_risk.types import FeatureSnapshot, SystemicRiskState


@dataclass
class StateMachineConfig:
    l1_stress_threshold: float = 0.58
    l1_min_features: int = 2
    l1_persist_days: int = 2
    confirm_stress_threshold: float = 0.65
    confirm_min_features: int = 1
    releasing_persist_days: int = 5
    divergence_threshold: float = 0.55
    critical_l1: Tuple[str, ...] = ("hy_oas",)
    # Critical funding + credit pair (non-compensatory veto)
    critical_funding_keys: Tuple[str, ...] = (
        "sofr_iorb_spread",
        "cp_tbill_spread",
        "effr_iorb_spread",
    )
    critical_credit_keys: Tuple[str, ...] = ("hy_oas", "hy_oas_d20")
    # Quiet tightening: funding pressure without credit blowout (Alice 2026-01 style)
    soft_l1_threshold: float = 0.50
    quiet_funding_min: int = 2
    funding_alone_threshold: float = 0.68


@dataclass
class _Internal:
    state: str = "normal"
    days_in_state: int = 0
    l1_hot_streak: int = 0
    calm_streak: int = 0


class SystemicRiskStateMachine:
    """Walk day-by-day FeatureSnapshots into SystemicRiskState."""

    def __init__(self, config: Optional[StateMachineConfig] = None):
        self.config = config or StateMachineConfig()
        self._int = _Internal()

    def reset(self) -> None:
        self._int = _Internal()

    def step(self, snapshot: FeatureSnapshot) -> SystemicRiskState:
        cfg = self.config

        # --- Degraded path ---
        if snapshot.missing_critical or snapshot.stale_critical:
            return self._emit(
                state="degraded",
                snapshot=snapshot,
                drivers=self._degraded_drivers(snapshot),
                data_quality="degraded",
            )

        l1_stress = aggregate_mean_stress(snapshot.l1_stresses)
        confirm_stress = aggregate_mean_stress(snapshot.confirm_stresses)
        div = float(snapshot.divergence_stress or 0.0)

        hot_count, hot_names = self._count_hot(
            snapshot.l1_stresses, cfg.l1_stress_threshold
        )
        # Divergence boost: counts as one extra L1 vote and lowers min features
        effective_min = cfg.l1_min_features
        if div >= cfg.divergence_threshold:
            hot_count += 1
            hot_names = list(hot_names) + ["gold_fc_divergence"]
            effective_min = max(1, cfg.l1_min_features - 1)

        critical_pair = self._critical_subgraph_hot(snapshot.l1_stresses, cfg)
        quiet_funding = self._quiet_funding_tightening(snapshot.l1_stresses, cfg)
        funding_alone = self._funding_alone_hot(snapshot.l1_stresses, cfg)
        if quiet_funding:
            hot_names = list(hot_names) + ["quiet_funding_tightening"]
        if funding_alone:
            hot_names = list(hot_names) + ["funding_alone"]

        l1_signal = (
            hot_count >= effective_min
            or critical_pair
            or quiet_funding
            or funding_alone
        )

        if l1_signal:
            self._int.l1_hot_streak += 1
            self._int.calm_streak = 0
        else:
            self._int.l1_hot_streak = 0
            self._int.calm_streak += 1

        # persist_days<=1: first hot day is enough; else require streak
        if cfg.l1_persist_days <= 1:
            l1_persistent = l1_signal
        else:
            l1_persistent = self._int.l1_hot_streak >= cfg.l1_persist_days

        confirm_count, confirm_names = self._count_hot(
            snapshot.confirm_stresses, cfg.confirm_stress_threshold
        )
        confirm_ok = confirm_count >= cfg.confirm_min_features

        # Hard evidence for confirmed — scarce on purpose (anti cry-wolf).
        # building  = L1 / quiet-funding / credit pressure (watch band)
        # confirmed = L1 persistent AND vol confirmation (VIX/MOVE)
        # Divergence alone does not confirm (too sticky when gold trends up).
        can_confirm = bool(l1_persistent and confirm_ok)

        prev = self._int.state
        new_state = self._transition(
            prev=prev,
            l1_persistent=l1_persistent,
            l1_signal=l1_signal,
            can_confirm=can_confirm,
            calm=(not l1_signal and not confirm_ok),
        )

        if new_state == prev:
            self._int.days_in_state += 1
        else:
            self._int.state = new_state
            self._int.days_in_state = 1

        drivers = self._build_drivers(
            snapshot=snapshot,
            hot_names=hot_names,
            confirm_names=confirm_names,
            critical_pair=critical_pair,
            quiet_funding=quiet_funding,
            funding_alone=funding_alone,
            div=div,
            state=new_state,
        )
        display = self._display_score(l1_stress, confirm_stress, div, snapshot)

        return self._emit(
            state=new_state,
            snapshot=snapshot,
            drivers=drivers,
            l1_stress=l1_stress,
            confirm_stress=confirm_stress,
            divergence_stress=div,
            display_score=display,
            data_quality=snapshot.data_quality,
            confidence=self._confidence(new_state, l1_stress, confirm_stress, div),
        )

    def _transition(
        self,
        prev: str,
        l1_persistent: bool,
        l1_signal: bool,
        can_confirm: bool,
        calm: bool,
    ) -> str:
        """State transitions with scarce confirmed (anti cry-wolf).

        building  = L1 / quiet-funding pressure (can be frequent)
        confirmed = L1 persistent + hard evidence (vol/credit/divergence)
        """
        cfg = self.config

        if prev == "degraded":
            prev = "normal"

        if prev == "normal":
            if l1_persistent:
                if can_confirm:
                    return "confirmed"
                return "building"
            return "normal"

        if prev == "building":
            if can_confirm:
                return "confirmed"
            if not l1_signal and calm:
                if self._int.calm_streak >= 2:
                    return "normal"
                return "building"
            if l1_signal or l1_persistent:
                return "building"
            return "normal"

        if prev == "confirmed":
            if can_confirm:
                return "confirmed"
            # Lose hard evidence but L1 still hot → demote to building (not sticky)
            if l1_signal or l1_persistent:
                return "building"
            return "releasing"

        if prev == "releasing":
            if can_confirm:
                return "confirmed"
            if l1_persistent:
                return "building"
            if self._int.calm_streak >= cfg.releasing_persist_days:
                return "normal"
            if calm or not l1_signal:
                return "releasing"
            return "releasing"

        return "normal"

    @staticmethod
    def _count_hot(
        stresses: Dict[str, Optional[float]], threshold: float
    ) -> Tuple[int, List[str]]:
        names = []
        for k, v in stresses.items():
            if v is not None and v >= threshold:
                names.append(k)
        return len(names), names

    @staticmethod
    def _critical_subgraph_hot(
        l1: Dict[str, Optional[float]], cfg: StateMachineConfig
    ) -> bool:
        """Funding stress AND credit stress both hot → non-compensatory building."""
        def any_hot(keys: Sequence[str], thr: Optional[float] = None) -> bool:
            t = cfg.l1_stress_threshold if thr is None else thr
            for k in keys:
                v = l1.get(k)
                if v is not None and v >= t:
                    return True
            return False

        return any_hot(cfg.critical_funding_keys) and any_hot(cfg.critical_credit_keys)

    @staticmethod
    def _quiet_funding_tightening(
        l1: Dict[str, Optional[float]], cfg: StateMachineConfig
    ) -> bool:
        """Multiple funding proxies soft-hot without needing credit blowout.

        Catches Alice-style 2026-01 quiet USD funding pressure before VIX/HY explode.
        """
        soft = []
        for k in cfg.critical_funding_keys:
            v = l1.get(k)
            if v is not None and v >= cfg.soft_l1_threshold:
                soft.append(k)
        return len(soft) >= cfg.quiet_funding_min

    @staticmethod
    def _funding_alone_hot(
        l1: Dict[str, Optional[float]], cfg: StateMachineConfig
    ) -> bool:
        """Single funding leg extremely stressed is enough for L1 signal."""
        for k in cfg.critical_funding_keys:
            v = l1.get(k)
            if v is not None and v >= cfg.funding_alone_threshold:
                return True
        return False

    def _display_score(
        self,
        l1: float,
        confirm: float,
        div: float,
        snapshot: FeatureSnapshot,
    ) -> float:
        l2 = aggregate_mean_stress(snapshot.l2_stresses)
        score = 100.0 * (0.50 * l1 + 0.20 * l2 + 0.15 * confirm + 0.15 * div)
        return round(float(min(100.0, max(0.0, score))), 1)

    def _confidence(
        self, state: str, l1: float, confirm: float, div: float
    ) -> float:
        if state == "degraded":
            return 0.0
        if state == "confirmed":
            return round(min(1.0, 0.5 + 0.3 * l1 + 0.2 * confirm), 3)
        if state == "building":
            return round(min(1.0, 0.35 + 0.4 * l1 + 0.2 * div), 3)
        if state == "releasing":
            return round(min(1.0, 0.3 + 0.2 * (1 - l1)), 3)
        return round(min(1.0, 0.2 + 0.3 * (1 - l1)), 3)

    def _build_drivers(
        self,
        snapshot: FeatureSnapshot,
        hot_names: List[str],
        confirm_names: List[str],
        critical_pair: bool,
        quiet_funding: bool,
        funding_alone: bool,
        div: float,
        state: str,
    ) -> List[str]:
        drivers: List[str] = []
        if state == "degraded":
            return self._degraded_drivers(snapshot)
        if critical_pair:
            drivers.append("Critical subgraph: funding + credit both stressed")
        if quiet_funding:
            drivers.append("Quiet funding tightening (multi-leg soft stress)")
        if funding_alone:
            drivers.append("Elevated single-leg USD funding stress")
        if div >= self.config.divergence_threshold:
            drivers.append(
                f"Gold vs financial-conditions divergence (stress={div:.2f})"
            )
        for n in hot_names[:3]:
            v = snapshot.l1_stresses.get(n)
            if v is not None:
                drivers.append(f"L1 {n} stress={v:.2f}")
            elif n == "gold_fc_divergence":
                continue
        for n in confirm_names[:2]:
            v = snapshot.confirm_stresses.get(n)
            if v is not None:
                drivers.append(f"Confirm {n} stress={v:.2f}")
        if state == "normal" and not drivers:
            drivers.append("No systemic stress detected")
        if state == "releasing":
            drivers.append("Stress fading; cooling period active")
        # de-dupe preserve order
        seen = set()
        out = []
        for d in drivers:
            if d not in seen:
                seen.add(d)
                out.append(d)
        return out[:5]

    @staticmethod
    def _degraded_drivers(snapshot: FeatureSnapshot) -> List[str]:
        drivers = []
        if snapshot.missing_critical:
            drivers.append(
                "Missing critical L1: " + ", ".join(snapshot.missing_critical)
            )
        if snapshot.stale_critical:
            drivers.append("Critical L1 data stale")
        return drivers or ["Data quality degraded"]

    def _emit(
        self,
        state: str,
        snapshot: FeatureSnapshot,
        drivers: List[str],
        l1_stress: float = 0.0,
        confirm_stress: float = 0.0,
        divergence_stress: float = 0.0,
        display_score: Optional[float] = None,
        data_quality: str = "ok",
        confidence: float = 0.0,
    ) -> SystemicRiskState:
        if state == "degraded":
            self._int.state = "degraded"
            # do not advance hot streaks meaningfully
        feat_snap = {
            k: float(v)
            for k, v in {**snapshot.l1_stresses, **snapshot.confirm_stresses}.items()
            if v is not None
        }
        if snapshot.divergence_stress:
            feat_snap["gold_fc_divergence"] = float(snapshot.divergence_stress)

        return SystemicRiskState(
            state=state,
            as_of=snapshot.as_of,
            confidence=confidence,
            days_in_state=self._int.days_in_state if state != "degraded" else 1,
            l1_stress=round(l1_stress, 4),
            confirm_stress=round(confirm_stress, 4),
            divergence_stress=round(divergence_stress, 4),
            drivers=drivers,
            feature_snapshot=feat_snap,
            display_score=display_score,
            data_quality=data_quality,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )


def evaluate_path(
    snapshots: List[FeatureSnapshot],
    config: Optional[StateMachineConfig] = None,
) -> List[SystemicRiskState]:
    """Evaluate an ordered list of daily snapshots."""
    sm = SystemicRiskStateMachine(config)
    return [sm.step(s) for s in snapshots]
