#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Systemic risk event evaluation (Phase 0–3).

Usage:
  # Offline synthetic demo
  uv run python scripts/systemic_risk_event_eval.py --demo \\
    --out reports/systemic_risk_demo.md

  # Live FRED/Yahoo walk-forward on fixed events
  uv run python scripts/systemic_risk_event_eval.py --live \\
    --out reports/systemic_risk_eval.md

  # Single event
  uv run python scripts/systemic_risk_event_eval.py --live --event covid_2020
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant.analysis.indicators.systemic_risk.legacy_map import (
    confidence_to_pseudo_state,
    risk_score_to_pseudo_state,
)
from quant.analysis.indicators.systemic_risk.metrics import evaluate_state_path
from quant.analysis.indicators.systemic_risk.panel import build_panel_from_frames
from quant.analysis.indicators.systemic_risk.service import (
    SystemicRiskAnalyzer,
    load_state_machine_config,
)
from quant.analysis.indicators.systemic_risk.state_machine import (
    StateMachineConfig,
    SystemicRiskStateMachine,
)


def load_events(path: Path) -> List[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return list(data.get("events") or [])


def _demo_frames(n: int = 300, spike_start: int = 240) -> Dict[str, pd.Series]:
    idx = pd.date_range("2019-01-01", periods=n, freq="B")
    calm = np.linspace(0.01, 0.02, n)
    hy = np.linspace(3.0, 3.5, n)
    vix = np.linspace(14, 16, n)
    gold = np.linspace(1500, 1600, n)
    calm[spike_start:] = np.linspace(0.02, 0.25, n - spike_start)
    hy[spike_start:] = np.linspace(3.5, 8.0, n - spike_start)
    vix[spike_start + 5 :] = np.linspace(16, 45, n - spike_start - 5)
    gold[spike_start:] = np.linspace(1600, 1900, n - spike_start)
    return {
        "sofr_iorb_spread": pd.Series(calm, index=idx),
        "hy_oas": pd.Series(hy, index=idx),
        "cp_tbill_spread": pd.Series(calm * 2, index=idx),
        "nfcirisk": pd.Series(np.linspace(-0.3, 0.5, n), index=idx),
        "stlfsi4": pd.Series(np.linspace(-0.5, 1.0, n), index=idx),
        "net_liquidity": pd.Series(np.linspace(3.5e6, 2.8e6, n), index=idx),
        "vix": pd.Series(vix, index=idx),
        "move": pd.Series(vix * 4, index=idx),
        "gold": pd.Series(gold, index=idx),
        "copper_gold": pd.Series(np.linspace(0.0025, 0.0015, n), index=idx),
        "usdjpy": pd.Series(np.linspace(110, 105, n), index=idx),
        "dgs2": pd.Series(np.linspace(2.5, 1.5, n), index=idx),
        "real_yield": pd.Series(np.linspace(0.5, 1.5, n), index=idx),
    }


def run_demo(cfg: StateMachineConfig) -> str:
    frames = _demo_frames()
    idx = frames["hy_oas"].index
    days = idx[-80:]
    sm = SystemicRiskStateMachine(cfg)
    dates: List[str] = []
    states: List[str] = []
    legacy_scores: List[float] = []
    for d in days:
        panel = build_panel_from_frames(frames, as_of=d, percentile_window=60)
        st = sm.step(panel)
        dates.append(st.as_of)
        states.append(st.state)
        l1_vals = [v for v in panel.l1_stresses.values() if v is not None]
        legacy_scores.append(100.0 * (sum(l1_vals) / len(l1_vals) if l1_vals else 0.3))

    anchor = dates[min(50, len(dates) - 1)]
    m = evaluate_state_path(dates, states, anchor_date=anchor)
    legacy_states = [risk_score_to_pseudo_state(s) for s in legacy_scores]
    m_legacy = evaluate_state_path(dates, legacy_states, anchor_date=anchor)

    lines = [
        "# Systemic Risk Demo Eval (synthetic, offline)",
        "",
        f"Anchor (demo): `{anchor}`",
        "",
        "## systemic_v1",
        f"- first_building: {m.first_building}",
        f"- first_confirmed: {m.first_confirmed}",
        f"- lead_confirmed: {m.lead_confirmed}",
        f"- hit: {m.hit} miss: {m.miss} flicker: {m.flicker}",
        "",
        "## legacy_risk_score_map (synthetic mean L1)",
        f"- first_building: {m_legacy.first_building}",
        f"- first_confirmed: {m_legacy.first_confirmed}",
        f"- lead_confirmed: {m_legacy.lead_confirmed}",
        f"- hit: {m_legacy.hit} miss: {m_legacy.miss}",
        "",
    ]
    return "\n".join(lines)


def _proxy_legacy_from_panel_stress(l1_mean: float, confirm_mean: float) -> float:
    """Proxy legacy risk score 0–100 from panel stresses (not full MacroLiquidityAnalyzer)."""
    return float(np.clip(100.0 * (0.7 * l1_mean + 0.3 * confirm_mean), 0, 100))


def run_live(
    events: List[dict],
    cfg: StateMachineConfig,
    step: int = 1,
    event_filter: Optional[str] = None,
) -> str:
    if event_filter:
        events = [e for e in events if e.get("id") == event_filter]
        if not events:
            return f"# Error\n\nEvent not found: {event_filter}\n"

    # Global fetch covering all event windows + history buffer
    min_start = min(e["window"][0] for e in events)
    max_end = max(e["window"][1] for e in events)
    print(f"Fetching FRED/Yahoo data for {min_start} .. {max_end} ...")
    analyzer = SystemicRiskAnalyzer()
    frames = analyzer.ensure_frames(start=min_start, end=max_end)
    print(f"Loaded series: {sorted(frames.keys())}")

    lines = [
        "# Systemic Risk Live Event Evaluation",
        "",
        f"Generated with live FRED/Yahoo frames.",
        f"Series: `{', '.join(sorted(frames.keys()))}`",
        f"State machine: l1_threshold={cfg.l1_stress_threshold}, "
        f"persist={cfg.l1_persist_days}, confirm_threshold={cfg.confirm_stress_threshold}",
        "",
        "## Summary",
        "",
        "| event | anchor | v1_first_building | v1_first_confirmed | v1_lead_conf | v1_hit | "
        "legacy_first_conf | legacy_lead | legacy_hit |",
        "|-------|--------|-------------------|--------------------|--------------|--------|"
        "------------------|-------------|------------|",
    ]

    detail_sections: List[str] = []

    for ev in events:
        eid = ev["id"]
        anchor = ev["anchor_date"]
        w0, w1 = ev["window"]
        print(f"Evaluating {eid} [{w0} .. {w1}] anchor={anchor}")

        # Re-bind analyzer frames (already loaded)
        az = SystemicRiskAnalyzer(frames=frames)
        path = az.walk_forward(start=w0, end=w1, step=step)
        if not path:
            lines.append(
                f"| {eid} | {anchor} | — | — | — | MISS | — | — | MISS |"
            )
            detail_sections.append(f"### {eid}\n\nNo path data.\n")
            continue

        dates = [s.as_of for s in path]
        states = [s.state for s in path]
        m = evaluate_state_path(dates, states, anchor_date=anchor)

        # Proxy legacy from display-ish stresses along path
        legacy_states = []
        for s in path:
            # reconstruct approx from feature_snapshot
            snap = s.feature_snapshot or {}
            l1_keys = [
                k
                for k in snap
                if k
                not in (
                    "vix",
                    "move",
                    "gold_fc_divergence",
                )
            ]
            l1_vals = [snap[k] for k in l1_keys if isinstance(snap.get(k), (int, float))]
            conf_vals = [
                snap[k]
                for k in ("vix", "move")
                if isinstance(snap.get(k), (int, float))
            ]
            l1_m = float(np.mean(l1_vals)) if l1_vals else 0.3
            c_m = float(np.mean(conf_vals)) if conf_vals else 0.3
            score = _proxy_legacy_from_panel_stress(l1_m, c_m)
            legacy_states.append(risk_score_to_pseudo_state(score))

        m_leg = evaluate_state_path(dates, legacy_states, anchor_date=anchor)

        lines.append(
            f"| {eid} | {anchor} | {m.first_building} | {m.first_confirmed} | "
            f"{m.lead_confirmed} | {m.hit} | {m_leg.first_confirmed} | "
            f"{m_leg.lead_confirmed} | {m_leg.hit} |"
        )

        # Detail: last drivers at first confirmed or end
        target = next((s for s in path if s.state == "confirmed"), path[-1])
        detail_sections.append(
            f"### {eid} — {ev.get('name', '')}\n\n"
            f"- window: {w0} → {w1}\n"
            f"- anchor: {anchor}\n"
            f"- v1: building={m.first_building}, confirmed={m.first_confirmed}, "
            f"lead_confirmed={m.lead_confirmed}, hit={m.hit}, flicker={m.flicker}\n"
            f"- proxy_legacy: confirmed={m_leg.first_confirmed}, "
            f"lead={m_leg.lead_confirmed}, hit={m_leg.hit}\n"
            f"- sample state @ {target.as_of}: **{target.state}** "
            f"(l1={target.l1_stress:.2f}, confirm={target.confirm_stress:.2f}, "
            f"div={target.divergence_stress:.2f})\n"
            f"- drivers: {target.drivers}\n"
        )

    lines.append("")
    lines.append("## Event details")
    lines.append("")
    lines.extend(detail_sections)
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- `legacy_*` columns use a **stress-proxy** map (not full MacroLiquidityAnalyzer "
        "replay). Treat as rough baseline until snapshot scoring is extracted (plan 0.5)."
    )
    lines.append(
        "- `lead_confirmed` = first_confirmed_index − anchor_index on the event calendar "
        "(negative = earlier than anchor)."
    )
    lines.append(
        "- Alice reference event `alice_2025_01` uses anchor 2025-01-23."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Systemic risk event evaluation")
    parser.add_argument(
        "--events",
        default=str(PROJECT_ROOT / "config" / "systemic_risk_events.yaml"),
    )
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "systemic_risk.yaml"),
    )
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "reports" / "systemic_risk_eval.md"),
    )
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--event", default=None, help="Filter single event id")
    parser.add_argument(
        "--step",
        type=int,
        default=1,
        help="Walk-forward step in trading days (default 1)",
    )
    args = parser.parse_args()

    cfg = load_state_machine_config(Path(args.config))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.demo:
        report = run_demo(cfg)
    elif args.live:
        events = load_events(Path(args.events))
        report = run_live(events, cfg, step=args.step, event_filter=args.event)
    else:
        events = load_events(Path(args.events))
        report = (
            "# Systemic Risk Event Catalog\n\n"
            f"Events: {len(events)}\n\n"
            "Use `--demo` (offline) or `--live` (FRED/Yahoo).\n"
        )

    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
