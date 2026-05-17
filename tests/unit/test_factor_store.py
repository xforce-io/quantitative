import sqlite3
import tempfile
import os
import pandas as pd
from quant.data.db import init_db
from quant.data.factor_store import FactorStore


def _make_store():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    init_db(f.name)
    # Seed data
    with sqlite3.connect(f.name) as conn:
        conn.execute("INSERT INTO etf_shares VALUES ('2026-04-30','512480.SH',100000.0)")
        conn.execute("INSERT INTO etf_shares VALUES ('2026-03-31','512480.SH',90000.0)")
        conn.execute(
            "INSERT INTO industry_valuation VALUES ('2026-04-30','000933.SH',25.0,3.0,0.75,0.60)"
        )
        conn.execute("INSERT INTO macro_pmi VALUES ('2026-04-30',49.0,50.2)")
        conn.execute("INSERT INTO proxy_prices_ext VALUES ('2026-04-30','399101.SZ',1200.0)")
        conn.execute("INSERT INTO proxy_prices_ext VALUES ('2026-03-31','399101.SZ',1150.0)")
    return FactorStore(f.name), f.name


def test_get_etf_shares():
    store, db = _make_store()
    try:
        result = store.get_etf_shares(["512480.SH"], "2026-04-30")
        assert result == {"512480.SH": 100000.0}
    finally:
        os.unlink(db)


def test_get_etf_shares_missing_returns_empty():
    store, db = _make_store()
    try:
        result = store.get_etf_shares(["999999.SH"], "2026-04-30")
        assert result == {}
    finally:
        os.unlink(db)


def test_get_valuation_pct():
    store, db = _make_store()
    try:
        result = store.get_valuation_pct(["000933.SH"], "2026-04-30")
        assert result["000933.SH"]["pe_pct"] == 0.75
        assert result["000933.SH"]["pb_pct"] == 0.60
    finally:
        os.unlink(db)


def test_get_pmi():
    store, db = _make_store()
    try:
        assert store.get_pmi("2026-04-30") == 49.0
        assert store.get_pmi("2020-01-31") is None
    finally:
        os.unlink(db)


def test_get_proxy_prices_ext():
    store, db = _make_store()
    try:
        df = store.get_proxy_prices_ext(["399101.SZ"], "2026-01-01", "2026-04-30")
        assert "399101.SZ" in df.columns
        assert len(df) == 2
        assert df["399101.SZ"].iloc[-1] == 1200.0
    finally:
        os.unlink(db)
