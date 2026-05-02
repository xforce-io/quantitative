"""Tests for TushareProvider.get_margin_data() — integration test with real API."""

import pytest
import pandas as pd
from quant.data.implementations.tushare_provider import TushareProvider


@pytest.fixture
def provider():
    return TushareProvider()


class TestGetMarginData:
    def test_returns_dataframe(self, provider):
        df = provider.get_margin_data(lookback_days=30)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_has_required_columns(self, provider):
        df = provider.get_margin_data(lookback_days=10)
        for col in ["trade_date", "rzye"]:
            assert col in df.columns, f"Missing column: {col}"

    def test_sorted_by_date(self, provider):
        df = provider.get_margin_data(lookback_days=30)
        dates = df["trade_date"].tolist()
        assert dates == sorted(dates)
