"""
Stock Analysis Skill — unified, side-effect-free entry point for
single-stock analysis (money-flow, technical, valuation).

This module extracts the core logic that was previously embedded inside
``web/data_service.fetch_stock_full_analysis`` and decouples it from
any Streamlit dependency (``@st.cache_data``, ``st.session_state``).

Consumers:
  - ``web/data_service.py``  →  can wrap these with ``@st.cache_data``
  - ``web/skillkits/``       →  can call directly for agent tool-calls
  - ``tui/``                 →  can format results with ``rich``
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from quant.core.indicators import TechnicalIndicators
from quant.core.symbol_resolver import SymbolResolver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy provider singleton
# ---------------------------------------------------------------------------

_provider_instance = None


def _get_provider():
    """Return a lazily-initialised TushareProvider singleton."""
    global _provider_instance
    if _provider_instance is None:
        from quant.data.implementations.tushare_provider import TushareProvider
        _provider_instance = TushareProvider()
    return _provider_instance


# ===================================================================
# Low-level data fetchers (no Streamlit, no print)
# ===================================================================


def get_stock_money_flow(
    symbol: str,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """Fetch institutional-vs-retail money flow analysis.

    Args:
        symbol: Stock code, e.g. '002594.SZ'.
        start_date: Start date 'YYYYMMDD'.
        end_date: End date 'YYYYMMDD'.

    Returns:
        Dict with keys: total_institutional_net, total_retail_net,
        institutional_inflow_days, total_days, sentiment, sentiment_detail.
    """
    provider = _get_provider()
    return provider.analyze_institutional_vs_retail(symbol, start_date, end_date)


def get_stock_price(
    symbol: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch stock OHLCV price data.

    Args:
        symbol: Stock code, e.g. '002594.SZ'.
        start_date: Start date 'YYYYMMDD'.
        end_date: End date 'YYYYMMDD'.

    Returns:
        DataFrame with columns: open, high, low, close, vol, etc.
    """
    provider = _get_provider()
    try:
        return provider.get_stock_data(symbol, start_date, end_date)
    except Exception:
        return pd.DataFrame()


