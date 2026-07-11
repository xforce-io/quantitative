"""Service-level tests with preloaded frames (no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.analysis.indicators.systemic_risk.service import SystemicRiskAnalyzer


def _stress_frames(n=200, spike_at=160):
    idx = pd.date_range("2019-01-01", periods=n, freq="B")
    sofr = np.full(n, 0.02)
    hy = np.full(n, 3.5)
    vix = np.full(n, 15.0)
    gold = np.linspace(1500, 1550, n)
    sofr[spike_at:] = np.linspace(0.02, 0.30, n - spike_at)
    hy[spike_at:] = np.linspace(3.5, 9.0, n - spike_at)
    vix[spike_at + 3 :] = np.linspace(15, 40, n - spike_at - 3)
    gold[spike_at:] = np.linspace(1550, 1900, n - spike_at)
    return {
        "sofr_iorb_spread": pd.Series(sofr, index=idx),
        "hy_oas": pd.Series(hy, index=idx),
        "cp_tbill_spread": pd.Series(sofr * 1.5, index=idx),
        "nfcirisk": pd.Series(np.linspace(-0.3, 0.8, n), index=idx),
        "stlfsi4": pd.Series(np.linspace(-0.5, 1.2, n), index=idx),
        "net_liquidity": pd.Series(np.linspace(3.5e6, 2.5e6, n), index=idx),
        "vix": pd.Series(vix, index=idx),
        "move": pd.Series(vix * 5, index=idx),
        "gold": pd.Series(gold, index=idx),
        "copper_gold": pd.Series(np.linspace(0.0025, 0.0015, n), index=idx),
        "usdjpy": pd.Series(np.linspace(110, 105, n), index=idx),
        "dgs2": pd.Series(np.linspace(2.5, 1.8, n), index=idx),
        "real_yield": pd.Series(np.linspace(0.5, 1.2, n), index=idx),
    }, idx


class TestSystemicRiskAnalyzer:
    def test_analyze_at_stress_is_not_normal(self):
        frames, idx = _stress_frames()
        az = SystemicRiskAnalyzer(frames=frames)
        st = az.analyze(as_of=idx[-1], warm_days=40)
        assert st.state in ("building", "confirmed", "releasing")
        assert st.data_quality in ("ok", "partial")

    def test_walk_forward_hits_confirmed(self):
        frames, idx = _stress_frames()
        az = SystemicRiskAnalyzer(frames=frames)
        start = idx[150].strftime("%Y-%m-%d")
        end = idx[-1].strftime("%Y-%m-%d")
        path = az.walk_forward(start=start, end=end)
        states = [s.state for s in path]
        assert "confirmed" in states or "building" in states

    def test_analyze_dict_degraded_on_empty(self):
        az = SystemicRiskAnalyzer(frames={})
        d = az.analyze_dict()
        assert d["state"] == "degraded"
        assert d["data_quality"] == "degraded"
