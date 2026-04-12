"""🔍 Scanner — market opportunity discovery by asset pool."""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
from web.ui_theme import apply_custom_css
from web.data_service_verdict import get_regime
from web.scanner.ashare_scan import render_ashare_scan
from web.scanner.us_value_scan import render_us_value_scan
from web.scanner.commodity_scan import render_commodity_scan

apply_custom_css()
st.title("🔍 Scanner")
st.caption("Find opportunities across asset pools")

tab_ashare, tab_us, tab_commodity = st.tabs([
    "🇨🇳 A-Share Scan",
    "🇺🇸 US Value Scan",
    "🥇 Gold & Commodity Scan",
])

with tab_ashare:
    render_ashare_scan(get_regime("a_shares"))

with tab_us:
    render_us_value_scan(get_regime("us_stocks"))

with tab_commodity:
    render_commodity_scan(get_regime("gold"))
