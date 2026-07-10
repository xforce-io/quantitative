"""Tests for ETF share-split forward adjustment."""
from __future__ import annotations

import pandas as pd

from quant.data.etf_adjust import ETF_ADJ_CACHE_VERSION, apply_fund_adj_factors


def test_apply_fund_adj_factors_forward_adjusts_pre_split_prices() -> None:
    # 1:4 share split: raw close 4 -> 1. Tushare-style adj_factor rises with splits
    # so 前复权 (price * factor / factor_latest) keeps the latest price fixed and
    # scales history down: 4 * 1/4 = 1, continuous across the split.
    prices = pd.DataFrame(
        {
            "trade_date": ["20210101", "20210102", "20210103"],
            "open": [4.0, 4.0, 1.0],
            "high": [4.0, 4.0, 1.0],
            "low": [4.0, 4.0, 1.0],
            "close": [4.0, 4.0, 1.0],
            "pre_close": [4.0, 4.0, 4.0],
        }
    )
    adj = pd.DataFrame(
        {
            "trade_date": ["20210101", "20210102", "20210103"],
            "adj_factor": [1.0, 1.0, 4.0],
        }
    )
    out = apply_fund_adj_factors(prices, adj)
    assert abs(out.loc[0, "close"] - 1.0) < 1e-9
    assert abs(out.loc[1, "close"] - 1.0) < 1e-9
    assert abs(out.loc[2, "close"] - 1.0) < 1e-9
    # Daily return across split should be flat (no fake -75%)
    rets = out["close"].pct_change().dropna()
    assert (rets.abs() < 1e-9).all()


def test_apply_fund_adj_empty_adj_returns_copy() -> None:
    prices = pd.DataFrame(
        {"trade_date": ["20210101"], "close": [1.0], "open": [1.0], "high": [1.0], "low": [1.0]}
    )
    out = apply_fund_adj_factors(prices, pd.DataFrame())
    assert out.equals(prices)
    assert out is not prices


def test_cache_version_is_stable_string() -> None:
    assert ETF_ADJ_CACHE_VERSION.startswith("adj_v")
