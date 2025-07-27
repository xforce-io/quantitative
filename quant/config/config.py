import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration class for quantitative trading system"""
    
    # Base directories
    BASE_DIR = os.path.dirname(os.path.dirname(__file__))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    LOG_DIR = os.path.join(BASE_DIR, 'log')
    
    # Ensure directories exist
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Data Provider Configuration
    DATA_PROVIDER_CONFIG = {
        'defaultProvider': os.getenv('DATA_PROVIDER', 'tushare'),  # Default provider
        'preferredProviders': ['tushare', 'yahoo'],  # Fallback order
        
        # Provider-specific configurations
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
    
    # Legacy support - keep for backward compatibility
    TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN', '')
    
    # Grid Trading Strategy Parameters - 优化版本
    GRID_STRATEGY_CONFIG = {
        'gridLevels': 6,         # 减少网格层数，避免过度交易
        'gridSpacing': 0.025,    # 增加网格间距到2.5%，确保有足够利润空间
        'maxPosition': 100000,   # Maximum position size in RMB
        'baseRatio': 0.4,        # 增加基础仓位到40%，提高稳定性
        'minTradeAmount': 1000,  # Minimum trade amount in RMB
        'commission': 0.0003,    # Commission rate (0.03%)
        'slippage': 0.001,       # Slippage rate (0.1%)
        'stopLoss': 0.20,        # 调整止损到20%
        'takeProfit': 0.40,      # 调整止盈到40%
        'rebalanceThreshold': 0.08,  # 调整重平衡阈值到8%
        'validateInputs': True,  # Validate input parameters
        
        # Dynamic grid adjustment parameters - 优化动态调整
        'dynamicEnabled': True,  # Enable dynamic grid adjustment
        'centerPricePeriod': 15, # 减少中心价格计算周期到15天，更敏感
        'adjustmentThreshold': 0.15,    # 提高调整阈值到15%，减少频繁调整
        'minAdjustmentRatio': 0.08,     # 提高最小调整比例到8%
        'adjustmentCooldown': 7,        # 增加冷却期到7天
        'centerPriceMethod': 'ema',     # 使用EMA更快响应趋势
    }
    
    # Enhanced Grid Strategy Configuration for better performance
    ENHANCED_GRID_CONFIG = {
        'gridLevels': 8,         # Fewer levels for better execution
        'gridSpacing': 0.015,    # 1.5% spacing for tighter grids  
        'maxPosition': 100000,   # Total capital allocation
        'baseRatio': 0.4,        # 40% base position for stability
        'minTradeAmount': 100,   # Minimum trade size
        'commission': 0.0003,    # 0.03% commission
        'slippage': 0.001,       # 0.1% slippage
        'stopLoss': 0.15,        # 15% stop loss
        'takeProfit': 0.30,      # 30% take profit
        'riskManagement': {
            'maxDrawdown': 0.20,    # 20% max drawdown
            'positionLimit': 0.8,   # Max 80% position
            'volatilityAdjust': True # Adjust for volatility
        }
    }
    
    # Backtesting Configuration
    BACKTEST_CONFIG = {
        'initialCapital': 100000,  # Initial capital in RMB
        'startDate': '20230101',   # Start date for backtesting
        'endDate': '20241201',     # End date for backtesting
    }
    
    # Legacy Data Configuration - keep for backward compatibility
    DATA_CONFIG = {
        'dataPath': DATA_DIR,
        'cacheEnabled': True,
        'cacheExpiry': 3600,  # Cache expiry in seconds
    }
    
    # Logging Configuration
    LOGGING_CONFIG = {
        'logDir': LOG_DIR,
        'level': 'INFO',
        'enableFileLogging': True,
        'enableConsoleLogging': True,
        'maxLogFileSize': 10 * 1024 * 1024,  # 10MB
        'backupCount': 5,
    } 