"""
Strategy Agent System for Trading Optimization
策略代理系统 - 用于交易策略优化
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np
import logging
from ..environments.trading_environment import TradingEnvironment, EnvironmentState

@dataclass
class AgentConfig:
    """代理配置"""
    strategyType: str
    parameters: Dict[str, Any]
    riskProfile: str  # conservative, moderate, aggressive
    name: str
    description: str

class StrategyAgent(ABC):
    """策略代理基类"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{config.name}")
        self.performance_history = []
        
    @abstractmethod
    def decide(self, state: EnvironmentState) -> Dict[str, Any]:
        """根据当前状态决定动作"""
        pass
    
    @abstractmethod
    def getName(self) -> str:
        """获取策略名称"""
        pass
    
    def getDescription(self) -> str:
        """获取策略描述"""
        return self.config.description
    
    def updatePerformance(self, metrics: Dict[str, Any]):
        """更新性能指标"""
        self.performance_history.append(metrics)

class GridTradingAgent(StrategyAgent):
    """网格交易代理"""
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        
        # Extract grid parameters
        params = config.parameters
        self.gridLevels = params.get('gridLevels', 10)
        self.gridSpacing = params.get('gridSpacing', 0.02)
        self.maxPosition = params.get('maxPosition', 100000)
        self.baseRatio = params.get('baseRatio', 0.3)
        self.commission = params.get('commission', 0.0003)
        
        # Initialize grid state
        self.gridPrices = []
        self.gridInitialized = False
        self.basePositionEstablished = False
        self.lastPrice = None
        
    def getName(self) -> str:
        return f"GridTrading_L{self.gridLevels}_S{self.gridSpacing:.1%}_B{self.baseRatio:.1%}"
    
    def decide(self, state: EnvironmentState) -> Dict[str, Any]:
        """网格交易决策逻辑"""
        currentPrice = state.currentPrice
        
        # Initialize grid on first call
        if not self.gridInitialized:
            self._initializeGrid(currentPrice)
            self.gridInitialized = True
        
        # Establish base position if not done
        if not self.basePositionEstablished:
            baseAmount = self.maxPosition * self.baseRatio
            self.basePositionEstablished = True
            return {
                'type': 'buy',
                'amount': baseAmount,
                'reason': 'Establishing base position'
            }
        
        # Check for grid trading opportunities
        action = self._checkGridTriggers(currentPrice, state)
        self.lastPrice = currentPrice
        
        return action
    
    def _initializeGrid(self, centerPrice: float):
        """初始化网格价格"""
        self.gridPrices = []
        
        # Create buy levels (below current price)
        for i in range(1, self.gridLevels // 2 + 1):
            buyPrice = centerPrice * (1 - i * self.gridSpacing)
            self.gridPrices.append({
                'price': buyPrice,
                'type': 'buy',
                'triggered': False,
                'level': -i
            })
        
        # Create sell levels (above current price)
        for i in range(1, self.gridLevels // 2 + 1):
            sellPrice = centerPrice * (1 + i * self.gridSpacing)
            self.gridPrices.append({
                'price': sellPrice,
                'type': 'sell',
                'triggered': False,
                'level': i
            })
        
        # Sort by price
        self.gridPrices.sort(key=lambda x: x['price'])
        
        self.logger.info(f"Initialized grid with {len(self.gridPrices)} levels around {centerPrice:.2f}")
    
    def _checkGridTriggers(self, currentPrice: float, state: EnvironmentState) -> Dict[str, Any]:
        """检查网格触发条件"""
        # Check for triggered grid levels
        for grid in self.gridPrices:
            if grid['triggered']:
                continue
                
            if grid['type'] == 'buy' and currentPrice <= grid['price']:
                # Trigger buy order
                grid['triggered'] = True
                tradeAmount = self.maxPosition * (1 - self.baseRatio) / (self.gridLevels // 2)
                
                return {
                    'type': 'buy',
                    'amount': tradeAmount,
                    'reason': f"Grid buy triggered at level {grid['level']}"
                }
                
            elif grid['type'] == 'sell' and currentPrice >= grid['price']:
                # Trigger sell order (only if we have position)
                if state.position > 0:
                    grid['triggered'] = True
                    tradeAmount = self.maxPosition * (1 - self.baseRatio) / (self.gridLevels // 2)
                    
                    return {
                        'type': 'sell',
                        'amount': tradeAmount,
                        'reason': f"Grid sell triggered at level {grid['level']}"
                    }
        
        # Reset grid if price moves too far
        if self.lastPrice is not None:
            priceChange = abs(currentPrice - self.lastPrice) / self.lastPrice
            if priceChange > self.gridSpacing * 3:  # Reset if moved 3 grid levels
                self._resetGrid(currentPrice)
        
        return {'type': 'hold', 'amount': 0, 'reason': 'No grid triggers'}
    
    def _resetGrid(self, newCenterPrice: float):
        """重置网格"""
        self.logger.info(f"Resetting grid around new price {newCenterPrice:.2f}")
        self.gridInitialized = False
        self._initializeGrid(newCenterPrice)

class DCAAgent(StrategyAgent):
    """定投代理"""
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        
        params = config.parameters
        self.interval = params.get('interval', 'weekly')  # daily, weekly, monthly
        self.amount = params.get('amount', 1000)
        self.maxPosition = params.get('maxPosition', 100000)
        self.baseRatio = params.get('baseRatio', 0.5)
        
        # Track investment schedule
        self.lastInvestment = None
        self.investmentCount = 0
        self.intervalDays = {'daily': 1, 'weekly': 7, 'monthly': 30}[self.interval]
        
    def getName(self) -> str:
        return f"DCA_{self.interval}_{self.amount}_B{self.baseRatio:.1%}"
    
    def decide(self, state: EnvironmentState) -> Dict[str, Any]:
        """定投决策逻辑"""
        currentTime = state.timestamp
        
        # First investment or time for next investment
        if (self.lastInvestment is None or 
            (currentTime - self.lastInvestment).days >= self.intervalDays):
            
            # Check if we haven't exceeded max position
            if state.totalValue < self.maxPosition:
                self.lastInvestment = currentTime
                self.investmentCount += 1
                
                return {
                    'type': 'buy',
                    'amount': self.amount,
                    'reason': f"DCA investment #{self.investmentCount}"
                }
        
        return {'type': 'hold', 'amount': 0, 'reason': 'Waiting for next DCA interval'}

class MomentumAgent(StrategyAgent):
    """动量策略代理"""
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        
        params = config.parameters
        self.lookbackPeriod = params.get('lookbackPeriod', 20)
        self.threshold = params.get('threshold', 0.05)
        self.maxPosition = params.get('maxPosition', 100000)
        self.baseRatio = params.get('baseRatio', 0.2)
        
        self.priceHistory = []
        
    def getName(self) -> str:
        return f"Momentum_{self.lookbackPeriod}d_{self.threshold:.1%}_B{self.baseRatio:.1%}"
    
    def decide(self, state: EnvironmentState) -> Dict[str, Any]:
        """动量策略决策逻辑"""
        currentPrice = state.currentPrice
        self.priceHistory.append(currentPrice)
        
        # Keep only required history
        if len(self.priceHistory) > self.lookbackPeriod:
            self.priceHistory = self.priceHistory[-self.lookbackPeriod:]
        
        # Need enough history to calculate momentum
        if len(self.priceHistory) < self.lookbackPeriod:
            return {'type': 'hold', 'amount': 0, 'reason': 'Building price history'}
        
        # Calculate momentum (price change over lookback period)
        oldPrice = self.priceHistory[0]
        momentum = (currentPrice - oldPrice) / oldPrice
        
        # Momentum trading decisions
        tradeAmount = self.maxPosition * (1 - self.baseRatio) / 2  # Half for buy, half for sell
        
        if momentum > self.threshold:
            # Strong upward momentum - buy
            return {
                'type': 'buy',
                'amount': tradeAmount,
                'reason': f"Positive momentum: {momentum:.2%}"
            }
        elif momentum < -self.threshold:
            # Strong downward momentum - sell (if we have position)
            if state.position > 0:
                return {
                    'type': 'sell',
                    'amount': tradeAmount,
                    'reason': f"Negative momentum: {momentum:.2%}"
                }
        
        return {'type': 'hold', 'amount': 0, 'reason': f'Low momentum: {momentum:.2%}'}

class MeanReversionAgent(StrategyAgent):
    """均值回归策略代理"""
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        
        params = config.parameters
        self.period = params.get('period', 20)
        self.deviationThreshold = params.get('deviationThreshold', 2.0)  # Number of std devs
        self.maxPosition = params.get('maxPosition', 100000)
        self.baseRatio = params.get('baseRatio', 0.3)
        
    def getName(self) -> str:
        return f"MeanReversion_{self.period}d_{self.deviationThreshold:.1f}std_B{self.baseRatio:.1%}"
    
    def decide(self, state: EnvironmentState) -> Dict[str, Any]:
        """均值回归决策逻辑"""
        indicators = state.technicalIndicators
        currentPrice = state.currentPrice
        
        # Get Bollinger Bands from technical indicators
        bb_upper = indicators.get('BB_upper', 0)
        bb_lower = indicators.get('BB_lower', 0)
        bb_middle = indicators.get('SMA_20', currentPrice)  # Use SMA_20 as middle band
        
        if bb_upper == 0 or bb_lower == 0:
            return {'type': 'hold', 'amount': 0, 'reason': 'Insufficient data for Bollinger Bands'}
        
        tradeAmount = self.maxPosition * (1 - self.baseRatio) / 2
        
        # Mean reversion logic
        if currentPrice <= bb_lower:
            # Price below lower band - oversold, buy
            return {
                'type': 'buy',
                'amount': tradeAmount,
                'reason': f"Oversold - price {currentPrice:.2f} below lower band {bb_lower:.2f}"
            }
        elif currentPrice >= bb_upper and state.position > 0:
            # Price above upper band - overbought, sell
            return {
                'type': 'sell',
                'amount': tradeAmount,
                'reason': f"Overbought - price {currentPrice:.2f} above upper band {bb_upper:.2f}"
            }
        
        return {'type': 'hold', 'amount': 0, 'reason': 'Price within normal range'}

class TrendAwareGridAgent(StrategyAgent):
    """趋势感知网格交易代理 - 针对趋势市场优化的网格策略"""
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        
        # Extract parameters
        params = config.parameters
        self.gridLevels = params.get('gridLevels', 6)
        self.gridSpacing = params.get('gridSpacing', 0.08)
        self.maxPosition = params.get('maxPosition', 100000)
        self.baseRatio = params.get('baseRatio', 0.8)
        self.commission = params.get('commission', 0.0003)
        
        # Trend detection parameters
        self.trendPeriod = params.get('trendPeriod', 30)
        self.trendThreshold = params.get('trendThreshold', 0.10)
        self.stopLoss = params.get('stopLoss', 0.15)
        self.takeProfit = params.get('takeProfit', 0.30)
        
        # State tracking
        self.priceHistory = []
        self.gridPrices = []
        self.gridInitialized = False
        self.basePositionEstablished = False
        self.lastPrice = None
        self.currentTrend = 'neutral'
        self.avgCost = 0.0
        
    def getName(self) -> str:
        return f"TrendGrid_L{self.gridLevels}_S{self.gridSpacing:.0%}_B{self.baseRatio:.0%}_T{self.trendPeriod}"
    
    def decide(self, state: EnvironmentState) -> Dict[str, Any]:
        """趋势感知网格交易决策逻辑"""
        currentPrice = state.currentPrice
        
        # Update price history for trend detection
        self.priceHistory.append(currentPrice)
        if len(self.priceHistory) > self.trendPeriod:
            self.priceHistory = self.priceHistory[-self.trendPeriod:]
        
        # Detect current trend
        self.currentTrend = self._detectTrend()
        
        # Initialize grid on first call
        if not self.gridInitialized:
            self._initializeTrendAwareGrid(currentPrice)
            self.gridInitialized = True
        
        # Establish base position if not done
        if not self.basePositionEstablished:
            baseAmount = self.maxPosition * self.baseRatio
            self.basePositionEstablished = True
            self.avgCost = currentPrice
            return {
                'type': 'buy',
                'amount': baseAmount,
                'reason': f'Establishing base position ({self.baseRatio:.0%})'
            }
        
        # Check risk management first
        riskAction = self._checkRiskManagement(currentPrice, state)
        if riskAction['type'] != 'hold':
            return riskAction
        
        # Check for grid trading opportunities based on trend
        action = self._checkTrendAwareGridTriggers(currentPrice, state)
        self.lastPrice = currentPrice
        
        return action
    
    def _detectTrend(self) -> str:
        """检测市场趋势"""
        if len(self.priceHistory) < self.trendPeriod:
            return 'neutral'
        
        startPrice = self.priceHistory[0]
        endPrice = self.priceHistory[-1]
        totalReturn = (endPrice - startPrice) / startPrice
        
        # Calculate trend consistency
        upMoves = sum(1 for i in range(1, len(self.priceHistory)) 
                     if self.priceHistory[i] > self.priceHistory[i-1])
        downMoves = sum(1 for i in range(1, len(self.priceHistory)) 
                       if self.priceHistory[i] < self.priceHistory[i-1])
        
        if totalReturn > self.trendThreshold and upMoves > downMoves * 1.3:
            return 'bullish'
        elif totalReturn < -self.trendThreshold and downMoves > upMoves * 1.3:
            return 'bearish'
        else:
            return 'neutral'
    
    def _initializeTrendAwareGrid(self, centerPrice: float):
        """初始化趋势感知网格"""
        self.gridPrices = []
        
        # Adjust grid levels based on trend
        if self.currentTrend == 'bullish':
            # In uptrend: fewer buy grids, wider spacing for sells
            buyLevels = max(1, self.gridLevels // 3)
            sellLevels = max(1, self.gridLevels // 4)
            sellSpacing = self.gridSpacing * 2
            buySpacing = self.gridSpacing
        elif self.currentTrend == 'bearish':
            # In downtrend: more buy grids, fewer sell grids
            buyLevels = max(2, self.gridLevels // 2)
            sellLevels = max(1, self.gridLevels // 4)
            sellSpacing = self.gridSpacing
            buySpacing = self.gridSpacing * 0.7
        else:
            # Neutral: balanced approach
            buyLevels = self.gridLevels // 2
            sellLevels = self.gridLevels // 2
            sellSpacing = self.gridSpacing
            buySpacing = self.gridSpacing
        
        # Create buy levels
        for i in range(1, buyLevels + 1):
            buyPrice = centerPrice * (1 - i * buySpacing)
            self.gridPrices.append({
                'price': buyPrice,
                'type': 'buy',
                'triggered': False,
                'level': -i
            })
        
        # Create sell levels
        for i in range(1, sellLevels + 1):
            sellPrice = centerPrice * (1 + i * sellSpacing)
            self.gridPrices.append({
                'price': sellPrice,
                'type': 'sell',
                'triggered': False,
                'level': i
            })
        
        self.gridPrices.sort(key=lambda x: x['price'])
        
        self.logger.info(f"Initialized trend-aware grid ({self.currentTrend}) with {len(self.gridPrices)} levels")
    
    def _checkRiskManagement(self, currentPrice: float, state: EnvironmentState) -> Dict[str, Any]:
        """检查止损和止盈"""
        if self.avgCost <= 0 or state.position <= 0:
            return {'type': 'hold', 'amount': 0, 'reason': 'No position for risk management'}
        
        priceChange = (currentPrice - self.avgCost) / self.avgCost
        
        # Stop-loss
        if priceChange < -self.stopLoss:
            return {
                'type': 'sell',
                'amount': state.position * currentPrice,  # Sell all
                'reason': f'Stop-loss triggered: {priceChange:.2%} loss'
            }
        
        # Take-profit (partial)
        if priceChange > self.takeProfit and state.position > 200:
            sellAmount = state.position * currentPrice * 0.3  # Sell 30%
            return {
                'type': 'sell',
                'amount': sellAmount,
                'reason': f'Take-profit triggered: {priceChange:.2%} gain'
            }
        
        return {'type': 'hold', 'amount': 0, 'reason': 'Risk management OK'}
    
    def _checkTrendAwareGridTriggers(self, currentPrice: float, state: EnvironmentState) -> Dict[str, Any]:
        """检查趋势感知网格触发条件"""
        for grid in self.gridPrices:
            if grid['triggered']:
                continue
                
            if grid['type'] == 'buy' and currentPrice <= grid['price']:
                # Trigger buy order
                grid['triggered'] = True
                tradeAmount = self.maxPosition * (1 - self.baseRatio) / max(len([g for g in self.gridPrices if g['type'] == 'buy']), 1)
                
                return {
                    'type': 'buy',
                    'amount': tradeAmount,
                    'reason': f"Trend-aware grid buy at level {grid['level']} (trend: {self.currentTrend})"
                }
                
            elif grid['type'] == 'sell' and currentPrice >= grid['price']:
                # In strong uptrend, be conservative about selling
                if self.currentTrend == 'bullish' and abs(currentPrice - self.avgCost) / self.avgCost > 0.25:
                    continue  # Skip selling in very strong uptrend
                
                # Only sell if we have grid position (not base position)
                gridPosition = state.position - (self.maxPosition * self.baseRatio / self.avgCost)
                if gridPosition > 0:
                    grid['triggered'] = True
                    tradeAmount = self.maxPosition * (1 - self.baseRatio) / max(len([g for g in self.gridPrices if g['type'] == 'sell']), 1)
                    
                    return {
                        'type': 'sell',
                        'amount': min(tradeAmount, gridPosition * currentPrice),
                        'reason': f"Trend-aware grid sell at level {grid['level']} (trend: {self.currentTrend})"
                    }
        
        # Reset grid if trend changes significantly
        if self.lastPrice is not None:
            priceChange = abs(currentPrice - self.lastPrice) / self.lastPrice
            if priceChange > self.gridSpacing * 2:  # Reset if moved 2 grid levels
                self._resetTrendAwareGrid(currentPrice)
        
        return {'type': 'hold', 'amount': 0, 'reason': f'No grid triggers (trend: {self.currentTrend})'}
    
    def _resetTrendAwareGrid(self, newCenterPrice: float):
        """重置趋势感知网格"""
        oldTrend = self.currentTrend
        newTrend = self._detectTrend()
        
        if oldTrend != newTrend:
            self.logger.info(f"Trend changed from {oldTrend} to {newTrend}, resetting grid around {newCenterPrice:.2f}")
            self.gridInitialized = False
            self._initializeTrendAwareGrid(newCenterPrice)

class HybridAgent(StrategyAgent):
    """混合策略代理 - 结合多种策略"""
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        
        params = config.parameters
        self.gridWeight = params.get('gridWeight', 0.4)
        self.momentumWeight = params.get('momentumWeight', 0.3)
        self.meanReversionWeight = params.get('meanReversionWeight', 0.3)
        
        # Create sub-agents
        self.gridAgent = GridTradingAgent(AgentConfig(
            strategyType='grid',
            parameters=params.get('gridParams', {}),
            riskProfile=config.riskProfile,
            name='grid_sub',
            description='Grid sub-strategy'
        ))
        
        self.momentumAgent = MomentumAgent(AgentConfig(
            strategyType='momentum',
            parameters=params.get('momentumParams', {}),
            riskProfile=config.riskProfile,
            name='momentum_sub',
            description='Momentum sub-strategy'
        ))
        
        self.meanReversionAgent = MeanReversionAgent(AgentConfig(
            strategyType='mean_reversion',
            parameters=params.get('meanReversionParams', {}),
            riskProfile=config.riskProfile,
            name='mean_reversion_sub',
            description='Mean reversion sub-strategy'
        ))
        
    def getName(self) -> str:
        return f"Hybrid_G{self.gridWeight:.1f}_M{self.momentumWeight:.1f}_MR{self.meanReversionWeight:.1f}"
    
    def decide(self, state: EnvironmentState) -> Dict[str, Any]:
        """混合策略决策逻辑"""
        # Get decisions from all sub-agents
        gridDecision = self.gridAgent.decide(state)
        momentumDecision = self.momentumAgent.decide(state)
        meanReversionDecision = self.meanReversionAgent.decide(state)
        
        # Weight the decisions
        decisions = [
            (gridDecision, self.gridWeight),
            (momentumDecision, self.momentumWeight),
            (meanReversionDecision, self.meanReversionWeight)
        ]
        
        # Simple voting mechanism
        buyVotes = sum(weight for decision, weight in decisions if decision['type'] == 'buy')
        sellVotes = sum(weight for decision, weight in decisions if decision['type'] == 'sell')
        holdVotes = sum(weight for decision, weight in decisions if decision['type'] == 'hold')
        
        # Calculate weighted average amount
        totalBuyAmount = sum(decision['amount'] * weight for decision, weight in decisions 
                           if decision['type'] == 'buy')
        totalSellAmount = sum(decision['amount'] * weight for decision, weight in decisions 
                            if decision['type'] == 'sell')
        
        # Make final decision
        if buyVotes > sellVotes and buyVotes > holdVotes:
            return {
                'type': 'buy',
                'amount': totalBuyAmount if totalBuyAmount > 0 else 1000,
                'reason': f"Hybrid buy (weights: B{buyVotes:.2f}, S{sellVotes:.2f}, H{holdVotes:.2f})"
            }
        elif sellVotes > buyVotes and sellVotes > holdVotes:
            return {
                'type': 'sell',
                'amount': totalSellAmount if totalSellAmount > 0 else 1000,
                'reason': f"Hybrid sell (weights: B{buyVotes:.2f}, S{sellVotes:.2f}, H{holdVotes:.2f})"
            }
        else:
            return {
                'type': 'hold',
                'amount': 0,
                'reason': f"Hybrid hold (weights: B{buyVotes:.2f}, S{sellVotes:.2f}, H{holdVotes:.2f})"
            }

def createAgent(agentType: str, config: AgentConfig) -> StrategyAgent:
    """创建策略代理工厂函数"""
    agentClasses = {
        'grid': TrendAwareGridAgent,
        'trend_aware_grid': TrendAwareGridAgent,
        'dca': DCAAgent,
        'momentum': MomentumAgent,
        'mean_reversion': MeanReversionAgent,
        'hybrid': HybridAgent
    }
    
    if agentType not in agentClasses:
        raise ValueError(f"Unknown agent type: {agentType}")
    
    return agentClasses[agentType](config) 