#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
短期动量分析器
专门分析最近几天/一周的急涨急跌信号，补充传统技术分析的不足
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from quant.data_providers.data_provider_factory import DataProviderFactory


class ShortTermMomentumAnalyzer:
    def __init__(self, data_provider='auto'):
        """初始化短期动量分析器"""
        self.data_provider = None
        
        if data_provider == 'auto':
            try:
                self.data_provider = DataProviderFactory.create('tushare', enableCache=True)
            except:
                self.data_provider = DataProviderFactory.create('yahoo', enableCache=True)
        else:
            self.data_provider = DataProviderFactory.create(data_provider, enableCache=True)
    
    def analyze_symbol(self, symbol: str, days: int = 30) -> Dict:
        """
        分析单个标的的短期动量
        
        Args:
            symbol: 标的代码
            days: 分析的历史数据天数
            
        Returns:
            短期动量分析结果
        """
        try:
            # 获取数据
            data = self._get_recent_data(symbol, days)
            if data is None or len(data) < 5:
                return {'error': '数据不足'}
            
            # 计算各种短期动量指标
            analysis = {
                'symbol': symbol,
                'latest_price': float(data['close'].iloc[-1]),
                'latest_date': data.index[-1].strftime('%Y-%m-%d'),
                'data_points': len(data)
            }
            
            # 1. 不同时期的涨跌幅
            analysis.update(self._calculate_period_returns(data))
            
            # 2. 连续上涨/下跌天数
            analysis.update(self._calculate_consecutive_moves(data))
            
            # 3. 成交量放大倍数
            analysis.update(self._calculate_volume_expansion(data))
            
            # 4. 价格突破情况
            analysis.update(self._calculate_breakout_signals(data))
            
            # 5. 短期趋势强度
            analysis.update(self._calculate_trend_strength(data))
            
            # 6. 综合动量评分
            analysis['momentum_score'] = self._calculate_momentum_score(analysis)
            
            # 7. 短期操作建议
            analysis['short_term_signal'] = self._generate_short_term_signal(analysis)
            
            return analysis
            
        except Exception as e:
            return {'error': str(e)}
    
    def _get_recent_data(self, symbol: str, days: int) -> Optional[pd.DataFrame]:
        """获取最近数据"""
        try:
            end = datetime.now()
            start = end - timedelta(days=days + 10)
            start_str = start.strftime('%Y%m%d')
            end_str = end.strftime('%Y%m%d')
            
            # 尝试不同的数据接口
            if self._is_fund_or_etf(symbol):
                df = self.data_provider.getFundData(symbol, start_str, end_str, 'D')
            elif self._is_global_index(symbol):
                df = self.data_provider.getGlobalIndexData(symbol, start_str, end_str, 'D')
            elif self._is_domestic_index(symbol):
                df = self.data_provider.getIndexData(symbol, start_str, end_str, 'D')
            else:
                df = self.data_provider.getStockData(symbol, start_str, end_str, 'D')
            
            return df.sort_index() if df is not None else None
            
        except Exception as e:
            print(f"获取数据失败 {symbol}: {e}")
            return None
    
    def _calculate_period_returns(self, data: pd.DataFrame) -> Dict:
        """计算不同时期的收益率"""
        returns = {}
        periods = {
            '1d': 1,
            '3d': 3, 
            '5d': 5,
            '1w': 7,
            '2w': 14
        }
        
        for period_name, period_days in periods.items():
            if len(data) > period_days:
                current_price = data['close'].iloc[-1]
                past_price = data['close'].iloc[-(period_days + 1)]
                period_return = (current_price / past_price - 1) * 100
                returns[f'return_{period_name}'] = round(period_return, 2)
            else:
                returns[f'return_{period_name}'] = None
        
        return returns
    
    def _calculate_consecutive_moves(self, data: pd.DataFrame) -> Dict:
        """计算连续上涨/下跌天数"""
        if len(data) < 2:
            return {'consecutive_up': 0, 'consecutive_down': 0}
        
        # 计算日收益率
        data['daily_return'] = data['close'].pct_change()
        
        consecutive_up = 0
        consecutive_down = 0
        
        # 从最新日期向前计算连续天数
        for i in range(len(data) - 1, 0, -1):
            daily_ret = data['daily_return'].iloc[i]
            if np.isnan(daily_ret):
                continue
                
            if daily_ret > 0:
                if consecutive_down > 0:  # 如果之前在下跌，停止计算
                    break
                consecutive_up += 1
            elif daily_ret < 0:
                if consecutive_up > 0:  # 如果之前在上涨，停止计算
                    break
                consecutive_down += 1
            else:  # 持平
                break
        
        return {
            'consecutive_up': consecutive_up,
            'consecutive_down': consecutive_down
        }
    
    def _calculate_volume_expansion(self, data: pd.DataFrame) -> Dict:
        """计算成交量放大情况"""
        if 'vol' not in data.columns or len(data) < 10:
            return {'volume_expansion': None, 'avg_volume_ratio': None}
        
        # 计算最近5天平均成交量 vs 之前10天平均成交量
        recent_vol = data['vol'].tail(5).mean()
        historical_vol = data['vol'].iloc[-15:-5].mean() if len(data) >= 15 else data['vol'].iloc[:-5].mean()
        
        if historical_vol > 0:
            volume_expansion = recent_vol / historical_vol
        else:
            volume_expansion = 1.0
        
        # 今日成交量 vs 平均成交量
        latest_vol = data['vol'].iloc[-1]
        avg_vol = data['vol'].tail(20).mean() if len(data) >= 20 else data['vol'].mean()
        avg_volume_ratio = latest_vol / avg_vol if avg_vol > 0 else 1.0
        
        return {
            'volume_expansion': round(volume_expansion, 2),
            'avg_volume_ratio': round(avg_volume_ratio, 2)
        }
    
    def _calculate_breakout_signals(self, data: pd.DataFrame) -> Dict:
        """计算突破信号"""
        if len(data) < 20:
            return {'breakout_high': False, 'breakout_low': False}
        
        # 计算20日高点和低点
        high_20 = data['high'].rolling(20).max()
        low_20 = data['low'].rolling(20).min()
        
        current_high = data['high'].iloc[-1]
        current_low = data['low'].iloc[-1]
        
        # 检查是否突破20日高点或低点
        breakout_high = current_high >= high_20.iloc[-2]  # 突破前一日的20日高点
        breakout_low = current_low <= low_20.iloc[-2]     # 跌破前一日的20日低点
        
        return {
            'breakout_high': bool(breakout_high),
            'breakout_low': bool(breakout_low)
        }
    
    def _calculate_trend_strength(self, data: pd.DataFrame) -> Dict:
        """计算短期趋势强度"""
        if len(data) < 10:
            return {'trend_strength': 0, 'trend_direction': 'neutral'}
        
        # 使用斜率计算趋势强度
        recent_data = data.tail(10)
        x = np.arange(len(recent_data))
        y = recent_data['close'].values
        
        # 计算线性回归斜率
        slope = np.polyfit(x, y, 1)[0]
        
        # 标准化斜率为强度得分
        avg_price = y.mean()
        trend_strength = (slope / avg_price) * 100 * 10  # 放大10倍便于理解
        
        if trend_strength > 1:
            trend_direction = 'strong_up'
        elif trend_strength > 0.3:
            trend_direction = 'up'
        elif trend_strength > -0.3:
            trend_direction = 'neutral'
        elif trend_strength > -1:
            trend_direction = 'down'
        else:
            trend_direction = 'strong_down'
        
        return {
            'trend_strength': round(trend_strength, 2),
            'trend_direction': trend_direction
        }
    
    def _calculate_momentum_score(self, analysis: Dict) -> int:
        """计算综合动量评分 (0-100)"""
        score = 50  # 基础分
        
        # 1. 一周收益率贡献 (±30分)
        week_return = analysis.get('return_1w')
        if week_return is not None:
            if week_return > 10:
                score += 30
            elif week_return > 5:
                score += 20
            elif week_return > 2:
                score += 10
            elif week_return > 0:
                score += 5
            elif week_return < -10:
                score -= 30
            elif week_return < -5:
                score -= 20
            elif week_return < -2:
                score -= 10
            else:
                score -= 5
        
        # 2. 连续上涨天数贡献 (±15分)
        consecutive_up = analysis.get('consecutive_up', 0)
        consecutive_down = analysis.get('consecutive_down', 0)
        
        if consecutive_up >= 5:
            score += 15
        elif consecutive_up >= 3:
            score += 10
        elif consecutive_up >= 1:
            score += 5
        
        if consecutive_down >= 5:
            score -= 15
        elif consecutive_down >= 3:
            score -= 10
        elif consecutive_down >= 1:
            score -= 5
        
        # 3. 成交量放大贡献 (±10分)
        volume_expansion = analysis.get('volume_expansion')
        if volume_expansion is not None:
            if volume_expansion > 2:
                score += 10
            elif volume_expansion > 1.5:
                score += 5
            elif volume_expansion < 0.5:
                score -= 10
            elif volume_expansion < 0.8:
                score -= 5
        
        # 4. 突破信号贡献 (±10分)
        if analysis.get('breakout_high'):
            score += 10
        elif analysis.get('breakout_low'):
            score -= 10
        
        # 5. 趋势强度贡献 (±15分)
        trend_strength = analysis.get('trend_strength', 0)
        if trend_strength > 2:
            score += 15
        elif trend_strength > 1:
            score += 10
        elif trend_strength > 0.5:
            score += 5
        elif trend_strength < -2:
            score -= 15
        elif trend_strength < -1:
            score -= 10
        elif trend_strength < -0.5:
            score -= 5
        
        return max(0, min(100, score))
    
    def _generate_short_term_signal(self, analysis: Dict) -> str:
        """生成短期操作信号"""
        score = analysis.get('momentum_score', 50)
        week_return = analysis.get('return_1w', 0) or 0
        consecutive_up = analysis.get('consecutive_up', 0)
        
        if score >= 80:
            if week_return > 8 or consecutive_up >= 5:
                return "🔥 短期强势急涨，注意高位风险"
            else:
                return "🚀 短期动量强劲，可追涨"
        elif score >= 70:
            return "🟢 短期趋势向好，适合持有"
        elif score >= 60:
            return "🟡 短期偏强，可轻仓参与"
        elif score >= 40:
            return "⚪ 短期中性，观望为主"
        elif score >= 30:
            return "🟠 短期偏弱，谨慎操作"
        elif score >= 20:
            return "🔴 短期走弱，考虑减仓"
        else:
            return "⚫ 短期急跌，回避为主"
    
    def _is_fund_or_etf(self, symbol: str) -> bool:
        """判断是否为基金ETF"""
        return (symbol.startswith('5') or symbol.startswith('1')) and ('SH' in symbol or 'SZ' in symbol)
    
    def _is_global_index(self, symbol: str) -> bool:
        """判断是否为全球指数"""
        return symbol.upper() in {'IXIC', 'NDX', 'SPX', 'DJI', 'HSI', 'HKTECH', 'HSCEI'}
    
    def _is_domestic_index(self, symbol: str) -> bool:
        """判断是否为国内指数"""
        return symbol in {'000300.SH', '000001.SH', '399001.SZ', '000016.SH', '399006.SZ'}


