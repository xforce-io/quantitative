#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tushare Data Provider (New Architecture)
Tushare 数据提供者 (新架构)

This module wraps the existing TushareDataProvider with snake_case interface.
保持与旧接口的完全兼容性。
"""

import sys
import os

# Add parent path for importing old provider
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from quant.data_providers.data_provider import TushareDataProvider as _LegacyTushareProvider
from quant.data.base_provider import BaseDataProvider
from quant.core.logging_config import get_logger
from typing import Dict, Optional
import pandas as pd

logger = get_logger(__name__)


class TushareProvider(BaseDataProvider):
    """
    Tushare data provider for A-share stock data.
    
    This is a wrapper around the legacy TushareDataProvider that provides
    a snake_case interface while maintaining full backward compatibility.
    
    Features:
    - A-share daily/minute data
    - Index data (SSE, SZSE)
    - Fund/ETF data
    - Financial data (EPS, PE, PB, etc.)
    - Money flow data
    - Hong Kong stock data
    - Global index data
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize Tushare data provider.
        
        Args:
            config: Provider configuration, may include:
                - token: Tushare API token (or use TUSHARE_TOKEN env var)
                - dataPath: Cache directory path
                - cacheEnabled: Whether to enable caching (default True)
                - cacheExpiry: Cache expiry in seconds (default 3600)
        """
        super().__init__(config)
        # Delegate to legacy implementation
        self._legacy = _LegacyTushareProvider(config)
        self.pro = self._legacy.pro
    
    # ==================== 核心方法实现 ====================
    
    def get_stock_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        freq: str = 'D'
    ) -> pd.DataFrame:
        """
        Get stock OHLCV data from Tushare.
        
        Args:
            symbol: Stock symbol (e.g., '000001.SZ', '600036.SH', '00700.HK')
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            freq: Data frequency ('D' for daily)
            
        Returns:
            DataFrame with columns: [open, high, low, close, volume, amount, ...]
            Index: DatetimeIndex
        """
        return self._legacy.getStockData(symbol, start_date, end_date, freq)
    
    def get_stock_info(self, symbol: str) -> Dict:
        """Get basic stock information."""
        return self._legacy.getStockInfo(symbol)
    
    def validate_symbol(self, symbol: str) -> bool:
        """Validate if a symbol is valid for Tushare."""
        return self._legacy.validateSymbol(symbol)
    
    def format_symbol(self, symbol: str) -> str:
        """Format symbol to Tushare format."""
        return self._legacy.formatSymbol(symbol)
    
    def search_stock(self, keyword: str) -> pd.DataFrame:
        """Search for stocks by keyword."""
        return self._legacy.searchStock(keyword)
    
    # ==================== 扩展方法 ====================
    
    def get_index_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        freq: str = 'D'
    ) -> pd.DataFrame:
        """
        Get index data from Tushare.
        
        Args:
            symbol: Index symbol (e.g., '000300.SH', '399001.SZ')
        """
        return self._legacy.getIndexData(symbol, start_date, end_date, freq)
    
    def get_fund_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        freq: str = 'D'
    ) -> pd.DataFrame:
        """
        Get fund/ETF data from Tushare.
        
        Args:
            symbol: Fund/ETF symbol (e.g., '510330.SH', '518880.SH')
        """
        return self._legacy.getFundData(symbol, start_date, end_date, freq)
    
    def get_financial_data(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict:
        """
        Get financial data including EPS, PE, PB, etc.
        
        Returns:
            Dict with keys: eps_data, pe_data, pb_data, revenue_data, profit_data,
                           latest_eps, latest_pe, latest_pb, canslim_analysis, etc.
        """
        return self._legacy.getFinancialData(symbol, start_date, end_date)
    
    def get_global_index_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        freq: str = 'D'
    ) -> pd.DataFrame:
        """
        Get global index data from Tushare.
        
        Args:
            symbol: Global index symbol (e.g., 'IXIC', 'SPX', 'DJI')
        """
        return self._legacy.getGlobalIndexData(symbol, start_date, end_date, freq)
    
    def get_money_flow(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Get individual stock money flow data.
        
        Args:
            symbol: Stock symbol (e.g., '000001.SZ')
        """
        return self._legacy.getMoneyFlow(symbol, start_date, end_date)
    
    def get_hsgt_flow(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Get HSGT (Hong Kong-Shanghai-Shenzhen Stock Connect) capital flow data."""
        return self._legacy.getHSGTFlow(start_date, end_date)
    
    def get_hsgt_top10(self, trade_date: str, market: str = 'SH') -> pd.DataFrame:
        """Get HSGT top 10 traded stocks for a specific date."""
        return self._legacy.getHSGTTop10(trade_date, market)
    
    def get_stock_list(
        self,
        exchange: str = '',
        list_status: str = 'L',
        fields: str = 'ts_code,symbol,name,area,industry,list_date,market'
    ) -> pd.DataFrame:
        """Get all listed companies."""
        return self._legacy.getStockList(exchange, list_status, fields)
    
    def get_fund_basic(self, market: str = 'E', status: str = 'L') -> pd.DataFrame:
        """Get fund basic information."""
        return self._legacy.getFundBasic(market, status)
    
    def get_income_data(
        self,
        period: str,
        fields: str = 'ts_code,ann_date,f_ann_date,end_date,report_type,basic_eps,diluted_eps,total_revenue,revenue,n_income'
    ) -> pd.DataFrame:
        """Get income statement data for a specific period."""
        return self._legacy.getIncomeData(period, fields)
    
    def get_enhanced_stock_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        freq: str = 'D',
        include_financials: bool = True
    ) -> Dict:
        """
        Get enhanced stock data including technical indicators and financial data.
        
        Returns:
            Dict with keys: price_data, symbol, volume_stats, financial_data
        """
        return self._legacy.getEnhancedStockData(symbol, start_date, end_date, freq, include_financials)
    
    def is_fund_symbol(self, symbol: str) -> bool:
        """Check if symbol is a fund/ETF."""
        return self._legacy.isFundSymbol(symbol)
    
    # ==================== 元信息方法 ====================
    
    def get_supported_frequencies(self) -> list:
        """Get supported data frequencies for Tushare."""
        return self._legacy.getSupportedFrequencies()
    
    def get_supported_markets(self) -> list:
        """Get supported markets for Tushare."""
        return self._legacy.getSupportedMarkets()
    
    # ==================== 行业/板块资金流向接口 ====================
    
    def get_industry_money_flow_ths(
        self,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None,
        ts_code: str = None
    ) -> pd.DataFrame:
        """
        Get THS (同花顺) industry money flow data.
        
        Args:
            trade_date: Trade date in YYYYMMDD format
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            ts_code: Industry code (e.g., '881101.TI')
            
        Returns:
            DataFrame with industry money flow data including:
            - Institutional flow (xlarge + large orders)
            - Retail flow (mid + small orders)
            - Net amounts and percentages
        """
        return self._legacy.getIndustryMoneyFlowTHS(trade_date, start_date, end_date, ts_code)
    
    def get_industry_money_flow_dc(
        self,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None,
        ts_code: str = None
    ) -> pd.DataFrame:
        """
        Get DC (东方财富) industry money flow data.
        
        Args:
            trade_date: Trade date in YYYYMMDD format
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            ts_code: Sector code
            
        Returns:
            DataFrame with sector money flow data
        """
        return self._legacy.getIndustryMoneyFlowDC(trade_date, start_date, end_date, ts_code)
    
    def get_market_money_flow_summary(self, trade_date: str) -> Dict:
        """
        Get market-wide money flow summary with institutional vs retail analysis.
        
        Args:
            trade_date: Trade date in YYYYMMDD format
            
        Returns:
            Dict containing:
            - institutional_analysis: Institutional (xlarge+large) flow summary
            - retail_analysis: Retail (mid+small) flow summary
            - industry_ranking: Top inflow/outflow industries
            - north_money: Northbound capital flow
            - market_sentiment: Overall market sentiment judgment
        """
        return self._legacy.getMarketMoneyFlowSummary(trade_date)
    
    def analyze_institutional_vs_retail(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> Dict:
        """
        Analyze institutional vs retail money flow for a specific stock.
        
        Args:
            symbol: Stock symbol (e.g., '000001.SZ')
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            
        Returns:
            Dict with institutional vs retail flow analysis including:
            - institutional: Total/avg net flow, inflow/outflow days
            - retail: Total/avg net flow, inflow/outflow days
            - trend: 'institutional_accumulation', 'institutional_distribution', etc.
            - interpretation: Chinese interpretation of the trend
        """
        return self._legacy.analyzeInstitutionalVsRetail(symbol, start_date, end_date)


    @staticmethod
    def normalize_flow_columns(df: pd.DataFrame) -> pd.DataFrame:
        """
        归一化行业资金流向 DataFrame 的机构/散户字段

        确保输出包含 institutional_net 和 retail_net 列。
        优先使用 Provider 已算好的值；若全为 0 则回退到主力净额字段。

        Args:
            df: 单日行业资金流向 DataFrame（须含 net_amount 列）

        Returns:
            带有 institutional_net, retail_net 列的 DataFrame
        """
        has_valid_inst = (
            'institutional_net' in df.columns
            and (df['institutional_net'] != 0).any()
        )

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

        return df

    def get_stock_basic(self) -> pd.DataFrame:
        """Get all listed companies basic info."""
        return self._legacy.get_stock_basic()


    def get_trading_days(self, start_date: str, end_date: str) -> list:
        """
        Get trading days list within a date range.
        
        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            
        Returns:
            List of date strings (YYYYMMDD)
        """
        try:
            df = self.pro.trade_cal(exchange='', start_date=start_date, end_date=end_date, is_open='1')
            if not df.empty:
                return df['cal_date'].tolist()
            return []
        except Exception as e:
            logger.error(f"Error fetching trading days: {e}")
            return []


    def get_hk_stock_basic(self) -> pd.DataFrame:
        """Get all listed Hong Kong stocks basic info."""
        return self._legacy.get_hk_stock_basic()

    def get_daily_basic(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        fields: str = 'ts_code,trade_date,close,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_mv,circ_mv'
    ) -> pd.DataFrame:
        """
        Get daily basic indicators (PE, PB, PS, etc.) for a stock.

        Args:
            symbol: Stock symbol (e.g., '000001.SZ')
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            fields: Fields to retrieve

        Returns:
            DataFrame with daily basic indicators
        """
        try:
            df = self.pro.daily_basic(
                ts_code=symbol,
                start_date=start_date,
                end_date=end_date,
                fields=fields
            )
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            logger.error(f"Error fetching daily_basic for {symbol}: {e}")
            return pd.DataFrame()

    def get_margin_data(self, lookback_days: int = 90, exchange: str = "SSE") -> pd.DataFrame:
        """
        获取全市场融资融券数据。

        Args:
            lookback_days: 回溯天数
            exchange: 交易所代码，SSE(上交所) 或 SZSE(深交所)

        Returns:
            DataFrame with columns: trade_date, exchange_id, rzye, rzmre, rzche, rqye, ...
            Sorted by trade_date ascending.
        """
        from datetime import datetime, timedelta

        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=lookback_days + 10)
        start_str = start_dt.strftime("%Y%m%d")
        end_str = end_dt.strftime("%Y%m%d")

        try:
            df = self.pro.margin(
                exchange_id=exchange,
                start_date=start_str,
                end_date=end_str,
            )
            if df is None or df.empty:
                return pd.DataFrame()
            return df.sort_values("trade_date").reset_index(drop=True)
        except Exception as e:
            logger.error(f"获取融资融券数据失败: {e}")
            return pd.DataFrame()


# Backward compatibility alias
TushareDataProvider = TushareProvider

