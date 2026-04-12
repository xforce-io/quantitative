"""Gold & commodity scanning tab."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st


def _regime_badge(label: str, verdict: dict) -> None:
    """Render a regime badge for a named pool."""
    icon = verdict.get("regime_icon", "⚪")
    regime = verdict.get("regime", "unknown")
    action = verdict.get("action", "hold")
    reasoning = verdict.get("reasoning", "")
    updated = verdict.get("updated_at", "")

    action_colors = {"add": "#2ecc71", "reduce": "#e74c3c", "hold": "#f1c40f"}
    color = action_colors.get(action, "#95a5a6")

    st.markdown(
        f'<div style="padding:10px 14px;border-radius:8px;'
        f'background:linear-gradient(135deg,{color}22,{color}11);'
        f'border-left:4px solid {color};margin-bottom:8px;">'
        f'<strong style="color:{color};">{icon} {label}</strong> — '
        f'Regime: <strong>{regime}</strong> | Action: <strong>{action}</strong>'
        f'{"<br/><small>" + reasoning + "</small>" if reasoning else ""}'
        f'{"<br/><small style=color:#888>Updated: " + updated + "</small>" if updated else ""}'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_commodity_scan(verdict: dict) -> None:
    """Gold & commodity scanning tab."""
    st.subheader("🥇 Gold & Commodity Scan")

    # Show gold verdict badge
    _regime_badge("Gold (GLD / GC=F)", verdict)

    st.divider()

    st.info(
        "Commodity scanning coming soon — CommodityAnalyzer integration pending.\n\n"
        "Planned: Gold/Silver technicals, Copper-Gold ratio, Crude oil trend, "
        "commodity momentum screener with watchlist add support."
    )

    # Brief summary of current verdict
    action = verdict.get("action", "hold")
    regime = verdict.get("regime", "unknown")
    reasoning = verdict.get("reasoning", "No data available")

    col1, col2 = st.columns(2)
    col1.metric("Gold Regime", regime, help="Derived from USD liquidity confidence")
    col2.metric("Suggested Action", action.upper())

    st.caption(f"Reasoning: {reasoning}")
