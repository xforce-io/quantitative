"""Unit tests for application services."""

import pandas as pd

from quant.services import DataService, PriceRequest, StrategyService, SystemService


class FakeDataProvider:
    """Small fake provider for service-layer unit tests."""

    def __init__(self):
        self.calls = []

    def get_stock_data(self, symbol, start, end, freq="D"):
        self.calls.append(("stock", symbol, start, end, freq))
        return pd.DataFrame(
            {
                "trade_date": ["20240102", "20240103"],
                "open": [10.0, 10.5],
                "high": [10.8, 11.0],
                "low": [9.8, 10.2],
                "close": [10.4, 10.9],
                "vol": [1000, 1200],
            }
        )

    def get_index_data(self, symbol, start, end, freq="D"):
        self.calls.append(("index", symbol, start, end, freq))
        return self.get_stock_data(symbol, start, end, freq)

    def get_fund_data(self, symbol, start, end, freq="D"):
        self.calls.append(("fund", symbol, start, end, freq))
        return self.get_stock_data(symbol, start, end, freq)

    def get_daily_basic(self, symbol, start, end):
        self.calls.append(("daily_basic", symbol, start, end))
        return pd.DataFrame({"ts_code": [symbol], "pe_ttm": [12.3]})

    def get_money_flow(self, symbol, start, end):
        self.calls.append(("money_flow", symbol, start, end))
        return pd.DataFrame({"ts_code": [symbol], "net_mf_amount": [100.0]})

    def get_margin_balance(self, start, end):
        self.calls.append(("margin_balance", start, end))
        return pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "rzye": [1.0e12, 1.05e12],
                "rqye": [1.0e10, 1.1e10],
                "total": [1.01e12, 1.061e12],
            }
        )

    def get_northbound_flow(self, start, end):
        self.calls.append(("northbound_flow", start, end))
        return pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "hgt_net": [10.0, -5.0],
                "sgt_net": [3.0, 2.0],
                "total_net": [13.0, -3.0],
            }
        )

    def get_trading_days(self, start, end):
        self.calls.append(("trading_days", start, end))
        return ["20240102", "20240103"]


