#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
交易策略相关命令
"""

import sys
import logging

logger = logging.getLogger(__name__)


def register_strategy_commands(subparsers):
    """注册交易策略相关命令"""
    strategy_parser = subparsers.add_parser('strategy', help='交易策略回测')
    strategy_subparsers = strategy_parser.add_subparsers(dest='strategy_action', help='策略操作')
    
    # backtest 命令
    backtest_parser = strategy_subparsers.add_parser('backtest', help='策略回测')
    backtest_parser.add_argument('strategy_name', help='策略名称，如 ma_crossover, pyramid_dca')
    backtest_parser.add_argument('symbol', help='股票代码')
    backtest_parser.add_argument('--start', default='20230101', help='开始日期 YYYYMMDD')
    backtest_parser.add_argument('--end', default='20241201', help='结束日期 YYYYMMDD')
    backtest_parser.add_argument('--config', help='策略配置文件')
    
    # 金字塔定投策略参数
    backtest_parser.add_argument('--pyramid-type', choices=['normal', 'inverse'], 
                                 help='金字塔类型: normal(正金字塔) / inverse(倒金字塔)')
    backtest_parser.add_argument('--reference-method', choices=['ma', 'cost', 'initial'],
                                 help='参考基准: ma(均线) / cost(成本价) / initial(首次价格)')
    backtest_parser.add_argument('--reference-period', type=int,
                                 help='参考周期(日)，用于均线计算，默认60')
    backtest_parser.add_argument('--adjustment-factor', type=float,
                                 help='调整系数，控制投入金额变化幅度，默认0.5')
    backtest_parser.add_argument('--base-invest-amount', type=float,
                                 help='基准投入金额，默认10000')
    backtest_parser.add_argument('--invest-interval-days', type=int,
                                 help='定投间隔天数，默认30')
    
    # list 命令
    list_parser = strategy_subparsers.add_parser('list', help='列出可用策略')
    
    return strategy_parser


def handle_strategy_command(args):
    """交易策略命令总入口"""
    if args.strategy_action == 'backtest':
        handle_strategy_backtest(args)
    elif args.strategy_action == 'list':
        handle_strategy_list(args)
    else:
        print("❌ 未知的策略操作")
        sys.exit(1)


def handle_strategy_backtest(args):
    """处理策略回测"""
    print(f"\n📊 回测策略: {args.strategy_name}")
    print("=" * 80)
    print(f"标的: {args.symbol}")
    print(f"时间: {args.start} - {args.end}")
    
    try:
        from quant import create_data_provider, BacktestEngine, STRATEGY_REGISTRY, get_config
        
        # 检查策略是否存在
        if args.strategy_name not in STRATEGY_REGISTRY:
            print(f"❌ 策略不存在: {args.strategy_name}")
            print(f"可用策略: {', '.join(STRATEGY_REGISTRY.keys())}")
            sys.exit(1)
        
        # 获取配置
        config = get_config()
        
        # 创建数据提供器
        provider = create_data_provider('auto', config.get_providers_config())
        
        # 创建策略
        strategy_class = STRATEGY_REGISTRY[args.strategy_name]
        strategy_config = config.get_strategy_config(args.strategy_name) if args.config is None else args.config
        
        # 如果是金字塔定投策略，处理命令行参数
        if args.strategy_name in ['pyramid_dca', 'pyramid']:
            if strategy_config is None:
                strategy_config = {}
            if hasattr(args, 'pyramid_type') and args.pyramid_type:
                strategy_config['pyramid_type'] = args.pyramid_type
            if hasattr(args, 'reference_method') and args.reference_method:
                strategy_config['reference_method'] = args.reference_method
            if hasattr(args, 'reference_period') and args.reference_period:
                strategy_config['reference_period'] = args.reference_period
            if hasattr(args, 'adjustment_factor') and args.adjustment_factor:
                strategy_config['adjustment_factor'] = args.adjustment_factor
            if hasattr(args, 'base_invest_amount') and args.base_invest_amount:
                strategy_config['base_invest_amount'] = args.base_invest_amount
            if hasattr(args, 'invest_interval_days') and args.invest_interval_days:
                strategy_config['invest_interval_days'] = args.invest_interval_days
        
        strategy = strategy_class(args.symbol, strategy_config)
        
        # 创建回测引擎
        engine = BacktestEngine('auto')

        # 运行回测
        print("\n正在运行回测...")
        result = engine.runBacktest(args.symbol, args.start, args.end,
                                    initialCapital=100000, strategyConfig=strategy_config,
                                    strategy=strategy)
        
        # 显示结果
        perf = result.get('performance', {})
        print(f"\n📈 回测结果:")
        print(f"  初始资金: ¥{result.get('initialCapital', 0):,.0f}")
        print(f"  最终价值: ¥{perf.get('finalValue', 0):,.2f}")
        print(f"  总收益率: {perf.get('totalReturn', 0)*100:+.2f}%")
        print(f"  年化收益: {perf.get('annualReturn', 0)*100:+.2f}%" if 'annualReturn' in perf else "")
        print(f"  最大回撤: {perf.get('maxDrawdown', 0)*100:.2f}%")
        print(f"  交易次数: {perf.get('totalTrades', 0)}次")
        print(f"  胜率: {perf.get('winRate', 0)*100:.1f}%" if 'winRate' in perf else "")
        
        print("\n✅ 回测完成")
        
    except Exception as e:
        print(f"❌ 回测失败: {e}")
        logger.error(f"策略回测错误: {e}", exc_info=True)
        sys.exit(1)


def handle_strategy_list(args):
    """列出可用策略"""
    print("\n📋 可用的交易策略")
    print("=" * 80)
    
    try:
        from quant import STRATEGY_REGISTRY
        
        if not STRATEGY_REGISTRY:
            print("未找到注册的策略")
            return
        
        for name, strategy_class in STRATEGY_REGISTRY.items():
            doc = strategy_class.__doc__ or "无描述"
            print(f"\n📦 {name}")
            print(f"  {doc.strip().split(chr(10))[0]}")
        
    except Exception as e:
        print(f"❌ 读取策略失败: {e}")
        logger.error(f"读取策略错误: {e}", exc_info=True)

