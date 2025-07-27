"""
Trading Environment for Strategy Optimization
交易环境 - 为策略优化提供模拟环境
"""
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

@dataclass
class EnvironmentState:
    """环境状态"""
    currentPrice: float
    priceHistory: List[float]
    position: float  # 当前持仓股数
    cash: float
    totalValue: float
    timestamp: datetime
    technicalIndicators: Dict[str, float]

@dataclass
class ActionResult:
    """动作执行结果"""
    success: bool
    executedAmount: float
    executionPrice: float
    commission: float
    slippage: float
    newPosition: float
    newCash: float
    message: str

@dataclass
class PerformanceMetrics:
    """性能指标"""
    totalReturn: float
    annualizedReturn: float
    sharpeRatio: float
    maxDrawdown: float
    winRate: float
    profitLossRatio: float
    totalTrades: int
    volatility: float
    alpha: float
    beta: float
    avgTradeReturn: float = 0.0  # Average return per trade

class TradingEnvironment:
    """交易环境类 - 为策略代理提供模拟交易环境"""
    
    def __init__(self, symbol: str, dataProvider, startDate: str, endDate: str, 
                 initialCapital: float = 100000, commission: float = 0.0003, 
                 slippage: float = 0.001):
        self.symbol = symbol
        self.dataProvider = dataProvider
        self.startDate = startDate
        self.endDate = endDate
        self.initialCapital = initialCapital
        self.commission = commission
        self.slippage = slippage
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        
        # Load historical data
        self.priceData = self._loadPriceData()
        self.benchmarkData = self._loadBenchmarkData()
        
        # Environment state
        self.reset()
    
    def _loadPriceData(self) -> pd.DataFrame:
        """加载价格数据"""
        try:
            data = self.dataProvider.getStockData(self.symbol, self.startDate, self.endDate)
            if data is None or data.empty:
                raise ValueError(f"No data available for {self.symbol}")
            
            # Ensure data is sorted by date
            data = data.sort_index()
            
            # Calculate technical indicators
            data = self._calculateTechnicalIndicators(data)
            
            return data
        except Exception as e:
            self.logger.error(f"Failed to load price data for {self.symbol}: {str(e)}")
            raise
    
    def _loadBenchmarkData(self) -> pd.DataFrame:
        """加载基准数据（如沪深300）"""
        try:
            # Use a broad market index as benchmark
            benchmarkSymbol = '000300.SH'  # 沪深300
            if self.symbol.endswith('.HK'):
                benchmarkSymbol = '^HSI'  # 恒生指数
            elif self.symbol.endswith('.US'):
                benchmarkSymbol = '^GSPC'  # S&P 500
            
            # Try to get benchmark data using index-specific method if available
            # Check if data provider supports getIndexData and if we're dealing with index symbols
            if hasattr(self.dataProvider, 'getIndexData') and (
                benchmarkSymbol.endswith(('.SH', '.SZ')) or 
                benchmarkSymbol.startswith(('000', '399', '^'))
            ):
                # Use dedicated index data method for indices
                try:
                    self.logger.info(f"Attempting to load benchmark index data for {benchmarkSymbol}")
                    benchmarkData = self.dataProvider.getIndexData(benchmarkSymbol, self.startDate, self.endDate)
                    if benchmarkData is not None and not benchmarkData.empty:
                        self.logger.info(f"Successfully loaded benchmark index data for {benchmarkSymbol}")
                        return benchmarkData
                    else:
                        self.logger.warning(f"No benchmark index data available for {benchmarkSymbol}")
                except Exception as e:
                    self.logger.warning(f"Failed to load benchmark index data for {benchmarkSymbol}: {str(e)}")
                
                # If main benchmark fails, try alternative benchmarks for A-shares
                if self.symbol.endswith(('.SZ', '.SH')):
                    alternativeBenchmarks = ['399300.SZ', '000001.SH']  # 沪深300深圳版本, 上证指数
                    for altSymbol in alternativeBenchmarks:
                        try:
                            self.logger.info(f"Trying alternative benchmark index {altSymbol}")
                            benchmarkData = self.dataProvider.getIndexData(altSymbol, self.startDate, self.endDate)
                            if benchmarkData is not None and not benchmarkData.empty:
                                self.logger.info(f"Successfully loaded alternative benchmark index data for {altSymbol}")
                                return benchmarkData
                        except Exception as e:
                            self.logger.debug(f"Alternative benchmark index {altSymbol} also failed: {str(e)}")
                            continue
                
                # If all index methods fail, try with a major stock as proxy (not ideal but better than nothing)
                if self.symbol.endswith(('.SZ', '.SH')):
                    self.logger.info("All index data attempts failed, trying major stock as benchmark proxy")
                    try:
                        # Use a major stock like 中国平安 as a rough market proxy
                        proxySymbol = '601318.SH'  # 中国平安 - large cap stock
                        benchmarkData = self.dataProvider.getStockData(proxySymbol, self.startDate, self.endDate)
                        if benchmarkData is not None and not benchmarkData.empty:
                            self.logger.info(f"Using stock {proxySymbol} as benchmark proxy")
                            return benchmarkData
                    except Exception as e:
                        self.logger.debug(f"Benchmark proxy stock {proxySymbol} also failed: {str(e)}")
                
                # Return empty DataFrame if all index/proxy attempts failed
                self.logger.info("All benchmark index attempts failed, proceeding without benchmark")
                return pd.DataFrame()
            
            # Only use stock data method for non-index symbols or data providers without getIndexData
            else:
                try:
                    self.logger.info(f"Using stock data method for benchmark {benchmarkSymbol}")
                    benchmarkData = self.dataProvider.getStockData(benchmarkSymbol, self.startDate, self.endDate)
                    if benchmarkData is not None and not benchmarkData.empty:
                        self.logger.info(f"Successfully loaded benchmark data for {benchmarkSymbol}")
                        return benchmarkData
                    else:
                        self.logger.warning(f"No benchmark data available for {benchmarkSymbol}")
                except Exception as e:
                    self.logger.warning(f"Failed to load benchmark data for {benchmarkSymbol}: {str(e)}")
                
                self.logger.info("No benchmark data available, proceeding without benchmark")
                return pd.DataFrame()
            
        except Exception as e:
            self.logger.warning(f"Error loading benchmark data: {str(e)}")
            return pd.DataFrame()
    
    def _calculateTechnicalIndicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        # Simple Moving Averages
        data['SMA_5'] = data['close'].rolling(window=5).mean()
        data['SMA_10'] = data['close'].rolling(window=10).mean()
        data['SMA_20'] = data['close'].rolling(window=20).mean()
        data['SMA_60'] = data['close'].rolling(window=60).mean()
        
        # Exponential Moving Averages
        data['EMA_12'] = data['close'].ewm(span=12).mean()
        data['EMA_26'] = data['close'].ewm(span=26).mean()
        
        # MACD
        data['MACD'] = data['EMA_12'] - data['EMA_26']
        data['MACD_signal'] = data['MACD'].ewm(span=9).mean()
        data['MACD_histogram'] = data['MACD'] - data['MACD_signal']
        
        # RSI
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        data['RSI'] = 100 - (100 / (1 + rs))
        
        # Bollinger Bands
        data['BB_middle'] = data['close'].rolling(window=20).mean()
        bb_std = data['close'].rolling(window=20).std()
        data['BB_upper'] = data['BB_middle'] + (bb_std * 2)
        data['BB_lower'] = data['BB_middle'] - (bb_std * 2)
        
        # Volume indicators
        data['volume_SMA_20'] = data['volume'].rolling(window=20).mean()
        data['volume_ratio'] = data['volume'] / data['volume_SMA_20']
        
        # Price change indicators
        data['price_change'] = data['close'].pct_change()
        data['volatility_20'] = data['price_change'].rolling(window=20).std()
        
        return data
    
    def reset(self) -> EnvironmentState:
        """重置环境状态"""
        self.currentIndex = 0
        self.cash = self.initialCapital
        self.position = 0.0  # 持仓股数
        self.basePosition = 0.0  # Base position that doesn't trade
        self.tradeHistory = []
        self.valueHistory = []
        self.drawdownHistory = []
        
        if len(self.priceData) == 0:
            raise ValueError("No price data available")
        
        currentRow = self.priceData.iloc[self.currentIndex]
        currentPrice = currentRow['close']
        
        state = EnvironmentState(
            currentPrice=currentPrice,
            priceHistory=[currentPrice],
            position=self.position,
            cash=self.cash,
            totalValue=self.cash + self.position * currentPrice,
            timestamp=currentRow.name,
            technicalIndicators=self._getTechnicalIndicators(self.currentIndex)
        )
        
        return state
    
    def step(self, action: Dict[str, Any]) -> Tuple[EnvironmentState, float, bool, Dict]:
        """执行一步动作"""
        if self.currentIndex >= len(self.priceData) - 1:
            return self.getCurrentState(), 0.0, True, {'message': 'Episode finished'}
        
        # Execute action
        actionResult = self._executeAction(action)
        
        # Move to next time step
        self.currentIndex += 1
        currentRow = self.priceData.iloc[self.currentIndex]
        currentPrice = currentRow['close']
        
        # Calculate reward
        previousValue = self.valueHistory[-1] if self.valueHistory else self.initialCapital
        currentValue = self.cash + (self.position * currentPrice if currentPrice > 0 else 0)
        self.valueHistory.append(currentValue)
        
        reward = self._calculateReward(previousValue, currentValue, actionResult)
        
        # Update state
        state = EnvironmentState(
            currentPrice=currentPrice,
            priceHistory=self.valueHistory[-50:],  # Keep last 50 values
            position=self.position,
            cash=self.cash,
            totalValue=currentValue,
            timestamp=currentRow.name,
            technicalIndicators=self._getTechnicalIndicators(self.currentIndex)
        )
        
        # Check if episode is done
        done = self.currentIndex >= len(self.priceData) - 1
        
        info = {
            'actionResult': actionResult,
            'currentValue': currentValue,
            'totalReturn': (currentValue - self.initialCapital) / self.initialCapital
        }
        
        return state, reward, done, info
    
    def _executeAction(self, action: Dict[str, Any]) -> ActionResult:
        """执行交易动作"""
        actionType = action.get('type', 'hold')  # buy, sell, hold
        amount = action.get('amount', 0)  # Amount in currency
        
        currentRow = self.priceData.iloc[self.currentIndex]
        currentPrice = currentRow['close']
        
        if actionType == 'hold':
            return ActionResult(
                success=True, executedAmount=0, executionPrice=currentPrice,
                commission=0, slippage=0, newPosition=self.position,
                newCash=self.cash, message="Held position"
            )
        
        # Apply slippage
        if actionType == 'buy':
            executionPrice = currentPrice * (1 + self.slippage)
        else:  # sell
            executionPrice = currentPrice * (1 - self.slippage)
        
        if actionType == 'buy':
            # Calculate how many shares we can buy
            maxSpendable = min(amount, self.cash)
            
            # Calculate shares considering commission (100 shares minimum trading unit)
            sharesCount = int(maxSpendable / (executionPrice * (1 + self.commission)) / 100) * 100
            
            if sharesCount < 100:
                return ActionResult(
                    success=False, executedAmount=0, executionPrice=executionPrice,
                    commission=0, slippage=0, newPosition=self.position,
                    newCash=self.cash, message="Insufficient cash for minimum 100 shares"
                )
            
            actualAmount = sharesCount * executionPrice
            commission = actualAmount * self.commission
            totalCost = actualAmount + commission
            
            if totalCost > self.cash:
                return ActionResult(
                    success=False, executedAmount=0, executionPrice=executionPrice,
                    commission=0, slippage=0, newPosition=self.position,
                    newCash=self.cash, message="Insufficient cash after commission"
                )
            
            self.position += sharesCount
            self.cash -= totalCost
            
            # Record trade
            self.tradeHistory.append({
                'timestamp': currentRow.name,
                'type': 'buy',
                'price': executionPrice,
                'shares': sharesCount,
                'amount': actualAmount,
                'commission': commission
            })
            
            return ActionResult(
                success=True, executedAmount=actualAmount, executionPrice=executionPrice,
                commission=commission, slippage=self.slippage, newPosition=self.position,
                newCash=self.cash, message=f"Bought {sharesCount} shares (100x multiple)"
            )
        
        elif actionType == 'sell':
            if self.position <= 0:
                return ActionResult(
                    success=False, executedAmount=0, executionPrice=executionPrice,
                    commission=0, slippage=0, newPosition=self.position,
                    newCash=self.cash, message="No shares to sell"
                )
            
            # Calculate how many shares to sell based on amount (100 shares minimum trading unit)
            if amount <= 0:
                # Sell all position, round down to nearest 100 shares
                sharesToSell = int(self.position / 100) * 100
            else:
                sharesToSell = min(int(amount / executionPrice / 100) * 100, int(self.position / 100) * 100)
            
            if sharesToSell < 100:
                return ActionResult(
                    success=False, executedAmount=0, executionPrice=executionPrice,
                    commission=0, slippage=0, newPosition=self.position,
                    newCash=self.cash, message="Insufficient shares for minimum 100 shares sale"
                )
            
            actualAmount = sharesToSell * executionPrice
            commission = actualAmount * self.commission
            netAmount = actualAmount - commission
            
            self.position -= sharesToSell
            self.cash += netAmount
            
            # Record trade
            self.tradeHistory.append({
                'timestamp': currentRow.name,
                'type': 'sell',
                'price': executionPrice,
                'shares': sharesToSell,
                'amount': actualAmount,
                'commission': commission
            })
            
            return ActionResult(
                success=True, executedAmount=actualAmount, executionPrice=executionPrice,
                commission=commission, slippage=self.slippage, newPosition=self.position,
                newCash=self.cash, message=f"Sold {sharesToSell} shares (100x multiple)"
            )
    
    def _calculateReward(self, previousValue: float, currentValue: float, 
                        actionResult: ActionResult) -> float:
        """计算奖励"""
        # Basic return-based reward
        returnReward = (currentValue - previousValue) / previousValue if previousValue > 0 else 0
        
        # Transaction cost penalty
        costPenalty = -(actionResult.commission + 
                       abs(actionResult.executedAmount * self.slippage)) / self.initialCapital
        
        # Risk penalty (for large drawdowns)
        if self.valueHistory:
            peak = max(self.valueHistory)
            drawdown = (peak - currentValue) / peak if peak > 0 else 0
            riskPenalty = -drawdown * 0.1  # Penalize drawdowns
        else:
            riskPenalty = 0
        
        return returnReward + costPenalty + riskPenalty
    
    def _getTechnicalIndicators(self, index: int) -> Dict[str, float]:
        """获取当前时点的技术指标"""
        if index >= len(self.priceData):
            return {}
        
        row = self.priceData.iloc[index]
        return {
            'SMA_5': row.get('SMA_5', 0),
            'SMA_20': row.get('SMA_20', 0),
            'RSI': row.get('RSI', 50),
            'MACD': row.get('MACD', 0),
            'MACD_signal': row.get('MACD_signal', 0),
            'BB_upper': row.get('BB_upper', 0),
            'BB_lower': row.get('BB_lower', 0),
            'volume_ratio': row.get('volume_ratio', 1),
            'volatility_20': row.get('volatility_20', 0)
        }
    
    def getCurrentState(self) -> EnvironmentState:
        """获取当前状态"""
        if self.currentIndex >= len(self.priceData):
            currentPrice = self.priceData.iloc[-1]['close']
        else:
            currentPrice = self.priceData.iloc[self.currentIndex]['close']
        
        currentValue = self.cash + (self.position * currentPrice if currentPrice > 0 else 0)
        
        return EnvironmentState(
            currentPrice=currentPrice,
            priceHistory=self.valueHistory[-50:] if self.valueHistory else [self.initialCapital],
            position=self.position,
            cash=self.cash,
            totalValue=currentValue,
            timestamp=self.priceData.index[min(self.currentIndex, len(self.priceData)-1)],
            technicalIndicators=self._getTechnicalIndicators(min(self.currentIndex, len(self.priceData)-1))
        )
    
    def calculatePerformanceMetrics(self) -> PerformanceMetrics:
        """计算性能指标"""
        if not self.valueHistory:
            return PerformanceMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        
        # Convert to numpy array for easier calculation
        values = np.array(self.valueHistory)
        returns = np.diff(values) / values[:-1]
        
        # Total return
        totalReturn = (values[-1] - self.initialCapital) / self.initialCapital
        
        # Annualized return
        tradingDays = len(values)
        annualizedReturn = (1 + totalReturn) ** (252 / tradingDays) - 1 if tradingDays > 0 else 0
        
        # Sharpe ratio
        if len(returns) > 1:
            sharpeRatio = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpeRatio = 0
        
        # Maximum drawdown
        peaks = np.maximum.accumulate(values)
        drawdowns = (peaks - values) / peaks
        maxDrawdown = np.max(drawdowns) if len(drawdowns) > 0 else 0
        
        # Win rate and profit/loss ratio
        trades = pd.DataFrame(self.tradeHistory)
        if len(trades) > 0:
            # Group buy and sell trades
            buyTrades = trades[trades['type'] == 'buy']
            sellTrades = trades[trades['type'] == 'sell']
            
            if len(sellTrades) > 0:
                profits = []
                for _, sellTrade in sellTrades.iterrows():
                    # Find corresponding buy trades
                    correspondingBuys = buyTrades[buyTrades['timestamp'] <= sellTrade['timestamp']]
                    if len(correspondingBuys) > 0:
                        avgBuyPrice = correspondingBuys['price'].mean()
                        profit = (sellTrade['price'] - avgBuyPrice) / avgBuyPrice
                        profits.append(profit)
                
                if profits:
                    winningTrades = [p for p in profits if p > 0]
                    losingTrades = [p for p in profits if p < 0]
                    
                    winRate = len(winningTrades) / len(profits)
                    
                    if losingTrades:
                        avgWin = np.mean(winningTrades) if winningTrades else 0
                        avgLoss = abs(np.mean(losingTrades))
                        profitLossRatio = avgWin / avgLoss if avgLoss > 0 else 0
                    else:
                        profitLossRatio = float('inf') if winningTrades else 0
                else:
                    winRate = 0
                    profitLossRatio = 0
            else:
                winRate = 0
                profitLossRatio = 0
                
            totalTrades = len(trades)
        else:
            winRate = 0
            profitLossRatio = 0
            totalTrades = 0
        
        # Volatility
        volatility = np.std(returns) * np.sqrt(252) if len(returns) > 1 else 0
        
        # Alpha and Beta (vs benchmark)
        alpha, beta = 0, 1  # Default values
        if not self.benchmarkData.empty and len(returns) > 1:
            try:
                benchmarkReturns = self.benchmarkData['close'].pct_change().dropna()
                if len(benchmarkReturns) >= len(returns):
                    benchmarkReturns = benchmarkReturns.iloc[:len(returns)]
                    if len(benchmarkReturns) == len(returns):
                        covariance = np.cov(returns, benchmarkReturns)[0][1]
                        benchmarkVariance = np.var(benchmarkReturns)
                        if benchmarkVariance > 0:
                            beta = covariance / benchmarkVariance
                            alpha = np.mean(returns) - beta * np.mean(benchmarkReturns)
            except:
                pass  # Use default values
        
        # Calculate average trade return
        avgTradeReturn = 0.0
        if trades and len(trades) > 0:
            # Calculate average return per trade based on portfolio value changes
            if len(self.valueHistory) > 1:
                totalGain = values[-1] - values[0]
                avgTradeReturn = totalGain / len(trades) if len(trades) > 0 else 0.0
        
        return PerformanceMetrics(
            totalReturn=totalReturn,
            annualizedReturn=annualizedReturn,
            sharpeRatio=sharpeRatio,
            maxDrawdown=maxDrawdown,
            winRate=winRate,
            profitLossRatio=profitLossRatio,
            totalTrades=totalTrades,
            volatility=volatility,
            alpha=alpha,
            beta=beta,
            avgTradeReturn=avgTradeReturn
        ) 