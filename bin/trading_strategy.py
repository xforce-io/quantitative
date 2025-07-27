#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Trading Strategy CLI Tool
交易策略命令行工具

统一的交易策略入口脚本，支持多种交易策略功能
Unified trading strategy entry script supporting various trading strategy functions
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到路径
projectRoot = Path(__file__).parent.parent
sys.path.insert(0, str(projectRoot))

# 加载环境变量
load_dotenv(dotenv_path=projectRoot / '.env')

from quant.strategies.unified_grid_strategy import UnifiedGridTradingStrategy
from quant.strategies.ma_crossover_strategy import MACrossoverStrategy
from quant.engines.backtest_engine import BacktestEngine
from quant.engines.strategy_optimizer import StrategyOptimizer
from quant.data_providers.data_provider_factory import DataProviderFactory

def setupLogging(level: str = 'INFO'):
    """设置日志配置"""
    logLevel = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=logLevel,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f'logs/trading_strategy_{datetime.now().strftime("%Y%m%d")}.log')
        ]
    )

def listStrategies():
    """列出可用的交易策略"""
    strategies = {
        'unified_grid': '统一网格交易策略 - 支持仓位占比和动态网格中心调整',
        'adaptive_grid': '自适应网格交易策略 - 基于机器学习的参数自动优化',
        'ma_crossover': '均线交叉策略 - 基于移动平均线交叉的趋势跟踪策略',
    }
    
    print("🎯 可用的交易策略:")
    print("=" * 50)
    for key, desc in strategies.items():
        print(f"  {key:<15} : {desc}")
    print("=" * 50)

