#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资金流向可视化模块 (Capital Flow Visualizer)

提供资金流向分析的图表生成功能，包括：
1. 个股资金流向时序图
2. 板块资金流向对比图
3. 行业资金流向热力图
4. 资金流向趋势分析图
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import seaborn as sns
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import warnings

from quant.core.logging_config import get_logger
logger = get_logger(__name__)

warnings.filterwarnings('ignore')

# 设置中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class CapitalFlowVisualizer:
    """资金流向可视化器"""

    def __init__(self, output_dir: str = 'reports/capital_flow'):
        """
        初始化可视化器

        Args:
            output_dir: 输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 配色方案
        self.colors = {
            'inflow': '#FF6B6B',      # 流入 - 红色
            'outflow': '#4ECDC4',     # 流出 - 青色
            'main': '#FF6B6B',        # 主力资金
            'large': '#FFA07A',       # 大单
            'mid': '#FFD700',         # 中单
            'small': '#87CEEB',       # 小单
            'positive': '#FF6B6B',
            'negative': '#4ECDC4',
            'neutral': '#95A5A6'
        }

    def plot_stock_flow_timeline(
        self,
        flow_data: pd.DataFrame,
        symbol: str,
        save_path: Optional[str] = None
    ) -> str:
        """
        绘制个股资金流向时序图

        Args:
            flow_data: 资金流向数据（DataFrame with columns: date, main_inflow, large_inflow, etc.）
            symbol: 股票代码
            save_path: 保存路径

        Returns:
            图表保存路径
        """
        fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
        fig.suptitle(f'{symbol} 资金流向分析', fontsize=16, fontweight='bold')

        # 确保数据有日期索引
        if 'date' in flow_data.columns:
            flow_data = flow_data.set_index('date')

        flow_data.index = pd.to_datetime(flow_data.index)

        # 图1: 主力资金净流入
        ax1 = axes[0]
        if 'net_main_amount' in flow_data.columns:
            colors = [self.colors['inflow'] if x >= 0 else self.colors['outflow']
                     for x in flow_data['net_main_amount']]
            ax1.bar(flow_data.index, flow_data['net_main_amount'], color=colors, alpha=0.7)
            ax1.axhline(y=0, color='gray', linestyle='--', linewidth=0.8)
            ax1.set_ylabel('主力资金净流入 (元)', fontsize=11)
            ax1.set_title('主力资金净流入', fontsize=12, fontweight='bold')
            ax1.grid(True, alpha=0.3)

        # 图2: 各类资金流向堆叠图
        ax2 = axes[1]
        flow_cols = ['small_net_amount', 'mid_net_amount', 'large_net_amount', 'xlarge_net_amount']
        available_cols = [col for col in flow_cols if col in flow_data.columns]

        if available_cols:
            flow_subset = flow_data[available_cols].fillna(0)
            # 分离正负值
            positive = flow_subset.clip(lower=0)
            negative = flow_subset.clip(upper=0)

            labels = {'small_net_amount': '散户', 'mid_net_amount': '中户',
                     'large_net_amount': '大户', 'xlarge_net_amount': '超大户'}

            ax2.bar(flow_data.index, positive['small_net_amount'] if 'small_net_amount' in positive.columns else 0,
                   label=labels.get('small_net_amount', '散户'), color=self.colors['small'], alpha=0.8)
            ax2.bar(flow_data.index, positive['mid_net_amount'] if 'mid_net_amount' in positive.columns else 0,
                   bottom=positive['small_net_amount'] if 'small_net_amount' in positive.columns else 0,
                   label=labels.get('mid_net_amount', '中户'), color=self.colors['mid'], alpha=0.8)

            ax2.axhline(y=0, color='gray', linestyle='--', linewidth=0.8)
            ax2.set_ylabel('资金流向 (元)', fontsize=11)
            ax2.set_title('各类资金流向分布', fontsize=12, fontweight='bold')
            ax2.legend(loc='upper left', fontsize=9)
            ax2.grid(True, alpha=0.3)

        # 图3: 主力资金流入比例
        ax3 = axes[2]
        if 'main_inflow_ratio' in flow_data.columns:
            colors = [self.colors['inflow'] if x >= 0 else self.colors['outflow']
                     for x in flow_data['main_inflow_ratio']]
            ax3.fill_between(flow_data.index, 0, flow_data['main_inflow_ratio'],
                            color=colors, alpha=0.3)
            ax3.plot(flow_data.index, flow_data['main_inflow_ratio'],
                    color='darkblue', linewidth=1.5, alpha=0.8)
            ax3.axhline(y=0, color='gray', linestyle='--', linewidth=0.8)
            ax3.set_ylabel('主力净流入比例 (%)', fontsize=11)
            ax3.set_title('主力资金净流入比例', fontsize=12, fontweight='bold')
            ax3.grid(True, alpha=0.3)

        # 格式化x轴日期
        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())

        plt.xticks(rotation=45)
        plt.tight_layout()

        # 保存图表
        if save_path is None:
            save_path = self.output_dir / f'{symbol}_flow_timeline.png'

        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()

        return str(save_path)

    def plot_sector_flow_comparison(
        self,
        sector_data: Dict[str, Dict[str, Any]],
        sector_name: str,
        save_path: Optional[str] = None
    ) -> str:
        """
        绘制板块资金流向对比图

        Args:
            sector_data: 板块数据 {symbol: flow_analysis_result}
            sector_name: 板块名称
            save_path: 保存路径

        Returns:
            图表保存路径
        """
        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        fig.suptitle(f'{sector_name} 板块资金流向分析', fontsize=16, fontweight='bold')

        # 提取数据
        symbols = list(sector_data.keys())
        main_inflows = [data.get('main_inflow_ratio', 0) for data in sector_data.values()]
        flow_scores = [data.get('comprehensive_score', 0) for data in sector_data.values()]
        consistency = [data.get('flow_consistency', 0) for data in sector_data.values()]
        institutional = [data.get('institutional_activity', 0) for data in sector_data.values()]

        # 图1: 主力资金净流入对比
        ax1 = axes[0, 0]
        colors = [self.colors['inflow'] if x >= 0 else self.colors['outflow'] for x in main_inflows]
        bars1 = ax1.barh(symbols, main_inflows, color=colors, alpha=0.7)
        ax1.axvline(x=0, color='gray', linestyle='--', linewidth=0.8)
        ax1.set_xlabel('主力净流入比例 (%)', fontsize=10)
        ax1.set_title('主力资金净流入对比', fontsize=12, fontweight='bold')
        ax1.grid(True, alpha=0.3, axis='x')

        # 图2: 综合评分对比
        ax2 = axes[0, 1]
        colors2 = [self._get_score_color(score) for score in flow_scores]
        bars2 = ax2.barh(symbols, flow_scores, color=colors2, alpha=0.7)
        ax2.set_xlabel('综合评分', fontsize=10)
        ax2.set_title('资金流向综合评分', fontsize=12, fontweight='bold')
        ax2.set_xlim(0, 100)
        ax2.grid(True, alpha=0.3, axis='x')

        # 图3: 资金流向一致性
        ax3 = axes[1, 0]
        ax3.bar(range(len(symbols)), consistency, color=self.colors['neutral'], alpha=0.7)
        ax3.set_xticks(range(len(symbols)))
        ax3.set_xticklabels(symbols, rotation=45, ha='right')
        ax3.set_ylabel('一致性评分', fontsize=10)
        ax3.set_title('资金流向一致性', fontsize=12, fontweight='bold')
        ax3.set_ylim(0, 1)
        ax3.grid(True, alpha=0.3, axis='y')

        # 图4: 机构活跃度
        ax4 = axes[1, 1]
        ax4.bar(range(len(symbols)), institutional, color=self.colors['main'], alpha=0.7)
        ax4.set_xticks(range(len(symbols)))
        ax4.set_xticklabels(symbols, rotation=45, ha='right')
        ax4.set_ylabel('机构活跃度', fontsize=10)
        ax4.set_title('机构活跃度对比', fontsize=12, fontweight='bold')
        ax4.set_ylim(0, 1)
        ax4.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()

        # 保存图表
        if save_path is None:
            save_path = self.output_dir / f'{sector_name}_sector_comparison.png'

        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()

        return str(save_path)

    def plot_industry_flow_heatmap(
        self,
        industry_data: Dict[str, Dict[str, Any]],
        days: int = 30,
        save_path: Optional[str] = None
    ) -> str:
        """
        绘制行业资金流向热力图

        Args:
            industry_data: 行业数据 {industry_name: {metrics}}
            days: 分析天数
            save_path: 保存路径

        Returns:
            图表保存路径
        """
        fig, ax = plt.subplots(figsize=(14, 8))
        fig.suptitle(f'行业资金流向热力图 ({days}天)', fontsize=16, fontweight='bold')

        # 准备热力图数据
        industries = list(industry_data.keys())
        metrics = ['avg_inflow_ratio', 'sector_consistency', 'sector_heat_score', 'avg_institutional_activity']
        metric_labels = ['平均流入比例', '板块一致性', '热度评分', '机构活跃度']

        # 构建数据矩阵
        data_matrix = []
        for industry in industries:
            row = []
            for metric in metrics:
                value = industry_data[industry].get(metric, 0)
                # 标准化处理
                if metric == 'avg_inflow_ratio':
                    value = value * 100  # 转换为百分比
                elif metric == 'sector_heat_score':
                    value = value  # 保持原值
                row.append(value)
            data_matrix.append(row)

        data_matrix = np.array(data_matrix)

        # 绘制热力图
        im = ax.imshow(data_matrix, cmap='RdYlGn', aspect='auto', vmin=-10, vmax=10)

        # 设置坐标轴
        ax.set_xticks(np.arange(len(metric_labels)))
        ax.set_yticks(np.arange(len(industries)))
        ax.set_xticklabels(metric_labels, fontsize=11)
        ax.set_yticklabels(industries, fontsize=10)

        # 旋转x轴标签
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

        # 添加数值标注
        for i in range(len(industries)):
            for j in range(len(metrics)):
                text = ax.text(j, i, f'{data_matrix[i, j]:.2f}',
                             ha="center", va="center", color="black", fontsize=9)

        # 添加颜色条
        cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label('强度', rotation=270, labelpad=15, fontsize=11)

        plt.tight_layout()

        # 保存图表
        if save_path is None:
            save_path = self.output_dir / f'industry_flow_heatmap_{days}days.png'

        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()

        return str(save_path)

    def plot_industry_ranking(
        self,
        industry_data: Dict[str, Dict[str, Any]],
        metric: str = 'avg_inflow_ratio',
        top_n: int = 15,
        save_path: Optional[str] = None
    ) -> str:
        """
        绘制行业排名图

        Args:
            industry_data: 行业数据
            metric: 排名指标
            top_n: 显示前N个行业
            save_path: 保存路径

        Returns:
            图表保存路径
        """
        fig, ax = plt.subplots(figsize=(12, 8))

        metric_labels = {
            'avg_inflow_ratio': '平均资金流入比例',
            'sector_heat_score': '板块热度评分',
            'sector_consistency': '板块一致性'
        }

        title = f'行业{metric_labels.get(metric, metric)}排名 (Top {top_n})'
        fig.suptitle(title, fontsize=16, fontweight='bold')

        # 排序
        sorted_industries = sorted(
            industry_data.items(),
            key=lambda x: x[1].get(metric, 0),
            reverse=True
        )[:top_n]

        industries = [item[0] for item in sorted_industries]
        values = [item[1].get(metric, 0) for item in sorted_industries]

        # 根据值设置颜色
        colors = [self._get_value_color(v, metric) for v in values]

        # 绘制条形图
        bars = ax.barh(industries, values, color=colors, alpha=0.7)
        ax.axvline(x=0, color='gray', linestyle='--', linewidth=0.8)
        ax.set_xlabel(metric_labels.get(metric, metric), fontsize=11)
        ax.grid(True, alpha=0.3, axis='x')

        # 添加数值标签
        for i, (bar, value) in enumerate(zip(bars, values)):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2,
                   f'{value:.2f}',
                   ha='left' if width >= 0 else 'right',
                   va='center',
                   fontsize=9)

        plt.tight_layout()

        # 保存图表
        if save_path is None:
            save_path = self.output_dir / f'industry_ranking_{metric}.png'

        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()

        return str(save_path)

    def plot_flow_trend_analysis(
        self,
        trend_data: pd.DataFrame,
        industry_name: str,
        save_path: Optional[str] = None
    ) -> str:
        """
        绘制资金流向趋势分析图

        Args:
            trend_data: 趋势数据（时序）
            industry_name: 行业名称
            save_path: 保存路径

        Returns:
            图表保存路径
        """
        fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
        fig.suptitle(f'{industry_name} 资金流向趋势分析', fontsize=16, fontweight='bold')

        # 确保数据有日期索引
        if 'date' in trend_data.columns:
            trend_data = trend_data.set_index('date')
        trend_data.index = pd.to_datetime(trend_data.index)

        # 图1: 累计资金流向
        ax1 = axes[0]
        if 'cumulative_flow' in trend_data.columns:
            ax1.fill_between(trend_data.index, 0, trend_data['cumulative_flow'],
                           where=trend_data['cumulative_flow'] >= 0,
                           color=self.colors['inflow'], alpha=0.3, label='累计流入')
            ax1.fill_between(trend_data.index, 0, trend_data['cumulative_flow'],
                           where=trend_data['cumulative_flow'] < 0,
                           color=self.colors['outflow'], alpha=0.3, label='累计流出')
            ax1.plot(trend_data.index, trend_data['cumulative_flow'],
                    color='darkblue', linewidth=2, alpha=0.8)
            ax1.axhline(y=0, color='gray', linestyle='--', linewidth=0.8)
            ax1.set_ylabel('累计资金流向', fontsize=11)
            ax1.set_title('累计资金流向趋势', fontsize=12, fontweight='bold')
            ax1.legend(loc='upper left', fontsize=9)
            ax1.grid(True, alpha=0.3)

        # 图2: 日资金流向与移动平均
        ax2 = axes[1]
        if 'daily_flow' in trend_data.columns:
            colors = [self.colors['inflow'] if x >= 0 else self.colors['outflow']
                     for x in trend_data['daily_flow']]
            ax2.bar(trend_data.index, trend_data['daily_flow'], color=colors, alpha=0.5, label='日资金流向')

            # 添加移动平均线
            if len(trend_data) >= 5:
                ma5 = trend_data['daily_flow'].rolling(window=5).mean()
                ax2.plot(trend_data.index, ma5, color='red', linewidth=2, label='5日均线', alpha=0.8)

            if len(trend_data) >= 10:
                ma10 = trend_data['daily_flow'].rolling(window=10).mean()
                ax2.plot(trend_data.index, ma10, color='blue', linewidth=2, label='10日均线', alpha=0.8)

            ax2.axhline(y=0, color='gray', linestyle='--', linewidth=0.8)
            ax2.set_ylabel('日资金流向', fontsize=11)
            ax2.set_title('日资金流向及均线', fontsize=12, fontweight='bold')
            ax2.legend(loc='upper left', fontsize=9)
            ax2.grid(True, alpha=0.3)

        # 格式化x轴日期
        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())

        plt.xticks(rotation=45)
        plt.tight_layout()

        # 保存图表
        if save_path is None:
            save_path = self.output_dir / f'{industry_name}_flow_trend.png'

        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()

        return str(save_path)

    def _get_score_color(self, score: float) -> str:
        """根据评分获取颜色"""
        if score >= 70:
            return self.colors['inflow']
        elif score >= 40:
            return self.colors['neutral']
        else:
            return self.colors['outflow']

    def _get_value_color(self, value: float, metric: str) -> str:
        """根据指标值获取颜色"""
        if metric == 'avg_inflow_ratio':
            return self.colors['inflow'] if value >= 0 else self.colors['outflow']
        elif metric in ['sector_heat_score', 'sector_consistency']:
            if value >= 60:
                return self.colors['inflow']
            elif value >= 30:
                return self.colors['neutral']
            else:
                return self.colors['outflow']
        return self.colors['neutral']


def test_visualizer():
    """测试可视化器"""
    logger.info("🎨 测试资金流向可视化器...")

    visualizer = CapitalFlowVisualizer()

    # 测试数据
    dates = pd.date_range('2024-01-01', periods=30, freq='D')
    test_flow_data = pd.DataFrame({
        'date': dates,
        'net_main_amount': np.random.randn(30) * 1e7,
        'main_inflow_ratio': np.random.randn(30) * 5,
        'small_net_amount': np.random.randn(30) * 1e6,
        'mid_net_amount': np.random.randn(30) * 5e6,
        'large_net_amount': np.random.randn(30) * 1e7,
        'xlarge_net_amount': np.random.randn(30) * 2e7
    })

    # 测试时序图
    path = visualizer.plot_stock_flow_timeline(test_flow_data, '002594.SZ')
    logger.info("✅ 时序图已保存: {path}")

    logger.info("\n✅ 可视化器测试完成")


if __name__ == '__main__':
    test_visualizer()