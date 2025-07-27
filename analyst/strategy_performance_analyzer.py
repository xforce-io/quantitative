#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Strategy Performance Analyzer
策略性能分析工具

分析获利高的策略特征，进行相关度分析
Analyze high-profit strategy characteristics and perform correlation analysis
"""

import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class StrategyPerformanceAnalyzer:
    """策略性能分析器"""
    
    def __init__(self, data_dir: str = "data/expr"):
        self.dataDir = Path(data_dir)
        self.results = []
        self.df = None
        
    def loadExperimentData(self) -> None:
        """加载实验数据"""
        print("📊 加载实验数据...")
        
        for experiment_dir in self.dataDir.iterdir():
            if experiment_dir.is_dir():
                results_file = experiment_dir / "all_results.json"
                if results_file.exists():
                    try:
                        with open(results_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # 添加实验信息
                        for item in data:
                            item['experiment_name'] = experiment_dir.name
                            item['experiment_date'] = experiment_dir.name.split('_')[1] if '_' in experiment_dir.name else 'unknown'
                        
                        self.results.extend(data)
                        print(f"✅ 加载实验: {experiment_dir.name} ({len(data)} 个策略)")
                        
                    except Exception as e:
                        print(f"❌ 加载失败 {experiment_dir.name}: {e}")
        
        print(f"📈 总共加载了 {len(self.results)} 个策略结果")
    
    def createDataFrame(self) -> None:
        """创建分析用的DataFrame"""
        if not self.results:
            print("❌ 没有数据可分析")
            return
        
        # 提取关键特征
        data = []
        for result in self.results:
            row = {
                # 基本信息
                'agent_name': result['agent_name'],
                'strategy_type': result['strategy_type'],
                'experiment_name': result['experiment_name'],
                'rank': result['rank'],
                
                # 策略参数
                'base_ratio': result['config']['parameters'].get('baseRatio', 0),
                'max_position': result['config']['parameters'].get('maxPosition', 100000),
                'commission': result['config']['parameters'].get('commission', 0.0003),
                'risk_profile': result['config'].get('riskProfile', 'unknown'),
                
                # 网格策略特有参数
                'grid_levels': result['config']['parameters'].get('gridLevels', 0),
                'grid_spacing': result['config']['parameters'].get('gridSpacing', 0),
                'slippage': result['config']['parameters'].get('slippage', 0),
                
                # DCA策略特有参数
                'interval': result['config']['parameters'].get('interval', ''),
                'amount': result['config']['parameters'].get('amount', 0),
                
                # 动量策略特有参数
                'lookback_period': result['config']['parameters'].get('lookbackPeriod', 0),
                'threshold': result['config']['parameters'].get('threshold', 0),
                
                # 性能指标
                'total_return': result['performance']['totalReturn'],
                'sharpe_ratio': result['performance']['sharpeRatio'],
                'max_drawdown': abs(result['performance']['maxDrawdown']),
                'win_rate': result['performance']['winRate'],
                'total_trades': result['performance']['totalTrades'],
                'volatility': result['performance']['volatility'],
                'beta': result['performance']['beta'],
                'alpha': result['performance']['alpha'],
                'calmar_ratio': result['performance']['calmarRatio'],
                'profit_factor': result['performance']['profitFactor'] if result['performance']['profitFactor'] != float('inf') else 1000,
                'avg_profit': result['performance']['avgProfit'],
                'benchmark_return': result['performance']['benchmarkReturn'],
                
                # 衍生指标
                'excess_return': result['performance']['totalReturn'] - result['performance']['benchmarkReturn'],
                'risk_adjusted_return': result['performance']['totalReturn'] / max(abs(result['performance']['maxDrawdown']), 0.01),
                'trade_efficiency': result['performance']['totalReturn'] / max(result['performance']['totalTrades'], 1)
            }
            data.append(row)
        
        self.df = pd.DataFrame(data)
        print(f"✅ 创建DataFrame: {self.df.shape[0]} 行, {self.df.shape[1]} 列")
    
    def analyzeHighProfitStrategies(self, top_n: int = 10) -> pd.DataFrame:
        """分析获利最高的策略"""
        if self.df is None:
            print("❌ 请先加载数据")
            return pd.DataFrame()
        
        # 按总收益率排序
        top_strategies = self.df.nlargest(top_n, 'total_return')
        
        print(f"\n🏆 获利最高的前 {top_n} 个策略:")
        print("=" * 80)
        
        for i, (_, row) in enumerate(top_strategies.iterrows(), 1):
            print(f"{i:2d}. {row['agent_name']:<30} | "
                  f"收益率: {row['total_return']:>7.2%} | "
                  f"夏普: {row['sharpe_ratio']:>5.2f} | "
                  f"回撤: {row['max_drawdown']:>6.2%} | "
                  f"胜率: {row['win_rate']:>5.1%}")
        
        return top_strategies
    
    def analyzeStrategyTypePerformance(self) -> Dict:
        """分析不同策略类型的性能"""
        if self.df is None:
            return {}
        
        strategy_stats = {}
        
        for strategy_type in self.df['strategy_type'].unique():
            subset = self.df[self.df['strategy_type'] == strategy_type]
            
            stats = {
                'count': len(subset),
                'avg_return': subset['total_return'].mean(),
                'avg_sharpe': subset['sharpe_ratio'].mean(),
                'avg_drawdown': subset['max_drawdown'].mean(),
                'avg_win_rate': subset['win_rate'].mean(),
                'best_return': subset['total_return'].max(),
                'best_sharpe': subset['sharpe_ratio'].max(),
                'worst_return': subset['total_return'].min(),
                'std_return': subset['total_return'].std(),
                'median_return': subset['total_return'].median()
            }
            
            strategy_stats[strategy_type] = stats
        
        print(f"\n📊 策略类型性能对比:")
        print("=" * 80)
        for strategy_type, stats in strategy_stats.items():
            print(f"{strategy_type.upper():<12} | "
                  f"数量: {stats['count']:>3} | "
                  f"平均收益: {stats['avg_return']:>7.2%} | "
                  f"最佳收益: {stats['best_return']:>7.2%} | "
                  f"平均夏普: {stats['avg_sharpe']:>5.2f}")
        
        return strategy_stats
    
    def correlationAnalysis(self) -> pd.DataFrame:
        """进行相关度分析"""
        if self.df is None:
            return pd.DataFrame()
        
        # 选择数值型特征进行相关性分析
        numeric_columns = [
            'total_return', 'sharpe_ratio', 'max_drawdown', 'win_rate', 
            'total_trades', 'volatility', 'beta', 'alpha', 'calmar_ratio',
            'base_ratio', 'grid_levels', 'grid_spacing', 'amount', 
            'lookback_period', 'threshold', 'excess_return', 
            'risk_adjusted_return', 'trade_efficiency'
        ]
        
        # 过滤存在的列
        available_columns = [col for col in numeric_columns if col in self.df.columns]
        correlation_df = self.df[available_columns].corr()
        
        print(f"\n🔍 相关性分析 (与总收益率的相关度):")
        print("=" * 60)
        
        # 获取与总收益率的相关性
        return_correlations = correlation_df['total_return'].sort_values(key=abs, ascending=False)
        
        for feature, corr in return_correlations.items():
            if feature != 'total_return':
                direction = "正相关" if corr > 0 else "负相关"
                strength = "强" if abs(corr) > 0.5 else "中等" if abs(corr) > 0.3 else "弱"
                print(f"{feature:<20} | {corr:>6.3f} | {strength} {direction}")
        
        return correlation_df
    
    def parameterImpactAnalysis(self) -> Dict:
        """分析参数对收益的影响"""
        if self.df is None:
            return {}
        
        impact_analysis = {}
        
        # 分析基础比率的影响
        if 'base_ratio' in self.df.columns:
            base_ratio_groups = self.df.groupby(pd.cut(self.df['base_ratio'], bins=5))
            impact_analysis['base_ratio'] = {
                'groups': base_ratio_groups['total_return'].mean().to_dict(),
                'correlation': self.df['base_ratio'].corr(self.df['total_return'])
            }
        
        # 分析网格层数的影响
        if 'grid_levels' in self.df.columns:
            grid_data = self.df[self.df['grid_levels'] > 0]
            if not grid_data.empty:
                grid_levels_groups = grid_data.groupby('grid_levels')
                impact_analysis['grid_levels'] = {
                    'groups': grid_levels_groups['total_return'].mean().to_dict(),
                    'correlation': self.df['grid_levels'].corr(self.df['total_return'])
                }
        
        # 分析网格间距的影响
        if 'grid_spacing' in self.df.columns:
            grid_spacing_groups = self.df[self.df['grid_spacing'] > 0].groupby(pd.cut(self.df['grid_spacing'], bins=5))
            impact_analysis['grid_spacing'] = {
                'groups': grid_spacing_groups['total_return'].mean().to_dict(),
                'correlation': self.df['grid_spacing'].corr(self.df['total_return'])
            }
        
        print(f"\n🎯 参数影响分析:")
        print("=" * 60)
        
        for param, analysis in impact_analysis.items():
            print(f"\n{param.upper()}:")
            print(f"  与总收益率相关性: {analysis['correlation']:.3f}")
            if 'groups' in analysis:
                print(f"  分组平均收益:")
                for group, avg_return in analysis['groups'].items():
                    print(f"    {group}: {avg_return:.2%}")
        
        return impact_analysis
    
    def generateVisualizations(self, output_dir: str = "reports/strategy_analysis") -> None:
        """生成可视化图表"""
        if self.df is None:
            return
        
        # 创建输出目录
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 设置图表样式
        plt.style.use('seaborn-v0_8')
        fig_size = (12, 8)
        
        # 1. 策略类型收益分布
        plt.figure(figsize=fig_size)
        strategy_types = self.df['strategy_type'].unique()
        returns_by_type = [self.df[self.df['strategy_type'] == st]['total_return'] for st in strategy_types]
        
        plt.boxplot(returns_by_type, labels=[st.upper() for st in strategy_types])
        plt.title('不同策略类型的收益分布', fontsize=14, fontweight='bold')
        plt.ylabel('总收益率')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path / 'strategy_type_returns.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. 收益 vs 风险散点图
        plt.figure(figsize=fig_size)
        colors = {'dca': 'blue', 'grid': 'green', 'momentum': 'red'}
        
        for strategy_type in strategy_types:
            subset = self.df[self.df['strategy_type'] == strategy_type]
            plt.scatter(subset['max_drawdown'], subset['total_return'], 
                       c=colors.get(strategy_type, 'gray'), 
                       label=strategy_type.upper(), alpha=0.7, s=50)
        
        plt.xlabel('最大回撤')
        plt.ylabel('总收益率')
        plt.title('收益 vs 风险散点图', fontsize=14, fontweight='bold')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path / 'return_vs_risk.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 3. 相关性热力图
        numeric_columns = ['total_return', 'sharpe_ratio', 'max_drawdown', 'win_rate', 
                          'total_trades', 'volatility', 'base_ratio']
        available_columns = [col for col in numeric_columns if col in self.df.columns]
        
        if len(available_columns) > 1:
            correlation_matrix = self.df[available_columns].corr()
            
            plt.figure(figsize=(10, 8))
            sns.heatmap(correlation_matrix, annot=True, cmap='coolwarm', center=0,
                       square=True, fmt='.2f', cbar_kws={'shrink': 0.8})
            plt.title('策略指标相关性热力图', fontsize=14, fontweight='bold')
            plt.tight_layout()
            plt.savefig(output_path / 'correlation_heatmap.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        # 4. 参数影响分析图
        if 'base_ratio' in self.df.columns:
            plt.figure(figsize=fig_size)
            plt.scatter(self.df['base_ratio'], self.df['total_return'], alpha=0.6, s=50)
            plt.xlabel('基础比率')
            plt.ylabel('总收益率')
            plt.title('基础比率对收益的影响', fontsize=14, fontweight='bold')
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(output_path / 'base_ratio_impact.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        print(f"📊 可视化图表已保存到: {output_path}")
    
    def generateReport(self, output_file: str = "reports/strategy_analysis_report.md") -> None:
        """生成分析报告"""
        if self.df is None:
            return
        
        # 确保输出目录存在
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 获取分析结果
        top_strategies = self.analyzeHighProfitStrategies(10)
        strategy_stats = self.analyzeStrategyTypePerformance()
        correlation_df = self.correlationAnalysis()
        impact_analysis = self.parameterImpactAnalysis()
        
        # 生成报告
        report_content = f"""# 策略性能分析报告

