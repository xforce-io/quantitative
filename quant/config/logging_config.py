#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Logging Configuration
日志配置

This module provides logging configuration for the quantitative trading system
此模块为量化交易系统提供日志配置
"""

import os
import logging
import logging.config
from datetime import datetime

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'log')

# 确保日志目录存在
os.makedirs(LOG_DIR, exist_ok=True)

# 日志配置字典
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'detailed': {
            'format': '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(funcName)s(): %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'simple': {
            'format': '[%(levelname)s] %(message)s'
        }
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'stream': 'ext://sys.stdout'
        },
        'file_info': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'standard',
            'filename': os.path.join(LOG_DIR, 'trading.log'),
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'encoding': 'utf-8'
        },
        'file_debug': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'detailed',
            'filename': os.path.join(LOG_DIR, 'debug.log'),
            'maxBytes': 10485760,  # 10MB
            'backupCount': 3,
            'encoding': 'utf-8'
        },
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'detailed',
            'filename': os.path.join(LOG_DIR, 'error.log'),
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'encoding': 'utf-8'
        },
        'backtest_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'standard',
            'filename': os.path.join(LOG_DIR, 'backtest.log'),
            'maxBytes': 10485760,  # 10MB
            'backupCount': 10,
            'encoding': 'utf-8'
        },
        'strategy_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'standard',
            'filename': os.path.join(LOG_DIR, 'strategy.log'),
            'maxBytes': 10485760,  # 10MB
            'backupCount': 10,
            'encoding': 'utf-8'
        }
    },
    'loggers': {
        'quant': {
            'level': 'DEBUG',
            'handlers': ['console', 'file_info', 'file_debug', 'file_error'],
            'propagate': False
        },
        'quant.strategies': {
            'level': 'DEBUG',
            'handlers': ['console', 'strategy_file', 'file_error'],
            'propagate': False
        },
        'quant.engines': {
            'level': 'DEBUG',
            'handlers': ['console', 'backtest_file', 'file_error'],
            'propagate': False
        },
        'quant.data_providers': {
            'level': 'INFO',
            'handlers': ['console', 'file_info', 'file_error'],
            'propagate': False
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console', 'file_info']
    }
}

def setupLogging(configDict=None, defaultLevel=logging.INFO):
    """
    Setup logging configuration
    设置日志配置
    
    Args:
        configDict (dict): Custom logging configuration
        defaultLevel (int): Default logging level
    """
    if configDict is None:
        configDict = LOGGING_CONFIG
    
    try:
        logging.config.dictConfig(configDict)
        print(f"Logging configured successfully. Log files will be saved to: {LOG_DIR}")
    except Exception as e:
        logging.basicConfig(level=defaultLevel)
        print(f"Failed to configure logging: {e}")
        print("Using basic logging configuration")

def getLogger(name):
    """
    Get a logger instance
    获取日志记录器实例
    
    Args:
        name (str): Logger name
        
    Returns:
        logging.Logger: Logger instance
    """
    return logging.getLogger(name)

# 自动设置日志配置
setupLogging() 