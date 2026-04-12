"""
Web Data Service Layer
统一的数据获取服务，供所有 Web 页面复用。
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Any
import sys
import logging
from pathlib import Path

# 确保项目路径
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from quant.data.implementations.tushare_provider import TushareProvider
from quant.core.indicators import TechnicalIndicators
from quant.core.symbol_resolver import SymbolResolver

# 获取 logger
logger = logging.getLogger(__name__)


# ==================== Provider 单例 ====================

@st.cache_resource
def get_provider() -> TushareProvider:
    """获取 TushareProvider 单例"""
    return TushareProvider()


# ==================== 候选池管理 ====================

CANDIDATES_DIR = Path(__file__).parent.parent / "config" / "candidates"


def get_candidate_files() -> List[str]:
    """获取所有候选池文件列表"""
    if not CANDIDATES_DIR.exists():
        return []
    return [f.stem for f in CANDIDATES_DIR.glob("*.txt")]


@st.cache_data(ttl=7200, show_spinner=False)  # 2小时缓存
def load_candidates(pool_name: str = "top_ashare_stocks") -> pd.DataFrame:
    """
    加载候选池数据
    
    文件格式: 行业,名称,代码,描述 (每行一条)
    
    Args:
        pool_name: 候选池文件名 (不含扩展名)
    
    Returns:
        DataFrame with columns: [industry, name, symbol, description]
    """
    file_path = CANDIDATES_DIR / f"{pool_name}.txt"
    
    if not file_path.exists():
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(
            file_path, 
            header=None, 
            names=['industry', 'name', 'symbol', 'description'],
            dtype=str
        )
        
        # 转换代码格式: 300033 -> 300033.SZ
        df['symbol'] = df['symbol'].apply(SymbolResolver.format_symbol)
        df['display'] = df.apply(lambda x: f"{x['symbol']} {x['name']}", axis=1)
        
        return df
    except Exception as e:
        return pd.DataFrame()


def get_candidate_industries(pool_name: str = "top_ashare_stocks") -> List[str]:
    """获取候选池中的所有行业"""
    df = load_candidates(pool_name)
    if df.empty:
        return []
    return sorted(df['industry'].unique().tolist())


# ==================== 交易日历 ====================

@st.cache_data(ttl=7200, show_spinner=False)  # 2小时缓存
def get_trading_days(start: str, end: str) -> List[str]:
    """获取交易日列表"""
    provider = get_provider()
    return provider.get_trading_days(start, end)


def get_latest_trading_day() -> datetime:
    """获取最近的交易日 (智能回溯，委托给 SymbolResolver)"""
    return SymbolResolver.get_latest_trading_day()


# ==================== 股票数据 ====================

@st.cache_data(ttl=86400, show_spinner=False)
def get_stock_list() -> List[str]:
    """
    获取所有股票列表 (A股 + 港股)
    格式: ["000001.SZ 平安银行", "00700.HK 腾讯控股", ...] 
    用于 Selectbox 搜索
    """
    provider = get_provider()
    result = []
    
    # A股
    df_a = provider.get_stock_basic()
    if not df_a.empty:
        result.extend(df_a.apply(lambda x: f"{x['ts_code']} {x['name']}", axis=1).tolist())
    
    # 港股
    try:
        df_hk = provider.get_hk_stock_basic()
        if not df_hk.empty and 'ts_code' in df_hk.columns and 'name' in df_hk.columns:
            result.extend(df_hk.apply(lambda x: f"{x['ts_code']} {x['name']}", axis=1).tolist())
    except Exception as e:
        logger.debug(f"港股接口不可用: {e}")  # 记录日志而非静默忽略

    return result


@st.cache_data(ttl=86400, show_spinner=False)  # 24小时缓存
def get_stock_money_flow(symbol: str, start: str, end: str) -> Dict[str, Any]:
    """获取个股资金流向分析 (机构 vs 散户)"""
    provider = get_provider()
    return provider.analyze_institutional_vs_retail(symbol, start, end)


@st.cache_data(ttl=7200, show_spinner=False)  # 2小时缓存
def get_stock_technical_data(symbol: str, start: str, end: str) -> pd.DataFrame:
    """
    获取个股K线数据并计算技术指标
    返回包含 OHLCV + MA + MACD + RSI 的 DataFrame
    """
    provider = get_provider()
    try:
        df = provider.get_stock_data(symbol, start, end)
    except Exception:
        return pd.DataFrame()
    
    if df.empty or 'close' not in df.columns:
        return df

    # 使用统一的技术指标计算
    df = TechnicalIndicators.calculate_all_indicators(df)

    # 列名别名：保持向后兼容
    # MACD: TechnicalIndicators 输出 MACD/MACD_Signal/MACD_Histogram → 中国市场惯例 DIF/DEA/HIST
    if 'MACD' in df.columns:
        df['MACD_DIF'] = df['MACD']
    if 'MACD_Signal' in df.columns:
        df['MACD_DEA'] = df['MACD_Signal']
    if 'MACD_DIF' in df.columns and 'MACD_DEA' in df.columns:
        df['MACD_HIST'] = (df['MACD_DIF'] - df['MACD_DEA']) * 2  # 中国市场惯例

    # 布林带: BB_Upper/BB_Middle/BB_Lower → BOLL_UP/BOLL_MID/BOLL_DOWN
    if 'BB_Upper' in df.columns:
        df['BOLL_UP'] = df['BB_Upper']
    if 'BB_Middle' in df.columns:
        df['BOLL_MID'] = df['BB_Middle']
    if 'BB_Lower' in df.columns:
        df['BOLL_DOWN'] = df['BB_Lower']

    return df


@st.cache_data(ttl=7200, show_spinner=False)  # 2小时缓存
def get_stock_valuation(symbol: str, days: int = 250) -> Dict[str, Any]:
    """
    获取个股估值数据 (PE/PB/PS) 及历史分位

    Args:
        symbol: 股票代码
        days: 历史数据天数 (用于计算分位数，默认250个交易日≈1年)

    Returns:
        Dict with:
        - latest: 最新估值指标
        - percentile: 历史分位数 (0-100, 越低越便宜)
        - history: 历史数据 DataFrame
    """
    from quant.analysis.valuation.stock_valuation import StockValuationAnalyzer
    provider = get_provider()

    try:
        # 计算日期范围
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days*2)).strftime('%Y%m%d')

        # 使用封装好的接口获取每日基本面指标
        df = provider.get_daily_basic(symbol, start_date, end_date)

        # 委托给 StockValuationAnalyzer 计算分位数和状态
        return StockValuationAnalyzer.compute_percentile_valuation(df, days)

    except Exception as e:
        return {'error': str(e)}


# ==================== 行业数据 ====================

@st.cache_data(ttl=86400, show_spinner=False)  # 24小时缓存，历史日数据不会变
def get_industry_flow_daily(date_str: str) -> pd.DataFrame:
    """获取单日行业资金流向 (缓存24小时)"""
    provider = get_provider()
    return provider.get_industry_money_flow_dc(trade_date=date_str)


@st.cache_data(ttl=7200, show_spinner=False)  # 2小时缓存
def get_industry_flow_with_details(start: str, end: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    获取行业资金流向 (聚合 + 明细)
    返回: (aggregated_df, raw_daily_df)
    """
    days = get_trading_days(start, end)
    if not days:
        return pd.DataFrame(), pd.DataFrame()
    
    all_dfs = []
    for day in days:
        try:
            df = get_industry_flow_daily(day)
            if not df.empty and 'net_amount' in df.columns:
                df['net_amount'] = pd.to_numeric(df['net_amount'], errors='coerce')

                # 归一化机构/散户字段
                df = TushareProvider.normalize_flow_columns(df)

                cols = ['trade_date', 'name', 'net_amount', 'pct_change', 'institutional_net', 'retail_net']
                cols = [c for c in cols if c in df.columns]
                all_dfs.append(df[cols])
        except Exception:
            continue
    
    if not all_dfs:
        return pd.DataFrame(), pd.DataFrame()
    
    combined = pd.concat(all_dfs)
    
    if 'trade_date' in combined.columns:
        combined['trade_date'] = pd.to_datetime(combined['trade_date'])
    
    aggregated = combined.groupby('name').agg({'net_amount': 'sum', 'pct_change': 'mean'}).reset_index()
    return aggregated, combined


