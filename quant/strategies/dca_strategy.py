#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DCA Strategy - 定投策略 (Dollar Cost Averaging)
按固定周期投入固定金额购买资产
"""

from typing import Dict, Any
from datetime import timedelta
from .base_strategy import BaseStrategy, MarketState, TradingDecision


class DCAStrategy(BaseStrategy):
    """定投策略"""
    
    def __init__(self, symbol: str, config: Dict = None):
        super().__init__(symbol, config)
        self.initial_capital = 100000.0
        self.position = 0.0
        self.cash = self.initial_capital
        self.trades = []
        
        # 定投参数
        self.invest_interval_days = config.get('invest_interval_days', 30)  # 定投间隔天数
        self.invest_amount = config.get('invest_amount', 10000)  # 每次投入金额
        self.last_invest_date = None
        
    def reset(self, initial_capital: float = 100000.0):
        """重置策略状态"""
        self.initial_capital = initial_capital
        self.position = 0.0
        self.cash = initial_capital
        self.trades = []
        self.last_invest_date = None
        
    def makeDecision(self, market_state: MarketState) -> TradingDecision:
        """
        做出交易决策
        - 每隔固定时间买入固定金额
        """
        current_date = market_state.timestamp
        
        # 判断是否需要定投
        should_invest = False
        if self.last_invest_date is None:
            # 首次投资
            should_invest = True
        else:
            # 检查是否达到定投间隔
            days_since_last_invest = (current_date - self.last_invest_date).days
            if days_since_last_invest >= self.invest_interval_days:
                should_invest = True
        
        if should_invest and self.cash >= self.invest_amount:
            # 执行定投
            commission_rate = self.config.get('commission', 0.0003)
            available_cash = min(self.invest_amount, self.cash)
            net_cash = available_cash / (1 + commission_rate)
            shares_to_buy = int(net_cash / market_state.close)
            
            if shares_to_buy > 0:
                cost = shares_to_buy * market_state.close
                commission = cost * commission_rate
                total_cost = cost + commission
                
                self.position += shares_to_buy
                self.cash -= total_cost
                self.last_invest_date = current_date
                
                self.trades.append({
                    'timestamp': current_date,
                    'action': 'buy',
                    'price': market_state.close,
                    'shares': shares_to_buy,
                    'cost': total_cost,
                    'invest_round': len(self.trades) + 1
                })
                
                return TradingDecision(
                    action='buy',
                    amount=shares_to_buy,
                    reason=f'定投第{len(self.trades)}次: 买入 {shares_to_buy} 股',
                    confidence=1.0,
                    metadata={
                        'price': market_state.close,
                        'cost': total_cost,
                        'invest_round': len(self.trades)
                    }
                )
        
        # 持有状态
        return TradingDecision(
            action='hold',
            amount=0,
            reason='等待下次定投',
            confidence=1.0
        )
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        if not self.trades:
            return {
                'total_trades': 0,
                'total_invested': 0.0,
                'position': 0,
                'average_cost': 0.0
            }
        
        total_invested = sum(t['cost'] for t in self.trades)
        average_cost = total_invested / self.position if self.position > 0 else 0
        
        return {
            'total_trades': len(self.trades),
            'position': self.position,
            'total_invested': total_invested,
            'average_cost': average_cost,
            'remaining_cash': self.cash,
            'invest_interval_days': self.invest_interval_days,
            'invest_amount': self.invest_amount,
            'first_invest_date': self.trades[0]['timestamp'] if self.trades else None,
            'last_invest_date': self.trades[-1]['timestamp'] if self.trades else None
        }
