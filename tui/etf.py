"""
ETF Screening TUI — rich terminal rendering for ETF screening results.

This module replaces the ``ETFMomentumScreener.print_screening_results``
method that was previously embedded inside the analysis engine.

Usage:
    from tui.etf import print_screening_results
    from quant.skills import screen_etfs

    df = screen_etfs(etf_types=['broad_market'], max_etfs=10)
    print_screening_results(df)
"""

from __future__ import annotations

import pandas as pd
from typing import Optional

from tui.formatters import (
    console,
    RICH_AVAILABLE,
    grade_style,
    valuation_style,
    pct_color,
    print_plain,
)

if RICH_AVAILABLE:
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text


def print_screening_results(results_df: pd.DataFrame, top_n: int = 10) -> None:
    """Render ETF screening results to the terminal.

    Args:
        results_df: DataFrame from ``quant.skills.screen_etfs`` or similar.
        top_n: Max rows to show in the "top" and "failed" sections.
    """
    if RICH_AVAILABLE:
        _print_rich(results_df, top_n)
    else:
        _print_plain(results_df, top_n)


# ===================================================================
# Rich rendering
# ===================================================================

def _print_rich(df: pd.DataFrame, top_n: int) -> None:
    if df.empty:
        console.print("[bold red]No ETFs matched the screening criteria.[/bold red]")
        return

    passed = df[df["passes_screening"] == True]
    failed = df[df["passes_screening"] == False]

    # Header
    console.print()
    console.rule("[bold cyan]ETF Momentum Screening Results[/bold cyan]")
    console.print(
        f"  Total analysed: [bold]{len(df)}[/bold]  |  "
        f"Passed: [bold green]{len(passed)}[/bold green]  |  "
        f"Failed: [bold red]{len(failed)}[/bold red]"
    )
    console.print()

    # --- Passed ETFs table ---
    if not passed.empty:
        table = Table(
            title="✅ Passed Screening (sorted by overall score)",
            show_lines=False,
            header_style="bold cyan",
            border_style="dim",
            pad_edge=False,
        )
        table.add_column("#", style="dim", width=3)
        table.add_column("Code", width=11)
        table.add_column("Name", width=16)
        table.add_column("Category", width=10)
        table.add_column("Score", width=6, justify="right")
        table.add_column("Grade", width=5, justify="center")
        table.add_column("1M%", width=7, justify="right")
        table.add_column("3M%", width=7, justify="right")
        table.add_column("6M%", width=7, justify="right")
        table.add_column("12M%", width=7, justify="right")
        table.add_column("RSI", width=5, justify="right")
        table.add_column("Valuation", width=10)
        table.add_column("Warnings", width=28, overflow="ellipsis")

        for idx, (_, row) in enumerate(passed.iterrows(), 1):
            grade = row.get("grade", "C")
            val_level = str(row.get("valuation_level", ""))
            warnings = str(row.get("risk_warnings", ""))

            table.add_row(
                str(idx),
                str(row["ts_code"]),
                str(row["name"]),
                str(row.get("category", "")),
                f"{row['overall_score']:.3f}",
                Text(grade, style=grade_style(grade)),
                Text(f"{row['1m_return']:.1f}", style=pct_color(row["1m_return"])),
                Text(f"{row['3m_return']:.1f}", style=pct_color(row["3m_return"])),
                Text(f"{row['6m_return']:.1f}", style=pct_color(row["6m_return"])),
                Text(f"{row['12m_return']:.1f}", style=pct_color(row["12m_return"])),
                f"{row.get('rsi', 50):.0f}",
                Text(val_level, style=valuation_style(val_level)),
                warnings[:28] if warnings else "",
            )

        console.print(table)
        console.print()

    # --- Top N overall ---
    console.print(f"[bold]📊 Top {top_n} by Overall Score:[/bold]")
    top = df.head(top_n)
    for idx, (_, row) in enumerate(top.iterrows(), 1):
        status = "✅" if row["passes_screening"] else "❌"
        score_style = grade_style(row.get("grade", "C"))
        console.print(
            f"  {status} {idx:>2}  {row['ts_code']:<11} {row['name']:<16} "
            f"[{score_style}]{row['overall_score']:.3f}[/{score_style}]  "
            f"1M: [{pct_color(row['1m_return'])}]{row['1m_return']:+.1f}%[/{pct_color(row['1m_return'])}]  "
            f"3M: [{pct_color(row['3m_return'])}]{row['3m_return']:+.1f}%[/{pct_color(row['3m_return'])}]  "
            f"6M: [{pct_color(row['6m_return'])}]{row['6m_return']:+.1f}%[/{pct_color(row['6m_return'])}]"
        )
    console.print()

    # --- Failed top N ---
    if not failed.empty:
        failed_sorted = failed.sort_values("overall_score", ascending=False).head(top_n)

        table_f = Table(
            title=f"❌ Top {top_n} Near-Miss (failed, highest scores first)",
            show_lines=False,
            header_style="bold yellow",
            border_style="dim",
        )
        table_f.add_column("#", style="dim", width=3)
        table_f.add_column("Code", width=11)
        table_f.add_column("Name", width=16)
        table_f.add_column("Score", width=6, justify="right")
        table_f.add_column("Grade", width=5, justify="center")
        table_f.add_column("Failed Reasons", overflow="ellipsis")

        for idx, (_, row) in enumerate(failed_sorted.iterrows(), 1):
            reasons = row.get("failed_reasons", [])
            if isinstance(reasons, list):
                reasons_str = ", ".join(reasons[:2]) if reasons else "Score < 0.6"
            else:
                reasons_str = str(reasons) if reasons else "Score < 0.6"

            table_f.add_row(
                str(idx),
                str(row["ts_code"]),
                str(row["name"]),
                f"{row['overall_score']:.3f}",
                row.get("grade", "C"),
                reasons_str[:55],
            )

        console.print(table_f)
        console.print()

    # --- Statistics ---
    if not passed.empty:
        console.print(Panel(
            f"Avg 1M: [green]{passed['1m_return'].mean():.2f}%[/green]  |  "
            f"Avg 3M: [green]{passed['3m_return'].mean():.2f}%[/green]  |  "
            f"Avg 6M: [green]{passed['6m_return'].mean():.2f}%[/green]  |  "
            f"Avg 12M: [green]{passed['12m_return'].mean():.2f}%[/green]",
            title="📈 Passed ETF Statistics",
            border_style="green",
        ))


