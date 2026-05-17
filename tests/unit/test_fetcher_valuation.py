import sqlite3, tempfile, os
import pandas as pd
from unittest.mock import patch, MagicMock
from quant.data.db import init_db
from quant.data.fetchers.valuation import fetch_valuation

SYMBOLS = ['000933.SH', '399986.SZ']

def _make_db():
    f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    init_db(f.name)
    return f.name

def _fake_trade_cal(**kwargs):
    return pd.DataFrame({'cal_date': ['20260130', '20260227', '20260331', '20260430']})

def _fake_dailybasic(trade_date, fields):
    return pd.DataFrame({
        'ts_code':    ['000933.SH', '399986.SZ', '000300.SH'],
        'trade_date': [trade_date] * 3,
        'pe_ttm':     [25.0, 10.0, 15.0],
        'pb':         [3.0,  1.2,  1.8],
    })

def test_fetch_valuation_inserts_rows():
    db = _make_db()
    try:
        mock_pro = MagicMock()
        mock_pro.trade_cal.side_effect = _fake_trade_cal
        mock_pro.index_dailybasic.side_effect = _fake_dailybasic
        with patch('quant.data.fetchers.valuation._get_pro', return_value=mock_pro):
            n = fetch_valuation(SYMBOLS, '20260101', '20260430', db_path=db)
        # 4 months × 2 symbols = 8 rows
        assert n == 8
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT date, symbol, pe_ttm, pe_pct FROM industry_valuation ORDER BY date, symbol"
            ).fetchall()
        assert len(rows) == 8
        # pe_pct must be between 0 and 1
        for _, _, _, pe_pct in rows:
            assert 0.0 <= pe_pct <= 1.0
    finally:
        os.unlink(db)