@st.cache_data(ttl=7200, show_spinner=False)  # 2小时缓存
def get_industry_list() -> List[str]:
    """获取所有行业名称列表"""
    today = get_latest_trading_day().strftime('%Y%m%d')
    df = get_industry_flow_daily(today)
    
    if df.empty:
        # 回溯查找
        start = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
        days = get_trading_days(start, today)
        if days:
            df = get_industry_flow_daily(days[-1])
    
    if not df.empty and 'name' in df.columns:
        return sorted(df['name'].unique().tolist())
    return []


@st.cache_data(ttl=86400, show_spinner=False)
def get_industry_constituent_stocks(industry_name: str) -> pd.DataFrame:
    """
    获取某个行业/概念板块的成分股列表
    
    Args:
        industry_name: 行业或概念板块名称
        
    Returns:
        包含成分股信息的 DataFrame (ts_code, name, industry等)
    """
    try:
        provider = get_provider()
        
        # 获取所有 A 股列表
        stock_basic = provider.get_stock_basic()
        
        if stock_basic.empty:
            return pd.DataFrame()
        
        # 按行业名称筛选
        # 注意: Tushare 中行业字段可能是 industry 或 cnspell
        result = pd.DataFrame()
        
        if 'industry' in stock_basic.columns:
            result = stock_basic[stock_basic['industry'] == industry_name]
        
        # 如果没有找到匹配的行业，可能是概念板块
        # Tushare 的概念板块需要单独调用 concept_detail 接口
        # 由于概念板块数据可能不全，我们返回空 DataFrame 并提示用户
        if result.empty:
            logger.warning(f"未找到行业 {industry_name} 的成分股，可能是概念板块")
            return pd.DataFrame()
        
        # 只返回需要的列
        cols = ['ts_code', 'name', 'industry']
        return result[[c for c in cols if c in result.columns]]
        
    except Exception as e:
        logger.error(f"获取行业成分股失败: {e}")
        return pd.DataFrame()


