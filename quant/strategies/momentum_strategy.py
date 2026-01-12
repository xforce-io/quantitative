#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Momentum Strategy
动量策略

基于价格动量和技术指标的趋势跟踪策略，符合统一BaseStrategy接口
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque
from datetime import datetime

# 导入基础策略类
try:
    from .base_strategy import BaseStrategy, MarketState, TradingDecision
except ImportError:
    # 回退到绝对导入
    from quant.strategies.base_strategy import BaseStrategy, MarketState, TradingDecision

from quant.core.logging_config import get_logger
logger = get_logger(__name__)


@dataclass
class MomentumTrade:
    """动量策略交易记录"""
    timestamp: datetime
    action: str  # 'buy', 'sell', 'hold'
    price: float
    quantity: int
    amount: float
    commission: float
    reason: str
    momentum_score: float
    rsi: float = 0.0
    macd: float = 0.0

class MomentumStrategy(BaseStrategy):
    """
    动量策略实现
    
    策略逻辑:
    1. 基于价格动量计算动量得分
    2. 结合RSI、MACD等技术指标
    3. 动量得分超过阈值时买入，低于阈值时卖出
    """
    
    def __init__(self, symbol: str, config: Dict = None):
        """
        初始化动量策略
        
        Args:
            symbol (str): 股票代码
            config (Dict): 策略配置参数
        """
        super().__init__(symbol, config)
        
        # 动量策略参数
        self.momentum_period = self.config.get('momentum_period', 20)  # 动量计算周期
        self.momentum_threshold = self.config.get('momentum_threshold', 0.05)  # 5%动量阈值
        self.rsi_period = self.config.get('rsi_period', 14)  # RSI周期
        self.rsi_oversold = self.config.get('rsi_oversold', 30)  # RSI超卖线
        self.rsi_overbought = self.config.get('rsi_overbought', 70)  # RSI超买线
        
        # MACD参数
        self.macd_fast = self.config.get('macd_fast', 12)
        self.macd_slow = self.config.get('macd_slow', 26)
        self.macd_signal = self.config.get('macd_signal', 9)
        
        # 交易参数
        self.commission = self.config.get('commission', 0.0003)
        self.slippage = self.config.get('slippage', 0.001)
        self.max_position = self.config.get('max_position', 100000)
        self.position_size = self.config.get('position_size', 0.8)  # 80%仓位
        
        # 风险控制
        self.stop_loss = self.config.get('stop_loss', 0.08)  # 8%止损
        self.take_profit = self.config.get('take_profit', 0.15)  # 15%止盈
        self.max_holding_days = self.config.get('max_holding_days', 30)  # 最大持仓天数
        
        # 日志配置
        self.verbose_logging = self.config.get('verbose_logging', True)
        self.compact_logging = self.config.get('compact_logging', False)
        
        # 策略状态
        self.reset()
        
        logger.info("Momentum strategy initialized for {self.symbol}")
        logger.info("  Momentum period: {self.momentum_period}, threshold: {self.momentum_threshold:.1%}")
        logger.info("  RSI: {self.rsi_period} period, {self.rsi_oversold}-{self.rsi_overbought}")
        logger.info("  MACD: {self.macd_fast}-{self.macd_slow}-{self.macd_signal}")
        logger.info("  Risk control: {self.stop_loss:.1%} stop loss, {self.take_profit:.1%} take profit")
    
    def reset(self, initial_capital: float = 100000.0):
        """重置策略状态"""
        self.initial_capital = initial_capital
        self.current_cash = initial_capital
        self.current_position = 0
        self.total_value = initial_capital
        self.trades: List[MomentumTrade] = []
        
        # 技术指标历史数据
        self.price_history = deque(maxlen=max(self.momentum_period, self.macd_slow) + 10)
        self.volume_history = deque(maxlen=50)
        self.returns_history = deque(maxlen=self.momentum_period + 5)
        
        # 技术指标缓存
        self.rsi_history = deque(maxlen=30)
        self.macd_history = deque(maxlen=30)
        self.macd_signal_history = deque(maxlen=30)
        self.momentum_scores = deque(maxlen=30)
        
        # 持仓跟踪
        self.entry_price = 0.0
        self.entry_date = None
        self.last_trade_date = None
        
        logger.info("Momentum strategy reset with initial capital: ¥{initial_capital:,.2f}")
    
    def makeDecision(self, market_state: MarketState) -> TradingDecision:
        """统一的决策接口"""
        current_price = market_state.currentPrice
        timestamp = market_state.timestamp
        volume = market_state.volume
        
        # 更新历史数据和技术指标
        self._update_indicators(current_price, volume)
        
        # 检查是否有足够的历史数据
        if len(self.price_history) < self.momentum_period:
            return TradingDecision(
                action='hold',
                amount=0,
                reason=f'Insufficient data: {len(self.price_history)}/{self.momentum_period}',
                confidence=0.0
            )
        
        # 计算当前技术指标
        momentum_score = self._calculate_momentum_score()
        rsi = self._calculate_rsi()
        macd, macd_signal = self._calculate_macd()
        
        # 更新指标历史
        self.momentum_scores.append(momentum_score)
        self.rsi_history.append(rsi)
        self.macd_history.append(macd)
        self.macd_signal_history.append(macd_signal)
        
        # 风险控制检查
        risk_decision = self._check_risk_controls(current_price, timestamp)
        if risk_decision:
            return risk_decision
        
        # 生成交易信号
        return self._generate_trading_signal(
            current_price, timestamp, momentum_score, rsi, macd, macd_signal
        )
    
    def _update_indicators(self, price: float, volume: float):
        """更新技术指标数据"""
        self.price_history.append(price)
        self.volume_history.append(volume)
        
        # 计算收益率
        if len(self.price_history) > 1:
            return_rate = (price - self.price_history[-2]) / self.price_history[-2]
            self.returns_history.append(return_rate)
    
    def _calculate_momentum_score(self) -> float:
        """计算动量得分"""
        if len(self.price_history) < self.momentum_period:
            return 0.0
        
        # 价格动量：当前价格相对于N日前的涨幅
        current_price = self.price_history[-1]
        past_price = self.price_history[-self.momentum_period]
        price_momentum = (current_price - past_price) / past_price
        
        # 成交量动量（如果有成交量数据）
        volume_momentum = 0.0
        if (len(self.volume_history) >= self.momentum_period and 
            self.volume_history[-1] is not None and 
            not np.isnan(self.volume_history[-1]) and 
            self.volume_history[-1] > 0):
            current_volume = self.volume_history[-1]
            # 过滤掉NaN值
            valid_volumes = [v for v in list(self.volume_history)[-self.momentum_period:] 
                           if v is not None and not np.isnan(v)]
            if valid_volumes:
                avg_volume = np.mean(valid_volumes)
                volume_momentum = (current_volume - avg_volume) / avg_volume if avg_volume > 0 else 0
        
        # 收益率动量：最近收益率的趋势
        returns_momentum = 0.0
        if len(self.returns_history) >= 5:
            recent_returns = list(self.returns_history)[-5:]
            returns_momentum = np.mean(recent_returns)
        
        # 综合动量得分（加权平均）
        momentum_score = (
            price_momentum * 0.6 +  # 价格动量权重60%
            volume_momentum * 0.2 + # 成交量动量权重20%
            returns_momentum * 0.2  # 收益率动量权重20%
        )
        
        return momentum_score
    
    def _calculate_rsi(self) -> float:
        """计算RSI指标"""
        if len(self.returns_history) < self.rsi_period:
            return 50.0  # 默认中性值
        
        returns = list(self.returns_history)[-self.rsi_period:]
        gains = [r for r in returns if r > 0]
        losses = [-r for r in returns if r < 0]
        
        if not gains or not losses:
            return 50.0
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_macd(self) -> Tuple[float, float]:
        """计算MACD指标"""
        if len(self.price_history) < self.macd_slow:
            return 0.0, 0.0
        
        prices = list(self.price_history)
        
        # 计算EMA
        def calculate_ema(data, period):
            alpha = 2.0 / (period + 1)
            ema = data[0]
            for price in data[1:]:
                ema = alpha * price + (1 - alpha) * ema
            return ema
        
        # 快线和慢线EMA
        ema_fast = calculate_ema(prices[-self.macd_fast:], self.macd_fast)
        ema_slow = calculate_ema(prices[-self.macd_slow:], self.macd_slow)
        
        # MACD线
        macd = ema_fast - ema_slow
        
        # 信号线（MACD的EMA）
        if len(self.macd_history) >= self.macd_signal:
            macd_values = list(self.macd_history)[-self.macd_signal:] + [macd]
            macd_signal = calculate_ema(macd_values, self.macd_signal)
        else:
            macd_signal = macd
        
        return macd, macd_signal
    
    def _check_risk_controls(self, current_price: float, timestamp: datetime) -> Optional[TradingDecision]:
        """检查风险控制条件"""
        if self.current_position <= 0:
            return None
        
        # 止损检查
        if self.entry_price > 0:
            loss_ratio = (self.entry_price - current_price) / self.entry_price
            if loss_ratio > self.stop_loss:
                return TradingDecision(
                    action='sell',
                    amount=self.current_position,
                    reason=f'Stop loss triggered: {loss_ratio:.1%} loss',
                    confidence=0.9
                )
        
        # 止盈检查
        if self.entry_price > 0:
            profit_ratio = (current_price - self.entry_price) / self.entry_price
            if profit_ratio > self.take_profit:
                return TradingDecision(
                    action='sell',
                    amount=self.current_position,
                    reason=f'Take profit triggered: {profit_ratio:.1%} profit',
                    confidence=0.8
                )
        
        # 最大持仓天数检查
        if self.entry_date and self.max_holding_days > 0:
            holding_days = (timestamp - self.entry_date).days
            if holding_days > self.max_holding_days:
                return TradingDecision(
                    action='sell',
                    amount=self.current_position,
                    reason=f'Max holding period: {holding_days} days',
                    confidence=0.7
                )
        
        return None
    
    def _generate_trading_signal(self, current_price: float, timestamp: datetime,
                               momentum_score: float, rsi: float, macd: float, macd_signal: float) -> TradingDecision:
        """生成交易信号"""
        
        # 买入信号条件
        buy_conditions = [
            momentum_score > self.momentum_threshold,  # 动量超过阈值
            rsi < self.rsi_overbought,  # RSI未超买
            macd > macd_signal,  # MACD金叉
            self.current_position == 0  # 当前无仓位
        ]
        
        # 卖出信号条件
        sell_conditions = [
            momentum_score < -self.momentum_threshold,  # 负动量
            rsi > self.rsi_overbought,  # RSI超买
            macd < macd_signal,  # MACD死叉
            self.current_position > 0  # 当前有仓位
        ]
        
        # 计算信号强度
        buy_strength = sum(buy_conditions[:-1]) / 3  # 排除仓位条件
        sell_strength = sum(sell_conditions[:-1]) / 3
        
        # 生成买入信号
        if all(buy_conditions) and buy_strength >= 0.67:  # 至少2/3条件满足
            trade_amount = self.current_cash * self.position_size
            
            # 根据标的类型调整最小股数
            if self.symbol in ['IXIC', 'SPX', 'DJI', 'NDX', 'NASDAQ', 'HKTECH', 'HSI', 'HSCEI'] or self.symbol.startswith('^'):
                # 指数：直接买入不要求整数倍
                shares = int(trade_amount / current_price)
                min_shares = 1
            else:
                # 股票：100股整数倍
                shares = int(trade_amount / current_price / 100) * 100
                min_shares = 100
            
            shares = max(shares, min_shares)  # 确保达到最小股数
            actual_amount = shares * current_price * (1 + self.commission + self.slippage)
            
            if actual_amount <= self.current_cash:
                return TradingDecision(
                    action='buy',
                    amount=shares,
                    reason=f'Momentum buy: score={momentum_score:.1%}, RSI={rsi:.1f}, MACD={macd:.3f}',
                    confidence=buy_strength,
                    metadata={
                        'momentum_score': momentum_score,
                        'rsi': rsi,
                        'macd': macd,
                        'macd_signal': macd_signal
                    }
                )
        
        # 生成卖出信号
        if any(sell_conditions[:3]) and self.current_position > 0:  # 技术条件满足且有仓位
            return TradingDecision(
                action='sell',
                amount=self.current_position,
                reason=f'Momentum sell: score={momentum_score:.1%}, RSI={rsi:.1f}, MACD={macd:.3f}',
                confidence=sell_strength,
                metadata={
                    'momentum_score': momentum_score,
                    'rsi': rsi,
                    'macd': macd,
                    'macd_signal': macd_signal
                }
            )
        
        # 默认持有
        return TradingDecision(
            action='hold',
            amount=0,
            reason=f'Hold: momentum={momentum_score:.1%}, RSI={rsi:.1f}, conditions not met',
            confidence=0.5,
            metadata={
                'momentum_score': momentum_score,
                'rsi': rsi,
                'macd': macd,
                'macd_signal': macd_signal
            }
        )
    
    def execute_decision(self, decision: TradingDecision, market_state: MarketState):
        """执行交易决策（可选的辅助方法）"""
        if decision.action == 'buy':
            self._execute_buy(decision, market_state)
        elif decision.action == 'sell':
            self._execute_sell(decision, market_state)
        
        # 更新总价值
        self.total_value = self.current_cash + self.current_position * market_state.currentPrice
    
    def _execute_buy(self, decision: TradingDecision, market_state: MarketState):
        """执行买入"""
        shares = int(decision.amount)
        actual_price = market_state.currentPrice * (1 + self.slippage)
        trade_amount = shares * actual_price
        commission = trade_amount * self.commission
        total_cost = trade_amount + commission
        
        if total_cost <= self.current_cash:
            self.current_cash -= total_cost
            self.current_position += shares
            self.entry_price = actual_price
            self.entry_date = market_state.timestamp
            self.last_trade_date = market_state.timestamp
            
            # 记录交易
            trade = MomentumTrade(
                timestamp=market_state.timestamp,
                action='buy',
                price=actual_price,
                quantity=shares,
                amount=trade_amount,
                commission=commission,
                reason=decision.reason,
                momentum_score=decision.metadata.get('momentum_score', 0),
                rsi=decision.metadata.get('rsi', 0),
                macd=decision.metadata.get('macd', 0)
            )
            self.trades.append(trade)
            
            if self.compact_logging:
                logger.info("📈 买入 {shares}股@¥{actual_price:.2f} 动量{decision.metadata.get('momentum_score', 0):.1%}")
            elif self.verbose_logging:
                logger.info("[{market_state.timestamp.strftime('%Y-%m-%d')}] Momentum BUY: {shares} shares at ¥{actual_price:.2f}")
                logger.info("  Reason: {decision.reason}")
                logger.info("  Cash: ¥{self.current_cash:,.0f}, Position: {self.current_position}, Total: ¥{self.total_value:,.0f}")
    
    def _execute_sell(self, decision: TradingDecision, market_state: MarketState):
        """执行卖出"""
        shares = min(int(decision.amount), self.current_position)
        actual_price = market_state.currentPrice * (1 - self.slippage)
        trade_amount = shares * actual_price
        commission = trade_amount * self.commission
        net_proceeds = trade_amount - commission
        
        # 计算盈亏
        pnl = 0.0
        if self.entry_price > 0:
            pnl = (actual_price - self.entry_price) * shares - commission
        
        self.current_cash += net_proceeds
        self.current_position -= shares
        
        if self.current_position == 0:
            self.entry_price = 0.0
            self.entry_date = None
        
        self.last_trade_date = market_state.timestamp
        
        # 记录交易
        trade = MomentumTrade(
            timestamp=market_state.timestamp,
            action='sell',
            price=actual_price,
            quantity=shares,
            amount=trade_amount,
            commission=commission,
            reason=decision.reason,
            momentum_score=decision.metadata.get('momentum_score', 0),
            rsi=decision.metadata.get('rsi', 0),
            macd=decision.metadata.get('macd', 0)
        )
        self.trades.append(trade)
        
        if self.compact_logging:
            logger.info("📉 卖出 {shares}股@¥{actual_price:.2f} 盈亏¥{pnl:+.0f} 动量{decision.metadata.get('momentum_score', 0):.1%}")
        elif self.verbose_logging:
            logger.info("[{market_state.timestamp.strftime('%Y-%m-%d')}] Momentum SELL: {shares} shares at ¥{actual_price:.2f}")
            logger.info("  Reason: {decision.reason}")
            logger.info("  P&L: ¥{pnl:+.2f}, Cash: ¥{self.current_cash:,.0f}, Total: ¥{self.total_value:,.0f}")
    
    def get_performance_metrics(self) -> Dict:
        """获取性能指标"""
        if not self.trades:
            return {
                'totalReturn': 0.0,
                'annualizedReturn': 0.0,
                'sharpeRatio': 0.0,
                'maxDrawdown': 0.0,
                'totalTrades': 0,
                'winRate': 0.0,
                'avgMomentumScore': 0.0,
                'currentPosition': self.current_position,
                'currentCash': self.current_cash,
                'totalValue': self.total_value
            }
        
        # 基础指标
        total_return = (self.total_value - self.initial_capital) / self.initial_capital
        total_trades = len([t for t in self.trades if t.action in ['buy', 'sell']])
        
        # 计算交易对盈亏
        trade_pairs = []
        buy_trades = []
        
        for trade in self.trades:
            if trade.action == 'buy':
                buy_trades.append(trade)
            elif trade.action == 'sell' and buy_trades:
                # 匹配最近的买入交易
                buy_trade = buy_trades.pop(0)  # FIFO
                pnl = (trade.price - buy_trade.price) * trade.quantity - trade.commission - buy_trade.commission
                trade_return = pnl / (buy_trade.price * buy_trade.quantity)
                trade_pairs.append({
                    'pnl': pnl,
                    'return': trade_return,
                    'holding_days': (trade.timestamp - buy_trade.timestamp).days
                })
        
        # 胜率和平均收益
        if trade_pairs:
            winning_trades = [tp for tp in trade_pairs if tp['pnl'] > 0]
            win_rate = len(winning_trades) / len(trade_pairs)
            avg_return = np.mean([tp['return'] for tp in trade_pairs])
            avg_holding_days = np.mean([tp['holding_days'] for tp in trade_pairs])
        else:
            win_rate = 0.0
            avg_return = 0.0
            avg_holding_days = 0.0
        
        # 年化收益率
        if hasattr(self, 'trades') and self.trades:
            days = (self.trades[-1].timestamp - self.trades[0].timestamp).days
            years = max(days / 365.0, 1/365.0)  # 最少1天
            annualized_return = (1 + total_return) ** (1/years) - 1
        else:
            annualized_return = 0.0
        
        # 夏普比率（简化）
        if trade_pairs:
            returns = [tp['return'] for tp in trade_pairs]
            sharpe_ratio = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0.0
        else:
            sharpe_ratio = 0.0
        
        # 最大回撤（简化）
        portfolio_values = [self.initial_capital]
        running_cash = self.initial_capital
        running_position = 0
        
        for trade in self.trades:
            if trade.action == 'buy':
                running_cash -= trade.amount + trade.commission
                running_position += trade.quantity
            elif trade.action == 'sell':
                running_cash += trade.amount - trade.commission
                running_position -= trade.quantity
            
            # 假设当前价格为最后交易价格
            current_value = running_cash + running_position * trade.price
            portfolio_values.append(current_value)
        
        peak = portfolio_values[0]
        max_drawdown = 0.0
        for value in portfolio_values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            max_drawdown = max(max_drawdown, drawdown)
        
        # 平均动量得分
        avg_momentum_score = np.mean([t.momentum_score for t in self.trades if hasattr(t, 'momentum_score')]) if self.trades else 0.0
        
        return {
            'totalReturn': total_return,
            'annualizedReturn': annualized_return,
            'sharpeRatio': sharpe_ratio,
            'maxDrawdown': max_drawdown,
            'totalTrades': total_trades,
            'winRate': win_rate,
            'avgReturn': avg_return,
            'avgHoldingDays': avg_holding_days,
            'avgMomentumScore': avg_momentum_score,
            'profitableTrades': len([tp for tp in trade_pairs if tp['pnl'] > 0]),
            'currentPosition': self.current_position,
            'currentCash': self.current_cash,
            'totalValue': self.total_value,
            'strategySpecific': {
                'momentum_threshold': self.momentum_threshold,
                'rsi_signals': len([t for t in self.trades if 'RSI' in t.reason]),
                'macd_signals': len([t for t in self.trades if 'MACD' in t.reason])
            }
        }
    
    def get_current_indicators(self) -> Dict:
        """获取当前技术指标状态"""
        return {
            'momentum_score': self.momentum_scores[-1] if self.momentum_scores else 0.0,
            'rsi': self.rsi_history[-1] if self.rsi_history else 50.0,
            'macd': self.macd_history[-1] if self.macd_history else 0.0,
            'macd_signal': self.macd_signal_history[-1] if self.macd_signal_history else 0.0,
            'entry_price': self.entry_price,
            'entry_date': self.entry_date,
            'days_held': (datetime.now() - self.entry_date).days if self.entry_date else 0
        }
