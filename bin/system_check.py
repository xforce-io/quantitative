#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
系统状态检查快捷脚本

这是调用统一CLI的快捷方式，保持向后兼容。
推荐使用: python -m quant system <subcommand> [options]

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
    parser = argparse.ArgumentParser(description='系统管理 (快捷方式)')
    parser.add_argument('--status', action='store_true', default=True, help='系统状态检查')
    parser.add_argument('--clean', action='store_true', help='清理缓存')
    parser.add_argument('--type', choices=['all', 'data', 'reports', 'etf'], 
                       default='all', help='清理类型')
    parser.add_argument('--version', action='store_true', help='显示版本信息')
    
    args, unknown = parser.parse_known_args()
    
    # 构建新CLI参数
    cli_args = ['system']
    
    if args.version:
        cli_args.append('version')
    elif args.clean:
        cli_args.append('clean')
        cli_args.extend(['--type', args.type])
    else:
        # 默认状态检查
        cli_args.append('status')
    
    return cli_args


def main():
    """主函数"""
    logger.info("📢 提示: 这是快捷脚本，实际调用统一CLI")
    logger.info("💡 推荐使用: python -m quant system <subcommand> [options]")
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

