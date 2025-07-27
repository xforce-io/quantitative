import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from collections import deque
from quant.config.config import Config
import logging

@dataclass
class GridLevel:
    """Grid level data structure"""
    price: float
    quantity: int
    isFilled: bool = False
    orderId: Optional[str] = None

@dataclass
class Trade:
    """Trade record data structure"""
    timestamp: pd.Timestamp
    price: float
    quantity: int
    side: str  # 'buy', 'sell', 'buy_base'
    commission: float
    slippage: float
    pnl: float = 0.0

class UnifiedGridTradingStrategy:
    """
    Unified grid trading strategy with:
    1. Position ratio management (base position + grid trading)
    2. Dynamic grid center adjustment based on price movement
    """
    
    def __init__(self, symbol: str, config: Dict = None):
        """
        Initialize unified grid trading strategy
        
        Args:
            symbol (str): Stock symbol
            config (Dict): Strategy configuration
        """
        self.symbol = symbol
        self.config = config or Config.GRID_STRATEGY_CONFIG
        
        # Core strategy parameters
        self.gridLevels = self.config.get('gridLevels', 10)
        self.gridSpacing = self.config.get('gridSpacing', 0.02)  # 2% spacing
        self.maxPosition = self.config.get('maxPosition', 100000)
        self.baseRatio = self.config.get('baseRatio', 0.3)  # 30% for base position
        self.commission = self.config.get('commission', 0.0003)
        self.slippage = self.config.get('slippage', 0.001)
        
        # Dynamic grid adjustment parameters
        self.dynamicEnabled = self.config.get('dynamicEnabled', True)
        self.centerPricePeriod = self.config.get('centerPricePeriod', 20)  # Days for center calculation
        
        # 支持保守调整模式
        conservative_mode = self.config.get('conservativeAdjustment', False)
        if conservative_mode:
            # 保守模式：半年调整一次，更大的触发阈值和网格间距
            self.adjustmentThreshold = self.config.get('adjustmentThreshold', 0.15)  # 15% deviation triggers adjustment  
            self.minAdjustmentRatio = self.config.get('minAdjustmentRatio', 0.08)  # 8% minimum adjustment
            self.adjustmentCooldown = self.config.get('adjustmentCooldown', 180)  # 半年冷却期
            self.gridSpacing = max(self.gridSpacing, 0.035)  # 至少3.5%网格间距
            print(f"🔧 Conservative adjustment mode enabled: 半年调整周期, 15%触发阈值, 3.5%+网格间距")
        else:
            # 标准模式：保持原有参数但稍作优化
            self.adjustmentThreshold = self.config.get('adjustmentThreshold', 0.12)  # 12% deviation (was 10%)
            self.minAdjustmentRatio = self.config.get('minAdjustmentRatio', 0.06)  # 6% minimum adjustment (was 5%)
            self.adjustmentCooldown = self.config.get('adjustmentCooldown', 30)  # 30天冷却期 (was 7 days)
        
        self.centerPriceMethod = self.config.get('centerPriceMethod', 'sma')  # sma, ema, vwap
        
        # 日志配置选项 - 新增
        self.verboseLogging = self.config.get('verboseLogging', True)  # 详细日志
        self.compactLogging = self.config.get('compactLogging', False)  # 紧凑日志
        self.showGridAdjustDetails = self.config.get('showGridAdjustDetails', True)  # 显示网格调整详情
        self.showSafetyAlerts = self.config.get('showSafetyAlerts', True)  # 显示安全警告
        
        # Calculated values
        self.basePositionValue = self.maxPosition * self.baseRatio
        self.gridTradingValue = self.maxPosition * (1 - self.baseRatio)
        
        # Strategy state
        self.buyGrids: List[GridLevel] = []
        self.sellGrids: List[GridLevel] = []
        self.currentPosition = 0  # Total position including base
        self.basePosition = 0     # Base position for value investing
        self.gridPosition = 0     # Position from grid trading
        self.currentCash = 0
        self.totalValue = 0
        self.trades: List[Trade] = []
        
        # Dynamic grid state
        self.currentGridCenter = 0.0
        self.lastAdjustmentDate = None
        self.priceHistory = deque(maxlen=self.centerPricePeriod)
        self.volumeHistory = deque(maxlen=self.centerPricePeriod)
        self.basePositionEstablished = False
        
        # Grid adjustment tracking
        self.gridAdjustments = []
        # Portfolio value tracking for accurate performance calculation
        self.dailyPortfolioHistory = []
        self.lastUpdateDate = None
        
        # Initialize capital tracking for P&L calculation
        self.initialCapital = 0
        
        # Setup logging
        self.logger = logging.getLogger(f"{self.__class__.__name__}_{symbol}")
        
        # 计数器用于紧凑日志
        self.tradeCounter = 0
        self.adjustmentCounter = 0
        
        # 网格回收机制配置 - 行业标准解决方案
        self.enableGridRecycling = self.config.get('enableGridRecycling', True)  # 启用网格回收
        self.recyclingProfitThreshold = self.config.get('recyclingProfitThreshold', 0.005)  # 0.5%盈利触发回收
        self.maxFilledGridRatio = self.config.get('maxFilledGridRatio', 0.8)  # 80%网格被填充时触发回收
        self.recyclingCooldown = self.config.get('recyclingCooldown', 300)  # 5分钟回收冷却期（秒）
        self.lastRecyclingTime = None
        
        print(f"Unified grid strategy initialized for {self.symbol}")
        print(f"Total capital: ¥{self.maxPosition:,.0f} Base position ratio: {self.baseRatio:.1%} (¥{self.basePositionValue:,.0f}) Grid trading ratio: {1-self.baseRatio:.1%} (¥{self.gridTradingValue:,.0f}) Grid levels: {self.gridLevels}, Spacing: {self.gridSpacing:.1%}")
        print(f"Dynamic adjustment: {'Enabled' if self.dynamicEnabled else 'Disabled'}")
        if self.dynamicEnabled:
            print(f"  └─ Threshold: {self.adjustmentThreshold:.1%}, Min adjustment: {self.minAdjustmentRatio:.1%}")
            print(f"  └─ Period: {self.centerPricePeriod} days, Cooldown: {self.adjustmentCooldown} days, Method: {self.centerPriceMethod}")
        else:
            print(f"  └─ Static grid (no automatic adjustments)")
    
    def setupGrids(self, referencePrice: float, maxPrice: float = None, minPrice: float = None):
        """
        Setup grids based on price range with enhanced validation
        
        Args:
            referencePrice (float): Reference price for grid center
            maxPrice (float): Maximum expected price
            minPrice (float): Minimum expected price
        """
        if referencePrice <= 0:
            raise ValueError("Reference price must be positive")
        
        # Set grid center
        self.currentGridCenter = referencePrice
        
        # 修复：在网格设置时建立基础仓位，确保有持仓可以设置卖出网格
        if not self.basePositionEstablished:
            self._establishBasePosition(referencePrice)
        
        # Then setup grids around the center
        self._setupGridsAroundCenter(referencePrice)
        
        # Grid setup日志 - 支持紧凑和详细模式
        if self.compactLogging:
            print(f"📊 网格初始化: 中心¥{self.currentGridCenter:.1f} 基础仓{self.basePosition}股 买入档{len(self.buyGrids)}个 卖出档{len(self.sellGrids)}个")
        elif self.verboseLogging:
            print(f"📊 Grid setup: center: ¥{self.currentGridCenter:.2f} Base: {self.basePosition} shares (¥{self.basePosition * referencePrice:,.2f}) Grid position: {self.gridPosition} shares Total position: {self.currentPosition} shares Available cash: ¥{self.currentCash:,.2f}")
            print(f"Buy grids: {len(self.buyGrids)} levels, Sell grids: {len(self.sellGrids)} levels")
    
    def _establishBasePosition(self, currentPrice: float):
        """Establish base position for value investing approach"""
        if self.basePositionEstablished:
            return
        
        available_cash = self.currentCash
        
        # 计算基础仓位资金需求
        intended_base_value = self.maxPosition * self.baseRatio
        
        # 动态调整基础仓位比例以适应实际资金
        if intended_base_value > available_cash * 0.6:  # 如果超过60%现金
            # 使用40%现金建立基础仓位，保留60%用于网格交易
            actual_base_value = available_cash * 0.4
            if self.verboseLogging:
                print(f"🔧 Adjusting base position: config需要¥{intended_base_value:,.0f}, 实际使用¥{actual_base_value:,.0f}")
        else:
            actual_base_value = intended_base_value
        
        # 确保最少基础仓位：至少买入100股
        min_cost_for_100_shares = 100 * currentPrice * (1 + self.commission)
        if actual_base_value < min_cost_for_100_shares:
            actual_base_value = min(min_cost_for_100_shares, available_cash * 0.3)
        
        # 尝试建立基础仓位
        if actual_base_value > 0 and available_cash >= actual_base_value:
            shares = int(actual_base_value / currentPrice / 100) * 100  # Round to 100 shares
            shares = max(shares, 100)  # Minimum 100 shares
            
            actualCost = shares * currentPrice * (1 + self.commission)
            
            # 最终检查：确保有足够现金
            if available_cash >= actualCost:
                self.currentCash -= actualCost
                self.basePosition = shares
                self.currentPosition = self.basePosition
                self.basePositionEstablished = True
                
                # 重新计算网格交易资金分配
                remaining_cash = self.currentCash
                self.gridTradingValue = remaining_cash * 0.8  # 使用80%剩余现金进行网格交易
                
                # 基础仓位建立日志
                if self.compactLogging:
                    print(f"📈 建仓: {shares}股@¥{actualCost/shares:.1f} 余额¥{self.currentCash:,.0f} 网格资金¥{self.gridTradingValue:,.0f}")
                elif self.verboseLogging:
                    print(f"📈 Base position established:")
                    print(f"  Shares: {shares}, Cost: ¥{actualCost:,.2f}")
                    print(f"  Remaining cash: ¥{self.currentCash:,.2f}, Grid trading value: ¥{self.gridTradingValue:,.2f}")
                return
        
        # 如果无法建立基础仓位，至少标记为已尝试
        if self.verboseLogging:
            print(f"⚠️  Cannot establish base position: need ¥{actual_base_value:,.2f}, have ¥{available_cash:,.2f}")
        self.basePositionEstablished = True
    
    def _setupGridsAroundCenter(self, centerPrice: float):
        """Setup grids around the center price with enhanced safety checks"""
        self.buyGrids = []
        self.sellGrids = []
        
        # Setup buy grids (below center price) - Always setup if we have cash
        buyLevels = max(1, self.gridLevels // 2)
        for i in range(buyLevels):
            gridPrice = centerPrice * (1 - (i + 1) * self.gridSpacing)
            if gridPrice > 0:
                quantity = self._calculateGridQuantity(gridPrice)
                if quantity > 0:
                    self.buyGrids.append(GridLevel(price=gridPrice, quantity=quantity))
       
        # First layer: Check if any position exists
        if self.currentPosition <= 0:
            print(f"  ❌ No position available (position: {self.currentPosition}), skipping ALL sell grids")
            return
        
        # Second layer: Check minimum trading unit
        minRequiredShares = 100  # Minimum trading unit
        if self.currentPosition < minRequiredShares:
            print(f"  ❌ Insufficient position for trading unit (have: {self.currentPosition}, need: {minRequiredShares})")
            return
            
        # Third layer: Check grid quantity calculation
        testQuantity = self._calculateGridQuantity(centerPrice * 1.01)  # Test with slightly higher price
        if testQuantity > self.currentPosition:
            print(f"  ❌ Grid quantity ({testQuantity}) exceeds available position ({self.currentPosition})")
            print(f"  📊 Final grid setup: {len(self.buyGrids)} buy grids, 0 sell grids")
            return
        
        # ALL CHECKS PASSED: Setup sell grids
        sellLevels = max(1, self.gridLevels // 2)
        for i in range(sellLevels):
            gridPrice = centerPrice * (1 + (i + 1) * self.gridSpacing)
            quantity = self._calculateGridQuantity(gridPrice)
            # ADDITIONAL SAFETY: Don't create sell grid larger than available position
            quantity = min(quantity, self.currentPosition)
            quantity = max(int(quantity / 100) * 100, 100)  # Ensure 100 shares multiple
            
            # Final check before adding to sell grids
            if quantity > 0 and quantity <= self.currentPosition:
                self.sellGrids.append(GridLevel(price=gridPrice, quantity=quantity))
            else:
                print(f"    ⚠️  Skipping sell grid level {i+1}: quantity {quantity} invalid for position {self.currentPosition}")
                
        # Final grid setup日志 - 支持紧凑和详细模式
        if self.compactLogging:
            buy_range = f"买入¥{self.buyGrids[-1].price:.1f}-¥{self.buyGrids[0].price:.1f}" if self.buyGrids else "无买入档"
            sell_range = f"卖出¥{self.sellGrids[0].price:.1f}-¥{self.sellGrids[-1].price:.1f}" if self.sellGrids else "无卖出档"
            print(f"最终网格=> 买入{len(self.buyGrids)}档 卖出{len(self.sellGrids)}档")
            print(f"  {buy_range} {sell_range}")
        elif self.verboseLogging:
            print(f"Final grid setup=> Buy: {len(self.buyGrids)} Sell: {len(self.sellGrids)}")
            if self.buyGrids:
                print(f"  Buy range: ¥{self.buyGrids[-1].price:.2f} - ¥{self.buyGrids[0].price:.2f}", end=" ")
            if self.sellGrids:
                print(f"Sell range: ¥{self.sellGrids[0].price:.2f} - ¥{self.sellGrids[-1].price:.2f}")
            else:
                print(f"  ⚠️  NO SELL GRIDS SET (this is expected if no position)")
    
    def _calculateGridQuantity(self, price: float) -> int:
        """Calculate quantity for each grid level using grid trading allocation - ensure 100 shares minimum trading unit"""
        if self.gridLevels <= 0 or price <= 0:
            return 100
            
        tradeAmount = self.gridTradingValue / self.gridLevels
        # Round down to nearest 100 shares (1 hand = 100 shares in Chinese stock market)
        quantity = int(tradeAmount / price / 100) * 100
        return max(quantity, 100)  # Minimum 100 shares (1 hand)
    
    def onMarketData(self, timestamp: pd.Timestamp, price: float, volume: float = 0):
        """Process new market data and execute grid trading logic"""
        # Update price and volume history
        self.priceHistory.append(price)
        if volume > 0:
            self.volumeHistory.append(volume)
            
        # Initialize grids on first data point
        if not self.buyGrids and not self.sellGrids:
            self.setupGrids(price)
            self._record_initial_grid_state(timestamp, price)
            
        # Process grid trades
        self._processGridTrades(timestamp, price)
        
        # Check for grid recycling (行业标准解决方案)
        if self._shouldRecycleGrids(timestamp, price):
            self._recycleGrids(timestamp, price)
        
        # Check for dynamic grid adjustment if enabled
        if self.dynamicEnabled and self._shouldAdjustGrid(timestamp, price):
            self._adjustGrid(timestamp, price)
        
        # Update portfolio value for tracking
        self.updatePortfolioValue(price)
        
        # Record daily portfolio history for performance calculation
        current_date = timestamp.date()
        if self.lastUpdateDate != current_date:
            portfolio_value = self.currentCash + self.currentPosition * price
            self.dailyPortfolioHistory.append({
                'date': current_date,
                'portfolio_value': portfolio_value,
                'price': price
            })
            self.lastUpdateDate = current_date
    
    def _shouldAdjustGrid(self, timestamp: pd.Timestamp, currentPrice: float) -> bool:
        """Check if grid should be adjusted based on strategy parameters"""
        if not self.dynamicEnabled:
            return False
        
        # Need enough price history for reliable center calculation
        required_history = max(self.centerPricePeriod, 30)  # 至少30天历史数据
        if len(self.priceHistory) < required_history:
            return False
        
        # Check cooldown period to avoid frequent adjustments
        if (self.lastAdjustmentDate and 
            (timestamp - self.lastAdjustmentDate).days < self.adjustmentCooldown):
            return False
        
        # Calculate current price deviation from grid center
        currentDeviation = abs(currentPrice - self.currentGridCenter) / self.currentGridCenter
        
        # 使用配置的触发阈值，不再硬编码
        effective_threshold = self.adjustmentThreshold
        
        # Only trigger adjustment if deviation exceeds threshold
        if currentDeviation < effective_threshold:
            return False
        
        # Calculate potential new center price
        newCenter = self._calculateNewCenterPrice()
        
        # Check if the adjustment would be significant enough to justify the cost
        adjustmentMagnitude = abs(newCenter - self.currentGridCenter) / self.currentGridCenter
        
        # 使用配置的最小调整比例
        effective_min_ratio = self.minAdjustmentRatio
        
        should_adjust = adjustmentMagnitude >= effective_min_ratio
        
        if should_adjust and self.verboseLogging:
            print(f"🔄 Grid adjustment criteria met => Price deviation: {currentDeviation:.2%} > threshold {effective_threshold:.2%}, Adjustment magnitude: {adjustmentMagnitude:.2%} > min ratio {effective_min_ratio:.2%}")
        
        return should_adjust
    
    def _calculateNewCenterPrice(self) -> float:
        """Calculate new center price based on recent market data"""
        if len(self.priceHistory) == 0:
            return self.currentGridCenter
        
        prices = list(self.priceHistory)
        volumes = list(self.volumeHistory)
        
        if self.centerPriceMethod == 'sma':
            # Simple Moving Average
            return np.mean(prices)
        
        elif self.centerPriceMethod == 'ema':
            # Exponential Moving Average
            alpha = 2.0 / (len(prices) + 1)
            ema = prices[0]
            for price in prices[1:]:
                ema = alpha * price + (1 - alpha) * ema
            return ema
        
        elif self.centerPriceMethod == 'vwap':
            # Volume Weighted Average Price
            if all(v > 0 for v in volumes):
                return np.average(prices, weights=volumes)
            else:
                return np.mean(prices)  # Fall back to SMA if no volume data
        
        else:
            return np.mean(prices)  # Default to SMA
    
    def _adjustGrid(self, timestamp: pd.Timestamp, currentPrice: float):
        """Adjust grid center and recreate grids with enhanced safety validation"""
        oldCenter = self.currentGridCenter
        newCenter = self._calculateNewCenterPrice()
        
        # Calculate metrics for logging
        currentDeviation = abs(currentPrice - oldCenter) / oldCenter
        adjustmentMagnitude = abs(newCenter - oldCenter) / oldCenter
        
        self.adjustmentCounter += 1
        
        # 紧凑日志模式
        if self.compactLogging:
            print(f"🔄 调整#{self.adjustmentCounter} [{timestamp.strftime('%m-%d')}] "
                  f"价格¥{currentPrice:.1f} 偏离{currentDeviation:.1%} → 中心¥{oldCenter:.1f}→¥{newCenter:.1f}")
        # 详细日志模式（默认）
        elif self.verboseLogging and self.showGridAdjustDetails:
            print(f"🔄 Grid adjustment: Current: ¥{currentPrice:.2f} (deviation: {currentDeviation:.2%}) Old: ¥{oldCenter:.2f} New: ¥{newCenter:.2f} Adjustment: {adjustmentMagnitude:.2%}")
            print(f"  Current: {self.currentPosition} shares (base: {self.basePosition}, grid: {self.gridPosition}) Cooldown until: {(timestamp + pd.Timedelta(days=self.adjustmentCooldown)).strftime('%Y-%m-%d')}")
        
        # SAFETY CHECK: Validate current position state before adjustment
        if self.currentPosition < 0:
            if self.showSafetyAlerts:
                print(f"🚨 ERROR: Invalid position state before adjustment: {self.currentPosition}. Correcting.")
            self.currentPosition = max(0, self.basePosition)
            self.gridPosition = self.currentPosition - self.basePosition

        # 保存旧网格信息用于记录
        old_buy_grids = [{'price': g.price, 'quantity': g.quantity, 'filled': g.isFilled} for g in self.buyGrids]
        old_sell_grids = [{'price': g.price, 'quantity': g.quantity, 'filled': g.isFilled} for g in self.sellGrids]
        
        # Clear existing unfilled grids
        self._clearUnfilledGrids()
        
        # Setup new grids around new center with current position state
        self._setupGridsAroundCenter(newCenter)
        
        # 获取新网格信息用于记录
        new_buy_grids = [{'price': g.price, 'quantity': g.quantity, 'filled': g.isFilled} for g in self.buyGrids]
        new_sell_grids = [{'price': g.price, 'quantity': g.quantity, 'filled': g.isFilled} for g in self.sellGrids]
        
        # Record adjustment with detailed grid information
        adjustment = {
            'timestamp': timestamp,
            'old_center': oldCenter,
            'new_center': newCenter,
            'current_price': currentPrice,
            'deviation': adjustmentMagnitude,
            'trigger_reason': f'price_deviation_{currentDeviation:.1%}',
            'position_at_adjustment': self.currentPosition,
            'grid_info': {
                'old_grids': {
                    'buy_levels': [g['price'] for g in old_buy_grids if not g['filled']],
                    'sell_levels': [g['price'] for g in old_sell_grids if not g['filled']],
                    'buy_count': len(old_buy_grids),
                    'sell_count': len(old_sell_grids)
                },
                'new_grids': {
                    'buy_levels': [g['price'] for g in new_buy_grids],
                    'sell_levels': [g['price'] for g in new_sell_grids], 
                    'buy_count': len(new_buy_grids),
                    'sell_count': len(new_sell_grids)
                }
            }
        }
        self.gridAdjustments.append(adjustment)
        
        # Update grid center
        self.currentGridCenter = newCenter
        self.lastAdjustmentDate = timestamp
        
    def _record_initial_grid_state(self, timestamp: pd.Timestamp, center_price: float):
        """Records the initial grid state as a pseudo-adjustment for historical accuracy."""
        initial_buy_grids = [{'price': g.price, 'quantity': g.quantity, 'filled': g.isFilled} for g in self.buyGrids]
        initial_sell_grids = [{'price': g.price, 'quantity': g.quantity, 'filled': g.isFilled} for g in self.sellGrids]

        initial_state = {
            'timestamp': timestamp,
            'old_center': 0,
            'new_center': center_price,
            'current_price': center_price,
            'deviation': 0,
            'trigger_reason': 'initial_setup',
            'position_at_adjustment': self.currentPosition,
            'grid_info': {
                'old_grids': {},
                'new_grids': {
                    'buy_levels': [g['price'] for g in initial_buy_grids],
                    'sell_levels': [g['price'] for g in initial_sell_grids],
                    'buy_count': len(initial_buy_grids),
                    'sell_count': len(initial_sell_grids)
                }
            }
        }
        self.gridAdjustments.append(initial_state)
        self.logger.info(f"Initial grid state recorded at center price ¥{center_price:.2f}")

    def _clearUnfilledGrids(self):
        """Clear unfilled grids before adjustment - crucial to maintain position consistency"""
        # Only clear grids that haven't been filled (not executed)
        # Clear the grids list completely - we'll create new ones in setupGrids
        self.buyGrids.clear()
        self.sellGrids.clear()
    
    def _processGridTrades(self, timestamp: pd.Timestamp, price: float):
        """Process grid trading logic"""
        # Check buy grid triggers
        for grid in self.buyGrids:
            if not grid.isFilled and price <= grid.price:
                self._executeBuyOrder(timestamp, grid)
        
        # Check sell grid triggers
        for grid in self.sellGrids:
            if not grid.isFilled and price >= grid.price:
                self._executeSellOrder(timestamp, grid)
    
    def _executeBuyOrder(self, timestamp: pd.Timestamp, grid: GridLevel):
        """Execute buy order when grid level is triggered - ensure 100 shares minimum trading unit"""
        if grid.quantity <= 0 or grid.price <= 0:
            print(f"Warning: Invalid grid parameters - quantity: {grid.quantity}, price: {grid.price}")
            return
        
        # Ensure quantity is multiple of 100 shares
        if grid.quantity % 100 != 0:
            print(f"Warning: Adjusting buy quantity from {grid.quantity} to {int(grid.quantity / 100) * 100} shares (100x multiple)")
            grid.quantity = max(int(grid.quantity / 100) * 100, 100)
        
        # Apply slippage
        executionPrice = grid.price * (1 + self.slippage)
        
        # Calculate trade cost
        tradeValue = executionPrice * grid.quantity
        commissionCost = tradeValue * self.commission
        totalCost = tradeValue + commissionCost
        
        # Check if we have enough cash
        if self.currentCash >= totalCost:
            # Execute trade
            self.currentCash -= totalCost
            self.gridPosition += grid.quantity
            self.currentPosition = self.basePosition + self.gridPosition
            grid.isFilled = True
            
            # Record trade
            trade = Trade(
                timestamp=timestamp,
                price=executionPrice,
                quantity=grid.quantity,
                side='buy',
                commission=commissionCost,
                slippage=executionPrice - grid.price
            )
            self.trades.append(trade)
            
            # Update portfolio value for accurate logging
            positionValue = self.currentPosition * executionPrice
            totalValue = self.currentCash + positionValue
            totalPnL = totalValue - self.initialCapital
            totalReturn = (totalPnL / self.initialCapital * 100) if hasattr(self, 'initialCapital') and self.initialCapital > 0 else 0
            
            self.tradeCounter += 1
            
            # 紧凑日志模式
            if self.compactLogging:
                print(f"📈 买#{self.tradeCounter} [{timestamp.strftime('%m-%d')}] {grid.quantity}股@¥{executionPrice:.1f} "
                      f"总仓{self.currentPosition} 盈亏¥{totalPnL:,.0f}({totalReturn:+.1f}%)")
            # 详细日志模式
            elif self.verboseLogging:
                print(f"[{timestamp.strftime('%Y-%m-%d')}] Grid buy: {grid.quantity} shares at ¥{executionPrice:.2f} | "
                      f"Grid: {self.gridPosition} | Total: {self.currentPosition} | "
                      f"Cash: ¥{self.currentCash:,.0f} | Value: ¥{positionValue:,.0f} | "
                      f"Total: ¥{totalValue:,.0f} | P&L: ¥{totalPnL:,.0f} ({totalReturn:+.2f}%)")
            
            # Reset corresponding sell grid
            self._resetSellGrid(grid.price)
        else:
            # 现金不足，记录日志以便诊断
            if self.showSafetyAlerts:
                if self.compactLogging:
                    print(f"💰 现金不足: 需要¥{totalCost:,.0f}, 可用¥{self.currentCash:,.0f}, 差额¥{totalCost-self.currentCash:,.0f}")
                elif self.verboseLogging:
                    print(f"💰 [CASH INSUFFICIENT] Cannot buy {grid.quantity} shares at ¥{executionPrice:.2f}")
                    print(f"   Required: ¥{totalCost:,.2f} (trade: ¥{tradeValue:.2f} + commission: ¥{commissionCost:.2f})")
                    print(f"   Available: ¥{self.currentCash:,.2f}")
                    print(f"   Shortfall: ¥{totalCost - self.currentCash:,.2f}")
            grid.isFilled = True  # Mark as filled to prevent repeated attempts
    
    def _executeSellOrder(self, timestamp: pd.Timestamp, grid: GridLevel):
        """Execute sell order when grid level is triggered - ensure proper position deduction logic"""
        if grid.quantity <= 0 or grid.price <= 0:
            print(f"Warning: Invalid grid parameters - quantity: {grid.quantity}, price: {grid.price}")
            return
        
        # Ensure quantity is multiple of 100 shares
        if grid.quantity % 100 != 0:
            print(f"Warning: Adjusting sell quantity from {grid.quantity} to {int(grid.quantity / 100) * 100} shares (100x multiple)")
            grid.quantity = max(int(grid.quantity / 100) * 100, 100)
        
        # ENHANCED SAFETY CHECK: Multiple layers of position validation
        if self.currentPosition <= 0:
            if self.showSafetyAlerts:
                if self.compactLogging:
                    print(f"❌ 无仓位拒绝卖出")
                else:
                    print(f"🚨 CRITICAL SAFETY: No position available for selling. Current position: {self.currentPosition}. Trade REJECTED.")
            grid.isFilled = True
            return
            
        # SAFETY CHECK: Ensure we don't sell more than we have
        if self.currentPosition < grid.quantity:
            if self.showSafetyAlerts:
                if self.compactLogging:
                    print(f"❌ 仓位不足: 需要{grid.quantity}, 持有{self.currentPosition}")
                else:
                    print(f"🚨 CRITICAL SAFETY: Insufficient position for sell. Need {grid.quantity}, have {self.currentPosition}. Trade REJECTED.")
            grid.isFilled = True
            return
            
        # Apply slippage
        executionPrice = grid.price * (1 - self.slippage)
        
        # Calculate trade proceeds
        tradeValue = executionPrice * grid.quantity
        commissionCost = tradeValue * self.commission
        netProceeds = tradeValue - commissionCost
        
        # Calculate P&L before executing (for safety)
        pnl = self._calculateTradePnL('sell', executionPrice, grid.quantity)
        
        remainingToSell = grid.quantity
        
        # Layer 1: Deduct from gridPosition first (FIFO for grid trades)
        if self.gridPosition > 0 and remainingToSell > 0:
            gridSellQuantity = min(self.gridPosition, remainingToSell)
            self.gridPosition -= gridSellQuantity
            remainingToSell -= gridSellQuantity
        
        # Layer 2: Deduct from basePosition if needed  
        if self.basePosition > 0 and remainingToSell > 0:
            baseSellQuantity = min(self.basePosition, remainingToSell)
            self.basePosition -= baseSellQuantity
            remainingToSell -= baseSellQuantity
        
        # Update total position (should equal basePosition + gridPosition)
        self.currentPosition = self.basePosition + self.gridPosition
        
        # SAFETY VALIDATION: Ensure no negative positions
        if self.gridPosition < 0:
            print(f"🚨 CRITICAL ERROR: Grid position went negative: {self.gridPosition}. This should never happen!")
            self.gridPosition = 0
            
        if self.basePosition < 0:
            print(f"🚨 CRITICAL ERROR: Base position went negative: {self.basePosition}. This should never happen!")
            self.basePosition = 0
            
        if remainingToSell > 0:
            print(f"🚨 CRITICAL ERROR: Could not sell all shares! Remaining: {remainingToSell}")
            # This should never happen if our checks above are correct
            
        # Final position consistency check
        calculatedPosition = self.basePosition + self.gridPosition
        if calculatedPosition != self.currentPosition:
            print(f"🚨 POSITION MISMATCH: calculated={calculatedPosition}, stored={self.currentPosition}. Correcting.")
            self.currentPosition = calculatedPosition

        # Execute trade (update cash)
        self.currentCash += netProceeds
        grid.isFilled = True
        
        # Record trade
        trade = Trade(
            timestamp=timestamp,
            price=executionPrice,
            quantity=grid.quantity,
            side='sell',
            commission=commissionCost,
            slippage=grid.price - executionPrice,
            pnl=pnl
        )
        self.trades.append(trade)

        # Update portfolio value for accurate logging
        positionValue = self.currentPosition * executionPrice
        totalValue = self.currentCash + positionValue
        totalPnL = totalValue - self.initialCapital
        totalReturn = (totalPnL / self.initialCapital * 100) if hasattr(self, 'initialCapital') and self.initialCapital > 0 else 0
        
        self.tradeCounter += 1
        
        # 紧凑日志模式
        if self.compactLogging:
            print(f"📉 卖#{self.tradeCounter} [{timestamp.strftime('%m-%d')}] {grid.quantity}股@¥{executionPrice:.1f} "
                  f"单笔¥{pnl:+.0f} 总仓{self.currentPosition} 盈亏¥{totalPnL:,.0f}({totalReturn:+.1f}%)")
        # 详细日志模式
        elif self.verboseLogging:
            print(f"[{timestamp.strftime('%Y-%m-%d')}] Grid sell: {grid.quantity} shares at ¥{executionPrice:.2f}, P&L: ¥{pnl:.2f} | "
                  f"Grid: {self.gridPosition} | Total: {self.currentPosition} | "
                  f"Cash: ¥{self.currentCash:,.0f} | Value: ¥{positionValue:,.0f} | "
                  f"Total: ¥{totalValue:,.0f} | P&L: ¥{totalPnL:,.0f} ({totalReturn:+.2f}%)")
        
        # Reset corresponding buy grid
        self._resetBuyGrid(grid.price)
    
    def _resetSellGrid(self, buyPrice: float):
        """Reset sell grid after buy execution"""
        targetSellPrice = buyPrice * (1 + self.gridSpacing)
        for grid in self.sellGrids:
            if abs(grid.price - targetSellPrice) / targetSellPrice < 0.01:  # 1% tolerance
                grid.isFilled = False
                break
    
    def _resetBuyGrid(self, sellPrice: float):
        """Reset buy grid after sell execution"""
        targetBuyPrice = sellPrice * (1 - self.gridSpacing)
        for grid in self.buyGrids:
            if abs(grid.price - targetBuyPrice) / targetBuyPrice < 0.01:  # 1% tolerance
                grid.isFilled = False
                break
    
    def _calculateTradePnL(self, side: str, price: float, quantity: int) -> float:
        """Calculate P&L for a trade (simplified FIFO method) - Enhanced version with detailed safety checks"""
        if side == 'sell':
            # CRITICAL FIX: For abnormal sell (without sufficient position), P&L should be 0
            if self.currentPosition <= 0:
                print(f"🚨 WARNING: Abnormal sell detected (no position). Current position: {self.currentPosition}. P&L set to 0.")
                return 0.0
                
            # ADDITIONAL CHECK: If selling more than we have, this is an error
            if quantity > self.currentPosition:
                print(f"🚨 WARNING: Selling more than available position. Selling {quantity}, have {self.currentPosition}. P&L set to 0.")
                return 0.0
                
            # Find corresponding buy trades (LIFO - Last In First Out for tax efficiency)
            remainingQuantity = quantity
            totalPnL = 0.0
            matchedTrades = 0
            
            # Search for matching buy trades (newest to oldest to follow LIFO)
            for trade in reversed(self.trades):
                # 修复：确保匹配所有买入类型的交易
                if trade.side in ['buy', 'buy_base'] and remainingQuantity > 0:
                    matchedQuantity = min(remainingQuantity, trade.quantity)
                    tradePnL = (price - trade.price) * matchedQuantity
                    totalPnL += tradePnL
                    remainingQuantity -= matchedQuantity
                    matchedTrades += 1
                    
                    if self.verboseLogging and not self.compactLogging:
                        print(f"🔄 P&L Match: Sell {matchedQuantity} @ ¥{price:.2f} vs Buy @ ¥{trade.price:.2f} = ¥{tradePnL:.2f}")
                    
                    if remainingQuantity == 0:
                        break
            
            # 修复：如果没有找到匹配的买入交易，使用平均成本计算
            if matchedTrades == 0 and len(self.trades) > 0:
                if self.verboseLogging and not self.compactLogging:
                    print(f"🔄 No exact buy match found. Using average cost method.")
                # 计算所有买入交易的平均成本
                buyTrades = [t for t in self.trades if t.side in ['buy', 'buy_base']]
                if buyTrades:
                    totalBuyValue = sum(t.price * t.quantity for t in buyTrades)
                    totalBuyQuantity = sum(t.quantity for t in buyTrades)
                    avgBuyPrice = totalBuyValue / totalBuyQuantity if totalBuyQuantity > 0 else price
                    totalPnL = (price - avgBuyPrice) * quantity
                    if self.verboseLogging and not self.compactLogging:
                        print(f"🔄 Average cost P&L: Sell {quantity} @ ¥{price:.2f} vs Avg ¥{avgBuyPrice:.2f} = ¥{totalPnL:.2f}")
                else:
                    if self.showSafetyAlerts:
                        print(f"🚨 WARNING: No buy trades found for P&L calculation. P&L set to 0.")
                    return 0.0
            
            # INFORMATIONAL: If partial matching (shouldn't happen in normal operation)
            if remainingQuantity > 0:
                print(f"⚠️  INFO: Partial trade matching. Unmatched quantity: {remainingQuantity} shares.")
                
            return totalPnL
        
        return 0.0
    
    def updatePortfolioValue(self, currentPrice: float):
        """Update total portfolio value with history tracking"""
        positionValue = self.currentPosition * currentPrice
        self.totalValue = self.currentCash + positionValue
        
        # Track daily portfolio values for performance calculation
        self.dailyPortfolioHistory.append(self.totalValue)
        
        # Keep only recent history to avoid memory issues
        if len(self.dailyPortfolioHistory) > 1000:
            self.dailyPortfolioHistory = self.dailyPortfolioHistory[-500:]
    
    def getPerformanceMetrics(self, initialCapital: float) -> Dict:
        """Calculate strategy performance metrics"""
        if not self.trades or self.totalValue <= 0:
            return {
                'totalReturn': 0.0,
                'totalTrades': 0,
                'winRate': 0.0,
                'avgProfitPerTrade': 0.0,
                'maxDrawdown': 0.0,
                'sharpeRatio': 0.0,
                'gridAdjustments': len(self.gridAdjustments)
            }
        
        # Calculate total return
        totalReturn = (self.totalValue - initialCapital) / initialCapital
        
        # Calculate trade statistics
        profitTrades = [t for t in self.trades if t.pnl > 0]
        lossTrades = [t for t in self.trades if t.pnl < 0]
        
        tradesWithPnl = [t for t in self.trades if t.pnl != 0]
        totalProfit = sum(t.pnl for t in tradesWithPnl)
        avgProfitPerTrade = totalProfit / len(tradesWithPnl) if tradesWithPnl else 0
        
        winRate = len(profitTrades) / len(tradesWithPnl) if tradesWithPnl else 0
        
        # CRITICAL FIX: Calculate missing performance metrics
        
        # Calculate daily returns for advanced metrics
        dailyReturns = []
        portfolioValues = []
        if hasattr(self, 'dailyPortfolioHistory') and self.dailyPortfolioHistory:
            # Extract numeric values if history contains dictionaries
            for item in self.dailyPortfolioHistory:
                if isinstance(item, dict):
                    portfolioValues.append(item.get('total_value', item.get('portfolio_value', self.totalValue)))
                else:
                    portfolioValues.append(float(item))
        else:
            # Estimate daily values from trades if no daily history
            if self.trades:
                currentValue = initialCapital
                for trade in self.trades:
                    if trade.side == 'buy':
                        currentValue -= trade.price * trade.quantity * (1 + self.commission)
                    else:
                        currentValue += trade.price * trade.quantity * (1 - self.commission)
                    portfolioValues.append(currentValue)
            else:
                portfolioValues = [initialCapital, self.totalValue]
        
        # Calculate returns
        if len(portfolioValues) >= 2:
            returns = [(portfolioValues[i] - portfolioValues[i-1]) / portfolioValues[i-1] 
                      for i in range(1, len(portfolioValues)) if portfolioValues[i-1] > 0]
            dailyReturns = [r for r in returns if not (r > 10 or r < -0.9)]  # Filter extreme outliers
        
        # Calculate Sharpe ratio
        sharpeRatio = 0.0
        if len(dailyReturns) >= 2:
            import numpy as np
            meanReturn = np.mean(dailyReturns)
            stdReturn = np.std(dailyReturns)
            if stdReturn > 0 and not np.isnan(stdReturn) and not np.isinf(stdReturn):
                sharpeRatio = meanReturn / stdReturn * np.sqrt(252)  # Annualized
                # Cap extreme Sharpe ratios
                sharpeRatio = max(-10, min(10, sharpeRatio))
        
        # Calculate maximum drawdown
        maxDrawdown = 0.0
        if len(portfolioValues) >= 2:
            import numpy as np
            peak = portfolioValues[0]
            for value in portfolioValues[1:]:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak if peak > 0 else 0
                maxDrawdown = min(maxDrawdown, -drawdown)
        
        # Calculate volatility
        volatility = 0.0
        if len(dailyReturns) >= 2:
            import numpy as np
            volatility = np.std(dailyReturns) * np.sqrt(252)  # Annualized
            volatility = max(0, min(5, volatility))  # Cap at 500%
        
        # SAFETY CHECK: Validate total return
        if abs(totalReturn) > 50:  # More than 5000% gain/loss
            print(f"🚨 WARNING: Extreme total return detected: {totalReturn:.2%}")
            print(f"   Initial capital: ¥{initialCapital:,.2f}")
            print(f"   Final value: ¥{self.totalValue:,.2f}")
            print(f"   This may indicate a calculation error.")
            # Cap extreme returns
            totalReturn = max(-0.99, min(10.0, totalReturn))
        
        return {
            'totalReturn': totalReturn,
            'annualizedReturn': (1 + totalReturn) ** (252 / max(len(portfolioValues), 1)) - 1 if totalReturn > -0.99 else totalReturn,
            'sharpeRatio': sharpeRatio,
            'maxDrawdown': maxDrawdown,
            'volatility': volatility,
            'totalTrades': len(self.trades),
            'profitableTrades': len(profitTrades),
            'losingTrades': len(lossTrades),
            'winRate': winRate,
            'totalProfit': totalProfit,
            'avgProfitPerTrade': avgProfitPerTrade,
            'profitLossRatio': (sum(t.pnl for t in profitTrades) / abs(sum(t.pnl for t in lossTrades))) if lossTrades else float('inf'),
            'alpha': 0.0,  # Placeholder
            'beta': 1.0,   # Placeholder
            'basePosition': self.basePosition,
            'gridPosition': self.gridPosition,
            'currentPosition': self.currentPosition,
            'currentCash': self.currentCash,
            'totalValue': self.totalValue,
            'gridAdjustments': len(self.gridAdjustments),
            'currentGridCenter': self.currentGridCenter
        }
    
    def getGridStatus(self) -> Dict:
        """Get current grid status"""
        return {
            'grid_center': self.currentGridCenter,
            'buy_grids': [{'price': g.price, 'quantity': g.quantity, 'filled': g.isFilled} 
                         for g in self.buyGrids],
            'sell_grids': [{'price': g.price, 'quantity': g.quantity, 'filled': g.isFilled} 
                          for g in self.sellGrids],
            'total_buy_grids': len(self.buyGrids),
            'total_sell_grids': len(self.sellGrids),
            'filled_buy_grids': sum(1 for g in self.buyGrids if g.isFilled),
            'filled_sell_grids': sum(1 for g in self.sellGrids if g.isFilled),
            'last_adjustment': self.lastAdjustmentDate,
            'adjustments_count': len(self.gridAdjustments)
        }
    
    def reset(self, initialCapital: float):
        """Reset strategy state"""
        self.currentPosition = 0
        self.basePosition = 0
        self.gridPosition = 0
        self.currentCash = initialCapital
        self.totalValue = initialCapital
        self.initialCapital = initialCapital  # Record initial capital for P&L calculation
        self.trades = []
        self.buyGrids = []
        self.sellGrids = []
        self.basePositionEstablished = False
        self.currentGridCenter = 0.0
        self.lastAdjustmentDate = None
        self.priceHistory.clear()
        self.volumeHistory.clear()
        self.gridAdjustments = []
        # Portfolio value tracking for accurate performance calculation
        self.dailyPortfolioHistory = []
        self.lastUpdateDate = None
        
        print(f"Strategy reset with initial capital: ¥{initialCapital:,.2f}") 
    
    def run(self, data: pd.DataFrame, initialCapital: float) -> Dict:
        """Main backtest execution logic"""
        self.reset(initialCapital)
        
        # Initial grid setup
        if not data.empty:
            initial_center_price = self._calculateInitialCenterPrice(data['close'])
            # 修复：使用setupGrids方法，它会自动建立基础仓位并设置网格
            self.setupGrids(initial_center_price)
            self.lastAdjustmentDate = data.index[0]
            # Record initial grid state for historical tracking
            self._record_initial_grid_state(self.lastAdjustmentDate, initial_center_price)

        # Main backtest loop
        for timestamp, row in data.iterrows():
            current_price = row['close']
            volume = row.get('volume', 0)
            self.onMarketData(timestamp, current_price, volume)
        
        # Update final portfolio value
        if not data.empty:
            self.updatePortfolioValue(data['close'].iloc[-1])
        
        return {
            'trades': self.trades,
            'portfolio_values': self.dailyPortfolioHistory,
            'performance': self.getPerformanceMetrics(initialCapital),
            'grid_adjustments': self.gridAdjustments
        }

    def _shouldRecycleGrids(self, timestamp: pd.Timestamp, currentPrice: float) -> bool:
        """
        检查是否应该回收网格 - 修复版本，只在有实际意义时触发
        
        Args:
            timestamp: 当前时间戳
            currentPrice: 当前价格
            
        Returns:
            bool: 是否应该回收网格
        """
        if not self.enableGridRecycling:
            return False
            
        # 重要：只有当存在卖出网格时，回收才有意义
        if len(self.sellGrids) == 0:
            return False
            
        # 检查冷却期
        if self.lastRecyclingTime:
            time_diff = (timestamp - self.lastRecyclingTime).total_seconds()
            if time_diff < self.recyclingCooldown:
                return False
        
        # 条件1：网格填充率检查 - 必须有足够多的网格被填充
        filled_buy_grids = sum(1 for grid in self.buyGrids if grid.isFilled)
        filled_sell_grids = sum(1 for grid in self.sellGrids if grid.isFilled)
        total_grids = len(self.buyGrids) + len(self.sellGrids)
        
        if total_grids > 0:
            filled_ratio = (filled_buy_grids + filled_sell_grids) / total_grids
            # 提高触发阈值，避免过度频繁的回收
            if filled_ratio >= self.maxFilledGridRatio:  # 至少60%网格被填充
                # 额外检查：确保至少有一些盈利交易
                if len(self.trades) >= 2:  # 至少有一些交易历史
                    recent_trades = self.trades[-5:] if len(self.trades) >= 5 else self.trades
                    profitable_trades = [t for t in recent_trades if t.pnl > 0]
                    if len(profitable_trades) > 0:  # 有盈利交易才回收
                        return True
        
        # 条件2：显著盈利水平检查 - 提高阈值避免微小盈利时回收
        total_value = self.currentCash + self.currentPosition * currentPrice
        if hasattr(self, 'initialCapital') and self.initialCapital > 0:
            profit_ratio = (total_value - self.initialCapital) / self.initialCapital
            # 提高盈利阈值，从0.5%提高到2%
            if profit_ratio >= max(self.recyclingProfitThreshold, 0.02):
                # 同样需要有交易历史
                if len(self.trades) >= 3:
                    return True
        
        return False
    
    def _recycleGrids(self, timestamp: pd.Timestamp, currentPrice: float):
        """
        执行网格回收 - 行业标准解决方案
        
        Args:
            timestamp: 当前时间戳
            currentPrice: 当前价格
        """
        if self.compactLogging:
            print(f"♻️ 网格回收 [{timestamp.strftime('%m-%d %H:%M')}] 价格¥{currentPrice:.1f}")
        elif self.verboseLogging:
            print(f"♻️ Grid recycling triggered at price ¥{currentPrice:.2f}")
            print(f"   Filled grids: {sum(1 for g in self.buyGrids + self.sellGrids if g.isFilled)}/{len(self.buyGrids) + len(self.sellGrids)}")
        
        # 只重置已填充的网格，保持未填充的网格继续工作
        for grid in self.buyGrids:
            if grid.isFilled and abs(currentPrice - grid.price) / currentPrice < self.gridSpacing * 2:
                grid.isFilled = False  # 重置填充状态
                if self.verboseLogging:
                    print(f"   Recycled buy grid at ¥{grid.price:.2f}")
        
        for grid in self.sellGrids:
            if grid.isFilled and abs(currentPrice - grid.price) / currentPrice < self.gridSpacing * 2:
                grid.isFilled = False  # 重置填充状态
                if self.verboseLogging:
                    print(f"   Recycled sell grid at ¥{grid.price:.2f}")
        
        self.lastRecyclingTime = timestamp

    def _calculateInitialCenterPrice(self, prices: pd.Series) -> float:
        """
        计算初始网格中心价格
        
        Args:
            prices: 价格序列
            
        Returns:
            float: 初始中心价格
        """
        if len(prices) == 0:
            raise ValueError("Price series is empty")
        
        # 使用前几天的平均价格作为初始中心，避免使用单点价格
        initial_period = min(5, len(prices))
        initial_prices = prices.iloc[:initial_period]
        
        # 使用简单移动平均作为初始中心价格
        center_price = initial_prices.mean()
        
        if self.verboseLogging:
            print(f"📊 Initial center price calculation:")
            print(f"  Using {initial_period} days average: ¥{center_price:.2f}")
            print(f"  Price range: ¥{initial_prices.min():.2f} - ¥{initial_prices.max():.2f}")
        
        return center_price