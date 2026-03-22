"""
Shared TUI formatting utilities.

Provides reusable Rich components (tables, panels, progress bars)
used across all TUI sub-modules.  Falls back to plain-text output
if Rich is unavailable.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Module-level console singleton
console = Console() if RICH_AVAILABLE else None


# ---------------------------------------------------------------------------
# Grade / status helpers
# ---------------------------------------------------------------------------

GRADE_COLORS = {
    "A": "bold green",
    "B": "yellow",
    "C": "red",
}

VALUATION_COLORS = {
    "极度低估": "bold green",
    "低估": "green",
    "合理": "white",
    "高估": "yellow",
    "极度高估": "bold red",
    "数据不足": "dim",
}


def grade_style(grade: str) -> str:
    """Return Rich style string for a screening grade."""
    return GRADE_COLORS.get(grade, "white")


def valuation_style(level: str) -> str:
    """Return Rich style string for a valuation level."""
    for key, style in VALUATION_COLORS.items():
        if key in level:
            return style
    return "white"


def pct_color(value: float) -> str:
    """Return Rich color name based on positive/negative percentage."""
    if value > 0:
        return "green"
    elif value < 0:
        return "red"
    return "white"


def fmt_pct(value: float, width: int = 0) -> str:
    """Format a percentage value with sign."""
    return f"{value:+.1f}%" if value else "N/A"


def print_plain(msg: str) -> None:
    """Fallback printer when Rich is not available."""
    print(msg, file=sys.stdout)
