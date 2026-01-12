#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Algorithm Engine
算法引擎

Core engine that orchestrates the Alpha -> Portfolio -> Risk -> Execution flow.
This engine supports the new componentized strategy architecture while remaining
compatible with the existing BacktestEngine for traditional strategies.

Usage:
    from quant.engines import AlgorithmEngine
    from quant.analysis.alpha import MomentumAlpha, MeanReversionAlpha
    from quant.portfolio import EqualWeightConstructor
    from quant.risk import PositionLimits, DrawdownMonitor, CompositeRiskModel
    
    # Create engine with components
    engine = AlgorithmEngine(
        alphas=[MomentumAlpha(), MeanReversionAlpha()],
        portfolio_constructor=EqualWeightConstructor(),
        risk_model=CompositeRiskModel([
            PositionLimits(max_single_position=0.10),
            DrawdownMonitor(max_drawdown=0.20)
        ])
    )
    
    # Run on market data
    result = engine.run(market_data)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import pandas as pd
import numpy as np

from quant.analysis.alpha.base_alpha import BaseAlpha, Insight
from quant.portfolio.base_constructor import BasePortfolioConstructor, Order
from quant.risk.base_risk_model import BaseRiskModel, RiskCheckResult
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class AlgorithmState:
    """
    Current state of the algorithm engine.
    算法引擎状态。
    """
    timestamp: datetime
    insights: List[Insight] = field(default_factory=list)
    target_positions: Dict[str, float] = field(default_factory=dict)
    adjusted_positions: Dict[str, float] = field(default_factory=dict)
    risk_result: Optional[RiskCheckResult] = None
    orders: List[Order] = field(default_factory=list)
    portfolio_value: float = 1.0
    
    def __str__(self):
        return (
            f"State @ {self.timestamp}: "
            f"{len(self.insights)} insights, "
            f"{len(self.adjusted_positions)} positions, "
            f"{len(self.orders)} orders"
        )


@dataclass
class AlgorithmResult:
    """
    Result of algorithm execution.
    算法执行结果。
    """
    start_time: datetime
    end_time: datetime
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    final_positions: Dict[str, float]
    portfolio_history: pd.DataFrame
    states: List[AlgorithmState] = field(default_factory=list)
    
    def summary(self) -> str:
        """Generate result summary."""
        return (
            f"Algorithm Result:\n"
            f"  Period: {self.start_time.date()} to {self.end_time.date()}\n"
            f"  Total Return: {self.total_return:.2%}\n"
            f"  Sharpe Ratio: {self.sharpe_ratio:.2f}\n"
            f"  Max Drawdown: {self.max_drawdown:.2%}\n"
            f"  Total Trades: {self.total_trades}\n"
            f"  Final Positions: {len(self.final_positions)}"
        )