# ==================== 股票排名服务 ====================

@st.cache_resource
def get_stock_ranker():
    """获取 StockRanker 单例"""
    from quant.analysis.screener.ranker import StockRanker
    return StockRanker()


# ==================== 趋势强度分析服务 ====================

@st.cache_data(ttl=7200, show_spinner=False)  # 2小时缓存
def get_trend_strength(symbol: str, days: int = 90) -> Dict[str, Any]:
    """
    获取个股趋势强度评分
    
    基于四条均线规则计算趋势强度 (0-4分):
    1. 股价在20日均线上方 (+1分)
    2. 20日均线上行 (+1分)
    3. 60日均线上行 (+1分)
    4. 20日均线在60日均线上方 (+1分)
    
    Args:
        symbol: 股票代码
        days: 分析天数
    
    Returns:
        趋势强度分析结果
    """
    try:
        from quant.analysis.indicators.trend_strength_analyzer import TrendStrengthAnalyzer
        analyzer = TrendStrengthAnalyzer()
        return analyzer.analyze(symbol, days)
    except Exception as e:
        logger.error(f"获取趋势强度失败: {e}")
        return {'error': str(e)}


def get_trend_strength_from_price_data(price_df: pd.DataFrame, symbol: str = "unknown") -> Dict[str, Any]:
    """
    从价格数据计算趋势强度（用于行业指数等没有股票代码的场景）
    
    Args:
        price_df: 包含 close 列的价格数据
        symbol: 标识符（可选）
    
    Returns:
        趋势强度分析结果
    """
    try:
        from quant.analysis.indicators.trend_strength_analyzer import TrendStrengthAnalyzer
        analyzer = TrendStrengthAnalyzer()
        return analyzer.analyze_from_dataframe(price_df, symbol)
    except Exception as e:
        logger.error(f"计算趋势强度失败: {e}")
        return {'error': str(e)}


