#!/usr/bin/env python3
"""
筛选结果分析器 - Screening Analyzer
对公司筛选器的结果进行深度分析和展示

功能：
1. 去重和数据清理
2. 行业和地区分析
3. 增长率统计分析
4. 质量评估和排名
5. 生成详细报告

Created by: Quantitative Trading System  
Date: 2024
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os
import logging
from typing import Dict, List, Optional
import matplotlib.pyplot as plt
import seaborn as sns

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ScreeningAnalyzer:
    """筛选结果分析器"""
    
    def __init__(self, cache_dir: str = "cache/screener"):
        self.cache_dir = cache_dir
        self.results_df = None
        
    def load_latest_results(self) -> pd.DataFrame:
        """
        加载最新的筛选结果
        
        Returns:
            筛选结果DataFrame
        """
        # 查找最新的结果文件
        result_files = [f for f in os.listdir(self.cache_dir) 
                       if f.startswith('screening_results_') and f.endswith('.csv')]
        
        if not result_files:
            logger.error("未找到筛选结果文件")
            return pd.DataFrame()
        
        # 按时间戳排序，获取最新文件
        result_files.sort(reverse=True)
        latest_file = os.path.join(self.cache_dir, result_files[0])
        
        logger.info(f"加载筛选结果: {latest_file}")
        
        try:
            df = pd.read_csv(latest_file)
            # 去重处理
            df = df.drop_duplicates(subset=['ts_code']).reset_index(drop=True)
            
            self.results_df = df
            logger.info(f"加载了 {len(df)} 只股票的筛选结果（去重后）")
            return df
            
        except Exception as e:
            logger.error(f"加载筛选结果失败: {e}")
            return pd.DataFrame()
    
    def quality_score_analysis(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        质量评分分析
        
        Args:
            df: 筛选结果DataFrame
            
        Returns:
            包含质量评分的DataFrame
        """
        df_scored = df.copy()
        
        # EPS质量评分 (0-40分)
        eps_growth_percentile = df_scored['eps_growth'].rank(pct=True)
        df_scored['eps_quality_score'] = eps_growth_percentile * 40
        
        # 收入质量评分 (0-30分)
        revenue_growth_percentile = df_scored['revenue_growth'].rank(pct=True)
        df_scored['revenue_quality_score'] = revenue_growth_percentile * 30
        
        # 规模评分 (0-20分) - 收入规模适中为好
        # 太小可能不稳定，太大可能增长乏力
        revenue_log = np.log10(df_scored['current_revenue'] + 1)
        optimal_size = 1.5  # 对应约30亿收入规模
        size_penalty = np.abs(revenue_log - optimal_size)
        size_score = np.maximum(0, 20 - size_penalty * 5)
        df_scored['size_quality_score'] = size_score
        
        # 稳定性评分 (0-10分) - 基于EPS是否为正值
        stability_score = np.where(df_scored['current_eps'] > 0, 10, 
                                 np.where(df_scored['current_eps'] > -0.1, 5, 0))
        df_scored['stability_quality_score'] = stability_score
        
        # 综合质量评分
        df_scored['total_quality_score'] = (
            df_scored['eps_quality_score'] + 
            df_scored['revenue_quality_score'] + 
            df_scored['size_quality_score'] +
            df_scored['stability_quality_score']
        )
        
        # 排序
        df_scored = df_scored.sort_values('total_quality_score', ascending=False)
        
        return df_scored
    
    def industry_analysis(self, df: pd.DataFrame) -> Dict:
        """
        行业分析
        
        Args:
            df: 筛选结果DataFrame
            
        Returns:
            行业分析结果字典
        """
        industry_stats = {}
        
        # 行业分布
        industry_counts = df['industry'].value_counts()
        industry_stats['distribution'] = industry_counts.to_dict()
        
        # 各行业平均增长率
        industry_growth = df.groupby('industry').agg({
            'eps_growth': ['mean', 'median', 'std', 'count'],
            'revenue_growth': ['mean', 'median', 'std'],
            'current_revenue': ['mean', 'median']
        }).round(2)
        
        industry_stats['growth_stats'] = industry_growth
        
        # 表现最好的行业（按平均EPS增长率）
        avg_eps_growth = df.groupby('industry')['eps_growth'].mean().sort_values(ascending=False)
        industry_stats['best_eps_industries'] = avg_eps_growth.head(10).to_dict()
        
        # 表现最好的行业（按平均收入增长率）
        avg_revenue_growth = df.groupby('industry')['revenue_growth'].mean().sort_values(ascending=False)
        industry_stats['best_revenue_industries'] = avg_revenue_growth.head(10).to_dict()
        
        return industry_stats
    
    def regional_analysis(self, df: pd.DataFrame) -> Dict:
        """
        地区分析
        
        Args:
            df: 筛选结果DataFrame
            
        Returns:
            地区分析结果字典
        """
        regional_stats = {}
        
        # 地区分布
        area_counts = df['area'].value_counts()
        regional_stats['distribution'] = area_counts.to_dict()
        
        # 各地区平均增长率
        area_growth = df.groupby('area').agg({
            'eps_growth': ['mean', 'median', 'count'],
            'revenue_growth': ['mean', 'median'],
            'current_revenue': ['mean', 'median']
        }).round(2)
        
        regional_stats['growth_stats'] = area_growth
        
        # 表现最好的地区
        avg_eps_growth = df.groupby('area')['eps_growth'].mean().sort_values(ascending=False)
        regional_stats['best_areas'] = avg_eps_growth.head(10).to_dict()
        
        return regional_stats
    
    def generate_top_picks(self, df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
        """
        生成顶级精选股票
        
        Args:
            df: 带质量评分的DataFrame
            top_n: 返回前N只股票
            
        Returns:
            顶级精选股票DataFrame
        """
        top_picks = df.head(top_n).copy()
        
        # 添加投资理由
        reasons = []
        for _, row in top_picks.iterrows():
            reason_list = []
            
            if row['eps_growth'] > 200:
                reason_list.append(f"超高EPS增长({row['eps_growth']:.1f}%)")
            elif row['eps_growth'] > 100:
                reason_list.append(f"高EPS增长({row['eps_growth']:.1f}%)")
            
            if row['revenue_growth'] > 100:
                reason_list.append(f"高收入增长({row['revenue_growth']:.1f}%)")
            elif row['revenue_growth'] > 50:
                reason_list.append(f"稳定收入增长({row['revenue_growth']:.1f}%)")
            
            if row['current_eps'] > 0.5:
                reason_list.append("高盈利能力")
            elif row['current_eps'] > 0:
                reason_list.append("盈利稳定")
            
            if row['current_revenue'] > 50:
                reason_list.append("大型企业")
            elif row['current_revenue'] > 10:
                reason_list.append("中型企业")
            
            reasons.append("; ".join(reason_list))
        
        top_picks['investment_reason'] = reasons
        
        return top_picks
    
    def print_comprehensive_report(self, df: pd.DataFrame):
        """
        打印综合分析报告
        
        Args:
            df: 带质量评分的DataFrame
        """
        print("\n" + "="*100)
        print("🎯 CANSLIM股票筛选 - 综合分析报告")
        print("="*100)
        
        # 基本统计
        print(f"\n📊 基本统计信息:")
        print(f"  • 符合条件股票总数: {len(df)}只")
        print(f"  • 平均EPS增长率: {df['eps_growth'].mean():.1f}%")
        print(f"  • EPS增长率中位数: {df['eps_growth'].median():.1f}%")
        print(f"  • 平均收入增长率: {df['revenue_growth'].mean():.1f}%")
        print(f"  • 收入增长率中位数: {df['revenue_growth'].median():.1f}%")
        print(f"  • 平均质量评分: {df['total_quality_score'].mean():.1f}分")
        
        # 行业分析
        industry_stats = self.industry_analysis(df)
        print(f"\n🏭 行业分析:")
        print(f"  • 涉及行业数量: {len(industry_stats['distribution'])}个")
        print("  • 股票数量前5行业:")
        for industry, count in list(industry_stats['distribution'].items())[:5]:
            print(f"    - {industry}: {count}只")
        
        print("  • EPS增长率前5行业:")
        for industry, growth in list(industry_stats['best_eps_industries'].items())[:5]:
            print(f"    - {industry}: {growth:.1f}%")
        
        # 地区分析
        regional_stats = self.regional_analysis(df)
        print(f"\n🗺️ 地区分析:")
        print("  • 股票数量前5地区:")
        for area, count in list(regional_stats['distribution'].items())[:5]:
            print(f"    - {area}: {count}只")
        
        # 顶级精选
        top_picks = self.generate_top_picks(df, 15)
        print(f"\n⭐ 顶级精选股票 (按质量评分排序):")
        print("-" * 120)
        print(f"{'排名':<4} {'代码':<12} {'名称':<16} {'行业':<12} {'EPS增长%':<10} {'收入增长%':<12} {'质量评分':<8} {'投资理由':<30}")
        print("-" * 120)
        
        for idx, (_, row) in enumerate(top_picks.iterrows(), 1):
            print(f"{idx:<4} {row['ts_code']:<12} {row['name']:<16} {row['industry']:<12} "
                  f"{row['eps_growth']:<10.1f} {row['revenue_growth']:<12.1f} "
                  f"{row['total_quality_score']:<8.1f} {row['investment_reason']:<30}")
        
        # 风险提示
        print(f"\n⚠️ 风险提示:")
        high_growth_count = len(df[df['eps_growth'] > 300])
        negative_eps_count = len(df[df['current_eps'] < 0])
        small_revenue_count = len(df[df['current_revenue'] < 5])
        
        if high_growth_count > 0:
            print(f"  • {high_growth_count}只股票EPS增长超过300%，需关注增长可持续性")
        if negative_eps_count > 0:
            print(f"  • {negative_eps_count}只股票当前EPS为负值，存在盈利风险")
        if small_revenue_count > 0:
            print(f"  • {small_revenue_count}只股票收入规模较小(< 5亿)，可能存在流动性风险")
        
        print(f"  • 建议分散投资，控制单只股票仓位")
        print(f"  • 持续关注季度业绩，及时调整持仓")
        
    def save_detailed_report(self, df: pd.DataFrame, filename: str = None):
        """
        保存详细报告到文件
        
        Args:
            df: 带质量评分的DataFrame
            filename: 输出文件名，如果为None则自动生成
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"detailed_analysis_{timestamp}.csv"
        
        filepath = os.path.join(self.cache_dir, filename)
        
        # 选择要保存的列
        columns_to_save = [
            'ts_code', 'name', 'industry', 'area',
            'current_eps', 'previous_eps', 'eps_growth',
            'current_revenue', 'previous_revenue', 'revenue_growth',
            'eps_quality_score', 'revenue_quality_score', 
            'size_quality_score', 'stability_quality_score',
            'total_quality_score', 'investment_reason'
        ]
        
        # 只保存存在的列
        existing_columns = [col for col in columns_to_save if col in df.columns]
        df[existing_columns].to_csv(filepath, index=False, encoding='utf-8-sig')
        
        logger.info(f"详细分析报告已保存到: {filepath}")
        
    def analyze(self, load_latest: bool = True) -> pd.DataFrame:
        """
        执行完整分析
        
        Args:
            load_latest: 是否加载最新结果
            
        Returns:
            分析后的DataFrame
        """
        if load_latest or self.results_df is None:
            df = self.load_latest_results()
        else:
            df = self.results_df
            
        if df.empty:
            logger.error("没有数据可供分析")
            return df
            
        # 质量评分
        df_scored = self.quality_score_analysis(df)
        
        # 生成顶级精选
        df_scored = self.generate_top_picks(df_scored, len(df_scored))
        
        # 打印报告
        self.print_comprehensive_report(df_scored)
        
        # 保存详细报告
        self.save_detailed_report(df_scored)
        
        return df_scored


def main():
    """主函数"""
    try:
        analyzer = ScreeningAnalyzer()
        
        print("🔍 开始分析筛选结果...")
        results = analyzer.analyze()
        
        if not results.empty:
            print(f"\n✅ 分析完成！共分析了 {len(results)} 只股票")
            print("详细结果已保存到文件中。")
        
    except Exception as e:
        logger.error(f"分析过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
