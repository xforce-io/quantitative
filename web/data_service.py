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
def get_stock_price(symbol: str, start: str, end: str) -> pd.DataFrame:
    """获取个股价格数据"""
    provider = get_provider()
    try:
        return provider.get_stock_data(symbol, start, end)
    except Exception:
        return pd.DataFrame()


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
def get_industry_flow_aggregated(start_date: str, end_date: str) -> pd.DataFrame:
    """
    获取聚合的行业资金流向 (多日汇总)
    返回: DataFrame with columns [name, net_amount, pct_change, ...]
    """
    days = get_trading_days(start_date, end_date)
    if not days:
        return pd.DataFrame()
    
    all_dfs = []
    for day in days:
        try:
            df = get_industry_flow_daily(day)
            if not df.empty and 'net_amount' in df.columns:
                df['net_amount'] = pd.to_numeric(df['net_amount'], errors='coerce')
                
                # 选取需要的列
                cols = ['name', 'net_amount', 'pct_change']
                if 'company_num' in df.columns:
                    cols.append('company_num')
                cols = [c for c in cols if c in df.columns]
                
                all_dfs.append(df[cols])
        except Exception:
            continue
    
    if not all_dfs:
        return pd.DataFrame()
    
    combined = pd.concat(all_dfs, ignore_index=True)
    
    agg_rules = {'net_amount': 'sum', 'pct_change': 'mean'}
    if 'company_num' in combined.columns:
        agg_rules['company_num'] = 'last'
    
    return combined.groupby('name').agg(agg_rules).reset_index()


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


# ==================== 市场概览 ====================

@st.cache_data(ttl=7200, show_spinner=False)  # 2小时缓存
def get_market_summary(date_str: str) -> Dict[str, Any]:
    """获取市场资金流向摘要"""
    provider = get_provider()
    return provider.get_market_money_flow_summary(date_str)


# ==================== 股票排名服务 ====================

@st.cache_resource
def get_stock_ranker():
    """获取 StockRanker 单例"""
    from quant.analysis.screener.ranker import StockRanker
    return StockRanker()


def get_ranking_profiles() -> Dict[str, Dict]:
    """获取可用的排名配置"""
    ranker = get_stock_ranker()

    # 配置的中文名称和描述
    profile_info = {
        'short_term': {'name': '短线交易', 'desc': '重视资金流向和趋势动量'},
        'balanced': {'name': '均衡配置', 'desc': '四因子均衡考虑'},
        'value': {'name': '价值投资', 'desc': '重视估值和基本面'},
        'trend': {'name': '趋势跟踪', 'desc': '趋势因子占50%权重'},
        'momentum': {'name': '资金驱动', 'desc': '资金流向+趋势动量'},
    }

    result = {}
    for name in ranker.get_available_profiles():
        weights = ranker.profiles.get(name, {})
        info = profile_info.get(name, {'name': name, 'desc': ''})
        result[name] = {
            'name': info['name'],
            'description': info['desc'],
            'weights': weights
        }
    return result


# 注意：rank_stocks 不再使用 Streamlit 缓存
# 因为底层 StockRanker._calculate_scores 已有当日有效的模块级缓存
# Streamlit 缓存反而会导致问题（如切换配置时无法更新权重）
def rank_stocks(symbols: List[str], profile: str = 'balanced', days: int = 60) -> pd.DataFrame:
    """
    对股票列表进行排名

    Args:
        symbols: 股票代码列表
        profile: 权重配置名称
        days: 分析数据天数

    Returns:
        排名结果 DataFrame
    """
    ranker = get_stock_ranker()
    return ranker.rank(symbols, profile=profile, days=days)


# ==================== AI 按需获取服务 ====================

def resolve_stock_symbol(query: str) -> str:
    """
    将股票名称/简称解析为标准代码 (委托给 SymbolResolver)

    Args:
        query: 用户输入（可能是代码如 "002594.SZ" 或名称如 "比亚迪"）

    Returns:
        标准股票代码（如 "002594.SZ"），未找到则返回原值
    """
    try:
        stock_list = get_stock_list()
    except Exception:
        stock_list = None
    return SymbolResolver.resolve(query, stock_list)


