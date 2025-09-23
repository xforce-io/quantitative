#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
基础分析器 (Basic Analyzer)

提供基础的股票分析功能，整合自analyst中的重复功能
Provides basic stock analysis functionality, consolidating duplicated features from analyst
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

from ..core.indicators import TechnicalIndicators, add_technical_indicators
from ..core.metrics import PerformanceMetrics, calculate_performance_summary


class BasicAnalyzer:
    """基础分析器 - 提供股票基础分析功能"""
    
    def __init__(self):
        """初始化基础分析器"""
        self.indicators = TechnicalIndicators()
        self.metrics = PerformanceMetrics()
    
    def analyze_stock_characteristics(self, data: pd.DataFrame, symbol: str = "") -> Dict:
        """
        分析股票基本特征
        
        Args:
            data: 股价数据，包含OHLCV列
            symbol: 股票代码
            
        Returns:
            股票特征分析结果
        """
        if data.empty or 'close' not in data.columns:
            return {'error': '数据为空或缺少必要列'}
        
        # 添加技术指标
        data_with_indicators = add_technical_indicators(data)
        
        # 基本统计
        total_return = (data['close'].iloc[-1] / data['close'].iloc[0]) - 1
        annual_return = (1 + total_return) ** (252 / len(data)) - 1
        
        # 计算波动率
        daily_returns = data['close'].pct_change().dropna()
        volatility = daily_returns.std() * np.sqrt(252)
        
        # 计算最大回撤
        cummax = data['close'].expanding().max()
        drawdowns = (data['close'] - cummax) / cummax
        max_drawdown = drawdowns.min()
        
        # 夏普比率
        sharpe_ratio = (annual_return - 0.03) / volatility if volatility > 0 else 0.0
        
        # 价格特征
        price_range = (data['high'].max() - data['low'].min()) / data['close'].mean()
        avg_price = data['close'].mean()
        price_std = data['close'].std()
        price_cv = price_std / avg_price  # 变异系数
        
        # 交易量特征
        if 'volume' in data.columns:
            avg_volume = data['volume'].mean()
            volume_volatility = data['volume'].std() / avg_volume if avg_volume > 0 else 0.0
        else:
            avg_volume = 0
            volume_volatility = 0.0
        
        # 趋势强度（使用20日均线斜率）
        if 'MA20' in data_with_indicators.columns and len(data_with_indicators) > 20:
            ma20_start = data_with_indicators['MA20'].iloc[-21]
            ma20_end = data_with_indicators['MA20'].iloc[-1]
            if pd.notna(ma20_start) and pd.notna(ma20_end) and ma20_start != 0:
                trend_strength = abs(ma20_end - ma20_start) / ma20_start
            else:
                trend_strength = abs(total_return)
        else:
            trend_strength = abs(total_return)
        
        # RSI特征
        if 'RSI' in data_with_indicators.columns:
            rsi_avg = data_with_indicators['RSI'].mean()
            rsi_std = data_with_indicators['RSI'].std()
        else:
            rsi_avg = 50.0
            rsi_std = 0.0
        
        # 市场环境判断
        market_environment = self._judge_market_environment(total_return, volatility, trend_strength)
        
        characteristics = {
            'symbol': symbol,
            'analysis_date': datetime.now().strftime('%Y-%m-%d'),
            'data_points': len(data),
            'date_range': {
                'start': data.index[0].strftime('%Y-%m-%d') if hasattr(data.index[0], 'strftime') else str(data.index[0]),
                'end': data.index[-1].strftime('%Y-%m-%d') if hasattr(data.index[-1], 'strftime') else str(data.index[-1])
            },
            
            # 收益指标
            'total_return': total_return,
            'annual_return': annual_return,
            'daily_return_mean': daily_returns.mean(),
            
            # 风险指标
            'volatility': volatility,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'var_95': daily_returns.quantile(0.05),
            
            # 价格特征
            'price_range': price_range,
            'price_cv': price_cv,
            'avg_price': avg_price,
            'current_price': data['close'].iloc[-1],
            
            # 交易量特征
            'avg_volume': avg_volume,
            'volume_volatility': volume_volatility,
            
            # 技术指标特征
            'trend_strength': trend_strength,
            'rsi_avg': rsi_avg,
            'rsi_std': rsi_std,
            
            # 市场环境
            'market_environment': market_environment
        }
        
        return characteristics
    
    def _judge_market_environment(self, total_return: float, volatility: float, trend_strength: float) -> str:
        """判断市场环境"""
        if total_return > 0.2 and trend_strength > 0.3:
            return "强上涨趋势"
        elif total_return > 0.1 and trend_strength > 0.2:
            return "上涨趋势"
        elif total_return < -0.2 and trend_strength > 0.3:
            return "强下跌趋势"
        elif total_return < -0.1 and trend_strength > 0.2:
            return "下跌趋势"
        elif volatility > 0.4:
            return "高波动震荡"
        elif volatility > 0.2:
            return "中等波动震荡"
        else:
            return "低波动震荡"
    
    def analyze_position_in_history(self, data: pd.DataFrame, current_price: float = None, 
                                  historical_extremes: Dict = None) -> Dict:
        """
        分析当前位置在历史中的相对位置
        
        Args:
            data: 历史价格数据
            current_price: 当前价格，如果为None则使用最新收盘价
            historical_extremes: 历史极值配置 {'high': float, 'low': float}
            
        Returns:
            位置分析结果
        """
        if data.empty or 'close' not in data.columns:
            return {'error': '数据为空或缺少必要列'}
        
        if current_price is None:
            current_price = float(data['close'].iloc[-1])
        
        # 获取数据期间的最高最低
        data_high = float(data['high'].max()) if 'high' in data.columns else float(data['close'].max())
        data_low = float(data['low'].min()) if 'low' in data.columns else float(data['close'].min())
        
        # 使用历史极值（如果提供）
        hist_high = data_high
        hist_low = data_low
        
        if historical_extremes:
            hist_high = max(historical_extremes.get('high', data_high), data_high)
            hist_low = min(historical_extremes.get('low', data_low), data_low)
        
        # 计算位置百分比
        if hist_high != hist_low:
            position_pct = (current_price - hist_low) / (hist_high - hist_low) * 100
        else:
            position_pct = 50.0
        
        distance_to_high = (hist_high - current_price) / current_price * 100 if current_price > 0 else 0
        distance_to_low = (current_price - hist_low) / current_price * 100 if current_price > 0 else 0
        
        # 计算近期位置（52周/1年）
        if len(data) > 252:
            recent_data = data.tail(252)
        else:
            recent_data = data
            
        high_52w = float(recent_data['high'].max()) if 'high' in recent_data.columns else float(recent_data['close'].max())
        low_52w = float(recent_data['low'].min()) if 'low' in recent_data.columns else float(recent_data['close'].min())
        
        if high_52w != low_52w:
            position_52w = (current_price - low_52w) / (high_52w - low_52w) * 100
        else:
            position_52w = 50.0
        
        return {
            'current_price': current_price,
            'historical_high': hist_high,
            'historical_low': hist_low,
            'position_pct': position_pct,
            'distance_to_high_pct': distance_to_high,
            'distance_to_low_pct': distance_to_low,
            'high_52w': high_52w,
            'low_52w': low_52w,
            'position_52w': position_52w,
            'is_near_historical_high': position_pct > 85,
            'is_near_historical_low': position_pct < 15,
            'is_near_52w_high': position_52w > 85,
            'is_near_52w_low': position_52w < 15,
        }
    
    def calculate_technical_signals(self, data: pd.DataFrame) -> Dict:
        """
        计算技术信号
        
        Args:
            data: 股价数据
            
        Returns:
            技术信号分析结果
        """
        if data.empty or 'close' not in data.columns:
            return {'error': '数据为空或缺少必要列'}
        
        # 添加技术指标
        data_with_indicators = add_technical_indicators(data)
        
        if len(data_with_indicators) == 0:
            return {'error': '无法计算技术指标'}
        
        # 最新数据
        latest = data_with_indicators.iloc[-1]
        prev = data_with_indicators.iloc[-2] if len(data_with_indicators) > 1 else latest
        
        signals = {}
        
        # MA信号
        ma_signals = []
        ma_scores = 0
        
        for ma_period in [5, 10, 20, 50]:
            ma_col = f'MA{ma_period}'
            if ma_col in data_with_indicators.columns and pd.notna(latest[ma_col]):
                if latest['close'] > latest[ma_col]:
                    ma_signals.append(f"高于MA{ma_period}")
                    ma_scores += 1
                else:
                    ma_signals.append(f"低于MA{ma_period}")
        
        signals['ma_signals'] = ma_signals
        signals['ma_score'] = ma_scores
        
        # RSI信号
        if 'RSI' in data_with_indicators.columns and pd.notna(latest['RSI']):
            rsi = latest['RSI']
            if rsi > 70:
                rsi_signal = "超买"
            elif rsi < 30:
                rsi_signal = "超卖"
            else:
                rsi_signal = "中性"
            signals['rsi_signal'] = rsi_signal
            signals['rsi_value'] = rsi
        
        # MACD信号
        if all(col in data_with_indicators.columns for col in ['MACD', 'MACD_Signal']):
            if pd.notna(latest['MACD']) and pd.notna(latest['MACD_Signal']):
                if latest['MACD'] > latest['MACD_Signal']:
                    macd_signal = "金叉"
                else:
                    macd_signal = "死叉"
                signals['macd_signal'] = macd_signal
        
        # 布林带信号
        if all(col in data_with_indicators.columns for col in ['BB_Upper', 'BB_Lower']):
            if pd.notna(latest['BB_Upper']) and pd.notna(latest['BB_Lower']):
                if latest['close'] > latest['BB_Upper']:
                    bb_signal = "突破上轨"
                elif latest['close'] < latest['BB_Lower']:
                    bb_signal = "跌破下轨"
                else:
                    bb_signal = "轨道内运行"
                signals['bollinger_signal'] = bb_signal
        
        # 成交量信号
        if 'Volume_Ratio' in data_with_indicators.columns and pd.notna(latest['Volume_Ratio']):
            volume_ratio = latest['Volume_Ratio']
            if volume_ratio > 2.0:
                volume_signal = "成交量放大"
            elif volume_ratio < 0.5:
                volume_signal = "成交量萎缩"
            else:
                volume_signal = "成交量正常"
            signals['volume_signal'] = volume_signal
            signals['volume_ratio'] = volume_ratio
        
        # 综合信号评分
        total_score = ma_scores
        if 'rsi_signal' in signals:
            if signals['rsi_signal'] == "超卖":
                total_score += 1
            elif signals['rsi_signal'] == "超买":
                total_score -= 1
        
        if 'macd_signal' in signals and signals['macd_signal'] == "金叉":
            total_score += 1
        
        signals['total_score'] = total_score
        signals['max_score'] = 4  # MA(4) + RSI(1) 的最高分
        
        # 信号强度
        if total_score >= 4:
            signal_strength = "强买入"
        elif total_score >= 2:
            signal_strength = "买入"
        elif total_score <= -2:
            signal_strength = "卖出"
        else:
            signal_strength = "中性"
        
        signals['signal_strength'] = signal_strength
        
        return signals
    
    def generate_analysis_summary(self, characteristics: Dict, position_analysis: Dict, 
                                signals: Dict) -> str:
        """
        生成分析摘要报告
        
        Args:
            characteristics: 股票特征分析结果
            position_analysis: 位置分析结果
            signals: 技术信号分析结果
            
        Returns:
            格式化的分析报告
        """
        if not characteristics or 'error' in characteristics:
            return "无法生成分析报告：数据不足"
        
        symbol = characteristics.get('symbol', '未知')
        current_price = characteristics.get('current_price', 0)
        
        lines = [
            f"📊 {symbol} 股票分析报告",
            "=" * 60,
            f"📅 分析日期: {characteristics.get('analysis_date', 'N/A')}",
            f"💰 当前价格: ¥{current_price:.2f}",
            f"📈 数据期间: {characteristics.get('date_range', {}).get('start', 'N/A')} 至 {characteristics.get('date_range', {}).get('end', 'N/A')}",
            "",
            "📈 收益分析:",
            f"  总收益率: {characteristics.get('total_return', 0):.2%}",
            f"  年化收益率: {characteristics.get('annual_return', 0):.2%}",
            f"  日均收益率: {characteristics.get('daily_return_mean', 0):.4%}",
            "",
            "📉 风险分析:", 
            f"  年化波动率: {characteristics.get('volatility', 0):.2%}",
            f"  最大回撤: {characteristics.get('max_drawdown', 0):.2%}",
            f"  夏普比率: {characteristics.get('sharpe_ratio', 0):.3f}",
            f"  VaR(95%): {characteristics.get('var_95', 0):.4%}",
            "",
            f"🌍 市场环境: {characteristics.get('market_environment', '未知')}",
        ]
        
        # 添加位置分析
        if position_analysis and 'error' not in position_analysis:
            lines.extend([
                "",
                "📍 历史位置分析:",
                f"  历史位置: {position_analysis.get('position_pct', 0):.1f}% (历史区间)",
                f"  52周位置: {position_analysis.get('position_52w', 0):.1f}% (52周区间)", 
                f"  距历史高点: {position_analysis.get('distance_to_high_pct', 0):.1f}%",
                f"  距历史低点: {position_analysis.get('distance_to_low_pct', 0):.1f}%",
            ])
        
        # 添加技术信号
        if signals and 'error' not in signals:
            lines.extend([
                "",
                "🔍 技术信号分析:",
                f"  均线信号: {' | '.join(signals.get('ma_signals', []))}",
                f"  RSI信号: {signals.get('rsi_signal', 'N/A')} ({signals.get('rsi_value', 0):.1f})",
                f"  MACD信号: {signals.get('macd_signal', 'N/A')}",
                f"  成交量信号: {signals.get('volume_signal', 'N/A')}",
                f"  综合评分: {signals.get('total_score', 0)}/{signals.get('max_score', 0)}",
                f"  信号强度: {signals.get('signal_strength', 'N/A')}",
            ])
        
        lines.extend([
            "",
            "=" * 60
        ])
        
        return "\n".join(lines)
