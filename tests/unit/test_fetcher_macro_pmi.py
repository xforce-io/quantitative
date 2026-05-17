import sqlite3, tempfile, os
import pandas as pd
from unittest.mock import patch, MagicMock
from quant.data.db import init_db
from quant.data.fetchers.macro_pmi import fetch_pmi

def _make_db():
    f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    init_db(f.name)
    return f.name

def _fake_cn_pmi(start_m, end_m):
    return pd.DataFrame({
        'MONTH':      ['202604', '202603', '202602', '202601'],
        'PMI010000':  [49.0, 50.5, 50.2, 49.1],
        'PMI030000':  [50.2, 51.4, 51.1, 50.1],
    })

def _fake_trade_cal(**kwargs):
    return pd.DataFrame({'cal_date': ['20260130', '20260227', '20260331', '20260430']})

def test_fetch_pmi_inserts_rows():
    db = _make_db()
    try:
        mock_pro = MagicMock()
        mock_pro.cn_pmi.side_effect = _fake_cn_pmi
        mock_pro.trade_cal.side_effect = _fake_trade_cal
        with patch('quant.data.fetchers.macro_pmi._get_pro', return_value=mock_pro):
            n = fetch_pmi('202601', '202604', db_path=db)
        assert n == 4
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT date, mfg_pmi, non_mfg_pmi FROM macro_pmi ORDER BY date"
            ).fetchall()
        assert len(rows) == 4
        assert rows[0][1] == 49.1   # Jan mfg PMI
        assert rows[3][1] == 49.0   # Apr mfg PMI
    finally:
        os.unlink(db)