def fetch_stock_full_analysis(symbol: str, days: int = 60) -> Dict[str, Any]:
    """
    一次性获取股票完整分析数据（资金流 + 技术 + 估值）
    用于 AI 按需查询未在页面注册的股票

    Args:
        symbol: 股票代码（支持名称，会自动解析）
        days: 分析数据天数

    Returns:
        包含 money_flow, technical, valuation 三个维度的分析数据
    """
    # 解析股票代码
    resolved_symbol = resolve_stock_symbol(symbol)

    result = {
        "symbol": resolved_symbol,
        "query": symbol,
        "resolved": resolved_symbol != symbol,
        "fetch_time": datetime.now().isoformat(),
    }

    # 计算日期范围
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

    # 1. 资金流向
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

    # 2. 技术指标
    try:
        from quant.analysis.indicators.technical_analyzer import TechnicalAnalyzer
        tech_df = get_stock_technical_data(resolved_symbol, start, end)
        if tech_df is not None and not tech_df.empty:
            result['technical'] = TechnicalAnalyzer.interpret_latest_signals(tech_df)
    except Exception as e:
        result['technical'] = {'error': str(e)}

    # 3. 估值分析
    try:
        val = get_stock_valuation(resolved_symbol, days=250)
        if val and 'error' not in val:
            latest = val.get('latest', {})
            percentile = val.get('percentile', {})
            status = val.get('status', {})

            result['valuation'] = {
                'pe_ttm': round(float(latest.get('pe_ttm', 0)), 2) if latest.get('pe_ttm') else None,
                'pb': round(float(latest.get('pb', 0)), 2) if latest.get('pb') else None,
                'ps_ttm': round(float(latest.get('ps_ttm', 0)), 2) if latest.get('ps_ttm') else None,
                'dv_ratio': round(float(latest.get('dv_ratio', 0)), 2) if latest.get('dv_ratio') else None,
                'total_mv_yi': round(float(latest.get('total_mv', 0)) / 10000, 2) if latest.get('total_mv') else None,
                'pe_percentile': percentile.get('pe_ttm'),
                'pb_percentile': percentile.get('pb'),
                'pe_status': status.get('pe_ttm', ''),
                'pb_status': status.get('pb', ''),
            }
    except Exception as e:
        result['valuation'] = {'error': str(e)}

    # 检查是否有有效数据
    has_valid_data = any(
        key in result and 'error' not in result[key]
        for key in ['money_flow', 'technical', 'valuation']
    )

    if not has_valid_data:
        result['error'] = f"无法获取 {resolved_symbol} 的有效数据，请检查代码是否正确"

    return result


def _calc_boll_position(row) -> str:
    """计算价格在布林带中的位置 (委托给 TechnicalAnalyzer)"""
    from quant.analysis.indicators.technical_analyzer import TechnicalAnalyzer
    return TechnicalAnalyzer.bollinger_position(row)


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

@st.cache_data(ttl=7200, show_spinner=False)  # 2小时缓存
def get_box_breakout(symbol: str, period: int = 20, days: int = 120,
                      volume_threshold: float = 1.5) -> Dict[str, Any]:
    """
    获取单个标的的箱体突破分析

    Args:
        symbol: 股票代码
        period: 箱体计算周期（天）
        days: 历史数据天数
        volume_threshold: 放量确认倍数阈值

    Returns:
        箱体突破分析结果
    """
    try:
        from quant.analysis.indicators.box_breakout_analyzer import BoxBreakoutAnalyzer
        analyzer = BoxBreakoutAnalyzer()
        return analyzer.analyze(symbol, period, days, volume_threshold)
    except Exception as e:
        logger.error(f"获取箱体突破分析失败: {e}")
        return {'symbol': symbol, 'error': str(e)}


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


@st.cache_data(ttl=7200, show_spinner=False)  # 2小时缓存
def get_industry_trend_strength(industry_name: str, start: str, end: str) -> Dict[str, Any]:
    """
    获取行业趋势强度评分
    
    使用行业涨跌幅构建价格指数，然后计算趋势强度。
    
    Args:
        industry_name: 行业名称
        start: 开始日期 (YYYYMMDD)
        end: 结束日期 (YYYYMMDD)
    
    Returns:
        趋势强度分析结果
    """
    try:
        # 获取行业趋势数据
        _, trend_df = get_industry_flow_with_details(start, end)
        
        if trend_df.empty:
            return {'error': '无法获取行业数据'}
        
        # 筛选该行业
        industry_data = trend_df[trend_df['name'] == industry_name].copy()
        
        if industry_data.empty:
            return {'error': f'未找到行业 {industry_name} 的数据'}
        
        # 排序
        industry_data = industry_data.sort_values('trade_date')
        
        if len(industry_data) < 60:
            return {'error': f'数据不足，需要至少60个交易日（当前:{len(industry_data)}）'}
        
        # 使用涨跌幅构建价格指数
        if 'pct_change' in industry_data.columns:
            industry_data['close'] = (1 + industry_data['pct_change']/100).cumprod() * 100
        else:
            return {'error': '缺少涨跌幅数据'}
        
        # 计算趋势强度
        return get_trend_strength_from_price_data(industry_data, industry_name)
        
    except Exception as e:
        logger.error(f"获取行业趋势强度失败: {e}")
        return {'error': str(e)}


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