def main():
    """主函数 - 分析科创50和半导体ETF的短期动量"""
    analyzer = ShortTermMomentumAnalyzer()
    
    symbols = {
        '588000.SH': '科创50ETF',
        '159665.SZ': '半导体龙头ETF'
    }
    
    print("=" * 80)
    print("🚀 短期动量分析报告")
    print("=" * 80)
    
    for symbol, name in symbols.items():
        print(f"\n📊 {name} ({symbol})")
        print("-" * 60)
        
        result = analyzer.analyze_symbol(symbol, days=30)
        
        if 'error' in result:
            print(f"❌ 分析失败: {result['error']}")
            continue
        
        # 基本信息
        print(f"💰 最新价格: {result['latest_price']:.4f}")
        print(f"📅 数据日期: {result['latest_date']}")
        
        # 各期收益率
        print(f"\n📈 各期收益率:")
        periods = ['1d', '3d', '5d', '1w', '2w']
        for period in periods:
            ret = result.get(f'return_{period}')
            if ret is not None:
                color = "🟢" if ret > 0 else "🔴" if ret < 0 else "⚪"
                print(f"   {period}: {color} {ret:+.2f}%")
        
        # 连续涨跌情况
        print(f"\n📊 连续走势:")
        if result['consecutive_up'] > 0:
            print(f"   🟢 连续上涨: {result['consecutive_up']} 天")
        elif result['consecutive_down'] > 0:
            print(f"   🔴 连续下跌: {result['consecutive_down']} 天")
        else:
            print(f"   ⚪ 无明显连续走势")
        
        # 成交量情况
        if result['volume_expansion']:
            print(f"\n📊 成交量:")
            print(f"   近期放量: {result['volume_expansion']:.2f}x")
            print(f"   今日量比: {result['avg_volume_ratio']:.2f}x")
        
        # 突破情况
        if result['breakout_high']:
            print(f"   🚀 突破20日高点!")
        elif result['breakout_low']:
            print(f"   📉 跌破20日低点!")
        
        # 趋势强度
        trend_strength = result['trend_strength']
        direction = result['trend_direction']
        print(f"\n📈 趋势分析:")
        print(f"   强度得分: {trend_strength:.2f}")
        print(f"   趋势方向: {direction}")
        
        # 综合评分和建议
        print(f"\n🎯 短期动量评分: {result['momentum_score']}/100")
        print(f"🎯 短期操作建议: {result['short_term_signal']}")


if __name__ == "__main__":
    main()