# ==================== 箱体突破分析服务 ====================

@st.cache_data(ttl=3600, show_spinner=False)  # 1小时缓存
def scan_box_breakouts(symbols: tuple, period: int = 20, days: int = 120,
                        volume_threshold: float = 1.5,
                        proximity_pct: float = 0.0,
                        max_workers: int = 10) -> List[Dict[str, Any]]:
    """
    批量扫描箱体突破信号（支持并发）

    Args:
        symbols: 标的代码元组（tuple 以支持 st.cache_data 哈希）
        period: 箱体计算周期
        days: 历史数据天数
        volume_threshold: 放量确认倍数阈值
        proximity_pct: 接近突破阈值（%），0 表示不启用
        max_workers: 并发线程数

    Returns:
        分析结果列表（按评分降序）
    """
    try:
        from quant.analysis.indicators.box_breakout_analyzer import BoxBreakoutAnalyzer
        analyzer = BoxBreakoutAnalyzer()
        return analyzer.scan_breakouts(
            list(symbols), period, days, volume_threshold,
            proximity_pct=proximity_pct, max_workers=max_workers,
        )
    except Exception as e:
        logger.error(f"批量扫描箱体突破失败: {e}")
        return []


@st.cache_data(ttl=86400, show_spinner=False)  # 24小时缓存
def load_all_ashare_stocks() -> pd.DataFrame:
    """
    加载全部 A 股上市公司列表

    Returns:
        DataFrame with columns: [symbol, name, industry]
    """
    provider = get_provider()
    df = provider.get_stock_basic()
    if df.empty:
        return pd.DataFrame(columns=['symbol', 'name', 'industry'])
    # 统一列名
    result = pd.DataFrame({
        'symbol': df['ts_code'],
        'name': df['name'],
        'industry': df.get('industry', ''),
    })
    return result


# ==================== 美股价值投资分析服务 ====================

@st.cache_data(ttl=86400, show_spinner=False)  # 24小时缓存，基本面变化慢
def get_value_investing_analysis(symbol: str) -> Dict[str, Any]:
    """
    获取单只美股的价值投资分析

    Args:
        symbol: 美股代码 (e.g. 'AAPL')

    Returns:
        价值投资分析结果
    """
    try:
        from quant.analysis.indicators.value_investing_analyzer import ValueInvestingAnalyzer
        analyzer = ValueInvestingAnalyzer()
        return analyzer.analyze(symbol)
    except Exception as e:
        logger.error(f"价值投资分析失败: {e}")
        return {'symbol': symbol, 'error': str(e)}


@st.cache_data(ttl=43200, show_spinner=False)  # 12小时缓存
def scan_value_stocks(symbols: tuple) -> List[Dict[str, Any]]:
    """
    批量扫描美股价值投资评分

    Args:
        symbols: 美股代码元组（tuple 以支持 st.cache_data 哈希）

    Returns:
        分析结果列表（按评分降序）
    """
    try:
        from quant.analysis.indicators.value_investing_analyzer import ValueInvestingAnalyzer
        analyzer = ValueInvestingAnalyzer()
        return analyzer.scan_value_stocks(list(symbols), max_workers=5)
    except Exception as e:
        logger.error(f"批量价值投资扫描失败: {e}")
        return []


# ==================== 宏观流动性分析服务 ====================