class TestDataService:
    """Data service behavior."""

    def test_get_status_does_not_initialize_provider(self, tmp_path):
        """Data status should inspect availability without network authentication."""
        status = DataService(project_root=tmp_path).get_status()

        assert "tushare" in status.providers
        assert "yahoo" in status.providers
        assert "TUSHARE_TOKEN" in status.environment
        assert status.cache_dir == str(tmp_path / "cache")
        assert status.cache_exists is False

    def test_auto_provider_selection_prefers_available_provider(self, tmp_path):
        """Auto status should resolve to a concrete provider when possible."""
        status = DataService(project_root=tmp_path).get_status(default_provider="auto")

        assert status.default_provider in {"auto", "tushare", "yahoo"}

    def test_get_price_normalizes_stock_data(self):
        """Stock price data should normalize date, symbol, and OHLCV columns."""
        provider = FakeDataProvider()
        service = DataService()

        df = service.get_price(
            PriceRequest("000001.SZ", "20240101", "20240131"),
            provider=provider,
        )

        assert provider.calls[0] == ("stock", "000001.SZ", "20240101", "20240131", "D")
        assert list(df.columns[:6]) == ["symbol", "open", "high", "low", "close", "volume"]
        assert str(df.index[0].date()) == "2024-01-02"
        assert df.index.name == "date"
        assert df.iloc[0]["symbol"] == "000001.SZ"
        assert df.iloc[0]["volume"] == 1000

    def test_get_price_routes_index_and_etf_assets(self):
        """Asset type should select the matching provider method."""
        provider = FakeDataProvider()
        service = DataService()

        service.get_price(
            PriceRequest("000300.SH", "20240101", "20240131", asset_type="index"),
            provider=provider,
        )
        service.get_price(
            PriceRequest("510300.SH", "20240101", "20240131", asset_type="etf"),
            provider=provider,
        )

        assert provider.calls[0][0] == "index"
        assert provider.calls[2][0] == "fund"

    def test_get_price_rejects_missing_ohlcv_columns(self):
        """Price normalization should fail fast when required columns are absent."""
        service = DataService()
        bad_df = pd.DataFrame({"trade_date": ["20240102"], "close": [10.0]})

        try:
            service._normalize_price_frame(bad_df, "000001.SZ")
        except ValueError as exc:
            assert "missing required columns" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing OHLCV columns")

    def test_get_fundamental_money_flow_and_calendar(self):
        """Low-frequency A-share data facets should share one service entrypoint."""
        provider = FakeDataProvider()
        service = DataService()

        fundamental = service.get_fundamental("000001.SZ", "20240101", "20240131", provider)
        money_flow = service.get_money_flow("000001.SZ", "20240101", "20240131", provider)
        trading_days = service.get_trading_days("20240101", "20240131", provider)

        assert fundamental.iloc[0]["pe_ttm"] == 12.3
        assert money_flow.iloc[0]["net_mf_amount"] == 100.0
        assert trading_days == ["20240102", "20240103"]

    def test_get_margin_balance_delegates_to_provider(self):
        provider = FakeDataProvider()
        service = DataService()

        df = service.get_margin_balance("20240101", "20240131", provider)

        assert provider.calls[-1] == ("margin_balance", "20240101", "20240131")
        assert df.iloc[0]["total"] == 1.01e12

    def test_get_northbound_flow_delegates_to_provider(self):
        provider = FakeDataProvider()
        service = DataService()

        df = service.get_northbound_flow("20240101", "20240131", provider)

        assert provider.calls[-1] == ("northbound_flow", "20240101", "20240131")
        assert df.iloc[0]["total_net"] == 13.0

    def test_get_margin_balance_raises_when_provider_missing_method(self):
        class BareProvider:
            pass

        service = DataService()
        try:
            service.get_margin_balance("20240101", "20240131", BareProvider())
        except NotImplementedError as exc:
            assert "Margin balance" in str(exc)
        else:
            raise AssertionError("Expected NotImplementedError")


class TestSystemService:
    """System service behavior."""

    def test_get_status_uses_project_root(self, tmp_path):
        """Status checks should be relative to the configured project root."""
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "config.yaml").write_text("app: test\n", encoding="utf-8")
        (tmp_path / "data").mkdir()

        status = SystemService(project_root=tmp_path).get_status(
            directories=("data", "cache"),
            config_files=("config/config.yaml", "config/screens.yaml"),
        )

        assert status.directories == {"data": True, "cache": False}
        assert status.config_files == {
            "config/config.yaml": True,
            "config/screens.yaml": False,
        }

    def test_default_project_root_points_to_repo(self):
        """Default service should resolve the repository root."""
        root = SystemService().project_root

        assert (root / "quant").is_dir()
        assert (root / "pyproject.toml").is_file()


class TestStrategyService:
    """Strategy service behavior."""

    def test_list_strategies_returns_registered_metadata(self):
        """Strategy list should expose stable metadata for CLI and web."""
        strategies = StrategyService().list_strategies()
        names = {item["name"] for item in strategies}

        assert "ma_crossover" in names
        assert "hold" in names
        assert all(item["class"] for item in strategies)
        assert all(item["description"] for item in strategies)

    def test_unknown_strategy_backtest_raises_value_error(self):
        """Backtest requests should reject unknown strategy names before data access."""
        from quant.services import StrategyBacktestRequest

        service = StrategyService()
        request = StrategyBacktestRequest(strategy_name="missing", symbol="000001.SZ")

        try:
            service.run_backtest(request)
        except ValueError as exc:
            assert "Unknown strategy" in str(exc)
        else:
            raise AssertionError("Expected ValueError for unknown strategy")
