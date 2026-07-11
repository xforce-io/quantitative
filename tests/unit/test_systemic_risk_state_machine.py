"""Spec scenarios S1–S6 for systemic risk state machine (TDD)."""

from __future__ import annotations

from quant.analysis.indicators.systemic_risk.state_machine import (
    StateMachineConfig,
    SystemicRiskStateMachine,
)
from quant.analysis.indicators.systemic_risk.types import FeatureSnapshot


def _snap(
    *,
    as_of: str,
    l1: dict[str, float | None],
    confirm: dict[str, float | None] | None = None,
    divergence: float = 0.0,
    l2: dict[str, float | None] | None = None,
    missing_critical: list[str] | None = None,
    stale_critical: bool = False,
) -> FeatureSnapshot:
    return FeatureSnapshot(
        as_of=as_of,
        l1_stresses=l1,
        confirm_stresses=confirm or {},
        l2_stresses=l2 or {},
        divergence_stress=divergence,
        missing_critical=missing_critical or [],
        stale_critical=stale_critical,
    )


def _cfg(**kwargs) -> StateMachineConfig:
    base = dict(
        l1_stress_threshold=0.65,
        l1_min_features=2,
        l1_persist_days=3,
        confirm_stress_threshold=0.60,
        confirm_min_features=1,
        releasing_persist_days=5,
        divergence_threshold=0.55,
        critical_l1=("hy_oas",),
    )
    base.update(kwargs)
    return StateMachineConfig(**base)


class TestS1GoldUpFinancialTight:
    """S1: gold up + L1 tight → at least building, never forced normal by gold strength."""

    def test_enters_building_with_divergence_boost(self):
        sm = SystemicRiskStateMachine(_cfg(l1_persist_days=1, l1_min_features=2))
        # Only one raw L1 above threshold, but divergence boost should help
        snap = _snap(
            as_of="2025-01-23",
            l1={
                "sofr_iorb_spread": 0.70,
                "hy_oas": 0.50,  # below threshold alone
                "cp_tbill_spread": 0.40,
            },
            confirm={"vix": 0.20},
            divergence=0.80,
        )
        # Divergence boosts L1 signal → building; no vol → not confirmed
        state = sm.step(snap)
        assert state.state == "building"
        assert state.state != "normal"

    def test_critical_subgraph_forces_building(self):
        sm = SystemicRiskStateMachine(_cfg(l1_persist_days=1))
        snap = _snap(
            as_of="2025-01-20",
            l1={
                "sofr_iorb_spread": 0.80,
                "hy_oas": 0.75,  # credit widening proxy via level stress
                "hy_oas_d20": 0.80,
                "cp_tbill_spread": 0.20,
            },
            confirm={"vix": 0.25},
            divergence=0.0,
        )
        state = sm.step(snap)
        # Without vol/divergence, funding+credit is building only (anti cry-wolf)
        assert state.state == "building"


class TestS2VixSpikeOnly:
    """S2: VIX blip alone must not confirm."""

    def test_vix_only_not_confirmed(self):
        sm = SystemicRiskStateMachine(_cfg(l1_persist_days=1))
        snap = _snap(
            as_of="2024-06-01",
            l1={
                "sofr_iorb_spread": 0.20,
                "hy_oas": 0.25,
                "cp_tbill_spread": 0.15,
            },
            confirm={"vix": 0.95, "move": 0.20},
            divergence=0.0,
        )
        state = sm.step(snap)
        assert state.state != "confirmed"
        assert state.state in ("normal", "building", "releasing")


class TestS3LeadThenConfirm:
    """S3: persistent L1 then confirmation → confirmed."""

    def test_building_then_confirmed(self):
        sm = SystemicRiskStateMachine(_cfg(l1_persist_days=3, confirm_min_features=1))
        # Funding-heavy L1 without credit pair — stays building until vol confirms
        l1_tight = {
            "sofr_iorb_spread": 0.80,
            "effr_iorb_spread": 0.75,
            "cp_tbill_spread": 0.70,
            "hy_oas": 0.30,
            "hy_oas_d20": 0.25,
        }
        # Days 1-2: building path
        for i, d in enumerate(["2020-02-20", "2020-02-21", "2020-02-24"]):
            st = sm.step(_snap(as_of=d, l1=l1_tight, confirm={"vix": 0.30}))
            if i < 2:
                assert st.state in ("building", "normal")  # may still accumulate
        # Day 3+: L1 persisted, still no hard evidence → building
        st = sm.step(_snap(as_of="2020-02-25", l1=l1_tight, confirm={"vix": 0.30}))
        assert st.state == "building"
        # Confirmation layer fires
        st = sm.step(
            _snap(
                as_of="2020-02-26",
                l1=l1_tight,
                confirm={"vix": 0.85, "move": 0.70},
            )
        )
        assert st.state == "confirmed"


