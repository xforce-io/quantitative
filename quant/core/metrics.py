#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
性能指标计算模块 (Performance Metrics Module)

提供统一的投资和策略性能指标计算
Provides unified investment and strategy performance metrics calculations
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple, List
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')


class PerformanceMetrics:
    """性能指标计算器"""
    
    @staticmethod
    def calculate_returns_metrics(returns: pd.Series) -> Dict[str, float]:
        """
        计算收益率相关指标
        
        Args:
            returns: 日收益率序列
            
        Returns:
            收益率指标字典
        """
        if returns.empty or returns.isna().all():
            return {
                'total_return': 0.0,
                'annual_return': 0.0,
                'monthly_return': 0.0,
                'daily_return_mean': 0.0,
                'daily_return_std': 0.0
            }
        
        # 清除无效值
        clean_returns = returns.dropna()
        if len(clean_returns) == 0:
            return {
                'total_return': 0.0,
                'annual_return': 0.0,
                'monthly_return': 0.0,
                'daily_return_mean': 0.0,
                'daily_return_std': 0.0
            }
        
        # 总收益率
        total_return = (1 + clean_returns).prod() - 1
        
        # 年化收益率
        trading_days = len(clean_returns)
        if trading_days > 0:
            annual_return = (1 + total_return) ** (252 / trading_days) - 1
            monthly_return = (1 + total_return) ** (21 / trading_days) - 1
        else:
            annual_return = 0.0
            monthly_return = 0.0
        
        # 日均收益率和标准差
        daily_return_mean = clean_returns.mean()
        daily_return_std = clean_returns.std()
        
        return {
            'total_return': total_return,
            'annual_return': annual_return,
            'monthly_return': monthly_return,
            'daily_return_mean': daily_return_mean,
            'daily_return_std': daily_return_std
        }
    
    @staticmethod
    def calculate_drawdown_metrics(prices: pd.Series) -> Dict[str, float]:
        """
        计算回撤相关指标
        
        Args:
            prices: 价格或净值序列
            
        Returns:
            回撤指标字典
        """
        if prices.empty or prices.isna().all():
            return {
                'max_drawdown': 0.0,
                'current_drawdown': 0.0,
                'drawdown_periods': 0,
                'recovery_factor': 0.0
            }
        
        # 清除无效值
        clean_prices = prices.dropna()
        if len(clean_prices) == 0:
            return {
                'max_drawdown': 0.0,
                'current_drawdown': 0.0,
                'drawdown_periods': 0,
                'recovery_factor': 0.0
            }
        
        # 计算滚动最高点
        rolling_max = clean_prices.expanding().max()
        
        # 计算回撤
        drawdowns = (clean_prices - rolling_max) / rolling_max
        
        # 最大回撤
        max_drawdown = drawdowns.min()
        
        # 当前回撤
        current_drawdown = drawdowns.iloc[-1]
        
        # 回撤期数（连续负回撤的期数）
        drawdown_periods = 0
        for i in range(len(drawdowns) - 1, -1, -1):
            if drawdowns.iloc[i] < 0:
                drawdown_periods += 1
            else:
                break
        
        # 恢复因子（总收益率/最大回撤的绝对值）
        total_return = (clean_prices.iloc[-1] / clean_prices.iloc[0]) - 1
        recovery_factor = total_return / abs(max_drawdown) if max_drawdown != 0 else 0.0
        
        return {
            'max_drawdown': max_drawdown,
            'current_drawdown': current_drawdown,
            'drawdown_periods': drawdown_periods,
            'recovery_factor': recovery_factor
        }
    
    @staticmethod
    def calculate_risk_metrics(returns: pd.Series, risk_free_rate: float = 0.03) -> Dict[str, float]:
        """
        计算风险相关指标
        
        Args:
            returns: 日收益率序列
            risk_free_rate: 无风险利率（年化）
            
        Returns:
            风险指标字典
        """
        if returns.empty or returns.isna().all():
            return {
                'volatility': 0.0,
                'sharpe_ratio': 0.0,
                'sortino_ratio': 0.0,
                'calmar_ratio': 0.0,
                'var_95': 0.0,
                'cvar_95': 0.0
            }
        
        # 清除无效值
        clean_returns = returns.dropna()
        if len(clean_returns) == 0:
            return {
                'volatility': 0.0,
                'sharpe_ratio': 0.0,
                'sortino_ratio': 0.0,
                'calmar_ratio': 0.0,
                'var_95': 0.0,
                'cvar_95': 0.0
            }
        
        # 年化波动率
        volatility = clean_returns.std() * np.sqrt(252)
        
        # 年化收益率
        annual_return = clean_returns.mean() * 252
        
        # 夏普比率
        sharpe_ratio = (annual_return - risk_free_rate) / volatility if volatility > 0 else 0.0
        
        # 索提诺比率（只考虑下行风险）
        downside_returns = clean_returns[clean_returns < 0]
        downside_volatility = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0.0
        sortino_ratio = (annual_return - risk_free_rate) / downside_volatility if downside_volatility > 0 else 0.0
        
        # 卡玛比率（年化收益率/最大回撤）
        cumulative_returns = (1 + clean_returns).cumprod()
        max_drawdown = ((cumulative_returns / cumulative_returns.expanding().max()) - 1).min()
        calmar_ratio = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0.0
        
        # VaR（在险价值）- 95%置信度
        var_95 = clean_returns.quantile(0.05)
        
        # CVaR（条件在险价值）- 95%置信度
        cvar_95 = clean_returns[clean_returns <= var_95].mean() if len(clean_returns[clean_returns <= var_95]) > 0 else var_95
        
        return {
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'var_95': var_95,
            'cvar_95': cvar_95
        }
    
    @staticmethod
    def calculate_trading_metrics(trades: List[Dict]) -> Dict[str, float]:
        """
        计算交易相关指标
        
        Args:
            trades: 交易记录列表，每个交易包含{'return': float, 'profit': float}等字段
            
        Returns:
            交易指标字典
        """
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'profit_loss_ratio': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'largest_win': 0.0,
                'largest_loss': 0.0
            }
        
        # 提取交易收益
        trade_returns = []
        for trade in trades:
            if isinstance(trade, dict):
                if 'return' in trade:
                    trade_returns.append(trade['return'])
                elif 'profit' in trade:
                    trade_returns.append(trade['profit'])
        
        if not trade_returns:
            return {
                'total_trades': len(trades),
                'win_rate': 0.0,
                'profit_loss_ratio': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'largest_win': 0.0,
                'largest_loss': 0.0
            }
        
        # 分离盈利和亏损交易
        winning_trades = [r for r in trade_returns if r > 0]
        losing_trades = [r for r in trade_returns if r < 0]
        
        # 胜率
        win_rate = len(winning_trades) / len(trade_returns) if trade_returns else 0.0
        
        # 盈亏比
        avg_win = np.mean(winning_trades) if winning_trades else 0.0
        avg_loss = abs(np.mean(losing_trades)) if losing_trades else 0.0
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0
        
        # 最大单笔盈利和亏损
        largest_win = max(winning_trades) if winning_trades else 0.0
        largest_loss = min(losing_trades) if losing_trades else 0.0
        
        return {
            'total_trades': len(trade_returns),
            'win_rate': win_rate,
            'profit_loss_ratio': profit_loss_ratio,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'largest_win': largest_win,
            'largest_loss': largest_loss
        }
    
    @staticmethod
    def calculate_comprehensive_metrics(prices: pd.Series, trades: List[Dict] = None, 
                                      benchmark: pd.Series = None, risk_free_rate: float = 0.03) -> Dict[str, float]:
        """
        计算综合性能指标
        
        Args:
            prices: 价格或净值序列
            trades: 交易记录列表（可选）
            benchmark: 基准价格序列（可选）
            risk_free_rate: 无风险利率
            
        Returns:
            综合性能指标字典
        """
        if prices.empty or prices.isna().all():
            return {}
        
        # 计算收益率
        returns = prices.pct_change().dropna()
        
        # 基础指标
        metrics = {}
        
        # 收益率指标
        returns_metrics = PerformanceMetrics.calculate_returns_metrics(returns)
        metrics.update(returns_metrics)
        
        # 回撤指标
        drawdown_metrics = PerformanceMetrics.calculate_drawdown_metrics(prices)
        metrics.update(drawdown_metrics)
        
        # 风险指标
        risk_metrics = PerformanceMetrics.calculate_risk_metrics(returns, risk_free_rate)
        metrics.update(risk_metrics)
        
        # 交易指标（如果提供）
        if trades:
            trading_metrics = PerformanceMetrics.calculate_trading_metrics(trades)
            metrics.update(trading_metrics)
        
        # 相对基准指标（如果提供基准）
        if benchmark is not None and not benchmark.empty:
            benchmark_returns = benchmark.pct_change().dropna()
            if len(benchmark_returns) > 0 and len(returns) > 0:
                # 对齐数据
                common_index = returns.index.intersection(benchmark_returns.index)
                if len(common_index) > 0:
                    aligned_returns = returns.reindex(common_index)
                    aligned_benchmark = benchmark_returns.reindex(common_index)
                    
                    # 超额收益
                    excess_returns = aligned_returns - aligned_benchmark
                    excess_annual_return = excess_returns.mean() * 252
                    
                    # 跟踪误差
                    tracking_error = excess_returns.std() * np.sqrt(252)
                    
                    # 信息比率
                    information_ratio = excess_annual_return / tracking_error if tracking_error > 0 else 0.0
                    
                    # Beta
                    covariance = np.cov(aligned_returns, aligned_benchmark)[0][1]
                    benchmark_variance = aligned_benchmark.var()
                    beta = covariance / benchmark_variance if benchmark_variance > 0 else 0.0
                    
                    # Alpha
                    alpha = metrics['annual_return'] - (risk_free_rate + beta * (aligned_benchmark.mean() * 252 - risk_free_rate))
                    
                    metrics.update({
                        'excess_return': excess_annual_return,
                        'tracking_error': tracking_error,
                        'information_ratio': information_ratio,
                        'beta': beta,
                        'alpha': alpha
                    })
        
        return metrics
    
    @staticmethod
    def format_metrics_for_display(metrics: Dict[str, float]) -> Dict[str, str]:
        """
        格式化指标用于显示
        
        Args:
            metrics: 原始指标字典
            
        Returns:
            格式化后的指标字典
        """
        formatted = {}
        
        percentage_metrics = [
            'total_return', 'annual_return', 'monthly_return', 'daily_return_mean', 'daily_return_std',
            'max_drawdown', 'current_drawdown', 'volatility', 'var_95', 'cvar_95', 'win_rate',
            'excess_return', 'tracking_error', 'alpha'
        ]
        
        ratio_metrics = [
            'sharpe_ratio', 'sortino_ratio', 'calmar_ratio', 'profit_loss_ratio',
            'information_ratio', 'beta', 'recovery_factor'
        ]
        
        integer_metrics = ['total_trades', 'drawdown_periods']
        
        currency_metrics = ['avg_win', 'avg_loss', 'largest_win', 'largest_loss']
        
        for key, value in metrics.items():
            if key in percentage_metrics:
                formatted[key] = f"{value:.2%}" if not np.isnan(value) else "N/A"
            elif key in ratio_metrics:
                formatted[key] = f"{value:.3f}" if not np.isnan(value) else "N/A"
            elif key in integer_metrics:
                formatted[key] = f"{int(value)}" if not np.isnan(value) else "N/A"
            elif key in currency_metrics:
                formatted[key] = f"¥{value:,.2f}" if not np.isnan(value) else "N/A"
            else:
                formatted[key] = f"{value:.4f}" if not np.isnan(value) else "N/A"
        
        return formatted


