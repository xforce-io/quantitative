#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Legacy Config Compatibility Layer
遗留配置兼容层

This module provides backward compatibility for code that still imports
from `quant.config.config`. New code should use `quant.core.config` instead.

Migration guide:
    # Old way (deprecated):
    from quant.config.config import Config
    token = Config.TUSHARE_TOKEN
    
    # New way (recommended):
    from quant.core.config import get_config
    config = get_config()
    token = config.get('providers.tushare.token')
"""

import os
import warnings
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """
    Legacy configuration class for backward compatibility.
    
    ⚠️ DEPRECATED: Use `quant.core.config.get_config()` instead.
    
    This class provides the same interface as the old Config class
    to maintain backward compatibility during migration.
    """
    
    # Base directories - computed from this file's location
    _project_root = Path(__file__).parent.parent.parent
    BASE_DIR = str(_project_root)
    DATA_DIR = str(_project_root / 'data')
    LOG_DIR = str(_project_root / 'log')
    
    # Ensure directories exist
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Data Provider Configuration
    DATA_PROVIDER_CONFIG = {
        'defaultProvider': os.getenv('DATA_PROVIDER', 'tushare'),
        'preferredProviders': ['tushare', 'yahoo'],
        
        'tushare': {
            'token': os.getenv('TUSHARE_TOKEN', ''),
            'dataPath': os.path.join(DATA_DIR, 'tushare'),
            'cacheEnabled': True,
            'cacheExpiry': 3600,
        },
        
        'yahoo': {
            'dataPath': os.path.join(DATA_DIR, 'yahoo'),
            'cacheEnabled': True,
            'cacheExpiry': 3600,
        }
    }
    
    # Legacy support
    TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN', '')
    
    # Grid Trading Strategy Parameters
    GRID_STRATEGY_CONFIG = {
        'gridLevels': 6,
        'gridSpacing': 0.025,
        'maxPosition': 100000,
        'baseRatio': 0.4,
        'minTradeAmount': 1000,
        'commission': 0.0003,
        'slippage': 0.001,
        'stopLoss': 0.20,
        'takeProfit': 0.40,
        'rebalanceThreshold': 0.08,
        'validateInputs': True,
        'dynamicEnabled': True,
        'centerPricePeriod': 15,
        'adjustmentThreshold': 0.15,
        'minAdjustmentRatio': 0.08,
        'adjustmentCooldown': 7,
        'centerPriceMethod': 'ema',
    }
    
    # Enhanced Grid Strategy Configuration
    ENHANCED_GRID_CONFIG = {
        'gridLevels': 8,
        'gridSpacing': 0.015,
        'maxPosition': 100000,
        'baseRatio': 0.4,
        'minTradeAmount': 100,
        'commission': 0.0003,
        'slippage': 0.001,
        'stopLoss': 0.15,
        'takeProfit': 0.30,
        'riskManagement': {
            'maxDrawdown': 0.20,
            'positionLimit': 0.8,
            'volatilityAdjust': True
        }
    }
    
    # Backtesting Configuration
    BACKTEST_CONFIG = {
        'initialCapital': 100000,
        'startDate': '20230101',
        'endDate': '20241201',
    }
    
    # Legacy Data Configuration
    DATA_CONFIG = {
        'dataPath': DATA_DIR,
        'cacheEnabled': True,
        'cacheExpiry': 3600,
    }
    
    # Logging Configuration
    LOGGING_CONFIG = {
        'logDir': LOG_DIR,
        'level': 'INFO',
        'enableFileLogging': True,
        'enableConsoleLogging': True,
        'maxLogFileSize': 10 * 1024 * 1024,
        'backupCount': 5,
    }


def _emit_deprecation_warning():
    """Emit deprecation warning when this module is imported directly."""
    warnings.warn(
        "quant.core.legacy_config.Config is deprecated. "
        "Use quant.core.config.get_config() for the new configuration API.",
        DeprecationWarning,
        stacklevel=3
    )
