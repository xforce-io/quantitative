"""ETF price adjustment helpers (share-split / merger forward adjustment).

Tushare ``fund_daily`` returns unadjusted prices. When an ETF splits, unit NAV
drops (e.g. 1:4 -> -75% single-day jump) without a corresponding market move.
Apply ``fund_adj`` factors as 前复权:

    adjusted_price_t = raw_price_t * (adj_factor_t / adj_factor_latest)

See docs/incidents/2026-05-etf-split-data-anomaly.md.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

# Cache key version: bump when adjustment logic changes so stale unadjusted
# cache files are not reused.
ETF_ADJ_CACHE_VERSION = "adj_v1"

PRICE_COLUMNS = ("open", "high", "low", "close", "pre_close")


def apply_fund_adj_factors(
    prices: pd.DataFrame,
    adj: pd.DataFrame,
    *,
    date_col: str = "trade_date",
    factor_col: str = "adj_factor",
    price_cols: Iterable[str] = PRICE_COLUMNS,
) -> pd.DataFrame:
    """Return a copy of ``prices`` with OHLC columns scaled by forward adj factors.

    Args:
        prices: OHLCV frame containing ``date_col`` (or already indexed by it).
        adj: Frame with ``date_col`` and ``factor_col`` columns.
        date_col: Trade date column name (YYYYMMDD strings or timestamps).
        factor_col: Adjustment factor column name.
        price_cols: Columns to scale when present.

    Returns:
        Adjusted price frame (same shape/columns as input). If ``adj`` is empty
        or has non-positive latest factor, returns ``prices`` unchanged (copy).
    """
    if prices is None or prices.empty:
        return prices.copy() if prices is not None else pd.DataFrame()
    if adj is None or adj.empty or factor_col not in adj.columns:
        return prices.copy()

    out = prices.copy()
    was_indexed = date_col not in out.columns
    if was_indexed:
        out = out.reset_index()
        # After reset_index the date may be named 'index' or date_col
        if date_col not in out.columns:
            # common case: DatetimeIndex reset -> 'index' or 'date'
            for candidate in ("index", "date", "trade_date"):
                if candidate in out.columns:
                    out = out.rename(columns={candidate: date_col})
                    break
        if date_col not in out.columns:
            return prices.copy()

    adj_sorted = adj.sort_values(date_col)
    latest = float(adj_sorted.iloc[-1][factor_col])
    if latest <= 0:
        return prices.copy()

    ratio = adj_sorted.set_index(date_col)[factor_col].astype(float) / latest
    # Normalize keys to string YYYYMMDD for robust join
    ratio.index = _normalize_date_index(ratio.index)
    out_dates = _normalize_date_index(out[date_col])
    scale = ratio.reindex(out_dates).ffill().bfill()
    scale = scale.to_numpy(dtype=float)

    for col in price_cols:
        if col in out.columns:
            out[col] = out[col].astype(float) * scale

    if was_indexed:
        out = out.set_index(date_col)
        # Preserve original index name/type best-effort
        if isinstance(prices.index, pd.DatetimeIndex):
            out.index = pd.to_datetime(out.index)
        return out

    return out


def _normalize_date_index(values) -> pd.Index:
    """Normalize date-like values to YYYYMMDD strings."""
    series = pd.Series(list(values))
    ts = pd.to_datetime(series, errors="coerce")
    formatted = ts.dt.strftime("%Y%m%d")
    result = []
    for raw, fmt, parsed in zip(series.tolist(), formatted.tolist(), ts.tolist()):
        if pd.isna(parsed) or fmt is None or (isinstance(fmt, float) and pd.isna(fmt)):
            result.append(str(raw).replace("-", "")[:8])
        else:
            result.append(str(fmt))
    return pd.Index(result)
