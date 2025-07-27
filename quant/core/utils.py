#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quantitative Trading System Utils
量化交易系统工具模块

提供通用的工具函数和错误处理
Common utility functions and error handling
"""

import os
import sys
import logging
import json
import yaml
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from functools import wraps

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent

class QuantError(Exception):
    """量化系统基础异常类"""
    pass

class ConfigurationError(QuantError):
    """配置错误"""
    pass

class DataError(QuantError):
    """数据相关错误"""
    pass

class AnalysisError(QuantError):
    """分析错误"""
    pass

def setupUnifiedLogging(
    logLevel: str = 'INFO',
    loggerName: str = 'quant',
    logFile: Optional[str] = None
) -> logging.Logger:
    """
    设置统一的日志配置
    
    Args:
        logLevel: 日志级别
        loggerName: 日志器名称
        logFile: 日志文件名 (可选)
    
    Returns:
        logging.Logger: 配置好的日志器
    """
    # 确保logs目录存在
    logsDir = PROJECT_ROOT / 'logs'
    logsDir.mkdir(exist_ok=True)
    
    # 创建日志器
    logger = logging.getLogger(loggerName)
    logger.setLevel(getattr(logging, logLevel.upper(), logging.INFO))
    
    # 清除已有处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 创建格式器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 控制台处理器
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)
    
    # 文件处理器
    if logFile is None:
        logFile = f'quant_system_{datetime.now().strftime("%Y%m%d")}.log'
    
    fileHandler = logging.FileHandler(logsDir / logFile)
    fileHandler.setFormatter(formatter)
    logger.addHandler(fileHandler)
    
    return logger

def errorHandler(logger: Optional[logging.Logger] = None):
    """
    统一错误处理装饰器
    
    Args:
        logger: 日志器实例
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except QuantError as e:
                if logger:
                    logger.error(f"Quantitative system error in {func.__name__}: {str(e)}")
                raise
            except Exception as e:
                if logger:
                    logger.error(f"Unexpected error in {func.__name__}: {str(e)}")
                raise QuantError(f"Unexpected error in {func.__name__}: {str(e)}")
        return wrapper
    return decorator

def ensureDirectoryExists(dirPath: Union[str, Path]) -> Path:
    """
    确保目录存在，如不存在则创建
    
    Args:
        dirPath: 目录路径
    
    Returns:
        Path: 目录路径对象
    """
    path = Path(dirPath)
    path.mkdir(parents=True, exist_ok=True)
    return path

def loadYamlConfig(configPath: Union[str, Path]) -> Dict[str, Any]:
    """
    加载YAML配置文件
    
    Args:
        configPath: 配置文件路径
    
    Returns:
        Dict[str, Any]: 配置数据
    
    Raises:
        ConfigurationError: 配置加载失败
    """
    try:
        path = Path(configPath)
        if not path.exists():
            raise ConfigurationError(f"Configuration file not found: {configPath}")
        
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
            
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Failed to parse YAML config {configPath}: {str(e)}")
    except Exception as e:
        raise ConfigurationError(f"Failed to load config {configPath}: {str(e)}")

def saveJsonReport(
    data: Dict[str, Any],
    filePath: Union[str, Path],
    ensureAscii: bool = False
) -> Path:
    """
    保存JSON格式报告
    
    Args:
        data: 要保存的数据
        filePath: 文件路径
        ensureAscii: 是否确保ASCII编码
    
    Returns:
        Path: 保存的文件路径
    """
    path = Path(filePath)
    ensureDirectoryExists(path.parent)
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=ensureAscii, indent=2, default=str)
    
    return path

def saveMarkdownReport(
    title: str,
    content: Dict[str, Any],
    filePath: Union[str, Path]
) -> Path:
    """
    保存Markdown格式报告
    
    Args:
        title: 报告标题
        content: 报告内容
        filePath: 文件路径
    
    Returns:
        Path: 保存的文件路径
    """
    path = Path(filePath)
    ensureDirectoryExists(path.parent)
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # 递归写入内容
        def writeContent(data, level=2):
            for key, value in data.items():
                f.write("#" * level + f" {key}\n\n")
                
                if isinstance(value, dict):
                    writeContent(value, level + 1)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            for k, v in item.items():
                                f.write(f"- **{k}**: {v}\n")
                        else:
                            f.write(f"- {item}\n")
                    f.write("\n")
                else:
                    f.write(f"{value}\n\n")
        
        writeContent(content)
    
    return path