class AlgorithmEngine:
    """
    Algorithm Engine for componentized strategies.
    
    Orchestrates the flow:
    1. Alpha Layer: Generate insights from market data
    2. Portfolio Layer: Convert insights to target positions
    3. Risk Layer: Check and adjust positions for risk
    4. Execution Layer: Generate orders for rebalancing
    
    This engine is designed to work alongside the existing BacktestEngine,
    providing a modern component-based approach while maintaining compatibility
    with existing strategies.
    """
    
    def __init__(
        self,
        alphas: Optional[List[BaseAlpha]] = None,
        portfolio_constructor: Optional[BasePortfolioConstructor] = None,
        risk_model: Optional[BaseRiskModel] = None,
        rebalance_frequency: str = 'daily',
        initial_capital: float = 1_000_000.0,
        transaction_cost: float = 0.001
    ):
        """
        Initialize Algorithm Engine.
        
        Args:
            alphas: List of Alpha models
            portfolio_constructor: Portfolio construction model
            risk_model: Risk management model
            rebalance_frequency: 'daily', 'weekly', 'monthly'
            initial_capital: Starting capital
            transaction_cost: Transaction cost as fraction
        """
        self.alphas = alphas or []
        self.portfolio_constructor = portfolio_constructor
        self.risk_model = risk_model
        self.rebalance_frequency = rebalance_frequency
        self.initial_capital = initial_capital
        self.transaction_cost = transaction_cost
        
        # State tracking
        self._current_positions: Dict[str, float] = {}
        self._portfolio_value: float = initial_capital
        self._states: List[AlgorithmState] = []
    
    def add_alpha(self, alpha: BaseAlpha):
        """Add an Alpha model."""
        self.alphas.append(alpha)
    
    def set_portfolio_constructor(self, constructor: BasePortfolioConstructor):
        """Set portfolio constructor."""
        self.portfolio_constructor = constructor
    
    def set_risk_model(self, model: BaseRiskModel):
        """Set risk model."""
        self.risk_model = model
    
    def run(
        self,
        market_data: Dict[str, pd.DataFrame],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> AlgorithmResult:
        """
        Run algorithm on market data.
        
        Args:
            market_data: Price data by symbol {symbol: DataFrame}
            start_date: Start date (default: earliest in data)
            end_date: End date (default: latest in data)
            
        Returns:
            AlgorithmResult with performance metrics
        """
        if not self.alphas:
            raise ValueError("No Alpha models configured")
        if not self.portfolio_constructor:
            raise ValueError("No portfolio constructor configured")
        
        # Determine date range
        all_dates = self._get_all_dates(market_data)
        if start_date:
            all_dates = [d for d in all_dates if d >= start_date]
        if end_date:
            all_dates = [d for d in all_dates if d <= end_date]
        
        if not all_dates:
            raise ValueError("No data in specified date range")
        
        logger.info(
            f"Running algorithm from {all_dates[0].date()} to {all_dates[-1].date()} "
            f"({len(all_dates)} periods)"
        )
        
        # Initialize
        self._current_positions = {}
        self._portfolio_value = self.initial_capital
        self._states = []
        portfolio_history = []
        total_trades = 0
        
        # Get rebalance dates
        rebalance_dates = self._get_rebalance_dates(all_dates)
        
        # Run through each date
        for date in all_dates:
            # Get data up to current date
            current_data = self._slice_data(market_data, date)
            
            # Check if rebalance date
            if date in rebalance_dates:
                state = self._step(date, current_data)
                total_trades += len(state.orders)
                self._states.append(state)
            
            # Update portfolio value
            daily_return = self._calculate_daily_return(market_data, date)
            self._portfolio_value *= (1 + daily_return)
            
            portfolio_history.append({
                'date': date,
                'value': self._portfolio_value,
                'return': daily_return,
                'positions': len(self._current_positions)
            })
        
        # Calculate final metrics
        history_df = pd.DataFrame(portfolio_history)
        history_df.set_index('date', inplace=True)
        
        returns = history_df['return'].dropna()
        total_return = (self._portfolio_value / self.initial_capital) - 1
        volatility = returns.std() * np.sqrt(252) if len(returns) > 1 else 0
        sharpe = (total_return / volatility) if volatility > 0 else 0
        
        # Max drawdown
        cumulative = (1 + returns).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdowns = cumulative / rolling_max - 1
        max_drawdown = abs(drawdowns.min()) if len(drawdowns) > 0 else 0
        
        return AlgorithmResult(
            start_time=all_dates[0],
            end_time=all_dates[-1],
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            total_trades=total_trades,
            final_positions=self._current_positions.copy(),
            portfolio_history=history_df,
            states=self._states
        )
    
    def _step(
        self,
        date: datetime,
        market_data: Dict[str, pd.DataFrame]
    ) -> AlgorithmState:
        """
        Execute one step of the algorithm.
        
        Args:
            date: Current date
            market_data: Market data up to current date
            
        Returns:
            AlgorithmState for this step
        """
        state = AlgorithmState(timestamp=date)
        
        # Step 1: Generate insights from Alpha models
        all_insights = []
        for alpha in self.alphas:
            insights = alpha.generate_insights(market_data)
            all_insights.extend(insights)
        
        # Combine insights if multiple alphas
        if len(self.alphas) > 1 and all_insights:
            # Use first alpha's combine method
            combined = self.alphas[0].combine_insights([all_insights])
            state.insights = combined
        else:
            state.insights = all_insights
        
        # Step 2: Construct target portfolio
        state.target_positions = self.portfolio_constructor.construct(
            state.insights,
            current_positions=self._current_positions
        )
        
        # Step 3: Risk check and adjustment
        if self.risk_model:
            # Get returns data for VaR calculation
            returns_data = self._calculate_returns_data(market_data)
            
            state.risk_result = self.risk_model.check(
                state.target_positions,
                returns_data=returns_data
            )
            state.adjusted_positions = state.risk_result.adjusted_positions
            
            if not state.risk_result.passed:
                logger.warning(
                    f"Risk check failed: {state.risk_result.violations}"
                )
        else:
            state.adjusted_positions = state.target_positions.copy()
        
        # Step 4: Calculate rebalance orders
        state.orders = self.portfolio_constructor.rebalance(
            self._current_positions,
            state.adjusted_positions
        )
        
        # Apply orders (update positions)
        for order in state.orders:
            self._current_positions[order.symbol] = order.target_weight
        
        # Remove zero positions
        self._current_positions = {
            k: v for k, v in self._current_positions.items() if v > 0
        }
        
        state.portfolio_value = self._portfolio_value
        
        return state
    
    def _get_all_dates(self, market_data: Dict[str, pd.DataFrame]) -> List[datetime]:
        """Get all unique dates from market data."""
        all_dates = set()
        for symbol, df in market_data.items():
            if isinstance(df.index, pd.DatetimeIndex):
                all_dates.update(df.index.tolist())
            elif 'date' in df.columns:
                all_dates.update(pd.to_datetime(df['date']).tolist())
        
        return sorted(all_dates)
    
    def _get_rebalance_dates(self, dates: List[datetime]) -> set:
        """Get dates when rebalancing should occur."""
        if self.rebalance_frequency == 'daily':
            return set(dates)
        
        rebalance_dates = set()
        
        if self.rebalance_frequency == 'weekly':
            # Rebalance on Mondays (weekday 0)
            for d in dates:
                if d.weekday() == 0:
                    rebalance_dates.add(d)
        
        elif self.rebalance_frequency == 'monthly':
            # Rebalance on first trading day of month
            current_month = None
            for d in dates:
                if d.month != current_month:
                    rebalance_dates.add(d)
                    current_month = d.month
        
        # Always include first date
        if dates:
            rebalance_dates.add(dates[0])
        
        return rebalance_dates
    
    def _slice_data(
        self,
        market_data: Dict[str, pd.DataFrame],
        end_date: datetime
    ) -> Dict[str, pd.DataFrame]:
        """Slice market data up to end_date."""
        sliced = {}
        for symbol, df in market_data.items():
            if isinstance(df.index, pd.DatetimeIndex):
                sliced[symbol] = df[df.index <= end_date]
            else:
                sliced[symbol] = df[pd.to_datetime(df['date']) <= end_date]
        return sliced
    
    def _calculate_daily_return(
        self,
        market_data: Dict[str, pd.DataFrame],
        date: datetime
    ) -> float:
        """Calculate portfolio return for a single day."""
        if not self._current_positions:
            return 0.0
        
        total_return = 0.0
        
        for symbol, weight in self._current_positions.items():
            if symbol in market_data:
                df = market_data[symbol]
                if isinstance(df.index, pd.DatetimeIndex):
                    if date in df.index:
                        idx = df.index.get_loc(date)
                        if idx > 0:
                            prev_close = df['close'].iloc[idx - 1]
                            curr_close = df['close'].iloc[idx]
                            if prev_close > 0:
                                asset_return = (curr_close - prev_close) / prev_close
                                total_return += weight * asset_return
        
        return total_return
    
    def _calculate_returns_data(
        self,
        market_data: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.Series]:
        """Calculate returns series for each symbol."""
        returns_data = {}
        for symbol, df in market_data.items():
            if 'close' in df.columns and len(df) > 1:
                returns = df['close'].pct_change().dropna()
                returns_data[symbol] = returns
        return returns_data
    
    def reset(self):
        """Reset engine state."""
        self._current_positions = {}
        self._portfolio_value = self.initial_capital
        self._states = []
