#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pyramid DCA Strategy - 金字塔定投策略
根据价格相对参考基准的偏离度，动态调整每期定投金额
"""

from typing import Dict, Any, List
from datetime import timedelta
import numpy as np
from .base_strategy import BaseStrategy, MarketState, TradingDecision


class PyramidDCAStrategy(BaseStrategy):
    """金字塔定投策略
    
    核心理念：
    - 正金字塔(normal): 价格越高投入越少，追求更低平均成本
    - 倒金字塔(inverse): 价格越高投入越多，顺应上涨趋势
    """
    
    def __init__(self, symbol: str, config: Dict = None):
        super().__init__(symbol, config)
        self.initial_capital = 100000.0
        self.position = 0.0
        self.cash = self.initial_capital
        self.trades = []
        
        # 基础定投参数
        self.invest_interval_days = config.get('invest_interval_days', 30)
        self.base_invest_amount = config.get('base_invest_amount', 10000)
        self.last_invest_date = None
        
        # 金字塔参数
        self.pyramid_type = config.get('pyramid_type', 'normal')  # 'normal' or 'inverse'
        self.reference_method = config.get('reference_method', 'ma')  # 'ma', 'cost', 'initial'
        self.reference_period = config.get('reference_period', 60)  # MA周期
        self.adjustment_factor = config.get('adjustment_factor', 0.5)  # 调整系数
        self.min_invest_ratio = config.get('min_invest_ratio', 0.3)  # 最小投入比例
        self.max_invest_ratio = config.get('max_invest_ratio', 2.0)  # 最大投入比例
        
        # 历史数据缓存
        self.price_history = []
        self.first_invest_price = None
        self.adjustment_history = []
        
    def reset(self, initial_capital: float = 100000.0):
        """重置策略状态"""
        self.initial_capital = initial_capital
        self.position = 0.0
        self.cash = initial_capital
        self.trades = []
        self.last_invest_date = None
        self.price_history = []
        self.first_invest_price = None
        self.adjustment_history = []
        
    def _calculate_reference_price(self, market_state: MarketState) -> float:
        """计算参考价格基准
        
        Args:
            market_state: 当前市场状态
            
        Returns:
            参考价格
        """
        if self.reference_method == 'ma':
            # 移动平均线作为参考
            if len(self.price_history) < self.reference_period:
                # 数据不足，使用现有数据的平均
                return np.mean(self.price_history) if self.price_history else market_state.close
            else:
                # 使用最近N日的移动平均
                return np.mean(self.price_history[-self.reference_period:])
                
        elif self.reference_method == 'cost':
            # 持仓成本价作为参考
            if self.position > 0:
                total_cost = sum(t['cost'] for t in self.trades)
                return total_cost / self.position
            else:
                return market_state.close
                
        elif self.reference_method == 'initial':
            # 首次定投价格作为参考
            if self.first_invest_price is not None:
                return self.first_invest_price
            else:
                return market_state.close
        else:
            # 默认使用当前价格
            return market_state.close
    
    def _calculate_invest_amount(self, market_state: MarketState) -> float:
        """计算本次定投金额
        
        Args:
            market_state: 当前市场状态
            
        Returns:
            实际投入金额
        """
        current_price = market_state.close
        reference_price = self._calculate_reference_price(market_state)
        
        # 计算价格偏离度
        if reference_price > 0:
            deviation = (current_price - reference_price) / reference_price
        else:
            deviation = 0.0
        
        # 根据金字塔类型计算调整比例
        if self.pyramid_type == 'normal':
            # 正金字塔：价格越高，投入越少
            adjust_ratio = 1.0 - deviation * self.adjustment_factor
        elif self.pyramid_type == 'inverse':
            # 倒金字塔：价格越高，投入越多
            adjust_ratio = 1.0 + deviation * self.adjustment_factor
        else:
            # 默认不调整
            adjust_ratio = 1.0
        
        # 限制在合理区间
        invest_ratio = max(self.min_invest_ratio, min(self.max_invest_ratio, adjust_ratio))
        actual_invest_amount = self.base_invest_amount * invest_ratio
        
        # 记录调整历史
        self.adjustment_history.append({
            'date': market_state.timestamp,
            'current_price': current_price,
            'reference_price': reference_price,
            'deviation': deviation,
            'invest_ratio': invest_ratio,
            'actual_amount': actual_invest_amount
        })
        
        return actual_invest_amount
        
    def makeDecision(self, market_state: MarketState) -> TradingDecision:
        """做出交易决策
        
        Args:
            market_state: 当前市场状态
            
        Returns:
            交易决策
        """
        # 更新价格历史
        self.price_history.append(market_state.close)
        
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
        
        if should_invest:
            # 计算本次投入金额
            invest_amount = self._calculate_invest_amount(market_state)
            
            # 检查现金是否充足
            if self.cash >= invest_amount:
                # 执行定投
                commission_rate = self.config.get('commission', 0.0003)
                available_cash = min(invest_amount, self.cash)
                net_cash = available_cash / (1 + commission_rate)
                shares_to_buy = int(net_cash / market_state.close)
                
                if shares_to_buy > 0:
                    cost = shares_to_buy * market_state.close
                    commission = cost * commission_rate
                    total_cost = cost + commission
                    
                    self.position += shares_to_buy
                    self.cash -= total_cost
                    self.last_invest_date = current_date
                    
                    # 记录首次投资价格
                    if self.first_invest_price is None:
                        self.first_invest_price = market_state.close
                    
                    # 获取当前调整信息
                    current_adjustment = self.adjustment_history[-1] if self.adjustment_history else {}
                    reference_price = current_adjustment.get('reference_price', market_state.close)
                    deviation = current_adjustment.get('deviation', 0.0)
                    invest_ratio = current_adjustment.get('invest_ratio', 1.0)
                    
                    self.trades.append({
                        'timestamp': current_date,
                        'action': 'buy',
                        'price': market_state.close,
                        'shares': shares_to_buy,
                        'cost': total_cost,
                        'invest_round': len(self.trades) + 1,
                        'invest_amount': invest_amount,
                        'reference_price': reference_price,
                        'deviation': deviation,
                        'invest_ratio': invest_ratio
                    })
                    
                    pyramid_desc = "正金字塔" if self.pyramid_type == 'normal' else "倒金字塔"
                    reason = (f'{pyramid_desc}定投第{len(self.trades)}次: '
                             f'买入{shares_to_buy}股, '
                             f'投入比例{invest_ratio:.2%}, '
                             f'偏离度{deviation:+.2%}')
                    
                    return TradingDecision(
                        action='buy',
                        amount=shares_to_buy,
                        reason=reason,
                        confidence=1.0,
                        metadata={
                            'price': market_state.close,
                            'cost': total_cost,
                            'invest_round': len(self.trades),
                            'invest_amount': invest_amount,
                            'reference_price': reference_price,
                            'deviation': deviation,
                            'invest_ratio': invest_ratio
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
                'average_cost': 0.0,
                'pyramid_type': self.pyramid_type,
                'reference_method': self.reference_method
            }
        
        total_invested = sum(t['cost'] for t in self.trades)
        average_cost = total_invested / self.position if self.position > 0 else 0
        
        # 统计投入金额的变化
        invest_amounts = [t['invest_amount'] for t in self.trades]
        invest_ratios = [t['invest_ratio'] for t in self.trades]
        
        metrics = {
            'total_trades': len(self.trades),
            'position': self.position,
            'total_invested': total_invested,
            'average_cost': average_cost,
            'remaining_cash': self.cash,
            
            # 金字塔参数
            'pyramid_type': self.pyramid_type,
            'reference_method': self.reference_method,
            'reference_period': self.reference_period,
            'adjustment_factor': self.adjustment_factor,
            
            # 投入统计
            'base_invest_amount': self.base_invest_amount,
            'average_invest_amount': np.mean(invest_amounts) if invest_amounts else 0,
            'max_invest_amount': max(invest_amounts) if invest_amounts else 0,
            'min_invest_amount': min(invest_amounts) if invest_amounts else 0,
            'invest_amount_std': np.std(invest_amounts) if invest_amounts else 0,
            
            # 比例统计
            'average_invest_ratio': np.mean(invest_ratios) if invest_ratios else 0,
            'max_invest_ratio': max(invest_ratios) if invest_ratios else 0,
            'min_invest_ratio': min(invest_ratios) if invest_ratios else 0,
            
            # 时间信息
            'invest_interval_days': self.invest_interval_days,
            'first_invest_date': self.trades[0]['timestamp'] if self.trades else None,
            'last_invest_date': self.trades[-1]['timestamp'] if self.trades else None,
            'first_invest_price': self.first_invest_price,
            
            # 调整历史（用于详细分析）
            'adjustment_history': self.adjustment_history[-10:]  # 只保留最近10次
        }
        
        return metrics
