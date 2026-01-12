#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
量化交易系统统一CLI入口

Quantitative Trading System Unified CLI Entry Point

使用方式:
    python -m quant <command> <subcommand> [options]

示例:
    python -m quant etf screen --types broad_market --save
    python -m quant portfolio analyze USER_REAL_PORTFOLIO
    python -m quant advisor single 002594.SZ
    python -m quant strategy backtest ma_crossover 002594.SZ
    python -m quant system status
"""

import sys
import argparse
import logging
from pathlib import Path

# 确保项目根目录在路径中
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from quant.cli import (
    register_etf_commands,
    register_portfolio_commands,
    register_advisor_commands,
    register_strategy_commands,
    register_system_commands,
    register_screener_commands
)
from quant.cli.etf import handle_etf_command
from quant.cli.portfolio import handle_portfolio_command
from quant.cli.advisor import handle_advisor_command
from quant.cli.strategy import handle_strategy_command
from quant.cli.system import handle_system_command
from quant.cli.screener import handle_screener_command

# 配置日志
logging.basicConfig(
    level=logging.WARNING,  # 默认只显示警告和错误
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 获取版本号
try:
    from quant import __version__
except ImportError:
    __version__ = "未知"


def create_parser():
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog='python -m quant',
        description=f'量化交易系统统一CLI (v{__version__})',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
命令示例:

  ETF筛选:
    python -m quant etf screen --types broad_market sector --save
    python -m quant etf screen --from-config INDUSTRY_ETF --save
    python -m quant etf single 510300.SH
    python -m quant etf config --list

  投资组合分析:
    python -m quant portfolio analyze USER_REAL_PORTFOLIO
    python -m quant portfolio list

  投资顾问:
    python -m quant advisor single 002594.SZ
    python -m quant advisor comprehensive 002594.SZ

  策略回测:
    python -m quant strategy backtest ma_crossover 002594.SZ
    python -m quant strategy list

  股票排名:
    python -m quant screener rank --symbols "000001.SZ,002594.SZ" --profile balanced
    python -m quant screener rank --pool BANK --profile value --top 10
    python -m quant screener profiles

  系统管理:
    python -m quant system status
    python -m quant system clean --type all
    python -m quant system version

更多信息请查看文档: docs/
        """
    )
    
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细日志')
    
    # 创建子命令解析器
    subparsers = parser.add_subparsers(dest='command', help='可用命令', metavar='<command>')
    
    # 注册各个模块的命令
    register_etf_commands(subparsers)
    register_portfolio_commands(subparsers)
    register_advisor_commands(subparsers)
    register_strategy_commands(subparsers)
    register_system_commands(subparsers)
    register_screener_commands(subparsers)
    
    return parser


def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    
    # 如果没有提供命令，显示帮助
    if not args.command:
        parser.print_help()
        return 0
    
    try:
        # 路由到对应的命令处理器
        if args.command == 'etf':
            handle_etf_command(args)
        elif args.command == 'portfolio':
            handle_portfolio_command(args)
        elif args.command == 'advisor':
            handle_advisor_command(args)
        elif args.command == 'strategy':
            handle_strategy_command(args)
        elif args.command == 'system':
            handle_system_command(args)
        elif args.command == 'screener':
            handle_screener_command(args)
        else:
            print(f"❌ 未知命令: {args.command}")
            parser.print_help()
            return 1
        
        return 0
    
    except KeyboardInterrupt:
        print("\n\n👋 操作已取消")
        return 130
    
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
