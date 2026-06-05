#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Seykota-Style MA Crossover Strategy
塞柯塔风格的均线交叉策略

结合艾迪·塞柯塔的交易哲学：
1. 趋势跟踪为主
2. 快速止损，让利润奔跑
3. 成交量确认信号
4. 动态仓位管理
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
    from quant.strategies.base_strategy import BaseStrategy, MarketState, TradingDecision

from quant.core.logging_config import get_logger
logger = get_logger(__name__)


@dataclass
class SeyKotaTrade:
    """塞柯塔风格交易记录"""
    timestamp: datetime
    action: str
    price: float
    shares: int
    amount: float
    commission: float
    balance: float
    position: int
    signal_type: str
    stop_loss: float = 0.0
    volume_confirm: bool = False
    atr: float = 0.0
    risk_level: str = "normal"

class SeyKotaMAStrategy(BaseStrategy):
    """塞柯塔风格的MA交叉策略
    
    核心特征:
    1. ATR基础的动态止损
    2. 成交量确认信号
    3. 动态仓位管理
    4. 快速止损，让利润奔跑
    """
    
    def __init__(self, symbol: str, config: Optional[Dict] = None):
        """初始化策略"""
        super().__init__(symbol, config)
        
        # MA参数
        self.ma_short = self.config.get('ma_short', 5)
        self.ma_long = self.config.get('ma_long', 20)
        
        # 塞柯塔风格参数
        self.atr_period = self.config.get('atr_period', 14)  # ATR周期
        self.stop_loss_atr_multiplier = self.config.get('stop_atr_mult', 2.0)  # 止损ATR倍数
        self.position_risk = self.config.get('position_risk', 0.02)  # 单笔风险2%
        
        # 成交量参数
        self.volume_ma_period = self.config.get('volume_ma_period', 20)
        self.volume_threshold = self.config.get('volume_threshold', 1.2)  # 成交量放大倍数
        
        # 趋势强度参数
        self.trend_strength_period = self.config.get('trend_strength', 10)
        
        # 交易成本
        self.commission = self.config.get('commission', 0.0003)
        self.slippage = self.config.get('slippage', 0.001)
        
        # 状态变量
        self.reset()
        
        logger.info("🚀 SeyKota MA Strategy initialized for {self.symbol}")
        logger.info("   MA: {self.ma_short}/{self.ma_long} | ATR: {self.atr_period} | Risk: {self.position_risk:.1%}")
    
    @property
    def cash(self) -> float:
        """Engine-facing alias for available cash (makeDecision contract)."""
        return self.current_cash

    @property
    def position(self) -> int:
        """Engine-facing alias for held position (makeDecision contract)."""
        return self.current_position

    def makeDecision(self, market_state: MarketState) -> TradingDecision:
        """塞柯塔风格的决策制定.

        The backtest engines never apply the returned decision; they read
        ``cash``/``position`` after each bar. So makeDecision executes the trade
        against the internal ledger here before reporting it.
        """
        current_price = market_state.currentPrice
        timestamp = market_state.timestamp

        # 更新数据
        self._update_indicators(market_state)

        # 检查止损
        if self.current_position > 0 and self.current_stop_loss > 0:
            if current_price <= self.current_stop_loss:
                decision = TradingDecision(
                    action='sell',
                    amount=self.current_position,
                    reason=f'ATR止损触发: 价格{current_price:.2f} ≤ 止损{self.current_stop_loss:.2f}',
                    confidence=0.95,
                    metadata={'signal_type': 'stop_loss', 'stop_price': self.current_stop_loss}
                )
                self._execute_sell(timestamp, current_price, 'stop_loss')
                return decision

        # 生成交易信号
        signal_info = self._generate_seykota_signal(current_price, market_state.volume)

        if signal_info['signal'] == 'buy' and self.current_cash > 0 and self.current_position == 0:
            # 计算仓位大小（基于ATR的风险管理）
            shares = self._calculate_position_size(current_price, signal_info['atr'])

            if shares > 0 and self._execute_buy(timestamp, current_price, shares, signal_info):
                return TradingDecision(
                    action='buy',
                    amount=shares,
                    reason=signal_info['reason'],
                    confidence=signal_info['confidence'],
                    metadata={
                        'signal_type': 'seykota_buy',
                        'stop_loss': signal_info['stop_loss'],
                        'atr': signal_info['atr'],
                        'volume_confirm': signal_info['volume_confirm']
                    }
                )

        elif signal_info['signal'] == 'sell' and self.current_position > 0:
            decision = TradingDecision(
                action='sell',
                amount=self.current_position,
                reason=signal_info['reason'],
                confidence=signal_info['confidence'],
                metadata={
                    'signal_type': 'seykota_sell',
                    'trend_broken': True
                }
            )
            self._execute_sell(timestamp, current_price, 'seykota_sell',
                               volume_confirm=signal_info['volume_confirm'], atr=signal_info['atr'])
            return decision

        self.total_value = self.current_cash + self.current_position * current_price
        return TradingDecision(action='hold', amount=0, reason='无信号或条件不满足', confidence=0.5)

    def _execute_buy(self, timestamp, price: float, shares: int, signal_info: Dict) -> bool:
        """Execute a buy against the internal ledger; returns True if filled."""
        actual_price = price * (1 + self.slippage)
        commission = shares * actual_price * self.commission
        total_cost = shares * actual_price + commission
        if total_cost > self.current_cash:
            return False
        self.current_cash -= total_cost
        self.current_position += shares
        self.current_stop_loss = signal_info.get('stop_loss', 0.0)
        self.last_signal = 'buy'
        self.signal_count += 1
        self.total_value = self.current_cash + self.current_position * price
        self.trades.append(SeyKotaTrade(
            timestamp=timestamp, action='buy', price=actual_price, shares=shares,
            amount=shares * actual_price, commission=commission, balance=self.current_cash,
            position=self.current_position, signal_type=signal_info.get('signal_type', 'seykota_buy'),
            stop_loss=self.current_stop_loss, volume_confirm=signal_info.get('volume_confirm', False),
            atr=signal_info.get('atr', 0.0),
        ))
        return True

    def _execute_sell(self, timestamp, price: float, signal_type: str,
                      volume_confirm: bool = False, atr: float = 0.0) -> None:
        """Execute a full exit against the internal ledger."""
        shares = self.current_position
        if shares <= 0:
            return
        actual_price = price * (1 - self.slippage)
        commission = shares * actual_price * self.commission
        net_proceeds = shares * actual_price - commission
        self.current_cash += net_proceeds
        self.current_position = 0
        self.current_stop_loss = 0.0
        self.last_signal = 'sell'
        self.signal_count += 1
        self.total_value = self.current_cash
        self.trades.append(SeyKotaTrade(
            timestamp=timestamp, action='sell', price=actual_price, shares=shares,
            amount=shares * actual_price, commission=commission, balance=self.current_cash,
            position=0, signal_type=signal_type, stop_loss=0.0,
            volume_confirm=volume_confirm, atr=atr,
        ))
    
    def _update_indicators(self, market_state: MarketState):
        """更新技术指标"""
        self.high_history.append(market_state.high)
        self.low_history.append(market_state.low)
        self.close_history.append(market_state.close)
        self.volume_history.append(market_state.volume)
        
        # 计算MA
        if len(self.close_history) >= self.ma_short:
            ma_short = np.mean(self.close_history[-self.ma_short:])
            self.ma_short_history.append(ma_short)
        else:
            self.ma_short_history.append(np.nan)
            
        if len(self.close_history) >= self.ma_long:
            ma_long = np.mean(self.close_history[-self.ma_long:])
            self.ma_long_history.append(ma_long)
        else:
            self.ma_long_history.append(np.nan)
        
        # 计算ATR
        self._calculate_atr()
        
        # 计算成交量MA
        if len(self.volume_history) >= self.volume_ma_period:
            volume_ma = np.mean(self.volume_history[-self.volume_ma_period:])
            self.volume_ma_history.append(volume_ma)
        else:
            self.volume_ma_history.append(np.nan)
    
    def _calculate_atr(self):
        """计算Average True Range (ATR)"""
        if len(self.close_history) < 2:
            self.atr_history.append(np.nan)
            return

        high = self.high_history[-1]
        low = self.low_history[-1]
        prev_close = self.close_history[-2]
        
        true_range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        self.tr_history.append(true_range)
        
        if len(self.tr_history) >= self.atr_period:
            atr = np.mean(self.tr_history[-self.atr_period:])
            self.atr_history.append(atr)
        else:
            self.atr_history.append(np.nan)
    
    def _generate_seykota_signal(self, price: float, volume: float) -> Dict:
        """生成塞柯塔风格信号"""
        if len(self.ma_short_history) < 2 or len(self.ma_long_history) < 2:
            return {'signal': None, 'reason': '数据不足', 'confidence': 0}
        
        ma_short_curr = self.ma_short_history[-1]
        ma_long_curr = self.ma_long_history[-1]
        ma_short_prev = self.ma_short_history[-2]
        ma_long_prev = self.ma_long_history[-2]
        
        if np.isnan(ma_short_curr) or np.isnan(ma_long_curr):
            return {'signal': None, 'reason': 'MA无效', 'confidence': 0}
        
        current_atr = self.atr_history[-1] if self.atr_history else 0
        
        # 成交量确认
        volume_confirm = self._check_volume_confirmation(volume)
        
        # 趋势强度
        trend_strength = self._calculate_trend_strength()
        
        # 买入信号：金叉 + 成交量确认或趋势强度
        if (ma_short_prev <= ma_long_prev and ma_short_curr > ma_long_curr and
            (volume_confirm or trend_strength > 0.0)):
            
            stop_loss = price - (current_atr * self.stop_loss_atr_multiplier)
            confidence = 0.8 + (0.2 * trend_strength) if volume_confirm else 0.6
            
            return {
                'signal': 'buy',
                'reason': f'塞柯塔金叉: MA{self.ma_short}({ma_short_curr:.2f}) > MA{self.ma_long}({ma_long_curr:.2f}), '
                         f'成交量确认: {volume_confirm}, 趋势强度: {trend_strength:.2f}',
                'confidence': confidence,
                'stop_loss': stop_loss,
                'atr': current_atr,
                'volume_confirm': volume_confirm,
                'trend_strength': trend_strength
            }
        
        # 卖出信号：死叉或趋势减弱
        elif (ma_short_prev >= ma_long_prev and ma_short_curr < ma_long_curr) or trend_strength < -0.2:
            return {
                'signal': 'sell',
                'reason': f'塞柯塔死叉或趋势减弱: MA{self.ma_short}({ma_short_curr:.2f}) < MA{self.ma_long}({ma_long_curr:.2f}), '
                         f'趋势强度: {trend_strength:.2f}',
                'confidence': 0.8,
                'stop_loss': 0,
                'atr': current_atr,
                'volume_confirm': volume_confirm,
                'trend_strength': trend_strength
            }
        
        return {'signal': None, 'reason': '无明确信号', 'confidence': 0.5}
    
    def _check_volume_confirmation(self, current_volume: float) -> bool:
        """检查成交量确认"""
        # 对于指数数据，volume可能为NaN，这是正常的
        if (current_volume is None or np.isnan(current_volume) or 
            len(self.volume_ma_history) == 0 or np.isnan(self.volume_ma_history[-1])):
            return True  # 无成交量数据时默认确认
        
        volume_ma = self.volume_ma_history[-1]
        return current_volume >= (volume_ma * self.volume_threshold)
    
    def _calculate_trend_strength(self) -> float:
        """计算趋势强度 (-1到1之间)"""
        if len(self.close_history) < self.trend_strength_period:
            return 0
        
        prices = self.close_history[-self.trend_strength_period:]
        
        # 计算线性回归斜率作为趋势强度
        x = np.arange(len(prices))
        slope, _ = np.polyfit(x, prices, 1)
        
        # 标准化到-1到1之间
        price_range = max(prices) - min(prices)
        if price_range > 0:
            trend_strength = slope / (price_range / len(prices))
            return np.clip(trend_strength, -1, 1)
        
        return 0
    
    def _calculate_position_size(self, price: float, atr: float) -> int:
        """基于ATR的仓位大小计算（塞柯塔风险管理）"""
        if atr <= 0:
            return 0
        
        # 风险金额 = 总资产 * 风险比例
        total_capital = self.current_cash + (self.current_position * price)
        risk_amount = total_capital * self.position_risk
        
        # 止损距离 = ATR * 倍数
        stop_distance = atr * self.stop_loss_atr_multiplier
        
        # 仓位大小 = 风险金额 / 止损距离
        if stop_distance > 0:
            position_value = risk_amount / (stop_distance / price)
            shares = int(position_value / price)
            
            # 确保不超过可用资金
            max_shares = int(self.current_cash / (price * 1.01))  # 疙1%缓冲
            shares = min(shares, max_shares)
            
            # 根据标的类型调整最小股数
            if self.symbol in ['IXIC', 'SPX', 'DJI', 'NDX', 'NASDAQ', 'HKTECH', 'HSI', 'HSCEI'] or self.symbol.startswith('^'):
                # 指数：直接买入不要求整数倍，最少1股
                min_shares = 1
            else:
                # 股票：100股整数倍
                shares = (shares // 100) * 100
                min_shares = 100
            
            return max(shares, min_shares)
        
        return 0
    
    def reset(self, initial_capital: float = 100000.0):
        """重置策略状态"""
        self.initial_capital = initial_capital
        self.current_cash = initial_capital
        self.current_position = 0
        self.current_stop_loss = 0.0
        self.total_value = initial_capital
        self.trades: List[SeyKotaTrade] = []
        
        # 技术指标历史
        self.high_history = []
        self.low_history = []
        self.close_history = []
        self.volume_history = []
        self.ma_short_history = []
        self.ma_long_history = []
        self.tr_history = [] # True Range history
        self.atr_history = []
        self.volume_ma_history = []
        
        # 信号状态
        self.last_signal = None
        self.signal_count = 0
    
    def get_performance_metrics(self) -> Dict:
        """获取性能指标"""
        if not self.trades:
            return {
                'totalReturn': 0.0,
                'annualizedReturn': 0.0,
                'totalTrades': 0,
                'winRate': 0.0,
                'sharpeRatio': 0.0,
                'maxDrawdown': 0.0,
                'finalCapital': self.total_value,
                'strategySpecific': {
                    'stop_loss_triggers': 0,
                    'volume_confirmed_trades': 0,
                    'avg_holding_period': 0
                }
            }
        
        # 基础计算
        total_return = (self.total_value - self.initial_capital) / self.initial_capital
        total_trades = len([t for t in self.trades if t.action in ['buy', 'sell']])
        
        # 统计特殊信号
        stop_loss_triggers = len([t for t in self.trades if t.signal_type == 'stop_loss'])
        volume_confirmed = len([t for t in self.trades if t.volume_confirm])
        
        # 计算胜率
        profitable_trades = 0
        trade_pairs = []
        
        for i in range(len(self.trades) - 1):
            if self.trades[i].action == 'buy' and self.trades[i+1].action == 'sell':
                buy_price = self.trades[i].price
                sell_price = self.trades[i+1].price
                trade_return = (sell_price - buy_price) / buy_price
                trade_pairs.append(trade_return)
                if trade_return > 0:
                    profitable_trades += 1
        
        win_rate = profitable_trades / len(trade_pairs) if trade_pairs else 0
        
        # 年化收益率
        days = len(self.close_history)
        years = days / 250.0 if days > 0 else 1.0
        annualized_return = (1 + total_return) ** (1/years) - 1 if years > 0 else 0
        
        # 夏普比率
        if trade_pairs:
            avg_return = np.mean(trade_pairs)
            return_std = np.std(trade_pairs)
            sharpe_ratio = avg_return / return_std if return_std > 0 else 0
        else:
            sharpe_ratio = 0
        
        return {
            'totalReturn': total_return,
            'annualizedReturn': annualized_return,
            'totalTrades': total_trades,
            'winRate': win_rate,
            'sharpeRatio': sharpe_ratio,
            'maxDrawdown': self._calculate_max_drawdown(),
            'finalCapital': self.total_value,
            'strategySpecific': {
                'stop_loss_triggers': stop_loss_triggers,
                'volume_confirmed_trades': volume_confirmed,
                'avg_atr': np.mean([t.atr for t in self.trades if t.atr > 0]) if self.trades else 0,
                'risk_adjusted_trades': len([t for t in self.trades if t.risk_level == 'low'])
            }
        }
    
    def _calculate_max_drawdown(self) -> float:
        """计算最大回撤"""
        if not self.close_history:
            return 0.0
        
        # 如果没有交易，假设持有不动
        if not self.trades:
            # 计算简单的价格回撤
            prices = np.array(self.close_history)
            peak = np.maximum.accumulate(prices)
            drawdown = (peak - prices) / peak
            return np.max(drawdown)
        
        # 有交易时，计算账户价值回撤
        portfolio_values = []
        cash = self.initial_capital
        position = 0
        
        price_index = 0
        trade_index = 0
        
        for price in self.close_history:
            # 检查是否有交易
            while trade_index < len(self.trades) and price_index >= 0:
                trade = self.trades[trade_index]
                if trade.action == 'buy':
                    cash -= trade.amount
                    position += trade.shares
                elif trade.action == 'sell':
                    cash += trade.amount
                    position = 0
                trade_index += 1
                
            # 计算当前总价值
            total_value = cash + position * price
            portfolio_values.append(total_value)
            price_index += 1
        
        # 计算最大回撤
        portfolio_values = np.array(portfolio_values)
        peak = np.maximum.accumulate(portfolio_values)
        drawdown = (peak - portfolio_values) / peak
        return np.max(drawdown)
