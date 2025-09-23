#!/usr/bin/env python3
"""
公司筛选器 - Company Screener
基于CANSLIM选股法筛选符合条件的股票

筛选条件：
1. 当前季度每股收益（EPS）同比至少增长25%
2. 销售收入同比至少增长25%

Created by: Quantitative Trading System
Date: 2024
"""

import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from typing import Dict, List, Optional, Tuple
import os
import json

# 调整sys.path以便从项目根目录导入quant包
import sys
from pathlib import Path
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])  # /Users/xupeng/lab/quantitative_trading
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# 使用统一数据提供器工厂和缓存管理器
from quant.data_providers.data_provider_factory import DataProviderFactory

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CompanyScreener:
    """公司筛选器"""
    
    def __init__(self, token: str = None):
        """
        初始化筛选器
        
        Args:
            token: Tushare token，如果为None则从环境变量获取
        """
        if token is None:
            token = os.getenv('TUSHARE_TOKEN')
        
        if not token:
            raise ValueError("请设置TUSHARE_TOKEN环境变量或提供token参数")
        
        # 筛选条件
        self.min_eps_growth = 25.0  # 最小EPS增长率(%)
        self.min_revenue_growth = 25.0  # 最小销售收入增长率(%)
        self.min_annual_eps_cagr = 25.0  # 最小年度EPS复合增长率(%)
        
        # 威廉·欧奈尔CANSLIM严格准则（可选）
        self.enable_william_oneil_rules = False  # 是否启用威廉·欧奈尔严格准则
        self.min_current_eps_growth = 20.0  # 当前季度EPS最小增长率(%)
        self.required_continuous_years = 5    # 要求连续增长年数
        self.min_volume_increase = 50.0      # 创新高时成交量增长(%)
        self.price_nearness_to_high = 15.0   # 距离52周高点的百分比阈值
        
        # 增强筛选功能（多层次筛选）
        self.enable_enhanced_mode = False  # 是否启用增强模式
        self.screening_tiers = {
            'growth_stocks': {
                'name': '成长股',
                'revenue_threshold': [0, 100],  # 0-100亿收入
                'eps_growth_min': 25.0,
                'revenue_growth_min': 25.0,
                'description': '小中盘成长股，追求高增长'
            },
            'large_cap': {
                'name': '大盘蓝筹',
                'revenue_threshold': [100, float('inf')],  # >100亿收入
                'eps_growth_min': 10.0,
                'revenue_growth_min': 10.0,
                'description': '大盘蓝筹股，稳健增长'
            },
            'mid_growth': {
                'name': '中等成长',
                'revenue_threshold': [20, 200],  # 20-200亿收入
                'eps_growth_min': 15.0,
                'revenue_growth_min': 15.0,
                'description': '中等规模成长股'
            },
            'conservative': {
                'name': '保守筛选',
                'revenue_threshold': [0, float('inf')],  # 所有规模
                'eps_growth_min': 5.0,
                'revenue_growth_min': 5.0,
                'description': '保守筛选条件，包含更多股票'
            }
        }
        
        # 行业适应性调整
        self.industry_adjustments = {
            '银行': {'eps_growth_min': 5.0, 'revenue_growth_min': 5.0},
            '白酒': {'eps_growth_min': 8.0, 'revenue_growth_min': 8.0},
            '保险': {'eps_growth_min': 5.0, 'revenue_growth_min': 5.0},
            '房地产': {'eps_growth_min': 0.0, 'revenue_growth_min': 0.0},
            '汽车整车': {'eps_growth_min': 15.0, 'revenue_growth_min': 15.0},
            '电气设备': {'eps_growth_min': 15.0, 'revenue_growth_min': 15.0},
            '铜': {'eps_growth_min': 10.0, 'revenue_growth_min': 10.0},
            '黄金': {'eps_growth_min': 10.0, 'revenue_growth_min': 10.0},
        }
        
        # 使用数据提供者工厂创建带缓存的Tushare数据提供者
        try:
            config = {'token': token}
            self.data_provider = DataProviderFactory.create('tushare', config, enableCache=True)
            logger.info("✅ 成功初始化缓存数据提供者 (Tushare)")
        except Exception as e:
            logger.error(f"初始化数据提供者失败: {e}")
            raise
        
        # 导出目录（仅用于保存筛选结果）- 使用统一缓存目录
        self.cache_dir = os.path.join(PROJECT_ROOT, "cache", "screener")
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def get_stock_list(self) -> pd.DataFrame:
        """
        获取所有上市公司列表（使用统一数据提供者）
        
        Returns:
            包含股票基本信息的DataFrame
        """
        logger.info("获取上市公司列表...")
        
        try:
            # 使用数据提供者获取股票列表（带缓存）
            data = self.data_provider.getStockList(
                exchange='',
                list_status='L',
                fields='ts_code,symbol,name,area,industry,list_date,market'
            )
            
            logger.info(f"获取到 {len(data)} 只股票")
            return data
            
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return pd.DataFrame()
    
    def get_latest_periods(self) -> Tuple[str, str]:
        """
        获取最新的两个季度报告期
        
        Returns:
            (当前季度, 去年同期季度) 的报告期字符串
        """
        now = datetime.now()
        year = now.year
        month = now.month
        
        # 根据当前月份确定最新已发布的季度
        if month >= 10:
            # Q3已发布
            current_quarter = f"{year}0930"
            last_year_quarter = f"{year-1}0930"
        elif month >= 7:
            # Q2已发布
            current_quarter = f"{year}0630"
            last_year_quarter = f"{year-1}0630"
        elif month >= 4:
            # Q1已发布
            current_quarter = f"{year}0331"
            last_year_quarter = f"{year-1}0331"
        else:
            # 年报已发布
            current_quarter = f"{year-1}1231"
            last_year_quarter = f"{year-2}1231"
        
        logger.info(f"分析期间: {current_quarter} vs {last_year_quarter}")
        return current_quarter, last_year_quarter

    def get_q1_yoy_periods(self) -> Tuple[str, str]:
        """
        获取Q1对比去年的Q1的两个报告期（用于数据覆盖不足时的回退）
        """
        now = datetime.now()
        year = now.year
        month = now.month
        if month >= 4:
            # 当年Q1已披露
            return f"{year}0331", f"{year-1}0331"
        else:
            # 使用去年的Q1与前年的Q1
            return f"{year-1}0331", f"{year-2}0331"

    def _is_coverage_incomplete(self, current_df: pd.DataFrame, previous_df: pd.DataFrame) -> bool:
        """
        判断当前季度数据是否覆盖不全。
        规则：当前期样本数小于上一期的一半，或当前期样本数低于3000。
        """
        try:
            if current_df is None or previous_df is None:
                return True
            cur_len = len(current_df)
            prev_len = len(previous_df) if previous_df is not None else 0
            if cur_len < 3000:
                return True
            if prev_len > 0 and cur_len < 0.5 * prev_len:
                return True
            return False
        except Exception:
            return True
    
    def get_period_financial_data(self, period: str, max_stocks: int = None) -> pd.DataFrame:
        """
        获取指定季度的财务数据（使用统一数据提供者）
        
        Args:
            period: 报告期 (YYYYMMDD格式)
            max_stocks: 最大获取股票数量，用于测试
            
        Returns:
            财务数据DataFrame
        """
        logger.info(f"获取 {period} 季度财务数据...")
        
        try:
            fields = 'ts_code,ann_date,f_ann_date,end_date,report_type,basic_eps,diluted_eps,total_revenue,revenue,n_income'
            # 使用数据提供者获取财务数据（带缓存）
            df = self.data_provider.getIncomeData(period, fields)
            
            if df is None or df.empty:
                logger.warning(f"未获取到 {period} 的财务数据")
                return pd.DataFrame()
            
            # 过滤掉非主要报告类型
            if 'report_type' in df.columns:
                df = df[df['report_type'] == '1'].copy()
            
            # 限制股票数量（测试用）
            if max_stocks:
                df = df.head(max_stocks)
            
            logger.info(f"获取到 {len(df)} 条财务记录")
            return df
            
        except Exception as e:
            logger.error(f"获取 {period} 财务数据失败: {e}")
            return pd.DataFrame()
    
    def get_annual_financial_data(self, years: List[int]) -> Dict[int, pd.DataFrame]:
        """
        获取多年年度财务数据（使用统一数据提供者）
        
        Args:
            years: 年份列表，如[2021, 2022, 2023]
            
        Returns:
            年度财务数据字典 {year: DataFrame}
        """
        annual_data = {}
        
        for year in years:
            period = f"{year}1231"  # 年报期
            logger.info(f"获取 {year} 年度财务数据...")
            
            try:
                fields = 'ts_code,ann_date,end_date,report_type,basic_eps,diluted_eps,total_revenue,revenue,n_income'
                # 使用数据提供者获取年度财务数据（带缓存）
                df = self.data_provider.getIncomeData(period, fields)
                
                if df is None or df.empty:
                    logger.warning(f"未获取到 {year} 年度财务数据")
                    continue
                
                # 过滤报告类型
                if 'report_type' in df.columns:
                    df = df[df['report_type'] == '1'].copy()
                
                annual_data[year] = df
                logger.info(f"获取到 {year} 年度 {len(df)} 条财务记录")
                
                # API限制
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"获取 {year} 年度财务数据失败: {e}")
                continue
        
        return annual_data
    
    def calculate_annual_eps_cagr(self, annual_data: Dict[int, pd.DataFrame], years: List[int]) -> pd.DataFrame:
        """
        计算年度EPS复合增长率
        
        Args:
            annual_data: 年度财务数据字典
            years: 年份列表，按时间顺序排列
            
        Returns:
            包含年度EPS复合增长率的DataFrame
        """
        logger.info("计算年度EPS复合增长率...")
        
        if len(years) < 2:
            logger.warning("需要至少2年数据计算复合增长率")
            return pd.DataFrame()
        
        # 准备EPS数据
        eps_data = {}
        for year in years:
            if year in annual_data and not annual_data[year].empty:
                year_data = annual_data[year][['ts_code', 'basic_eps']].copy()
                year_data.columns = ['ts_code', f'eps_{year}']
                eps_data[year] = year_data
        
        if len(eps_data) < 2:
            logger.warning("有效年度数据不足，无法计算复合增长率")
            return pd.DataFrame()
        
        # 逐步合并各年数据
        merged = None
        for year in sorted(eps_data.keys()):
            if merged is None:
                merged = eps_data[year]
            else:
                merged = pd.merge(merged, eps_data[year], on='ts_code', how='inner')
        
        if merged is None or merged.empty:
            logger.warning("无法合并年度EPS数据")
            return pd.DataFrame()
        
        # 计算复合增长率
        start_year = min(years)
        end_year = max(years)
        years_span = end_year - start_year
        
        start_col = f'eps_{start_year}'
        end_col = f'eps_{end_year}'
        
        if start_col not in merged.columns or end_col not in merged.columns:
            logger.warning(f"缺少起始年份({start_year})或结束年份({end_year})的EPS数据")
            return pd.DataFrame()
        
        # 过滤有效数据（起始年份EPS > 0）
        valid_data = merged[
            (merged[start_col] > 0) & 
            (merged[end_col].notna()) & 
            (merged[start_col].notna())
        ].copy()
        
        if valid_data.empty:
            logger.warning("没有有效的EPS数据用于计算复合增长率")
            return pd.DataFrame()
        
        # 计算CAGR：((结束值/起始值)^(1/年数) - 1) * 100
        valid_data['annual_eps_cagr'] = (
            ((valid_data[end_col] / valid_data[start_col]) ** (1.0 / years_span) - 1) * 100
        )
        
        # 处理异常值
        valid_data['annual_eps_cagr'] = valid_data['annual_eps_cagr'].replace([float('inf'), float('-inf')], float('nan'))
        valid_data = valid_data.dropna(subset=['annual_eps_cagr'])
        
        result = valid_data[['ts_code', 'annual_eps_cagr', start_col, end_col]].copy()
        result.columns = ['ts_code', 'annual_eps_cagr', 'eps_start_year', 'eps_end_year']
        
        logger.info(f"计算出 {len(result)} 只股票的年度EPS复合增长率（{start_year}-{end_year}）")
        return result
    
    def calculate_growth_rates(self, current_data: pd.DataFrame, 
                             previous_data: pd.DataFrame) -> pd.DataFrame:
        """
        计算增长率
        
        Args:
            current_data: 当前期财务数据
            previous_data: 上年同期财务数据
            
        Returns:
            包含增长率的DataFrame
        """
        logger.info("计算增长率...")
        
        # 合并数据
        current_key = current_data[['ts_code', 'basic_eps', 'total_revenue']].copy()
        current_key.columns = ['ts_code', 'current_eps', 'current_revenue']
        
        previous_key = previous_data[['ts_code', 'basic_eps', 'total_revenue']].copy()
        previous_key.columns = ['ts_code', 'previous_eps', 'previous_revenue']
        
        merged = pd.merge(current_key, previous_key, on='ts_code', how='inner')
        
        # 计算增长率
        merged['eps_growth'] = ((merged['current_eps'] - merged['previous_eps']) / 
                               merged['previous_eps'].abs()) * 100
        
        merged['revenue_growth'] = ((merged['current_revenue'] - merged['previous_revenue']) / 
                                   merged['previous_revenue']) * 100
        
        # 处理无穷大和NaN值
        merged = merged.replace([float('inf'), float('-inf')], float('nan'))
        merged = merged.dropna()
        
        logger.info(f"计算出 {len(merged)} 只股票的增长率")
        return merged
    
    def apply_filters(self, growth_data: pd.DataFrame, annual_cagr_data: pd.DataFrame = None) -> pd.DataFrame:
        """
        应用筛选条件
        
        Args:
            growth_data: 包含增长率的数据
            annual_cagr_data: 包含年度EPS复合增长率的数据
            
        Returns:
            筛选后的数据
        """
        filter_desc = f"EPS增长>={self.min_eps_growth}%, 收入增长>={self.min_revenue_growth}%"
        if annual_cagr_data is not None and not annual_cagr_data.empty:
            filter_desc += f", 年度EPS复合增长率>={self.min_annual_eps_cagr}%"
        
        logger.info(f"应用筛选条件: {filter_desc}")
        
        # 基本筛选条件
        filtered = growth_data[
            (growth_data['eps_growth'] >= self.min_eps_growth) &
            (growth_data['revenue_growth'] >= self.min_revenue_growth)
        ].copy()
        
        # 如果有年度CAGR数据，加入筛选
        if annual_cagr_data is not None and not annual_cagr_data.empty:
            # 合并年度CAGR数据
            filtered = pd.merge(filtered, annual_cagr_data, on='ts_code', how='inner')
            
            # 应用年度CAGR筛选条件
            before_cagr_count = len(filtered)
            filtered = filtered[filtered['annual_eps_cagr'] >= self.min_annual_eps_cagr].copy()
            logger.info(f"年度EPS复合增长率筛选: {before_cagr_count} -> {len(filtered)} 只股票")
        
        # 按EPS增长率排序
        filtered = filtered.sort_values('eps_growth', ascending=False)
        
        logger.info(f"最终筛选出 {len(filtered)} 只符合条件的股票")
        return filtered
    
    def enrich_results(self, filtered_data: pd.DataFrame, 
                      stock_basic: pd.DataFrame) -> pd.DataFrame:
        """
        丰富筛选结果信息
        
        Args:
            filtered_data: 筛选后的数据
            stock_basic: 股票基本信息
            
        Returns:
            丰富后的结果
        """
        # 合并基本信息
        result = pd.merge(filtered_data, stock_basic, on='ts_code', how='left')
        
        # 去重：确保每只股票只出现一次（基于ts_code）
        original_count = len(result)
        result = result.drop_duplicates(subset=['ts_code'], keep='first')
        if len(result) < original_count:
            logger.info(f"去除重复股票: {original_count} -> {len(result)} 只股票")
        
        # 选择需要的列
        columns = [
            'ts_code', 'name', 'industry', 'area',
            'current_eps', 'previous_eps', 'eps_growth',
            'current_revenue', 'previous_revenue', 'revenue_growth'
        ]
        
        # 如果有年度CAGR数据，加入结果
        if 'annual_eps_cagr' in result.columns:
            columns.extend(['annual_eps_cagr', 'eps_start_year', 'eps_end_year'])
        
        # 只选择存在的列
        existing_columns = [col for col in columns if col in result.columns]
        result = result[existing_columns].copy()
        
        # 格式化数值
        result['eps_growth'] = result['eps_growth'].round(2)
        result['revenue_growth'] = result['revenue_growth'].round(2)
        result['current_revenue'] = (result['current_revenue'] / 1e8).round(2)  # 转换为亿元
        result['previous_revenue'] = (result['previous_revenue'] / 1e8).round(2)  # 转换为亿元
        
        # 格式化年度CAGR（如果存在）
        if 'annual_eps_cagr' in result.columns:
            result['annual_eps_cagr'] = result['annual_eps_cagr'].round(2)
        
        return result
    
    def enable_william_oneil_screening(self):
        """启用威廉·欧奈尔CANSLIM严格筛选准则"""
        self.enable_william_oneil_rules = True
        logger.info("✅ 已启用威廉·欧奈尔CANSLIM严格筛选准则")
    
    def check_continuous_eps_growth_robust(self, annual_data: Dict[int, pd.DataFrame], 
                                          years: List[int]) -> pd.DataFrame:
        """
        强化版连续EPS增长检查（威廉·欧奈尔准则）- 修复重复标签问题
        
        Args:
            annual_data: 年度财务数据字典
            years: 年份列表
            
        Returns:
            符合连续增长条件的股票DataFrame
        """
        logger.info("检查威廉·欧奈尔连续EPS增长准则（强化版）...")
        
        if len(years) < self.required_continuous_years:
            logger.warning(f"年份数量不足({len(years)} < {self.required_continuous_years})")
            return pd.DataFrame()
        
        try:
            # 准备EPS数据 - 修复重复标签问题
            valid_stocks = set()
            eps_records = []
            
            for year in sorted(years):
                if year in annual_data and not annual_data[year].empty:
                    year_data = annual_data[year][['ts_code', 'basic_eps']].copy()
                    # 去重处理
                    year_data = year_data.drop_duplicates(subset=['ts_code'], keep='first')
                    # 过滤有效数据
                    year_data = year_data[
                        year_data['basic_eps'].notna() & 
                        (year_data['basic_eps'] > 0) &
                        (year_data['basic_eps'] != float('inf')) &
                        (year_data['basic_eps'] != float('-inf'))
                    ]
                    
                    for _, row in year_data.iterrows():
                        valid_stocks.add(row['ts_code'])
                        eps_records.append({
                            'ts_code': row['ts_code'],
                            'year': year,
                            'eps': row['basic_eps']
                        })
            
            if not eps_records:
                logger.warning("没有有效的EPS数据")
                return pd.DataFrame()
            
            # 转换为DataFrame
            eps_df = pd.DataFrame(eps_records)
            
            # 计算每只股票的连续增长情况
            results = []
            
            for ts_code in valid_stocks:
                stock_data = eps_df[eps_df['ts_code'] == ts_code].sort_values('year')
                
                if len(stock_data) < 3:  # 至少需要3年数据
                    continue
                
                # 计算年度增长次数
                growth_count = 0
                total_growth = 0
                valid_comparisons = 0
                
                for i in range(1, len(stock_data)):
                    prev_eps = stock_data.iloc[i-1]['eps']
                    curr_eps = stock_data.iloc[i]['eps']
                    
                    if prev_eps > 0:  # 确保基数为正
                        growth_rate = (curr_eps - prev_eps) / prev_eps
                        total_growth += growth_rate
                        valid_comparisons += 1
                        
                        if growth_rate > 0:  # 正增长
                            growth_count += 1
                
                # 威廉·欧奈尔标准：5年中至少4年增长
                min_required_growth_years = max(2, len(stock_data) - 2)  # 保守估计
                avg_growth_rate = (total_growth / valid_comparisons * 100) if valid_comparisons > 0 else 0
                
                if growth_count >= min_required_growth_years and len(stock_data) >= 4:
                    results.append({
                        'ts_code': ts_code,
                        'growth_years': growth_count,
                        'total_years': len(stock_data),
                        'avg_growth_rate': avg_growth_rate
                    })
            
            qualified_df = pd.DataFrame(results)
            
            if not qualified_df.empty:
                logger.info(f"威廉·欧奈尔连续增长筛选: {len(valid_stocks)} -> {len(qualified_df)} 只股票")
                logger.info(f"平均连续增长年数: {qualified_df['growth_years'].mean():.1f}年")
            else:
                logger.warning("未找到符合连续增长条件的股票")
            
            return qualified_df
            
        except Exception as e:
            logger.error(f"连续EPS增长检查失败: {e}")
            return pd.DataFrame()
    
    def validate_and_clean_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        验证和清理数据，排除异常值
        
        Args:
            data: 原始数据
            
        Returns:
            清理后的数据
        """
        if data.empty:
            return data
        
        original_count = len(data)
        
        # 1. 排除ST股票
        data = data[~data['name'].str.contains('ST', na=False)]
        st_filtered = original_count - len(data)
        if st_filtered > 0:
            logger.info(f"排除ST股票: {st_filtered}只")
        
        # 2. 排除极端EPS增长率（>1000%的视为异常）
        if 'eps_growth' in data.columns:
            extreme_eps = data['eps_growth'] > 1000
            if extreme_eps.any():
                logger.info(f"发现极端EPS增长率股票: {extreme_eps.sum()}只，最高: {data['eps_growth'].max():.1f}%")
                data = data[data['eps_growth'] <= 1000]
        
        # 3. 排除极端收入增长率（>500%的视为异常）
        if 'revenue_growth' in data.columns:
            extreme_revenue = data['revenue_growth'] > 500
            if extreme_revenue.any():
                logger.info(f"发现极端收入增长率股票: {extreme_revenue.sum()}只")
                data = data[data['revenue_growth'] <= 500]
        
        # 4. 确保EPS和收入都为正值
        if 'current_eps' in data.columns:
            data = data[data['current_eps'] > 0]
        
        if 'current_revenue' in data.columns:
            data = data[data['current_revenue'] > 0]
        
        final_count = len(data)
        if final_count < original_count:
            logger.info(f"数据清理: {original_count} -> {final_count} 只股票")
        
        return data
    
    def check_volume_breakout(self, ts_codes: List[str]) -> pd.DataFrame:
        """
        检查成交量突破（日成交量比平均水平增加50%以上）
        
        Args:
            ts_codes: 股票代码列表
            
        Returns:
            包含成交量信息的DataFrame
        """
        logger.info(f"检查成交量突破条件，共{len(ts_codes)}只股票...")
        
        try:
            volume_results = []
            
            # 获取最近的交易日期
            end_date = datetime.now().strftime('%Y%m%d')
            # 获取过去30个交易日的数据（用于计算20日平均成交量）
            start_date = (datetime.now() - timedelta(days=45)).strftime('%Y%m%d')
            
            # 限制处理数量以避免API压力和超时
            limited_codes = ts_codes[:50]  # 只处理前50只股票
            
            for i, ts_code in enumerate(limited_codes):
                try:
                    # 获取股票的日线数据
                    daily_data = self.data_provider.getStockData(
                        symbol=ts_code, 
                        startDate=start_date, 
                        endDate=end_date, 
                        frequency='D'
                    )
                    
                    if daily_data.empty or len(daily_data) < 21:
                        logger.warning(f"股票 {ts_code} 数据不足，跳过成交量检查")
                        continue
                    
                    # 按日期排序（最新的在前）
                    daily_data = daily_data.sort_index(ascending=False)
                    
                    # 获取最新成交量
                    latest_volume = daily_data['volume'].iloc[0] if len(daily_data) > 0 else 0
                    
                    # 计算过去20个交易日的平均成交量（排除最新一天）
                    if len(daily_data) > 20:
                        avg_volume = daily_data['volume'].iloc[1:21].mean()
                    else:
                        avg_volume = daily_data['volume'].iloc[1:].mean()
                    
                    # 计算成交量比率
                    if avg_volume > 0:
                        volume_ratio = latest_volume / avg_volume
                        volume_breakout = volume_ratio >= 1.5  # 50%以上增长
                    else:
                        volume_ratio = 0
                        volume_breakout = False
                    
                    volume_results.append({
                        'ts_code': ts_code,
                        'latest_volume': latest_volume,
                        'avg_volume_20d': avg_volume,
                        'volume_ratio': volume_ratio,
                        'volume_breakout': volume_breakout
                    })
                    
                    # 进度提示
                    if (i + 1) % 10 == 0:
                        logger.info(f"已完成成交量检查: {i + 1}/{len(limited_codes)}")
                    
                    # API限制
                    time.sleep(0.2)
                    
                except Exception as e:
                    logger.warning(f"获取股票 {ts_code} 成交量数据失败: {e}")
                    continue
            
            if volume_results:
                result_df = pd.DataFrame(volume_results)
                breakout_count = result_df['volume_breakout'].sum()
                logger.info(f"成交量检查完成，{breakout_count}/{len(result_df)} 只股票符合成交量突破条件")
                return result_df
            else:
                logger.warning("未获取到任何有效的成交量数据")
                return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"成交量检查失败: {e}")
            return pd.DataFrame()
    
    def classify_stock_by_revenue(self, revenue: float) -> str:
        """
        根据收入规模对股票分类
        
        Args:
            revenue: 收入（亿元）
            
        Returns:
            股票分类
        """
        if revenue < 20:
            return 'small_cap'
        elif revenue < 100:
            return 'mid_cap'
        else:
            return 'large_cap'
    
    def get_adjusted_criteria(self, industry: str, revenue: float) -> Dict:
        """
        获取调整后的筛选条件（行业和规模适应性调整）
        
        Args:
            industry: 行业
            revenue: 收入规模（亿元）
            
        Returns:
            调整后的筛选条件
        """
        # 基础条件
        base_criteria = {
            'eps_growth_min': self.min_eps_growth,
            'revenue_growth_min': self.min_revenue_growth
        }
        
        # 行业调整
        if industry in self.industry_adjustments:
            base_criteria.update(self.industry_adjustments[industry])
        
        # 规模调整
        if revenue > 100:  # 大型企业
            base_criteria['eps_growth_min'] *= 0.6  # 降低40%要求
            base_criteria['revenue_growth_min'] *= 0.6
        elif revenue > 50:  # 中大型企业
            base_criteria['eps_growth_min'] *= 0.8  # 降低20%要求
            base_criteria['revenue_growth_min'] *= 0.8
        
        return base_criteria
    
    def enhanced_screen_stocks(self, screening_tier: str = 'all', max_stocks: int = None) -> Dict[str, pd.DataFrame]:
        """
        执行增强筛选（多层次筛选）
        
        Args:
            screening_tier: 筛选层次 ('growth_stocks', 'large_cap', 'mid_growth', 'conservative', 'all')
            max_stocks: 最大处理股票数量（测试用）
            
        Returns:
            不同层次的筛选结果字典
        """
        logger.info("🚀 开始增强筛选...")
        self.enable_enhanced_mode = True
        
        # 1. 获取所有财务数据
        stock_basic = self.get_stock_list()
        if stock_basic.empty:
            return {}
        
        current_period, previous_period = self.get_latest_periods()
        current_data = self.get_period_financial_data(current_period, max_stocks)
        previous_data = self.get_period_financial_data(previous_period, max_stocks)
        
        if current_data.empty or previous_data.empty:
            return {}
        
        # 检查数据覆盖完整性
        if self._is_coverage_incomplete(current_data, previous_data):
            q1_current, q1_previous = self.get_q1_yoy_periods()
            logger.info(f"检测到当前季度数据覆盖不足，改用Q1同比: {q1_current} vs {q1_previous}")
            current_data = self.get_period_financial_data(q1_current, max_stocks)
            time.sleep(1)
            previous_data = self.get_period_financial_data(q1_previous, max_stocks)
            if current_data.empty or previous_data.empty:
                logger.error("Q1同比回退仍未获取到有效数据")
                return {}
        
        # 2. 计算增长率
        growth_data = self.calculate_growth_rates(current_data, previous_data)
        if growth_data.empty:
            return {}
        
        # 3. 合并基本信息
        enhanced_data = pd.merge(growth_data, stock_basic, on='ts_code', how='left')
        
        # 4. 执行分层筛选
        results = {}
        
        if screening_tier == 'all':
            tiers_to_process = list(self.screening_tiers.keys())
        else:
            tiers_to_process = [screening_tier] if screening_tier in self.screening_tiers else ['conservative']
        
        for tier in tiers_to_process:
            tier_config = self.screening_tiers[tier]
            logger.info(f"处理筛选层次: {tier_config['name']}")
            
            # 应用收入规模筛选
            revenue_min, revenue_max = tier_config['revenue_threshold']
            tier_data = enhanced_data[
                (enhanced_data['current_revenue'] >= revenue_min * 1e8) &
                (enhanced_data['current_revenue'] <= revenue_max * 1e8)
            ].copy()
            
            if tier_data.empty:
                continue
            
            # 应用增长率筛选（考虑行业调整）
            filtered_stocks = []
            for _, row in tier_data.iterrows():
                adjusted_criteria = self.get_adjusted_criteria(row['industry'], row['current_revenue'] / 1e8)
                
                eps_meets = row['eps_growth'] >= adjusted_criteria['eps_growth_min']
                revenue_meets = row['revenue_growth'] >= adjusted_criteria['revenue_growth_min']
                
                if eps_meets and revenue_meets:
                    # 添加调整后的条件信息
                    row['applied_eps_threshold'] = adjusted_criteria['eps_growth_min']
                    row['applied_revenue_threshold'] = adjusted_criteria['revenue_growth_min']
                    row['revenue_size_category'] = self.classify_stock_by_revenue(row['current_revenue'] / 1e8)
                    filtered_stocks.append(row)
            
            if filtered_stocks:
                tier_result = pd.DataFrame(filtered_stocks).reset_index(drop=True)
                # 按EPS增长率排序
                tier_result = tier_result.sort_values('eps_growth', ascending=False)
                
                # 格式化数值
                tier_result['eps_growth'] = tier_result['eps_growth'].round(2)
                tier_result['revenue_growth'] = tier_result['revenue_growth'].round(2)
                tier_result['current_revenue'] = (tier_result['current_revenue'] / 1e8).round(2)  # 转换为亿元
                tier_result['previous_revenue'] = (tier_result['previous_revenue'] / 1e8).round(2)  # 转换为亿元
                
                results[tier] = tier_result
                
                logger.info(f"{tier_config['name']}筛选出 {len(tier_result)} 只股票")
        
        return results
    
    def print_enhanced_results(self, results: Dict[str, pd.DataFrame]):
        """
        打印增强筛选结果
        
        Args:
            results: 筛选结果字典
        """
        if not results:
            print("\n❌ 未找到符合条件的股票")
            return
        
        print(f"\n🎯 增强筛选结果汇总")
        print("=" * 100)
        
        total_stocks = sum(len(df) for df in results.values())
        print(f"总共找到 {total_stocks} 只符合条件的股票，分布在 {len(results)} 个筛选层次中")
        
        for tier, df in results.items():
            tier_config = self.screening_tiers.get(tier, {'name': tier, 'description': ''})
            
            print(f"\n📊 {tier_config['name']} - {len(df)}只股票")
            print(f"筛选说明: {tier_config['description']}")
            print("-" * 80)
            
            if len(df) > 0:
                print(f"{'排名':<4} {'代码':<12} {'名称':<16} {'行业':<12} {'EPS增长%':<10} {'收入增长%':<12} "
                      f"{'规模':<8} {'EPS门槛':<8} {'收入门槛':<8}")
                print("-" * 80)
                
                for idx, (_, row) in enumerate(df.head(10).iterrows(), 1):
                    print(f"{idx:<4} {row['ts_code']:<12} {row['name']:<16} {row['industry']:<12} "
                          f"{row['eps_growth']:<10.1f} {row['revenue_growth']:<12.1f} "
                          f"{row['revenue_size_category']:<8} {row['applied_eps_threshold']:<8.1f} "
                          f"{row['applied_revenue_threshold']:<8.1f}")
                
                if len(df) > 10:
                    print(f"... 还有 {len(df) - 10} 只股票")
            
            # 统计信息
            if len(df) > 0:
                print(f"\n统计信息:")
                print(f"  平均EPS增长率: {df['eps_growth'].mean():.1f}%")
                print(f"  平均收入增长率: {df['revenue_growth'].mean():.1f}%")
                
                # 规模分布
                size_dist = df['revenue_size_category'].value_counts()
                print(f"  规模分布: " + ", ".join([f"{k}: {v}只" for k, v in size_dist.items()]))
    
    def save_enhanced_results(self, results: Dict[str, pd.DataFrame], filename_prefix: str = "enhanced_screening"):
        """
        保存增强筛选结果
        
        Args:
            results: 筛选结果字典
            filename_prefix: 文件名前缀
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for tier, df in results.items():
            if not df.empty:
                filename = f"{filename_prefix}_{tier}_{timestamp}.csv"
                filepath = os.path.join(self.cache_dir, filename)
                
                # 选择要保存的列
                columns_to_save = [
                    'ts_code', 'name', 'industry', 'area', 'revenue_size_category',
                    'current_eps', 'previous_eps', 'eps_growth',
                    'current_revenue', 'previous_revenue', 'revenue_growth',
                    'applied_eps_threshold', 'applied_revenue_threshold'
                ]
                
                # 只保存存在的列
                existing_columns = [col for col in columns_to_save if col in df.columns]
                df[existing_columns].to_csv(filepath, index=False, encoding='utf-8-sig')
                
                logger.info(f"{tier}层次结果已保存到: {filepath}")
    
    def screen_stocks(self, max_stocks: int = None, save_results: bool = True, 
                     enable_oneil: bool = False, enable_enhanced: bool = False, 
                     screening_tier: str = 'all') -> pd.DataFrame:
        """
        执行股票筛选（支持多种模式）
        
        Args:
            max_stocks: 最大处理股票数量（测试用）
            save_results: 是否保存结果到文件
            enable_oneil: 是否启用威廉·欧奈尔严格准则
            enable_enhanced: 是否启用增强模式（多层次筛选）
            screening_tier: 筛选层次 ('growth_stocks', 'large_cap', 'mid_growth', 'conservative', 'all')
            
        Returns:
            筛选结果DataFrame（标准模式）或 Dict[str, DataFrame]（增强模式）
        """
        
        # 先检查是否启用增强模式
        if enable_enhanced:
            logger.info("🎆 启用增强筛选模式...")
            enhanced_results = self.enhanced_screen_stocks(screening_tier, max_stocks)
            if save_results:
                self.save_enhanced_results(enhanced_results)
            return enhanced_results
        
        if enable_oneil:
            self.enable_william_oneil_screening()
        logger.info("🔍 开始执行股票筛选...")
        
        # 1. 获取股票列表
        stock_basic = self.get_stock_list()
        if stock_basic.empty:
            logger.error("未能获取股票列表")
            return pd.DataFrame()
        
        # 2. 获取报告期
        current_period, previous_period = self.get_latest_periods()
        
        # 3. 获取财务数据
        logger.info("获取当前期财务数据...")
        current_data = self.get_period_financial_data(current_period, max_stocks)
        if current_data.empty:
            return pd.DataFrame()
        
        time.sleep(1)  # 避免API限制
        
        logger.info("获取对比期财务数据...")
        previous_data = self.get_period_financial_data(previous_period, max_stocks)
        if previous_data.empty:
            return pd.DataFrame()
        
        # 如果当前季度数据覆盖不足，则回退到Q1同比
        if self._is_coverage_incomplete(current_data, previous_data):
            q1_current, q1_previous = self.get_q1_yoy_periods()
            logger.info(f"检测到当前季度数据覆盖不足，改用Q1同比: {q1_current} vs {q1_previous}")
            current_data = self.get_period_financial_data(q1_current, max_stocks)
            time.sleep(1)
            previous_data = self.get_period_financial_data(q1_previous, max_stocks)
            if current_data.empty or previous_data.empty:
                logger.error("Q1同比回退仍未获取到有效数据")
                return pd.DataFrame()
        
        # 4. 计算增长率
        growth_data = self.calculate_growth_rates(current_data, previous_data)
        if growth_data.empty:
            logger.warning("未能计算出增长率数据")
            return pd.DataFrame()
        
        # 5. 获取并计算年度EPS复合增长率 / 威廉·欧奈尔连续增长检查
        annual_cagr_data = None
        william_oneil_qualified = None
        
        try:
            current_year = datetime.now().year
            
            if self.enable_william_oneil_rules:
                # 威廉·欧奈尔准则：获取过去5年数据
                years = [current_year - 5, current_year - 4, current_year - 3, 
                        current_year - 2, current_year - 1]
                logger.info(f"威廉·欧奈尔模式：获取年度数据，分析年份: {years}")
                
                annual_data = self.get_annual_financial_data(years)
                if len(annual_data) >= 3:
                    william_oneil_qualified = self.check_continuous_eps_growth_robust(annual_data, years)
                    if not william_oneil_qualified.empty:
                        logger.info(f"威廉·欧奈尔连续增长筛选通过 {len(william_oneil_qualified)} 只股票")
                    else:
                        logger.warning("未找到符合威廉·欧奈尔连续增长准则的股票")
                else:
                    logger.warning(f"威廉·欧奈尔模式：年度数据不足（仅获取到{len(annual_data)}年）")
            else:
                # 标准模式：获取过去3年的年度数据
                years = [current_year - 3, current_year - 2, current_year - 1]
                logger.info(f"标准模式：获取年度EPS复合增长率数据，分析年份: {years}")
                
                annual_data = self.get_annual_financial_data(years)
                if len(annual_data) >= 2:  # 至少需要2年数据
                    annual_cagr_data = self.calculate_annual_eps_cagr(annual_data, years)
                    if not annual_cagr_data.empty:
                        logger.info(f"计算出 {len(annual_cagr_data)} 只股票的年度EPS复合增长率")
                    else:
                        logger.warning("未能计算出有效的年度EPS复合增长率")
                else:
                    logger.warning(f"年度数据不足（仅获取到{len(annual_data)}年），跳过年度EPS复合增长率筛选")
                    
        except Exception as e:
            logger.error(f"年度数据分析失败: {e}")
            annual_cagr_data = None
            william_oneil_qualified = None
        
        # 6. 应用筛选条件
        if self.enable_william_oneil_rules and william_oneil_qualified is not None:
            # 威廉·欧奈尔模式：先应用连续增长筛选，再应用其他条件
            logger.info("应用威廉·欧奈尔筛选模式...")
            
            # 先筛选当前季度EPS增长>=20%
            growth_data_qualified = growth_data[
                growth_data['eps_growth'] >= self.min_current_eps_growth
            ].copy()
            
            logger.info(f"当前季度EPS增长筛选: {len(growth_data)} -> {len(growth_data_qualified)} 只股票")
            
            # 合并连续增长和当前增长的条件
            filtered_data = pd.merge(
                william_oneil_qualified[['ts_code', 'growth_years', 'avg_growth_rate']],
                growth_data_qualified,
                on='ts_code',
                how='inner'
            )
            
            logger.info(f"威廉·欧奈尔综合筛选结果: {len(filtered_data)} 只股票")
        else:
            # 标准模式
            filtered_data = self.apply_filters(growth_data, annual_cagr_data)
        
        if filtered_data.empty:
            mode_desc = "威廉·欧奈尔" if self.enable_william_oneil_rules else "标准"
            logger.warning(f"未找到符合{mode_desc}筛选条件的股票")
            return pd.DataFrame()
        
        # 7. 丰富结果信息
        results = self.enrich_results(filtered_data, stock_basic)
        
        # 8. 数据清理和验证
        if not results.empty:
            logger.info("正在进行数据清理和异常值检查...")
            results = self.validate_and_clean_data(results)
            
            # 威廉·欧奈尔模式额外检查成交量突破
            if self.enable_william_oneil_rules and not results.empty:
                logger.info("检查成交量突破条件...")
                volume_data = self.check_volume_breakout(results['ts_code'].tolist())
                if not volume_data.empty:
                    # 合并成交量数据
                    results = pd.merge(results, volume_data, on='ts_code', how='left')
                    # 筛选符合成交量突破的股票
                    results = results[results['volume_breakout'] == True]
                    logger.info(f"成交量突破筛选后保留: {len(results)} 只股票")
        
        # 9. 保存结果
        if save_results and not results.empty:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_file = os.path.join(self.cache_dir, f"screening_results_{timestamp}.csv")
            results.to_csv(result_file, index=False, encoding='utf-8-sig')
            logger.info(f"筛选结果已保存到: {result_file}")
        
        return results
    
    def analyze_single_stock(self, ts_code: str, enable_oneil: bool = False) -> Dict:
        """
        分析单只股票是否符合筛选条件
        
        Args:
            ts_code: 股票代码，如 '000001.SZ'
            enable_oneil: 是否使用威廉·欧奈尔严格准则
            
        Returns:
            包含分析结果的字典
        """
        logger.info(f"开始分析股票: {ts_code}")
        
        if enable_oneil:
            self.enable_william_oneil_screening()
        
        try:
            # 1. 获取股票基本信息
            stock_basic = self.get_stock_list()
            stock_info = stock_basic[stock_basic['ts_code'] == ts_code]
            
            if stock_info.empty:
                return {
                    'success': False,
                    'error': f'未找到股票代码: {ts_code}',
                    'ts_code': ts_code
                }
            
            stock_name = stock_info.iloc[0]['name']
            stock_industry = stock_info.iloc[0]['industry']
            stock_area = stock_info.iloc[0]['area']
            
            # 2. 获取季度财务数据
            current_period, previous_period = self.get_latest_periods()
            current_data = self.get_period_financial_data(current_period)
            previous_data = self.get_period_financial_data(previous_period)
            
            # 如果数据覆盖不足，回退到Q1
            if self._is_coverage_incomplete(current_data, previous_data):
                q1_current, q1_previous = self.get_q1_yoy_periods()
                logger.info(f"使用Q1数据: {q1_current} vs {q1_previous}")
                current_data = self.get_period_financial_data(q1_current)
                previous_data = self.get_period_financial_data(q1_previous)
                current_period, previous_period = q1_current, q1_previous
            
            # 查找该股票的财务数据
            current_stock = current_data[current_data['ts_code'] == ts_code]
            previous_stock = previous_data[previous_data['ts_code'] == ts_code]
            
            if current_stock.empty or previous_stock.empty:
                return {
                    'success': False,
                    'error': f'未找到股票 {ts_code} 的财务数据',
                    'ts_code': ts_code,
                    'name': stock_name,
                    'periods': f'{current_period} vs {previous_period}'
                }
            
            # 3. 计算增长率
            current_eps = current_stock.iloc[0]['basic_eps']
            previous_eps = previous_stock.iloc[0]['basic_eps']
            current_revenue = current_stock.iloc[0]['total_revenue']
            previous_revenue = previous_stock.iloc[0]['total_revenue']
            
            eps_growth = ((current_eps - previous_eps) / abs(previous_eps)) * 100 if previous_eps != 0 else 0
            revenue_growth = ((current_revenue - previous_revenue) / previous_revenue) * 100 if previous_revenue != 0 else 0
            
            # 4. 获取年度数据分析
            current_year = datetime.now().year
            annual_eps_cagr = None
            continuous_growth_info = None
            
            try:
                if self.enable_william_oneil_rules:
                    # 威廉·欧奈尔模式：5年数据
                    years = [current_year - 5, current_year - 4, current_year - 3, 
                            current_year - 2, current_year - 1]
                    annual_data = self.get_annual_financial_data(years)
                    
                    # 分析该股票的连续增长情况
                    stock_eps_records = []
                    for year in sorted(years):
                        if year in annual_data:
                            year_data = annual_data[year]
                            stock_year_data = year_data[year_data['ts_code'] == ts_code]
                            if not stock_year_data.empty:
                                eps = stock_year_data.iloc[0]['basic_eps']
                                if pd.notna(eps) and eps > 0:
                                    stock_eps_records.append({'year': year, 'eps': eps})
                    
                    # 计算连续增长
                    growth_years = 0
                    growth_details = []
                    for i in range(1, len(stock_eps_records)):
                        prev_eps = stock_eps_records[i-1]['eps']
                        curr_eps = stock_eps_records[i]['eps']
                        if prev_eps > 0:
                            growth_rate = (curr_eps - prev_eps) / prev_eps * 100
                            is_growth = growth_rate > 0
                            if is_growth:
                                growth_years += 1
                            growth_details.append({
                                'year': stock_eps_records[i]['year'],
                                'prev_year': stock_eps_records[i-1]['year'],
                                'growth_rate': growth_rate,
                                'is_growth': is_growth
                            })
                    
                    continuous_growth_info = {
                        'growth_years': growth_years,
                        'total_years': len(stock_eps_records),
                        'growth_details': growth_details,
                        'meets_requirement': growth_years >= max(2, len(stock_eps_records) - 2) and len(stock_eps_records) >= 4
                    }
                else:
                    # 标准模式：3年复合增长率
                    years = [current_year - 3, current_year - 2, current_year - 1]
                    annual_data = self.get_annual_financial_data(years)
                    
                    # 计算该股票的年度EPS复合增长率
                    if len(annual_data) >= 2:
                        stock_annual_eps = {}
                        for year in years:
                            if year in annual_data:
                                year_data = annual_data[year]
                                stock_year_data = year_data[year_data['ts_code'] == ts_code]
                                if not stock_year_data.empty:
                                    eps = stock_year_data.iloc[0]['basic_eps']
                                    if pd.notna(eps) and eps > 0:
                                        stock_annual_eps[year] = eps
                        
                        if len(stock_annual_eps) >= 2:
                            start_year = min(stock_annual_eps.keys())
                            end_year = max(stock_annual_eps.keys())
                            years_span = end_year - start_year
                            if years_span > 0 and stock_annual_eps[start_year] > 0:
                                annual_eps_cagr = ((stock_annual_eps[end_year] / stock_annual_eps[start_year]) ** (1.0 / years_span) - 1) * 100
            except Exception as e:
                logger.warning(f"年度数据分析失败: {e}")
            
            # 5. 检查成交量突破（威廉·欧奈尔模式）
            volume_info = None
            if self.enable_william_oneil_rules:
                try:
                    volume_data = self.check_volume_breakout([ts_code])
                    if not volume_data.empty:
                        volume_info = {
                            'latest_volume': volume_data.iloc[0]['latest_volume'],
                            'avg_volume_20d': volume_data.iloc[0]['avg_volume_20d'],
                            'volume_ratio': volume_data.iloc[0]['volume_ratio'],
                            'volume_breakout': volume_data.iloc[0]['volume_breakout']
                        }
                except Exception as e:
                    logger.warning(f"成交量数据获取失败: {e}")
            
            # 6. 数据清理检查
            is_st_stock = 'ST' in stock_name
            is_extreme_eps = eps_growth > 1000
            is_extreme_revenue = revenue_growth > 500
            has_positive_eps = current_eps > 0
            has_positive_revenue = current_revenue > 0
            
            # 7. 生成分析结果
            analysis_result = {
                'success': True,
                'ts_code': ts_code,
                'name': stock_name,
                'industry': stock_industry,
                'area': stock_area,
                'analysis_period': f'{current_period} vs {previous_period}',
                'analysis_mode': '威廉·欧奈尔严格准则' if self.enable_william_oneil_rules else '标准筛选',
                
                # 财务数据
                'financial_data': {
                    'current_eps': current_eps,
                    'previous_eps': previous_eps,
                    'eps_growth': round(eps_growth, 2),
                    'current_revenue_billion': round(current_revenue / 1e8, 2),
                    'previous_revenue_billion': round(previous_revenue / 1e8, 2),
                    'revenue_growth': round(revenue_growth, 2),
                    'annual_eps_cagr': round(annual_eps_cagr, 2) if annual_eps_cagr is not None else None
                },
                
                # 筛选条件检查
                'criteria_check': {
                    'eps_growth': {
                        'value': round(eps_growth, 2),
                        'threshold': self.min_current_eps_growth if self.enable_william_oneil_rules else self.min_eps_growth,
                        'meets': eps_growth >= (self.min_current_eps_growth if self.enable_william_oneil_rules else self.min_eps_growth),
                        'description': f'EPS同比增长率 >= {self.min_current_eps_growth if self.enable_william_oneil_rules else self.min_eps_growth}%'
                    },
                    'revenue_growth': {
                        'value': round(revenue_growth, 2),
                        'threshold': self.min_revenue_growth,
                        'meets': revenue_growth >= self.min_revenue_growth,
                        'description': f'收入同比增长率 >= {self.min_revenue_growth}%'
                    },
                    'annual_eps_cagr': {
                        'value': round(annual_eps_cagr, 2) if annual_eps_cagr is not None else None,
                        'threshold': self.min_annual_eps_cagr,
                        'meets': annual_eps_cagr is not None and annual_eps_cagr >= self.min_annual_eps_cagr,
                        'description': f'年度EPS复合增长率 >= {self.min_annual_eps_cagr}%',
                        'applicable': not self.enable_william_oneil_rules
                    },
                    'continuous_growth': {
                        'info': continuous_growth_info,
                        'meets': continuous_growth_info['meets_requirement'] if continuous_growth_info else False,
                        'description': '连续EPS增长（5年中至少4年正增长）',
                        'applicable': self.enable_william_oneil_rules
                    },
                    'volume_breakout': {
                        'info': volume_info,
                        'meets': volume_info['volume_breakout'] if volume_info else False,
                        'description': '成交量突破（比20日均量增长50%以上）',
                        'applicable': self.enable_william_oneil_rules
                    }
                },
                
                # 数据质量检查
                'data_quality': {
                    'is_st_stock': is_st_stock,
                    'is_extreme_eps': is_extreme_eps,
                    'is_extreme_revenue': is_extreme_revenue,
                    'has_positive_eps': has_positive_eps,
                    'has_positive_revenue': has_positive_revenue,
                    'passes_quality_check': not is_st_stock and not is_extreme_eps and not is_extreme_revenue and has_positive_eps and has_positive_revenue
                }
            }
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"分析股票 {ts_code} 时出错: {e}")
            return {
                'success': False,
                'error': str(e),
                'ts_code': ts_code
            }
    
    def print_single_stock_analysis(self, analysis_result: Dict):
        """
        打印单股票分析结果
        
        Args:
            analysis_result: analyze_single_stock方法的返回结果
        """
        if not analysis_result['success']:
            print(f"\n❌ 分析失败: {analysis_result.get('error', '未知错误')}")
            return
        
        result = analysis_result
        print(f"\n📊 股票分析报告")
        print("=" * 80)
        print(f"股票代码: {result['ts_code']}")
        print(f"股票名称: {result['name']}")
        print(f"所属行业: {result['industry']}")
        print(f"所属地区: {result['area']}")
        print(f"分析模式: {result['analysis_mode']}")
        print(f"分析期间: {result['analysis_period']}")
        
        # 财务数据概览
        fd = result['financial_data']
        print(f"\n💰 财务数据概览")
        print("-" * 40)
        print(f"当前EPS: {fd['current_eps']:.3f}")
        print(f"去年EPS: {fd['previous_eps']:.3f}")
        print(f"EPS增长率: {fd['eps_growth']:.1f}%")
        print(f"当前收入: {fd['current_revenue_billion']:.1f}亿元")
        print(f"去年收入: {fd['previous_revenue_billion']:.1f}亿元")
        print(f"收入增长率: {fd['revenue_growth']:.1f}%")
        if fd['annual_eps_cagr'] is not None:
            print(f"年度EPS复合增长率: {fd['annual_eps_cagr']:.1f}%")
        
        # 筛选条件检查
        print(f"\n🎯 筛选条件检查")
        print("-" * 40)
        
        criteria = result['criteria_check']
        total_applicable = 0
        total_passed = 0
        
        for criterion_name, criterion_data in criteria.items():
            if criterion_data.get('applicable', True):
                total_applicable += 1
                meets = criterion_data['meets']
                total_passed += 1 if meets else 0
                
                status = "✅ 通过" if meets else "❌ 不通过"
                
                if criterion_name == 'continuous_growth' and criterion_data.get('info'):
                    info = criterion_data['info']
                    print(f"{status} {criterion_data['description']}")
                    print(f"     连续增长年数: {info['growth_years']}/{info['total_years']}年")
                    if info.get('growth_details'):
                        print(f"     年度增长详情:")
                        for detail in info['growth_details']:
                            growth_status = "📈" if detail['is_growth'] else "📉"
                            print(f"       {detail['prev_year']}->{detail['year']}: {growth_status} {detail['growth_rate']:.1f}%")
                
                elif criterion_name == 'volume_breakout' and criterion_data.get('info'):
                    info = criterion_data['info']
                    print(f"{status} {criterion_data['description']}")
                    print(f"     最新成交量: {info['latest_volume']:,.0f}")
                    print(f"     20日均量: {info['avg_volume_20d']:,.0f}")
                    print(f"     成交量比率: {info['volume_ratio']:.2f}倍")
                
                else:
                    value = criterion_data['value']
                    threshold = criterion_data['threshold']
                    if value is not None:
                        print(f"{status} {criterion_data['description']} (实际: {value}%, 要求: {threshold}%)")
                    else:
                        print(f"{status} {criterion_data['description']} (数据不足)")
        
        # 数据质量检查
        dq = result['data_quality']
        print(f"\n🔍 数据质量检查")
        print("-" * 40)
        
        quality_checks = [
            ('ST股票检查', not dq['is_st_stock'], '非ST股票' if not dq['is_st_stock'] else 'ST股票'),
            ('极端EPS检查', not dq['is_extreme_eps'], '正常范围' if not dq['is_extreme_eps'] else '极端增长率(>1000%)'),
            ('极端收入检查', not dq['is_extreme_revenue'], '正常范围' if not dq['is_extreme_revenue'] else '极端增长率(>500%)'),
            ('EPS正值检查', dq['has_positive_eps'], '正值' if dq['has_positive_eps'] else '非正值'),
            ('收入正值检查', dq['has_positive_revenue'], '正值' if dq['has_positive_revenue'] else '非正值')
        ]
        
        for check_name, passes, description in quality_checks:
            status = "✅" if passes else "❌"
            print(f"{status} {check_name}: {description}")
        
        # 综合结论
        print(f"\n📋 综合评估")
        print("-" * 40)
        print(f"筛选条件通过率: {total_passed}/{total_applicable} ({total_passed/total_applicable*100:.1f}%)")
        print(f"数据质量: {'✅ 合格' if dq['passes_quality_check'] else '❌ 不合格'}")
        
        overall_pass = (total_passed == total_applicable) and dq['passes_quality_check']
        print(f"\n🏆 最终结论: {'✅ 符合筛选条件' if overall_pass else '❌ 不符合筛选条件'}")
        
        if not overall_pass:
            print("\n💡 改进建议:")
            if total_passed < total_applicable:
                print("   - 关注财务指标的改善，特别是EPS和收入增长")
            if not dq['passes_quality_check']:
                print("   - 注意数据质量问题，避免极端值或异常情况")
    
    def print_results(self, results: pd.DataFrame):
        """
        打印筛选结果
        
        Args:
            results: 筛选结果DataFrame
        """
        if results.empty:
            print("\n❌ 未找到符合条件的股票")
            return
        
        print(f"\n🎯 筛选结果 - 共找到 {len(results)} 只符合条件的股票")
        
        # 根据是否有年度CAGR数据调整表头
        if 'annual_eps_cagr' in results.columns:
            print("=" * 140)
            print(f"{'代码':<12} {'名称':<16} {'行业':<12} {'地区':<8} {'当前EPS':<10} {'去年EPS':<10} {'EPS增长%':<10} {'当前收入(亿)':<12} {'去年收入(亿)':<12} {'收入增长%':<10} {'年度EPS复合增长%':<12}")
            print("-" * 140)
        else:
            print("=" * 120)
            print(f"{'代码':<12} {'名称':<16} {'行业':<12} {'地区':<8} {'当前EPS':<10} {'去年EPS':<10} {'EPS增长%':<10} {'当前收入(亿)':<12} {'去年收入(亿)':<12} {'收入增长%':<10}")
            print("-" * 120)
        
        for idx, row in results.head(20).iterrows():  # 只显示前20个
            base_info = (f"{row['ts_code']:<12} {row['name']:<16} {row['industry']:<12} {row['area']:<8} "
                        f"{row['current_eps']:<10.3f} {row['previous_eps']:<10.3f} {row['eps_growth']:<10.1f} "
                        f"{row['current_revenue']:<12.1f} {row['previous_revenue']:<12.1f} {row['revenue_growth']:<10.1f}")
            
            if 'annual_eps_cagr' in results.columns:
                cagr_val = row.get('annual_eps_cagr', 0)
                print(f"{base_info} {cagr_val:<12.1f}")
            else:
                print(base_info)
        
        if len(results) > 20:
            print(f"\n... 还有 {len(results) - 20} 只股票符合条件")


