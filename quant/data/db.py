"""SQLite schema initialisation for factor data."""
from __future__ import annotations
import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS etf_shares (
    date    TEXT NOT NULL,
    symbol  TEXT NOT NULL,
    shares  REAL NOT NULL,
    PRIMARY KEY (date, symbol)
);

CREATE TABLE IF NOT EXISTS industry_valuation (
    date    TEXT NOT NULL,
    symbol  TEXT NOT NULL,
    pe_ttm  REAL,
    pb_mrq  REAL,
    pe_pct  REAL,
    pb_pct  REAL,
    PRIMARY KEY (date, symbol)
);

CREATE TABLE IF NOT EXISTS macro_pmi (
    date        TEXT PRIMARY KEY,
    mfg_pmi     REAL,
    non_mfg_pmi REAL
);

CREATE TABLE IF NOT EXISTS proxy_prices_ext (
    date    TEXT NOT NULL,
    symbol  TEXT NOT NULL,
    close   REAL NOT NULL,
    PRIMARY KEY (date, symbol)
);
"""

def init_db(db_path: str = "data/factors.db") -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(DDL)