def get_macro_liquidity(lookback_days: int = 365, force_refresh: bool = False) -> Dict[str, Any]:
    """
    获取宏观流动性分析（cache-first 逐维度文件缓存）

    策略：先查缓存，未过期直接用；过期或不存在才发起网络请求。
    每个维度独立缓存，失败的维度用上次成功的缓存兜底。
    """
    from quant.analysis.indicators.macro_liquidity_analyzer import (
        MacroLiquidityAnalyzer, DIMENSION_WEIGHTS, STATUS_MAP, THRESHOLDS
    )
    from quant.data.cache_manager import get_cache_manager

    cache = get_cache_manager()
    CACHE_PROVIDER = 'macro_liquidity'
    CACHE_API_TYPE = 'dimension'
    CACHE_EXPIRY_HOURS = 12

    dimension_names = list(DIMENSION_WEIGHTS.keys())

    # Phase 1: Check cache for all dimensions
    dimensions = {}
    dims_to_fetch = []

    if not force_refresh:
        for dim_name in dimension_names:
            cached = cache.get(CACHE_PROVIDER, CACHE_API_TYPE, dim_name,
                               expiry_hours=CACHE_EXPIRY_HOURS,
                               lookback_days=lookback_days)
            if cached:
                cached['from_cache'] = True
                dimensions[dim_name] = cached
            else:
                dims_to_fetch.append(dim_name)
    else:
        dims_to_fetch = dimension_names

    # Phase 2: Always fetch from analyzer to get series data for charts.
    # Cached dimensions are used as fallback when fetch fails.
    # Reuse global USD liquidity cache to avoid duplicate FRED requests.
    liquidity_confidence = None
    liquidity_velocity = None
    liquidity_acceleration = None
    try:
        usd_liq = get_global_usd_liquidity()
        liquidity_confidence = usd_liq.get('confidence')
        liquidity_velocity = usd_liq.get('velocity')
        liquidity_acceleration = usd_liq.get('acceleration')
    except Exception:
        pass

    try:
        analyzer = MacroLiquidityAnalyzer()
        result = analyzer.analyze(
            lookback_days,
            liquidity_confidence=liquidity_confidence,
            liquidity_velocity=liquidity_velocity,
            liquidity_acceleration=liquidity_acceleration,
        )
    except Exception as e:
        logger.error(f"宏观流动性分析失败: {e}")
        if dimensions:
            # All cached, no series but at least show scores
            return _assemble_macro_result(dimensions, DIMENSION_WEIGHTS, STATUS_MAP,
                                          MacroLiquidityAnalyzer, THRESHOLDS)
        return {'error': str(e)}

    fetched_dims = result.get('dimensions', {})

    # Phase 3: Merge fetched results, cache successes, fallback on failures
    for dim_name in dimension_names:
        fetched = fetched_dims.get(dim_name)
        is_error = (fetched is None or
                    (isinstance(fetched, dict) and 'error' in fetched))

        if not is_error:
            # Fresh data — cache non-series fields
            cache_data = {k: v for k, v in fetched.items() if k != 'series'}
            cache.set(CACHE_PROVIDER, CACHE_API_TYPE, dim_name,
                      cache_data, lookback_days=lookback_days)
            dimensions[dim_name] = fetched
        elif dim_name in dimensions:
            # Fetch failed but have cache — keep cached scores, no series
            pass
        else:
            # Failed and no cache — use error result
            dimensions[dim_name] = fetched or {'error': '数据不可用', 'risk_score': 50}

    return _assemble_macro_result(dimensions, DIMENSION_WEIGHTS, STATUS_MAP,
                                  MacroLiquidityAnalyzer, THRESHOLDS)


