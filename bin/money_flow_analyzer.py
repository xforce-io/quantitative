#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
资金流向分析与可视化工具 (Money Flow Analyzer)

功能：
1. 行业资金流向分析与可视化 (Top流入/流出)
2. 市场整体资金情绪可视化 (机构 vs 散户)
3. 个股资金流向趋势分析与绘图 (股价 vs 资金流)
4. 北向资金分析
"""

import sys
import os
import argparse
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
from pathlib import Path

import pandas as pd
import numpy as np

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from quant.core.logging_config import get_logger
from quant.data.implementations.tushare_provider import TushareProvider

logger = get_logger(__name__)

class MoneyFlowAnalyzer:
    """资金流向分析器"""
    
    def __init__(self):
        self.provider = TushareProvider()
        
    def analyze_industry_flow(self, trade_date: str) -> Dict:
        """分析行业资金流向"""
        logger.info(f"正在分析 {trade_date} 的行业资金流向...")
        df = self.provider.get_industry_money_flow_dc(trade_date=trade_date)
        
        if df.empty:
            logger.warning(f"未找到 {trade_date} 的行业资金流向数据")
            return {'error': 'No data found'}
            
        # 整理数据
        result = {
            'trade_date': trade_date,
            'total_industries': len(df),
            'net_inflow_count': len(df[df['net_amount'] > 0]),
            'net_outflow_count': len(df[df['net_amount'] < 0]),
            'top_inflow': [],
            'top_outflow': []
        }
        
        # 获取Top 10流入
        if 'net_amount' in df.columns:
            top_in = df.nlargest(10, 'net_amount')
            for _, row in top_in.iterrows():
                result['top_inflow'].append({
                    'name': row['name'],
                    'net_amount': float(row['net_amount']),
                    'pct_change': float(row.get('pct_change', 0))
                })
                
            # 获取Top 10流出
            top_out = df.nsmallest(10, 'net_amount')
            for _, row in top_out.iterrows():
                result['top_outflow'].append({
                    'name': row['name'],
                    'net_amount': float(row['net_amount']),
                    'pct_change': float(row.get('pct_change', 0))
                })
                
        return result

    def analyze_stock_flow(self, symbol: str, start_date: str, end_date: str) -> Dict:
        """分析个股资金流向趋势"""
        logger.info(f"正在分析 {symbol} ({start_date}-{end_date}) 的资金流向...")
        
        # 获取资金流数据
        result = self.provider.analyze_institutional_vs_retail(symbol, start_date, end_date)
        
        if 'error' in result:
            return result
            
        # 获取股价数据用于对比
        try:
            price_df = self.provider.get_stock_data(symbol, start_date, end_date)
            if not price_df.empty:
                # 合并数据
                flow_df = result['flow_data']
                
                # 确保索引类型一致
                if not isinstance(flow_df.index, pd.DatetimeIndex):
                    flow_df.index = pd.to_datetime(flow_df.index)
                if not isinstance(price_df.index, pd.DatetimeIndex):
                    price_df.index = pd.to_datetime(price_df.index)
                    
                # 合并，使用 flow_df 的索引（交易日）
                combined = flow_df.join(price_df[['close', 'pct_chg'] if 'pct_chg' in price_df.columns else ['close']], how='left')
                
                # 将合并后的数据转为 list 存回 result，方便序列化和绘图
                records = []
                for date, row in combined.iterrows():
                    record = {
                        'date': date.strftime('%Y-%m-%d'),
                        'close': float(row['close']) if pd.notnull(row['close']) else 0,
                        'institutional_net': float(row['institutional_net']) if pd.notnull(row.get('institutional_net')) else 0,
                        'retail_net': float(row['retail_net']) if pd.notnull(row.get('retail_net')) else 0,
                        'xlarge_net': float(row['xlarge_net_amount']) if 'xlarge_net_amount' in row and pd.notnull(row['xlarge_net_amount']) else 0,
                        'large_net': float(row['large_net_amount']) if 'large_net_amount' in row and pd.notnull(row['large_net_amount']) else 0,
                        'mid_net': float(row['mid_net_amount']) if 'mid_net_amount' in row  and pd.notnull(row['mid_net_amount']) else 0,
                        'small_net': float(row['small_net_amount']) if 'small_net_amount' in row and pd.notnull(row['small_net_amount']) else 0,
                    }
                    records.append(record)
                
                result['daily_data'] = records
                # 删除原始 DataFrame 以便 JSON 序列化
                del result['flow_data']
                
        except Exception as e:
            logger.error(f"获取股价数据失败: {e}")
            
        return result

    def analyze_market_summary(self, trade_date: str) -> Dict:
        """分析市场整体资金情况"""
        logger.info(f"正在分析 {trade_date} 的市场整体资金...")
        return self.provider.get_market_money_flow_summary(trade_date)


def plot_industry_ranking(result: Dict, save_path: Optional[str] = None):
    """绘制行业资金流向排行图"""
    try:
        import matplotlib.pyplot as plt
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        fig.suptitle(f'行业资金流向分析 ({result["trade_date"]})', fontsize=16, fontweight='bold')
        
        # 1. 净流入 Top 10
        in_names = [item['name'] for item in result['top_inflow'][::-1]]  # 倒序以便绘图从上到下
        in_values = [item['net_amount'] / 100000000 for item in result['top_inflow'][::-1]]  # 转为亿元
        
        bars1 = ax1.barh(in_names, in_values, color='#e74c3c', alpha=0.8)
        ax1.set_title('资金净流入 TOP 10 行业', fontsize=12)
        ax1.set_xlabel('净流入金额 (亿元)')
        ax1.grid(axis='x', linestyle='--', alpha=0.3)
        
        # 添加数值标签
        for bar in bars1:
            width = bar.get_width()
            ax1.text(width, bar.get_y() + bar.get_height()/2, f'{width:.2f}', 
                     ha='left', va='center', fontsize=9)

        # 2. 净流出 Top 10
        out_names = [item['name'] for item in result['top_outflow'][::-1]]
        out_values = [abs(item['net_amount']) / 100000000 for item in result['top_outflow'][::-1]]
        
        bars2 = ax2.barh(out_names, out_values, color='#2ecc71', alpha=0.8)
        ax2.set_title('资金净流出 TOP 10 行业', fontsize=12)
        ax2.set_xlabel('净流出金额 (亿元)')
        ax2.grid(axis='x', linestyle='--', alpha=0.3)
        
        for bar in bars2:
            width = bar.get_width()
            ax2.text(width, bar.get_y() + bar.get_height()/2, f'{width:.2f}', 
                     ha='left', va='center', fontsize=9)
            
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"✅ 图表已保存至: {save_path}")
        else:
            plt.show()
        plt.close()
        
    except ImportError:
        logger.warning("matplotlib 未安装，无法绘图")
    except Exception as e:
        logger.error(f"绘图失败: {e}")

def plot_stock_trend(result: Dict, save_path: Optional[str] = None):
    """绘制个股资金流向趋势图"""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        if 'daily_data' not in result or not result['daily_data']:
            logger.warning("无详细日线数据，无法绘图")
            return

        dates = [datetime.strptime(d['date'], '%Y-%m-%d') for d in result['daily_data']]
        closes = [d['close'] for d in result['daily_data']]
        # Tushare moneyflow 单位是万元，所以不需要额外换算，直接显示“万元”
        inst_net = [d['institutional_net'] for d in result['daily_data']] 
        retail_net = [d['retail_net'] for d in result['daily_data']] 
        
        fig, ax1 = plt.subplots(figsize=(14, 8))
        
        # 绘制资金流向 (柱状图)
        width = 0.35
        x = np.arange(len(dates))
        
        ax2 = ax1.twinx()  # 创建双轴
        
        # 绘制收盘价 (折线)
        ax2.plot(x, closes, color='#f1c40f', linewidth=2, marker='o', markersize=3, label='收盘价')
        ax2.set_ylabel('股价 (元)', color='#f39c12')
        
        # 资金流
        ax1.bar(x - width/2, inst_net, width, label='机构净流入', color='#e74c3c', alpha=0.7)
        ax1.bar(x + width/2, retail_net, width, label='散户净流入', color='#2ecc71', alpha=0.7)
        
        ax1.set_ylabel('净流入金额 (万元)')
        ax1.set_title(f'{result["symbol"]} 资金流向与股价趋势 ({result["period"]})', fontsize=14, fontweight='bold')
        
        # 设置X轴日期
        # 简化X轴标签，防止重叠
        step = max(1, len(dates) // 10)
        ax1.set_xticks(x[::step])
        ax1.set_xticklabels([d.strftime('%Y-%m-%d') for d in dates[::step]], rotation=45)
        
        # 图例
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        ax1.grid(True, linestyle='--', alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"✅ 图表已保存至: {save_path}")
        else:
            plt.show()
        plt.close()

    except Exception as e:
        logger.error(f"绘图失败: {e}")

def plot_market_summary(result: Dict, save_path: Optional[str] = None):
    """绘制市场资金概览图"""
    try:
        import matplotlib.pyplot as plt
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        fig = plt.figure(figsize=(14, 10))
        gs = fig.add_gridspec(2, 2)
        fig.suptitle(f'市场资金流向概览 ({result["trade_date"]})', fontsize=16, fontweight='bold')
        
        # 1. 机构 vs 散户 饼图
        ax1 = fig.add_subplot(gs[0, 0])
        inst_net = result.get('institutional_analysis', {}).get('total_net_flow', 0)
        retail_net = result.get('retail_analysis', {}).get('total_net_flow', 0)
        
        # 饼图展示绝对值的比例，区分颜色表示方向
        values = [abs(inst_net), abs(retail_net)]
        labels = ['机构净流入' if inst_net >0 else '机构净流出', 
                  '散户净流入' if retail_net >0 else '散户净流出']
        colors = ['#e74c3c' if inst_net >0 else '#c0392b',
                  '#2ecc71' if retail_net >0 else '#27ae60']
        
        ax1.pie(values, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90, explode=(0.05, 0))
        ax1.set_title('机构 vs 散户 资金力度对比')
        
        # 2. 北向资金
        ax2 = fig.add_subplot(gs[0, 1])
        north = result.get('north_money', {})
        north_in = north.get('north_money_in', 0)
        south_in = north.get('south_money_in', 0)
        
        bar_colors = ['#e74c3c' if x > 0 else '#2ecc71' for x in [north_in, south_in]]
        bars = ax2.bar(['北向资金', '南向资金'], [north_in, south_in], color=bar_colors)
        ax2.axhline(0, color='black', linewidth=0.8)
        ax2.set_ylabel('净流入金额 (亿元)')
        ax2.set_title('互联互通资金流向')
        
        for bar in bars:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2, height, f'{height:.2f}', 
                     ha='center', va='bottom' if height >0 else 'top')
            
        # 3. 市场情绪仪表盘 (模拟)
        ax3 = fig.add_subplot(gs[1, :])
        ax3.axis('off')
        sentiment = result.get('market_sentiment', {})
        
        status_text = f"市场情绪: {sentiment.get('sentiment', 'N/A')}\n"
        status_text += f"解读: {sentiment.get('reason', 'N/A')}\n\n"
        status_text += f"机构净额: {inst_net/10000:.2f} 亿元\n"
        status_text += f"散户净额: {retail_net/10000:.2f} 亿元\n"
        status_text += f"北向净额: {north_in/10000:.2f} 亿元"
        
        ax3.text(0.5, 0.5, status_text, ha='center', va='center', fontsize=14, 
                 bbox=dict(facecolor='#f0f0f0', edgecolor='gray', boxstyle='round,pad=1'))
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"✅ 图表已保存至: {save_path}")
        else:
            plt.show()
        plt.close()

    except Exception as e:
        logger.error(f"绘图失败: {e}")

def main():
    parser = argparse.ArgumentParser(
        description='资金流向分析与可视化工具',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--mode', choices=['industry', 'stock', 'market'], required=True,
                      help='分析模式: industry(行业), stock(个股), market(市场)')
    parser.add_argument('--symbol', help='股票代码 (stock模式必须)')
    parser.add_argument('--date', help='交易日期 (YYYYMMDD)')
    parser.add_argument('--days', type=int, default=30, help='个股分析的历史天数 (默认30)')
    parser.add_argument('--plot', action='store_true', help='是否生成并保存图表')
    parser.add_argument('--save', action='store_true', help='保存分析结果数据')
    
    args = parser.parse_args()
    
    analyzer = MoneyFlowAnalyzer()
    
    # 确定日期
    target_date = args.date
    if not target_date:
        now = datetime.now()
        if now.hour < 15: # 收盘前取前一天
            target_date = (now - timedelta(days=1)).strftime('%Y%m%d')
        else:
            target_date = now.strftime('%Y%m%d')
            
    # 新建 reports 目录
    report_dir = project_root / 'reports'
    report_dir.mkdir(exist_ok=True)
    
    if args.mode == 'industry':
        print(f"\n📊 开始行业资金流向分析 ({target_date})...")
        result = analyzer.analyze_industry_flow(target_date)
        
        if 'error' in result:
            print(f"❌ 分析失败: {result['error']}")
            return
            
        print("\n💰 资金净流入 Top 5:")
        for item in result['top_inflow'][:5]:
            print(f"   {item['name']:<10} 净流入: {item['net_amount']/100000000:>8.2f} 亿元 ({item['pct_change']:+.2f}%)")
            
        print("\n💸 资金净流出 Top 5:")
        for item in result['top_outflow'][:5]:
            print(f"   {item['name']:<10} 净流出: {item['net_amount']/100000000:>8.2f} 亿元 ({item['pct_change']:+.2f}%)")
            
        if args.plot:
            save_path = report_dir / f'industry_flow_{target_date}.png'
            plot_industry_ranking(result, str(save_path))
            print(f"\n🖼️  图表已保存: {save_path}")
            
    elif args.mode == 'stock':
        if not args.symbol:
            print("❌ stock 模式必须指定 --symbol")
            return
            
        end_date = target_date
        start_date = (datetime.strptime(end_date, '%Y%m%d') - timedelta(days=args.days)).strftime('%Y%m%d')
        
        print(f"\n📈 开始个股资金流向分析 {args.symbol} ({start_date} - {end_date})...")
        result = analyzer.analyze_stock_flow(args.symbol, start_date, end_date)
        
        if 'error' in result:
            print(f"❌ 分析失败: {result['error']}")
            return
            
        print(f"\n趋势: {result.get('interpretation', 'N/A')}")
        print(f"机构净流入天数: {result['institutional']['net_inflow_days']} / {result['total_days']}")
        
        if args.plot:
            save_path = report_dir / f'stock_flow_{args.symbol}_{end_date}.png'
            plot_stock_trend(result, str(save_path))
            print(f"\n🖼️  图表已保存: {save_path}")
            
    elif args.mode == 'market':
        print(f"\n🌍 开始市场资金概览分析 ({target_date})...")
        result = analyzer.analyze_market_summary(target_date)
        
        sent = result.get('market_sentiment', {})
        print(f"\n情绪: {sent.get('sentiment')} - {sent.get('reason')}")
        print(f"北向资金: {sent.get('north_money_net', 0)/10000:.2f} 亿元")
        
        if args.plot:
            save_path = report_dir / f'market_flow_{target_date}.png'
            plot_market_summary(result, str(save_path))
            print(f"\n🖼️  图表已保存: {save_path}")

    # 保存数据结果 (如果需要)
    if args.save:
        json_path = report_dir / f'money_flow_{args.mode}_{target_date}.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print(f"💾 数据已保存: {json_path}")

if __name__ == '__main__':
    sys.exit(main())