## 📊 数据概览
- 总策略数量: {len(self.df)}
- 策略类型: {', '.join(self.df['strategy_type'].unique())}
- 实验数量: {len(self.df['experiment_name'].unique())}

## 🏆 最佳策略特征

### 前10名策略
| 排名 | 策略名称 | 策略类型 | 总收益率 | 夏普比率 | 最大回撤 | 胜率 |
|------|----------|----------|----------|----------|----------|------|
"""
        
        for i, (_, row) in enumerate(top_strategies.iterrows(), 1):
            report_content += f"| {i} | {row['agent_name']} | {row['strategy_type']} | {row['total_return']:.2%} | {row['sharpe_ratio']:.2f} | {row['max_drawdown']:.2%} | {row['win_rate']:.1%} |\n"
        
        report_content += f"""

## 📈 策略类型性能对比

"""
        
        for strategy_type, stats in strategy_stats.items():
            report_content += f"""
### {strategy_type.upper()} 策略
- 策略数量: {stats['count']}
- 平均收益率: {stats['avg_return']:.2%}
- 最佳收益率: {stats['best_return']:.2%}
- 平均夏普比率: {stats['avg_sharpe']:.2f}
- 平均最大回撤: {stats['avg_drawdown']:.2%}
- 收益率标准差: {stats['std_return']:.2%}

