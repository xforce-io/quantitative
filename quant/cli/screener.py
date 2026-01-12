#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
筛选器/排名相关命令
"""

import sys
import logging

logger = logging.getLogger(__name__)


def register_screener_commands(subparsers):
    """注册筛选器/排名相关命令"""
    screener_parser = subparsers.add_parser('screener', help='股票筛选和排名')
    screener_subparsers = screener_parser.add_subparsers(dest='screener_action', help='筛选器操作')

    # rank 命令
    rank_parser = screener_subparsers.add_parser('rank', help='股票排名')
    rank_parser.add_argument(
        '--symbols',
        type=str,
        help='股票代码列表，逗号分隔，如 "000001.SZ,002594.SZ,600036.SH"'
    )
    rank_parser.add_argument(
        '--pool',
        type=str,
        help='从配置文件加载的股票池名称，如 BANK, SEMICONDUCTOR'
    )
    rank_parser.add_argument(
        '--profile',
        type=str,
        default='balanced',
        choices=['short_term', 'balanced', 'value', 'trend', 'momentum'],
        help='排名权重配置 (默认: balanced)'
    )
    rank_parser.add_argument(
        '--days',
        type=int,
        default=60,
        help='分析数据天数 (默认: 60)'
    )
    rank_parser.add_argument(
        '--top',
        type=int,
        default=None,
        help='只显示前N名'
    )
    rank_parser.add_argument(
        '--output',
        type=str,
        help='输出文件路径 (CSV格式)'
    )

    # profiles 命令 - 列出可用配置
    profiles_parser = screener_subparsers.add_parser('profiles', help='列出可用的排名配置')

    return screener_parser


def handle_screener_command(args):
    """筛选器命令总入口"""
    if args.screener_action == 'rank':
        handle_screener_rank(args)
    elif args.screener_action == 'profiles':
        handle_screener_profiles(args)
    else:
        print("❌ 未知的筛选器操作，使用 --help 查看帮助")
        sys.exit(1)


def handle_screener_rank(args):
    """处理排名命令"""
    print("\n📊 股票排名分析")
    print("=" * 80)

    # 检查参数
    if not args.symbols and not args.pool:
        print("❌ 请指定 --symbols 或 --pool 参数")
        print("示例:")
        print("  python -m quant screener rank --symbols '000001.SZ,002594.SZ'")
        print("  python -m quant screener rank --pool BANK --profile value")
        sys.exit(1)

    try:
        from quant.analysis.screener.ranker import StockRanker

        ranker = StockRanker()

        # 获取股票列表
        if args.symbols:
            symbols = [s.strip() for s in args.symbols.split(',')]
            print(f"📋 分析标的: {len(symbols)} 只")
        else:
            # 从配置加载
            print(f"📋 从配置加载股票池: {args.pool}")
            result = ranker.rank_from_config(
                screen_name=args.pool,
                profile=args.profile,
                days=args.days,
                top_n=args.top
            )

            if result.empty:
                print(f"❌ 未找到股票池 '{args.pool}' 或池中无股票")
                sys.exit(1)

            # 输出结果
            print(ranker.format_ranking_report(result, args.profile))

            # 保存到文件
            if args.output:
                result.to_csv(args.output, index=False, encoding='utf-8-sig')
                print(f"\n💾 结果已保存到: {args.output}")

            return

        # 使用 symbols 参数的情况
        print(f"⚙️  排名配置: {args.profile}")
        print(f"📅 分析天数: {args.days}")
        print("-" * 80)

        result = ranker.rank(
            symbols=symbols,
            profile=args.profile,
            days=args.days,
            top_n=args.top
        )

        # 输出结果
        print(ranker.format_ranking_report(result, args.profile))

        # 保存到文件
        if args.output:
            result.to_csv(args.output, index=False, encoding='utf-8-sig')
            print(f"\n💾 结果已保存到: {args.output}")

    except Exception as e:
        print(f"❌ 排名分析失败: {e}")
        logger.error(f"排名分析错误: {e}", exc_info=True)
        sys.exit(1)


def handle_screener_profiles(args):
    """列出可用的排名配置"""
    print("\n📊 可用的排名配置")
    print("=" * 80)

    try:
        from quant.analysis.screener.ranker import StockRanker

        ranker = StockRanker()

        # 尝试加载配置文件获取详细描述
        import yaml
        from pathlib import Path

        config_path = Path('config/ranking_profiles.yaml')
        profiles_info = {}

        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                for name, profile in config.get('profiles', {}).items():
                    profiles_info[name] = {
                        'name': profile.get('name', name),
                        'description': profile.get('description', ''),
                        'weights': profile.get('weights', {})
                    }

        print(f"\n{'配置名称':<15}{'显示名称':<12}{'资金流向':<10}{'技术形态':<10}{'估值':<10}")
        print("-" * 80)

        for profile_name in ranker.get_available_profiles():
            info = profiles_info.get(profile_name, {})
            weights = info.get('weights', ranker.profiles.get(profile_name, {}))
            display_name = info.get('name', profile_name)

            print(
                f"{profile_name:<15}"
                f"{display_name:<12}"
                f"{weights.get('money_flow', 0):<10.0%}"
                f"{weights.get('technical', 0):<10.0%}"
                f"{weights.get('valuation', 0):<10.0%}"
            )

            if info.get('description'):
                print(f"  └─ {info['description']}")

        print("\n" + "=" * 80)
        print("使用方法: python -m quant screener rank --profile <配置名称> --symbols <股票列表>")

    except Exception as e:
        print(f"❌ 获取配置失败: {e}")
        logger.error(f"获取配置错误: {e}", exc_info=True)
        sys.exit(1)
