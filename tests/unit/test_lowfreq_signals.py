"""Unit tests for low-frequency signal preparation."""

import pandas as pd

from quant.analysis.lowfreq import LowFrequencyBacktester, LowFrequencySignalBuilder, SignalConfig
from quant.services import LowFrequencyService, LowFrequencySignalRequest


def make_prices(periods: int = 260) -> pd.DataFrame:
    """Create deterministic daily OHLCV test prices."""
    index = pd.bdate_range("2023-01-02", periods=periods)
    close = pd.Series(range(100, 100 + periods), index=index, dtype=float)
    return pd.DataFrame(
        {
            "symbol": "000300.SH",
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000,
        },
        index=index,
    )


class FakeLowFreqDataService:
    """Fake data service for low-frequency service tests."""

    def __init__(self):
        self.price_request = None

    def get_price(self, request):
        self.price_request = request
        return make_prices()

    def get_trading_days(self, start, end):
        return [d.strftime("%Y%m%d") for d in make_prices().index]


class TestLowFrequencySignalBuilder:
    """Low-frequency signal builder behavior."""

    def test_build_month_end_signals(self):
        """Builder should generate one signal per available month end."""
        builder = LowFrequencySignalBuilder(
            SignalConfig(ma_months=3, vol_window=20, target_vol=0.20)
        )

        result = builder.build(make_prices())

        assert not result.empty
        assert result.index.name == "rebalance_date"
        assert {"close", "monthly_ma", "realized_vol", "trend_on", "target_position"}.issubset(
            result.columns
        )
        assert result["target_position"].between(0, 1).all()

    def test_trading_days_constrain_rebalance_dates(self):
        """Explicit trading days should determine rebalance month ends."""
        prices = make_prices(80)
        trading_days = ["20230131", "20230228", "20230331"]
        builder = LowFrequencySignalBuilder(SignalConfig(ma_months=2, vol_window=5))

        result = builder.build(prices, trading_days)

        assert list(result.index.strftime("%Y%m%d")) == trading_days

    def test_monthly_ma_uses_actual_trading_month_end(self):
        """Monthly MA should include current month when calendar month-end is closed."""
        prices = pd.DataFrame(
            {"close": [100.0, 110.0, 120.0]},
            index=pd.to_datetime(["2024-03-29", "2024-04-30", "2024-05-31"]),
        )
        builder = LowFrequencySignalBuilder(SignalConfig(ma_months=2, vol_window=2))

        result = builder.build(prices)

        assert result.loc[pd.Timestamp("2024-04-30"), "monthly_ma"] == 105.0
        assert result.loc[pd.Timestamp("2024-05-31"), "monthly_ma"] == 115.0

    def test_downtrend_sets_zero_target_position(self):
        """Price below monthly MA should produce a zero target position."""
        prices = make_prices()
        prices["close"] = list(reversed(range(100, 100 + len(prices))))
        builder = LowFrequencySignalBuilder(SignalConfig(ma_months=3, vol_window=20))

        result = builder.build(prices)

        mature = result[result["monthly_ma"].notna()]
        downtrend = ~mature["trend_on"]
        assert downtrend.any()
        assert (mature.loc[downtrend, "target_position"] == 0).all()

    def test_missing_close_raises_value_error(self):
        """Builder should reject price frames without close."""
        builder = LowFrequencySignalBuilder()

        try:
            builder.build(pd.DataFrame({"open": [1.0]}))
        except ValueError as exc:
            assert "missing required columns" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing close")


class TestLowFrequencyBacktester:
    """Low-frequency backtester behavior."""

    def test_backtest_uses_prior_month_position(self):
        """Monthly returns should use the previous rebalance target position."""
        signals = pd.DataFrame(
            {
                "close": [100.0, 110.0, 121.0],
                "target_position": [0.0, 1.0, 1.0],
            },
            index=pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-29"]),
        )

        result = LowFrequencyBacktester().run(signals)

        assert result.monthly_returns.iloc[1]["strategy"] == 0.0
        assert round(result.monthly_returns.iloc[2]["strategy"], 4) == 0.1
        assert round(result.equity_curve.iloc[-1]["strategy"], 4) == 1.1

    def test_backtest_computes_drawdown_and_metrics(self):
        """Backtest should return metrics and aligned equity curves."""
        signals = pd.DataFrame(
            {
                "close": [100.0, 120.0, 90.0, 99.0],
                "target_position": [1.0, 1.0, 0.0, 1.0],
            },
            index=pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-29", "2024-04-30"]),
        )

        result = LowFrequencyBacktester(transaction_cost=0.001).run(signals)

        assert "annual_return_strategy" in result.metrics
        assert result.metrics["max_drawdown_benchmark"] < 0
        assert list(result.equity_curve.columns) == ["strategy", "benchmark", "target_position"]

    def test_backtest_rejects_missing_required_columns(self):
        """Backtest should fail fast for invalid signal frames."""
        try:
            LowFrequencyBacktester().run(pd.DataFrame({"close": [1.0, 2.0]}))
        except ValueError as exc:
            assert "missing required columns" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing target_position")


class TestLowFrequencyService:
    """Low-frequency service behavior."""

    def test_build_signals_uses_data_service(self):
        """Service should fetch prices and calendar through DataService."""
        data_service = FakeLowFreqDataService()
        service = LowFrequencyService(data_service=data_service)

        result = service.build_signals(
            LowFrequencySignalRequest(
                symbol="000300.SH",
                start="20230101",
                end="20231231",
                asset_type="index",
                ma_months=3,
            )
        )

        assert not result.empty
        assert data_service.price_request.symbol == "000300.SH"
        assert data_service.price_request.asset_type == "index"

    def test_run_backtest_returns_metrics_and_equity(self):
        """Service should expose backtest artifacts for CLI and web."""
        data_service = FakeLowFreqDataService()
        service = LowFrequencyService(data_service=data_service)

        result = service.run_backtest(
            LowFrequencySignalRequest(
                symbol="000300.SH",
                start="20230101",
                end="20231231",
                asset_type="index",
                ma_months=3,
            )
        )

        assert "annual_return_strategy" in result["metrics"]
        assert not result["equity_curve"].empty
        assert not result["monthly_returns"].empty
