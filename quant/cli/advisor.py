#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
投资顾问相关命令
"""

import sys
import logging

logger = logging.getLogger(__name__)


def register_advisor_commands(subparsers):
    """注册投资顾问相关命令"""
    advisor_parser = subparsers.add_parser('advisor', help='投资顾问分析')
    advisor_subparsers = advisor_parser.add_subparsers(dest='advisor_action', help='顾问操作')
    
    # single 命令
    single_parser = advisor_subparsers.add_parser('single', help='单标的分析')
    single_parser.add_argument('symbol', help='股票代码，如 002594.SZ')
    single_parser.add_argument('--provider', default='auto', help='数据源')
    
    # comprehensive 命令
    comp_parser = advisor_subparsers.add_parser('comprehensive', help='综合分析')
    comp_parser.add_argument('symbol', help='股票代码')
    comp_parser.add_argument('--days', type=int, default=2500, help='历史数据天数')
    
    return advisor_parser


def handle_advisor_command(args):
    """投资顾问命令总入口"""
    if args.advisor_action == 'single':
        handle_advisor_single(args)
    elif args.advisor_action == 'comprehensive':
        handle_advisor_comprehensive(args)
    else:
        print("❌ 未知的顾问操作")
        sys.exit(1)


def handle_advisor_single(args):
    """处理单标的分析"""
    print(f"\n📊 分析标的: {args.symbol}")
    print("=" * 80)
    
    try:
        from quant.analysis.advisor import InvestmentAdvisor
        
        advisor = InvestmentAdvisor(
            symbols=[args.symbol],
            data_provider=args.provider
        )
        
        # 使用analyze_current_signals_only方法
        result = advisor.analyze_current_signals_only(symbols=[args.symbol], current_days=300)

        # 显示分析结果
        if result and args.symbol in result:
            symbol_result = result[args.symbol]
            print("\n✅ 分析完成")
            print(f"\n📈 当前信号: {symbol_result.get('current', {}).get('action', '未知')}")
            print(f"📊 综合评分: {symbol_result.get('current', {}).get('combined_score', 0)}")
            if 'action_advice' in symbol_result.get('current', {}):
                print(f"💡 操作建议: {symbol_result['current']['action_advice']}")
        else:
            print("⚠️ 分析未返回结果")
        
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        logger.error(f"投资顾问分析错误: {e}", exc_info=True)
        sys.exit(1)


def handle_advisor_comprehensive(args):
    """处理综合分析"""
    print(f"\n📊 综合分析标的: {args.symbol}")
    print("=" * 80)
    print(f"历史数据: {args.days} 天")
    
    try:
        from quant.analysis.advisor import InvestmentAdvisor
        
        advisor = InvestmentAdvisor(symbols=[args.symbol])
        result = advisor.analyze_current_signals_only(symbols=[args.symbol], current_days=args.days)
        
        print("\n✅ 综合分析完成")
        
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        logger.error(f"综合分析错误: {e}", exc_info=True)
        sys.exit(1)

