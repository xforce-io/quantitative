"""Gold & commodity scanning tab."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.data_service_verdict import get_regime


def render_commodity_scan(verdict: dict) -> None:
    """Gold & commodity scanning tab."""
    st.subheader("🥇 Gold & Commodity Scan")

    # Gold regime banner
    regime = verdict.get("regime", "unknown")
    confidence = verdict.get("confidence", 0)
    icon = "🟢" if regime == "risk-on" else "🔴" if regime == "risk-off" else "🟡"
    st.info(f"{icon} 黄金情景: **{regime}** (置信度: {confidence:.0%})")

    # Commodities regime banner
    commodity_regime = get_regime("commodities")
    c_regime = commodity_regime.get("regime", "unknown")
    c_confidence = commodity_regime.get("confidence", 0)
    c_icon = "🟢" if c_regime == "risk-on" else "🔴" if c_regime == "risk-off" else "🟡"
    st.info(f"{c_icon} 大宗商品情景: **{c_regime}** (置信度: {c_confidence:.0%})")

    st.divider()

    st.info(
        "Commodity scanning coming soon — CommodityAnalyzer integration pending.\n\n"
        "Planned: Gold/Silver technicals, Copper-Gold ratio, Crude oil trend, "
        "commodity momentum screener with watchlist add support."
    )
