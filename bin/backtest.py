#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略回测快捷脚本

这是调用统一CLI的快捷方式，保持向后兼容。
推荐使用: python -m quant strategy backtest <strategy> <symbol> [options]

本脚本将参数转换后调用主CLI入口。
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from quant.core.logging_config import get_logger
logger = get_logger(__name__)


def convert_args_to_cli_format():
    """将参数转换为新CLI格式"""
    import argparse
    
    # 解析参数
    parser = argparse.ArgumentParser(description='策略回测 (快捷方式)')
    parser.add_argument('strategy', nargs='?', 
                       help='策略名称，如 ma_crossover, momentum, unified_grid')
    parser.add_argument('symbol', nargs='?', help='股票代码，如 002594.SZ')
    parser.add_argument('--list', action='store_true', help='列出可用策略')
    parser.add_argument('--start', default='20230101', help='开始日期 YYYYMMDD')
    parser.add_argument('--end', default='20241201', help='结束日期 YYYYMMDD')
    parser.add_argument('--config', help='策略配置文件')
    
    args, unknown = parser.parse_known_args()
    
    # 构建新CLI参数
    cli_args = ['strategy']
    
    if args.list:
        cli_args.append('list')
    elif args.strategy and args.symbol:
        cli_args.append('backtest')
        cli_args.append(args.strategy)
        cli_args.append(args.symbol)
        if args.start != '20230101':
            cli_args.extend(['--start', args.start])
        if args.end != '20241201':
            cli_args.extend(['--end', args.end])
        if args.config:
            cli_args.extend(['--config', args.config])
    else:
        # 默认列出策略
        cli_args.append('list')
    
    return cli_args


def main():
    """主函数"""
    logger.info("📢 提示: 这是快捷脚本，实际调用统一CLI")
    logger.info("💡 推荐使用: python -m quant strategy backtest <strategy> <symbol> [options]")
    print()
    
    # 转换参数
    cli_args = convert_args_to_cli_format()
    
    # 调用主CLI
    from quant.__main__ import main as cli_main
    
    # 替换sys.argv以传递参数
    original_argv = sys.argv
    sys.argv = ['python -m quant'] + cli_args
    
    try:
        return cli_main()
    finally:
        sys.argv = original_argv


if __name__ == '__main__':
    sys.exit(main())

