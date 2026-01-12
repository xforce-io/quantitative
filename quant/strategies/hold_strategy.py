#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hold Strategy - 买入持有策略
最简单的投资策略：初始买入并持有到结束
"""

from typing import Dict, Any
from .base_strategy import BaseStrategy, MarketState, TradingDecision


class HoldStrategy(BaseStrategy):
    """买入持有策略"""
    
    def __init__(self, symbol: str, config: Dict = None):
        super().__init__(symbol, config)
        self.initial_capital = 100000.0
        self.position = 0.0  # 持仓数量
        self.cash = self.initial_capital
        self.has_bought = False  # 是否已经买入
        self.trades = []
        
    def reset(self, initial_capital: float = 100000.0):
        """重置策略状态"""
        self.initial_capital = initial_capital
        self.position = 0.0
        self.cash = initial_capital
        self.has_bought = False
        self.trades = []
        
    def makeDecision(self, market_state: MarketState) -> TradingDecision:
        """
        做出交易决策
        - 第一次调用时全仓买入
        - 之后一直持有
        """
        if not self.has_bought:
            # 首次买入：全仓买入
            commission_rate = self.config.get('commission', 0.0003)
            available_cash = self.cash * (1 - commission_rate)
            shares_to_buy = int(available_cash / market_state.close)
            
            if shares_to_buy > 0:
                self.position = shares_to_buy
                cost = shares_to_buy * market_state.close
                commission = cost * commission_rate
                self.cash -= (cost + commission)
                self.has_bought = True
                
                self.trades.append({
                    'timestamp': market_state.timestamp,
                    'action': 'buy',
                    'price': market_state.close,
                    'shares': shares_to_buy,
                    'cost': cost + commission
                })
                
                return TradingDecision(
                    action='buy',
                    amount=shares_to_buy,
                    reason=f'初始买入 {shares_to_buy} 股',
                    confidence=1.0,
                    metadata={
                        'price': market_state.close,
                        'cost': cost + commission
                    }
                )
        
        # 持有状态
        return TradingDecision(
            action='hold',
            amount=0,
            reason='持有',
            confidence=1.0
        )
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        if not self.trades:
            return {
                'total_trades': 0,
                'total_return': 0.0,
                'position': 0
            }
        
        # 基本统计
        return {
            'total_trades': len(self.trades),
            'position': self.position,
            'initial_capital': self.initial_capital,
            'buy_price': self.trades[0]['price'] if self.trades else 0,
            'buy_date': self.trades[0]['timestamp'] if self.trades else None
        }
