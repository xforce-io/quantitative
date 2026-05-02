#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""A 股行业 ETF 轮动策略命令。"""

import logging
import sys

logger = logging.getLogger(__name__)


def register_rotation_commands(subparsers):
    """Register rotation strategy commands."""
    parser = subparsers.add_parser("rotation", help="A 股行业 ETF 轮动")
    sub = parser.add_subparsers(dest="rotation_action", help="轮动操作")

    backtest = sub.add_parser("backtest", help="回测行业 ETF 轮动策略")
    _add_common_args(backtest)
    backtest.add_argument("--tail", type=int, default=12, help="显示最近 N 期净值，默认 12")
    backtest.add_argument("--output", help="保存净值 CSV 到指定路径")

    latest = sub.add_parser("latest", help="生成最近一个月末的目标持仓")
    _add_common_args(latest)

    return parser


def handle_rotation_command(args):
    """Route rotation commands."""
    if args.rotation_action == "backtest":
        handle_rotation_backtest(args)
    elif args.rotation_action == "latest":
        handle_rotation_latest(args)
    else:
        print("❌ 未知的轮动操作")
        sys.exit(1)


def _add_common_args(parser):
    parser.add_argument("--start", required=True, help="开始日期 YYYYMMDD")
    parser.add_argument("--end", required=True, help="结束日期 YYYYMMDD")
    parser.add_argument("--universe", help="universe yaml 路径，默认 config/rotation_universe.yaml")
    parser.add_argument("--top-k", type=int, default=3, help="持有数量，默认 3")
    parser.add_argument("--lookback", type=int, default=6, help="动量回看月数，默认 6")
    parser.add_argument("--skip", type=int, default=1, help="跳过最近 N 个月，默认 1")
    parser.add_argument("--cash-threshold", type=float, default=0.0, help="现金过滤阈值，默认 0")
    parser.add_argument("--transaction-cost", type=float, default=0.002, help="单边换仓成本，默认 0.2%%")
    parser.add_argument("--benchmark", default="000300.SH", help="overlay benchmark，默认沪深 300")
    parser.add_argument("--provider", default="auto", help="数据源，默认 auto")


def _build_request(args):
    from quant.analysis.rotation import RankerConfig
    from quant.services import RotationRequest

    return RotationRequest(
        start=args.start,
        end=args.end,
        universe_path=args.universe,
        ranker_config=RankerConfig(
            lookback_months=args.lookback,
            skip_recent_months=args.skip,
            top_k=args.top_k,
            cash_threshold=args.cash_threshold,
        ),
        overlay_benchmark=args.benchmark,
        transaction_cost=args.transaction_cost,
        provider=args.provider,
    )


def handle_rotation_backtest(args):
    """Run rotation backtest and print summary."""
    print("\n📊 A 股行业 ETF 轮动回测")
    print("=" * 80)
    print(f"区间: {args.start} - {args.end}  benchmark: {args.benchmark}  top-K: {args.top_k}")

    try:
        from quant.services import RotationService

        result = RotationService().run_backtest(_build_request(args))
        m = result.metrics

        print("\n核心指标:")
        print(f"  策略总收益: {m['total_return_strategy']:+.2%}")
        print(f"  HS300 总收益: {m['total_return_benchmark']:+.2%}")
        print(f"  等权 universe 总收益: {m['total_return_equal_weight']:+.2%}")
        print(f"  策略年化:   {m['annual_return_strategy']:+.2%}")
        print(f"  策略波动:   {m['annual_vol_strategy']:.2%}")
        print(f"  策略最大回撤: {m['max_drawdown_strategy']:.2%}")
        print(f"  策略 Sharpe:  {m['sharpe_strategy']:.2f}")

        print(f"\n最近 {args.tail} 期净值:")
        print(result.equity_curve.tail(args.tail).to_string())

        if args.output:
            result.equity_curve.to_csv(args.output, encoding="utf-8-sig")
            print(f"\n💾 已保存: {args.output}")

    except Exception as e:
        print(f"❌ 轮动回测失败: {e}")
        logger.error("Rotation backtest failed: %s", e, exc_info=True)
        sys.exit(1)


def handle_rotation_latest(args):
    """Print the latest target holdings."""
    print("\n🎯 A 股行业 ETF 轮动 — 最新目标持仓")
    print("=" * 80)

    try:
        from quant.services import RotationService

        targets = RotationService().latest_targets(_build_request(args))

        print(f"决策日期: {targets['as_of']}")
        print(f"风险 multiplier: {targets['multiplier']:.2f}")
        print("\n最终持仓:")
        if targets["final_positions"]:
            for sym, pos in sorted(targets["final_positions"].items(), key=lambda kv: kv[1], reverse=True):
                print(f"  {sym}: {pos:.2%}")
        else:
            print("  全现金（B 现金过滤触发或 multiplier=0）")

        print("\nTop 动量排名:")
        for row in targets["top_momentum"]:
            print(f"  {row['symbol']}: {row['momentum']:+.2%}")

    except Exception as e:
        print(f"❌ 生成目标持仓失败: {e}")
        logger.error("Rotation latest failed: %s", e, exc_info=True)
        sys.exit(1)
