"""Data service shared by CLI and web entrypoints."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Literal

import pandas as pd

from quant.data import create_data_provider
from quant.data import providers as provider_module

AssetType = Literal["stock", "index", "fund", "etf"]


@dataclass(frozen=True)
class PriceRequest:
    """Input model for normalized price data access."""

    symbol: str
    start: str
    end: str
    asset_type: AssetType = "stock"
    freq: str = "D"
    provider: str = "auto"


@dataclass(frozen=True)
class DataStatus:
    """Structured data layer status result."""

    providers: Dict[str, bool]
    environment: Dict[str, bool]
    cache_dir: str
    cache_exists: bool
    default_provider: str


class DataService:
    """Provide data layer inspection and orchestration."""

    REQUIRED_PRICE_COLUMNS = ("open", "high", "low", "close", "volume")

    def __init__(
        self,
        project_root: Path | None = None,
        provider_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self._provider_factory = provider_factory

    def get_status(self, default_provider: str = "auto") -> DataStatus:
        """Return data layer status without initializing authenticated providers."""
        cache_dir = self.project_root / "cache"
        has_tushare_token = bool(os.getenv("TUSHARE_TOKEN"))

        selected_provider = default_provider
        if default_provider == "auto":
            if provider_module.TUSHARE_AVAILABLE and has_tushare_token:
                selected_provider = "tushare"
            elif provider_module.YAHOO_AVAILABLE:
                selected_provider = "yahoo"

        return DataStatus(
            providers={
                "tushare": provider_module.TUSHARE_AVAILABLE,
                "yahoo": provider_module.YAHOO_AVAILABLE,
            },
            environment={
                "TUSHARE_TOKEN": has_tushare_token,
            },
            cache_dir=str(cache_dir),
            cache_exists=cache_dir.exists(),
            default_provider=selected_provider,
        )

    def get_price(self, request: PriceRequest, provider: Any | None = None) -> pd.DataFrame:
        """Return normalized OHLCV data for stock, index, fund, or ETF assets."""
        data_provider = provider or self._create_provider(request.provider)

        if request.asset_type == "stock":
            raw = data_provider.get_stock_data(
                request.symbol, request.start, request.end, request.freq
            )
        elif request.asset_type == "index":
            raw = data_provider.get_index_data(
                request.symbol, request.start, request.end, request.freq
            )
        elif request.asset_type in {"fund", "etf"}:
            raw = data_provider.get_fund_data(
                request.symbol, request.start, request.end, request.freq
            )
        else:
            raise ValueError(f"Unsupported asset type: {request.asset_type}")

        return self._normalize_price_frame(raw, request.symbol)

    def get_fundamental(
        self,
        symbol: str,
        start: str,
        end: str,
        provider: Any | None = None,
        provider_name: str = "tushare",
    ) -> pd.DataFrame | Dict[str, Any]:
        """Return fundamental data through the canonical data service path."""
        data_provider = provider or self._create_provider(provider_name)

        if hasattr(data_provider, "get_daily_basic"):
            return data_provider.get_daily_basic(symbol, start, end)
        if hasattr(data_provider, "get_financial_data"):
            return data_provider.get_financial_data(symbol, start, end)
        raise NotImplementedError("Fundamental data is not supported by this provider")

    def get_money_flow(
        self,
        symbol: str,
        start: str,
        end: str,
        provider: Any | None = None,
        provider_name: str = "tushare",
    ) -> pd.DataFrame:
        """Return money flow data through the canonical data service path."""
        data_provider = provider or self._create_provider(provider_name)

        if not hasattr(data_provider, "get_money_flow"):
            raise NotImplementedError("Money flow data is not supported by this provider")
        return data_provider.get_money_flow(symbol, start, end)

    def get_trading_days(
        self,
        start: str,
        end: str,
        provider: Any | None = None,
        provider_name: str = "tushare",
    ) -> list[str]:
        """Return open trading days in YYYYMMDD format."""
        data_provider = provider or self._create_provider(provider_name)

        if not hasattr(data_provider, "get_trading_days"):
            raise NotImplementedError("Trading calendar is not supported by this provider")
        return list(data_provider.get_trading_days(start, end))

    def _create_provider(self, provider_name: str) -> Any:
        """Create a provider using the configured factory."""
        if self._provider_factory is not None:
            return self._provider_factory(provider_name)
        return create_data_provider(provider_name)

    def _normalize_price_frame(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Normalize provider price data to a stable OHLCV frame."""
        if df is None or df.empty:
            return pd.DataFrame(columns=("symbol", "open", "high", "low", "close", "volume"))

        normalized = df.copy()
        normalized.columns = [str(col).lower() for col in normalized.columns]
        normalized = normalized.rename(columns={"trade_date": "date", "vol": "volume"})

        if "date" in normalized.columns:
            normalized["date"] = pd.to_datetime(normalized["date"])
            normalized = normalized.set_index("date")
        elif not isinstance(normalized.index, pd.DatetimeIndex):
            normalized.index = pd.to_datetime(normalized.index)

        normalized.index.name = "date"
        normalized = normalized.sort_index()

        missing = [col for col in self.REQUIRED_PRICE_COLUMNS if col not in normalized.columns]
        if missing:
            raise ValueError(f"Price data missing required columns: {', '.join(missing)}")

        for col in self.REQUIRED_PRICE_COLUMNS:
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce")

        normalized["symbol"] = symbol
        ordered = ["symbol", *self.REQUIRED_PRICE_COLUMNS]
        extra_cols = [col for col in normalized.columns if col not in ordered]
        return normalized[ordered + extra_cols]
