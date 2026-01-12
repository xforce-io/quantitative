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


@st.cache_data(ttl=3600)
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
        def format_symbol(code: str) -> str:
            code = str(code).strip()
            if '.' in code:
                return code
            if code.startswith('6'):
                return f"{code}.SH"
            elif code.startswith('0') or code.startswith('3'):
                return f"{code}.SZ"
            elif code.startswith('8') or code.startswith('4'):
                return f"{code}.BJ"
            return code
        
        df['symbol'] = df['symbol'].apply(format_symbol)
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

@st.cache_data(ttl=3600)
def get_trading_days(start: str, end: str) -> List[str]:
    """获取交易日列表"""
    provider = get_provider()
    return provider.get_trading_days(start, end)


def get_latest_trading_day() -> datetime:
    """获取最近的交易日 (智能回溯)"""
    today = datetime.now()
    
    # 周末自动回溯到周五
    if today.weekday() >= 5:
        today = today - timedelta(days=(today.weekday() - 4))
    # 盘前/盘中看前一天
    elif today.hour < 15:
        today = today - timedelta(days=1)
    
    return today


# ==================== 股票数据 ====================

@st.cache_data(ttl=86400)
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


@st.cache_data(ttl=86400)  # 24小时缓存
def get_stock_money_flow(symbol: str, start: str, end: str) -> Dict[str, Any]:
    """获取个股资金流向分析 (机构 vs 散户)"""
    provider = get_provider()
    return provider.analyze_institutional_vs_retail(symbol, start, end)


@st.cache_data(ttl=3600)
def get_stock_price(symbol: str, start: str, end: str) -> pd.DataFrame:
    """获取个股价格数据"""
    provider = get_provider()
    try:
        return provider.get_stock_data(symbol, start, end)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
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
    
    if df.empty:
        return df
    
    # 确保有必要的列
    if 'close' not in df.columns:
        return df
    
    # 计算均线
    df['MA5'] = df['close'].rolling(window=5).mean()
    df['MA10'] = df['close'].rolling(window=10).mean()
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA60'] = df['close'].rolling(window=60).mean()
    
    # 计算 MACD
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD_DIF'] = exp12 - exp26
    df['MACD_DEA'] = df['MACD_DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_HIST'] = (df['MACD_DIF'] - df['MACD_DEA']) * 2
    
    # 计算 RSI (14日)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 计算布林带
    df['BOLL_MID'] = df['close'].rolling(window=20).mean()
    df['BOLL_STD'] = df['close'].rolling(window=20).std()
    df['BOLL_UP'] = df['BOLL_MID'] + 2 * df['BOLL_STD']
    df['BOLL_DOWN'] = df['BOLL_MID'] - 2 * df['BOLL_STD']
    
    return df


@st.cache_data(ttl=3600)
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
    provider = get_provider()

    try:
        # 计算日期范围
        from datetime import datetime, timedelta
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days*2)).strftime('%Y%m%d')  # 扩大范围确保有足够交易日

        # 使用封装好的接口获取每日基本面指标
        df = provider.get_daily_basic(symbol, start_date, end_date)
        
        if df is None or df.empty:
            return {'error': '无估值数据'}
        
        # 排序
        df = df.sort_values('trade_date', ascending=True).reset_index(drop=True)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        # 只取最近 N 个交易日
        df = df.tail(days)
        
        if len(df) == 0:
            return {'error': '数据不足'}
        
        # 最新数据
        latest = df.iloc[-1].to_dict()
        
        # 计算历史分位数 (越低越便宜)
        percentile = {}
        for col in ['pe_ttm', 'pb', 'ps_ttm']:
            if col in df.columns:
                valid_data = df[col].dropna()
                if len(valid_data) > 10:
                    current = latest.get(col)
                    if pd.notna(current):
                        # 分位数: 当前值在历史中的位置 (0-100)
                        percentile[col] = round((valid_data < current).sum() / len(valid_data) * 100, 1)
        
        # 计算估值区间
        valuation_status = {}
        for col, pct in percentile.items():
            if pct < 20:
                valuation_status[col] = '低估'
            elif pct < 40:
                valuation_status[col] = '偏低'
            elif pct < 60:
                valuation_status[col] = '中性'
            elif pct < 80:
                valuation_status[col] = '偏高'
            else:
                valuation_status[col] = '高估'
        
        return {
            'latest': {
                'pe': latest.get('pe'),
                'pe_ttm': latest.get('pe_ttm'),
                'pb': latest.get('pb'),
                'ps': latest.get('ps'),
                'ps_ttm': latest.get('ps_ttm'),
                'dv_ratio': latest.get('dv_ratio'),  # 股息率
                'total_mv': latest.get('total_mv'),  # 总市值 (万元)
                'circ_mv': latest.get('circ_mv'),    # 流通市值 (万元)
                'close': latest.get('close'),
                'trade_date': latest.get('trade_date')
            },
            'percentile': percentile,
            'status': valuation_status,
            'history': df,
            'data_days': len(df)
        }
        
    except Exception as e:
        return {'error': str(e)}


# ==================== 行业数据 ====================

@st.cache_data(ttl=86400)  # 24小时缓存，历史日数据不会变
def get_industry_flow_daily(date_str: str) -> pd.DataFrame:
    """获取单日行业资金流向 (缓存24小时)"""
    provider = get_provider()
    return provider.get_industry_money_flow_dc(trade_date=date_str)


@st.cache_data(ttl=3600)
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


@st.cache_data(ttl=3600)
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
                
                # 映射机构/散户字段 (东财数据)
                if 'net_main_amount' in df.columns:
                    df['institutional_net'] = pd.to_numeric(df['net_main_amount'], errors='coerce')
                elif 'main_net_amount' in df.columns:
                    df['institutional_net'] = pd.to_numeric(df['main_net_amount'], errors='coerce')
                else:
                    df['institutional_net'] = 0
                
                if 'institutional_net' in df.columns:
                    df['retail_net'] = df['net_amount'] - df['institutional_net']
                else:
                    df['retail_net'] = 0
                
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


@st.cache_data(ttl=3600)
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


# ==================== 市场概览 ====================

@st.cache_data(ttl=3600)
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
        'short_term': {'name': '短线交易', 'desc': '重视资金流向和技术信号'},
        'balanced': {'name': '均衡配置', 'desc': '综合考虑各类因素'},
        'value': {'name': '价值投资', 'desc': '重视估值和基本面'},
        'trend': {'name': '趋势跟踪', 'desc': '跟随市场趋势'},
        'momentum': {'name': '资金驱动', 'desc': '跟随主力资金'},
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
