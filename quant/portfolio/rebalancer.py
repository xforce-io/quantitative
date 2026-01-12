#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Portfolio Rebalancer
组合再平衡器

Utilities for calculating rebalance trades and managing portfolio transitions.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from .base_constructor import Order


@dataclass
class RebalanceResult:
    """Result of rebalance calculation."""
    orders: List[Order]           # Orders to execute
    total_turnover: float         # Total turnover (sum of absolute weight changes)
    buy_count: int                # Number of buy orders
    sell_count: int               # Number of sell orders
    unchanged_count: int          # Number of unchanged positions
    
    def __str__(self):
        return (
            f"Rebalance: {len(self.orders)} orders, "
            f"{self.total_turnover:.1%} turnover, "
            f"{self.buy_count} buys, {self.sell_count} sells"
        )


class Rebalancer:
    """
    Portfolio rebalancer utility.
    
    Calculates the trades needed to transition from current to target portfolio.
    """
    
    def __init__(
        self,
        threshold: float = 0.02,
        min_trade_size: float = 0.01
    ):
        """
        Initialize rebalancer.
        
        Args:
            threshold: Minimum weight deviation to trigger rebalance
            min_trade_size: Minimum trade size (weight)
        """
        self.threshold = threshold
        self.min_trade_size = min_trade_size
    
    def calculate(
        self,
        current: Dict[str, float],
        target: Dict[str, float]
    ) -> RebalanceResult:
        """
        Calculate rebalance orders.
        
        Args:
            current: Current portfolio weights {symbol: weight}
            target: Target portfolio weights {symbol: weight}
            
        Returns:
            RebalanceResult with orders and statistics
        """
        orders = []
        total_turnover = 0.0
        buy_count = 0
        sell_count = 0
        unchanged_count = 0
        
        all_symbols = set(current.keys()) | set(target.keys())
        
        for symbol in all_symbols:
            curr_weight = current.get(symbol, 0.0)
            tgt_weight = target.get(symbol, 0.0)
            diff = tgt_weight - curr_weight
            
            if abs(diff) < self.threshold:
                unchanged_count += 1
                continue
            
            if abs(diff) < self.min_trade_size:
                unchanged_count += 1
                continue
            
            if diff > 0:
                direction = 'BUY'
                buy_count += 1
            else:
                direction = 'SELL'
                sell_count += 1
            
            orders.append(Order(
                symbol=symbol,
                direction=direction,
                weight_change=abs(diff),
                target_weight=tgt_weight
            ))
            
            total_turnover += abs(diff)
        
        # Sort: sells first (to free up cash), then buys
        orders.sort(key=lambda o: (0 if o.direction == 'SELL' else 1, -o.weight_change))
        
        return RebalanceResult(
            orders=orders,
            total_turnover=total_turnover,
            buy_count=buy_count,
            sell_count=sell_count,
            unchanged_count=unchanged_count
        )
    
    def apply_orders(
        self,
        current: Dict[str, float],
        orders: List[Order]
    ) -> Dict[str, float]:
        """
        Apply orders to current portfolio to get new portfolio.
        
        Args:
            current: Current portfolio weights
            orders: Orders to apply
            
        Returns:
            New portfolio weights after applying orders
        """
        new_portfolio = current.copy()
        
        for order in orders:
            new_portfolio[order.symbol] = order.target_weight
        
        # Remove zero positions
        new_portfolio = {k: v for k, v in new_portfolio.items() if v > 0}
        
        return new_portfolio
    
    def estimate_cost(
        self,
        orders: List[Order],
        transaction_cost: float = 0.001
    ) -> float:
        """
        Estimate transaction cost of rebalance.
        
        Args:
            orders: Rebalance orders
            transaction_cost: Cost per unit of turnover (default 0.1%)
            
        Returns:
            Estimated cost as fraction of portfolio
        """
        total_turnover = sum(o.weight_change for o in orders)
        return total_turnover * transaction_cost
