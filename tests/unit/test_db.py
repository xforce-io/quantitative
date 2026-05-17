import sqlite3
import tempfile
import os
import pytest
from quant.data.db import init_db


def test_init_db_creates_four_tables():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    try:
        init_db(db_path)
        with sqlite3.connect(db_path) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        assert tables == {'etf_shares', 'industry_valuation', 'macro_pmi', 'proxy_prices_ext'}
    finally:
        os.unlink(db_path)


def test_init_db_idempotent():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    try:
        init_db(db_path)
        init_db(db_path)  # second call must not raise
        with sqlite3.connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM etf_shares").fetchone()[0]
        assert count == 0
    finally:
        os.unlink(db_path)
