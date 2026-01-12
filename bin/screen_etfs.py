#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ETF筛选快捷脚本

这是调用统一CLI的快捷方式，保持向后兼容。
推荐使用: python -m quant etf <subcommand> [options]

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
    """将旧格式参数转换为新CLI格式"""
    import argparse
    
    # 解析旧格式参数
    parser = argparse.ArgumentParser(description='ETF筛选器 (快捷方式)')
    parser.add_argument('--screen', action='store_true', help='执行ETF筛选')
    parser.add_argument('--types', nargs='+', help='ETF类型')
    parser.add_argument('--max-etfs', type=int, help='最大分析数量')
    parser.add_argument('--save', action='store_true', help='保存结果')
    parser.add_argument('--from-config', dest='config_name', help='从配置加载')
    parser.add_argument('--single', help='分析单只ETF')
    parser.add_argument('--config-show', action='store_true', help='显示配置')
    parser.add_argument('--list-config', action='store_true', help='列出配置篮子')
    
    args, unknown = parser.parse_known_args()
    
    # 构建新CLI参数
    cli_args = ['etf']
    
    # 路由到相应的子命令
    if args.single:
        cli_args.append('single')
        cli_args.append(args.single)
    elif args.config_show or args.list_config:
        cli_args.append('config')
        if args.config_show:
            cli_args.append('--show')
        if args.list_config:
            cli_args.append('--list')
    else:
        cli_args.append('screen')
        if args.types:
            cli_args.extend(['--types'] + args.types)
        if args.max_etfs:
            cli_args.extend(['--max-etfs', str(args.max_etfs)])
        if args.save:
            cli_args.append('--save')
        if args.config_name:
            cli_args.extend(['--from-config', args.config_name])
    
    return cli_args


def main():
    """主函数"""
    logger.info("📢 提示: 这是快捷脚本，实际调用统一CLI")
    logger.info("💡 推荐使用: python -m quant etf <subcommand> [options]")
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
