#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
批量低估筛选器 - Batch Undervalue Screener

对一批公司进行系统性低估程度评估，输出排名结果。

使用方法:
    # 使用配置文件中的股票列表
    python bin/batch_undervalue_screener.py --config stocks.txt
    
    # 直接指定股票代码
    python bin/batch_undervalue_screener.py 600900.SH 002594.SZ 000001.SZ
    
    # 指定分析周期和输出格式
    python bin/batch_undervalue_screener.py --config stocks.txt --days 756 --output csv

stocks.txt 格式示例:
    600900.SH,长江电力
    002594.SZ,比亚迪
    000001.SZ,平安银行
"""

import sys
import os
import argparse
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional
import pandas as pd
import numpy as np

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quant import create_data_provider, get_config
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


class BatchUndervalueScreener:
    """批量低估筛选器"""
    
    def __init__(self, data_provider='tushare'):
        """初始化筛选器"""
        config = get_config()
        self.provider = create_data_provider(data_provider, config.get_providers_config())
        self.results = []
    
    def analyze_single(self, symbol: str, name: str = '', industry: str = '', days: int = 756) -> Dict:
        """
        分析单只股票的低估程度
        
        Args:
            symbol: 股票代码
            name: 股票名称
            industry: 行业分类
            days: 分析周期（天数）
            
        Returns:
            分析结果字典
        """
        result = {
            'symbol': symbol,
            'name': name,
            'industry': industry,
            'days': days,
            'status': 'success',
            'error': None,
            # 价格数据
            'current_price': None,
            'start_price': None,
            'high_price': None,
            'low_price': None,
            'avg_price': None,
            # 核心指标
            'price_position': None,      # 当前在区间位置 (0-100%)
            'deviation_pct': None,       # 相对均价偏离度
            'z_score': None,             # Z-Score
            'volatility': None,          # 年化波动率
            # 评分
            'undervalue_score': None,    # 低估评分 (0-100)
            'signal': None,              # BUY/HOLD/SELL
        }
        
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # 获取数据
            data = self.provider.get_stock_data(
                symbol, 
                start_date.strftime('%Y%m%d'), 
                end_date.strftime('%Y%m%d')
            )
            
            if data is None or data.empty or len(data) < 20:
                result['status'] = 'no_data'
                result['error'] = '数据不足'
                return result
            
            # 基础价格指标
            close_prices = data['close'].values
            result['current_price'] = float(close_prices[-1])
            result['start_price'] = float(close_prices[0])
            result['high_price'] = float(data['high'].max())
            result['low_price'] = float(data['low'].min())
            result['avg_price'] = float(close_prices.mean())
            
            # 1. 价格位置 (0-100%)
            price_range = result['high_price'] - result['low_price']
            if price_range > 0:
                result['price_position'] = (result['current_price'] - result['low_price']) / price_range * 100
            else:
                result['price_position'] = 50
            
            # 2. 相对均价偏离度
            result['deviation_pct'] = (result['current_price'] - result['avg_price']) / result['avg_price'] * 100
            
            # 3. 计算回归拟合（简化版）
            x = np.arange(len(close_prices))
            y = close_prices
            
            # 多项式拟合
            try:
                coeffs = np.polyfit(x, y, 2)
                y_fitted = np.polyval(coeffs, x)
                
                # 计算偏离度
                deviations = (y - y_fitted) / y_fitted * 100
                deviation_std = np.std(deviations)
                current_deviation = deviations[-1]
                
                # Z-Score
                result['z_score'] = current_deviation / deviation_std if deviation_std > 0 else 0
                
            except Exception:
                result['z_score'] = 0
            
            # 4. 波动率
            returns = np.diff(close_prices) / close_prices[:-1]
            result['volatility'] = float(np.std(returns) * np.sqrt(252) * 100)
            
            # 5. 计算低估评分 (0-100，越高越低估)
            score = 0
            
            # 价格位置得分 (位置越低分越高)
            position_score = 100 - result['price_position']
            score += position_score * 0.4  # 40% 权重
            
            # 偏离度得分 (负偏离越大分越高)
            deviation_score = max(0, min(100, 50 - result['deviation_pct'] * 2))
            score += deviation_score * 0.3  # 30% 权重
            
            # Z-Score 得分 (Z越负分越高)
            z_score_score = max(0, min(100, 50 - result['z_score'] * 25))
            score += z_score_score * 0.3  # 30% 权重
            
            result['undervalue_score'] = round(score, 2)
            
            # 6. 信号判断
            if result['undervalue_score'] >= 70:
                result['signal'] = '🔥 强买入'
            elif result['undervalue_score'] >= 60:
                result['signal'] = '📗 买入'
            elif result['undervalue_score'] >= 40:
                result['signal'] = '📙 持有'
            elif result['undervalue_score'] >= 30:
                result['signal'] = '📙 观望'
            else:
                result['signal'] = '📕 高估'
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
        
        return result
    
    def screen(self, stocks: List[Tuple[str, str, str]], days: int = 756, 
               progress_callback=None) -> pd.DataFrame:
        """
        批量筛选
        
        Args:
            stocks: 股票列表 [(symbol, name, industry), ...]
            days: 分析周期
            progress_callback: 进度回调函数
            
        Returns:
            结果DataFrame
        """
        self.results = []
        total = len(stocks)
        
        print(f"\n🔍 开始批量分析 {total} 只股票...\n")
        
        for i, stock_info in enumerate(stocks, 1):
            symbol = stock_info[0]
            name = stock_info[1] if len(stock_info) > 1 else symbol
            industry = stock_info[2] if len(stock_info) > 2 else ''
            
            if progress_callback:
                progress_callback(i, total, symbol, name)
            else:
                print(f"  [{i}/{total}] 分析 {name} ({symbol})...", end='\r')
            
            result = self.analyze_single(symbol, name, industry, days)
            self.results.append(result)
        
        print(f"\n✅ 分析完成，共 {total} 只股票\n")
        
        # 转换为 DataFrame
        df = pd.DataFrame(self.results)
        
        # 按低估评分排序
        df = df.sort_values('undervalue_score', ascending=False, na_position='last')
        
        return df
    
    def print_report(self, df: pd.DataFrame, top_n: int = 20):
        """打印筛选报告"""
        
        print("=" * 100)
        print("📊 批量低估筛选报告")
        print(f"📅 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 100)
        
        # 成功分析的数量
        success_df = df[df['status'] == 'success']
        fail_count = len(df) - len(success_df)
        
        print(f"\n📈 分析概况: 成功 {len(success_df)} 只, 失败 {fail_count} 只\n")
        
        # Top N 最低估
        print(f"🏆 最可能低估的 Top {min(top_n, len(success_df))} 只股票:")
        print("-" * 120)
        print(f"{'排名':<4} {'代码':<12} {'名称':<10} {'行业':<10} {'当前价':<10} {'评分':<8} {'位置%':<8} {'偏离%':<10} {'信号':<12}")
        print("-" * 120)
        
        for i, (_, row) in enumerate(success_df.head(top_n).iterrows(), 1):
            industry = row.get('industry', '')[:8] if row.get('industry') else ''
            print(f"{i:<4} {row['symbol']:<12} {row['name']:<10} "
                  f"{industry:<10} "
                  f"¥{row['current_price']:<8.2f} "
                  f"{row['undervalue_score']:<8.1f} "
                  f"{row['price_position']:<8.1f} "
                  f"{row['deviation_pct']:+<9.1f} "
                  f"{row['signal']:<12}")
        
        print("-" * 120)
        
        # 统计信息
        print(f"\n📊 统计信息:")
        print(f"   🔥 强买入 (≥70分): {len(success_df[success_df['undervalue_score'] >= 70])} 只")
        print(f"   📗 买入   (60-70分): {len(success_df[(success_df['undervalue_score'] >= 60) & (success_df['undervalue_score'] < 70)])} 只")
        print(f"   📙 持有   (40-60分): {len(success_df[(success_df['undervalue_score'] >= 40) & (success_df['undervalue_score'] < 60)])} 只")
        print(f"   📕 高估   (<40分): {len(success_df[success_df['undervalue_score'] < 40])} 只")
        
        print("\n" + "=" * 100)
        print("⚠️ 免责声明: 本分析仅供参考，不构成投资建议。投资有风险，决策需谨慎。")
        print("=" * 100)


def load_stocks_from_file(filepath: str) -> List[Tuple[str, str, str]]:
    """
    从文件加载股票列表
    
    支持两种格式:
    1. 简单格式: 代码,名称
    2. 详细格式: 行业,名称,代码,描述
    
    Returns:
        List of (symbol, name, industry)
    """
    stocks = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = [p.strip() for p in line.split(',')]
            
            if len(parts) >= 4:
                # 格式: 行业,名称,代码,描述
                industry = parts[0]
                name = parts[1]
                symbol = parts[2]
                # 标准化代码格式
                if '.' not in symbol:
                    if symbol.startswith('6'):
                        symbol = f"{symbol}.SH"
                    elif symbol.startswith(('0', '3')):
                        symbol = f"{symbol}.SZ"
                stocks.append((symbol, name, industry))
            elif len(parts) >= 2:
                # 格式: 代码,名称
                symbol = parts[0]
                name = parts[1]
                stocks.append((symbol, name, ''))
            elif len(parts) == 1:
                # 仅代码
                symbol = parts[0]
                stocks.append((symbol, symbol, ''))
    
    return stocks


def main():
    parser = argparse.ArgumentParser(description='批量低估筛选器')
    parser.add_argument('symbols', nargs='*', help='股票代码列表')
    parser.add_argument('--config', '-c', type=str, help='股票列表配置文件路径')
    parser.add_argument('--days', '-d', type=int, default=756, help='分析周期（天数，默认756=3年）')
    parser.add_argument('--output', '-o', type=str, help='输出文件路径 (csv/xlsx)')
    parser.add_argument('--top', '-t', type=int, default=20, help='显示前N只最低估股票')
    
    args = parser.parse_args()
    
    # 准备股票列表
    stocks = []
    
    if args.config:
        if os.path.exists(args.config):
            stocks = load_stocks_from_file(args.config)
            print(f"📂 从 {args.config} 加载了 {len(stocks)} 只股票")
        else:
            print(f"❌ 文件不存在: {args.config}")
            sys.exit(1)
    
    if args.symbols:
        for symbol in args.symbols:
            if (symbol, symbol) not in stocks:
                stocks.append((symbol, symbol))
    
    if not stocks:
        print("❌ 请指定要分析的股票")
        print("   用法: python bin/batch_undervalue_screener.py 600900.SH 002594.SZ")
        print("   或:   python bin/batch_undervalue_screener.py --config stocks.txt")
        sys.exit(1)
    
    # 执行筛选
    screener = BatchUndervalueScreener()
    df = screener.screen(stocks, days=args.days)
    
    # 打印报告
    screener.print_report(df, top_n=args.top)
    
    # 保存结果
    if args.output:
        if args.output.endswith('.csv'):
            df.to_csv(args.output, index=False, encoding='utf-8-sig')
            print(f"\n📁 结果已保存到: {args.output}")
        elif args.output.endswith('.xlsx'):
            df.to_excel(args.output, index=False)
            print(f"\n📁 结果已保存到: {args.output}")


if __name__ == '__main__':
    main()
