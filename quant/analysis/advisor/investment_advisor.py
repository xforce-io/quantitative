#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Investment Advisor Tool - Enhanced Version
提供投资标的的多策略分析和投资建议

Features:
- 支持A股、港股、美股及全球主要指数
- 多周期回测分析（3年、5年、10年）
- 实时信号分析与操作建议
- 策略组合优化与风险评估
- 性能优化与缓存机制
"""

import sys
import os
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
from functools import lru_cache
import warnings
warnings.filterwarnings('ignore')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from quant.analysis.strategy.strategy_comparator import StrategyComparison
from quant.analysis.indicators.capital_flow_analyzer import CapitalFlowAnalyzer
try:
    from analyst.etf_flow_simplified import SimplifiedETFFlowAnalyzer
except ImportError:
    SimplifiedETFFlowAnalyzer = None
from quant.data_providers.data_provider_factory import DataProviderFactory

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class SignalMetrics:
    """信号指标数据类"""
    date: datetime
    price: float
    ma_above_count: int = 0
    rsi: Optional[float] = None
    macd_positive: bool = False
    donchian_break: str = 'none'
    score: int = 0
    action: str = '观望'
    volume_ratio: Optional[float] = None
    volatility: Optional[float] = None
    trend_strength: Optional[float] = None


@dataclass
class StrategyResult:
    """策略回测结果数据类"""
    strategy_name: str
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    excess_return: float
    period: str = ''
    
    def to_dict(self) -> dict:
        return {
            'strategy': self.strategy_name,
            'total_return': f'{self.total_return:.2%}',
            'annual_return': f'{self.annual_return:.2%}',
            'max_drawdown': f'{self.max_drawdown:.2%}',
            'sharpe_ratio': f'{self.sharpe_ratio:.3f}',
            'win_rate': f'{self.win_rate:.2%}',
            'total_trades': str(self.total_trades),
            'excess_return': f'{self.excess_return:.2%}'
        }


try:
    from analyst.portfolios import portfolio_manager, SymbolInfo
except ImportError:
    # Fallback if portfolios module not available
    portfolio_manager = None
    from dataclasses import dataclass
    @dataclass
    class SymbolInfo:
        symbol: str
        name: str
        market: str
        sector: str

# 使用统一的 PortfolioManager 提供的组合定义
PORTFOLIOS = portfolio_manager.portfolios if portfolio_manager else {}


class InvestmentAdvisor:
    def __init__(self, symbols=None, use_cache=True, max_workers=4, portfolio='DEFAULT', data_provider='auto'):
        """
        初始化投资顾问
        
        Args:
            symbols: 要分析的标的列表
            use_cache: 是否使用缓存
            max_workers: 并行处理的最大线程数
            portfolio: 投资组合名称，必须在PORTFOLIOS中定义
        """
        # 根据指定的投资组合获取标的集合
        self.portfolio_name = portfolio
        if portfolio in PORTFOLIOS:
            self.portfolio_symbols = PORTFOLIOS[portfolio]
        else:
            logger.warning(f"未找到投资组合: {portfolio}。将仅使用传入的 symbols 进行分析。")
            self.portfolio_symbols = {}
        
        if symbols:
            # 如果提供了symbols，创建简单的SymbolInfo
            self.symbols = {}
            for i, symbol in enumerate(symbols):
                # 先从指定的投资组合中查找
                if symbol in self.portfolio_symbols:
                    self.symbols[symbol] = self.portfolio_symbols[symbol]
                # 都找不到则创建新的
                else:
                    self.symbols[symbol] = SymbolInfo(symbol, f'标的{i+1}', 'unknown', 'unknown')
        else:
            # 未提供symbols时使用选定的投资组合
            self.symbols = self.portfolio_symbols
            
        self.analysis_results = {}
        self.recommendations = {}
        self.use_cache = use_cache
        self.max_workers = max_workers
        self.cache_dir = project_root / 'cache' / 'analysis'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据提供者
        self.data_provider = None
        provider_name = data_provider.lower()
        
        if provider_name == 'auto':
            try:
                self.data_provider = DataProviderFactory.create('tushare', enableCache=use_cache)
                logger.info("成功初始化 Tushare 数据提供者")
            except Exception as e:
                logger.warning(f"无法初始化Tushare数据提供者: {e}")
                try:
                    self.data_provider = DataProviderFactory.create('yahoo', enableCache=use_cache)
                    logger.info("成功初始化 Yahoo 数据提供者")
                except Exception as e2:
                    logger.error(f"无法初始化任何数据提供者: {e2}")
        else:
            try:
                self.data_provider = DataProviderFactory.create(provider_name, enableCache=use_cache)
                logger.info(f"成功初始化 {provider_name} 数据提供者")
            except Exception as e:
                logger.error(f"无法初始化 {provider_name} 数据提供者: {e}")

        # 初始化资金流分析器（仅对A股）
        self.capital_flow_analyzer = None
        try:
            self.capital_flow_analyzer = CapitalFlowAnalyzer(use_cache=use_cache)
            logger.info("成功初始化资金流分析器")
        except Exception as e:
            logger.warning(f"无法初始化资金流分析器: {e}")
        
        # 初始化ETF资金流分析器
        self.etf_flow_analyzer = None
        if SimplifiedETFFlowAnalyzer:
            try:
                self.etf_flow_analyzer = SimplifiedETFFlowAnalyzer()
                logger.info("成功初始化ETF资金流分析器")
            except Exception as e:
                logger.warning(f"无法初始化ETF资金流分析器: {e}")
        else:
            logger.warning("SimplifiedETFFlowAnalyzer 模块不可用")

        # 🆕 初始化ETF估值分析器
        self.etf_valuation_analyzer = None
        try:
            from quant.analysis.etf_valuation_analyzer import ETFValuationAnalyzer
            self.etf_valuation_analyzer = ETFValuationAnalyzer()
            logger.info("✅ 成功初始化ETF估值分析器")
        except Exception as e:
            logger.warning(f"⚠️ 无法初始化ETF估值分析器: {e}")

    def _is_a_share_stock(self, symbol: str) -> bool:
        """检查是否为A股股票（支持资金流分析）"""
        return symbol.endswith('.SZ') or symbol.endswith('.SH')
    
    def _is_etf_or_fund(self, symbol: str) -> bool:
        """检查是否为ETF或基金（支持简化资金流分析）"""
        if not symbol:
            return False
        
        # ETF/基金常见代码前缀和后缀
        etf_prefixes = ['5', '15']  # ETF常见代码前缀
        fund_suffixes = ['.OF']     # 公募基金后缀
        etf_keywords = ['ETF', 'etf']
        
        # 检查代码前缀（ETF）
        for prefix in etf_prefixes:
            if symbol.startswith(prefix) and (symbol.endswith('.SH') or symbol.endswith('.SZ')):
                return True
        
        # 检查后缀（基金）
        for suffix in fund_suffixes:
            if symbol.endswith(suffix):
                return True
                
        # 检查关键词
        for keyword in etf_keywords:
            if keyword in symbol:
                return True
                
        return False

    def _discover_all_symbols(self) -> Dict[str, SymbolInfo]:
        """Discover all available symbols from config and local data.

        Priority:
        1) config/stocks/*.json filenames
        2) quant/data/tushare/* filenames
        3) include built-in default symbols (e.g., indices)
        """
        symbols: Dict[str, SymbolInfo] = {}

        # From config/stocks
        try:
            stocks_dir = project_root / 'config' / 'stocks'
            if stocks_dir.exists() and stocks_dir.is_dir():
                for f in stocks_dir.iterdir():
                    if f.is_file() and f.suffix.lower() == '.json':
                        sym = f.stem
                        if sym and sym not in symbols:
                            symbols[sym] = SymbolInfo(sym, sym, 'unknown', 'unknown')
        except Exception as e:
            logger.warning(f"Failed to discover from config/stocks: {e}")

        # From data/tushare (moved from quant/data/tushare)
        try:
            data_dir = project_root / 'data' / 'tushare'
            if data_dir.exists() and data_dir.is_dir():
                for f in data_dir.iterdir():
                    if not f.is_file():
                        continue
                    name = f.name
                    # Patterns:
                    #   002594.SZ_*.csv  -> 002594.SZ
                    #   600036.SH_*.csv  -> 600036.SH
                    #   index_000300.SH_*.csv -> 000300.SH
                    #   global_IXIC_*.csv -> IXIC
                    #   fund_518880.SH_*.csv -> 518880.SH
                    sym_candidate: Optional[str] = None
                    if name.startswith('global_'):
                        parts = name.split('_')
                        if len(parts) >= 3:
                            sym_candidate = parts[1]
                    elif name.startswith('index_'):
                        parts = name.split('_')
                        if len(parts) >= 2:
                            sym_candidate = parts[1]
                    elif name.startswith('fund_'):
                        parts = name.split('_')
                        if len(parts) >= 2:
                            # fund_518880.SH_*.csv -> 518880.SH
                            sym_candidate = parts[1]
                    else:
                        # take prefix before first underscore
                        if '_' in name:
                            candidate = name.split('_', 1)[0]
                            # 过滤掉无意义的候选符号
                            if candidate and candidate not in ['fund', 'index', 'global']:
                                sym_candidate = candidate
                    # strip extension artifacts and validate symbol
                    if sym_candidate:
                        # basic sanity: keep symbols like 000300.SH / 002594.SZ / IXIC
                        # 排除无效符号
                        if (sym_candidate != 'fund' and 
                            (('.' in sym_candidate and len(sym_candidate) > 3) or 
                             (sym_candidate.isalpha() and len(sym_candidate) >= 2)) and
                            sym_candidate not in symbols):
                            symbols[sym_candidate] = SymbolInfo(sym_candidate, sym_candidate, 'unknown', 'unknown')
        except Exception as e:
            logger.warning(f"Failed to discover from data/tushare: {e}")

        # Merge built-in defaults
        for sym, info in self.default_symbols.items():
            if sym not in symbols:
                symbols[sym] = info

        return symbols

    # ===== 新增：多周期回测与当前信号综合分析 =====
    def analyze_multi_period_and_current(self, symbols=None, periods=("3Y", "10Y"), current_days: int = 300):
        """
        按多周期（如3年、10年）进行回测，并结合最近数据给出当前操作建议。

        Args:
            symbols: 待分析标的（None=使用默认）
            periods: 周期列表，例如 ("3Y", "10Y")
            current_days: 最近数据天数用于当前信号分析
        """
        from datetime import datetime

        if symbols is None:
            symbols = list(self.symbols.keys())

        end_date_str = datetime.now().strftime('%Y-%m-%d')

        results = {}

        for symbol in symbols:
            name = self.symbols.get(symbol, symbol)
            print(f"\n{'='*80}")
            print(f"📌 标的: {name} ({symbol})")
            print(f"{'='*80}")
            symbol_results = { 'periods': {}, 'current': {} }

            # 多周期回测
            for period in periods:
                start_date_str = self._period_to_start_date_str(period)
                print(f"  🔄 回测周期: {period} | {start_date_str} ~ {end_date_str}")
                try:
                    comp = StrategyComparison(symbol=symbol, start_date=start_date_str, end_date=end_date_str)
                    # 为避免模拟网格干扰，跳过grid
                    comp.run_comparison(include_ma_analysis=False, skip_strategies={ 'grid' })
                    symbol_results['periods'][period] = comp.results
                except Exception as e:
                    print(f"  ❌ 回测失败: {e}")
                    symbol_results['periods'][period] = []

            # 当前信号
            try:
                current_signal = self._analyze_current_signal(symbol, days=current_days)
                symbol_results['current'] = current_signal
            except Exception as e:
                print(f"  ❌ 当前信号分析失败: {e}")
                symbol_results['current'] = {}

            # 生成综合策略与操作建议
            overall_strategy = self._synthesize_overall_strategy(symbol_results['periods'])
            action_advice = self._generate_action_advice(symbol_results['current'])

            results[symbol] = {
                'name': name,
                'period_results': symbol_results['periods'],
                'current_signal': symbol_results['current'],
                'overall_strategy': overall_strategy,
                'action_advice': action_advice,
            }

            # 简要输出
            print(f"  🧭 整体策略: {overall_strategy}")
            print(f"  🎯 当前建议: {action_advice}")

        return results

    def _period_to_start_date_str(self, period: str) -> str:
        """
        将周期字符串转换为开始日期
        
        Args:
            period: 周期字符串，如 '3Y', '5Y', '10Y', '1Y'
        
        Returns:
            开始日期字符串，格式为 YYYY-MM-DD
        """
        now = datetime.now()
        period_upper = period.upper().strip()
        
        if period_upper == '1Y':
            start = now - timedelta(days=1*365)
        elif period_upper == '3Y':
            start = now - timedelta(days=3*365)
        elif period_upper == '5Y':
            start = now - timedelta(days=5*365)
        elif period_upper == '10Y':
            start = now - timedelta(days=10*365)
        else:
            # 尝试解析更灵活的格式
            if period_upper.endswith('Y'):
                try:
                    years = int(period_upper[:-1])
                    start = now - timedelta(days=years*365)
                except ValueError:
                    raise ValueError(f"无法解析周期: {period}. 支持格式: 1Y, 3Y, 5Y, 10Y 等")
            else:
                raise ValueError(f"不支持的周期格式: {period}. 请使用如 '3Y', '5Y', '10Y' 等格式")
        
        return start.strftime('%Y-%m-%d')

    def _is_global_index(self, symbol: str) -> bool:
        symbol = symbol.upper()
        return (symbol.startswith('^') or 
                symbol in {'IXIC','NDX','NASDAQ','SPX','DJI','HSI','HKTECH','HSCEI'})
    
    def _is_domestic_index(self, symbol: str) -> bool:
        """检查是否为国内指数（A股指数）"""
        symbol = symbol.upper()
        # A股主要指数
        domestic_indices = {
            '000300.SH',  # 沪深300
            '000001.SH',  # 上证综指
            '399001.SZ',  # 深证成指
            '000016.SH',  # 上证50
            '399006.SZ',  # 创业板指
            '399005.SZ',  # 中小板指
        }
        return symbol in domestic_indices
    
    def _is_fund_or_etf(self, symbol: str) -> bool:
        """检查是否为基金或ETF"""
        # ETF通常以5开头，且在上海或深圳市场
        if symbol.startswith('5') and (symbol.endswith('.SH') or symbol.endswith('.SZ')):
            return True
        
        # 其他基金代码模式
        if symbol.startswith('1') and symbol.endswith('.SH'):  # 上海ETF
            return True
        if symbol.startswith('15') and symbol.endswith('.SZ'):  # 深圳ETF
            return True
        
        # 如果有数据提供者，直接查询
        try:
            if self.data_provider and hasattr(self.data_provider, 'isFundSymbol'):
                return self.data_provider.isFundSymbol(symbol)
        except:
            pass
        
        return False

    def _load_recent_data(self, symbol: str, days: int):
        """加载最近 days 天数据，自动识别全球指数/基金/股票。返回按日期升序的DataFrame。"""
        from datetime import datetime
        
        if not self.data_provider:
            raise ValueError("没有可用的数据提供者")
            
        provider = self.data_provider
        end = datetime.now()
        start = end - timedelta(days=days + 60)  # 多取一点保证指标可计算
        start_str = start.strftime('%Y%m%d')
        end_str = end.strftime('%Y%m%d')

        df = None
        data_type = "未知类型"
        
        try:
            if self._is_global_index(symbol):
                data_type = "全球指数"
                df = provider.getGlobalIndexData(symbol, start_str, end_str, 'D')
            elif self._is_domestic_index(symbol):
                data_type = "国内指数"
                # 使用专门的指数数据接口
                if hasattr(provider, 'getIndexData'):
                    df = provider.getIndexData(symbol, start_str, end_str, 'D')
                else:
                    # 回退到股票接口
                    print(f"⚠️  数据提供者不支持指数接口，尝试股票接口获取 {symbol}")
                    df = provider.getStockData(symbol, start_str, end_str, 'D')
            elif self._is_fund_or_etf(symbol):
                data_type = "基金/ETF"
                # 尝试使用基金数据接口
                if hasattr(provider, 'getFundData'):
                    df = provider.getFundData(symbol, start_str, end_str, 'D')
                else:
                    # 如果没有基金接口，作为股票数据获取
                    print(f"⚠️  数据提供者不支持基金接口，尝试股票接口获取 {symbol}")
                    df = provider.getStockData(symbol, start_str, end_str, 'D')
            else:
                data_type = "股票"
                df = provider.getStockData(symbol, start_str, end_str, 'D')
            
            if df is None or df.empty:
                raise ValueError(f"无法获取{symbol}({data_type})的近期数据")
            
            print(f"✅ 成功获取 {symbol}({data_type}) 数据，共 {len(df)} 条记录")
            return df.sort_index()
            
        except Exception as e:
            # 如果第一次尝试失败，尝试其他数据接口
            print(f"❌ 获取{symbol}({data_type})数据失败: {e}")
            
            # 改进的回退机制：逐步尝试不同的数据获取方式
            fallback_attempts = []
            
            # 为国内指数提供特殊的回退逻辑
            if self._is_domestic_index(symbol):
                fallback_attempts = [
                    ("getStockData", "股票接口"),
                    ("getIndexData", "指数接口(重试)"),
                    ("getFundData", "基金接口(备选)"),
                ]
            elif data_type == "基金/ETF":
                fallback_attempts = [
                    ("getStockData", "股票接口"),
                    ("getIndexData", "指数接口(备选)"),
                ]
            elif data_type == "全球指数":
                fallback_attempts = [
                    ("getStockData", "股票接口"),
                    ("getIndexData", "指数接口(备选)"),
                ]
            else:
                # 对于股票，也尝试其他接口
                fallback_attempts = [
                    ("getIndexData", "指数接口(备选)"),
                    ("getFundData", "基金接口(备选)"),
                ]
            
            for method_name, method_desc in fallback_attempts:
                if hasattr(provider, method_name):
                    try:
                        print(f"🔄 尝试使用{method_desc}获取 {symbol}")
                        method = getattr(provider, method_name)
                        df = method(symbol, start_str, end_str, 'D')
                        if df is not None and not df.empty:
                            print(f"✅ 使用{method_desc}成功获取 {symbol} 数据，共 {len(df)} 条记录")
                            return df.sort_index()
                    except Exception as fallback_e:
                        print(f"❌ {method_desc}也失败: {fallback_e}")
                        continue
            
            raise ValueError(f"无法通过任何方式获取{symbol}的数据，已尝试所有可用接口")

    def _is_valid_symbol(self, symbol: str) -> bool:
        """验证符号是否有效"""
        if not symbol or len(symbol) < 2:
            return False
        
        # 明确排除无效符号
        invalid_symbols = {'fund', 'index', 'global', 'test', 'demo', 'null', 'none', 'n/a'}
        if symbol.lower() in invalid_symbols:
            return False
            
        # 基本格式检查
        # A股格式: XXXXXX.SH / XXXXXX.SZ
        # 全球指数: 字母组合
        if ('.' in symbol and len(symbol) > 6) or (symbol.isalpha() and len(symbol) >= 2):
            return True
            
        return False
    
    def _analyze_canslim_ca(self, symbol: str, data: pd.DataFrame) -> dict:
        """
        威廉·欧奈尔CANSLIM分析中的C（Current Earnings）和A（Annual Earnings）
        
        C - Current Earnings: 当前季度盈利增长（>=25%同比增长）
        A - Annual Earnings: 年度盈利增长趋势（连续3年>=25%增长）
        
        注意: ETF和指数不适用CANSLIM评分，使用基于价格表现的替代评分
        
        Args:
            symbol: 股票代码
            data: 价格数据DataFrame
            
        Returns:
            威廉·欧奈尔CANSLIM分析结果字典
        """
        print(f"🐛 DEBUG: _analyze_canslim_ca called for {symbol}")
        
        # 检查是否为ETF或指数
        is_etf_or_index = (self._is_fund_or_etf(symbol) or 
                          self._is_global_index(symbol) or 
                          self._is_domestic_index(symbol))
        
        print(f"🐛 DEBUG: is_etf_or_index = {is_etf_or_index} for {symbol}")
        
        if is_etf_or_index:
            # ETF和指数使用基于价格表现的替代评分
            return self._analyze_etf_index_performance(symbol, data)
        
        # 股票的传统CANSLIM分析
        analysis_result = {
            'c_current_earnings': {'score': 0, 'description': '无法获取财务数据'},
            'a_annual_earnings': {'score': 0, 'description': '无法获取财务数据'},
            'total_score': 0,
            'overall_assessment': '基本面数据不足',
            'william_oneil_rating': 0,
            'canslim_signals': []
        }
        
        # 对于股票，尝试获取财务数据进行威廉·欧奈尔CANSLIM分析
        try:
            # 尝试获取财务数据
            financial_data = self._get_financial_data(symbol)
            print(f"🐛 DEBUG: financial_data is not None: {financial_data is not None}")
            if financial_data and financial_data.get('canslim_analysis'):
                # 使用威廉·欧奈尔方法的CANSLIM分析
                canslim_data = financial_data['canslim_analysis']
                print(f"🐛 DEBUG: canslim_data type: {type(canslim_data)}, is_none: {canslim_data is None}")
                
                if canslim_data is None:
                    print(f"🐛 DEBUG: canslim_data is None, fallback to price momentum proxy")
                    return self._analyze_price_momentum_proxy(symbol, data)
                
                # C - 当前季度盈利分析
                current_earnings_score = canslim_data.get('current_earnings_score', 0)
                print(f"🐛 DEBUG: current_earnings_score: {current_earnings_score}")
                
                detailed_analysis = canslim_data.get('detailed_analysis', {})
                print(f"🐛 DEBUG: detailed_analysis type: {type(detailed_analysis)}, is_none: {detailed_analysis is None}")
                
                if detailed_analysis is None:
                    print(f"🐛 DEBUG: detailed_analysis is None, using empty dict")
                    detailed_analysis = {}
                
                current_analysis = detailed_analysis.get('current', {})
                print(f"🐛 DEBUG: current_analysis type: {type(current_analysis)}, is_none: {current_analysis is None}")
                
                if current_analysis is None:
                    print(f"🐛 DEBUG: current_analysis is None, using empty dict")
                    current_analysis = {}
                    
                c_desc = current_analysis.get('reason', '当前季度盈利数据不可用')
                print(f"🐛 DEBUG: c_desc: {c_desc}")
                
                # A - 年度盈利趋势分析
                annual_earnings_score = canslim_data.get('annual_earnings_score', 0)
                print(f"🐛 DEBUG: annual_earnings_score: {annual_earnings_score}")
                
                # 重新获取 detailed_analysis 以确保不是缓存问题
                detailed_analysis_for_annual = canslim_data.get('detailed_analysis', {})
                print(f"🐛 DEBUG: detailed_analysis_for_annual type: {type(detailed_analysis_for_annual)}, is_none: {detailed_analysis_for_annual is None}")
                
                if detailed_analysis_for_annual is None:
                    print(f"🐛 DEBUG: detailed_analysis_for_annual is None, using empty dict")
                    detailed_analysis_for_annual = {}
                
                annual_analysis = detailed_analysis_for_annual.get('annual', {})
                print(f"🐛 DEBUG: annual_analysis type: {type(annual_analysis)}, is_none: {annual_analysis is None}")
                
                if annual_analysis is None:
                    print(f"🐛 DEBUG: annual_analysis is None, using empty dict")
                    annual_analysis = {}
                    
                a_desc = annual_analysis.get('reason', '年度盈利趋势数据不可用')
                print(f"🐛 DEBUG: a_desc: {a_desc}")
                
                # 威廉·欧奈尔综合评分
                oneil_rating = canslim_data.get('oneil_rating', 0)
                print(f"🐛 DEBUG: oneil_rating: {oneil_rating}")
                
                # 生成CANSLIM信号
                canslim_signals = []
                print(f"🐛 DEBUG: About to start CANSLIM signal generation")
                
                # C标准信号
                print(f"🐛 DEBUG: current_earnings_score: {current_earnings_score}, checking threshold 75...")
                if current_earnings_score >= 75:
                    print(f"🐛 DEBUG: C标准优秀分支 - current_analysis: {current_analysis}")
                    print(f"🐛 DEBUG: current_analysis.get('rating'): {current_analysis.get('rating') if current_analysis else 'current_analysis is None'}")
                    print(f"🐛 DEBUG: current_analysis.get('meets_oneil_standard'): {current_analysis.get('meets_oneil_standard') if current_analysis else 'current_analysis is None'}")
                    
                    canslim_signals.append({
                        'type': 'C_EXCELLENT',
                        'description': f'C标准优秀: {current_analysis.get("rating", "优秀") if current_analysis else "优秀"}',
                        'score': current_earnings_score,
                        'meets_oneil_standard': current_analysis.get('meets_oneil_standard', False) if current_analysis else False
                    })
                elif current_earnings_score >= 40:
                    print(f"🐛 DEBUG: C标准良好分支 - current_analysis: {current_analysis}")
                    canslim_signals.append({
                        'type': 'C_GOOD',
                        'description': f'C标准良好: {current_analysis.get("rating", "良好") if current_analysis else "良好"}',
                        'score': current_earnings_score
                    })
                else:
                    print(f"🐛 DEBUG: C标准较弱分支 - current_analysis: {current_analysis}")
                    canslim_signals.append({
                        'type': 'C_WEAK',
                        'description': f'C标准较弱: {current_analysis.get("rating", "较弱") if current_analysis else "较弱"}',
                        'score': current_earnings_score
                    })
                
                print(f"🐛 DEBUG: C标准信号处理完成，继续A标准...")
                
                # A标准信号
                print(f"🐛 DEBUG: annual_earnings_score: {annual_earnings_score}, checking threshold 75...")
                if annual_earnings_score >= 75:
                    print(f"🐛 DEBUG: A标准优秀分支 - annual_analysis: {annual_analysis}")
                    print(f"🐛 DEBUG: annual_analysis.get('rating'): {annual_analysis.get('rating') if annual_analysis else 'annual_analysis is None'}")
                    print(f"🐛 DEBUG: annual_analysis.get('meets_oneil_standard'): {annual_analysis.get('meets_oneil_standard') if annual_analysis else 'annual_analysis is None'}")
                    
                    canslim_signals.append({
                        'type': 'A_EXCELLENT',
                        'description': f'A标准优秀: {annual_analysis.get("rating", "优秀") if annual_analysis else "优秀"}',
                        'score': annual_earnings_score,
                        'meets_oneil_standard': annual_analysis.get('meets_oneil_standard', False) if annual_analysis else False
                    })
                elif annual_earnings_score >= 40:
                    print(f"🐛 DEBUG: A标准良好分支 - annual_analysis: {annual_analysis}")
                    canslim_signals.append({
                        'type': 'A_GOOD',
                        'description': f'A标准良好: {annual_analysis.get("rating", "良好") if annual_analysis else "良好"}',
                        'score': annual_earnings_score
                    })
                else:
                    print(f"🐛 DEBUG: A标准较弱分支 - annual_analysis: {annual_analysis}")
                    canslim_signals.append({
                        'type': 'A_WEAK',
                        'description': f'A标准较弱: {annual_analysis.get("rating", "较弱") if annual_analysis else "较弱"}',
                        'score': annual_earnings_score
                    })
                
                print(f"🐛 DEBUG: A标准信号处理完成，继续EPS加速...")
                
                # EPS加速信号
                print(f"🐛 DEBUG: Checking EPS acceleration...")
                eps_acceleration = canslim_data.get('eps_acceleration', False)
                print(f"🐛 DEBUG: eps_acceleration: {eps_acceleration}")
                
                if eps_acceleration:
                    print(f"🐛 DEBUG: Adding EPS_ACCELERATION signal")
                    canslim_signals.append({
                        'type': 'EPS_ACCELERATION',
                        'description': 'EPS增长加速: 符合威廉·欧奈尔增长加速理念',
                        'score': 85
                    })
                
                print(f"🐛 DEBUG: EPS加速信号处理完成，继续盈利质量...")
                
                # 盈利质量信号
                print(f"🐛 DEBUG: Checking earnings quality...")
                earnings_quality = canslim_data.get('earnings_quality', 'unknown')
                print(f"🐛 DEBUG: earnings_quality: {earnings_quality}")
                
                if earnings_quality in ['excellent', 'good']:
                    print(f"🐛 DEBUG: Adding HIGH_QUALITY_EARNINGS signal")
                    canslim_signals.append({
                        'type': 'HIGH_QUALITY_EARNINGS',
                        'description': f'盈利质量{earnings_quality}: 支持长期投资',
                        'score': 75 if earnings_quality == 'excellent' else 60
                    })
                else:
                    print(f"🐛 DEBUG: Skipping HIGH_QUALITY_EARNINGS signal, quality is {earnings_quality}")
                
                print(f"🐛 DEBUG: 盈利质量信号处理完成，开始更新分析结果...")
                print(f"🐛 DEBUG: canslim_signals length: {len(canslim_signals)}")
                print(f"🐛 DEBUG: canslim_signals content: {canslim_signals}")
                
                # 更新分析结果
                print(f"🐛 DEBUG: Updating analysis_result...")
                print(f"🐛 DEBUG: current_earnings_score: {current_earnings_score}")
                print(f"🐛 DEBUG: c_desc: {c_desc}")
                print(f"🐛 DEBUG: annual_earnings_score: {annual_earnings_score}")
                print(f"🐛 DEBUG: a_desc: {a_desc}")
                print(f"🐛 DEBUG: oneil_rating: {oneil_rating}")
                
                try:
                    analysis_result.update({
                        'c_current_earnings': {'score': current_earnings_score, 'description': c_desc},
                        'a_annual_earnings': {'score': annual_earnings_score, 'description': a_desc},
                        'total_score': current_earnings_score + annual_earnings_score,
                        'william_oneil_rating': oneil_rating,
                        'canslim_signals': canslim_signals
                    })
                    print(f"🐛 DEBUG: analysis_result.update() completed successfully")
                except Exception as update_e:
                    print(f"🐛 DEBUG: Error during analysis_result.update(): {update_e}")
                    raise update_e
                
                print(f"🐛 DEBUG: 开始威廉·欧奈尔标准综合评估...")
                
                # 威廉·欧奈尔标准综合评估
                print(f"🐛 DEBUG: oneil_rating for assessment: {oneil_rating}")
                try:
                    if oneil_rating >= 80:
                        analysis_result['overall_assessment'] = f'威廉·欧奈尔CANSLIM优秀({oneil_rating}/100): 完全符合成长股标准'
                        print(f"🐛 DEBUG: Set overall_assessment to excellent")
                    elif oneil_rating >= 60:
                        analysis_result['overall_assessment'] = f'威廉·欧奈尔CANSLIM良好({oneil_rating}/100): 基本符合成长股标准'
                        print(f"🐛 DEBUG: Set overall_assessment to good")
                    elif oneil_rating >= 40:
                        analysis_result['overall_assessment'] = f'威廉·欧奈尔CANSLIM一般({oneil_rating}/100): 部分符合成长股标准'
                        print(f"🐛 DEBUG: Set overall_assessment to fair")
                    else:
                        analysis_result['overall_assessment'] = f'威廉·欧奈尔CANSLIM较弱({oneil_rating}/100): 不符合成长股标准'
                        print(f"🐛 DEBUG: Set overall_assessment to weak")
                    
                    print(f"🐛 DEBUG: overall_assessment set successfully: {analysis_result.get('overall_assessment', 'NOT_SET')}")
                    print(f"🐛 DEBUG: About to return analysis_result: {type(analysis_result)}")
                    
                    # 检查 analysis_result 的完整性
                    print(f"🐛 DEBUG: Final analysis_result keys: {list(analysis_result.keys())}")
                    print(f"🐛 DEBUG: canslim_signals in result: {analysis_result.get('canslim_signals', 'NOT_FOUND')}")
                    
                    return analysis_result
                    
                except Exception as assessment_e:
                    print(f"🐛 DEBUG: Error during assessment: {assessment_e}")
                    raise assessment_e
                    
            elif financial_data is not None:
                print(f"🐛 DEBUG: 降级到传统 CANSLIM 分析...")
                # 降级到传统CANSLIM分析（只有当 financial_data 不是 None 时）
                c_score, c_desc = self._analyze_current_earnings(financial_data)
                a_score, a_desc = self._analyze_annual_earnings(financial_data)
                
                analysis_result['c_current_earnings'] = {'score': c_score, 'description': c_desc}
                analysis_result['a_annual_earnings'] = {'score': a_score, 'description': a_desc}
                analysis_result['total_score'] = c_score + a_score
                
                # 传统评估
                total_score = c_score + a_score
                if total_score >= 35:
                    analysis_result['overall_assessment'] = '传统CANSLIM优秀: 盈利强劲增长'
                elif total_score >= 20:
                    analysis_result['overall_assessment'] = '传统CANSLIM良好: 盈利稳定增长'
                elif total_score >= 0:
                    analysis_result['overall_assessment'] = '传统CANSLIM一般: 盈利增长平稳'
                else:
                    analysis_result['overall_assessment'] = '传统CANSLIM较弱: 盈利增长乏力'
            else:
                # 如果无法获取财务数据，使用价格趋势作为代理指标
                return self._analyze_price_momentum_proxy(symbol, data)
                
        except Exception as e:
            logger.warning(f"威廉·欧奈尔CANSLIM分析失败 {symbol}: {e}")
            # 降级到价格动量分析
            return self._analyze_price_momentum_proxy(symbol, data)
    
    def _analyze_etf_index_performance(self, symbol: str, data: pd.DataFrame) -> dict:
        """为ETF和指数提供基于价格表现的评分分析"""
        try:
            # 使用价格动量作为ETF/指数"基本面"评分的替代
            if len(data) < 60:
                return {
                    'c_current_earnings': {'score': 0, 'description': 'ETF/指数数据不足'},
                    'a_annual_earnings': {'score': 0, 'description': 'ETF/指数数据不足'},
                    'total_score': 0, 
                    'overall_assessment': 'ETF/指数数据不足',
                    'william_oneil_rating': 0,
                    'canslim_signals': []
                }
            
            # 近3个月表现(相当于"当前季度表现")
            recent_60d = data.tail(60)
            quarter_return = (recent_60d['close'].iloc[-1] / recent_60d['close'].iloc[0] - 1)
            
            # 近1年表现(相当于"年度表现")
            if len(data) >= 252:
                annual_data = data.tail(252)
                annual_return = (annual_data['close'].iloc[-1] / annual_data['close'].iloc[0] - 1)
            else:
                annual_return = quarter_return  # 数据不足时使用季度数据
            
            # C评分逻辑（短期表现）
            c_score = 0
            if quarter_return >= 0.15:
                c_score = 25
                c_desc = f'近季度ETF/指数上涨{quarter_return:.1%}，表现强劲'
            elif quarter_return >= 0.08:
                c_score = 15
                c_desc = f'近季度ETF/指数上涨{quarter_return:.1%}，表现良好'
            elif quarter_return >= 0.03:
                c_score = 10
                c_desc = f'近季度ETF/指数上涨{quarter_return:.1%}，涨幅平稳'
            elif quarter_return >= 0:
                c_score = 5
                c_desc = f'近季度ETF/指数上涨{quarter_return:.1%}，涨幅较小'
            else:
                c_score = -5
                c_desc = f'近季度ETF/指数下跌{abs(quarter_return):.1%}，表现较弱'
            
            # A评分逻辑（长期表现）  
            a_score = 0
            if annual_return >= 0.30:
                a_score = 25
                a_desc = f'近一年ETF/指数上涨{annual_return:.1%}，长期表现优异'
            elif annual_return >= 0.15:
                a_score = 20
                a_desc = f'近一年ETF/指数上涨{annual_return:.1%}，长期表现良好'
            elif annual_return >= 0.05:
                a_score = 15
                a_desc = f'近一年ETF/指数上涨{annual_return:.1%}，长期表现平稳'
            elif annual_return >= 0:
                a_score = 10
                a_desc = f'近一年ETF/指数上涨{annual_return:.1%}，长期涨幅较小'
            else:
                a_score = -5
                a_desc = f'近一年ETF/指数下跌{abs(annual_return):.1%}，长期表现较弱'
            
            total_score = c_score + a_score
            
            # 生成综合评价（注意：ETF不适用CANSLIM标准）
            if total_score >= 35:
                overall = f'ETF/指数强势：短期+长期表现优秀'
            elif total_score >= 20:
                overall = f'ETF/指数良好：整体表现稳健'
            elif total_score >= 5:
                overall = f'ETF/指数平稳：表现中性'
            else:
                overall = f'ETF/指数偏弱：需关注下行风险'
            
            return {
                'c_current_earnings': {'score': c_score, 'description': c_desc},
                'a_annual_earnings': {'score': a_score, 'description': a_desc},
                'total_score': total_score,
                'overall_assessment': overall,
                'william_oneil_rating': 0,  # ETF不适用威廉·欧奈尔标准
                'canslim_signals': []  # ETF不产生CANSLIM信号
            }
            
        except Exception as e:
            logger.warning(f"ETF/指数性能分析失败 {symbol}: {e}")
            return {
                'c_current_earnings': {'score': 0, 'description': 'ETF/指数分析失败'},
                'a_annual_earnings': {'score': 0, 'description': 'ETF/指数分析失败'},
                'total_score': 0, 
                'overall_assessment': 'ETF/指数分析失败',
                'william_oneil_rating': 0,
                'canslim_signals': []
            }
    
    def _get_financial_data(self, symbol: str) -> dict:
        """获取财务数据"""
        print(f"🐛 DEBUG: _get_financial_data called for {symbol}")
        try:
            if self.data_provider and hasattr(self.data_provider, 'getFinancialData'):
                financial_data = self.data_provider.getFinancialData(symbol)
                print(f"🐛 DEBUG: getFinancialData returned type: {type(financial_data)}, is_none: {financial_data is None}")
                if financial_data is not None:
                    print(f"🐛 DEBUG: financial_data keys: {list(financial_data.keys()) if isinstance(financial_data, dict) else 'Not a dict'}")
                return financial_data
            else:
                print(f"🐛 DEBUG: No data provider or getFinancialData method")
                return None
        except Exception as e:
            print(f"🐛 DEBUG: Exception in _get_financial_data: {e}")
            return None
    
    def _analyze_current_earnings(self, financial_data: dict) -> tuple:
        """分析当前季度盈利(C)"""
        try:
            # 假设financial_data包含季度盈利数据
            quarterly_earnings = financial_data.get('quarterly_earnings', [])
            if len(quarterly_earnings) >= 2:
                latest_quarter = quarterly_earnings[0]
                prev_quarter = quarterly_earnings[1]
                
                growth_rate = (latest_quarter - prev_quarter) / abs(prev_quarter) if prev_quarter != 0 else 0
                
                if growth_rate >= 0.25:  # 25%以上增长
                    return 25, f'当前季度盈利增长{growth_rate:.1%}，表现优秀'
                elif growth_rate >= 0.15:  # 15-25%增长
                    return 15, f'当前季度盈利增长{growth_rate:.1%}，表现良好'
                elif growth_rate >= 0.05:  # 5-15%增长
                    return 10, f'当前季度盈利增长{growth_rate:.1%}，增长平稳'
                elif growth_rate >= 0:  # 0-5%增长
                    return 5, f'当前季度盈利增长{growth_rate:.1%}，增长缓慢'
                else:  # 负增长
                    return -10, f'当前季度盈利下降{abs(growth_rate):.1%}，需要关注'
            else:
                return 0, '季度盈利数据不足'
                
        except Exception:
            return 0, '无法分析当前季度盈利'
    
    def _analyze_annual_earnings(self, financial_data: dict) -> tuple:
        """分析年度盈利趋势(A)"""
        try:
            # 假设financial_data包含年度盈利数据
            annual_earnings = financial_data.get('annual_earnings', [])
            if len(annual_earnings) >= 3:
                # 计算过去3年的复合增长率
                latest_year = annual_earnings[0]
                three_years_ago = annual_earnings[2]
                
                cagr = (latest_year / three_years_ago) ** (1/3) - 1 if three_years_ago > 0 else 0
                
                # 检查增长一致性
                consistent_growth = all(
                    annual_earnings[i] >= annual_earnings[i+1] 
                    for i in range(len(annual_earnings)-1)
                )
                
                base_score = 0
                if cagr >= 0.25:  # 25%以上复合增长
                    base_score = 25
                elif cagr >= 0.15:  # 15-25%复合增长
                    base_score = 20
                elif cagr >= 0.10:  # 10-15%复合增长
                    base_score = 15
                elif cagr >= 0.05:  # 5-10%复合增长
                    base_score = 10
                elif cagr >= 0:  # 0-5%复合增长
                    base_score = 5
                else:  # 负增长
                    base_score = -10
                
                # 一致性增长加分
                if consistent_growth and cagr > 0:
                    base_score += 5
                    description = f'年度盈利3年复合增长{cagr:.1%}，增长一致性好'
                else:
                    description = f'年度盈利3年复合增长{cagr:.1%}，增长不够一致'
                
                return base_score, description
            else:
                return 0, '年度盈利数据不足'
                
        except Exception:
            return 0, '无法分析年度盈利趋势'
    
    def _analyze_index_growth_proxy(self, symbol: str, data: pd.DataFrame) -> dict:
        """为指数提供增长代理分析"""
        try:
            # 使用价格动量作为指数"盈利"增长的代理
            if len(data) < 60:
                return {'c_current_earnings': {'score': 0, 'description': '数据不足'},
                       'a_annual_earnings': {'score': 0, 'description': '数据不足'},
                       'total_score': 0, 'overall_assessment': '指数数据不足'}
            
            # 近3个月表现(相当于"当前季度")
            recent_60d = data.tail(60)
            quarter_return = (recent_60d['close'].iloc[-1] / recent_60d['close'].iloc[0] - 1)
            
            # 近1年表现(相当于"年度")
            if len(data) >= 252:
                annual_data = data.tail(252)
                annual_return = (annual_data['close'].iloc[-1] / annual_data['close'].iloc[0] - 1)
            else:
                annual_return = quarter_return  # 数据不足时使用季度数据
            
            # 评分逻辑
            c_score = 0
            if quarter_return >= 0.15:
                c_score = 25
                c_desc = f'近季度指数上涨{quarter_return:.1%}，表现强劲'
            elif quarter_return >= 0.08:
                c_score = 15
                c_desc = f'近季度指数上涨{quarter_return:.1%}，表现良好'
            elif quarter_return >= 0.03:
                c_score = 10
                c_desc = f'近季度指数上涨{quarter_return:.1%}，涨幅平稳'
            elif quarter_return >= 0:
                c_score = 5
                c_desc = f'近季度指数上涨{quarter_return:.1%}，涨幅较小'
            else:
                c_score = -10
                c_desc = f'近季度指数下跌{abs(quarter_return):.1%}，表现较弱'
            
            a_score = 0
            if annual_return >= 0.20:
                a_score = 25
                a_desc = f'近一年指数上涨{annual_return:.1%}，长期表现优秀'
            elif annual_return >= 0.10:
                a_score = 20
                a_desc = f'近一年指数上涨{annual_return:.1%}，长期表现良好'
            elif annual_return >= 0.05:
                a_score = 10
                a_desc = f'近一年指数上涨{annual_return:.1%}，长期表现平稳'
            elif annual_return >= 0:
                a_score = 5
                a_desc = f'近一年指数上涨{annual_return:.1%}，长期涨幅较小'
            else:
                a_score = -10
                a_desc = f'近一年指数下跌{abs(annual_return):.1%}，长期表现较弱'
            
            total_score = c_score + a_score
            
            if total_score >= 35:
                overall = f'指数强势：短期+长期表现优秀'
            elif total_score >= 20:
                overall = f'指数良好：整体表现稳健'
            elif total_score >= 0:
                overall = f'指数平稳：表现中性'
            else:
                overall = f'指数偏弱：需关注下行风险'
            
            return {
                'c_current_earnings': {'score': c_score, 'description': c_desc},
                'a_annual_earnings': {'score': a_score, 'description': a_desc},
                'total_score': total_score,
                'overall_assessment': overall
            }
            
        except Exception as e:
            logger.warning(f"指数增长代理分析失败 {symbol}: {e}")
            return {'c_current_earnings': {'score': 0, 'description': '分析失败'},
                   'a_annual_earnings': {'score': 0, 'description': '分析失败'},
                   'total_score': 0, 'overall_assessment': '指数分析失败'}
    
    def _analyze_price_momentum_proxy(self, symbol: str, data: pd.DataFrame) -> dict:
        """使用价格动量作为盈利增长的代理分析"""
        print(f"🐛 DEBUG: _analyze_price_momentum_proxy called for {symbol}")
        try:
            if len(data) < 40:
                return {'c_current_earnings': {'score': 0, 'description': '数据不足'},
                       'a_annual_earnings': {'score': 0, 'description': '数据不足'},
                       'total_score': 0, 'overall_assessment': '价格数据不足'}
            
            # 使用20日和60日的价格动量作为短期"盈利"增长代理
            data_20d = data.tail(20)
            data_60d = data.tail(60)
            
            short_momentum = (data_20d['close'].iloc[-1] / data_20d['close'].iloc[0] - 1)
            medium_momentum = (data_60d['close'].iloc[-1] / data_60d['close'].iloc[0] - 1) if len(data_60d) >= 60 else short_momentum
            
            # 短期动量评分(相当于C)
            c_score = min(25, max(-15, int(short_momentum * 100)))  # 限制在-15到25之间
            c_desc = f'短期价格动量{short_momentum:.1%}（基本面数据不足，使用价格代理）'
            
            # 中期动量评分(相当于A)
            a_score = min(25, max(-15, int(medium_momentum * 80)))  # 限制在-15到25之间
            a_desc = f'中期价格动量{medium_momentum:.1%}（基本面数据不足，使用价格代理）'
            
            total_score = c_score + a_score
            
            if total_score >= 20:
                overall = '价格动量强劲（代理基本面分析）'
            elif total_score >= 0:
                overall = '价格动量平稳（代理基本面分析）'
            else:
                overall = '价格动量偏弱（代理基本面分析）'
                
            return {
                'c_current_earnings': {'score': c_score, 'description': c_desc},
                'a_annual_earnings': {'score': a_score, 'description': a_desc},
                'total_score': total_score,
                'overall_assessment': overall
            }
            
        except Exception as e:
            logger.warning(f"价格动量代理分析失败 {symbol}: {e}")
            return {'c_current_earnings': {'score': 0, 'description': '分析失败'},
                   'a_annual_earnings': {'score': 0, 'description': '分析失败'},
                   'total_score': 0, 'overall_assessment': '动量分析失败'}
    
    def _generate_technical_interpretation(self, ma_ok: int, rsi: float, macd_pos: bool, 
                                         up_break: bool, down_break: bool, latest_data) -> dict:
        """生成技术面详细解读"""
        interpretations = []
        
        # MA趋势分析
        if ma_ok == 3:
            ma_analysis = "🟢 多头排列完美：价格位于所有均线之上，趋势强劲"
            trend_strength = '强劲上升趋势'
        elif ma_ok == 2:
            ma_analysis = "🟡 多头优势：价格站上2条均线，趋势向好"
            trend_strength = '上升趋势'
        elif ma_ok == 1:
            ma_analysis = "🟠 中性偏多：仅站上1条均线，趋勿不明"
            trend_strength = '震荡整理'
        elif ma_ok == 0:
            ma_analysis = "🔴 多空焦灼：价格在所有均线之下，趋勿不明"
            trend_strength = '震荡整理'
        else:  # ma_ok < 0
            ma_analysis = "⚫ 空头优势：价格被均线压制，趋勿偏弱"
            trend_strength = '下降趋勿'
        
        interpretations.append(ma_analysis)
        
        # RSI动量分析
        if np.isfinite(rsi):
            if rsi >= 80:
                rsi_analysis = f"🔴 RSI过热（{rsi:.1f}）：严重超买，谨防回调风险"
                momentum_signal = '超买警告'
            elif rsi >= 70:
                rsi_analysis = f"🟠 RSI超买（{rsi:.1f}）：短期回调压力较大"
                momentum_signal = '超买区间'
            elif rsi >= 50:
                rsi_analysis = f"🟢 RSI中性偏多（{rsi:.1f}）：动量健康，上涨动能充足"
                momentum_signal = '多头动量'
            elif rsi >= 30:
                rsi_analysis = f"🟡 RSI中性偏空（{rsi:.1f}）：动量不足，需关注支撑"
                momentum_signal = '空头动量'
            elif rsi >= 20:
                rsi_analysis = f"🟠 RSI超卖（{rsi:.1f}）：出现反弹信号，可关注低吸机会"
                momentum_signal = '超卖区间'
            else:
                rsi_analysis = f"🔴 RSI过度超卖（{rsi:.1f}）：极端悲观，反弹信号强烈"
                momentum_signal = '超卖反弹'
        else:
            rsi_analysis = "⚪ RSI数据缺失：无法判断动量状态"
            momentum_signal = '数据不足'
        
        interpretations.append(rsi_analysis)
        
        # MACD信号分析
        if macd_pos:
            macd_analysis = "🟢 MACD多头信号：快线上穿慢线，中期趋势向好"
            macd_signal = '多头信号'
        else:
            macd_analysis = "🔴 MACD空头信号：快线位于慢线下方，中期趋勿偏弱"
            macd_signal = '空头信号'
        
        interpretations.append(macd_analysis)
        
        # 突破信号分析
        if up_break:
            breakout_analysis = "🚀 向上突破：突破前期高点，加速上行信号"
            breakout_signal = '上向突破'
        elif down_break:
            breakout_analysis = "📉 向下破位：跌破前期低点，加速下行信号"
            breakout_signal = '下向破位'
        else:
            breakout_analysis = "🟡 区间震荡：价格在通道内运行，等待突破方向"
            breakout_signal = '震荡整理'
        
        interpretations.append(breakout_analysis)
        
        return {
            'trend_strength': trend_strength,
            'momentum_signal': momentum_signal, 
            'macd_signal': macd_signal,
            'breakout_signal': breakout_signal,
            'detailed_analysis': interpretations,
            'summary': f'当前趋勿状态：{trend_strength}，{momentum_signal}，{macd_signal}，{breakout_signal}'
        }
    
    def _generate_comprehensive_analysis(self, technical_score: int, canslim_score: int, 
                                       combined_score: int, technical_interpretation: dict,
                                       canslim_analysis: dict, action: str) -> dict:
        """生成综合分析报告"""
        
        # 评分等级分析
        if technical_score >= 40:
            tech_grade = '优秀'
        elif technical_score >= 20:
            tech_grade = '良好'
        elif technical_score >= 0:
            tech_grade = '中性'
        elif technical_score >= -20:
            tech_grade = '较弱'
        else:
            tech_grade = '弱势'
            
        if canslim_score >= 30:
            fundamental_grade = '优秀'
        elif canslim_score >= 15:
            fundamental_grade = '良好'
        elif canslim_score >= 0:
            fundamental_grade = '中性'
        elif canslim_score >= -15:
            fundamental_grade = '较弱'
        else:
            fundamental_grade = '弱势'
        
        # 风险评估
        if combined_score >= 60:
            risk_level = '低风险'
            risk_desc = '技术+基本面双优，投资胜率较高'
        elif combined_score >= 40:
            risk_level = '低中风险'
            risk_desc = '整体信号积极，可适度加仓'
        elif combined_score >= 10:
            risk_level = '中等风险'
            risk_desc = '信号偏积极，可分批建仓'
        elif combined_score >= -10:
            risk_level = '中等风险'
            risk_desc = '信号不明显，建议观望为主'
        elif combined_score >= -40:
            risk_level = '中高风险'
            risk_desc = '信号偏弱，建议减仓防守'
        else:
            risk_level = '高风险'
            risk_desc = '多重负面信号，建议回避'
        
        # 操作建议解读
        action_reasoning = []
        
        if '强烈买入' in action:
            action_reasoning.append('🚀 双优信号：技术面与基本面均表现优异')
        elif '积极做多' in action:
            action_reasoning.append('🟢 积极信号：多数指标支持做多')
        elif '逢回调' in action:
            action_reasoning.append('🟡 谨慎乐观：有一定上涨动能，可等待低吸机会')
        elif '观望' in action:
            action_reasoning.append('🟠 中性策略：信号不明显，等待更明确方向')
        elif '减仓' in action:
            action_reasoning.append('🔴 防守姿态：多重负面信号，需要降低仓位')
        else:
            action_reasoning.append('⚫ 规避风险：信号明显偏空，保守为上')
        
        # 添加具体理由
        if technical_score > canslim_score:
            if technical_score > 20:
                action_reasoning.append(f'技术面优势显著（{technical_score}分），{technical_interpretation["summary"]}')
            if canslim_score < 10:
                action_reasoning.append(f'基本面表现一般（{canslim_score}分），{canslim_analysis.get("overall_assessment", "")}')
        elif canslim_score > technical_score:
            if canslim_score > 20:
                action_reasoning.append(f'基本面表现优秀（{canslim_score}分），{canslim_analysis.get("overall_assessment", "")}')
            if technical_score < 10:
                action_reasoning.append(f'技术面表现一般（{technical_score}分），{technical_interpretation["trend_strength"]}')
        else:
            action_reasoning.append(f'技术面与基本面表现较为一致（{technical_score}/{canslim_score}分）')
        
        return {
            'technical_grade': tech_grade,
            'fundamental_grade': fundamental_grade, 
            'risk_level': risk_level,
            'risk_description': risk_desc,
            'action_reasoning': action_reasoning,
            'key_factors': {
                'technical_highlights': technical_interpretation['detailed_analysis'][:2],
                'fundamental_highlights': [
                    canslim_analysis.get('c_current_earnings', {}).get('description', ''),
                    canslim_analysis.get('a_annual_earnings', {}).get('description', '')
                ][:2]
            },
            'overall_conclusion': f'综合评价：技术面{tech_grade}，基本面{fundamental_grade}，{risk_level}，{action}'
        }
    
    def _analyze_current_signal(self, symbol: str, days: int = 300) -> dict:
        """计算当下信号（MA/RSI/MACD/突破+CANSLIM），输出精简建议依据。"""
        # 验证符号
        if not self._is_valid_symbol(symbol):
            raise ValueError(f"无效的符号: {symbol}")
            
        import pandas as pd
        data = self._load_recent_data(symbol, days)

        # 计算关键技术指标
        data['MA20'] = data['close'].rolling(20).mean()
        data['EMA50'] = data['close'].ewm(span=50, adjust=False).mean()
        data['EMA200'] = data['close'].ewm(span=200, adjust=False).mean()

        delta = data['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        data['RSI'] = 100 - (100 / (1 + rs))

        ema12 = data['close'].ewm(span=12, adjust=False).mean()
        ema26 = data['close'].ewm(span=26, adjust=False).mean()
        data['MACD'] = ema12 - ema26
        data['MACD_Signal'] = data['MACD'].ewm(span=9, adjust=False).mean()

        data['Donchian_High'] = data['high'].rolling(20).max()
        data['Donchian_Low'] = data['low'].rolling(20).min()

        # CANSLIM分析
        canslim_analysis = self._analyze_canslim_ca(symbol, data)

        latest = data.iloc[-1]
        price = latest['close']
        ma_ok = int(price > latest.get('MA20', price)) + int(price > latest.get('EMA50', price)) + int(price > latest.get('EMA200', price))
        rsi = float(latest.get('RSI', np.nan))
        macd_pos = latest.get('MACD', 0) > latest.get('MACD_Signal', 0)
        up_break = latest.get('high', price) >= latest.get('Donchian_High', price)
        down_break = latest.get('low', price) <= latest.get('Donchian_Low', price)

        # 传统技术分析评分
        signal_score = 0
        signal_score += (ma_ok - 1) * 20  # -20, 0, +20, +40
        if np.isfinite(rsi):
            if rsi >= 70:
                signal_score -= 15
            elif rsi >= 50:
                signal_score += 10
            elif rsi <= 30:
                signal_score += 10
        signal_score += 20 if macd_pos else -10
        if up_break:
            signal_score += 20
        elif down_break:
            signal_score -= 20

        # 加入CANSLIM评分
        canslim_score = canslim_analysis.get('total_score', 0)

        # 资金流向分析增强（A股和ETF都支持）
        capital_flow_score = 0
        capital_flow_analysis = {}
        
        # 优先检查ETF/基金简化资金流分析
        if self.etf_flow_analyzer and self._is_etf_or_fund(symbol):
            try:
                # 使用已有数据进行ETF资金流分析
                etf_flow_result = self.etf_flow_analyzer.analyze_etf_flow_from_daily(data, symbol)
                capital_flow_analysis = etf_flow_result
                
                # 将ETF资金流分析转换为评分（相对保守的评分系统）
                if 'error' not in etf_flow_result:
                    comprehensive_score = etf_flow_result.get('comprehensive_score', 0)
                    
                    # ETF资金流评分转换（相比A股更保守）
                    if comprehensive_score >= 80:
                        capital_flow_score += 15  # 资金流入强劲
                    elif comprehensive_score >= 65:
                        capital_flow_score += 10  # 资金流入较好
                    elif comprehensive_score >= 50:
                        capital_flow_score += 5   # 资金流向中性
                    elif comprehensive_score >= 35:
                        capital_flow_score -= 5   # 资金流向偏弱
                    else:
                        capital_flow_score -= 10  # 资金流向疲弱
                    
                    # 根据成交量活跃度调整
                    volume_activity = etf_flow_result.get('volume_analysis', {}).get('activity_level', 'unknown')
                    if volume_activity == 'very_high':
                        capital_flow_score += 3
                    elif volume_activity == 'high':
                        capital_flow_score += 2
                    elif volume_activity == 'very_low':
                        capital_flow_score -= 2
                    
                    # 根据价量关系调整
                    pattern = etf_flow_result.get('price_volume_relation', {}).get('pattern', 'unknown')
                    if pattern == 'bullish':  # 上涨放量
                        capital_flow_score += 3
                    elif pattern == 'bearish':  # 下跌放量
                        capital_flow_score -= 3
                
            except Exception as e:
                logger.warning(f"ETF资金流分析失败 {symbol}: {e}")
                capital_flow_analysis = {'error': f'ETF分析失败: {str(e)}'}
        
        # A股传统资金流分析（非ETF的A股股票）
        elif self.capital_flow_analyzer and self._is_a_share_stock(symbol) and not self._is_etf_or_fund(symbol):
            try:
                flow_result = self.capital_flow_analyzer.analyze_stock_money_flow(symbol, days=20)
                capital_flow_analysis = flow_result

                # 将A股资金流分析转换为评分
                main_inflow_ratio = flow_result.get('main_inflow_ratio', 0)
                institutional_interest = flow_result.get('institutional_interest', 'unknown')
                flow_consistency = flow_result.get('flow_consistency', 0)

                if main_inflow_ratio is not None:
                    # 主力资金流入评分
                    if main_inflow_ratio > 0.05:
                        capital_flow_score += 25  # 大幅流入
                    elif main_inflow_ratio > 0.02:
                        capital_flow_score += 15  # 适度流入
                    elif main_inflow_ratio > -0.02:
                        capital_flow_score += 0   # 平衡
                    elif main_inflow_ratio > -0.05:
                        capital_flow_score -= 15  # 适度流出
                    else:
                        capital_flow_score -= 25  # 大幅流出

                    # 机构关注度加分
                    if institutional_interest == 'high':
                        capital_flow_score += 10
                    elif institutional_interest == 'medium':
                        capital_flow_score += 5

                    # 资金流向一致性加分
                    capital_flow_score += int(flow_consistency * 10)

            except Exception as e:
                logger.warning(f"资金流向分析失败 {symbol}: {e}")
                capital_flow_analysis = {'error': str(e)}

        # 🆕 ETF估值分析与评分调整
        valuation_score = 0
        valuation_analysis = {}

        if self._is_etf_or_fund(symbol) and self.etf_valuation_analyzer:
            try:
                # 使用ETF估值分析器
                percentile_analysis = self.etf_valuation_analyzer.calculate_price_percentile(data)
                mean_reversion = self.etf_valuation_analyzer.calculate_mean_reversion_signals(data)
                valuation_zone = self.etf_valuation_analyzer.calculate_valuation_zone(data)

                valuation_analysis = {
                    'percentile': percentile_analysis.get('overall_percentile', 50),
                    'valuation_level': percentile_analysis.get('overall_valuation', '合理'),
                    'mean_reversion_signal': mean_reversion.get('signal', '持有'),
                    'valuation_zone': valuation_zone.get('valuation_zone', '合理区'),
                    'bollinger_position': mean_reversion.get('bollinger_position', 50),
                    'detailed': {
                        'percentile_analysis': percentile_analysis,
                        'mean_reversion': mean_reversion,
                        'valuation_zone': valuation_zone
                    }
                }

                # 根据估值水平调整评分
                percentile = percentile_analysis.get('overall_percentile', 50)
                val_level = percentile_analysis.get('overall_valuation', '合理')

                # 估值评分逻辑（-50到+30）
                if percentile >= 95:
                    valuation_score = -50  # 极度高估，严重减分
                elif percentile >= 90:
                    valuation_score = -40  # 极度高估
                elif percentile >= 80:
                    valuation_score = -25  # 高估
                elif percentile >= 70:
                    valuation_score = -15  # 偏高
                elif percentile >= 60:
                    valuation_score = -5   # 略偏高
                elif percentile >= 40:
                    valuation_score = 0    # 合理
                elif percentile >= 30:
                    valuation_score = 10   # 偏低
                elif percentile >= 20:
                    valuation_score = 20   # 低估
                elif percentile >= 10:
                    valuation_score = 30   # 极度低估
                else:
                    valuation_score = 40   # 历史底部区域

                logger.info(f"📊 ETF估值分析 {symbol}: 分位数={percentile:.1f}%, 水平={val_level}, 评分={valuation_score}")

            except Exception as e:
                logger.warning(f"⚠️ ETF估值分析失败 {symbol}: {e}")
                valuation_analysis = {'error': str(e)}

        # 计算包含资金流和估值的综合评分
        combined_score = signal_score + canslim_score + capital_flow_score + valuation_score

        # 基于综合评分分类当前操作 - 修正为更严格的阈值
        # 同时考虑威廉·欧奈尔CANSLIM真实评分
        oneil_rating = canslim_analysis.get('william_oneil_rating', 0)
        
        # 真正的强烈买入需要同时满足：
        # 1. 综合评分很高 (>=120)
        # 2. 威廉·欧奈尔CANSLIM评分>=60 (基本符合成长股标准)
        if combined_score >= 120 and oneil_rating >= 60:
            action = "强烈买入/重仓（技术+基本面双优）"
        elif combined_score >= 100 and oneil_rating >= 40:
            action = "积极买入/加仓（技术面强+基本面一般）"
        elif combined_score >= 80:
            action = "适度买入/分批建仓"
        elif combined_score >= 60:
            action = "逢回调买入/持有"
        elif combined_score >= 40:
            action = "谨慎观望/小仓位试探"
        elif combined_score >= 10:
            action = "观望/持有，等待方向"
        elif combined_score > -10:
            action = "减仓/防守，等待止跌"
        else:
            action = "回避/清仓，等待反转"

        # 生成详细的技术面解读
        technical_interpretation = self._generate_technical_interpretation(
            ma_ok, rsi, macd_pos, up_break, down_break, latest
        )
        
        # 生成综合评估报告
        comprehensive_analysis = self._generate_comprehensive_analysis(
            signal_score, canslim_score, combined_score, technical_interpretation, 
            canslim_analysis, action
        )

        return {
            'date': data.index[-1],
            'price': float(price),
            'ma_above_count': int(ma_ok),
            'rsi': None if not np.isfinite(rsi) else float(rsi),
            'macd_positive': bool(macd_pos),
            'donchian_break': 'up' if up_break else ('down' if down_break else 'none'),
            'technical_score': int(signal_score),
            'canslim_score': int(canslim_score),
            'capital_flow_score': int(capital_flow_score),
            'valuation_score': int(valuation_score),  # 🆕 估值评分
            'combined_score': int(combined_score),
            'action': action,
            'canslim_analysis': canslim_analysis,
            'capital_flow_analysis': capital_flow_analysis,
            'valuation_analysis': valuation_analysis,  # 🆕 估值分析结果
            'is_etf': self._is_etf_or_fund(symbol),  # 🆕 标记是否为ETF
            'technical_interpretation': technical_interpretation,
            'comprehensive_analysis': comprehensive_analysis,
        }

    def _synthesize_overall_strategy(self, period_results: dict) -> str:
        """基于多周期回测结果，归纳适配的策略风格。"""
        def best_strategies(results):
            if not results:
                return []
            try:
                # 解析收益率字段，按收益排序
                sortable = [
                    (float(r.get('total_return', '0').replace('%','')), r.get('strategy',''))
                    for r in results if r.get('total_return') and r.get('total_return') != 'N/A'
                ]
                sortable.sort(reverse=True)
                return [s for _, s in sortable[:5]]
            except Exception:
                return []

        top_tags = []
        for period, results in period_results.items():
            tops = best_strategies(results)
            top_tags.extend(tops)

        if not top_tags:
            return "数据不足，建议持有或观望"

        joined = " ".join(top_tags)
        # 简单规则：统计最常见类型
        if '海龟' in joined:
            return "趋势突破型（海龟）优先，波动市更有效"
        if 'MA' in joined:
            # 识别是否偏慢速
            if any(tag for tag in top_tags if '10/100' in tag or '30/60' in tag or '20/50' in tag or '13/34' in tag or '8/21' in tag):
                return "中慢速MA趋势跟随优先，控制交易频率"
            return "MA趋势跟随有效，需调参适配波动"
        if '网格' in joined:
            return "震荡为主，网格策略稳健可作为底仓"
        if '动量' in joined:
            return "动量择时有一定效果，阈值需调优"
        return "多策略分散较好，建议组合配置"

    def _generate_action_advice(self, current_signal: dict) -> str:
        if not current_signal:
            return "当前数据不足，暂以持有/观望为主"
        
        # 使用综合评分
        combined_score = current_signal.get('combined_score', current_signal.get('score', 0))
        technical_score = current_signal.get('technical_score', 0)
        canslim_score = current_signal.get('canslim_score', 0)
        valuation_score = current_signal.get('valuation_score', 0)
        is_etf = current_signal.get('is_etf', False)

        action = current_signal.get('action', '观望')

        # 🆕 区分ETF和个股的显示
        if is_etf and valuation_score != 0:
            # ETF显示估值评分
            valuation_level = current_signal.get('valuation_analysis', {}).get('valuation_level', '合理')
            return f"{action}（综合评分 {combined_score}：技术 {technical_score}，估值 {valuation_score} [{valuation_level}]）"
        elif 'canslim_analysis' in current_signal:
            # 个股显示CANSLIM评分
            canslim_assessment = current_signal['canslim_analysis'].get('overall_assessment', '')
            return f"{action}（综合评分 {combined_score}：技术 {technical_score}，基本面 {canslim_score}，{canslim_assessment}）"
        else:
            return f"{action}（评分 {combined_score}）"

    def analyze_current_signals_only(self, symbols=None, current_days: int = 300):
        """
        仅进行当前信号分析，不进行多周期回测
        
        Args:
            symbols: 待分析标的（None=使用默认）
            current_days: 最近数据天数用于当前信号分析
        """
        if symbols is None:
            symbols = list(self.symbols.keys())
        
        print(f"🔍 当前信号分析 - 共 {len(symbols)} 个标的")
        print("="*80)
        
        results = {}
        
        for symbol in symbols:
            symbol_info = self.symbols.get(symbol, symbol)
            if hasattr(symbol_info, 'name'):
                display_name = symbol_info.name
            elif isinstance(symbol_info, dict) and 'name' in symbol_info:
                display_name = symbol_info['name']
            else:
                display_name = str(symbol_info)
                
            print(f"\n{'='*80}")
            print(f"📌 标的: {display_name} ({symbol})")
            print(f"{'='*80}")
            
            try:
                current_signal = self._analyze_current_signal(symbol, days=current_days)
                results[symbol] = {
                    'name': display_name,
                    'current_signal': current_signal,
                    'symbol_info': self.symbols.get(symbol),
                    'success': True
                }
                
                # 输出详细分析
                self._print_current_signal_analysis(symbol, display_name, current_signal)
                
            except Exception as e:
                print(f"❌ 当前信号分析失败: {e}")
                results[symbol] = {
                    'name': display_name,
                    'current_signal': {},
                    'error': str(e),
                    'success': False
                }
        
        print(f"\n{'='*100}")
        print("📋 当前信号分析总结")
        print(f"{'='*100}")
        
        # 汇总输出
        for symbol, data in results.items():
            if 'error' not in data and data.get('current_signal'):
                signal = data['current_signal']
                is_etf = signal.get('is_etf', False)
                print(f"\n{data['name']} ({symbol}):")
                print(f"  💰 价格: {signal.get('price', 0):.2f}")
                print(f"  🎯 建议: {signal.get('action', '观望')}")

                # 🆕 区分ETF和个股的评分显示
                if is_etf and signal.get('valuation_score', 0) != 0:
                    valuation_level = signal.get('valuation_analysis', {}).get('valuation_level', '合理')
                    print(f"  📈 综合评分: {signal.get('combined_score', 0)} "
                          f"(技术: {signal.get('technical_score', 0)}, "
                          f"估值: {signal.get('valuation_score', 0)} [{valuation_level}])")
                else:
                    print(f"  📈 综合评分: {signal.get('combined_score', 0)} "
                          f"(技术: {signal.get('technical_score', 0)}, "
                          f"基本面: {signal.get('canslim_score', 0)})")
                
                # 显示综合分析结论
                if 'comprehensive_analysis' in signal:
                    comp_analysis = signal['comprehensive_analysis']
                    print(f"  📊 {comp_analysis.get('overall_conclusion', '')}")
        
        return results
    
    def _print_current_signal_analysis(self, symbol: str, name: str, signal: dict):
        """打印当前信号的详细分析"""
        if not signal:
            print("❌ 无法获取信号数据")
            return
        
        # 基本信息
        print(f"📅 分析日期: {signal.get('date', 'N/A')}")
        print(f"💰 当前价格: {signal.get('price', 0):.2f}")
        
        # 技术面分析
        print(f"\n📈 技术面分析 (评分: {signal.get('technical_score', 0)})")
        print(f"{'-'*50}")
        
        tech_interp = signal.get('technical_interpretation', {})
        if tech_interp and 'detailed_analysis' in tech_interp:
            for analysis in tech_interp['detailed_analysis']:
                print(f"  {analysis}")
        
        # CANSLIM基本面分析
        print(f"\n📉 CANSLIM基本面分析 (评分: {signal.get('canslim_score', 0)})")
        print(f"{'-'*50}")
        
        canslim = signal.get('canslim_analysis', {})
        if canslim:
            c_info = canslim.get('c_current_earnings', {})
            a_info = canslim.get('a_annual_earnings', {})

            print(f"  🟢 C(当前盈利): {c_info.get('description', 'N/A')} (评分: {c_info.get('score', 0)})")
            print(f"  🟡 A(年度盈利): {a_info.get('description', 'N/A')} (评分: {a_info.get('score', 0)})")
            print(f"  📋 综合评价: {canslim.get('overall_assessment', 'N/A')}")

        # 🆕 ETF估值分析
        if signal.get('is_etf', False):
            valuation = signal.get('valuation_analysis', {})
            if valuation and 'error' not in valuation:
                print(f"\n💎 ETF估值分析 (评分: {signal.get('valuation_score', 0)})")
                print(f"{'-'*50}")
                print(f"  📊 价格分位数: {valuation.get('percentile', 50):.1f}%")
                print(f"  📈 估值水平: {valuation.get('valuation_level', '合理')}")
                print(f"  📍 估值区间: {valuation.get('valuation_zone', '合理区')}")
                print(f"  🔄 均值回归信号: {valuation.get('mean_reversion_signal', '持有')}")
                print(f"  📉 布林带位置: {valuation.get('bollinger_position', 50):.1f}%")

                # 估值风险提示
                percentile = valuation.get('percentile', 50)
                if percentile >= 90:
                    print(f"  ⚠️ 风险提示: 价格处于历史高位（{percentile:.1f}%分位），注意回调风险")
                elif percentile <= 10:
                    print(f"  💡 机会提示: 价格处于历史低位（{percentile:.1f}%分位），可能存在机会")

        # 综合分析
        print(f"\n🎯 综合分析 (综合评分: {signal.get('combined_score', 0)})")
        print(f"{'-'*50}")
        
        comp_analysis = signal.get('comprehensive_analysis', {})
        if comp_analysis:
            print(f"  📈 技术面等级: {comp_analysis.get('technical_grade', 'N/A')}")
            print(f"  📉 基本面等级: {comp_analysis.get('fundamental_grade', 'N/A')}")
            print(f"  ⚠️ 风险等级: {comp_analysis.get('risk_level', 'N/A')}")
            print(f"  📝 风险描述: {comp_analysis.get('risk_description', 'N/A')}")
            
            # 操作理由
            reasoning = comp_analysis.get('action_reasoning', [])
            if reasoning:
                print(f"  📝 操作理由:")
                for reason in reasoning:
                    print(f"    • {reason}")
        
        # 最终建议
        print(f"\n🎯 最终建议")
        print(f"{'-'*50}")
        print(f"  {signal.get('action', '观望')}")
        if comp_analysis:
            print(f"  📋 {comp_analysis.get('overall_conclusion', '')}")

    def analyze_all(self, parallel=True):
        """
        分析所有投资标的
        
        Args:
            parallel: 是否使用并行处理
        """
        print(f"🚀 开始分析 {len(self.symbols)} 个投资标的")
        print(f"⚙️  并行模式: {'启用' if parallel else '关闭'}")
        print("="*80)
        
        if parallel and self.max_workers > 1:
            self._analyze_all_parallel()
        else:
            self._analyze_all_sequential()
    
    def _analyze_all_sequential(self):
        """顺序分析所有标的"""
        for symbol, symbol_info in self.symbols.items():
            name = symbol_info.name if isinstance(symbol_info, SymbolInfo) else symbol_info
            print(f"\n📈 正在分析 {name} ({symbol})...")
            try:
                comparison = StrategyComparison(symbol=symbol)
                comparison.run_comparison(include_ma_analysis=True)
                self.analysis_results[symbol] = {
                    'name': name,
                    'results': comparison.results,
                    'benchmark_return': getattr(comparison, 'benchmark_return', 0),
                    'symbol_info': symbol_info if isinstance(symbol_info, SymbolInfo) else None
                }
                print(f"✅ {name} 分析完成")
            except Exception as e:
                logger.error(f"{name} 分析失败: {str(e)}")
                self.analysis_results[symbol] = {
                    'name': name,
                    'results': [],
                    'benchmark_return': 0,
                    'error': str(e)
                }
    
    def _analyze_all_parallel(self):
        """并行分析所有标的"""
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_symbol = {}
            
            # 提交所有任务
            for symbol, symbol_info in self.symbols.items():
                name = symbol_info.name if isinstance(symbol_info, SymbolInfo) else symbol_info
                future = executor.submit(self._analyze_single_symbol, symbol, name, symbol_info)
                future_to_symbol[future] = (symbol, name)
            
            # 处理完成的任务
            for future in as_completed(future_to_symbol):
                symbol, name = future_to_symbol[future]
                try:
                    result = future.result(timeout=60)  # 60秒超时
                    self.analysis_results[symbol] = result
                    print(f"✅ {name} 分析完成")
                except Exception as e:
                    logger.error(f"{name} 分析失败: {str(e)}")
                    self.analysis_results[symbol] = {
                        'name': name,
                        'results': [],
                        'benchmark_return': 0,
                        'error': str(e)
                    }
    
    def _analyze_single_symbol(self, symbol: str, name: str, symbol_info: Any) -> dict:
        """分析单个标的"""
        try:
            comparison = StrategyComparison(symbol=symbol)
            comparison.run_comparison(include_ma_analysis=True)
            return {
                'name': name,
                'results': comparison.results,
                'benchmark_return': getattr(comparison, 'benchmark_return', 0),
                'symbol_info': symbol_info if isinstance(symbol_info, SymbolInfo) else None
            }
        except Exception as e:
            raise Exception(f"分析失败: {str(e)}")

    def generate_recommendations(self):
        """生成投资建议"""
        print("\n" + "="*80)
        print("📊 投资标的综合分析报告")
        print("="*80)
        
        recommendations = []
        
        for symbol, data in self.analysis_results.items():
            if 'error' in data:
                continue
                
            name = data['name']
            results = data['results']
            benchmark_return = data.get('benchmark_return', 0)
            
            if not results:
                continue
            
            # 找出最佳策略（按总收益率）
            try:
                best_strategy = max(results, key=lambda x: self._parse_return(x.get('total_return', '0%')))
                best_return = self._parse_return(best_strategy.get('total_return', '0%'))
                
                # 找出风险调整后最佳策略（夏普比率）
                sharpe_strategies = [r for r in results if r.get('sharpe_ratio', 'N/A') != 'N/A']
                if sharpe_strategies:
                    best_sharpe_strategy = max(sharpe_strategies, key=lambda x: self._parse_sharpe(x.get('sharpe_ratio', '0')))
                else:
                    best_sharpe_strategy = best_strategy
                
                # 计算风险评级
                max_drawdown = self._parse_return(best_strategy.get('max_drawdown', '0%'))
                risk_level = self._assess_risk(max_drawdown, best_return)
                
                # 生成建议
                recommendation = self._generate_stock_recommendation(
                    symbol, name, best_strategy, best_sharpe_strategy, 
                    benchmark_return, risk_level
                )
                
                recommendations.append(recommendation)
                
            except Exception as e:
                print(f"❌ {name} 建议生成失败: {str(e)}")
        
        # 按收益率排序
        recommendations.sort(key=lambda x: x['expected_return'], reverse=True)
        
        # 输出建议
        self._print_recommendations(recommendations)
        
        return recommendations

    def _parse_return(self, return_str):
        """解析收益率字符串"""
        try:
            return float(return_str.replace('%', '')) / 100
        except:
            return 0
    
    def _parse_sharpe(self, sharpe_str):
        """解析夏普比率字符串"""
        try:
            return float(sharpe_str)
        except:
            return 0
    
    def _assess_risk(self, max_drawdown, expected_return):
        """评估风险等级"""
        if max_drawdown > 0.3:  # 最大回撤超过30%
            return "高风险"
        elif max_drawdown > 0.15:  # 最大回撤15-30%
            return "中风险"
        else:
            return "低风险"
    
    def _generate_stock_recommendation(self, symbol, name, best_strategy, best_sharpe_strategy, benchmark_return, risk_level):
        """为单个股票生成建议"""
        best_return = self._parse_return(best_strategy.get('total_return', '0%'))
        
        # 投资建议逻辑
        if best_return > benchmark_return * 1.2:  # 策略收益超过基准20%
            if risk_level == "低风险":
                advice = "强烈推荐"
                reason = "策略收益显著超过基准且风险可控"
            elif risk_level == "中风险":
                advice = "推荐"
                reason = "策略收益超过基准，风险适中"
            else:
                advice = "谨慎考虑"
                reason = "策略收益较高但风险较大"
        elif best_return > benchmark_return:
            if risk_level == "低风险":
                advice = "推荐"
                reason = "策略收益超过基准且风险较低"
            else:
                advice = "中性"
                reason = "策略收益略超基准但风险需关注"
        else:
            advice = "不推荐"
            reason = "策略收益未超过基准表现"
        
        return {
            'symbol': symbol,
            'name': name,
            'advice': advice,
            'reason': reason,
            'best_strategy': best_strategy['strategy'],
            'expected_return': best_return,
            'benchmark_return': benchmark_return,
            'risk_level': risk_level,
            'max_drawdown': best_strategy.get('max_drawdown', 'N/A'),
            'sharpe_ratio': best_sharpe_strategy.get('sharpe_ratio', 'N/A')
        }
    
    def _print_recommendations(self, recommendations):
        """打印投资建议"""
        print(f"\n📋 投资建议汇总 (分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        print("="*100)
        
        for i, rec in enumerate(recommendations, 1):
            print(f"\n{i}. {rec['name']} ({rec['symbol']})")
            print(f"   🎯 投资建议: {rec['advice']}")
            print(f"   📈 最佳策略: {rec['best_strategy']}")
            print(f"   💰 预期收益: {rec['expected_return']:.2%}")
            print(f"   📊 基准收益: {rec['benchmark_return']:.2%}")
            print(f"   ⚠️  风险等级: {rec['risk_level']}")
            print(f"   📉 最大回撤: {rec['max_drawdown']}")
            print(f"   📈 夏普比率: {rec['sharpe_ratio']}")
            print(f"   💡 建议理由: {rec['reason']}")
            print("   " + "-"*60)
        
        # 总结
        strong_buy = [r for r in recommendations if r['advice'] == '强烈推荐']
        buy = [r for r in recommendations if r['advice'] == '推荐']
        
        print(f"\n📈 总结:")
        if strong_buy:
            print(f"   🔥 强烈推荐: {', '.join([r['name'] for r in strong_buy])}")
        if buy:
            print(f"   ✅ 推荐: {', '.join([r['name'] for r in buy])}")
        
        print(f"\n⚠️  风险提示: 以上建议基于历史数据回测，实际投资需结合市场环境和个人风险承受能力。")

    def export_results_to_json(self, filepath: str = None) -> str:
        """
        导出分析结果到JSON文件
        
        Args:
            filepath: 输出文件路径，默认为results/investment_analysis_YYYYMMDD_HHMMSS.json
        
        Returns:
            实际保存的文件路径
        """
        if filepath is None:
            results_dir = project_root / 'results'
            results_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = results_dir / f'investment_analysis_{timestamp}.json'
        
        export_data = {
            'analysis_time': datetime.now().isoformat(),
            'symbols': {k: v.__dict__ if isinstance(v, SymbolInfo) else v for k, v in self.symbols.items()},
            'analysis_results': self.analysis_results,
            'recommendations': self.recommendations
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"分析结果已导出到: {filepath}")
        return str(filepath)
    
    def export_results_to_csv(self, filepath: str = None) -> str:
        """
        导出分析结果到CSV文件
        
        Args:
            filepath: 输出文件路径
        
        Returns:
            实际保存的文件路径
        """
        if filepath is None:
            results_dir = project_root / 'results'
            results_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = results_dir / f'investment_analysis_{timestamp}.csv'
        
        # 整理数据为DataFrame
        rows = []
        for symbol, data in self.analysis_results.items():
            if 'error' not in data:
                for result in data.get('results', []):
                    row = {
                        'symbol': symbol,
                        'name': data.get('name', ''),
                        'strategy': result.get('strategy', ''),
                        'total_return': result.get('total_return', ''),
                        'annual_return': result.get('annual_return', ''),
                        'max_drawdown': result.get('max_drawdown', ''),
                        'sharpe_ratio': result.get('sharpe_ratio', ''),
                        'win_rate': result.get('win_rate', ''),
                        'total_trades': result.get('total_trades', ''),
                        'excess_return': result.get('excess_return', '')
                    }
                    rows.append(row)
        
        if rows:
            df = pd.DataFrame(rows)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            logger.info(f"分析结果已导出到: {filepath}")
        else:
            logger.warning("没有可导出的结果")
        
        return str(filepath)
    
    def generate_report(self, format='text') -> str:
        """
        生成分析报告
        
        Args:
            format: 报告格式 ('text', 'markdown', 'html')
        
        Returns:
            报告内容
        """
        if format == 'markdown':
            return self._generate_markdown_report()
        elif format == 'html':
            return self._generate_html_report()
        else:
            return self._generate_text_report()
    
    def _generate_markdown_report(self) -> str:
        """生成Markdown格式报告"""
        report = []
        report.append(f"# 投资标的综合分析报告")
        report.append(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # 添加推荐汇总
        if hasattr(self, 'recommendations') and self.recommendations:
            report.append("## 📈 投资建议汇总\n")
            for rec in self.recommendations:
                report.append(f"### {rec['name']} ({rec['symbol']})")
                report.append(f"- **建议**: {rec['advice']}")
                report.append(f"- **最佳策略**: {rec['best_strategy']}")
                report.append(f"- **预期收益**: {rec['expected_return']:.2%}")
                report.append(f"- **风险等级**: {rec['risk_level']}")
                report.append(f"- **建议理由**: {rec['reason']}")
                report.append("")
        
        return "\n".join(report)
    
    def _generate_html_report(self) -> str:
        """生成HTML格式报告"""
        # 简化的HTML报告
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>投资分析报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                .strong-buy {{ color: #4CAF50; font-weight: bold; }}
                .buy {{ color: #8BC34A; }}
                .neutral {{ color: #FFC107; }}
                .sell {{ color: #F44336; }}
            </style>
        </head>
        <body>
            <h1>投资标的综合分析报告</h1>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        """
        
        if hasattr(self, 'recommendations') and self.recommendations:
            html += "<h2>投资建议</h2><table>"
            html += "<tr><th>标的</th><th>建议</th><th>最佳策略</th><th>预期收益</th><th>风险等级</th></tr>"
            
            for rec in self.recommendations:
                advice_class = ''
                if rec['advice'] == '强烈推荐':
                    advice_class = 'strong-buy'
                elif rec['advice'] == '推荐':
                    advice_class = 'buy'
                elif rec['advice'] == '中性':
                    advice_class = 'neutral'
                else:
                    advice_class = 'sell'
                
                html += f"""
                <tr>
                    <td>{rec['name']} ({rec['symbol']})</td>
                    <td class="{advice_class}">{rec['advice']}</td>
                    <td>{rec['best_strategy']}</td>
                    <td>{rec['expected_return']:.2%}</td>
                    <td>{rec['risk_level']}</td>
                </tr>
                """
            
            html += "</table>"
        
        html += "</body></html>"
        return html
    
    def _generate_text_report(self) -> str:
        """生成纯文本报告"""
        lines = []
        lines.append("="*80)
        lines.append("投资标的综合分析报告")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("="*80)
        
        if hasattr(self, 'recommendations') and self.recommendations:
            for rec in self.recommendations:
                lines.append(f"\n{rec['name']} ({rec['symbol']})")
                lines.append(f"  建议: {rec['advice']}")
                lines.append(f"  最佳策略: {rec['best_strategy']}")
                lines.append(f"  预期收益: {rec['expected_return']:.2%}")
                lines.append(f"  风险等级: {rec['risk_level']}")
                lines.append(f"  建议理由: {rec['reason']}")
        
        return "\n".join(lines)


def main():
    # 获取可用的投资组合列表
    available_portfolios = list(PORTFOLIOS.keys())
    
    parser = argparse.ArgumentParser(
        description='投资标的多策略分析和建议工具（支持A股、港股与全球主要指数）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f'''
使用示例:
  python analyst/investment_advisor.py                                # 分析DEFAULT投资组合
  python analyst/investment_advisor.py --portfolio BANK              # 分析银行投资组合
  python analyst/investment_advisor.py --symbols 300750.SZ 600036.SH  # 分析指定标的
  python analyst/investment_advisor.py --portfolio BANK --signal-only # 银行组合当前信号分析
  python analyst/investment_advisor.py --data-provider yahoo       # 使用Yahoo数据提供者
  python analyst/investment_advisor.py --advanced --periods 3Y,5Y,10Y # 多周期分析
  python analyst/investment_advisor.py --export json,csv              # 导出结果
  python analyst/investment_advisor.py --parallel --workers 8         # 并行分析

可用投资组合: {', '.join(available_portfolios)}
        '''
    )
    
    parser.add_argument('--portfolio', choices=available_portfolios, default='DEFAULT',
                       help=f'选择投资组合 (可选: {", ".join(available_portfolios)})，默认: DEFAULT')
    parser.add_argument('--symbols', nargs='*', 
                       help='指定要分析的股票代码（会覆盖投资组合设置）')
    parser.add_argument('--advanced', action='store_true',
                       help='启用多周期(3Y/10Y)+当前信号的综合分析')
    parser.add_argument('--periods', default='3Y,10Y',
                       help='多周期列表，逗号分隔（默认: 3Y,10Y）')
    parser.add_argument('--current-days', type=int, default=300,
                       help='当前信号分析使用的最近天数（默认: 300）')
    parser.add_argument('--export', 
                       help='导出格式: json, csv, html （可以用逗号分隔多个格式）')
    parser.add_argument('--parallel', action='store_true',
                       help='启用并行分析模式')
    parser.add_argument('--workers', type=int, default=4,
                       help='并行工作线程数（默认: 4）')
    parser.add_argument('--cache', action='store_true', default=True,
                       help='启用数据缓存（默认启用）')
    parser.add_argument('--no-cache', action='store_false', dest='cache',
                       help='禁用数据缓存')
    parser.add_argument('--signal-only', action='store_true',
                       help='仅进行当前信号分析，不进行回测')
    parser.add_argument('--data-provider', choices=['auto', 'tushare', 'yahoo'], default='auto',
                       help='选择数据提供者 (auto, tushare, yahoo), 默认: auto')
    
    args = parser.parse_args()
    
    # 创建分析器并设置投资组合
    print(f"\n📈 使用投资组合: {args.portfolio}")
    print(f"🔌 数据提供者: {args.data_provider}")
    
    # 创建自定义配置
    advisor_config = {
        'use_cache': args.cache,
        'max_workers': args.workers,
        'portfolio': args.portfolio,
        'data_provider': args.data_provider
    }
    advisor = InvestmentAdvisor(symbols=args.symbols, **advisor_config)

    if args.signal_only:
        # 仅进行当前信号分析
        target_symbols = args.symbols or list(advisor.symbols.keys())
        results = advisor.analyze_current_signals_only(
            symbols=target_symbols,
            current_days=args.current_days
        )
        return

    if args.advanced:
        # 多周期 + 当前信号综合分析
        # 未指定symbols时，使用全部可发现标的
        target_symbols = args.symbols or list(advisor.symbols.keys())
        periods = [p.strip() for p in args.periods.split(',') if p.strip()]
        results = advisor.analyze_multi_period_and_current(
            symbols=target_symbols,
            periods=periods,
            current_days=args.current_days
        )

        # 汇总输出
        print("\n" + "="*100)
        print("📋 综合结论（多周期+当前信号）")
        print("="*100)
        for symbol, res in results.items():
            print(f"\n{res['name']} ({symbol})")
            print(f"  🧭 整体策略: {res['overall_strategy']}")
            cur = res.get('current_signal', {})
            if cur:
                print(f"  ⏰ 当前: {cur.get('date').strftime('%Y-%m-%d')}  价格: {cur.get('price'):.2f}")
                print(f"  🎯 建议: {res['action_advice']}")
            else:
                print(f"  🎯 建议: {res['action_advice']}")
        return

    # 常规流程
    advisor.analyze_all(parallel=args.parallel)
    recommendations = advisor.generate_recommendations()
    
    # 处理导出
    if args.export:
        export_formats = [fmt.strip().lower() for fmt in args.export.split(',')]
        
        for fmt in export_formats:
            try:
                if fmt == 'json':
                    filepath = advisor.export_results_to_json()
                    print(f"✅ JSON结果已导出到: {filepath}")
                elif fmt == 'csv':
                    filepath = advisor.export_results_to_csv()
                    print(f"✅ CSV结果已导出到: {filepath}")
                elif fmt == 'html':
                    results_dir = project_root / 'results'
                    results_dir.mkdir(exist_ok=True)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filepath = results_dir / f'investment_report_{timestamp}.html'
                    
                    html_content = advisor.generate_report('html')
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    print(f"✅ HTML报告已导出到: {filepath}")
                elif fmt == 'markdown':
                    results_dir = project_root / 'results'
                    results_dir.mkdir(exist_ok=True)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filepath = results_dir / f'investment_report_{timestamp}.md'
                    
                    md_content = advisor.generate_report('markdown')
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(md_content)
                    print(f"✅ Markdown报告已导出到: {filepath}")
                else:
                    print(f"⚠️  未知的导出格式: {fmt}")
            except Exception as e:
                print(f"❌ 导出{fmt}格式失败: {e}")

if __name__ == "__main__":
    main()