def calculate_performance_summary(prices: pd.Series, **kwargs) -> Dict[str, float]:
    """
    便捷函数：计算性能摘要
    
    Args:
        prices: 价格或净值序列
        **kwargs: 其他参数传递给calculate_comprehensive_metrics
        
    Returns:
        性能指标摘要
    """
    return PerformanceMetrics.calculate_comprehensive_metrics(prices, **kwargs)


def format_performance_report(metrics: Dict[str, float]) -> str:
    """
    生成性能报告文本
    
    Args:
        metrics: 性能指标字典
        
    Returns:
        格式化的性能报告字符串
    """
    if not metrics:
        return "无可用的性能数据"
    
    formatted_metrics = PerformanceMetrics.format_metrics_for_display(metrics)
    
    report_lines = [
        "=" * 60,
        "📊 性能指标报告",
        "=" * 60,
        "",
        "📈 收益指标:",
        f"  总收益率: {formatted_metrics.get('total_return', 'N/A')}",
        f"  年化收益率: {formatted_metrics.get('annual_return', 'N/A')}",
        f"  月度收益率: {formatted_metrics.get('monthly_return', 'N/A')}",
        "",
        "📉 风险指标:",
        f"  年化波动率: {formatted_metrics.get('volatility', 'N/A')}",
        f"  最大回撤: {formatted_metrics.get('max_drawdown', 'N/A')}",
        f"  当前回撤: {formatted_metrics.get('current_drawdown', 'N/A')}",
        f"  VaR(95%): {formatted_metrics.get('var_95', 'N/A')}",
        "",
        "⚖️ 风险调整指标:",
        f"  夏普比率: {formatted_metrics.get('sharpe_ratio', 'N/A')}",
        f"  索提诺比率: {formatted_metrics.get('sortino_ratio', 'N/A')}",
        f"  卡玛比率: {formatted_metrics.get('calmar_ratio', 'N/A')}",
    ]
    
    # 添加交易指标（如果有）
    if 'total_trades' in formatted_metrics and int(formatted_metrics.get('total_trades', '0')) > 0:
        report_lines.extend([
            "",
            "🔄 交易指标:",
            f"  总交易次数: {formatted_metrics.get('total_trades', 'N/A')}",
            f"  胜率: {formatted_metrics.get('win_rate', 'N/A')}",
            f"  盈亏比: {formatted_metrics.get('profit_loss_ratio', 'N/A')}",
        ])
    
    # 添加基准比较指标（如果有）
    if 'beta' in formatted_metrics:
        report_lines.extend([
            "",
            "📊 相对基准指标:",
            f"  Beta: {formatted_metrics.get('beta', 'N/A')}",
            f"  Alpha: {formatted_metrics.get('alpha', 'N/A')}",
            f"  信息比率: {formatted_metrics.get('information_ratio', 'N/A')}",
        ])
    
    report_lines.extend([
        "",
        "=" * 60
    ])
    
    return "\n".join(report_lines)