# ===================================================================
# Plaintext fallback
# ===================================================================

def _print_plain(df: pd.DataFrame, top_n: int) -> None:
    if df.empty:
        print_plain("No ETFs matched the screening criteria.")
        return

    passed = df[df["passes_screening"] == True]
    failed = df[df["passes_screening"] == False]

    print_plain(f"\nETF Momentum Screening Results")
    print_plain("=" * 100)
    print_plain(f"Total: {len(df)} | Passed: {len(passed)} | Failed: {len(failed)}")

    if not passed.empty:
        print_plain(f"\n--- Passed ({len(passed)}) ---")
        header = f"{'#':<4}{'Code':<12}{'Name':<20}{'Score':<8}{'Grade':<6}{'1M%':<8}{'3M%':<8}{'6M%':<8}"
        print_plain(header)
        print_plain("-" * len(header))
        for idx, (_, row) in enumerate(passed.iterrows(), 1):
            print_plain(
                f"{idx:<4}{row['ts_code']:<12}{row['name']:<20}"
                f"{row['overall_score']:<8.3f}{row.get('grade',''):<6}"
                f"{row['1m_return']:<8.1f}{row['3m_return']:<8.1f}{row['6m_return']:<8.1f}"
            )

    print_plain(f"\n--- Top {top_n} Overall ---")
    for idx, (_, row) in enumerate(df.head(top_n).iterrows(), 1):
        status = "PASS" if row["passes_screening"] else "FAIL"
        print_plain(
            f"  [{status}] {idx:>2} {row['ts_code']:<12}{row['name']:<20}"
            f"Score: {row['overall_score']:.3f} | "
            f"1M: {row['1m_return']:+.1f}% | 3M: {row['3m_return']:+.1f}%"
        )
