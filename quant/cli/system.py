#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
系统管理相关命令
"""

import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def register_system_commands(subparsers):
    """注册系统管理相关命令"""
    system_parser = subparsers.add_parser('system', help='系统管理')
    system_subparsers = system_parser.add_subparsers(dest='system_action', help='系统操作')
    
    # status 命令
    status_parser = system_subparsers.add_parser('status', help='系统状态检查')
    
    # clean 命令
    clean_parser = system_subparsers.add_parser('clean', help='清理缓存')
    clean_parser.add_argument('--type', choices=['all', 'data', 'reports', 'etf'], 
                             default='all', help='清理类型')
    
    # version 命令
    version_parser = system_subparsers.add_parser('version', help='显示版本信息')
    
    return system_parser


def handle_system_command(args):
    """系统管理命令总入口"""
    if args.system_action == 'status':
        handle_system_status(args)
    elif args.system_action == 'clean':
        handle_system_clean(args)
    elif args.system_action == 'version':
        handle_system_version(args)
    else:
        print("❌ 未知的系统操作")
        sys.exit(1)


def handle_system_status(args):
    """处理系统状态检查"""
    print("\n🔍 系统状态检查")
    print("=" * 80)
    
    try:
        from quant.services import SystemService

        status_result = SystemService().get_status()
        
        # 版本信息
        print(f"\n📦 版本信息:")
        print(f"  量化系统版本: {status_result.version}")
        
        # 环境变量
        print(f"\n🔐 环境配置:")
        for name, exists in status_result.environment.items():
            print(f"  {name}: {'已设置 ✅' if exists else '未设置 ❌'}")
        
        # 目录检查
        print(f"\n📁 目录状态:")
        for dir_name, exists in status_result.directories.items():
            status = '✅' if exists else '❌'
            print(f"  {dir_name}/: {status}")
        
        # 配置文件检查
        print(f"\n⚙️ 配置文件:")
        for config_file, exists in status_result.config_files.items():
            status = '✅' if exists else '❌'
            print(f"  {config_file}: {status}")
        
        print("\n✅ 状态检查完成")
        
    except Exception as e:
        print(f"❌ 状态检查失败: {e}")
        logger.error(f"系统状态检查错误: {e}", exc_info=True)
        sys.exit(1)


def handle_system_clean(args):
    """处理缓存清理"""
    print(f"\n🧹 清理缓存: {args.type}")
    print("=" * 80)
    
    try:
        import shutil
        
        cleaned = []
        
        if args.type in ['all', 'data']:
            cache_dir = Path('cache')
            if cache_dir.exists():
                for item in cache_dir.iterdir():
                    if item.is_dir() and item.name != 'etf_screener':
                        shutil.rmtree(item)
                        cleaned.append(f"cache/{item.name}")
        
        if args.type in ['all', 'reports']:
            reports_dir = Path('reports')
            if reports_dir.exists():
                for item in reports_dir.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                        cleaned.append(f"reports/{item.name}")
        
        if args.type in ['all', 'etf']:
            etf_cache = Path('cache/etf_screener')
            if etf_cache.exists():
                for item in etf_cache.iterdir():
                    if item.is_file():
                        item.unlink()
                        cleaned.append(f"cache/etf_screener/{item.name}")
        
        if cleaned:
            print(f"\n已清理 {len(cleaned)} 项:")
            for item in cleaned[:10]:
                print(f"  • {item}")
            if len(cleaned) > 10:
                print(f"  ... 以及其他 {len(cleaned) - 10} 项")
        else:
            print("\n无需清理")
        
        print("\n✅ 清理完成")
        
    except Exception as e:
        print(f"❌ 清理失败: {e}")
        logger.error(f"缓存清理错误: {e}", exc_info=True)
        sys.exit(1)


def handle_system_version(args):
    """显示版本信息"""
    try:
        from quant import __version__
        
        print(f"\n📦 量化交易系统")
        print("=" * 80)
        print(f"版本: {__version__}")
        print(f"Python: {sys.version.split()[0]}")
        print()
        
    except Exception as e:
        print(f"❌ 获取版本信息失败: {e}")