"""
        
        report_content += f"""
## 🔍 相关性分析

### 与总收益率的相关度 (按绝对值排序)
"""
        
        if not correlation_df.empty and 'total_return' in correlation_df.columns:
            return_correlations = correlation_df['total_return'].sort_values(key=abs, ascending=False)
            for feature, corr in return_correlations.items():
                if feature != 'total_return':
                    direction = "正相关" if corr > 0 else "负相关"
                    strength = "强" if abs(corr) > 0.5 else "中等" if abs(corr) > 0.3 else "弱"
                    report_content += f"- **{feature}**: {corr:.3f} ({strength} {direction})\n"
        
        report_content += f"""
## 🎯 关键发现

### 1. 高收益策略的共同特征
"""
        
        # 分析高收益策略的特征
        high_return_threshold = self.df['total_return'].quantile(0.8)
        high_return_strategies = self.df[self.df['total_return'] >= high_return_threshold]
        
        if not high_return_strategies.empty:
            report_content += f"""
- **策略类型分布**: {high_return_strategies['strategy_type'].value_counts().to_dict()}
- **平均基础比率**: {high_return_strategies['base_ratio'].mean():.2f}
- **平均夏普比率**: {high_return_strategies['sharpe_ratio'].mean():.2f}
- **平均胜率**: {high_return_strategies['win_rate'].mean():.1%}
- **平均交易次数**: {high_return_strategies['total_trades'].mean():.1f}
"""
        
        report_content += f"""
