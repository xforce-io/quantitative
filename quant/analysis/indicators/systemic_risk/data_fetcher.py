"""Fetch FRED / Yahoo series for the systemic risk feature panel."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd

from quant.core.logging_config import get_logger

logger = get_logger(__name__)


def yf_download(ticker: str, start=None, end=None, progress: bool = False) -> pd.DataFrame:
    """Wrapper so tests can patch a stable symbol."""
    import yfinance as yf

    return yf.download(ticker, start=start, end=end, progress=progress)


def series_from_fred_map(
    raw: Dict[str, pd.Series],
    series_ids: list,
    compute: str = "direct",
) -> Optional[pd.Series]:
    """Combine raw FRED series into one indicator series."""
    series_list = []
    for sid in series_ids:
        s = raw.get(sid)
        if s is None or s.empty:
            return None
        series_list.append(s.dropna())

    if compute == "direct":
        result = series_list[0]
    elif compute == "subtract":
        s1, s2 = series_list[0], series_list[1]
        combined = pd.DataFrame({"s1": s1, "s2": s2}).sort_index().ffill().dropna()
        if combined.empty:
            return None
        result = combined["s1"] - combined["s2"]
    elif compute == "net_liquidity":
        walcl, tga, rrp = series_list[0], series_list[1], series_list[2]
        combined = (
            pd.DataFrame({"walcl": walcl, "tga": tga, "rrp": rrp})
            .sort_index()
            .ffill()
            .dropna()
        )
        if combined.empty:
            return None
        result = combined["walcl"] - combined["tga"] - combined["rrp"]
    else:
        raise ValueError(f"Unknown compute: {compute}")

    result = result.sort_index()
    # Business-day friendly: keep native index; panel truncates by as_of
    result.index = pd.to_datetime(result.index).normalize()
    result = result[~result.index.duplicated(keep="last")]
    return result.dropna()


# Logical name → FRED recipe
FRED_RECIPES: Dict[str, dict] = {
    "sofr_iorb_spread": {
        "ids": ["SOFR", "IORB"],
        "compute": "subtract",
    },
    "effr_iorb_spread": {
        "ids": ["EFFR", "IORB"],
        "compute": "subtract",
    },
    "cp_tbill_spread": {
        "ids": ["DCPF3M", "DGS3MO"],
        "compute": "subtract",
    },
    "nfcirisk": {"ids": ["NFCIRISK"], "compute": "direct"},
    "stlfsi4": {"ids": ["STLFSI4"], "compute": "direct"},
    # ICE BofA OAS series are truncated on FRED (~2023-07+ for many keys). Use BAA–10Y spread.
    "hy_oas": {"ids": ["BAA10Y"], "compute": "direct"},
    "net_liquidity": {
        "ids": ["WALCL", "WTREGEN", "RRPONTSYD"],
        "compute": "net_liquidity",
    },
    "dgs2": {"ids": ["DGS2"], "compute": "direct"},
    "real_yield": {"ids": ["DFII10"], "compute": "direct"},
}

YAHOO_TICKERS: Dict[str, str] = {
    "vix": "^VIX",
    "move": "^MOVE",
    "gold": "GC=F",
    "copper": "HG=F",
    "usdjpy": "JPY=X",
}


class SystemicRiskDataFetcher:
    """Network-backed fetcher for systemic risk frames."""

    def __init__(self, fred_api_key: Optional[str] = None):
        self._fred = None
        self._fred_api_key = fred_api_key

    def _get_fred(self):
        if self._fred is None:
            from fredapi import Fred
            from dotenv import load_dotenv

            load_dotenv()
            api_key = self._fred_api_key or os.environ.get("FRED_API_KEY")
            if not api_key:
                raise ValueError("FRED_API_KEY required for systemic risk fetcher")
            self._fred = Fred(api_key=api_key)
        return self._fred

    def _fetch_fred_raw(
        self, series_ids: list, start: datetime, end: datetime
    ) -> Dict[str, pd.Series]:
        fred = self._get_fred()
        raw: Dict[str, pd.Series] = {}
        for sid in series_ids:
            try:
                s = fred.get_series(sid, observation_start=start, observation_end=end)
                if s is not None and not s.empty:
                    s = s.dropna()
                    s.index = pd.to_datetime(s.index).normalize()
                    raw[sid] = s
            except Exception as e:
                logger.warning(f"FRED series {sid} failed: {e}")
        return raw

    def _fetch_yahoo_close(
        self, ticker: str, start: datetime, end: datetime
    ) -> Optional[pd.Series]:
        try:
            df = yf_download(
                ticker,
                start=start.strftime("%Y-%m-%d"),
                end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
                progress=False,
            )
            if df is None or df.empty:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            col = "Close" if "Close" in df.columns else "close"
            if col not in df.columns:
                return None
            s = df[col].dropna().squeeze()
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            s.index = pd.to_datetime(s.index).normalize()
            return s
        except Exception as e:
            logger.warning(f"Yahoo {ticker} failed: {e}")
            return None

    def fetch_all(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        lookback_days: int = 1200,
    ) -> Dict[str, pd.Series]:
        """Fetch all frames needed by ``build_panel_from_frames``."""
        end_dt = pd.Timestamp(end).to_pydatetime() if end else datetime.now()
        if start:
            start_dt = pd.Timestamp(start).to_pydatetime() - timedelta(days=400)
        else:
            start_dt = end_dt - timedelta(days=lookback_days)

        # Collect all FRED ids
        all_ids = sorted({sid for r in FRED_RECIPES.values() for sid in r["ids"]})
        raw = self._fetch_fred_raw(all_ids, start_dt, end_dt)

        frames: Dict[str, pd.Series] = {}
        for name, recipe in FRED_RECIPES.items():
            try:
                s = series_from_fred_map(raw, recipe["ids"], recipe["compute"])
                if s is not None and not s.empty:
                    frames[name] = s
            except Exception as e:
                logger.warning(f"Build {name} failed: {e}")

        # Yahoo
        yahoo_series: Dict[str, pd.Series] = {}
        for name, ticker in YAHOO_TICKERS.items():
            s = self._fetch_yahoo_close(ticker, start_dt, end_dt)
            if s is not None:
                yahoo_series[name] = s
                if name in ("vix", "move", "gold", "usdjpy"):
                    frames[name] = s

        # copper/gold ratio
        if "copper" in yahoo_series and "gold" in yahoo_series:
            aligned = pd.DataFrame(
                {"c": yahoo_series["copper"], "g": yahoo_series["gold"]}
            ).dropna()
            if not aligned.empty:
                frames["copper_gold"] = aligned["c"] / aligned["g"]

        logger.info(
            f"SystemicRiskDataFetcher: loaded {len(frames)} series "
            f"({', '.join(sorted(frames.keys()))})"
        )
        return frames