def _assemble_macro_result(dimensions, weights, status_map, analyzer_cls, thresholds=None):
    """从维度数据组装最终结果（重算加权分、状态、信号）"""
    signals = []
    dimension_scores = {}

    for dim_name, dim_data in dimensions.items():
        if isinstance(dim_data, dict):
            dimension_scores[dim_name] = dim_data.get('risk_score', 50)
            signals.extend(dim_data.get('signals', []))

    total_risk_score = sum(
        dimension_scores.get(dim, 50) * weight
        for dim, weight in weights.items()
    )
    total_risk_score = round(total_risk_score, 1)

    status_en, status_cn, status_icon = 'Normal', '正常', '🟡'
    for threshold, en, cn, icon in status_map:
        if total_risk_score >= threshold:
            status_en, status_cn, status_icon = en, cn, icon
            break

    series = analyzer_cls._merge_series(dimensions)

    return {
        'status': status_en,
        'status_cn': status_cn,
        'status_icon': status_icon,
        'risk_score': total_risk_score,
        'dimensions': dimensions,
        'dimension_scores': dimension_scores,
        'signals': signals,
        'series': series,
        'thresholds': thresholds or {},
        'analyzed_at': datetime.now().isoformat(),
    }


# ==================== A股/港股市场信号服务 ====================

@st.cache_data(ttl=3600, show_spinner=False)  # 1小时缓存
def get_china_market_signals(lookback_days: int = 60) -> Dict[str, Any]:
    """
    获取 A 股/港股市场信号分析

    Args:
        lookback_days: 回溯天数

    Returns:
        市场信号分析结果
    """
    try:
        from quant.analysis.indicators.china_market_signal_analyzer import ChinaMarketSignalAnalyzer
        analyzer = ChinaMarketSignalAnalyzer()
        return analyzer.analyze(lookback_days)
    except Exception as e:
        logger.error(f"A股/港股市场信号分析失败: {e}")
        return {'error': str(e)}


# ==================== LLM 宏观流动性总结 ====================

@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_liquidity_summary(
    status_cn: str,
    risk_score: float,
    signals_text: str,
    dimension_scores_text: str,
) -> str:
    """调用 LLM 生成宏观流动性一句话总结（带建议和预测）"""
    import httpx
    import yaml
    import os
    import re

    # Load config
    config_path = Path(__file__).parent.parent / "config" / "dolphin.yaml"
    if not config_path.exists():
        return ""

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    default_model_key = config.get("default", "qwen-plus")
    llms = config.get("llms", {})
    clouds = config.get("clouds", {})
    model_config = llms.get(default_model_key, {})
    cloud_name = model_config.get("cloud", "aliyun")
    cloud_config = clouds.get(cloud_name, {})

    def expand_env(val):
        if not isinstance(val, str):
            return val
        return re.sub(r'\$\{(\w+)\}', lambda m: os.getenv(m.group(1), ""), val)

    api_base = expand_env(cloud_config.get("api", ""))
    api_key = expand_env(cloud_config.get("api_key", ""))
    model_name = model_config.get("model_name", default_model_key)

    if not api_key:
        return ""

    prompt = (
        f"你是专业的宏观投资顾问。基于以下宏观流动性监控数据，给出一段简洁的市场总结（2-3句话），必须包含：\n"
        f"1. 当前市场状态的核心判断\n"
        f"2. 具体的仓位建议（如\"建议降低权益仓位至6成\"）\n"
        f"3. 未来1-2周的预测和需要关注的风险点\n\n"
        f"当前状态: {status_cn}（风险评分 {risk_score}/100）\n"
        f"维度评分: {dimension_scores_text}\n"
        f"触发信号: {signals_text}\n\n"
        f"直接给出总结，不要分点，不要标题，不要客套。语气果断专业。"
    )

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"LLM summary generation failed: {e}")
        return ""


