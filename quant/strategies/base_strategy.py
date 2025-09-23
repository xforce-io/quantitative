#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Base Strategy Interface
策略基类 - 统一策略接口设计
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

@dataclass
class MarketState:
    """市场状态统一数据结构"""
    timestamp: datetime
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    technicalIndicators: Dict[str, float] = None
    
    @property
    def currentPrice(self) -> float:
        """Alias for close price for backward compatibility."""
        return self.close

    def __post_init__(self):
        if self.technicalIndicators is None:
            self.technicalIndicators = {}

@dataclass
class TradingDecision:
    """交易决策统一返回格式"""
    action: str  # 'buy', 'sell', 'hold'
    amount: float
    reason: str
    confidence: float = 1.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class BaseStrategy(ABC):
    """策略基类 - 定义统一接口"""
    
    def __init__(self, symbol: str, config: Optional[Dict] = None):
        self.symbol = symbol
        self.config = config or {}
        
    @abstractmethod
    def makeDecision(self, market_state: MarketState) -> TradingDecision:
        """统一的决策接口
        
        Args:
            market_state: 市场状态
            
        Returns:
            TradingDecision: 交易决策
        """
        pass
    
    @abstractmethod
    def reset(self, initial_capital: float = 100000.0):
        """重置策略状态"""
        pass
    
    @abstractmethod
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        pass
    
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return self.__class__.__name__
    
    def get_strategy_params(self) -> Dict[str, Any]:
        """获取策略参数"""
        return self.config.copy()
