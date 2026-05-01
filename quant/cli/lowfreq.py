#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Low-frequency A-share strategy preparation commands."""

import logging
import sys

logger = logging.getLogger(__name__)


def register_lowfreq_commands(subparsers):
    """Register low-frequency strategy commands."""
    parser = subparsers.add_parser("lowfreq", help="A股低频策略准备")
    sub = parser.add_subparsers(dest="lowfreq_action", help="低频策略操作")

    signals = sub.add_parser("signals", help="生成月频趋势和波动率仓位信号")
    _add_common_signal_args(signals)
    signals.add_argument("--tail", type=int, default=12, help="显示最近 N 行，默认 12")
    signals.add_argument("--output", help="保存 CSV 到指定路径")

    backtest = sub.add_parser("backtest", help="回测月频趋势和波动率仓位策略")
    _add_common_signal_args(backtest)
    backtest.add_argument("--transaction-cost", type=float, default=0.0, help="单边换仓成本")
    backtest.add_argument("--tail", type=int, default=12, help="显示最近 N 行净值，默认 12")
    backtest.add_argument("--output", help="保存净值 CSV 到指定路径")

    return parser


def handle_lowfreq_command(args):
    """Route low-frequency commands."""
    if args.lowfreq_action == "signals":
        handle_lowfreq_signals(args)
    elif args.lowfreq_action == "backtest":
        handle_lowfreq_backtest(args)
    else:
        print("❌ 未知的低频策略操作")
        sys.exit(1)


def _add_common_signal_args(parser):
    """Add shared low-frequency signal arguments."""
    parser.add_argument("symbol", help="标的代码，如 000300.SH / 510300.SH")
    parser.add_argument("--start", required=True, help="开始日期 YYYYMMDD")
    parser.add_argument("--end", required=True, help="结束日期 YYYYMMDD")
    parser.add_argument(
        "--asset-type",
        choices=["stock", "index", "fund", "etf"],
        default="index",
        help="资产类型，默认 index",
    )
    parser.add_argument("--provider", default="auto", help="数据源，默认 auto")
    parser.add_argument("--ma-months", type=int, default=10, help="月线均线窗口，默认 10")
    parser.add_argument("--vol-window", type=int, default=20, help="日波动率窗口，默认 20")
    parser.add_argument("--target-vol", type=float, default=0.20, help="目标年化波动率")
    parser.add_argument("--max-position", type=float, default=1.0, help="最大仓位")
    parser.add_argument(
        "--regime",
        choices=["none", "simple"],
        default="none",
        help="市场状态仓位乘数，默认 none",
    )


def handle_lowfreq_signals(args):
    """Build and print low-frequency signal table."""
    print("\n📉 A股低频信号")
    print("=" * 80)
    print(f"标的: {args.symbol}")
    print(f"区间: {args.start} - {args.end}")
    print(f"类型: {args.asset_type}")

    try:
        from quant.services import LowFrequencyService, LowFrequencySignalRequest

        request = LowFrequencySignalRequest(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            asset_type=args.asset_type,
            provider=args.provider,
            ma_months=args.ma_months,
            vol_window=args.vol_window,
            target_vol=args.target_vol,
            max_position=args.max_position,
            regime=args.regime,
        )
        result = LowFrequencyService().build_signals(request)

        if result.empty:
            print("\n未生成信号")
            return

        print(f"\n信号行数: {len(result)}")
        print(result.tail(args.tail).to_string())

        if args.output:
            result.to_csv(args.output, encoding="utf-8-sig")
            print(f"\n💾 已保存: {args.output}")

    except Exception as e:
        print(f"❌ 生成低频信号失败: {e}")
        logger.error("Low-frequency signal generation failed: %s", e, exc_info=True)
        sys.exit(1)


def handle_lowfreq_backtest(args):
    """Run and print low-frequency benchmark backtest."""
    print("\n📊 A股低频基准回测")
    print("=" * 80)
    print(f"标的: {args.symbol}")
    print(f"区间: {args.start} - {args.end}")
    print(f"类型: {args.asset_type}")

    try:
        from quant.services import LowFrequencyService, LowFrequencySignalRequest

        request = LowFrequencySignalRequest(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            asset_type=args.asset_type,
            provider=args.provider,
            ma_months=args.ma_months,
            vol_window=args.vol_window,
            target_vol=args.target_vol,
            max_position=args.max_position,
            transaction_cost=args.transaction_cost,
            regime=args.regime,
        )
        result = LowFrequencyService().run_backtest(request)
        metrics = result["metrics"]
        equity_curve = result["equity_curve"]

        print("\n核心指标:")
        print(f"  策略总收益: {metrics['total_return_strategy']:+.2%}")
        print(f"  基准总收益: {metrics['total_return_benchmark']:+.2%}")
        print(f"  策略年化:   {metrics['annual_return_strategy']:+.2%}")
        print(f"  基准年化:   {metrics['annual_return_benchmark']:+.2%}")
        print(f"  策略波动:   {metrics['annual_vol_strategy']:.2%}")
        print(f"  基准波动:   {metrics['annual_vol_benchmark']:.2%}")
        print(f"  策略回撤:   {metrics['max_drawdown_strategy']:.2%}")
        print(f"  基准回撤:   {metrics['max_drawdown_benchmark']:.2%}")
        print(f"  策略Sharpe: {metrics['sharpe_strategy']:.2f}")
        print(f"  基准Sharpe: {metrics['sharpe_benchmark']:.2f}")

        print(f"\n最近 {args.tail} 期净值:")
        print(equity_curve.tail(args.tail).to_string())

        if args.output:
            equity_curve.to_csv(args.output, encoding="utf-8-sig")
            print(f"\n💾 已保存: {args.output}")

    except Exception as e:
        print(f"❌ 低频回测失败: {e}")
        logger.error("Low-frequency backtest failed: %s", e, exc_info=True)
        sys.exit(1)
