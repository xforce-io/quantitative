#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
均值回归策略
Mean Reversion Strategy

基于回归曲线偏离度进行买卖的策略
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import numpy as np
import pandas as pd
from scipy import stats

from .base_strategy import BaseStrategy, MarketState, TradingDecision
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


class MeanReversionStrategy(BaseStrategy):
    """
    均值回归策略
    
    策略逻辑：
    - 计算价格的回归曲线（线性/多项式）
    - 当价格低于回归曲线一定标准差时买入
    - 当价格高于回归曲线一定标准差时卖出
    
    参数:
    - threshold: 买卖阈值（标准差倍数，默认1.0）
    - regression_type: 回归类型 ('linear', 'polynomial')
    - degree: 多项式阶数（默认2）
    - lookback: 计算回归的回望期（默认120天）
    """
    
    def __init__(self, symbol: str, config: Optional[Dict] = None):
        super().__init__(symbol, config)
        
        # 策略参数
        self.threshold = self.config.get('threshold', 1.0)
        self.regression_type = self.config.get('regression_type', 'polynomial')
        self.degree = self.config.get('degree', 2)
        self.lookback = self.config.get('lookback', 120)
        
        # 状态变量
        self.cash = 0.0
        self.position = 0.0
        self.trades: List[Dict] = []
        self.price_history: List[float] = []
        self.date_history: List[datetime] = []
        
        # 回归模型参数
        self._regression_params = None
        self._deviation_std = None
        
    def reset(self, initial_capital: float = 100000.0):
        """重置策略状态"""
        self.cash = initial_capital
        self.position = 0.0
        self.trades = []
        self.price_history = []
        self.date_history = []
        self._regression_params = None
        self._deviation_std = None
        
    def makeDecision(self, market_state: MarketState) -> TradingDecision:
        """
        根据市场状态做出交易决策
        
        Args:
            market_state: 市场状态
            
        Returns:
            TradingDecision: 交易决策
        """
        current_price = market_state.close
        timestamp = market_state.timestamp
        
        # 记录价格历史
        self.price_history.append(current_price)
        self.date_history.append(timestamp)
        
        # 数据不足时持有
        if len(self.price_history) < self.lookback:
            return TradingDecision(
                action='hold',
                amount=0,
                reason=f'数据积累中 ({len(self.price_history)}/{self.lookback})'
            )
        
        # 计算回归和偏离度
        deviation, fitted_price = self._calculate_deviation()
        
        if deviation is None:
            return TradingDecision(
                action='hold',
                amount=0,
                reason='回归计算失败'
            )
        
        # 买入信号：偏离度 < -threshold * std
        if deviation < -self.threshold * self._deviation_std and self.position == 0:
            # 计算可买入股数
            shares = self.cash / current_price
            if shares > 0:
                self.position = shares
                self.cash = 0
                
                trade = {
                    'timestamp': timestamp,
                    'action': 'buy',
                    'price': current_price,
                    'shares': shares,
                    'deviation': deviation,
                    'fitted_price': fitted_price
                }
                self.trades.append(trade)
                
                return TradingDecision(
                    action='buy',
                    amount=shares,
                    reason=f'偏离度 {deviation:.2f}% < -{self.threshold}σ ({-self.threshold * self._deviation_std:.2f}%)',
                    metadata={'deviation': deviation, 'fitted_price': fitted_price}
                )
        
        # 卖出信号：偏离度 > threshold * std
        elif deviation > self.threshold * self._deviation_std and self.position > 0:
            shares = self.position
            self.cash = shares * current_price
            self.position = 0
            
            trade = {
                'timestamp': timestamp,
                'action': 'sell',
                'price': current_price,
                'shares': shares,
                'deviation': deviation,
                'fitted_price': fitted_price
            }
            self.trades.append(trade)
            
            return TradingDecision(
                action='sell',
                amount=shares,
                reason=f'偏离度 {deviation:.2f}% > +{self.threshold}σ ({self.threshold * self._deviation_std:.2f}%)',
                metadata={'deviation': deviation, 'fitted_price': fitted_price}
            )
        
        # 持有
        return TradingDecision(
            action='hold',
            amount=0,
            reason=f'偏离度 {deviation:.2f}% 在 ±{self.threshold}σ 范围内',
            metadata={'deviation': deviation, 'fitted_price': fitted_price}
        )
    
    def _calculate_deviation(self) -> tuple:
        """
        计算当前价格相对回归曲线的偏离度
        
        Returns:
            (deviation_pct, fitted_price) 或 (None, None) 如果计算失败
        """
        try:
            prices = np.array(self.price_history[-self.lookback:])
            x = np.arange(len(prices))
            
            if self.regression_type == 'linear':
                # 线性回归
                slope, intercept, _, _, _ = stats.linregress(x, prices)
                y_pred = slope * x + intercept
            else:
                # 多项式回归
                coeffs = np.polyfit(x, prices, self.degree)
                poly = np.poly1d(coeffs)
                y_pred = poly(x)
            
            # 计算偏离度
            deviations = (prices - y_pred) / y_pred * 100
            self._deviation_std = np.std(deviations)
            
            # 当前点的偏离度
            current_deviation = deviations[-1]
            fitted_price = y_pred[-1]
            
            return current_deviation, fitted_price
            
        except Exception as e:
            logger.warning(f"回归计算失败: {e}")
            return None, None
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        if not self.price_history:
            return {}
        
        # 计算胜率
        winning_trades = 0
        total_round_trips = 0
        buy_price = 0
        
        for trade in self.trades:
            if trade['action'] == 'buy':
                buy_price = trade['price']
            elif trade['action'] == 'sell' and buy_price > 0:
                total_round_trips += 1
                if trade['price'] > buy_price:
                    winning_trades += 1
                buy_price = 0
        
        win_rate = (winning_trades / total_round_trips * 100) if total_round_trips > 0 else 0
        
        return {
            'total_trades': len(self.trades),
            'round_trips': total_round_trips,
            'winning_trades': winning_trades,
            'win_rate': win_rate,
            'threshold': self.threshold,
            'regression_type': self.regression_type,
            'lookback': self.lookback
        }
    
    def get_strategy_name(self) -> str:
        return f"MeanReversion({self.regression_type}, ±{self.threshold}σ)"
    
    def get_strategy_params(self) -> Dict[str, Any]:
        return {
            'threshold': self.threshold,
            'regression_type': self.regression_type,
            'degree': self.degree,
            'lookback': self.lookback
        }
