"""
Skills Package - Agent-facing capability layer (Facade)

This package provides a unified, side-effect-free API surface for all
quantitative analysis capabilities.  Every public function:

  1. Returns structured data ONLY (dict / list / DataFrame / Pydantic model).
  2. Produces NO stdout output (no print, no rich console, no progress bars).
  3. Has a clear, LLM-friendly docstring suitable for tool-call descriptions.

Consumers:
  - TUI layer        (tui/)          → formats results for the terminal
  - Web layer        (web/)          → renders results in Streamlit / FastAPI
  - Agent toolkits   (web/skillkits) → exposes results to LLM agents
  - External scripts (bin/)          → quick-access wrappers
"""

from quant.skills.etf_screening import (
    screen_etfs,
    screen_symbols,
    analyze_etf,
    get_screening_config,
    list_etf_pools,
)
from quant.skills.stock_analysis import (
    fetch_full_analysis,
    get_stock_money_flow,
    get_stock_technical_data,
    get_stock_valuation,
    get_trend_strength,
    resolve_symbol,
)

__all__ = [
    # ETF screening
    "screen_etfs",
    "screen_symbols",
    "analyze_etf",
    "get_screening_config",
    "list_etf_pools",
    # Stock analysis
    "fetch_full_analysis",
    "get_stock_money_flow",
    "get_stock_technical_data",
    "get_stock_valuation",
    "get_trend_strength",
    "resolve_symbol",
]