### 2. 参数优化建议
"""
        
        for param, analysis in impact_analysis.items():
            if 'correlation' in analysis:
                report_content += f"""
- **{param}**: 相关性 {analysis['correlation']:.3f}
"""
        
        report_content += f"""
### 3. 风险管理建议
- 建议最大回撤控制在 30% 以内
- 夏普比率应大于 1.0
- 胜率应保持在 70% 以上

## 📊 可视化图表
相关图表已生成并保存到 `reports/strategy_analysis/` 目录。

---
*报告生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        # 保存报告
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        print(f"📄 分析报告已保存到: {output_path}")

def main():
    """主函数"""
    print("🚀 策略性能分析工具启动")
    print("=" * 60)
    
    # 创建分析器
    analyzer = StrategyPerformanceAnalyzer()
    
    # 加载数据
    analyzer.loadExperimentData()
    
    if not analyzer.results:
        print("❌ 没有找到实验数据")
        return
    
    # 创建DataFrame
    analyzer.createDataFrame()
    
    # 执行分析
    print("\n" + "="*60)
    print("📊 开始策略性能分析")
    print("="*60)
    
    # 分析高收益策略
    top_strategies = analyzer.analyzeHighProfitStrategies(10)
    
    # 策略类型性能对比
    strategy_stats = analyzer.analyzeStrategyTypePerformance()
    
    # 相关性分析
    correlation_df = analyzer.correlationAnalysis()
    
    # 参数影响分析
    impact_analysis = analyzer.parameterImpactAnalysis()
    
    # 生成可视化
    analyzer.generateVisualizations()
    
    # 生成报告
    analyzer.generateReport()
    
    print("\n✅ 分析完成！")
    print("📊 可视化图表: reports/strategy_analysis/")
    print("📄 详细报告: reports/strategy_analysis_report.md")

if __name__ == "__main__":
    main() 