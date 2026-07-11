"""No-lookahead guarantees for systemic risk panel."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.analysis.indicators.systemic_risk.panel import build_panel_from_frames


def _mk_frame(n=150, start="2020-01-01"):
    idx = pd.date_range(start, periods=n, freq="B")
    # Flat calm baseline (avoids trending percentile artifacts)
    data = {
        "sofr_iorb_spread": pd.Series(np.full(n, 0.02), index=idx),
        "hy_oas": pd.Series(np.full(n, 3.5), index=idx),
        "hy_oas_d20_src": pd.Series(np.full(n, 3.5), index=idx),
        "cp_tbill_spread": pd.Series(np.full(n, 0.15), index=idx),
        "nfcirisk": pd.Series(np.full(n, -0.2), index=idx),
        "stlfsi4": pd.Series(np.full(n, -0.4), index=idx),
        "net_liquidity": pd.Series(np.full(n, 3.0e6), index=idx),
        "vix": pd.Series(np.full(n, 15.0), index=idx),
        "move": pd.Series(np.full(n, 80.0), index=idx),
        "gold": pd.Series(np.full(n, 1800.0), index=idx),
        "copper_gold": pd.Series(np.full(n, 0.002), index=idx),
        "usdjpy": pd.Series(np.full(n, 110.0), index=idx),
        "dgs2": pd.Series(np.full(n, 2.0), index=idx),
        "real_yield": pd.Series(np.full(n, 0.5), index=idx),
    }
    return idx, data


class TestNoLookahead:
    def test_future_spike_does_not_affect_as_of(self):
        idx, data = _mk_frame(150)
        # Spike only on last 5 days
        data["hy_oas"].iloc[-5:] = 12.0
        data["sofr_iorb_spread"].iloc[-5:] = 0.50

        as_of = idx[-20]  # well before the spike
        panel_cut = build_panel_from_frames(data, as_of=as_of, percentile_window=60)
        truncated = {k: v.loc[:as_of] for k, v in data.items()}
        panel_trunc = build_panel_from_frames(
            truncated, as_of=as_of, percentile_window=60
        )

        assert panel_cut.as_of == panel_trunc.as_of
        for name in panel_cut.l1_stresses:
            a = panel_cut.l1_stresses.get(name)
            b = panel_trunc.l1_stresses.get(name)
            if a is None and b is None:
                continue
            assert a is not None and b is not None
            assert abs(a - b) < 1e-9

        # Flat series → median-ish stress; future spike must not lift hy_oas
        assert panel_cut.l1_stresses.get("hy_oas", 1.0) < 0.7

    def test_as_of_after_spike_sees_stress(self):
        idx, data = _mk_frame(150)
        data["hy_oas"].iloc[-5:] = 12.0
        as_of = idx[-1]
        panel = build_panel_from_frames(data, as_of=as_of, percentile_window=60)
        assert panel.l1_stresses.get("hy_oas", 0) > 0.5
