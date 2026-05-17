import sqlite3, tempfile, os
import pandas as pd
from unittest.mock import patch, MagicMock
from quant.data.db import init_db
from quant.data.fetchers.proxy_ext import fetch_proxy_ext, EXT_PROXY_MAP


def _make_db():
    f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    init_db(f.name)
    return f.name


def _fake_index_daily(ts_code, start_date, end_date, fields):
    dates = pd.date_range('2026-01-02', '2026-04-30', freq='B')
    return pd.DataFrame({
        'trade_date': dates.strftime('%Y%m%d'),
        'close': [4500.0 + i for i in range(len(dates))],
    })


def _fake_yfinance_download(tickers, start, end, auto_adjust):
    dates = pd.date_range('2026-01-02', '2026-04-30', freq='B')
    ticker = tickers if isinstance(tickers, str) else tickers[0]
    data = {'Close': {dates[i]: 200.0 + i for i in range(len(dates))}}
    df = pd.DataFrame(data, index=dates)
    # Simulate yfinance MultiIndex columns (real behavior in 0.2.65+)
    df.columns = pd.MultiIndex.from_tuples(
        [('Close', ticker)], names=['Price', 'Ticker']
    )
    return df


def test_fetch_proxy_ext_inserts_tushare_rows():
    db = _make_db()
    try:
        mock_pro = MagicMock()
        mock_pro.index_daily.side_effect = _fake_index_daily
        with patch('quant.data.fetchers.proxy_ext._get_pro', return_value=mock_pro), \
             patch('quant.data.fetchers.proxy_ext.yf.download', side_effect=_fake_yfinance_download):
            n = fetch_proxy_ext('20260101', '20260430', db_path=db)
        assert n > 0
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM proxy_prices_ext"
            ).fetchall()
        symbols = {r[0] for r in rows}
        # All 7 proxy symbols should be present
        assert len(symbols) == 7
    finally:
        os.unlink(db)


def test_ext_proxy_map_has_seven_entries():
    assert len(EXT_PROXY_MAP) == 7
