#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Data management commands."""

import logging
import sys

logger = logging.getLogger(__name__)


def register_data_commands(subparsers):
    """Register data management commands."""
    data_parser = subparsers.add_parser("data", help="数据层管理")
    data_subparsers = data_parser.add_subparsers(dest="data_action", help="数据操作")

    data_subparsers.add_parser("status", help="数据源和缓存状态检查")

    price_parser = data_subparsers.add_parser("price", help="获取标准化价格数据")
    price_parser.add_argument("symbol", help="标的代码，如 000001.SZ / 000300.SH / 510300.SH")
    price_parser.add_argument("--start", required=True, help="开始日期 YYYYMMDD")
    price_parser.add_argument("--end", required=True, help="结束日期 YYYYMMDD")
    price_parser.add_argument(
        "--asset-type",
        choices=["stock", "index", "fund", "etf"],
        default="stock",
        help="资产类型",
    )
    price_parser.add_argument("--freq", default="D", help="数据频率，默认 D")
    price_parser.add_argument("--provider", default="auto", help="数据源，默认 auto")
    price_parser.add_argument("--head", type=int, default=5, help="显示前 N 行，默认 5")

    return data_parser


def handle_data_command(args):
    """Route data commands."""
    if args.data_action == "status":
        handle_data_status(args)
    elif args.data_action == "price":
        handle_data_price(args)
    else:
        print("❌ 未知的数据操作")
        sys.exit(1)


def handle_data_status(args):
    """Print data layer status."""
    print("\n🗄️ 数据层状态检查")
    print("=" * 80)

    try:
        from quant.services import DataService

        status = DataService().get_status()

        print("\n📡 数据源:")
        for name, available in status.providers.items():
            print(f"  {name}: {'可用 ✅' if available else '不可用 ❌'}")

        print("\n🔐 环境配置:")
        for name, exists in status.environment.items():
            print(f"  {name}: {'已设置 ✅' if exists else '未设置 ❌'}")

        print("\n💾 缓存:")
        print(f"  路径: {status.cache_dir}")
        print(f"  状态: {'存在 ✅' if status.cache_exists else '不存在 ❌'}")

        print("\n⚙️ 默认数据源:")
        print(f"  {status.default_provider}")

        print("\n✅ 数据层状态检查完成")

    except Exception as e:
        print(f"❌ 数据层状态检查失败: {e}")
        logger.error("Data status check failed: %s", e, exc_info=True)
        sys.exit(1)


def handle_data_price(args):
    """Fetch and print normalized price data."""
    print("\n📈 标准化价格数据")
    print("=" * 80)
    print(f"标的: {args.symbol}")
    print(f"区间: {args.start} - {args.end}")
    print(f"类型: {args.asset_type}")
    print(f"数据源: {args.provider}")

    try:
        from quant.services import DataService, PriceRequest

        service = DataService()
        df = service.get_price(
            PriceRequest(
                symbol=args.symbol,
                start=args.start,
                end=args.end,
                asset_type=args.asset_type,
                freq=args.freq,
                provider=args.provider,
            )
        )

        if df.empty:
            print("\n未返回数据")
            return

        print(f"\n返回行数: {len(df)}")
        print(df.head(args.head).to_string())

    except Exception as e:
        print(f"❌ 获取价格数据失败: {e}")
        logger.error("Price data fetch failed: %s", e, exc_info=True)
        sys.exit(1)
