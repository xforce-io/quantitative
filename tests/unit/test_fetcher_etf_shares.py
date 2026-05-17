import sqlite3, tempfile, os
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from quant.data.db import init_db
from quant.data.fetchers.etf_shares import fetch_etf_shares

def _make_db():
    f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    init_db(f.name)
    return f.name

def _fake_fund_share(ts_code, start_date, end_date):
    """Mock Tushare fund_share response."""
    start_dt = pd.to_datetime(start_date, format='%Y%m%d')
    end_dt = pd.to_datetime(end_date, format='%Y%m%d')
    dates = pd.date_range(start_dt, end_dt, freq='B')
    return pd.DataFrame({
        'ts_code': ts_code,
        'trade_date': dates.strftime('%Y%m%d'),
        'fd_share': [100000.0 + i for i in range(len(dates))],
        'fund_type': None,
        'market': 'SH',
    })

def test_fetch_etf_shares_inserts_monthly_rows():
    db = _make_db()
    try:
        mock_pro = MagicMock()
        mock_pro.fund_share.side_effect = _fake_fund_share
        with patch('quant.data.fetchers.etf_shares._get_pro', return_value=mock_pro):
            n = fetch_etf_shares(['512480.SH'], '20260101', '20260430', db_path=db)
        assert n == 4  # Jan, Feb, Mar, Apr month-end rows
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT date, symbol, shares FROM etf_shares ORDER BY date"
            ).fetchall()
        assert len(rows) == 4
        assert rows[0][1] == '512480.SH'
        assert rows[0][2] > 0
    finally:
        os.unlink(db)

def test_fetch_etf_shares_upsert_on_duplicate():
    db = _make_db()
    try:
        mock_pro = MagicMock()
        mock_pro.fund_share.side_effect = _fake_fund_share
        with patch('quant.data.fetchers.etf_shares._get_pro', return_value=mock_pro):
            fetch_etf_shares(['512480.SH'], '20260101', '20260131', db_path=db)
            fetch_etf_shares(['512480.SH'], '20260101', '20260131', db_path=db)
        with sqlite3.connect(db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM etf_shares").fetchone()[0]
        assert count == 1  # upsert, not duplicate
    finally:
        os.unlink(db)