def runMACrossBacktest(args):
    """运行均线交叉策略回测"""
    print(f"📊 均线交叉策略回测")
    print("=" * 60)
    print(f"股票代码: {args.symbol}")
    print(f"回测期间: {args.start_date} 到 {args.end_date}")
    print(f"短期均线: MA{args.ma_short}")
    print(f"长期均线: MA{args.ma_long}")
    print(f"初始资金: ¥{args.initial_balance:,.0f}")
    print("=" * 60)
    
    try:
        # 初始化数据提供者
        dataProvider = DataProviderFactory.create('tushare')
        
        # 获取股票数据
        stock_data = dataProvider.getStockData(
            symbol=args.symbol,
            startDate=args.start_date.replace('-', ''),
            endDate=args.end_date.replace('-', ''),
            frequency='D'
        )
        
        if stock_data.empty:
            print(f"❌ 无法获取 {args.symbol} 的数据")
            return
            
        print(f"✅ 成功获取数据: {len(stock_data)} 个交易日")

        # 初始化策略配置
        strategyConfig = {
            'ma_short': args.ma_short,
            'ma_long': args.ma_long,
            'commission': 0.0003,
            'slippage': 0.001,
            'position_size': 1.0,
            'min_volume_ratio': 1.0,
            'min_price_change': 0.001
        }

        # 创建策略实例
        strategy = MACrossoverStrategy(args.symbol, strategyConfig)
        strategy.reset(args.initial_balance)

        # 回测变量
        portfolio_values = []
        positions = []
        trades = []
        
        print("\n🔄 开始回测...")
        
        # 逐日回测
        for i, (timestamp, row) in enumerate(stock_data.iterrows()):
            current_price = row['close']
            current_volume = row.get('vol', 0)
            
            # 处理市场数据
            strategy.on_market_data(timestamp, current_price, current_volume)
            
            # 记录每日数据
            portfolio_values.append(strategy.total_value)
            positions.append(strategy.current_position)

        # 计算性能指标
        performance_metrics = strategy.get_performance_metrics(args.initial_balance)
        
        # 显示回测结果
        print("\n📈 回测结果:")
        print("=" * 60)
        print(f"初始资金: ¥{args.initial_balance:,.0f}")
        print(f"最终资金: ¥{strategy.total_value:,.0f}")
        print(f"总收益率: {performance_metrics['totalReturn']:.2%}")
        print(f"年化收益率: {performance_metrics['annualizedReturn']:.2%}")
        print(f"最大回撤: {performance_metrics['maxDrawdown']:.2%}")
        print(f"夏普比率: {performance_metrics['sharpeRatio']:.3f}")
        print(f"总交易次数: {performance_metrics['totalTrades']}")
        print(f"盈利交易: {performance_metrics['profitableTrades']}")
        print(f"胜率: {performance_metrics['winRate']:.2%}")
        print("=" * 60)

        # 显示交易记录
        if strategy.trades:
            print(f"\n📋 交易记录 (共 {len(strategy.trades)} 笔):")
            print("-" * 80)
            for i, trade in enumerate(strategy.trades[:10]):  # 显示前10笔
                action_cn = "买入" if trade.action == 'buy' else "卖出"
                signal_cn = "金叉" if trade.signal_type == 'golden_cross' else "死叉"
                print(f"{i+1:2d}. {trade.timestamp.strftime('%Y-%m-%d')} | "
                      f"{action_cn} {trade.shares:4d}股 @ ¥{trade.price:6.2f} | "
                      f"{signal_cn} | 余额: ¥{trade.balance:8,.0f}")
            
            if len(strategy.trades) > 10:
                print(f"... 还有 {len(strategy.trades) - 10} 笔交易")

        # 计算基准收益（买入并持有）
        benchmark_return = (stock_data['close'].iloc[-1] / stock_data['close'].iloc[0]) - 1
        excess_return = performance_metrics['totalReturn'] - benchmark_return
        
        print(f"\n📊 与基准对比:")
        print(f"基准收益 (买入持有): {benchmark_return:.2%}")
        print(f"策略收益: {performance_metrics['totalReturn']:.2%}")
        print(f"超额收益: {excess_return:.2%}")

        # 保存结果
        result_data = {
            'symbol': args.symbol,
            'start_date': args.start_date,
            'end_date': args.end_date,
            'ma_short': args.ma_short,
            'ma_long': args.ma_long,
            'initial_capital': args.initial_balance,
            'final_capital': strategy.total_value,
            'performance': performance_metrics,
            'benchmark_return': benchmark_return,
            'trades': [{'timestamp': t.timestamp.isoformat(), 'action': t.action, 
                       'price': t.price, 'shares': t.shares, 'signal_type': t.signal_type} 
                      for t in strategy.trades]
        }
        
        resultFile = f"reports/ma_backtest_{args.symbol}_MA{args.ma_short}_{args.ma_long}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs('reports', exist_ok=True)

        import json
        with open(resultFile, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n💾 结果已保存至: {resultFile}")

    except Exception as e:
        import traceback
        print(f"❌ 回测失败: {str(e)}")
        print(f"详细错误信息:")
        traceback.print_exc()

def runBacktest(args):
    """运行回测"""
    if args.strategy == 'ma_crossover':
        return runMACrossBacktest(args)
    
    print(f"📊 开始回测策略: {args.strategy}")
    print(f"🏷️  股票代码: {args.symbol}")
    print(f"📅 回测期间: {args.start_date} 到 {args.end_date}")
    
    try:
        # 初始化数据提供者
        dataProvider = DataProviderFactory.create('tushare')
        
        # 获取数据
        data = dataProvider.getStockData(
            symbol=args.symbol,
            startDate=args.start_date,
            endDate=args.end_date,
            frequency='D'
        )
        
        if data.empty:
            print(f"❌ 无法获取 {args.symbol} 的数据")
            return
        
        # 准备策略配置
        strategyConfig = {
            'gridSpacing': args.grid_spacing or 0.02,
            'gridLevels': args.grid_levels or 10,
            'maxPosition': args.initial_balance or 100000,
            'minTradeAmount': 1000,
            'commission': 0.0003,
            'slippage': 0.001,
            'baseRatio': 0.3,
            'dynamicEnabled': True
        }
        
        # 运行回测 (BacktestEngine会自己创建策略实例)
        engine = BacktestEngine(dataProvider='tushare')
        results = engine.runBacktest(
            symbol=args.symbol,
            startDate=args.start_date,
            endDate=args.end_date,
            initialCapital=args.initial_balance,
            strategyConfig=strategyConfig
        )
        
        # 显示结果
        print(f"\n📈 回测结果:")
        print("=" * 60)
        print(f"总收益率: {results.get('total_return', 0):.2%}")
        print(f"年化收益率: {results.get('annual_return', 0):.2%}")
        print(f"最大回撤: {results.get('max_drawdown', 0):.2%}")
        print(f"夏普比率: {results.get('sharpe_ratio', 0):.3f}")
        print(f"交易次数: {results.get('total_trades', 0)}")
        print(f"胜率: {results.get('win_rate', 0):.2%}")
        print("=" * 60)
        
        # 保存结果
        resultFile = f"reports/backtest_{args.symbol}_{args.strategy}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs('reports', exist_ok=True)
        
        import json
        with open(resultFile, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"📁 详细结果已保存至: {resultFile}")
        
    except Exception as e:
        import traceback
        print(f"❌ 回测失败: {str(e)}")
        print(f"详细错误信息:")
        traceback.print_exc()
        logging.error(f"Backtest failed: {e}")
        logging.error(f"Traceback: {traceback.format_exc()}")

def optimizeStrategy(args):
    """优化策略参数"""
    print(f"{'='*80}")
    print(f"🔧 开始优化策略: {args.strategy} | 股票: {args.symbol}")
    print(f"{'='*80}")
    # 省略优化逻辑
    

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='量化交易策略工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s list                                       # 列出可用策略
  %(prog)s backtest unified_grid 000001.SZ            # 回测统一网格策略
  %(prog)s backtest ma_crossover 002594.SZ            # 回测均线交叉策略
  %(prog)s backtest ma_crossover 002594.SZ --ma-short 5 --ma-long 20   # 自定义均线参数
        """
    )
    
    # 创建子命令
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # list 命令
    listParser = subparsers.add_parser('list', help='列出可用的交易策略')
    
    # backtest 命令
    backtestParser = subparsers.add_parser('backtest', help='运行策略回测')
    backtestParser.add_argument('strategy', choices=['unified_grid', 'adaptive_grid', 'ma_crossover'], help='策略类型')
    backtestParser.add_argument('symbol', help='股票代码 (例如: 002594.SZ)')
    backtestParser.add_argument('--start-date', default='2023-01-01', help='开始日期 (YYYY-MM-DD)')
    backtestParser.add_argument('--end-date', default=datetime.now().strftime('%Y-%m-%d'), help='结束日期 (YYYY-MM-DD)')
    backtestParser.add_argument('--initial-balance', type=float, default=100000, help='初始资金')

    # 网格策略参数
    backtestParser.add_argument('--grid-spacing', type=float, help='网格间距')
    backtestParser.add_argument('--grid-levels', type=int, help='网格层数')

    # 均线交叉策略参数
    backtestParser.add_argument('--ma-short', type=int, default=5, help='短期均线周期 (默认: 5)')
    backtestParser.add_argument('--ma-long', type=int, default=10, help='长期均线周期 (默认: 10)')

    # optimize 命令
    optimizeParser = subparsers.add_parser('optimize', help='优化策略参数')
    optimizeParser.add_argument('strategy', choices=['unified_grid', 'adaptive_grid'], help='策略类型')
    optimizeParser.add_argument('symbol', help='股票代码')
    optimizeParser.add_argument('--start-date', default='2024-01-01', help='开始日期')
    optimizeParser.add_argument('--end-date', default=datetime.now().strftime('%Y-%m-%d'), help='结束日期')

    # 通用参数
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                       default='INFO', help='日志级别')

    args = parser.parse_args()

    # 设置日志
    setupLogging(args.log_level)

    # 创建必要的目录
    os.makedirs('logs', exist_ok=True)
    os.makedirs('reports', exist_ok=True)

    if not args.command:
        parser.print_help()
        return

    # 参数验证
    if hasattr(args, 'ma_short') and hasattr(args, 'ma_long'):
        if args.ma_short >= args.ma_long:
            print("❌ 错误: 短期均线周期必须小于长期均线周期")
            return

    try:
        if args.command == 'list':
            listStrategies()
        elif args.command == 'backtest':
            runBacktest(args)
        elif args.command == 'optimize':
            optimizeStrategy(args)
        else:
            print(f"❌ 未知命令: {args.command}")
            parser.print_help()

    except KeyboardInterrupt:
        print("\n👋 用户中断操作")
    except Exception as e:
        print(f"❌ 执行失败: {str(e)}")
        logging.error(f"Command execution failed: {e}")

if __name__ == "__main__":
    main()