def get_global_usd_liquidity(
    display_days: int = 365,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    获取全球美元流动性置信度（带缓存）

    缓存策略：缓存完整分析结果（不含 series），12 小时过期。
    总是尝试获取最新数据，缓存作为 fallback。
    """
    from quant.analysis.indicators.global_usd_liquidity import (
        GlobalUsdLiquidityAnalyzer,
    )
    from quant.data.cache_manager import get_cache_manager

    cache = get_cache_manager()
    CACHE_PROVIDER = 'global_usd_liquidity'
    CACHE_API_TYPE = 'result'
    CACHE_SYMBOL = 'composite'
    CACHE_EXPIRY_HOURS = 12

    # Try to load cached result as fallback
    cached_result = None
    if not force_refresh:
        cached_result = cache.get(
            CACHE_PROVIDER, CACHE_API_TYPE, CACHE_SYMBOL,
            expiry_hours=CACHE_EXPIRY_HOURS,
        )

    # Always try fresh data (need series for charts)
    try:
        analyzer = GlobalUsdLiquidityAnalyzer()
        result = analyzer.analyze(display_days=display_days)

        # Cache non-series fields
        cache_data = {
            'confidence': result['confidence'],
            'wow_change': result['wow_change'],
            'velocity': result.get('velocity'),
            'acceleration': result.get('acceleration'),
            'inflection_points': result.get('inflection_points', []),
            'groups': {
                k: {kk: vv for kk, vv in v.items() if kk != 'indicators'}
                for k, v in result['groups'].items()
            },
            'indicators': {
                k: {kk: vv for kk, vv in v.items() if kk != 'series'}
                for k, v in result['indicators'].items()
            },
            'analyzed_at': result['analyzed_at'],
        }
        cache.set(CACHE_PROVIDER, CACHE_API_TYPE, CACHE_SYMBOL, cache_data)

        return result
    except Exception as e:
        logger.error(f"全球美元流动性分析失败: {e}")
        if cached_result:
            cached_result['from_cache'] = True
            return cached_result
        return {'error': str(e)}


@st.cache_data(ttl=14400, show_spinner=False)  # 4 hour cache — macro data is daily frequency
def get_leading_indicators(lookback_days: int = 365) -> Dict[str, Any]:
    """
    获取三个领先指标分析结果（VIX / 信用利差 / 融资余额）。
    数据层与分析层解耦：margin 数据从 TushareProvider 获取后传入 analyzer。
    """
    from quant.analysis.indicators.leading_indicators import LeadingIndicatorsAnalyzer

    analyzer = LeadingIndicatorsAnalyzer()

    # 获取融资融券数据（数据层）
    margin_df = None
    try:
        provider = get_provider()
        margin_df = provider.get_margin_data(lookback_days=90)
    except Exception as e:
        logger.warning(f"融资融券数据获取失败: {e}")

    # 分析（能力层）
    result = analyzer.analyze_all(margin_df=margin_df, lookback_days=lookback_days)

    # 过滤掉 series 数据（不能被 st.cache_data 序列化为 hashable）
    for key in result:
        if isinstance(result[key], dict):
            result[key].pop("series", None)
            delta = result[key].get("delta")
            if isinstance(delta, dict):
                delta.pop("velocity_series", None)

    return result


@st.cache_data(ttl=3600, show_spinner=False)
def get_dashboard_summary() -> Dict[str, Any]:
    """
    Aggregate dashboard data: macro status + watchlist alerts + top signals.
    Returns dict with keys: macro, watchlist_alerts, top_signals
    """
    summary = {}

    # 1. Macro status
    macro = {}
    try:
        usd_liq = get_global_usd_liquidity()
        macro['usd_liquidity'] = {
            'confidence': usd_liq.get('confidence'),
            'wow_change': usd_liq.get('wow_change'),
        }
    except Exception:
        macro['usd_liquidity'] = {'confidence': None}

    try:
        macro_liq = get_macro_liquidity(lookback_days=365)
        macro['macro_status'] = macro_liq.get('status', 'Unknown')
        macro['macro_score'] = macro_liq.get('weighted_score', 50)
    except Exception:
        macro['macro_status'] = 'Unknown'
        macro['macro_score'] = 50

    try:
        china = get_china_market_signals(lookback_days=60)
        macro['china_sentiment'] = china.get('status', 'Unknown')
    except Exception:
        macro['china_sentiment'] = 'Unknown'

    summary['macro'] = macro
    return summary


# ==================== Heuristic Verdict (pre-signal-framework) ====================

@st.cache_data(ttl=3600, show_spinner=False)
def get_heuristic_pool_verdict(pool: str) -> Dict[str, Any]:
    """
    Compute a heuristic verdict for an asset pool using existing analyzers.
    Temporary implementation — will be replaced by VerdictEngine.
    """
    from datetime import datetime
    result = {"pool": pool, "updated_at": datetime.now().strftime("%H:%M")}

    if pool == "a_shares":
        try:
            china = get_china_market_signals(lookback_days=60)
            status = china.get("status", "Unknown")
            risk_score = china.get("risk_score", 50)
            if status == "Defensive" or risk_score > 70:
                result.update(action="reduce", reasoning="A-share sentiment defensive, risk score high",
                             regime="risk-off", regime_icon="🔴")
            elif status == "Bullish" or risk_score < 30:
                result.update(action="add", reasoning="A-share sentiment bullish",
                             regime="risk-on", regime_icon="🟢")
            else:
                result.update(action="hold", reasoning=f"A-share sentiment {status}",
                             regime="transition", regime_icon="🟡")
        except Exception:
            result.update(action="hold", reasoning="data unavailable", regime="unknown", regime_icon="⚪")

    elif pool == "us_stocks":
        try:
            macro = get_macro_liquidity(lookback_days=365)
            status = macro.get("status", "Unknown")
            risk_score = macro.get("risk_score", 50)
            if status == "Abundant" or risk_score < 35:
                result.update(action="add", reasoning="macro liquidity abundant",
                             regime="expansion", regime_icon="🟢")
            elif status == "Crisis" or risk_score > 70:
                result.update(action="reduce", reasoning="macro liquidity crisis",
                             regime="contraction", regime_icon="🔴")
            else:
                result.update(action="hold", reasoning=f"macro liquidity {status}",
                             regime="transition", regime_icon="🟡")
        except Exception:
            result.update(action="hold", reasoning="data unavailable", regime="unknown", regime_icon="⚪")

    elif pool == "gold":
        try:
            usd = get_global_usd_liquidity()
            confidence = usd.get("confidence", 0)
            if confidence is not None and confidence < -10:
                result.update(action="add", reasoning="USD liquidity contracting — gold bullish",
                             regime="bullish", regime_icon="🟢")
            elif confidence is not None and confidence > 20:
                result.update(action="reduce", reasoning="USD liquidity expanding — gold headwind",
                             regime="bearish", regime_icon="🔴")
            else:
                result.update(action="hold", reasoning="USD liquidity neutral",
                             regime="neutral", regime_icon="🟡")
        except Exception:
            result.update(action="hold", reasoning="data unavailable", regime="unknown", regime_icon="⚪")

    elif pool == "commodities":
        try:
            macro = get_macro_liquidity(lookback_days=365)
            dimensions = macro.get("dimension_scores", {})
            copper_gold = dimensions.get("copper_gold", {}).get("score", 50)
            crude = dimensions.get("crude_oil", {}).get("score", 50)
            if copper_gold > 60 and crude > 60:
                result.update(action="add", reasoning="copper/gold + crude both bullish",
                             regime="reflation", regime_icon="🟢")
            elif copper_gold < 40 and crude < 40:
                result.update(action="reduce", reasoning="copper/gold + crude both weak",
                             regime="deflation", regime_icon="🔴")
            else:
                result.update(action="hold", reasoning="commodity signals mixed",
                             regime="neutral", regime_icon="🟡")
        except Exception:
            result.update(action="hold", reasoning="data unavailable", regime="unknown", regime_icon="⚪")

    return result


@st.cache_data(ttl=3600, show_spinner=False)
def get_all_pool_verdicts() -> Dict[str, Dict[str, Any]]:
    """Get heuristic verdicts for all four asset pools."""
    return {pool: get_heuristic_pool_verdict(pool) for pool in ("a_shares", "us_stocks", "gold", "commodities")}