def get_stock_technical_data(
    symbol: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch stock OHLCV data and compute technical indicators.

    Returns DataFrame with OHLCV + MA + MACD + RSI + Bollinger bands.
    Chinese-market column aliases (MACD_DIF, MACD_DEA, MACD_HIST,
    BOLL_UP, BOLL_MID, BOLL_DOWN) are added for compatibility.

    Args:
        symbol: Stock code.
        start_date: Start date 'YYYYMMDD'.
        end_date: End date 'YYYYMMDD'.

    Returns:
        DataFrame with technical indicator columns.
    """
    df = get_stock_price(symbol, start_date, end_date)
    if df.empty or 'close' not in df.columns:
        return df

    df = TechnicalIndicators.calculate_all_indicators(df)

    # Column aliases — Chinese market conventions
    if 'MACD' in df.columns:
        df['MACD_DIF'] = df['MACD']
    if 'MACD_Signal' in df.columns:
        df['MACD_DEA'] = df['MACD_Signal']
    if 'MACD_DIF' in df.columns and 'MACD_DEA' in df.columns:
        df['MACD_HIST'] = (df['MACD_DIF'] - df['MACD_DEA']) * 2

    if 'BB_Upper' in df.columns:
        df['BOLL_UP'] = df['BB_Upper']
    if 'BB_Middle' in df.columns:
        df['BOLL_MID'] = df['BB_Middle']
    if 'BB_Lower' in df.columns:
        df['BOLL_DOWN'] = df['BB_Lower']

    return df


def get_stock_valuation(
    symbol: str,
    days: int = 250,
) -> Dict[str, Any]:
    """Fetch stock valuation metrics (PE/PB/PS) with historical percentile.

    Args:
        symbol: Stock code.
        days: Lookback trading days for percentile calculation (default 250 ≈ 1Y).

    Returns:
        Dict with keys: latest, percentile, status, history, data_days.
    """
    from quant.analysis.valuation.stock_valuation import StockValuationAnalyzer
    provider = _get_provider()

    try:
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')
        df = provider.get_daily_basic(symbol, start_date, end_date)
        return StockValuationAnalyzer.compute_percentile_valuation(df, days)
    except Exception as e:
        return {'error': str(e)}


def get_trend_strength(
    symbol: str,
    days: int = 90,
) -> Dict[str, Any]:
    """Compute trend strength score for a stock (0-4 points).

    Scoring rules:
      1. Price above MA20         (+1)
      2. MA20 rising              (+1)
      3. MA60 rising              (+1)
      4. MA20 above MA60          (+1)

    Args:
        symbol: Stock code.
        days: Analysis lookback days.

    Returns:
        Trend strength analysis dict.
    """
    try:
        from quant.analysis.indicators.trend_strength_analyzer import TrendStrengthAnalyzer
        analyzer = TrendStrengthAnalyzer()
        return analyzer.analyze(symbol, days)
    except Exception as e:
        logger.error("Trend strength analysis failed: %s", e)
        return {'error': str(e)}


def resolve_symbol(
    query: str,
    stock_list: Optional[List[str]] = None,
) -> str:
    """Resolve a stock name or alias to a standard code.

    Args:
        query: User input, e.g. '比亚迪' or '002594.SZ'.
        stock_list: Optional list of known stock strings for fuzzy matching.

    Returns:
        Standard code like '002594.SZ'.  Returns *query* unchanged if
        resolution fails.
    """
    return SymbolResolver.resolve(query, stock_list)


# ===================================================================
# Composite Skill Functions
# ===================================================================


def fetch_full_analysis(
    symbol: str,
    days: int = 60,
) -> Dict[str, Any]:
    """One-shot comprehensive analysis: money-flow + technical + valuation.

    This is the agent-facing equivalent of the former
    ``web.data_service.fetch_stock_full_analysis``, but **without**
    any Streamlit dependency.

    Args:
        symbol: Stock code or name (auto-resolved).
        days: Analysis lookback days.

    Returns:
        Dict with keys: symbol, query, resolved, fetch_time,
        money_flow (dict), technical (dict), valuation (dict).
        Each sub-dict may contain an 'error' key on partial failure.
    """
    resolved_symbol = resolve_symbol(symbol)

    result: Dict[str, Any] = {
        "symbol": resolved_symbol,
        "query": symbol,
        "resolved": resolved_symbol != symbol,
        "fetch_time": datetime.now().isoformat(),
    }

    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

    # 1. Money flow
    try:
        flow = get_stock_money_flow(resolved_symbol, start, end)
        if flow and 'error' not in flow:
            result['money_flow'] = {
                'inst_net_flow_yi': round(flow.get('total_institutional_net', 0) / 1e8, 2),
                'retail_net_flow_yi': round(flow.get('total_retail_net', 0) / 1e8, 2),
                'inst_inflow_days': flow.get('institutional_inflow_days', 0),
                'total_days': flow.get('total_days', 0),
                'sentiment': flow.get('sentiment', ''),
                'sentiment_detail': flow.get('sentiment_detail', ''),
            }
    except Exception as e:
        result['money_flow'] = {'error': str(e)}

    # 2. Technical signals
    try:
        from quant.analysis.indicators.technical_analyzer import TechnicalAnalyzer
        tech_df = get_stock_technical_data(resolved_symbol, start, end)
        if tech_df is not None and not tech_df.empty:
            result['technical'] = TechnicalAnalyzer.interpret_latest_signals(tech_df)
    except Exception as e:
        result['technical'] = {'error': str(e)}

    # 3. Valuation
    try:
        val = get_stock_valuation(resolved_symbol, days=250)
        if val and 'error' not in val:
            latest = val.get('latest', {})
            percentile = val.get('percentile', {})
            status = val.get('status', {})

            result['valuation'] = {
                'pe_ttm': round(float(latest.get('pe_ttm', 0)), 2)
                    if latest.get('pe_ttm') else None,
                'pb': round(float(latest.get('pb', 0)), 2)
                    if latest.get('pb') else None,
                'ps_ttm': round(float(latest.get('ps_ttm', 0)), 2)
                    if latest.get('ps_ttm') else None,
                'dv_ratio': round(float(latest.get('dv_ratio', 0)), 2)
                    if latest.get('dv_ratio') else None,
                'total_mv_yi': round(float(latest.get('total_mv', 0)) / 10000, 2)
                    if latest.get('total_mv') else None,
                'pe_percentile': percentile.get('pe_ttm'),
                'pb_percentile': percentile.get('pb'),
                'pe_status': status.get('pe_ttm', ''),
                'pb_status': status.get('pb', ''),
            }
    except Exception as e:
        result['valuation'] = {'error': str(e)}

    # Check overall validity
    has_valid = any(
        key in result and 'error' not in result[key]
        for key in ['money_flow', 'technical', 'valuation']
    )
    if not has_valid:
        result['error'] = (
            f"Unable to fetch valid data for {resolved_symbol}. "
            "Please verify the stock code."
        )

    return result