class TestS4Release:
    """S4: stress fade → releasing → normal."""

    def test_release_path(self):
        sm = SystemicRiskStateMachine(
            _cfg(l1_persist_days=1, releasing_persist_days=3, confirm_min_features=1)
        )
        tight = {
            "sofr_iorb_spread": 0.85,
            "hy_oas": 0.80,
            "hy_oas_d20": 0.85,
        }
        calm = {
            "sofr_iorb_spread": 0.20,
            "hy_oas": 0.20,
            "hy_oas_d20": 0.15,
        }
        sm.step(_snap(as_of="2020-03-10", l1=tight, confirm={"vix": 0.90}))
        st = sm.step(_snap(as_of="2020-03-11", l1=tight, confirm={"vix": 0.90}))
        assert st.state == "confirmed"

        for d in ["2020-03-12", "2020-03-13", "2020-03-16"]:
            st = sm.step(_snap(as_of=d, l1=calm, confirm={"vix": 0.25}))
        assert st.state in ("releasing", "normal")
        # More calm days complete release
        for d in ["2020-03-17", "2020-03-18", "2020-03-19"]:
            st = sm.step(_snap(as_of=d, l1=calm, confirm={"vix": 0.20}))
        assert st.state == "normal"


class TestS5MissingCritical:
    """S5: missing critical L1 → degraded."""

    def test_degraded_on_missing_critical(self):
        sm = SystemicRiskStateMachine(_cfg())
        snap = _snap(
            as_of="2024-01-01",
            l1={"sofr_iorb_spread": 0.3, "hy_oas": None},
            missing_critical=["hy_oas"],
        )
        st = sm.step(snap)
        assert st.state == "degraded"
        assert st.data_quality == "degraded"

    def test_degraded_on_stale(self):
        sm = SystemicRiskStateMachine(_cfg())
        snap = _snap(
            as_of="2024-01-01",
            l1={"sofr_iorb_spread": 0.3, "hy_oas": 0.3},
            stale_critical=True,
        )
        st = sm.step(snap)
        assert st.state == "degraded"


class TestS6NonCompensatory:
    """S6: one critical stress cluster cannot be averaged away by calm others."""

    def test_not_normal_when_critical_pair_hot(self):
        sm = SystemicRiskStateMachine(_cfg(l1_persist_days=1))
        snap = _snap(
            as_of="2023-03-10",
            l1={
                "sofr_iorb_spread": 0.90,
                "hy_oas": 0.88,
                "hy_oas_d20": 0.90,
                "cp_tbill_spread": 0.10,
                "nfcirisk": 0.10,
                "stlfsi4": 0.10,
            },
            confirm={},
            divergence=0.0,
        )
        st = sm.step(snap)
        assert st.state == "building"
        assert st.state != "normal"


class TestDisplayScoreNotDriving:
    def test_state_enum_is_primary(self):
        sm = SystemicRiskStateMachine(_cfg(l1_persist_days=1))
        st = sm.step(
            _snap(
                as_of="2020-01-01",
                l1={"sofr_iorb_spread": 0.2, "hy_oas": 0.2},
            )
        )
        assert st.state == "normal"
        assert st.display_score is not None
        assert 0.0 <= st.display_score <= 100.0


class TestQuietFundingTightening:
    """Alice 2026-01 style: multi-leg funding soft-hot without credit blowout."""

    def test_quiet_funding_enters_building_not_confirmed(self):
        sm = SystemicRiskStateMachine(_cfg(l1_persist_days=1, quiet_funding_min=2))
        snap = _snap(
            as_of="2026-01-23",
            l1={
                "sofr_iorb_spread": 0.55,
                "effr_iorb_spread": 0.62,
                "cp_tbill_spread": 0.52,
                "hy_oas": 0.20,
                "hy_oas_d20": 0.15,
                "nfcirisk": 0.25,
            },
            confirm={"vix": 0.35, "move": 0.20},
        )
        # Several days of quiet funding alone must stay building (anti cry-wolf)
        for i in range(5):
            st = sm.step(snap)
        assert st.state == "building"
        assert st.state != "confirmed"
        assert any("Quiet funding" in d or "funding" in d.lower() for d in st.drivers)

    def test_funding_alone_extreme_is_building_only(self):
        sm = SystemicRiskStateMachine(
            _cfg(l1_persist_days=1, funding_alone_threshold=0.68)
        )
        snap = _snap(
            as_of="2026-01-23",
            l1={
                "sofr_iorb_spread": 0.20,
                "effr_iorb_spread": 0.72,
                "cp_tbill_spread": 0.20,
                "hy_oas": 0.15,
            },
            confirm={"vix": 0.20, "move": 0.15},
        )
        st = sm.step(snap)
        assert st.state == "building"

    def test_quiet_funding_plus_vix_can_confirm(self):
        sm = SystemicRiskStateMachine(_cfg(l1_persist_days=1, quiet_funding_min=2))
        base_l1 = {
            "sofr_iorb_spread": 0.55,
            "effr_iorb_spread": 0.62,
            "cp_tbill_spread": 0.52,
            "hy_oas": 0.20,
        }
        sm.step(_snap(as_of="2026-01-20", l1=base_l1, confirm={"vix": 0.30}))
        st = sm.step(
            _snap(
                as_of="2026-01-21",
                l1=base_l1,
                confirm={"vix": 0.80, "move": 0.40},
            )
        )
        assert st.state == "confirmed"
