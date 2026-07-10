#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd


def _make_ohlcv(trade_dates):
    n = len(trade_dates)
    return pd.DataFrame(
        {
            'trade_date': trade_dates,
            'open': [1.0] * n,
            'high': [1.0] * n,
            'low': [1.0] * n,
            'close': [1.0] * n,
            'vol': [100.0] * n,
            'amount': [1000.0] * n,
        }
    )


def _date_range_yyyymmdd(start_date: str, end_date: str):
    dates = pd.date_range(pd.to_datetime(start_date), pd.to_datetime(end_date), freq='D')
    return [d.strftime('%Y%m%d') for d in dates]


class _FakePro:
    def __init__(self, limit: int):
        self.limit = limit
        self.calls = []

    def daily(self, ts_code: str, start_date: str, end_date: str, **_kwargs):
        self.calls.append(('daily', ts_code, start_date, end_date))
        if ts_code == '513100.SH':
            return pd.DataFrame()

        all_dates = _date_range_yyyymmdd(start_date, end_date)
        trade_dates = list(reversed(all_dates[-self.limit :]))
        return _make_ohlcv(trade_dates)

    def fund_daily(self, ts_code: str, start_date: str, end_date: str, **_kwargs):
        self.calls.append(('fund_daily', ts_code, start_date, end_date))
        all_dates = _date_range_yyyymmdd(start_date, end_date)
        trade_dates = list(reversed(all_dates[-self.limit :]))
        return _make_ohlcv(trade_dates)

    def fund_adj(self, ts_code: str, start_date: str, end_date: str, **_kwargs):
        self.calls.append(('fund_adj', ts_code, start_date, end_date))
        all_dates = _date_range_yyyymmdd(start_date, end_date)
        return pd.DataFrame(
            {
                'trade_date': all_dates,
                'adj_factor': [1.0] * len(all_dates),
            }
        )


def test_data_provider_tushare_paging_stock(monkeypatch):
    from quant.data.providers import DataProvider

    fake_pro = _FakePro(limit=3)

    class _DP(DataProvider):
        def __init__(self):
            self.provider_name = 'tushare'
            self.provider = fake_pro
            self.cache_enabled = False
            self.config = {
                'tushare_paging_threshold': 3,
                'tushare_paging_max_pages': 20,
            }

    dp = _DP()
    df = dp._fetch_tushare_data('000001.SZ', '20200101', '20200110', 'D')

    assert len(df) == 10
    assert df['date'].min() == '20200101'
    assert df['date'].max() == '20200110'

    end_dates = [c[3] for c in fake_pro.calls if c[0] == 'daily']
    assert end_dates == ['20200110', '20200107', '20200104', '20200101']


def test_data_provider_tushare_paging_fund(monkeypatch):
    from quant.data.providers import DataProvider

    fake_pro = _FakePro(limit=3)

    class _DP(DataProvider):
        def __init__(self):
            self.provider_name = 'tushare'
            self.provider = fake_pro
            self.cache_enabled = False
            self.config = {
                'tushare_paging_threshold': 3,
                'tushare_paging_max_pages': 20,
            }

    dp = _DP()
    df = dp._fetch_tushare_data('513100.SH', '20200101', '20200110', 'D')

    assert len(df) == 10
    assert df['date'].min() == '20200101'
    assert df['date'].max() == '20200110'

    daily_calls = [c for c in fake_pro.calls if c[0] == 'daily']
    fund_calls = [c for c in fake_pro.calls if c[0] == 'fund_daily']
    assert len(daily_calls) == 1
    assert len(fund_calls) > 1


def test_tushare_data_provider_get_fund_data_paging(monkeypatch, tmp_path):
    import quant.data_providers.data_provider as dp_mod
    from quant.data_providers.data_provider import TushareDataProvider

    fake_pro = _FakePro(limit=3)
    monkeypatch.setattr(dp_mod.ts, 'set_token', lambda _: None)
    monkeypatch.setattr(dp_mod.ts, 'pro_api', lambda: fake_pro)

    provider = TushareDataProvider(
        {
            'token': 'dummy',
            'cacheEnabled': False,
            'dataPath': str(tmp_path / 'tushare'),
            'pagingThreshold': 3,
            'pagingMaxPages': 20,
        }
    )

    df = provider.getFundData('513100.SH', '20200101', '20200110', 'D')
    assert len(df) == 10
    assert str(df.index.min().date()) == '2020-01-01'
    assert str(df.index.max().date()) == '2020-01-10'
