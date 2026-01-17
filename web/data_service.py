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


@st.cache_data(ttl=3600, show_spinner=False)
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

@st.cache_data(ttl=3600, show_spinner=False)
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


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_price(symbol: str, start: str, end: str) -> pd.DataFrame:
    """获取个股价格数据"""
    provider = get_provider()
    try:
        return provider.get_stock_data(symbol, start, end)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
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


@st.cache_data(ttl=3600, show_spinner=False)
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

@st.cache_data(ttl=86400, show_spinner=False)  # 24小时缓存，历史日数据不会变
def get_industry_flow_daily(date_str: str) -> pd.DataFrame:
    """获取单日行业资金流向 (缓存24小时)"""
    provider = get_provider()
    return provider.get_industry_money_flow_dc(trade_date=date_str)


@st.cache_data(ttl=3600, show_spinner=False)
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


@st.cache_data(ttl=3600, show_spinner=False)
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
                
                # 映射机构/散户字段 (优先使用 Provider 处理好的字段)
                # 映射机构/散户字段 (优先使用 Provider 处理好的字段)
                # 修复逻辑：即使 Provider 已计算了 institutional_net，如果算出来全是 0 (可能是明细缺失)，
                # 但存在 net_main_amount (主力净额)，则优先使用主力净额
                has_valid_inst = 'institutional_net' in df.columns and (df['institutional_net'] != 0).any()
                
                if not has_valid_inst:
                    if 'net_main_amount' in df.columns:
                        df['institutional_net'] = pd.to_numeric(df['net_main_amount'], errors='coerce')
                    elif 'main_net_amount' in df.columns:
                        df['institutional_net'] = pd.to_numeric(df['main_net_amount'], errors='coerce')
                    elif 'institutional_net' not in df.columns:
                        df['institutional_net'] = 0
                
                if 'retail_net' not in df.columns:
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


@st.cache_data(ttl=3600, show_spinner=False)
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

@st.cache_data(ttl=3600, show_spinner=False)
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
    将股票名称/简称解析为标准代码

    Args:
        query: 用户输入（可能是代码如 "002594.SZ" 或名称如 "比亚迪"）

    Returns:
        标准股票代码（如 "002594.SZ"），未找到则返回原值
    """
    query = query.strip()

    # 已是标准代码格式
    if '.' in query:
        suffix = query.split('.')[-1].upper()
        if suffix in ('SZ', 'SH', 'BJ', 'HK'):
            return query.upper()

    # 纯数字代码，补充后缀
    if query.isdigit() and len(query) == 6:
        if query.startswith('6'):
            return f"{query}.SH"
        elif query.startswith(('0', '3')):
            return f"{query}.SZ"
        elif query.startswith(('8', '4')):
            return f"{query}.BJ"

    # 从股票列表搜索名称
    try:
        stock_list = get_stock_list()  # ["000001.SZ 平安银行", ...]
        for item in stock_list:
            parts = item.split(' ', 1)
            if len(parts) == 2:
                code, name = parts
                # 精确匹配名称
                if query == name:
                    return code
        # 模糊匹配（名称包含查询词）
        for item in stock_list:
            parts = item.split(' ', 1)
            if len(parts) == 2:
                code, name = parts
                if query in name:
                    return code
    except Exception:
        pass

    return query  # 未找到则原样返回


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
        tech_df = get_stock_technical_data(resolved_symbol, start, end)
        if tech_df is not None and not tech_df.empty:
            latest = tech_df.iloc[-1]

            # 判断均线趋势
            ma_trend = "unknown"
            if 'MA5' in latest and 'MA20' in latest and 'MA60' in latest:
                if latest['MA5'] > latest['MA20'] > latest['MA60']:
                    ma_trend = "多头排列"
                elif latest['MA5'] < latest['MA20'] < latest['MA60']:
                    ma_trend = "空头排列"
                else:
                    ma_trend = "震荡整理"

            # 判断 MACD 信号
            macd_signal = "unknown"
            if 'MACD_DIF' in latest and 'MACD_DEA' in latest:
                if latest['MACD_DIF'] > latest['MACD_DEA']:
                    macd_signal = "金叉/多头"
                else:
                    macd_signal = "死叉/空头"

            result['technical'] = {
                'latest_close': round(float(latest.get('close', 0)), 2),
                'ma5': round(float(latest.get('MA5', 0)), 2) if pd.notna(latest.get('MA5')) else None,
                'ma20': round(float(latest.get('MA20', 0)), 2) if pd.notna(latest.get('MA20')) else None,
                'ma60': round(float(latest.get('MA60', 0)), 2) if pd.notna(latest.get('MA60')) else None,
                'ma_trend': ma_trend,
                'macd_signal': macd_signal,
                'rsi_value': round(float(latest.get('RSI', 50)), 1) if pd.notna(latest.get('RSI')) else None,
                'boll_position': _calc_boll_position(latest) if 'BOLL_UP' in latest else None,
            }
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
    """计算价格在布林带中的位置"""
    try:
        close = row.get('close', 0)
        up = row.get('BOLL_UP', 0)
        down = row.get('BOLL_DOWN', 0)
        mid = row.get('BOLL_MID', 0)

        if pd.isna(up) or pd.isna(down) or up == down:
            return "unknown"

        if close >= up:
            return "上轨之上（超买）"
        elif close <= down:
            return "下轨之下（超卖）"
        elif close > mid:
            return "中轨之上"
        else:
            return "中轨之下"
    except Exception:
        return "unknown"


# ==================== 趋势强度分析服务 ====================

@st.cache_data(ttl=3600, show_spinner=False)
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


@st.cache_data(ttl=3600, show_spinner=False)
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
