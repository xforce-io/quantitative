#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Moving Average Crossover Strategy
均线交叉策略

实现基于移动平均线交叉的趋势跟踪策略
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class MACrossoverTrade:
    """均线交叉策略交易记录"""
    timestamp: datetime
    action: str  # 'buy' or 'sell'
    price: float
    shares: int
    amount: float
    commission: float
    balance: float
    position: int
    signal_type: str  # 'golden_cross' or 'death_cross'
    ma_short: float
    ma_long: float


class MACrossoverStrategy:
    """移动平均线交叉策略
    
    策略逻辑:
    - 买入信号: 短期均线上穿长期均线 (金叉)
    - 卖出信号: 短期均线下穿长期均线 (死叉)
    """
    
    def __init__(self, symbol: str, config: Optional[Dict] = None):
        """初始化策略
        
        Args:
            symbol: 股票代码
            config: 策略配置参数
        """
        self.symbol = symbol
        self.config = config or {}
        
        # 策略参数
        self.ma_short = self.config.get('ma_short', 5)  # 短期均线周期
        self.ma_long = self.config.get('ma_long', 10)   # 长期均线周期
        self.commission = self.config.get('commission', 0.0003)  # 手续费率
        self.slippage = self.config.get('slippage', 0.001)       # 滑点率
        self.min_shares = self.config.get('min_shares', 100)     # 最小交易股数
        self.position_size = self.config.get('position_size', 1.0)  # 仓位大小(0-1)
        
        # 过滤条件
        self.min_volume_ratio = self.config.get('min_volume_ratio', 1.0)  # 最小成交量倍数
        self.min_price_change = self.config.get('min_price_change', 0.005)  # 最小价格变化
        
        # 状态变量
        self.reset()
    
    def reset(self, initial_capital: float = 100000.0):
        """重置策略状态"""
        self.initial_capital = initial_capital
        self.current_cash = initial_capital
        self.current_position = 0  # 持股数量
        self.total_value = initial_capital
        self.trades: List[MACrossoverTrade] = []
        
        # 技术指标历史
        self.price_history = []
        self.volume_history = []
        self.ma_short_history = []
        self.ma_long_history = []
        
        # 信号状态
        self.last_signal = None
        self.signal_count = 0
        
    def add_data_point(self, timestamp: datetime, price: float, volume: float = 0):
        """添加数据点并计算技术指标"""
        self.price_history.append(price)
        self.volume_history.append(volume)
        
        # 计算移动平均线
        if len(self.price_history) >= self.ma_short:
            ma_short = np.mean(self.price_history[-self.ma_short:])
            self.ma_short_history.append(ma_short)
        else:
            self.ma_short_history.append(np.nan)
            
        if len(self.price_history) >= self.ma_long:
            ma_long = np.mean(self.price_history[-self.ma_long:])
            self.ma_long_history.append(ma_long)
        else:
            self.ma_long_history.append(np.nan)
    
    def generate_signal(self, timestamp: datetime, price: float, volume: float = 0) -> Optional[str]:
        """生成交易信号
        
        Returns:
            'buy': 买入信号 (金叉)
            'sell': 卖出信号 (死叉)
            None: 无信号
        """
        self.add_data_point(timestamp, price, volume)
        
        # 需要足够的历史数据
        if len(self.ma_short_history) < 2 or len(self.ma_long_history) < 2:
            return None
            
        # 获取当前和前一期的均线值
        ma_short_curr = self.ma_short_history[-1]
        ma_long_curr = self.ma_long_history[-1]
        ma_short_prev = self.ma_short_history[-2]
        ma_long_prev = self.ma_long_history[-2]
        
        # 检查均线是否有效
        if np.isnan(ma_short_curr) or np.isnan(ma_long_curr) or \
           np.isnan(ma_short_prev) or np.isnan(ma_long_prev):
            return None
        
        # 检测交叉信号
        signal = None
        
        # 金叉: 短期均线从下方穿越长期均线
        if ma_short_prev <= ma_long_prev and ma_short_curr > ma_long_curr:
            if self._validate_signal('buy', timestamp, price, volume):
                signal = 'buy'
                
        # 死叉: 短期均线从上方穿越长期均线
        elif ma_short_prev >= ma_long_prev and ma_short_curr < ma_long_curr:
            if self._validate_signal('sell', timestamp, price, volume):
                signal = 'sell'
        
        return signal
    
    def _validate_signal(self, signal: str, timestamp: datetime, price: float, volume: float) -> bool:
        """验证信号有效性"""
        # 检查成交量
        if len(self.volume_history) >= 20 and volume > 0:
            avg_volume = np.mean(self.volume_history[-20:])
            if volume < avg_volume * self.min_volume_ratio:
                return False
        
        # 检查价格变化幅度
        if len(self.price_history) >= 2:
            price_change = abs(price - self.price_history[-2]) / self.price_history[-2]
            if price_change < self.min_price_change:
                return False
        
        # 避免频繁交易 (可选)
        if self.last_signal and self.last_signal == signal:
            return False
            
        return True
    
    def execute_trade(self, timestamp: datetime, price: float, signal: str, volume: float = 0):
        """执行交易"""
        if signal == 'buy' and self.current_cash > 0:
            self._execute_buy(timestamp, price, volume)
        elif signal == 'sell' and self.current_position > 0:
            self._execute_sell(timestamp, price, volume)
            
        self.last_signal = signal
        self.signal_count += 1
    
    def _execute_buy(self, timestamp: datetime, price: float, volume: float):
        """执行买入"""
        # 计算可买股数
        available_cash = self.current_cash * self.position_size
        shares_to_buy = int(available_cash / (price * (1 + self.slippage)))
        
        # 调整为100股的整数倍
        shares_to_buy = (shares_to_buy // self.min_shares) * self.min_shares
        
        if shares_to_buy >= self.min_shares:
            # 计算实际成本
            actual_price = price * (1 + self.slippage)
            trade_amount = shares_to_buy * actual_price
            commission = trade_amount * self.commission
            total_cost = trade_amount + commission
            
            # 更新仓位
            self.current_cash -= total_cost
            self.current_position += shares_to_buy
            
            # 记录交易
            trade = MACrossoverTrade(
                timestamp=timestamp,
                action='buy',
                price=actual_price,
                shares=shares_to_buy,
                amount=trade_amount,
                commission=commission,
                balance=self.current_cash,
                position=self.current_position,
                signal_type='golden_cross',
                ma_short=self.ma_short_history[-1],
                ma_long=self.ma_long_history[-1]
            )
            self.trades.append(trade)
    
    def _execute_sell(self, timestamp: datetime, price: float, volume: float):
        """执行卖出"""
        shares_to_sell = self.current_position
        
        if shares_to_sell > 0:
            # 计算实际收入
            actual_price = price * (1 - self.slippage)
            trade_amount = shares_to_sell * actual_price
            commission = trade_amount * self.commission
            net_proceeds = trade_amount - commission
            
            # 更新仓位
            self.current_cash += net_proceeds
            self.current_position = 0
            
            # 记录交易
            trade = MACrossoverTrade(
                timestamp=timestamp,
                action='sell',
                price=actual_price,
                shares=shares_to_sell,
                amount=trade_amount,
                commission=commission,
                balance=self.current_cash,
                position=self.current_position,
                signal_type='death_cross',
                ma_short=self.ma_short_history[-1],
                ma_long=self.ma_long_history[-1]
            )
            self.trades.append(trade)
    
    def update_portfolio_value(self, current_price: float):
        """更新组合价值"""
        position_value = self.current_position * current_price
        self.total_value = self.current_cash + position_value
    
    def on_market_data(self, timestamp: datetime, price: float, volume: float = 0):
        """处理市场数据"""
        # 生成信号
        signal = self.generate_signal(timestamp, price, volume)
        
        # 执行交易
        if signal:
            self.execute_trade(timestamp, price, signal, volume)
        
        # 更新组合价值
        self.update_portfolio_value(price)
    
    def get_performance_metrics(self, initial_capital: float) -> Dict:
        """计算策略性能指标"""
        if not self.trades:
            return {
                'totalReturn': 0.0,
                'annualizedReturn': 0.0,
                'totalTrades': 0,
                'winRate': 0.0,
                'sharpeRatio': 0.0,
                'maxDrawdown': 0.0,
                'finalCapital': self.total_value,
                'signalCount': self.signal_count,
                'profitableTrades': 0
            }
        
        # 基础指标
        total_return = (self.total_value - initial_capital) / initial_capital
        total_trades = len(self.trades)
        
        # 计算盈利交易
        profitable_trades = 0
        trade_returns = []
        
        for i, trade in enumerate(self.trades):
            if trade.action == 'sell' and i > 0:
                # 找到对应的买入交易
                buy_trade = None
                for j in range(i-1, -1, -1):
                    if self.trades[j].action == 'buy':
                        buy_trade = self.trades[j]
                        break
                
                if buy_trade:
                    trade_return = (trade.price - buy_trade.price) / buy_trade.price
                    trade_returns.append(trade_return)
                    if trade_return > 0:
                        profitable_trades += 1
        
        win_rate = profitable_trades / len(trade_returns) if trade_returns else 0.0
        
        # 年化收益率 (假设250个交易日)
        days = len(self.price_history)
        years = days / 250.0 if days > 0 else 1.0
        annualized_return = (1 + total_return) ** (1/years) - 1 if years > 0 else 0.0
        
        # 夏普比率 (简化计算)
        if trade_returns:
            avg_return = np.mean(trade_returns)
            return_std = np.std(trade_returns)
            sharpe_ratio = avg_return / return_std if return_std > 0 else 0.0
        else:
            sharpe_ratio = 0.0
        
        # 最大回撤 (简化计算)
        portfolio_values = [initial_capital]
        cash = initial_capital
        position = 0
        
        for i, (price, trade) in enumerate(zip(self.price_history, self.trades + [None])):
            if trade and trade.action == 'buy':
                cash = trade.balance
                position = trade.position
            elif trade and trade.action == 'sell':
                cash = trade.balance
                position = trade.position
            
            current_value = cash + position * price
            portfolio_values.append(current_value)
        
        peak = portfolio_values[0]
        max_drawdown = 0.0
        
        for value in portfolio_values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            max_drawdown = max(max_drawdown, drawdown)
        
        return {
            'totalReturn': total_return,
            'annualizedReturn': annualized_return,
            'totalTrades': total_trades,
            'winRate': win_rate,
            'sharpeRatio': sharpe_ratio,
            'maxDrawdown': max_drawdown,
            'finalCapital': self.total_value,
            'signalCount': self.signal_count,
            'profitableTrades': profitable_trades
        }
    
    def get_current_status(self) -> Dict:
        """获取当前状态"""
        current_ma_short = self.ma_short_history[-1] if self.ma_short_history else np.nan
        current_ma_long = self.ma_long_history[-1] if self.ma_long_history else np.nan
        
        return {
            'cash': self.current_cash,
            'position': self.current_position,
            'totalValue': self.total_value,
            'lastSignal': self.last_signal,
            'maShort': current_ma_short,
            'maLong': current_ma_long,
            'isGoldenCross': current_ma_short > current_ma_long if not np.isnan(current_ma_short) and not np.isnan(current_ma_long) else False
        }
