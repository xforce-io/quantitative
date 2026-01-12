#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一日志系统
Unified Logging System

提供结构化、可配置的日志记录功能
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器（用于终端输出）"""

    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',    # 青色
        'INFO': '\033[32m',     # 绿色
        'WARNING': '\033[33m',  # 黄色
        'ERROR': '\033[31m',    # 红色
        'CRITICAL': '\033[35m', # 紫色
    }
    RESET = '\033[0m'

    def format(self, record):
        # 添加颜色
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"

        # 格式化
        formatted = super().format(record)

        # 恢复原始级别名（避免影响其他handler）
        record.levelname = levelname

        return formatted


class StructuredLogger:
    """
    结构化日志记录器

    支持上下文信息和结构化字段
    """

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.context: Dict[str, Any] = {}

    def set_context(self, **kwargs):
        """
        设置上下文信息（会附加到后续所有日志）

        示例:
            logger.set_context(strategy='ma_crossover', symbol='000001.SZ')
        """
        self.context.update(kwargs)

    def clear_context(self):
        """清除上下文"""
        self.context.clear()

    def _format_extra(self, **kwargs) -> str:
        """格式化额外信息"""
        merged = {**self.context, **kwargs}
        if merged:
            parts = [f"{k}={v}" for k, v in merged.items()]
            return f" | {' '.join(parts)}"
        return ""

    def debug(self, msg: str, **kwargs):
        """调试日志"""
        self.logger.debug(msg + self._format_extra(**kwargs))

    def info(self, msg: str, **kwargs):
        """信息日志"""
        self.logger.info(msg + self._format_extra(**kwargs))

    def warning(self, msg: str, **kwargs):
        """警告日志"""
        self.logger.warning(msg + self._format_extra(**kwargs))

    def error(self, msg: str, **kwargs):
        """错误日志"""
        self.logger.error(msg + self._format_extra(**kwargs))

    def critical(self, msg: str, **kwargs):
        """严重错误日志"""
        self.logger.critical(msg + self._format_extra(**kwargs))

    def exception(self, msg: str, **kwargs):
        """异常日志（自动包含堆栈跟踪）"""
        self.logger.exception(msg + self._format_extra(**kwargs))


# 全局日志配置状态
_logging_configured = False


def setup_logging(
    log_level: str = 'INFO',
    log_dir: Optional[str] = None,
    enable_file_logging: bool = True,
    enable_console_logging: bool = True,
    enable_color: bool = True
) -> logging.Logger:
    """
    设置全局日志系统

    Args:
        log_level: 日志级别 ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        log_dir: 日志文件目录，默认为 'logs'
        enable_file_logging: 是否启用文件日志
        enable_console_logging: 是否启用控制台日志
        enable_color: 是否启用彩色输出（仅控制台）

    Returns:
        logging.Logger: 根日志记录器

    示例:
        >>> setup_logging('DEBUG', 'logs/', enable_color=True)
        >>> logger = get_logger(__name__)
        >>> logger.info("Application started")
    """
    global _logging_configured

    # 避免重复配置
    if _logging_configured:
        return logging.getLogger()

    # 根logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # 清除现有handlers（避免重复）
    root_logger.handlers.clear()

    # 日志格式
    file_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    if enable_color:
        console_format = ColoredFormatter(
            '%(levelname)s | %(name)s | %(message)s'
        )
    else:
        console_format = logging.Formatter(
            '%(levelname)s | %(name)s | %(message)s'
        )

    # 控制台Handler
    if enable_console_logging:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_format)
        console_handler.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)

    # 文件Handler
    if enable_file_logging:
        if log_dir is None:
            log_dir = 'logs'

        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # 主日志文件（按日期轮转）
        log_file = log_path / f"quant_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_file,
            when='midnight',
            interval=1,
            backupCount=30,  # 保留30天
            encoding='utf-8'
        )
        file_handler.setFormatter(file_format)
        file_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)

        # 错误日志单独文件
        error_log_file = log_path / 'errors.log'
        error_handler = logging.FileHandler(error_log_file, encoding='utf-8')
        error_handler.setFormatter(file_format)
        error_handler.setLevel(logging.ERROR)
        root_logger.addHandler(error_handler)

    # 设置第三方库的日志级别（避免过多输出）
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)

    _logging_configured = True

    root_logger.info(f"Logging configured: level={log_level}, dir={log_dir}")

    return root_logger


def get_logger(name: str) -> StructuredLogger:
    """
    获取结构化日志记录器

    Args:
        name: 日志记录器名称，通常使用 __name__

    Returns:
        StructuredLogger: 结构化日志记录器

    示例:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing data", symbol='000001.SZ', count=100)
    """
    return StructuredLogger(name)


def disable_logging():
    """禁用所有日志（用于测试）"""
    logging.disable(logging.CRITICAL)


def enable_logging():
    """启用日志"""
    logging.disable(logging.NOTSET)


# 便捷函数：直接使用的日志记录器
def get_simple_logger(name: str) -> logging.Logger:
    """
    获取简单的标准日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        logging.Logger: 标准日志记录器
    """
    return logging.getLogger(name)
