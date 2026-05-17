"""Unified read interface for factor data in factors.db."""
from __future__ import annotations
import sqlite3
import pandas as pd


class FactorStore:
    def __init__(self, db_path: str = "data/factors.db") -> None:
        self._db = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db)

    def get_etf_shares(self, symbols: list[str], date: str) -> dict[str, float]:
        """Return {symbol: shares(万份)} for the given month-end date."""
        if not symbols:
            return {}
        placeholders = ",".join("?" * len(symbols))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT symbol, shares FROM etf_shares WHERE date=? AND symbol IN ({placeholders})",
                [date] + symbols,
            ).fetchall()
        return {sym: shares for sym, shares in rows}

    def get_valuation_pct(self, symbols: list[str], date: str) -> dict[str, dict]:
        """Return {symbol: {pe_pct, pb_pct}} for the given month-end date."""
        if not symbols:
            return {}
        placeholders = ",".join("?" * len(symbols))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT symbol, pe_pct, pb_pct FROM industry_valuation "
                f"WHERE date=? AND symbol IN ({placeholders})",
                [date] + symbols,
            ).fetchall()
        return {sym: {"pe_pct": pe_pct, "pb_pct": pb_pct} for sym, pe_pct, pb_pct in rows}

    def get_pmi(self, date: str) -> float | None:
        """Return manufacturing PMI for the given month-end date, or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT mfg_pmi FROM macro_pmi WHERE date=?", [date]
            ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def get_proxy_prices_ext(
        self, symbols: list[str], start: str, end: str
    ) -> pd.DataFrame:
        """
        Return monthly close prices for extended proxy symbols.
        Index: DatetimeIndex (month-end), columns: symbol codes.
        """
        if not symbols:
            return pd.DataFrame()
        placeholders = ",".join("?" * len(symbols))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT date, symbol, close FROM proxy_prices_ext "
                f"WHERE date>=? AND date<=? AND symbol IN ({placeholders})",
                [start, end] + symbols,
            ).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["date", "symbol", "close"])
        df["date"] = pd.to_datetime(df["date"])
        return df.pivot(index="date", columns="symbol", values="close").sort_index()