def get_macro_liquidity(lookback_days: int = 365) -> Dict[str, Any]:
    """
    获取宏观流动性分析（逐维度文件缓存）

    每个维度独立缓存。成功获取的数据写入文件缓存，
    失败的维度使用上次成功的缓存兜底。
    """
    from quant.analysis.indicators.macro_liquidity_analyzer import (
        MacroLiquidityAnalyzer, DIMENSION_WEIGHTS, STATUS_MAP
    )
    from quant.data.cache_manager import get_cache_manager

    cache = get_cache_manager()
    CACHE_PROVIDER = 'macro_liquidity'
    CACHE_API_TYPE = 'dimension'
    CACHE_EXPIRY_HOURS = 12

    try:
        analyzer = MacroLiquidityAnalyzer()
        result = analyzer.analyze(lookback_days)
    except Exception as e:
        logger.error(f"宏观流动性分析失败: {e}")
        return {'error': str(e)}

    dimensions = result.get('dimensions', {})
    signals = []
    any_live_data = False

    for dim_name, dim_data in dimensions.items():
        is_error = isinstance(dim_data, dict) and 'error' in dim_data

        if not is_error:
            # Success — cache it (strip series before caching, re-add after)
            cache_data = {k: v for k, v in dim_data.items() if k != 'series'}
            cache.set(CACHE_PROVIDER, CACHE_API_TYPE, dim_name,
                      cache_data, lookback_days=lookback_days)
            any_live_data = True
            signals.extend(dim_data.get('signals', []))
        else:
            # Failed — try cache fallback
            cached = cache.get(CACHE_PROVIDER, CACHE_API_TYPE, dim_name,
                               expiry_hours=CACHE_EXPIRY_HOURS,
                               lookback_days=lookback_days)
            if cached:
                cached['from_cache'] = True
                dimensions[dim_name] = cached
                signals.extend(cached.get('signals', []))
                logger.info(f"维度 {dim_name} 使用缓存兜底")
            else:
                signals.extend(dim_data.get('signals', []))

    # Recalculate weighted risk score with potentially updated dimensions
    dimension_scores = {}
    for dim_name, dim_data in dimensions.items():
        if isinstance(dim_data, dict):
            dimension_scores[dim_name] = dim_data.get('risk_score', 50)

    total_risk_score = sum(
        dimension_scores.get(dim, 50) * weight
        for dim, weight in DIMENSION_WEIGHTS.items()
    )
    total_risk_score = round(total_risk_score, 1)

    status_en, status_cn, status_icon = 'Normal', '正常', '🟡'
    for threshold, en, cn, icon in STATUS_MAP:
        if total_risk_score >= threshold:
            status_en, status_cn, status_icon = en, cn, icon
            break

    # Merge series from dimensions
    series = MacroLiquidityAnalyzer._merge_series(dimensions)

    return {
        'status': status_en,
        'status_cn': status_cn,
        'status_icon': status_icon,
        'risk_score': total_risk_score,
        'dimensions': dimensions,
        'dimension_scores': dimension_scores,
        'signals': signals,
        'series': series,
        'thresholds': result.get('thresholds', {}),
        'analyzed_at': result.get('analyzed_at', ''),
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


# ==================== ETF 排行服务 ====================

# ETF 分类映射（基于 ts_code 前缀 / 名称关键词）
_ETF_CATEGORY_KEYWORDS = {
    '宽基': ['沪深300', '中证500', '中证1000', '上证50', '创业板', '科创50', 'A50', '中证100', '红利'],
    '科技': ['芯片', '半导体', '5G', '通信', '人工智能', 'AI', '科技', '信息', '计算机', '软件', '传媒', '大数据', '云计算', '机器人'],
    '新能源': ['新能源', '光伏', '锂电', '电力', '电池', '风电', '储能', '电网', '碳中和'],
    '资源': ['黄金', '有色', '煤炭', '钢铁', '石油', '油气', '铜', '豆粕', '能源化工', '稀土'],
    '军工制造': ['军工', '航天', '航空', '国防', '船舶', '工业母机', '机械', '高端装备'],
    '消费医药': ['消费', '食品', '饮料', '白酒', '医药', '医疗', '生物', '创新药', '中药', '家电', '农业', '养殖'],
    '金融地产': ['银行', '证券', '保险', '金融', '房地产', '地产', '基建'],
    '海外': ['纳斯达克', '纳指', '标普', '恒生', '港股', '中概', '日经', '德国', '美国', '香港'],
}


def _classify_etf(name: str) -> str:
    """根据 ETF 名称推断分类"""
    for category, keywords in _ETF_CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in name:
                return category
    return '其他'


@st.cache_data(ttl=86400, show_spinner=False)
def get_etf_pool(source: str = "default", top_n: int = 50) -> pd.DataFrame:
    """
    获取 ETF 池

    Args:
        source: "default" 使用精选池(25只), "tushare" 从 Tushare 拉取热门 ETF
        top_n: Tushare 模式下取成交额 Top N

    Returns:
        DataFrame(columns=['ts_code', 'name', 'category'])
    """
    if source == "default":
        from quant.strategies.etf_rotation_strategy import DEFAULT_ETF_POOL
        rows = [
            {'ts_code': code, 'name': name, 'category': _classify_etf(name)}
            for code, name in DEFAULT_ETF_POOL.items()
        ]
        return pd.DataFrame(rows)

    # Tushare 模式：拉取全量 ETF 并按成交额过滤
    try:
        provider = get_provider()
        df_basic = provider.get_fund_basic(market='E', status='L')
        if df_basic is None or df_basic.empty:
            logger.warning("Tushare fund_basic 返回空数据，回退到默认池")
            return get_etf_pool(source="default")

        # 只取股票型 ETF（被动指数型 + 增强指数型）
        df_equity = df_basic[df_basic['fund_type'] == '股票型'].copy()
        if df_equity.empty:
            return get_etf_pool(source="default")

        # 获取最近交易日的成交额来筛选活跃 ETF
        from datetime import datetime, timedelta
        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')

        vol_records = []
        # 批量抽样检查成交额（取前 200 只按上市日期排序的）
        candidates = df_equity.sort_values('list_date').tail(500)  # 取最近上市的500只
        # 也要保留上市时间长的大基金
        old_funds = df_equity.sort_values('list_date').head(200)
        candidates = pd.concat([old_funds, candidates]).drop_duplicates(subset='ts_code')

        for ts_code in candidates['ts_code'].tolist():
            try:
                fund_df = provider.get_fund_data(ts_code, start, end)
                if fund_df is not None and not fund_df.empty and 'amount' in fund_df.columns:
                    avg_amount = fund_df['amount'].mean()
                    vol_records.append({'ts_code': ts_code, 'avg_amount': avg_amount})
            except Exception:
                continue

        if not vol_records:
            return get_etf_pool(source="default")

        df_vol = pd.DataFrame(vol_records).sort_values('avg_amount', ascending=False).head(top_n)

        # 合并名称
        df_result = df_vol.merge(df_equity[['ts_code', 'name']], on='ts_code', how='left')
        df_result['category'] = df_result['name'].apply(_classify_etf)
        return df_result[['ts_code', 'name', 'category']].reset_index(drop=True)

    except Exception as e:
        logger.error(f"Tushare ETF 池加载失败: {e}")
        return get_etf_pool(source="default")


@st.cache_data(ttl=600, show_spinner=False)
def rank_etfs(etf_pool: str = "default", top_n: int = 50) -> pd.DataFrame:
    """
    对 ETF 池进行轮动排名，返回带评分和信号的 DataFrame。

    Args:
        etf_pool: "default" 或 "tushare"
        top_n: Tushare 模式下的池大小

    Returns:
        DataFrame with columns: ts_code, name, category, ret_20d, ret_60d,
                                score, tier, signal, ret_20d_pct, ret_60d_pct
    """
    pool_df = get_etf_pool(source=etf_pool, top_n=top_n)
    if pool_df.empty:
        return pd.DataFrame()

    # 构建 etf_pool dict
    etf_dict = dict(zip(pool_df['ts_code'], pool_df['name']))
    category_map = dict(zip(pool_df['ts_code'], pool_df['category']))

    # 使用 ETFRotationStrategy 计算排名和信号
    from quant.strategies.etf_rotation_strategy import ETFRotationStrategy
    provider = get_provider()
    strategy = ETFRotationStrategy(provider, etf_pool=etf_dict, request_sleep=0.1)
    result = strategy.run()

    if result.ranking.empty:
        return pd.DataFrame()

    df = result.ranking.copy()
    df['category'] = df['ts_code'].map(category_map).fillna('其他')
    df['signal'] = df['ts_code'].map(result.signals).fillna('无明显信号')

    return df