def main():
    """主函数"""
    try:
        # 创建筛选器
        screener = CompanyScreener()
        
        print("🎯 CANSLIM股票分析系统")
        print("=" * 50)
        print("1. 批量筛选股票")
        print("2. 分析单只股票")
        
        # 示例：单股票分析
        print("\n📊 示例：单股票分析")
        print("-" * 30)
        
        # 分析一只符合条件的股票
        sample_stocks = ['603129.SH', '000001.SZ']  # 春风动力和平安银行
        
        for stock_code in sample_stocks:
            print(f"\n分析股票: {stock_code}")
            analysis_result = screener.analyze_single_stock(stock_code, enable_oneil=False)
            screener.print_single_stock_analysis(analysis_result)
            print("\n" + "="*80 + "\n")
        
        # 执行批量筛选
        print("🚀 开始执行批量CANSLIM股票筛选...")
        print(f"筛选条件: EPS同比增长 >= {screener.min_eps_growth}%, 收入同比增长 >= {screener.min_revenue_growth}%, 年度EPS复合增长率 >= {screener.min_annual_eps_cagr}%")
        
        # 执行筛选 - 可以设置max_stocks=100进行测试
        # 如果要使用威廉·欧奈尔严格准则，设置enable_oneil=True
        results = screener.screen_stocks(max_stocks=200, enable_oneil=False)  # 使用200只股票做示例
        
        # 打印结果
        screener.print_results(results)
        
        # 统计信息
        if not results.empty:
            print(f"\n📊 统计信息:")
            print(f"平均EPS增长率: {results['eps_growth'].mean():.1f}%")
            print(f"平均收入增长率: {results['revenue_growth'].mean():.1f}%")
            print(f"最高EPS增长率: {results['eps_growth'].max():.1f}%")
            print(f"最高收入增长率: {results['revenue_growth'].max():.1f}%")
            
            # 行业分布
            industry_counts = results['industry'].value_counts().head(5)
            print(f"\n🏢 主要行业分布:")
            for industry, count in industry_counts.items():
                print(f"  {industry}: {count}只")
        
        # 使用说明
        print(f"\n📚 使用说明:")
        print(f"单股票分析: screener.analyze_single_stock('000001.SZ')")
        print(f"批量筛选: screener.screen_stocks(max_stocks=100)")
        print(f"威廉欧奈尔模式: screener.screen_stocks(enable_oneil=True)")
        print(f"增强模式: screener.screen_stocks(enable_enhanced=True)")
        
    except Exception as e:
        logger.error(f"筛选过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