def formatNumber(
    value: Union[int, float],
    decimals: int = 2,
    percentage: bool = False,
    prefix: str = "",
    suffix: str = ""
) -> str:
    """
    格式化数字显示
    
    Args:
        value: 数值
        decimals: 小数位数
        percentage: 是否为百分比
        prefix: 前缀
        suffix: 后缀
    
    Returns:
        str: 格式化后的字符串
    """
    if percentage:
        value = value * 100
        suffix = "%" + suffix
    
    formatted = f"{value:.{decimals}f}"
    return f"{prefix}{formatted}{suffix}"

def formatCurrency(value: Union[int, float], currency: str = "¥") -> str:
    """
    格式化货币显示
    
    Args:
        value: 金额
        currency: 货币符号
    
    Returns:
        str: 格式化后的货币字符串
    """
    if abs(value) >= 10000:
        return f"{currency}{value/10000:.2f}万"
    else:
        return f"{currency}{value:.2f}"

def cleanOldFiles(
    directory: Union[str, Path],
    pattern: str = "*",
    daysOld: int = 30,
    dryRun: bool = False
) -> List[Path]:
    """
    清理旧文件
    
    Args:
        directory: 目录路径
        pattern: 文件模式
        daysOld: 文件天数阈值
        dryRun: 是否只是预览，不实际删除
    
    Returns:
        List[Path]: 被删除(或将被删除)的文件列表
    """
    directory = Path(directory)
    if not directory.exists():
        return []
    
    cutoffTime = datetime.now() - timedelta(days=daysOld)
    deletedFiles = []
    
    for filePath in directory.glob(pattern):
        if filePath.is_file():
            fileTime = datetime.fromtimestamp(filePath.stat().st_mtime)
            if fileTime < cutoffTime:
                if not dryRun:
                    filePath.unlink()
                deletedFiles.append(filePath)
    
    return deletedFiles

def getProjectPaths() -> Dict[str, Path]:
    """
    获取项目主要路径
    
    Returns:
        Dict[str, Path]: 路径字典
    """
    return {
        'root': PROJECT_ROOT,
        'bin': PROJECT_ROOT / 'bin',
        'quant': PROJECT_ROOT / 'quant',
        'config': PROJECT_ROOT / 'config',
        'data': PROJECT_ROOT / 'data',
        'cache': PROJECT_ROOT / 'cache',
        'logs': PROJECT_ROOT / 'logs',
        'reports': PROJECT_ROOT / 'reports',
        'docs': PROJECT_ROOT / 'docs',
        'demo': PROJECT_ROOT / 'demo'
    }

def validateEnvironment() -> Dict[str, bool]:
    """
    验证环境配置
    
    Returns:
        Dict[str, bool]: 验证结果
    """
    paths = getProjectPaths()
    results = {}
    
    # 检查关键目录
    for name, path in paths.items():
        results[f'dir_{name}'] = path.exists()
    
    # 检查环境文件
    results['env_file'] = (PROJECT_ROOT / '.env').exists()
    
    # 检查requirements文件
    results['requirements'] = (PROJECT_ROOT / 'requirements.txt').exists()
    
    # 检查主要配置文件
    configDir = paths['config']
    configFiles = ['system_config.yaml', 'trading_config.yaml', 'news_analysis_config.yaml']
    for configFile in configFiles:
        results[f'config_{configFile.replace(".yaml", "")}'] = (configDir / configFile).exists()
    
    return results

def printColoredText(text: str, color: str = 'white') -> None:
    """
    打印彩色文本 (简单版本)
    
    Args:
        text: 文本内容
        color: 颜色 (支持: red, green, yellow, blue, white)
    """
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'white': '\033[97m',
        'reset': '\033[0m'
    }
    
    colorCode = colors.get(color, colors['white'])
    print(f"{colorCode}{text}{colors['reset']}")

def createSystemReport() -> Dict[str, Any]:
    """
    创建系统状态报告
    
    Returns:
        Dict[str, Any]: 系统状态报告
    """
    paths = getProjectPaths()
    validation = validateEnvironment()
    
    # 计算目录大小
    def getDirSize(path: Path) -> int:
        if not path.exists():
            return 0
        return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'project_root': str(PROJECT_ROOT),
        'environment_validation': validation,
        'directory_sizes': {
            name: {
                'exists': path.exists(),
                'size_mb': getDirSize(path) / (1024 * 1024) if path.exists() else 0
            }
            for name, path in paths.items()
        },
        'python_version': sys.version,
        'system_health': {
            'config_files_ok': sum(1 for k, v in validation.items() if k.startswith('config_') and v),
            'directories_ok': sum(1 for k, v in validation.items() if k.startswith('dir_') and v),
            'env_configured': validation.get('env_file', False)
        }
    }
    
    return report

# 常用的日志器实例
DEFAULT_LOGGER = setupUnifiedLogging() 