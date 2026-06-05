import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import Dict, List, Tuple
from datetime import datetime, timedelta

from ..data_providers.data_provider_factory import createDataProvider
from ..strategies.unified_grid_strategy import UnifiedGridTradingStrategy
from quant.core.legacy_config import Config
from quant.core.logging_config import get_logger

logger = get_logger(__name__)

class BacktestEngine:
    """Backtesting engine for grid trading strategy"""
    
    def __init__(self, dataProvider: str = None):
        """
        Initialize backtest engine
        
        Args:
            dataProvider (str): Data provider name ('tushare', 'yahoo', 'auto')
        """
        # Ensure dataProvider is a string or None
        if dataProvider is not None and not isinstance(dataProvider, str):
            # If someone passed an object instead of a string, extract the class name
            if hasattr(dataProvider, '__class__'):
                logger.warning(f"Expected string but got {type(dataProvider)}. Using 'auto' instead.")
                dataProvider = 'auto'
            else:
                dataProvider = str(dataProvider)
        
        providerName = dataProvider or Config.DATA_PROVIDER_CONFIG['defaultProvider']
        
        # Ensure providerName is a string
        if not isinstance(providerName, str):
            logger.warning(f"Config defaultProvider is not a string: {type(providerName)}. Using 'auto'.")
            providerName = 'auto'
        
        try:
            if providerName.lower() == 'auto':
                self.dataProvider = createDataProvider('auto', Config.DATA_PROVIDER_CONFIG)
            else:
                providerConfig = Config.DATA_PROVIDER_CONFIG.get(providerName, {})
                self.dataProvider = createDataProvider(providerName, providerConfig)
            
            logger.info(f"Initialized backtest engine with {self.dataProvider.__class__.__name__}")
            
        except Exception as e:
            logger.info(f"Failed to initialize data provider '{providerName}': {str(e)}")
            logger.info("Falling back to auto mode...")
            self.dataProvider = createDataProvider('auto', Config.DATA_PROVIDER_CONFIG)
        
        self.results = {}
        
    def runBacktest(self, symbol: str, startDate: str, endDate: str, 
                   initialCapital: float = None, strategyConfig: Dict = None, strategy = None) -> Dict:
        """
        Run backtest for grid trading strategy
        
        Args:
            symbol (str): Stock symbol (e.g., '000001.SZ')
            startDate (str): Start date in YYYYMMDD format
            endDate (str): End date in YYYYMMDD format
            initialCapital (float): Initial capital for trading
            strategyConfig (Dict): Strategy configuration parameters
            strategy: Strategy instance to use (if None, uses UnifiedGridTradingStrategy)
            
        Returns:
            Dict: Backtest results
        """
        logger.info(f"{'='*80}")
        logger.info(f"🚀 开始回测 {symbol} | 期间: {startDate} - {endDate} | 初始资金: ¥{initialCapital:,.0f}")
        logger.info(f"{'='*80}")
        
        # Set default values
        if initialCapital is None:
            initialCapital = Config.BACKTEST_CONFIG['initialCapital']
        
        # Get stock data
        stockData = self.dataProvider.getStockData(symbol, startDate, endDate)
        if stockData.empty:
            raise ValueError(f"No data available for {symbol}")
        
        # Initialize strategy
        if strategy is None:
            # Fall back to unified grid strategy
            strategy = UnifiedGridTradingStrategy(symbol, strategyConfig)
            
            # Add safety check: ensure strategy has proper configuration
            if not strategyConfig:
                logger.warning("No strategy configuration provided, using default safe config")
                strategyConfig = {
                    'gridLevels': 6,
                    'gridSpacing': 0.02,  # 2%
                    'maxPosition': 100000,
                    'baseRatio': 0.2,  # Conservative 20% base position
                    'commission': 0.0003,
                    'slippage': 0.001,
                    'dynamicEnabled': True  # Enable dynamic features for better risk control
                }
                strategy = UnifiedGridTradingStrategy(symbol, strategyConfig)
        
        strategy.reset(initialCapital)
        
        # Setup grids if strategy supports it (for grid-based strategies)
        if hasattr(strategy, 'setupGrids'):
            # Calculate price range for grid setup
            priceHigh = stockData['high'].max()
            priceLow = stockData['low'].min()
            referencePrice = stockData['close'].iloc[0]
            
            # Setup grids with some buffer
            maxPrice = priceHigh * 1.1
            minPrice = priceLow * 0.9
            strategy.setupGrids(referencePrice, maxPrice, minPrice)
        
        # Run simulation
        portfolioValues = []
        positions = []
        cashValues = []
        
        # Import MarketState for non-grid strategies
        from ..strategies.base_strategy import MarketState
        
        for timestamp, row in stockData.iterrows():
            currentPrice = row['close']
            currentVolume = row.get('volume', row.get('vol', 0))  # Volume column is 'volume'; fall back to 'vol'
            
            # Check if strategy uses the new BaseStrategy interface
            if hasattr(strategy, 'makeDecision'):
                # New interface: use makeDecision with MarketState
                market_state = MarketState(
                    timestamp=timestamp,
                    open=row.get('open', currentPrice),
                    high=row.get('high', currentPrice),
                    low=row.get('low', currentPrice),
                    close=currentPrice,
                    volume=currentVolume
                )
                decision = strategy.makeDecision(market_state)
                
                # Calculate portfolio value
                portfolio_value = strategy.cash + (strategy.position * currentPrice)
                positions.append(strategy.position)
                cashValues.append(strategy.cash)
            elif hasattr(strategy, 'onMarketData'):
                # Old interface: use onMarketData
                if 'volume' in strategy.onMarketData.__code__.co_varnames:
                    strategy.onMarketData(timestamp, currentPrice, currentVolume)
                else:
                    strategy.onMarketData(timestamp, currentPrice)
                
                # Update portfolio value
                strategy.updatePortfolioValue(currentPrice)
                portfolio_value = strategy.totalValue
                positions.append(strategy.currentPosition)
                cashValues.append(strategy.currentCash)
            
            # Record daily values
            portfolioValues.append(portfolio_value)
        
        # Calculate final portfolio value. Prefer the engine's own marked-to-market
        # series, which reflects an untraded base position even when a strategy does
        # not refresh its internal totalValue each bar (e.g. grid in a trend).
        final_price = stockData['close'].iloc[-1]
        if portfolioValues:
            final_value = portfolioValues[-1]
        elif hasattr(strategy, 'totalValue'):
            final_value = strategy.totalValue
        else:
            final_value = strategy.cash + (strategy.position * final_price)
        
        # SAFETY CHECK: Validate final portfolio value
        if final_value <= 0:
            logger.info(f"🚨 CRITICAL ERROR: Final portfolio value is 0 or negative: {final_value}")
            logger.info(f"   Initial capital: {initialCapital}")
            logger.info("   This indicates a serious calculation error.")
            # Set a reasonable minimum value
            final_value = max(initialCapital * 0.01, 1000)  # At least 1% of initial capital
        
        if final_value > initialCapital * 100:  # More than 10000% gain
            logger.info(f"🚨 WARNING: Extremely high portfolio value: {final_value}")
            logger.info(f"   Initial capital: {initialCapital}")
            logger.info(f"   Gain: {(final_value / initialCapital - 1):.1%}")
            logger.info("   This may indicate a calculation error.")
        
        # Close the book at market so strategy-side metrics agree with the engine's
        # final value (covers an untraded base position that rode the trend).
        if hasattr(strategy, 'totalValue'):
            strategy.totalValue = final_value

        # Get performance metrics
        if hasattr(strategy, 'getPerformanceMetrics'):
            performanceMetrics = strategy.getPerformanceMetrics(initialCapital)
        else:
            # Calculate basic metrics
            performanceMetrics = strategy.get_performance_metrics()
            performanceMetrics['totalValue'] = final_value
            performanceMetrics['totalReturn'] = (final_value - initialCapital) / initialCapital
            performanceMetrics['totalTrades'] = len(strategy.trades) if hasattr(strategy, 'trades') else 0
        
        # Calculate additional metrics
        additionalMetrics = self._calculateAdditionalMetrics(
            stockData, portfolioValues, initialCapital, strategy.trades
        )
        
        # Extract grid adjustments if available
        gridAdjustments = []
        if hasattr(strategy, 'gridAdjustments') and strategy.gridAdjustments:
            gridAdjustments = strategy.gridAdjustments
        
        # Combine results
        results = {
            'symbol': symbol,
            'startDate': startDate,
            'endDate': endDate,
            'initialCapital': initialCapital,
            'stockData': stockData,
            'portfolioValues': portfolioValues,
            'positions': positions,
            'cashValues': cashValues,
            'trades': strategy.trades,
            'performance': {**performanceMetrics, **additionalMetrics},
            'strategy': strategy,
            'gridAdjustments': gridAdjustments
        }
        
        self.results[symbol] = results
        
        # 提取关键策略参数用于显示
        dynamicEnabled = strategyConfig.get('dynamicEnabled', True) if strategyConfig else True
        gridLevels = strategyConfig.get('gridLevels', 'N/A') if strategyConfig else 'N/A'
        gridSpacing = strategyConfig.get('gridSpacing', 0) if strategyConfig else 0
        baseRatio = strategyConfig.get('baseRatio', 0) if strategyConfig else 0
        adjustmentThreshold = strategyConfig.get('adjustmentThreshold', 0) if strategyConfig else 0
        adjustmentCooldown = strategyConfig.get('adjustmentCooldown', 0) if strategyConfig else 0
        gridAdjustmentCount = len(gridAdjustments) if gridAdjustments else 0
        
        optimization_method = strategyConfig.get('optimizationMethod') if strategyConfig else None
        method_tag = f" [{optimization_method}]" if optimization_method else ""
        logger.info(f"✅ 回测完成{method_tag} {symbol} | 总收益: {performanceMetrics.get('totalReturn', 0):+.2%} | 交易: {performanceMetrics.get('totalTrades', 0)}次 | 胜率: {performanceMetrics.get('winRate', 0):.1%}")
        if dynamicEnabled:
            logger.info(f"📊 策略参数 | 动态调整: 启用 (阈值{adjustmentThreshold:.1%} 冷却{adjustmentCooldown}天) | 网格: {gridLevels}层 {gridSpacing:.1%}间距 | 基础仓位: {baseRatio:.1%} | 网格调整: {gridAdjustmentCount}次")
        else:
            logger.info(f"📊 策略参数 | 动态调整: 禁用 | 网格: {gridLevels}层 {gridSpacing:.1%}间距 | 基础仓位: {baseRatio:.1%} | 网格调整: {gridAdjustmentCount}次")
        logger.info(f"{'='*80}")
        
        return results
    
    def _calculateAdditionalMetrics(self, stockData: pd.DataFrame, portfolioValues: List[float], 
                                  initialCapital: float, trades: List) -> Dict:
        """Calculate additional performance metrics"""
        portfolioSeries = pd.Series(portfolioValues, index=stockData.index)
        stockReturns = stockData['close'].pct_change().dropna()
        portfolioReturns = portfolioSeries.pct_change().dropna()
        
        # Calculate max drawdown
        cumMax = portfolioSeries.expanding().max()
        drawdown = (portfolioSeries - cumMax) / cumMax
        maxDrawdown = drawdown.min()
        
        # Calculate volatility
        portfolioVolatility = portfolioReturns.std() * np.sqrt(252)
        
        # Calculate beta vs stock
        if len(portfolioReturns) > 1 and len(stockReturns) > 1:
            try:
                portfolioReturnsClean = portfolioReturns.dropna()
                stockReturnsClean = stockReturns.dropna()
                if len(portfolioReturnsClean) > 1 and len(stockReturnsClean) > 1:
                    covariance = np.cov(portfolioReturnsClean, stockReturnsClean)[0][1]
                    stockVariance = stockReturnsClean.var()
                    beta = covariance / stockVariance if stockVariance > 0 else 0
                else:
                    beta = 0
            except:
                beta = 0
        else:
            beta = 0
        
        # Calculate alpha and annualized return
        riskFreeRate = 0.03  # Assume 3% risk-free rate
        stockReturn = (stockData['close'].iloc[-1] / stockData['close'].iloc[0]) - 1
        portfolioReturn = (portfolioSeries.iloc[-1] / portfolioSeries.iloc[0]) - 1
        alpha = portfolioReturn - (riskFreeRate + beta * (stockReturn - riskFreeRate))
        
        # Calculate annualized return
        numDays = (stockData.index[-1] - stockData.index[0]).days
        numYears = numDays / 365.25
        annualReturn = (1 + portfolioReturn) ** (1 / numYears) - 1 if numYears > 0 else 0
        
        # Calculate Calmar ratio
        calmarRatio = portfolioReturn / abs(maxDrawdown) if maxDrawdown != 0 and abs(maxDrawdown) > 1e-10 else 0
        
        # Trade statistics
        if trades:
            # Handle both dict and object trades
            try:
                if isinstance(trades[0], dict):
                    # Dict-based trades
                    profitableTrades = [t for t in trades if t.get('pnl', 0) > 0]
                    avgProfit = np.mean([t.get('pnl', 0) for t in profitableTrades]) if profitableTrades else 0
                    avgLoss = np.mean([t.get('pnl', 0) for t in trades if t.get('pnl', 0) < 0]) if any(t.get('pnl', 0) < 0 for t in trades) else 0
                else:
                    # Object-based trades
                    profitableTrades = [t for t in trades if t.pnl > 0]
                    avgProfit = np.mean([t.pnl for t in profitableTrades]) if profitableTrades else 0
                    avgLoss = np.mean([t.pnl for t in trades if t.pnl < 0]) if any(t.pnl < 0 for t in trades) else 0
                profitFactor = abs(avgProfit / avgLoss) if avgLoss != 0 and abs(avgLoss) > 1e-10 else float('inf')
            except:
                avgProfit = avgLoss = profitFactor = 0
        else:
            avgProfit = avgLoss = profitFactor = 0
        
        return {
            'maxDrawdown': maxDrawdown,
            'volatility': portfolioVolatility,
            'beta': beta,
            'alpha': alpha,
            'calmarRatio': calmarRatio,
            'avgProfit': avgProfit,
            'avgLoss': avgLoss,
            'profitFactor': profitFactor,
            'finalValue': portfolioSeries.iloc[-1],
            'benchmarkReturn': stockReturn,
            'annualReturn': annualReturn
        }
    
    def optimizeParameters(self, symbol: str, startDate: str, endDate: str, 
                          parameterRanges: Dict) -> Dict:
        """
        Optimize strategy parameters using grid search
        
        Args:
            symbol (str): Stock symbol
            startDate (str): Start date
            endDate (str): End date
            parameterRanges (Dict): Parameter ranges for optimization
            
        Returns:
            Dict: Optimization results
        """
        logger.info(f"Starting parameter optimization for {symbol}")
        
        bestPerformance = -float('inf')
        bestParams = None
        allResults = []
        
        # Generate parameter combinations
        paramCombinations = self._generateParameterCombinations(parameterRanges)
        
        for i, params in enumerate(paramCombinations):
            logger.info(f"Testing parameter set {i+1}/{len(paramCombinations)}: {params}")
            
            try:
                # Create custom config for this test
                customConfig = Config.GRID_STRATEGY_CONFIG.copy()
                customConfig.update(params)
                
                # Run backtest
                result = self.runBacktest(
                    symbol, startDate, endDate, 
                    strategyConfig=customConfig
                )
                
                # Extract performance metric (using total return as primary metric)
                performance = result['performance'].get('totalReturn', -1)
                
                allResults.append({
                    'parameters': params,
                    'performance': performance,
                    'metrics': result['performance']
                })
                
                # Update best parameters
                if performance > bestPerformance:
                    bestPerformance = performance
                    bestParams = params
                    
            except Exception as e:
                logger.error(f"testing parameters {params}: {str(e)}")
                continue
        
        optimizationResults = {
            'bestParameters': bestParams,
            'bestPerformance': bestPerformance,
            'allResults': allResults,
            'symbol': symbol
        }
        
        logger.info(f"Optimization completed. Best performance: {bestPerformance:.2%}")
        logger.info(f"Best parameters: {bestParams}")
        
        return optimizationResults
    
    def _generateParameterCombinations(self, parameterRanges: Dict) -> List[Dict]:
        """Generate all parameter combinations for optimization"""
        import itertools

        keys = list(parameterRanges.keys())
        values = list(parameterRanges.values())
        
        combinations = []
        for combination in itertools.product(*values):
            paramDict = dict(zip(keys, combination))
            combinations.append(paramDict)
        
        return combinations
    
    def generateReport(self, symbol: str = None) -> str:
        """Generate backtest report"""
        if symbol and symbol in self.results:
            results = [self.results[symbol]]
        else:
            results = list(self.results.values())
        
        if not results:
            return "No backtest results available"
        
        report = "=== Grid Trading Strategy Backtest Report ===\n\n"
        
        for result in results:
            perf = result['performance']
            report += f"Symbol: {result['symbol']}\n"
            report += f"Period: {result['startDate']} to {result['endDate']}\n"
            report += f"Initial Capital: {result['initialCapital']:,.2f} RMB\n"
            report += f"Final Value: {perf.get('finalValue', 0):,.2f} RMB\n"
            report += f"Total Return: {perf.get('totalReturn', 0):.2%}\n"
            report += f"Benchmark Return: {perf.get('benchmarkReturn', 0):.2%}\n"
            report += f"Alpha: {perf.get('alpha', 0):.2%}\n"
            report += f"Max Drawdown: {perf.get('maxDrawdown', 0):.2%}\n"
            report += f"Sharpe Ratio: {perf.get('sharpeRatio', 0):.2f}\n"
            report += f"Calmar Ratio: {perf.get('calmarRatio', 0):.2f}\n"
            report += f"Total Trades: {perf.get('totalTrades', 0)}\n"
            report += f"Win Rate: {perf.get('winRate', 0):.2%}\n"
            report += f"Profit Factor: {perf.get('profitFactor', 0):.2f}\n"
            report += f"Volatility: {perf.get('volatility', 0):.2%}\n"
            report += f"Beta: {perf.get('beta', 0):.2f}\n"
            report += "\n" + "="*50 + "\n\n"
        
        return report
    
    def plotResults(self, symbol: str):
        """Plot backtest results using plotly"""
        if symbol not in self.results:
            logger.info(f"No results found for {symbol}")
            return
        
        result = self.results[symbol]
        stockData = result['stockData']
        portfolioValues = result['portfolioValues']
        trades = result['trades']
        
        # Create subplots
        fig = make_subplots(
            rows=3, cols=1,
            subplot_titles=('Stock Price & Portfolio Value', 'Position Size', 'Cash Balance'),
            vertical_spacing=0.08,
            specs=[[{"secondary_y": True}], [{}], [{}]]
        )
        
        # Plot stock price
        fig.add_trace(
            go.Scatter(
                x=stockData.index,
                y=stockData['close'],
                name='Stock Price',
                line=dict(color='blue'),
                yaxis='y'
            ),
            row=1, col=1, secondary_y=False
        )
        
        # Plot portfolio value
        fig.add_trace(
            go.Scatter(
                x=stockData.index,
                y=portfolioValues,
                name='Portfolio Value',
                line=dict(color='red'),
                yaxis='y2'
            ),
            row=1, col=1, secondary_y=True
        )
        
        # Add trade markers
        buyTrades = [t for t in trades if t.side == 'buy']
        sellTrades = [t for t in trades if t.side == 'sell']
        
        if buyTrades:
            fig.add_trace(
                go.Scatter(
                    x=[t.timestamp for t in buyTrades],
                    y=[t.price for t in buyTrades],
                    mode='markers',
                    name='Buy Trades',
                    marker=dict(color='green', symbol='triangle-up', size=8),
                    yaxis='y'
                ),
                row=1, col=1, secondary_y=False
            )
        
        if sellTrades:
            fig.add_trace(
                go.Scatter(
                    x=[t.timestamp for t in sellTrades],
                    y=[t.price for t in sellTrades],
                    mode='markers',
                    name='Sell Trades',
                    marker=dict(color='orange', symbol='triangle-down', size=8),
                    yaxis='y'
                ),
                row=1, col=1, secondary_y=False
            )
        
        # Plot position size
        fig.add_trace(
            go.Scatter(
                x=stockData.index,
                y=result['positions'],
                name='Position Size',
                line=dict(color='purple'),
                fill='tonexty'
            ),
            row=2, col=1
        )
        
        # Plot cash balance
        fig.add_trace(
            go.Scatter(
                x=stockData.index,
                y=result['cashValues'],
                name='Cash Balance',
                line=dict(color='brown'),
                fill='tonexty'
            ),
            row=3, col=1
        )
        
        # Update layout
        fig.update_layout(
            title=f'Grid Trading Strategy Backtest Results - {symbol}',
            height=800,
            showlegend=True
        )
        
        # Set y-axes titles
        fig.update_yaxes(title_text="Stock Price (RMB)", secondary_y=False, row=1, col=1)
        fig.update_yaxes(title_text="Portfolio Value (RMB)", secondary_y=True, row=1, col=1)
        fig.update_yaxes(title_text="Shares", row=2, col=1)
        fig.update_yaxes(title_text="Cash (RMB)", row=3, col=1)
        
        fig.show()
    
    def exportResults(self, symbol: str, filename: str = None):
        """Export backtest results to Excel"""
        if symbol not in self.results:
            logger.info(f"No results found for {symbol}")
            return
        
        result = self.results[symbol]
        
        if filename is None:
            filename = f"backtest_results_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        with pd.ExcelWriter(filename) as writer:
            # Stock data
            result['stockData'].to_excel(writer, sheet_name='Stock_Data')
            
            # Trades
            if result['trades']:
                tradesDF = pd.DataFrame([
                    {
                        'timestamp': t.timestamp,
                        'price': t.price,
                        'quantity': t.quantity,
                        'side': t.side,
                        'commission': t.commission,
                        'slippage': t.slippage,
                        'pnl': t.pnl
                    }
                    for t in result['trades']
                ])
                tradesDF.to_excel(writer, sheet_name='Trades', index=False)
            
            # Performance metrics
            perfDF = pd.DataFrame([result['performance']]).T
            perfDF.columns = ['Value']
            perfDF.to_excel(writer, sheet_name='Performance')
            
            # Daily portfolio values
            portfolioDF = pd.DataFrame({
                'date': result['stockData'].index,
                'portfolio_value': result['portfolioValues'],
                'position': result['positions'],
                'cash': result['cashValues']
            })
            portfolioDF.to_excel(writer, sheet_name='Portfolio_Daily', index=False)
        
        logger.info(f"Results exported to {filename}") 