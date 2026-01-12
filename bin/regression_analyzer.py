#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
股票/ETF 回归拟合分析工具

对价格走势进行多种回归拟合分析，包括：
- 线性回归 (Linear Regression)
- 多项式回归 (Polynomial Regression)
- 指数回归 (Exponential Regression)
- 对数回归 (Logarithmic Regression)

用法示例:
    # 基础线性回归分析
    python bin/regression_analyzer.py 002594.SZ

    # 指定回归类型和周期
    python bin/regression_analyzer.py 002594.SZ --type poly --degree 2 --days 120

    # 多种回归类型对比
    python bin/regression_analyzer.py 002594.SZ --compare-all

    # 预测未来价格
    python bin/regression_analyzer.py 002594.SZ --predict 5

    # 保存图表和结果
    python bin/regression_analyzer.py 002594.SZ --save --plot
"""

import sys
import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import curve_fit

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from quant import create_data_provider, get_config
from quant.core.logging_config import get_logger

logger = get_logger(__name__)

# 忽略scipy的警告
warnings.filterwarnings('ignore', category=RuntimeWarning)


class RegressionAnalyzer:
    """回归拟合分析器"""

    def __init__(self, data_provider: str = 'auto'):
        """
        初始化分析器

        Args:
            data_provider: 数据源 (tushare/yahoo/auto)
        """
        config = get_config()
        self.provider = create_data_provider(data_provider, config.get_providers_config())
        self.results = {}
        
        # 初始化 tushare pro api 用于获取复权数据
        try:
            import tushare as ts
            from quant.core.legacy_config import Config
            token = Config.TUSHARE_TOKEN
            if token:
                ts.set_token(token)
                self.ts_pro = ts.pro_api()
            else:
                self.ts_pro = None
        except:
            self.ts_pro = None

    def get_price_data(self, symbol: str, days: int = 120, adj: str = None) -> Optional[pd.DataFrame]:
        """
        获取价格数据

        Args:
            symbol: 股票/ETF代码
            days: 历史天数
            adj: 复权类型 ('qfq'=前复权, 'hfq'=后复权, None=不复权)

        Returns:
            价格数据DataFrame
        """
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days + 60)).strftime('%Y%m%d')

            # 首先尝试获取基础数据
            data = self.provider.get_stock_data(symbol, start_date, end_date, 'D')
            
            if data is None or data.empty:
                logger.error(f"无法获取 {symbol} 的数据")
                return None

            # 如果需要复权，尝试应用复权因子
            if adj and self.ts_pro:
                logger.info(f"获取 {symbol} 的复权因子...")
                try:
                    # 获取复权因子
                    adj_df = self.ts_pro.fund_adj(
                        ts_code=symbol,
                        start_date=start_date,
                        end_date=end_date
                    )
                    
                    if adj_df is not None and not adj_df.empty:
                        # 转换日期格式
                        adj_df['trade_date'] = pd.to_datetime(adj_df['trade_date'])
                        adj_df = adj_df.set_index('trade_date')
                        
                        # 确保data有正确的索引
                        if 'date' in data.columns:
                            data = data.set_index('date')
                        
                        # 合并复权因子
                        data = data.join(adj_df['adj_factor'], how='left')
                        
                        # 填充缺失的复权因子（用前值填充）
                        data['adj_factor'] = data['adj_factor'].fillna(method='ffill').fillna(method='bfill')
                        
                        if data['adj_factor'].notna().any():
                            # 获取最新的复权因子
                            latest_adj = data['adj_factor'].iloc[-1]
                            
                            if adj == 'qfq':  # 前复权
                                # 前复权 = 原始价格 * (复权因子 / 最新复权因子)
                                adj_ratio = data['adj_factor'] / latest_adj
                            else:  # hfq 后复权
                                # 后复权 = 原始价格 * 复权因子
                                adj_ratio = data['adj_factor']
                            
                            # 应用复权到 OHLC
                            for col in ['open', 'high', 'low', 'close']:
                                if col in data.columns:
                                    data[col] = data[col] * adj_ratio
                            
                            adj_name = '前复权' if adj == 'qfq' else '后复权'
                            logger.info(f"✅ 成功应用{adj_name}，最新复权因子: {latest_adj:.4f}")
                        else:
                            logger.warning("复权因子数据为空，使用原始数据")
                        
                        # 移除复权因子列
                        if 'adj_factor' in data.columns:
                            data = data.drop(columns=['adj_factor'])
                        
                        # 重置索引
                        data = data.reset_index()
                    else:
                        logger.warning(f"未获取到 {symbol} 的复权因子，使用原始数据")
                        
                except Exception as e:
                    logger.warning(f"获取复权因子失败: {e}，使用原始数据")

            # 取最近 days 天数据
            data = data.tail(days).copy()
            if 'date' not in data.columns:
                data = data.reset_index()

            # 确保有必要的列
            if 'close' not in data.columns:
                logger.error(f"数据中没有 close 列")
                return None

            return data

        except Exception as e:
            logger.error(f"获取数据失败: {e}")
            return None

    def linear_regression(self, x: np.ndarray, y: np.ndarray) -> Dict:
        """
        线性回归: y = ax + b

        Args:
            x: 时间序列索引
            y: 价格序列

        Returns:
            回归结果字典
        """
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        y_pred = slope * x + intercept
        residuals = y - y_pred
        mse = np.mean(residuals ** 2)
        rmse = np.sqrt(mse)

        # 计算年化收益率 (假设252个交易日)
        daily_return = slope / np.mean(y)
        annual_return = daily_return * 252

        return {
            'type': 'linear',
            'formula': f'y = {slope:.6f}x + {intercept:.4f}',
            'params': {'slope': slope, 'intercept': intercept},
            'r_squared': r_value ** 2,
            'p_value': p_value,
            'std_err': std_err,
            'rmse': rmse,
            'mse': mse,
            'y_pred': y_pred,
            'residuals': residuals,
            'daily_return_pct': daily_return * 100,
            'annual_return_pct': annual_return * 100,
            'trend': 'up' if slope > 0 else 'down'
        }

    def polynomial_regression(self, x: np.ndarray, y: np.ndarray, degree: int = 2) -> Dict:
        """
        多项式回归: y = a_n*x^n + ... + a_1*x + a_0

        Args:
            x: 时间序列索引
            y: 价格序列
            degree: 多项式阶数

        Returns:
            回归结果字典
        """
        coeffs = np.polyfit(x, y, degree)
        poly = np.poly1d(coeffs)
        y_pred = poly(x)

        # 计算R²
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        residuals = y - y_pred
        rmse = np.sqrt(np.mean(residuals ** 2))

        # 构建公式字符串
        terms = []
        for i, c in enumerate(coeffs):
            power = degree - i
            if power == 0:
                terms.append(f'{c:.6f}')
            elif power == 1:
                terms.append(f'{c:.6f}x')
            else:
                terms.append(f'{c:.6f}x^{power}')
        formula = ' + '.join(terms)

        # 判断趋势（基于二次项和一次项）
        if degree >= 2:
            # 二次项系数决定凹凸性
            if coeffs[0] > 0:
                curvature = 'convex (加速上涨或减速下跌)'
            else:
                curvature = 'concave (减速上涨或加速下跌)'
        else:
            curvature = 'linear'

        return {
            'type': f'polynomial_deg{degree}',
            'formula': f'y = {formula}',
            'params': {'coefficients': coeffs.tolist(), 'degree': degree},
            'r_squared': r_squared,
            'rmse': rmse,
            'y_pred': y_pred,
            'residuals': residuals,
            'curvature': curvature
        }

    def exponential_regression(self, x: np.ndarray, y: np.ndarray) -> Dict:
        """
        指数回归: y = a * e^(bx)

        Args:
            x: 时间序列索引
            y: 价格序列

        Returns:
            回归结果字典
        """
        try:
            # 使用对数变换进行线性回归
            y_positive = np.maximum(y, 1e-10)  # 避免log(0)
            log_y = np.log(y_positive)

            slope, intercept, r_value, _, _ = stats.linregress(x, log_y)

            a = np.exp(intercept)
            b = slope

            y_pred = a * np.exp(b * x)
            residuals = y - y_pred
            rmse = np.sqrt(np.mean(residuals ** 2))

            # 日增长率
            daily_growth_rate = (np.exp(b) - 1) * 100
            # 年化增长率
            annual_growth_rate = ((1 + daily_growth_rate/100) ** 252 - 1) * 100

            return {
                'type': 'exponential',
                'formula': f'y = {a:.4f} * e^({b:.6f}x)',
                'params': {'a': a, 'b': b},
                'r_squared': r_value ** 2,
                'rmse': rmse,
                'y_pred': y_pred,
                'residuals': residuals,
                'daily_growth_pct': daily_growth_rate,
                'annual_growth_pct': annual_growth_rate,
                'trend': 'up' if b > 0 else 'down'
            }
        except Exception as e:
            logger.warning(f"指数回归失败: {e}")
            return {'type': 'exponential', 'error': str(e)}

    def logarithmic_regression(self, x: np.ndarray, y: np.ndarray) -> Dict:
        """
        对数回归: y = a * ln(x) + b

        Args:
            x: 时间序列索引 (从1开始)
            y: 价格序列

        Returns:
            回归结果字典
        """
        try:
            # x 从1开始，避免log(0)
            x_shifted = x + 1
            log_x = np.log(x_shifted)

            slope, intercept, r_value, p_value, std_err = stats.linregress(log_x, y)

            y_pred = slope * log_x + intercept
            residuals = y - y_pred
            rmse = np.sqrt(np.mean(residuals ** 2))

            return {
                'type': 'logarithmic',
                'formula': f'y = {slope:.4f} * ln(x+1) + {intercept:.4f}',
                'params': {'a': slope, 'b': intercept},
                'r_squared': r_value ** 2,
                'p_value': p_value,
                'rmse': rmse,
                'y_pred': y_pred,
                'residuals': residuals,
                'trend': 'up' if slope > 0 else 'down'
            }
        except Exception as e:
            logger.warning(f"对数回归失败: {e}")
            return {'type': 'logarithmic', 'error': str(e)}

    def analyze(self, symbol: str, days: int = 120,
                regression_type: str = 'all', degree: int = 2,
                adj: str = None) -> Dict:
        """
        执行回归分析

        Args:
            symbol: 股票/ETF代码
            days: 分析的历史天数
            regression_type: 回归类型 (linear/poly/exp/log/all)
            degree: 多项式阶数
            adj: 复权类型 ('qfq'=前复权, 'hfq'=后复权, None=不复权)

        Returns:
            分析结果字典
        """
        data = self.get_price_data(symbol, days, adj=adj)
        if data is None:
            return {'error': f'无法获取 {symbol} 的数据'}

        x = np.arange(len(data))
        y = data['close'].values

        result = {
            'symbol': symbol,
            'data_points': len(data),
            'start_date': str(data['date'].iloc[0])[:10] if 'date' in data.columns else 'N/A',
            'end_date': str(data['date'].iloc[-1])[:10] if 'date' in data.columns else 'N/A',
            'start_price': float(y[0]),
            'end_price': float(y[-1]),
            'price_change_pct': float((y[-1] - y[0]) / y[0] * 100),
            'max_price': float(np.max(y)),
            'min_price': float(np.min(y)),
            'volatility': float(np.std(np.diff(y) / y[:-1]) * np.sqrt(252) * 100),
            'adj_type': adj,  # 复权类型
            'regressions': {}
        }
        
        # 计算真实年化收益率（复利公式）
        try:
            # 计算时间跨度（年）
            if 'date' in data.columns:
                start_dt = pd.to_datetime(data['date'].iloc[0])
                end_dt = pd.to_datetime(data['date'].iloc[-1])
                years = (end_dt - start_dt).days / 365.25
            else:
                # 用交易日估算
                years = len(data) / 252
            
            if years > 0 and y[0] > 0:
                # 复利年化收益率 = (1 + 累计收益率)^(1/年数) - 1
                total_return = y[-1] / y[0]
                annual_return_cagr = (total_return ** (1 / years) - 1) * 100
                result['years'] = round(years, 2)
                result['annual_return_cagr'] = round(annual_return_cagr, 2)
            else:
                result['years'] = 0
                result['annual_return_cagr'] = 0
        except Exception as e:
            logger.warning(f"计算年化收益率失败: {e}")
            result['years'] = 0
            result['annual_return_cagr'] = 0

        # 执行回归分析
        if regression_type in ['linear', 'all']:
            result['regressions']['linear'] = self.linear_regression(x, y)

        if regression_type in ['poly', 'all']:
            result['regressions']['polynomial'] = self.polynomial_regression(x, y, degree)

        if regression_type in ['exp', 'all']:
            result['regressions']['exponential'] = self.exponential_regression(x, y)

        if regression_type in ['log', 'all']:
            result['regressions']['logarithmic'] = self.logarithmic_regression(x, y)

        # 找出最佳拟合
        best_fit = None
        best_r2 = -1
        for name, reg in result['regressions'].items():
            if 'error' not in reg and reg.get('r_squared', 0) > best_r2:
                best_r2 = reg['r_squared']
                best_fit = name

        result['best_fit'] = best_fit
        result['best_r_squared'] = best_r2

        # 计算偏离度分析（用于判断买卖时机）
        if best_fit and best_fit in result['regressions']:
            best_reg = result['regressions'][best_fit]
            if 'y_pred' in best_reg:
                y_pred = best_reg['y_pred']
                current_price = y[-1]
                fitted_price = y_pred[-1]
                
                # 当前偏离度 = (实际价格 - 拟合价格) / 拟合价格
                deviation = (current_price - fitted_price) / fitted_price * 100
                
                # 计算历史偏离度的统计
                historical_deviations = (y - y_pred) / y_pred * 100
                deviation_std = np.std(historical_deviations)
                deviation_mean = np.mean(historical_deviations)
                deviation_max = np.max(historical_deviations)
                deviation_min = np.min(historical_deviations)
                
                # 计算当前偏离的标准差倍数 (z-score)
                z_score = (deviation - deviation_mean) / deviation_std if deviation_std > 0 else 0
                
                # 判断信号
                if deviation < -deviation_std:
                    signal = 'BUY'  # 低于1个标准差，买入信号
                    signal_strength = abs(deviation / deviation_std)
                elif deviation > deviation_std:
                    signal = 'SELL'  # 高于1个标准差，卖出信号
                    signal_strength = abs(deviation / deviation_std)
                else:
                    signal = 'HOLD'  # 在正常范围内，持有
                    signal_strength = 0
                
                result['deviation_analysis'] = {
                    'current_price': current_price,
                    'fitted_price': round(fitted_price, 4),
                    'deviation_pct': round(deviation, 2),
                    'z_score': round(z_score, 2),
                    'deviation_std': round(deviation_std, 2),
                    'deviation_mean': round(deviation_mean, 2),
                    'deviation_max': round(deviation_max, 2),
                    'deviation_min': round(deviation_min, 2),
                    'signal': signal,
                    'signal_strength': round(signal_strength, 2),
                    'buy_zone': round(fitted_price * (1 - deviation_std / 100), 4),  # 买入区间上限
                    'sell_zone': round(fitted_price * (1 + deviation_std / 100), 4),  # 卖出区间下限
                }

        # 存储原始数据用于绘图
        result['x'] = x
        result['y'] = y
        result['dates'] = data['date'].values if 'date' in data.columns else x

        self.results = result
        return result

    def backtest_mean_reversion(self, result: Dict, threshold: float = 1.0, mode: str = 'global') -> Dict:
        """
        回测均值回归策略
        
        策略逻辑：
        - 当价格低于回归曲线 threshold 个标准差时买入
        - 当价格高于回归曲线 threshold 个标准差时卖出
        - 否则持有
        
        Args:
            result: 分析结果
            threshold: 触发买卖的标准差阈值 (默认1.0)
            mode: 回测模式 ('global'=全局回归, 'rolling'=滚动回归)
            
        Returns:
            回测结果
        """
        if 'error' in result:
            return {'error': result['error']}
        
        # 根据模式选择回测方法
        if mode == 'global':
            return self._backtest_global(result, threshold)
        else:  # rolling
            return self._backtest_rolling(result, threshold)
    
    def _backtest_rolling(self, result: Dict, threshold: float = 1.0) -> Dict:
        """滚动回归回测 - 使用 quant 框架"""
        try:
            # 导入 quant 回测框架
            from quant.strategies.mean_reversion_strategy import MeanReversionStrategy
            from quant.engines.backtest_executor import BacktestExecutor
            from quant.engines.backtest_analyzer import BacktestAnalyzer
            
            symbol = result.get('symbol', 'UNKNOWN')
            y = result['y']
            dates = result.get('dates', np.arange(len(y)))
            
            # 构建股票数据 DataFrame
            stock_data = pd.DataFrame({
                'close': y,
                'open': y,
                'high': y,
                'low': y,
                'volume': [0] * len(y)
            })
            
            # 设置日期索引
            try:
                stock_data.index = pd.to_datetime(dates)
            except:
                stock_data.index = pd.date_range(start='2020-01-01', periods=len(y), freq='D')
            
            # 创建策略
            strategy_config = {
                'threshold': threshold,
                'regression_type': result.get('best_fit', 'polynomial'),
                'degree': 2,
                'lookback': min(120, len(y) // 2)  # 回望期不超过数据一半
            }
            strategy = MeanReversionStrategy(symbol, strategy_config)
            
            # 使用 BacktestExecutor 执行回测
            executor = BacktestExecutor()
            initial_capital = 100000
            
            trades, portfolio_values, positions, cash_values = executor.execute(
                strategy=strategy,
                stock_data=stock_data,
                initial_capital=initial_capital
            )
            
            # 计算结果
            final_value = portfolio_values[-1] if portfolio_values else initial_capital
            strategy_return = (final_value - initial_capital) / initial_capital * 100
            buy_hold_return = (y[-1] - y[0]) / y[0] * 100
            
            # 计算年化收益
            years = result.get('years', len(y) / 252)
            if years > 0:
                strategy_cagr = ((final_value / initial_capital) ** (1 / years) - 1) * 100
                buy_hold_cagr = ((y[-1] / y[0]) ** (1 / years) - 1) * 100
            else:
                strategy_cagr = 0
                buy_hold_cagr = 0
            
            # 计算最大回撤
            peak = portfolio_values[0] if portfolio_values else initial_capital
            max_drawdown = 0
            for value in portfolio_values:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak * 100
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            # 获取策略性能指标
            perf_metrics = strategy.get_performance_metrics()
            
            # 格式化交易记录
            formatted_trades = []
            for trade in trades[:20]:
                formatted_trades.append({
                    'date': str(trade.get('timestamp', ''))[:10],
                    'action': trade.get('action', '').upper(),
                    'price': round(trade.get('price', 0), 4),
                    'deviation': round(trade.get('deviation', 0), 2),
                })
            
            return {
                'strategy_name': strategy.get_strategy_name(),
                'model_used': result.get('best_fit', 'polynomial').upper(),
                'threshold': threshold,
                'initial_capital': initial_capital,
                'final_value': round(final_value, 2),
                'strategy_return': round(strategy_return, 2),
                'strategy_cagr': round(strategy_cagr, 2),
                'buy_hold_return': round(buy_hold_return, 2),
                'buy_hold_cagr': round(buy_hold_cagr, 2),
                'excess_return': round(strategy_return - buy_hold_return, 2),
                'excess_cagr': round(strategy_cagr - buy_hold_cagr, 2),
                'total_trades': perf_metrics.get('total_trades', len(trades)),
                'round_trips': perf_metrics.get('round_trips', 0),
                'win_rate': round(perf_metrics.get('win_rate', 0), 2),
                'max_drawdown': round(max_drawdown, 2),
                'final_position': 'HOLDING' if positions[-1] > 0 else 'CASH' if positions else 'CASH',
                'trades': formatted_trades,
                'portfolio_values': portfolio_values,
                'using_quant_framework': True  # 标记使用了 quant 框架
            }
            
        except ImportError as e:
            logger.warning(f"无法导入 quant 回测框架: {e}，使用全局回归回测")
            return self._backtest_global(result, threshold)
        except Exception as e:
            logger.warning(f"quant 框架回测失败: {e}，使用全局回归回测")
            return self._backtest_global(result, threshold)
    
    def _backtest_global(self, result: Dict, threshold: float = 1.0) -> Dict:
        """全局回归回测（使用分析时计算的固定回归曲线）"""
        best_fit = result.get('best_fit')
        if not best_fit or best_fit not in result['regressions']:
            return {'error': '没有有效的回归模型'}
        
        y = result['y']
        y_pred = result['regressions'][best_fit]['y_pred']
        dates = result.get('dates', np.arange(len(y)))
        
        # 计算偏离度
        deviations = (y - y_pred) / y_pred * 100
        deviation_std = np.std(deviations)
        
        # 模拟交易
        initial_capital = 100000
        cash = initial_capital
        shares = 0
        trades = []
        portfolio_values = []
        in_position = False
        
        for i in range(len(y)):
            price = y[i]
            deviation = deviations[i]
            
            if deviation < -threshold * deviation_std and not in_position:
                shares = cash / price
                cash = 0
                in_position = True
                trades.append({
                    'date': str(dates[i])[:10] if hasattr(dates[i], 'strftime') or isinstance(dates[i], str) else f'Day {i}',
                    'action': 'BUY',
                    'price': round(price, 4),
                    'deviation': round(deviation, 2),
                })
            elif deviation > threshold * deviation_std and in_position:
                cash = shares * price
                shares = 0
                in_position = False
                trades.append({
                    'date': str(dates[i])[:10] if hasattr(dates[i], 'strftime') or isinstance(dates[i], str) else f'Day {i}',
                    'action': 'SELL',
                    'price': round(price, 4),
                    'deviation': round(deviation, 2),
                })
            
            portfolio_values.append(cash + shares * price)
        
        final_value = cash + shares * y[-1]
        strategy_return = (final_value - initial_capital) / initial_capital * 100
        buy_hold_return = (y[-1] - y[0]) / y[0] * 100
        
        years = result.get('years', len(y) / 252)
        strategy_cagr = ((final_value / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0
        buy_hold_cagr = ((y[-1] / y[0]) ** (1 / years) - 1) * 100 if years > 0 else 0
        
        # 计算胜率
        winning_trades = 0
        total_round_trips = 0
        buy_price = 0
        for trade in trades:
            if trade['action'] == 'BUY':
                buy_price = trade['price']
            elif trade['action'] == 'SELL' and buy_price > 0:
                total_round_trips += 1
                if trade['price'] > buy_price:
                    winning_trades += 1
                buy_price = 0
        
        win_rate = (winning_trades / total_round_trips * 100) if total_round_trips > 0 else 0
        
        # 计算最大回撤
        peak = portfolio_values[0]
        max_drawdown = 0
        for value in portfolio_values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return {
            'strategy_name': f'均值回归策略 (±{threshold}σ)',
            'model_used': best_fit.upper(),
            'threshold': threshold,
            'initial_capital': initial_capital,
            'final_value': round(final_value, 2),
            'strategy_return': round(strategy_return, 2),
            'strategy_cagr': round(strategy_cagr, 2),
            'buy_hold_return': round(buy_hold_return, 2),
            'buy_hold_cagr': round(buy_hold_cagr, 2),
            'excess_return': round(strategy_return - buy_hold_return, 2),
            'excess_cagr': round(strategy_cagr - buy_hold_cagr, 2),
            'total_trades': len(trades),
            'round_trips': total_round_trips,
            'win_rate': round(win_rate, 2),
            'max_drawdown': round(max_drawdown, 2),
            'final_position': 'HOLDING' if in_position else 'CASH',
            'trades': trades[:20],
            'portfolio_values': portfolio_values,
            'using_quant_framework': False
        }

    def predict(self, result: Dict, future_days: int = 5) -> Dict:
        """
        预测未来价格

        Args:
            result: 分析结果
            future_days: 预测天数

        Returns:
            预测结果
        """
        if 'error' in result:
            return {'error': result['error']}

        predictions = {}
        current_x = len(result['x'])
        future_x = np.arange(current_x, current_x + future_days)
        current_price = result['end_price']

        for name, reg in result['regressions'].items():
            if 'error' in reg:
                continue

            if name == 'linear':
                params = reg['params']
                pred = params['slope'] * future_x + params['intercept']
            elif name == 'polynomial':
                coeffs = reg['params']['coefficients']
                poly = np.poly1d(coeffs)
                pred = poly(future_x)
            elif name == 'exponential':
                params = reg['params']
                pred = params['a'] * np.exp(params['b'] * future_x)
            elif name == 'logarithmic':
                params = reg['params']
                pred = params['a'] * np.log(future_x + 1) + params['b']
            else:
                continue

            predictions[name] = {
                'predicted_prices': pred.tolist(),
                'predicted_change_pct': [(p - current_price) / current_price * 100 for p in pred],
                'final_price': float(pred[-1]),
                'final_change_pct': float((pred[-1] - current_price) / current_price * 100)
            }

        return {
            'current_price': current_price,
            'future_days': future_days,
            'predictions': predictions
        }


def print_analysis_result(result: Dict, verbose: bool = True):
    """打印分析结果"""
    if 'error' in result:
        print(f"❌ 分析失败: {result['error']}")
        return

    print(f"\n{'=' * 80}")
    print(f"📊 回归拟合分析报告: {result['symbol']}")
    print(f"{'=' * 80}")

    # 基本信息
    print(f"\n📈 数据概况:")
    print(f"   数据区间: {result['start_date']} 至 {result['end_date']}")
    print(f"   数据点数: {result['data_points']}")
    
    # 显示复权类型
    adj_type = result.get('adj_type')
    if adj_type == 'qfq':
        print(f"   复权类型: 🟢 前复权（含分红收益）")
    elif adj_type == 'hfq':
        print(f"   复权类型: 🟡 后复权")
    else:
        print(f"   复权类型: ⚪ 不复权（不含分红收益）")
    
    print(f"   起始价格: {result['start_price']:.4f}")
    print(f"   结束价格: {result['end_price']:.4f}")
    print(f"   区间涨跌: {result['price_change_pct']:+.2f}%")
    print(f"   最高价格: {result['max_price']:.4f}")
    print(f"   最低价格: {result['min_price']:.4f}")
    print(f"   年化波动率: {result['volatility']:.2f}%")
    
    # 显示真实年化收益率
    if 'annual_return_cagr' in result:
        years = result.get('years', 0)
        cagr = result.get('annual_return_cagr', 0)
        cagr_emoji = '🟢' if cagr > 0 else '🔴'
        print(f"\n   🎯 投资绩效 ({years:.2f} 年):")
        print(f"      累计收益率: {result['price_change_pct']:+.2f}%")
        print(f"      {cagr_emoji} 真实年化收益率 (CAGR): {cagr:+.2f}%")

    # 回归结果
    print(f"\n📐 回归拟合结果:")
    print(f"{'─' * 80}")

    for name, reg in result['regressions'].items():
        if 'error' in reg:
            print(f"\n   ❌ {name}: {reg['error']}")
            continue

        r2_emoji = '🎯' if reg['r_squared'] > 0.9 else '✅' if reg['r_squared'] > 0.7 else '⚠️'

        print(f"\n   {r2_emoji} {name.upper()} 回归:")
        print(f"      公式: {reg['formula']}")
        print(f"      R²: {reg['r_squared']:.4f} ({reg['r_squared']*100:.1f}% 拟合度)")
        print(f"      RMSE: {reg['rmse']:.4f}")

        if 'trend' in reg:
            trend_emoji = '📈' if reg['trend'] == 'up' else '📉'
            print(f"      趋势: {trend_emoji} {reg['trend']}")

        if 'annual_return_pct' in reg:
            ret = reg['annual_return_pct']
            ret_emoji = '🟢' if ret > 0 else '🔴'
            print(f"      年化收益率 (线性): {ret_emoji} {ret:+.2f}%")

        if 'annual_growth_pct' in reg:
            growth = reg['annual_growth_pct']
            growth_emoji = '🟢' if growth > 0 else '🔴'
            print(f"      年化增长率 (指数): {growth_emoji} {growth:+.2f}%")

        if 'curvature' in reg:
            print(f"      曲率特征: {reg['curvature']}")

    # 最佳拟合
    print(f"\n{'─' * 80}")
    print(f"🏆 最佳拟合模型: {result['best_fit'].upper()} (R² = {result['best_r_squared']:.4f})")
    
    # 偏离度分析和买卖信号
    if 'deviation_analysis' in result:
        da = result['deviation_analysis']
        print(f"\n{'─' * 80}")
        print(f"📍 偏离度分析 (基于{result['best_fit'].upper()}模型):")
        print(f"   当前价格: {da['current_price']:.4f}")
        print(f"   拟合价格: {da['fitted_price']:.4f}")
        
        dev = da['deviation_pct']
        dev_emoji = '📈' if dev > 0 else '📉' if dev < 0 else '➡️'
        print(f"   当前偏离: {dev_emoji} {dev:+.2f}% (Z-Score: {da['z_score']:.2f}σ)")
        print(f"   历史偏离范围: {da['deviation_min']:+.2f}% ~ {da['deviation_max']:+.2f}%")
        print(f"   偏离标准差: ±{da['deviation_std']:.2f}%")
        
        # 买卖区间
        print(f"\n   💰 参考价格区间:")
        print(f"      买入区 (低于): < {da['buy_zone']:.4f}")
        print(f"      持有区: {da['buy_zone']:.4f} ~ {da['sell_zone']:.4f}")
        print(f"      卖出区 (高于): > {da['sell_zone']:.4f}")
        
        # 信号
        signal = da['signal']
        strength = da['signal_strength']
        if signal == 'BUY':
            signal_emoji = '🟢'
            signal_text = f"买入信号 (强度: {strength:.1f}σ)"
            advice = "当前价格低于趋势线，可考虑适量买入"
        elif signal == 'SELL':
            signal_emoji = '🔴'
            signal_text = f"卖出信号 (强度: {strength:.1f}σ)"
            advice = "当前价格高于趋势线，可考虑适量卖出"
        else:
            signal_emoji = '🟡'
            signal_text = "持有/观望"
            advice = "当前价格在正常范围内，可持有观望"
        
        print(f"\n   {signal_emoji} 当前信号: {signal_text}")
        print(f"   💡 建议: {advice}")

    print(f"{'=' * 80}\n")


def print_backtest_result(bt_result: Dict):
    """打印回测结果"""
    if 'error' in bt_result:
        print(f"❌ 回测失败: {bt_result['error']}")
        return

    print(f"\n{'=' * 80}")
    print(f"📈 均值回归策略回测报告")
    print(f"{'=' * 80}")
    
    print(f"\n📋 策略配置:")
    print(f"   策略名称: {bt_result['strategy_name']}")
    print(f"   使用模型: {bt_result['model_used']}")
    print(f"   买卖阈值: ±{bt_result['threshold']}σ")
    print(f"   初始资金: ¥{bt_result['initial_capital']:,.0f}")
    
    print(f"\n💰 收益对比:")
    print(f"   {'─' * 50}")
    
    # 策略收益
    sr = bt_result['strategy_return']
    sc = bt_result['strategy_cagr']
    sr_emoji = '🟢' if sr > 0 else '🔴'
    print(f"   {sr_emoji} 均值回归策略:")
    print(f"      最终资产: ¥{bt_result['final_value']:,.0f}")
    print(f"      累计收益: {sr:+.2f}%")
    print(f"      年化收益: {sc:+.2f}%")
    
    # 买入持有基准
    bhr = bt_result['buy_hold_return']
    bhc = bt_result['buy_hold_cagr']
    bh_emoji = '🟢' if bhr > 0 else '🔴'
    print(f"\n   {bh_emoji} 买入持有基准:")
    print(f"      累计收益: {bhr:+.2f}%")
    print(f"      年化收益: {bhc:+.2f}%")
    
    # 超额收益
    er = bt_result['excess_return']
    ec = bt_result['excess_cagr']
    er_emoji = '✅' if er > 0 else '❌'
    print(f"\n   {er_emoji} 超额收益:")
    print(f"      累计超额: {er:+.2f}%")
    print(f"      年化超额: {ec:+.2f}%")
    
    print(f"\n📊 交易统计:")
    print(f"   总交易次数: {bt_result['total_trades']}")
    print(f"   完整买卖: {bt_result['round_trips']} 轮")
    print(f"   胜率: {bt_result['win_rate']:.1f}%")
    print(f"   最大回撤: {bt_result['max_drawdown']:.2f}%")
    print(f"   最终持仓: {'持有中' if bt_result['final_position'] == 'HOLDING' else '空仓'}")
    
    # 显示部分交易记录
    if bt_result.get('trades'):
        print(f"\n📝 交易记录 (前10笔):")
        print(f"   {'日期':<12} {'操作':<6} {'价格':<10} {'偏离度':<10}")
        print(f"   {'─' * 40}")
        for trade in bt_result['trades'][:10]:
            action_emoji = '🟢' if trade['action'] == 'BUY' else '🔴'
            print(f"   {trade['date']:<12} {action_emoji} {trade['action']:<4} {trade['price']:<10.4f} {trade['deviation']:+.2f}%")
    
    # 策略评价
    print(f"\n{'─' * 80}")
    if er > 5:
        print(f"🏆 策略评价: 优秀！均值回归策略显著跑赢买入持有")
    elif er > 0:
        print(f"✅ 策略评价: 良好，均值回归策略小幅跑赢买入持有")
    elif er > -5:
        print(f"🟡 策略评价: 一般，与买入持有表现相当")
    else:
        print(f"❌ 策略评价: 较差，不如直接买入持有")
    
    print(f"{'=' * 80}\n")


def print_prediction_result(pred_result: Dict):
    """打印预测结果"""
    if 'error' in pred_result:
        print(f"❌ 预测失败: {pred_result['error']}")
        return

    print(f"\n{'=' * 80}")
    print(f"🔮 未来 {pred_result['future_days']} 天价格预测")
    print(f"   当前价格: {pred_result['current_price']:.4f}")
    print(f"{'=' * 80}")

    for name, pred in pred_result['predictions'].items():
        print(f"\n   📊 {name.upper()} 模型预测:")
        print(f"      预测价格序列: {[f'{p:.4f}' for p in pred['predicted_prices']]}")
        print(f"      第{pred_result['future_days']}天预测: {pred['final_price']:.4f} "
              f"({pred['final_change_pct']:+.2f}%)")

    print(f"{'=' * 80}\n")


def plot_regression(result: Dict, save_path: Optional[str] = None):
    """绘制回归拟合图"""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from datetime import datetime

        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

        # 创建2x3的图表布局
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle(f'{result["symbol"]} 回归拟合分析\n{result["start_date"]} - {result["end_date"]}',
                     fontsize=16, fontweight='bold')

        x = result['x']
        y = result['y']
        raw_dates = result.get('dates', x)

        # 转换日期格式用于绘图
        try:
            dates = []
            for d in raw_dates:
                if hasattr(d, 'strftime'):
                    dates.append(d)
                elif isinstance(d, str):
                    # 尝试解析日期字符串
                    date_str = str(d)[:10].replace('-', '')
                    dates.append(datetime.strptime(date_str, '%Y%m%d'))
                else:
                    dates.append(d)
            dates = np.array(dates)
            use_dates = True
        except:
            dates = x
            use_dates = False

        plot_configs = [
            ('linear', '线性回归 (Linear)', axes[0, 0], 'blue'),
            ('polynomial', '多项式回归 (Polynomial)', axes[0, 1], 'green'),
            ('exponential', '指数回归 (Exponential)', axes[0, 2], 'red'),
            ('logarithmic', '对数回归 (Logarithmic)', axes[1, 0], 'purple')
        ]

        # 绘制4个单独的回归图
        for reg_name, title, ax, color in plot_configs:
            # 使用日期作为X轴
            x_plot = dates if use_dates else x
            
            # 绘制实际价格散点
            ax.scatter(x_plot, y, alpha=0.3, s=8, label='实际价格', color='gray')

            if reg_name in result['regressions'] and 'error' not in result['regressions'][reg_name]:
                reg = result['regressions'][reg_name]
                y_pred = reg['y_pred']
                r2 = reg['r_squared']

                # 绘制拟合曲线
                ax.plot(x_plot, y_pred, color=color, linewidth=2.5,
                       label=f'拟合曲线 (R²={r2:.4f})')

                # 填充置信区间
                ax.fill_between(x_plot, y_pred * 0.95, y_pred * 1.05, 
                               alpha=0.1, color=color)

                ax.set_title(f'{title}\nR² = {r2:.4f}', fontsize=11, fontweight='bold')
            else:
                ax.set_title(f'{title}\n(拟合失败)', fontsize=11)

            # 设置X轴日期格式
            if use_dates:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
                ax.set_xlabel('日期', fontsize=9)
            else:
                ax.set_xlabel('交易日序号', fontsize=9)
            
            ax.set_ylabel('价格', fontsize=9)
            ax.legend(loc='upper left', fontsize=8)
            ax.grid(True, alpha=0.3, linestyle='--')

        # 绘制综合对比图 (所有模型在一张图上)
        ax_combined = axes[1, 1]
        x_plot = dates if use_dates else x
        ax_combined.scatter(x_plot, y, alpha=0.4, s=15, label='实际价格', color='black', zorder=5)

        colors = {'linear': 'blue', 'polynomial': 'green', 
                  'exponential': 'red', 'logarithmic': 'purple'}
        names = {'linear': '线性', 'polynomial': '多项式', 
                 'exponential': '指数', 'logarithmic': '对数'}

        for reg_name, reg in result['regressions'].items():
            if 'error' not in reg:
                y_pred = reg['y_pred']
                r2 = reg['r_squared']
                ax_combined.plot(x_plot, y_pred, color=colors.get(reg_name, 'gray'), 
                               linewidth=2, label=f'{names.get(reg_name, reg_name)} (R²={r2:.3f})',
                               alpha=0.8)

        ax_combined.set_title('综合对比 (All Models)', fontsize=11, fontweight='bold')
        if use_dates:
            ax_combined.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax_combined.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
            plt.setp(ax_combined.xaxis.get_majorticklabels(), rotation=45, ha='right')
            ax_combined.set_xlabel('日期', fontsize=9)
        else:
            ax_combined.set_xlabel('交易日序号', fontsize=9)
        ax_combined.set_ylabel('价格', fontsize=9)
        ax_combined.legend(loc='upper left', fontsize=8)
        ax_combined.grid(True, alpha=0.3, linestyle='--')

        # 绘制最佳模型的残差图
        ax_residual = axes[1, 2]
        best_fit = result.get('best_fit', 'linear')
        if best_fit and best_fit in result['regressions'] and 'error' not in result['regressions'][best_fit]:
            best_reg = result['regressions'][best_fit]
            residuals = best_reg.get('residuals', y - best_reg['y_pred'])
            
            ax_residual.scatter(x_plot, residuals, alpha=0.5, s=10, color='steelblue')
            ax_residual.axhline(y=0, color='red', linestyle='--', linewidth=1.5)
            ax_residual.fill_between(x_plot, -best_reg['rmse'], best_reg['rmse'], 
                                    alpha=0.2, color='orange', label=f'±RMSE ({best_reg["rmse"]:.4f})')
            
            ax_residual.set_title(f'残差分析 ({names.get(best_fit, best_fit)}模型)', 
                                 fontsize=11, fontweight='bold')
            if use_dates:
                ax_residual.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                ax_residual.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
                plt.setp(ax_residual.xaxis.get_majorticklabels(), rotation=45, ha='right')
                ax_residual.set_xlabel('日期', fontsize=9)
            else:
                ax_residual.set_xlabel('交易日序号', fontsize=9)
            ax_residual.set_ylabel('残差 (实际-预测)', fontsize=9)
            ax_residual.legend(loc='upper right', fontsize=8)
            ax_residual.grid(True, alpha=0.3, linestyle='--')
        else:
            ax_residual.text(0.5, 0.5, '无法计算残差', ha='center', va='center', fontsize=12)
            ax_residual.set_title('残差分析', fontsize=11)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"✅ 图表已保存至: {save_path}")
        else:
            plt.show()

        plt.close()

    except ImportError:
        logger.warning("matplotlib 未安装，无法绘图")
    except Exception as e:
        logger.error(f"绘图失败: {e}")
        import traceback
        traceback.print_exc()


def save_results(result: Dict, output_path: Path):
    """保存分析结果"""
    # 移除无法序列化的numpy数组
    serializable = {k: v for k, v in result.items()
                   if k not in ['x', 'y', 'dates']}

    for name in serializable.get('regressions', {}):
        reg = serializable['regressions'][name]
        for key in ['y_pred', 'residuals']:
            if key in reg:
                reg[key] = reg[key].tolist() if hasattr(reg[key], 'tolist') else reg[key]

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"✅ 结果已保存至: {output_path}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='股票/ETF 回归拟合分析工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python bin/regression_analyzer.py 002594.SZ
  python bin/regression_analyzer.py 002594.SZ --type linear --days 60
  python bin/regression_analyzer.py 002594.SZ --type poly --degree 3
  python bin/regression_analyzer.py 002594.SZ --compare-all
  python bin/regression_analyzer.py 002594.SZ --predict 10 --plot --save
        """
    )

    parser.add_argument('symbol', help='股票/ETF代码')
    parser.add_argument('--days', type=int, default=120,
                       help='分析的历史数据天数 (默认: 120)')
    parser.add_argument('--type', choices=['linear', 'poly', 'exp', 'log', 'all'],
                       default='all', help='回归类型 (默认: all)')
    parser.add_argument('--degree', type=int, default=2,
                       help='多项式回归的阶数 (默认: 2)')
    parser.add_argument('--compare-all', action='store_true',
                       help='比较所有回归模型')
    parser.add_argument('--predict', type=int, metavar='DAYS',
                       help='预测未来N天的价格')
    parser.add_argument('--plot', action='store_true',
                       help='绘制回归拟合图')
    parser.add_argument('--save', action='store_true',
                       help='保存结果到文件')
    parser.add_argument('--provider', default='auto',
                       help='数据源 (tushare/yahoo/auto, 默认: auto)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='详细输出模式')
    parser.add_argument('--adj', choices=['qfq', 'hfq'],
                       help='复权类型 (qfq=前复权, hfq=后复权, 默认不复权)')
    parser.add_argument('--backtest', action='store_true',
                       help='回测均值回归策略')
    parser.add_argument('--threshold', type=float, default=1.0,
                       help='回测买卖阈值 (标准差倍数, 默认: 1.0)')
    parser.add_argument('--backtest-mode', choices=['global', 'rolling'], default='global',
                       help='回测模式: global=全局回归(默认), rolling=滚动回归')

    args = parser.parse_args()

    # 如果指定了 --compare-all，强制使用 all
    regression_type = 'all' if args.compare_all else args.type

    # 创建分析器
    logger.info("🚀 初始化回归分析器...")
    analyzer = RegressionAnalyzer(data_provider=args.provider)

    # 执行分析
    adj_label = '前复权' if args.adj == 'qfq' else '后复权' if args.adj == 'hfq' else '不复权'
    logger.info(f"📊 分析 {args.symbol}，周期 {args.days} 天，{adj_label}...")
    result = analyzer.analyze(
        symbol=args.symbol,
        days=args.days,
        regression_type=regression_type,
        degree=args.degree,
        adj=args.adj
    )

    # 打印结果
    print_analysis_result(result, verbose=args.verbose)

    # 回测均值回归策略
    if args.backtest and 'error' not in result:
        backtest_mode = getattr(args, 'backtest_mode', 'global')
        bt_result = analyzer.backtest_mean_reversion(
            result, 
            threshold=args.threshold, 
            mode=backtest_mode
        )
        print_backtest_result(bt_result)

    # 预测
    if args.predict and 'error' not in result:
        pred_result = analyzer.predict(result, future_days=args.predict)
        print_prediction_result(pred_result)

    # 绘图
    if args.plot and 'error' not in result:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        plot_path = project_root / 'reports' / f'{args.symbol}_regression_{timestamp}.png'
        plot_path.parent.mkdir(parents=True, exist_ok=True)
        plot_regression(result, save_path=str(plot_path) if args.save else None)

    # 保存结果
    if args.save and 'error' not in result:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = project_root / 'reports' / f'{args.symbol}_regression_{timestamp}.json'
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_results(result, output_path)

    logger.info("✅ 分析完成")
    return 0


if __name__ == '__main__':
    sys.exit(main())
