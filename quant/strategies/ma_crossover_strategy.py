#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Moving Average Crossover Strategy
均线交叉策略

实现基于移动平均线交叉的趋势跟踪策略，符合统一BaseStrategy接口
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque

# 导入基础策略类
try:
    from .base_strategy import BaseStrategy, MarketState, TradingDecision
except ImportError:
    # 回退到绝对导入
    from quant.strategies.base_strategy import BaseStrategy, MarketState, TradingDecision

from quant.core.logging_config import get_logger
logger = get_logger(__name__)


@dataclass
class MACrossoverTrade:
    """均线交叉策略交易记录"""
    timestamp: datetime
    action: str  # 'buy', 'sell', 'hold'
    price: float
    shares: int
    amount: float
    commission: float
    balance: float
    position: int
    signal_type: str  # 'golden_cross', 'death_cross', 'hold'
    ma_short: float
    ma_long: float


class MACrossoverStrategy(BaseStrategy):
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
        super().__init__(symbol, config)
        
        # 策略参数
        self.ma_short = self.config.get('ma_short', 5)  # 短期均线周期
        self.ma_long = self.config.get('ma_long', 10)   # 长期均线周期
        self.commission = self.config.get('commission', 0.0003)  # 手续费率
        self.slippage = self.config.get('slippage', 0.001)       # 滑点率
        
        # 根据标的类型调整最小交易股数
        if symbol in ['IXIC', 'SPX', 'DJI', 'NDX', 'NASDAQ', 'HKTECH', 'HSI', 'HSCEI'] or symbol.startswith('^'):
            # 对于高价指数，使用更小的最小交易单位
            self.min_shares = self.config.get('min_shares', 1)   # 指数最少1股
        else:
            # 对于股票，保持100股的整数倍要求
            self.min_shares = self.config.get('min_shares', 100) # 股票最少100股
            
        self.position_size = self.config.get('position_size', 1.0)  # 仓位大小(0-1)
        
        # 放宽过滤条件，提高信号捕获率
        self.min_volume_ratio = self.config.get('min_volume_ratio', 0.5)  # 降低成交量要求
        self.min_price_change = self.config.get('min_price_change', 0.001)  # 降低价格变化要求
        self.volume_ma_period = self.config.get('volume_ma_period', 20)  # 成交量均线周期
        self.volume_surge_threshold = self.config.get('volume_surge_threshold', 1.1)  # 降低放量阈值
        self.price_volume_correlation = self.config.get('price_volume_correlation', False)  # 关闭价量配合检查
        
        # 日志配置
        self.verbose_logging = self.config.get('verbose_logging', True)
        self.compact_logging = self.config.get('compact_logging', False)
        
        # 状态变量
        self.reset()
        
        logger.info("MA Crossover strategy initialized for {self.symbol}")
        logger.info("  MA periods: {self.ma_short}/{self.ma_long}, position size: {self.position_size:.1%}")
        logger.info("  Commission: {self.commission:.2%}, slippage: {self.slippage:.2%}")
        logger.info("  Volume filters: ratio≥{self.min_volume_ratio:.1f}x, surge≥{self.volume_surge_threshold:.1f}x, correlation={self.price_volume_correlation}")
    
    @property
    def cash(self) -> float:
        """Engine-facing alias for available cash (makeDecision contract)."""
        return self.current_cash

    @property
    def position(self) -> int:
        """Engine-facing alias for held position (makeDecision contract)."""
        return self.current_position

    def makeDecision(self, market_state: MarketState) -> TradingDecision:
        """Unified decision interface.

        The backtest engines never apply the returned decision themselves; they
        read ``cash``/``position`` after each bar. So makeDecision must execute
        the trade against the internal ledger here, reusing the tested
        signal/execution path, and report what actually happened.
        """
        current_price = market_state.currentPrice
        timestamp = market_state.timestamp
        volume = market_state.volume

        position_before = self.current_position
        signal = self.generate_signal(timestamp, current_price, volume)
        if signal:
            self.execute_trade(timestamp, current_price, signal, volume)
        self.update_portfolio_value(current_price)

        ma_short = self.ma_short_history[-1] if self.ma_short_history else 0
        ma_long = self.ma_long_history[-1] if self.ma_long_history else 0
        if self.current_position > position_before:
            return TradingDecision(
                action='buy',
                amount=self.current_position - position_before,
                reason=f'Golden cross: MA{self.ma_short}({ma_short:.2f}) > MA{self.ma_long}({ma_long:.2f})',
                confidence=0.8,
                metadata={'signal_type': 'golden_cross', 'ma_short': ma_short, 'ma_long': ma_long},
            )
        if self.current_position < position_before:
            return TradingDecision(
                action='sell',
                amount=position_before - self.current_position,
                reason=f'Death cross: MA{self.ma_short}({ma_short:.2f}) < MA{self.ma_long}({ma_long:.2f})',
                confidence=0.8,
                metadata={'signal_type': 'death_cross', 'ma_short': ma_short, 'ma_long': ma_long},
            )
        return TradingDecision(
            action='hold',
            amount=0,
            reason='No MA crossover signal or insufficient funds/position',
            confidence=0.5,
        )
    
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
        self.volume_ma_history = []  # 成交量均线历史
        
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
        
        # 计算成交量均线
        if len(self.volume_history) >= self.volume_ma_period:
            volume_ma = np.mean(self.volume_history[-self.volume_ma_period:])
            self.volume_ma_history.append(volume_ma)
        else:
            self.volume_ma_history.append(np.nan)
    
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
        """验证信号有效性 - 极度简化版本"""
        
        # 对于指数数据，volume可能为NaN，这是正常的
        if not (np.isnan(volume) or volume > 0):
            if self.verbose_logging:
                logger.info("  ❌ 信号被拒绝: 无效成交量 (volume={volume:.0f})")
            return False
        
        # 避免连续的同一信号
        if self.last_signal and self.last_signal == signal:
            if self.verbose_logging:
                logger.info("  ❌ 信号被拒绝: 重复信号 ({signal})")
            return False
        
        if self.verbose_logging:
            logger.info("  ✅ 信号通过验证: {signal.upper()} (volume={volume:.0f})")
        return True
    
    def _validate_volume_basic(self, volume: float) -> bool:
        """基础成交量验证"""
        if volume <= 0:
            return False
        
        # 需要足够的历史数据
        if len(self.volume_history) < self.volume_ma_period:
            return True  # 数据不足时放行
        
        # 与成交量均线比较
        if len(self.volume_ma_history) > 0:
            volume_ma = self.volume_ma_history[-1]
            if not np.isnan(volume_ma) and volume < volume_ma * self.min_volume_ratio:
                return False
        
        return True
    
    def _validate_volume_surge(self, volume: float, signal: str) -> bool:
        """成交量放量验证"""
        if len(self.volume_history) < 5:  # 需要足够历史数据
            return True
        
        # 计算近期成交量均值
        recent_volume_avg = np.mean(self.volume_history[-5:])
        
        # 买入信号需要适度放量
        if signal == 'buy':
            if volume < recent_volume_avg * 1.2:
                return False
            # 特别强的信号需要更大放量
            if volume > recent_volume_avg * self.volume_surge_threshold:
                return True
        
        # 卖出信号也需要成交量配合
        elif signal == 'sell':
            if volume < recent_volume_avg * 0.8:  # 卖出允许稍低的成交量
                return False
        
        return True
    
    def _validate_price_volume_correlation(self, price: float, volume: float, signal: str) -> bool:
        """价量配合验证"""
        if len(self.price_history) < 2 or len(self.volume_history) < 2:
            return True
        
        # 计算价格和成交量的变化
        price_change = (price - self.price_history[-1]) / self.price_history[-1]
        prev_volume = self.volume_history[-1]
        volume_change = (volume - prev_volume) / prev_volume if prev_volume > 0 else 0
        
        # 买入信号: 价格上涨伴随成交量放大
        if signal == 'buy':
            if price_change > 0.01 and volume_change > 0.2:  # 价涨量增
                return True
            elif price_change > 0 and volume_change > 0:  # 温和价涨量增
                return True
            elif abs(price_change) < 0.005:  # 价格变化很小时放宽要求
                return True
            else:
                return False
        
        # 卖出信号: 价格下跌时成交量放大，或价格上涨但成交量萎缩
        elif signal == 'sell':
            if price_change < -0.01 and volume_change > 0.2:  # 价跌量增
                return True
            elif price_change > 0.01 and volume_change < -0.2:  # 价涨量缩
                return True
            elif abs(price_change) < 0.005:  # 价格变化很小时放宽要求
                return True
            else:
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
        
        # 根据最小股数要求调整
        if self.min_shares > 1:
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
    
    def get_performance_metrics(self) -> Dict:
        """获取性能指标 - 符合BaseStrategy接口"""
        initial_capital = getattr(self, 'initial_capital', 100000)
        
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
                'profitableTrades': 0,
                'currentPosition': self.current_position,
                'currentCash': self.current_cash,
                'totalValue': self.total_value,
                'strategySpecific': {
                    'ma_short_period': self.ma_short,
                    'ma_long_period': self.ma_long,
                    'golden_crosses': len([t for t in self.trades if t.signal_type == 'golden_cross']),
                    'death_crosses': len([t for t in self.trades if t.signal_type == 'death_cross'])
                }
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
            'profitableTrades': profitable_trades,
            'currentPosition': self.current_position,
            'currentCash': self.current_cash,
            'totalValue': self.total_value,
            'strategySpecific': {
                'ma_short_period': self.ma_short,
                'ma_long_period': self.ma_long,
                'golden_crosses': len([t for t in self.trades if t.signal_type == 'golden_cross']),
                'death_crosses': len([t for t in self.trades if t.signal_type == 'death_cross']),
                'current_ma_short': self.ma_short_history[-1] if self.ma_short_history else 0,
                'current_ma_long': self.ma_long_history[-1] if self.ma_long_history else 0
            }
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
