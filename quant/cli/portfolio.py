#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
投资组合相关命令
"""

import sys
import logging

logger = logging.getLogger(__name__)


def register_portfolio_commands(subparsers):
    """注册投资组合相关命令"""
    portfolio_parser = subparsers.add_parser('portfolio', help='投资组合分析')
    portfolio_subparsers = portfolio_parser.add_subparsers(dest='portfolio_action', help='组合操作')
    
    # analyze 命令
    analyze_parser = portfolio_subparsers.add_parser('analyze', help='分析投资组合')
    analyze_parser.add_argument('portfolio_name', help='组合名称，如 USER_REAL_PORTFOLIO')
    analyze_parser.add_argument('--detail', action='store_true', help='显示详细分析（控制台打印）')
    analyze_parser.add_argument('--save', action='store_true', help='保存JSON与Markdown报告到 reports/portfolio/YYYYMMDD')
    
    # list 命令
    list_parser = portfolio_subparsers.add_parser('list', help='列出可用组合')
    
    return portfolio_parser


def handle_portfolio_command(args):
    """投资组合命令总入口"""
    if args.portfolio_action == 'analyze':
        handle_portfolio_analyze(args)
    elif args.portfolio_action == 'list':
        handle_portfolio_list(args)
    else:
        print("❌ 未知的组合操作")
        sys.exit(1)


def handle_portfolio_analyze(args):
    """处理组合分析命令"""
    print(f"\n📊 分析投资组合: {args.portfolio_name}")
    print("=" * 80)
    
    try:
        from quant.analysis.portfolio import PortfolioAnalyzer
        analyzer = PortfolioAnalyzer()

        # 生成综合分析报告（内部会获取数据并计算）
        report = analyzer.create_detailed_report()

        # 打印详细/简要信息
        if args.detail:
            analyzer.print_comprehensive_report(report)
        else:
            info = report.get('analysis_info', {})
            overall = report.get('overall_analysis', {}).get('overall_metrics', {})
            print(f"\n💰 组合: {args.portfolio_name}")
            print(f"  期间: {info.get('analysis_period', '-')}")
            print(f"  实际收益: {overall.get('total_portfolio_return', 0.0):+.2f}% | 预期: {overall.get('expected_return', 0.0):.2f}% | 偏差: {overall.get('return_vs_expected', 0.0):+.2f}%")

        # 保存报告
        if args.save:
            paths = analyzer.save_analysis_report(report, write_markdown=True, use_dated_subdir=True)
            print(f"\n📁 报告已保存:\n  JSON: {paths.get('json')}\n  Markdown: {paths.get('markdown')}")

        print("\n✅ 分析完成")

    except Exception as e:
        print(f"❌ 分析失败: {e}")
        logger.error(f"组合分析错误: {e}", exc_info=True)
        sys.exit(1)


def handle_portfolio_list(args):
    """列出可用组合"""
    print("\n📋 可用的投资组合")
    print("=" * 80)
    
    try:
        from quant.core.config import get_config
        
        config = get_config()
        portfolios = config.get_portfolios() if hasattr(config, 'get_portfolios') else {}
        
        if not portfolios:
            print("未找到配置的投资组合")
            return
        
        for name, info in portfolios.items():
            print(f"\n📦 {name}")
            if isinstance(info, dict):
                holdings = info.get('holdings', {})
                print(f"  持仓数: {len(holdings)}")
        
    except Exception as e:
        print(f"❌ 读取组合失败: {e}")
        logger.error(f"读取组合错误: {e}", exc_info=True)
