#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
投资顾问分析快捷脚本

这是调用统一CLI的快捷方式，保持向后兼容。
推荐使用: python -m quant advisor <subcommand> [options]

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
    parser = argparse.ArgumentParser(description='投资顾问分析 (快捷方式)')
    parser.add_argument('symbol', help='股票代码，如 002594.SZ')
    parser.add_argument('--comprehensive', '-c', action='store_true', 
                       help='综合分析（包含策略回测）')
    parser.add_argument('--provider', default='auto', help='数据源')
    parser.add_argument('--days', type=int, default=2500, help='历史数据天数')
    
    args, unknown = parser.parse_known_args()
    
    # 构建新CLI参数
    cli_args = ['advisor']
    
    if args.comprehensive:
        cli_args.append('comprehensive')
        cli_args.append(args.symbol)
        if args.days != 2500:
            cli_args.extend(['--days', str(args.days)])
    else:
        cli_args.append('single')
        cli_args.append(args.symbol)
        if args.provider != 'auto':
            cli_args.extend(['--provider', args.provider])
    
    return cli_args


def main():
    """主函数"""
    logger.info("📢 提示: 这是快捷脚本，实际调用统一CLI")
    logger.info("💡 推荐使用: python -m quant advisor <subcommand> [options]")
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

