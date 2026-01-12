#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
计算多个时间周期的年化收益率
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from quant import create_data_provider, BacktestEngine, STRATEGY_REGISTRY, get_config


def calculate_returns_for_periods(symbol: str, periods_years: list):
    """计算多个时间周期的收益率"""
    
    print(f"\n{'='*80}")
    print(f"计算 {symbol} 的历史年化收益率")
    print(f"{'='*80}\n")
    
    # 获取配置
    config = get_config()
    
    # 创建回测引擎
    engine = BacktestEngine('auto')
    
    # 获取hold策略
    strategy_class = STRATEGY_REGISTRY['hold']
    
    # 当前日期
    end_date = datetime.now().strftime('%Y%m%d')
    
    results = []
    
    for years in periods_years:
        # 计算起始日期
        if years == 'MAX':
            # 尽可能早的日期 (如腾讯2004年上市)
            start_date = '20040616'
            period_name = '上市以来'
        else:
            start_datetime = datetime.now() - timedelta(days=years * 365.25)
            start_date = start_datetime.strftime('%Y%m%d')
            period_name = f'{years}年'
        
        print(f"\n{'='*60}")
        print(f"📊 计算 {period_name} 收益率")
        print(f"{'='*60}")
        print(f"起始日期: {start_date}")
        print(f"结束日期: {end_date}")
        
        try:
            # 创建策略实例
            strategy = strategy_class(symbol, {})
            
            # 运行回测
            result = engine.runBacktest(
                symbol,
                start_date,
                end_date,
                initialCapital=100000,
                strategyConfig={},
                strategy=strategy
            )
            
            # Add delay to respect Tushare rate limits (2 calls per minute)
            import time
            time.sleep(31)  # Wait 31 seconds between calls
            
            perf = result.get('performance', {})
            
            # 提取结果
            results.append({
                'period': period_name,
                'start_date': result['stockData'].index[0].strftime('%Y-%m-%d'),
                'end_date': result['stockData'].index[-1].strftime('%Y-%m-%d'),
                'initial_price': result['stockData']['close'].iloc[0],
                'final_price': result['stockData']['close'].iloc[-1],
                'total_return': perf.get('totalReturn', 0),
                'annual_return': perf.get('annualReturn', 0),
                'max_drawdown': perf.get('maxDrawdown', 0)
            })
            
        except Exception as e:
            print(f"❌ {period_name} 计算失败: {e}")
            continue
    
    # 打印汇总表格
    print(f"\n\n{'='*80}")
    print(f"📈 {symbol} 年化收益率汇总表")
    print(f"{'='*80}\n")
    
    print(f"{'周期':<12} {'起始':<12} {'结束':<12} {'初始价':<10} {'最新价':<10} {'累计收益':<12} {'年化收益':<12} {'最大回撤':<12}")
    print(f"{'-'*110}")
    
    for r in results:
        print(f"{r['period']:<12} "
              f"{r['start_date']:<12} "
              f"{r['end_date']:<12} "
              f"{r['initial_price']:<10.2f} "
              f"{r['final_price']:<10.2f} "
              f"{r['total_return']*100:>+10.2f}% "
              f"{r['annual_return']*100:>+10.2f}% "
              f"{r['max_drawdown']*100:>10.2f}%")
    
    print(f"\n{'='*80}\n")
    
    return results


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='计算多时间周期年化收益率')
    parser.add_argument('symbol', help='股票代码')
    parser.add_argument('--periods', default='3,5,10,MAX', 
                       help='时间周期(年),用逗号分隔,MAX表示最大可用时间')
    
    args = parser.parse_args()
    
    # 解析周期
    periods = []
    for p in args.periods.split(','):
        p = p.strip()
        if p == 'MAX':
            periods.append('MAX')
        else:
            periods.append(int(p))
    
    calculate_returns_for_periods(args.symbol, periods)
