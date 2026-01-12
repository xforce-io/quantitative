#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
自动将print语句转换为logging调用的工具

用法:
    # 分析模式（不修改文件）
    python scripts/migrate_print_to_logging.py --dry-run

    # 执行迁移
    python scripts/migrate_print_to_logging.py

    # 迁移特定目录
    python scripts/migrate_print_to_logging.py quant/strategies/
"""

import re
import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Dict


class PrintToLoggingMigrator:
    """Print语句迁移器"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.stats = {
            'files_scanned': 0,
            'files_modified': 0,
            'total_replacements': 0,
            'by_level': {
                'info': 0,
                'warning': 0,
                'error': 0,
                'debug': 0
            }
        }

    def migrate_file(self, file_path: Path) -> Tuple[int, List[str]]:
        """
        迁移单个文件

        Returns:
            (替换数量, 警告列表)
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            return 0, [f"⚠️  Cannot read {file_path}: encoding error"]

        original = content
        warnings = []
        count = 0

        # 检查是否已有logger
        has_logger = (
            'get_logger(__name__)' in content or
            'logging.getLogger' in content
        )

        # 如果没有logger，添加导入和初始化
        if not has_logger and 'print(' in content:
            content = self._add_logger_import(content)

        # 替换print语句
        content, level_counts = self._replace_print_statements(content)

        # 统计
        for level, n in level_counts.items():
            self.stats['by_level'][level] += n
            count += n

        # 保存文件
        if content != original:
            if not self.dry_run:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.stats['files_modified'] += 1

            self.stats['total_replacements'] += count

        return count, warnings

    def _add_logger_import(self, content: str) -> str:
        """添加logger导入"""
        # 查找导入区域
        import_pattern = r'^(from .+ import .+|import .+)$'
        lines = content.split('\n')

        # 找到最后一个import语句的位置
        last_import_idx = -1
        for i, line in enumerate(lines):
            if re.match(import_pattern, line.strip()):
                last_import_idx = i

        if last_import_idx >= 0:
            # 在最后一个import之后添加logger导入
            insert_lines = [
                '',
                'from quant.core.logging_config import get_logger',
                'logger = get_logger(__name__)',
                ''
            ]
            lines[last_import_idx + 1:last_import_idx + 1] = insert_lines

        return '\n'.join(lines)

    def _replace_print_statements(self, content: str) -> Tuple[str, Dict[str, int]]:
        """
        替换print语句

        Returns:
            (修改后的内容, 各级别计数)
        """
        level_counts = {
            'info': 0,
            'warning': 0,
            'error': 0,
            'debug': 0
        }

        # 模式和替换规则
        patterns = [
            # print(f"Error: xxx") -> logger.error("xxx")
            (
                r'print\(f?["\'](?:Error|ERROR|错误)[:\s]+(.+?)["\'](?:\.format\(.+?\))?\)',
                r'logger.error("\1")',
                'error'
            ),

            # print(f"Warning: xxx") -> logger.warning("xxx")
            (
                r'print\(f?["\'](?:Warning|WARNING|警告|⚠)[:\s]+(.+?)["\'](?:\.format\(.+?\))?\)',
                r'logger.warning("\1")',
                'warning'
            ),

            # print(f"DEBUG: xxx") -> logger.debug("xxx")
            (
                r'print\(f?["\'](?:Debug|DEBUG|调试)[:\s]+(.+?)["\'](?:\.format\(.+?\))?\)',
                r'logger.debug("\1")',
                'debug'
            ),

            # print(f"xxx {var}") -> logger.info("xxx %s", var)
            # 这个比较复杂，暂时简化处理
            (
                r'print\(f["\'](.+?)["\'](?:\.format\(.+?\))?\)',
                r'logger.info("\1")',
                'info'
            ),

            # print("xxx") -> logger.info("xxx")
            (
                r'print\((["\'].+?["\']\))',
                r'logger.info(\1',
                'info'
            ),

            # print(variable) -> logger.info("%s", variable)
            (
                r'print\(([a-zA-Z_][a-zA-Z0-9_]*)\)',
                r'logger.info("%s", \1)',
                'info'
            ),
        ]

        for pattern, replacement, level in patterns:
            new_content, n = re.subn(pattern, replacement, content)
            if n > 0:
                content = new_content
                level_counts[level] += n

        return content, level_counts

    def migrate_directory(self, directory: Path):
        """迁移整个目录"""
        print(f"{'='*80}")
        print(f"Migrating print statements in: {directory}")
        print(f"Dry run: {self.dry_run}")
        print(f"{'='*80}\n")

        for py_file in directory.rglob('*.py'):
            # 跳过虚拟环境和缓存
            if any(skip in str(py_file) for skip in ['venv', '__pycache__', '.git', 'bak']):
                continue

            self.stats['files_scanned'] += 1

            count, warnings = self.migrate_file(py_file)

            if count > 0:
                status = "Would modify" if self.dry_run else "✅ Modified"
                print(f"{status}: {py_file.relative_to(directory.parent)} ({count} replacements)")

            for warning in warnings:
                print(warning)

    def print_summary(self):
        """打印摘要"""
        print(f"\n{'='*80}")
        print("Migration Summary")
        print(f"{'='*80}")
        print(f"Files scanned: {self.stats['files_scanned']}")
        print(f"Files modified: {self.stats['files_modified']}")
        print(f"Total replacements: {self.stats['total_replacements']}")
        print(f"\nBy level:")
        for level, count in self.stats['by_level'].items():
            if count > 0:
                print(f"  {level}: {count}")
        print(f"{'='*80}")


def main():
    parser = argparse.ArgumentParser(
        description='Migrate print() statements to logger calls'
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='quant',
        help='Path to migrate (default: quant/)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without modifying files'
    )

    args = parser.parse_args()

    # 获取路径
    path = Path(args.path)
    if not path.exists():
        print(f"❌ Error: Path does not exist: {path}")
        sys.exit(1)

    # 执行迁移
    migrator = PrintToLoggingMigrator(dry_run=args.dry_run)

    if path.is_file():
        count, warnings = migrator.migrate_file(path)
        if count > 0:
            print(f"✅ Modified {path}: {count} replacements")
    else:
        migrator.migrate_directory(path)

    migrator.print_summary()

    if args.dry_run:
        print("\n💡 This was a dry run. Use without --dry-run to apply changes.")


if __name__ == '__main__':
    main()
