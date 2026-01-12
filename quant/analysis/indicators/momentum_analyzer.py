#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
短期动量分析器（增强版）
采用"量、价、势、强"四维度多因子模型进行综合评估

新增高级指标：
- ADX (平均趋向指标) - 判断趋势强度
- OBV (能量潮) - 量价结合分析
- MFI (资金流量指标) - 资金流向分析
- RS Rating (相对强度) - 与大盘对比
- EMA均线系统 (20/60/200) - 多头排列判断
- 背离检测 - 牛市背离/顶背离识别
- 动能生命周期 - 启动期/爆发期/衰退期判断
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

from quant.core.logging_config import get_logger
logger = get_logger(__name__)



class ShortTermMomentumAnalyzer:
    def __init__(self, data_provider='auto', mode='advanced', benchmark='000300.SH'):
        """
        初始化短期动量分析器（增强版）

        Args:
            data_provider: 数据源 ('auto', 'tushare', 'yahoo')
            mode: 分析模式 ('simple', 'advanced') - 默认 advanced
            benchmark: 基准指数，用于相对强度分析 (默认沪深300)
        """
        self.data_provider = None
        self.mode = mode
        self.benchmark = benchmark

        if data_provider == 'auto':
            try:
                self.data_provider = DataProviderFactory.create('tushare', enableCache=True)
            except:
                self.data_provider = DataProviderFactory.create('yahoo', enableCache=True)
        else:
            self.data_provider = DataProviderFactory.create(data_provider, enableCache=True)
    
    def analyze_symbol(self, symbol: str, days: int = 30) -> Dict:
        """
        分析单个标的的短期动量（增强版）

        Args:
            symbol: 标的代码
            days: 分析的历史数据天数

        Returns:
            短期动量分析结果（包含高级指标）
        """
        try:
            # 获取数据
            data = self._get_recent_data(symbol, days)
            if data is None or len(data) < 5:
                return {'error': '数据不足'}

            # 基础信息
            analysis = {
                'symbol': symbol,
                'latest_price': float(data['close'].iloc[-1]),
                'latest_date': data.index[-1].strftime('%Y-%m-%d'),
                'data_points': len(data),
                'analysis_mode': self.mode
            }

            # === 基础指标（所有模式都计算） ===
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

            # === 高级指标（advanced 模式） ===
            if self.mode == 'advanced':
                # 6. ADX - 趋势强度判断
                analysis.update(self._calculate_adx(data))

                # 7. OBV - 能量潮分析
                analysis.update(self._calculate_obv(data))

                # 8. MFI - 资金流量指标
                analysis.update(self._calculate_mfi(data))

                # 9. EMA均线系统
                analysis.update(self._calculate_ema_system(data))

                # 10. 相对强度分析（与大盘对比）
                analysis.update(self._calculate_relative_strength(symbol, data, days))

                # 11. 背离检测
                analysis.update(self._detect_divergence(data))

            # === 综合评估 ===
            # 12. 综合动量评分（根据模式使用不同的评分算法）
            if self.mode == 'advanced':
                analysis['momentum_score'] = self._calculate_advanced_momentum_score(analysis)
            else:
                analysis['momentum_score'] = self._calculate_momentum_score(analysis)

            # 13. 短期操作建议
            analysis['short_term_signal'] = self._generate_short_term_signal(analysis)

            # 14. 动能生命周期（仅 advanced 模式）
            if self.mode == 'advanced':
                analysis['momentum_lifecycle'] = self._determine_momentum_lifecycle(analysis)

            return analysis

        except Exception as e:
            logger.error(f"分析失败 {symbol}: {e}")
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
            logger.info("获取数据失败 {symbol}: {e}")
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

    def _calculate_advanced_momentum_score(self, analysis: Dict) -> int:
        """
        多因子加权评分模型（"量、价、势、强"四维度）

        维度权重分配：
        - 价格动能 (30%): RSI, MACD, 涨跌幅
        - 成交量动能 (25%): OBV, MFI, 成交量放大
        - 趋势强度 (25%): ADX, EMA系统, 趋势方向
        - 相对强度 (20%): RS Rating, 相对表现
        """
        score = 0.0

        # ========== 1. 价格动能层 (30分) ==========
        price_score = 0.0

        # 一周收益率 (10分)
        week_return = analysis.get('return_1w', 0) or 0
        if week_return > 10:
            price_score += 10
        elif week_return > 5:
            price_score += 8
        elif week_return > 2:
            price_score += 6
        elif week_return > 0:
            price_score += 4
        elif week_return > -2:
            price_score += 2
        elif week_return > -5:
            price_score += 0
        elif week_return > -10:
            price_score -= 4
        else:
            price_score -= 8

        # 连续涨跌 (8分)
        consecutive_up = analysis.get('consecutive_up', 0)
        consecutive_down = analysis.get('consecutive_down', 0)

        if consecutive_up >= 5:
            price_score += 8
        elif consecutive_up >= 3:
            price_score += 6
        elif consecutive_up >= 1:
            price_score += 3

        if consecutive_down >= 5:
            price_score -= 8
        elif consecutive_down >= 3:
            price_score -= 6
        elif consecutive_down >= 1:
            price_score -= 3

        # 突破信号 (6分)
        if analysis.get('breakout_high'):
            price_score += 6
        elif analysis.get('breakout_low'):
            price_score -= 6

        # 背离检测 (6分)
        divergence_type = analysis.get('divergence_type', 'none')
        if divergence_type == 'bullish':
            price_score += 6  # 牛市背离：看涨
        elif divergence_type == 'bearish':
            price_score -= 6  # 顶背离：看跌

        # 价格动能层得分限制在0-30
        price_score = max(0, min(30, price_score))
        score += price_score

        # ========== 2. 成交量动能层 (25分) ==========
        volume_score = 0.0

        # OBV信号 (10分)
        obv_signal = analysis.get('obv_signal')
        if obv_signal == '强势上涨':
            volume_score += 10
        elif obv_signal == '蓄势待发':
            volume_score += 8
        elif obv_signal == '正常':
            volume_score += 5
        elif obv_signal == '量价背离':
            volume_score -= 5

        # MFI资金流量 (8分)
        mfi = analysis.get('mfi')
        if mfi is not None:
            if mfi > 80:
                volume_score += 8  # 资金大量流入
            elif mfi > 50:
                volume_score += 6  # 资金流入
            elif mfi > 30:
                volume_score += 3  # 中性
            elif mfi > 20:
                volume_score -= 3  # 资金流出
            else:
                volume_score -= 6  # 资金大量流出

        # 成交量放大 (7分)
        volume_expansion = analysis.get('volume_expansion')
        if volume_expansion is not None:
            if volume_expansion > 2:
                volume_score += 7
            elif volume_expansion > 1.5:
                volume_score += 5
            elif volume_expansion > 1:
                volume_score += 3
            elif volume_expansion < 0.5:
                volume_score -= 5
            elif volume_expansion < 0.8:
                volume_score -= 3

        volume_score = max(0, min(25, volume_score))
        score += volume_score

        # ========== 3. 趋势强度层 (25分) ==========
        trend_score = 0.0

        # ADX趋势强度 (10分)
        adx = analysis.get('adx')
        adx_trend = analysis.get('adx_trend', 'unknown')

        if adx is not None and adx > 25:
            if adx_trend == 'strong_uptrend':
                trend_score += 10
            elif adx_trend == 'uptrend':
                trend_score += 7
            elif adx_trend == 'strong_downtrend':
                trend_score -= 10
            elif adx_trend == 'downtrend':
                trend_score -= 7
            else:  # sideways
                trend_score += 3
        elif adx is not None and adx > 20:
            if 'up' in adx_trend:
                trend_score += 5
            elif 'down' in adx_trend:
                trend_score -= 5

        # EMA均线系统 (8分)
        ema_system = analysis.get('ema_system', 'neutral')
        if ema_system == 'bullish_alignment':
            trend_score += 8  # 完美多头排列
        elif ema_system == 'above_ema20':
            trend_score += 5  # 价格在短期均线之上
        elif ema_system == 'bearish_alignment':
            trend_score -= 8  # 空头排列
        elif ema_system == 'below_ema20':
            trend_score -= 5  # 价格在短期均线之下

        # 短期趋势强度 (7分)
        trend_strength = analysis.get('trend_strength', 0)
        if trend_strength > 2:
            trend_score += 7
        elif trend_strength > 1:
            trend_score += 5
        elif trend_strength > 0.3:
            trend_score += 3
        elif trend_strength < -2:
            trend_score -= 7
        elif trend_strength < -1:
            trend_score -= 5
        elif trend_strength < -0.3:
            trend_score -= 3

        trend_score = max(0, min(25, trend_score))
        score += trend_score

        # ========== 4. 相对强度层 (20分) ==========
        rs_score = 0.0

        # RS Rating (12分)
        rs_trend = analysis.get('rs_trend', 'unknown')
        relative_performance = analysis.get('relative_performance')

        if relative_performance is not None:
            if relative_performance > 10:
                rs_score += 12  # 远超大盘
            elif relative_performance > 5:
                rs_score += 10  # 明显超过大盘
            elif relative_performance > 2:
                rs_score += 7  # 略超大盘
            elif relative_performance > 0:
                rs_score += 5  # 跑赢大盘
            elif relative_performance > -2:
                rs_score += 3  # 略弱于大盘
            elif relative_performance > -5:
                rs_score -= 3  # 明显弱于大盘
            else:
                rs_score -= 6  # 远弱于大盘

        # RS趋势 (8分)
        if rs_trend == 'strengthening':
            rs_score += 8  # 相对强度增强
        elif rs_trend == 'stable':
            rs_score += 4  # 稳定
        elif rs_trend == 'weakening':
            rs_score -= 4  # 减弱

        rs_score = max(0, min(20, rs_score))
        score += rs_score

        # 最终得分限制在0-100之间
        final_score = int(max(0, min(100, score)))

        # 记录各维度得分（用于调试）
        logger.debug(f"Advanced scoring breakdown - Price: {price_score:.1f}, Volume: {volume_score:.1f}, "
                    f"Trend: {trend_score:.1f}, RS: {rs_score:.1f}, Total: {final_score}")

        return final_score

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

    # ==================== 高级指标计算方法 ====================

    def _calculate_adx(self, data: pd.DataFrame, period: int = 14) -> Dict:
        """
        计算ADX (Average Directional Index) 平均趋向指标

        ADX用于判断趋势强度：
        - ADX > 25: 强趋势
        - ADX < 20: 弱趋势或震荡
        - +DI > -DI: 上涨趋势
        - +DI < -DI: 下跌趋势
        """
        if len(data) < period + 1 or 'high' not in data.columns or 'low' not in data.columns:
            return {'adx': None, 'plus_di': None, 'minus_di': None, 'adx_trend': 'unknown'}

        try:
            # 计算TR (True Range)
            high_low = data['high'] - data['low']
            high_close = np.abs(data['high'] - data['close'].shift())
            low_close = np.abs(data['low'] - data['close'].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

            # 计算+DM和-DM
            high_diff = data['high'].diff()
            low_diff = -data['low'].diff()

            plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
            minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)

            # 计算平滑后的TR、+DM、-DM
            atr = tr.rolling(window=period).mean()
            plus_dm_smooth = plus_dm.rolling(window=period).mean()
            minus_dm_smooth = minus_dm.rolling(window=period).mean()

            # 计算+DI和-DI
            plus_di = 100 * (plus_dm_smooth / atr)
            minus_di = 100 * (minus_dm_smooth / atr)

            # 计算DX和ADX
            dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(window=period).mean()

            # 获取最新值
            current_adx = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else None
            current_plus_di = plus_di.iloc[-1] if not pd.isna(plus_di.iloc[-1]) else None
            current_minus_di = minus_di.iloc[-1] if not pd.isna(minus_di.iloc[-1]) else None

            # 判断趋势
            if current_adx is None:
                adx_trend = 'unknown'
            elif current_adx > 25:
                if current_plus_di > current_minus_di:
                    adx_trend = 'strong_uptrend'
                else:
                    adx_trend = 'strong_downtrend'
            elif current_adx > 20:
                if current_plus_di > current_minus_di:
                    adx_trend = 'uptrend'
                else:
                    adx_trend = 'downtrend'
            else:
                adx_trend = 'sideways'

            return {
                'adx': round(current_adx, 2) if current_adx else None,
                'plus_di': round(current_plus_di, 2) if current_plus_di else None,
                'minus_di': round(current_minus_di, 2) if current_minus_di else None,
                'adx_trend': adx_trend
            }
        except Exception as e:
            logger.debug(f"ADX计算失败: {e}")
            return {'adx': None, 'plus_di': None, 'minus_di': None, 'adx_trend': 'unknown'}

    def _calculate_obv(self, data: pd.DataFrame) -> Dict:
        """
        计算OBV (On-Balance Volume) 能量潮指标

        OBV是价格先行指标：
        - OBV上升 + 价格横盘 = 即将上涨
        - OBV下降 + 价格横盘 = 即将下跌
        - OBV创新高 = 上涨动能强
        """
        if len(data) < 20 or 'vol' not in data.columns:
            return {'obv': None, 'obv_trend': 'unknown', 'obv_signal': None}

        try:
            # 计算OBV
            price_change = data['close'].diff()
            obv = (np.sign(price_change) * data['vol']).fillna(0).cumsum()

            # 计算OBV的移动平均
            obv_ma = obv.rolling(window=10).mean()

            # 获取最新值
            current_obv = obv.iloc[-1]
            obv_20d_high = obv.iloc[-20:].max()
            obv_20d_low = obv.iloc[-20:].min()

            # 判断OBV趋势
            if current_obv >= obv_20d_high:
                obv_trend = 'new_high'
            elif current_obv <= obv_20d_low:
                obv_trend = 'new_low'
            elif obv.iloc[-1] > obv_ma.iloc[-1]:
                obv_trend = 'rising'
            elif obv.iloc[-1] < obv_ma.iloc[-1]:
                obv_trend = 'falling'
            else:
                obv_trend = 'neutral'

            # 生成信号
            price_trend = (data['close'].iloc[-1] - data['close'].iloc[-10]) / data['close'].iloc[-10]
            obv_change = (obv.iloc[-1] - obv.iloc[-10]) / abs(obv.iloc[-10]) if obv.iloc[-10] != 0 else 0

            if obv_trend in ['new_high', 'rising'] and price_trend < 0.02:
                obv_signal = '蓄势待发'
            elif obv_trend in ['new_low', 'falling'] and price_trend > -0.02:
                obv_signal = '量价背离'
            elif obv_trend == 'new_high':
                obv_signal = '强势上涨'
            else:
                obv_signal = '正常'

            return {
                'obv': float(current_obv),
                'obv_trend': obv_trend,
                'obv_signal': obv_signal
            }
        except Exception as e:
            logger.debug(f"OBV计算失败: {e}")
            return {'obv': None, 'obv_trend': 'unknown', 'obv_signal': None}

    def _calculate_mfi(self, data: pd.DataFrame, period: int = 14) -> Dict:
        """
        计算MFI (Money Flow Index) 资金流量指标

        MFI是"加了成交量权重的RSI"：
        - MFI > 80: 资金大量流入，动能极强（警惕超买）
        - MFI < 20: 资金大量流出，动能极弱（警惕超卖）
        - MFI上升 + 价格上涨 = 健康上涨
        - MFI下降 + 价格上涨 = 量价背离
        """
        if len(data) < period + 1 or 'vol' not in data.columns:
            return {'mfi': None, 'mfi_signal': 'unknown'}

        try:
            # 计算典型价格
            typical_price = (data['high'] + data['low'] + data['close']) / 3

            # 计算资金流量
            money_flow = typical_price * data['vol']

            # 区分正负资金流量
            positive_flow = money_flow.where(typical_price > typical_price.shift(), 0)
            negative_flow = money_flow.where(typical_price < typical_price.shift(), 0)

            # 计算资金流量比率
            positive_mf_sum = positive_flow.rolling(window=period).sum()
            negative_mf_sum = negative_flow.rolling(window=period).sum()

            # 计算MFI
            mf_ratio = positive_mf_sum / negative_mf_sum
            mfi = 100 - (100 / (1 + mf_ratio))

            current_mfi = mfi.iloc[-1] if not pd.isna(mfi.iloc[-1]) else None

            # 判断信号
            if current_mfi is None:
                mfi_signal = 'unknown'
            elif current_mfi > 80:
                mfi_signal = 'overbought'  # 超买但动能强
            elif current_mfi > 50:
                mfi_signal = 'bullish'  # 资金流入
            elif current_mfi > 20:
                mfi_signal = 'bearish'  # 资金流出
            else:
                mfi_signal = 'oversold'  # 超卖

            return {
                'mfi': round(current_mfi, 2) if current_mfi else None,
                'mfi_signal': mfi_signal
            }
        except Exception as e:
            logger.debug(f"MFI计算失败: {e}")
            return {'mfi': None, 'mfi_signal': 'unknown'}

    def _calculate_ema_system(self, data: pd.DataFrame) -> Dict:
        """
        计算EMA均线系统 (20/60/200)

        多头排列：EMA20 > EMA60 > EMA200 且价格在EMA20之上
        空头排列：EMA20 < EMA60 < EMA200 且价格在EMA20之下
        """
        if len(data) < 200:
            return {'ema_system': 'insufficient_data', 'ema20': None, 'ema60': None, 'ema200': None}

        try:
            ema20 = data['close'].ewm(span=20, adjust=False).mean()
            ema60 = data['close'].ewm(span=60, adjust=False).mean()
            ema200 = data['close'].ewm(span=200, adjust=False).mean()

            current_price = data['close'].iloc[-1]
            current_ema20 = ema20.iloc[-1]
            current_ema60 = ema60.iloc[-1]
            current_ema200 = ema200.iloc[-1]

            # 判断排列
            if current_price > current_ema20 > current_ema60 > current_ema200:
                ema_system = 'bullish_alignment'  # 多头排列
            elif current_price < current_ema20 < current_ema60 < current_ema200:
                ema_system = 'bearish_alignment'  # 空头排列
            elif current_price > current_ema20:
                ema_system = 'above_ema20'  # 价格在短期均线之上
            elif current_price < current_ema20:
                ema_system = 'below_ema20'  # 价格在短期均线之下
            else:
                ema_system = 'neutral'

            return {
                'ema_system': ema_system,
                'ema20': round(current_ema20, 2),
                'ema60': round(current_ema60, 2),
                'ema200': round(current_ema200, 2)
            }
        except Exception as e:
            logger.debug(f"EMA系统计算失败: {e}")
            return {'ema_system': 'error', 'ema20': None, 'ema60': None, 'ema200': None}

    def _calculate_relative_strength(self, symbol: str, data: pd.DataFrame, days: int) -> Dict:
        """
        计算RS Rating (相对强度)

        与基准指数对比，衡量超额收益能力：
        - RS > 1: 强于大盘
        - RS < 1: 弱于大盘
        - RS曲线上升: 相对强度增强
        """
        try:
            # 获取基准指数数据
            benchmark_data = self._get_recent_data(self.benchmark, days)
            if benchmark_data is None or len(benchmark_data) < 20:
                return {'rs_rating': None, 'rs_trend': 'unknown', 'relative_performance': None}

            # 对齐日期
            common_dates = data.index.intersection(benchmark_data.index)
            if len(common_dates) < 20:
                return {'rs_rating': None, 'rs_trend': 'unknown', 'relative_performance': None}

            symbol_prices = data.loc[common_dates, 'close']
            benchmark_prices = benchmark_data.loc[common_dates, 'close']

            # 计算相对强度 = 标的价格 / 基准价格
            rs = symbol_prices / benchmark_prices

            # 标准化（以第一个值为基准）
            rs_normalized = (rs / rs.iloc[0]) * 100

            current_rs = rs_normalized.iloc[-1]
            rs_20d_ago = rs_normalized.iloc[-20] if len(rs_normalized) >= 20 else rs_normalized.iloc[0]

            # 计算相对表现
            symbol_return = (symbol_prices.iloc[-1] / symbol_prices.iloc[0] - 1) * 100
            benchmark_return = (benchmark_prices.iloc[-1] / benchmark_prices.iloc[0] - 1) * 100
            relative_performance = symbol_return - benchmark_return

            # 判断趋势
            if current_rs > rs_20d_ago * 1.05:
                rs_trend = 'strengthening'  # 相对强度增强
            elif current_rs < rs_20d_ago * 0.95:
                rs_trend = 'weakening'  # 相对强度减弱
            else:
                rs_trend = 'stable'

            return {
                'rs_rating': round(current_rs, 2),
                'rs_trend': rs_trend,
                'relative_performance': round(relative_performance, 2)
            }
        except Exception as e:
            logger.debug(f"RS Rating计算失败: {e}")
            return {'rs_rating': None, 'rs_trend': 'unknown', 'relative_performance': None}

    def _detect_divergence(self, data: pd.DataFrame) -> Dict:
        """
        检测牛市背离和顶背离

        牛市背离（看涨）：价格创新低，但RSI/MACD底部抬高
        顶背离（看跌）：价格创新高，但RSI/MACD顶部降低
        """
        if len(data) < 30:
            return {'divergence_type': 'none', 'divergence_signal': None}

        try:
            # 计算RSI
            delta = data['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            # 找最近30天的价格和RSI的高低点
            recent_data = data.tail(30)
            recent_rsi = rsi.tail(30)

            # 找价格的峰谷
            price_peaks = []
            price_troughs = []
            for i in range(1, len(recent_data) - 1):
                if recent_data['close'].iloc[i] > recent_data['close'].iloc[i-1] and \
                   recent_data['close'].iloc[i] > recent_data['close'].iloc[i+1]:
                    price_peaks.append((i, recent_data['close'].iloc[i]))
                elif recent_data['close'].iloc[i] < recent_data['close'].iloc[i-1] and \
                     recent_data['close'].iloc[i] < recent_data['close'].iloc[i+1]:
                    price_troughs.append((i, recent_data['close'].iloc[i]))

            # 检测顶背离（价格新高，RSI降低）
            if len(price_peaks) >= 2:
                last_peak_idx, last_peak_price = price_peaks[-1]
                prev_peak_idx, prev_peak_price = price_peaks[-2]

                if last_peak_price > prev_peak_price and \
                   recent_rsi.iloc[last_peak_idx] < recent_rsi.iloc[prev_peak_idx]:
                    return {
                        'divergence_type': 'bearish',
                        'divergence_signal': '顶背离：价格新高但RSI降低，警惕回调'
                    }

            # 检测牛市背离（价格新低，RSI抬高）
            if len(price_troughs) >= 2:
                last_trough_idx, last_trough_price = price_troughs[-1]
                prev_trough_idx, prev_trough_price = price_troughs[-2]

                if last_trough_price < prev_trough_price and \
                   recent_rsi.iloc[last_trough_idx] > recent_rsi.iloc[prev_trough_idx]:
                    return {
                        'divergence_type': 'bullish',
                        'divergence_signal': '牛市背离：价格新低但RSI抬高，看涨信号'
                    }

            return {'divergence_type': 'none', 'divergence_signal': None}

        except Exception as e:
            logger.debug(f"背离检测失败: {e}")
            return {'divergence_type': 'none', 'divergence_signal': None}

    def _determine_momentum_lifecycle(self, analysis: Dict) -> str:
        """
        判断动能生命周期

        启动期：OBV先行，MACD零轴金叉
        爆发期：RSI > 70，ADX快速上升
        衰退期：价格新高，MACD红柱缩短（顶背离）
        """
        try:
            # 启动期特征
            obv_signal = analysis.get('obv_signal')
            adx = analysis.get('adx', 0)
            adx_trend = analysis.get('adx_trend')

            # 爆发期特征
            momentum_score = analysis.get('momentum_score', 50)
            mfi = analysis.get('mfi', 50)

            # 衰退期特征
            divergence_type = analysis.get('divergence_type')

            if divergence_type == 'bearish':
                return 'decline'  # 衰退期
            elif momentum_score >= 80 and (adx or 0) > 30:
                return 'explosive'  # 爆发期
            elif obv_signal in ['蓄势待发', '强势上涨'] and adx_trend in ['uptrend', 'strong_uptrend']:
                return 'startup'  # 启动期
            elif momentum_score < 30:
                return 'weak'  # 弱势期
            else:
                return 'accumulation'  # 蓄积期

        except Exception as e:
            logger.debug(f"生命周期判断失败: {e}")
            return 'unknown'


def main():
    """主函数 - 分析科创50和半导体ETF的短期动量"""
    analyzer = ShortTermMomentumAnalyzer()
    
    symbols = {
        '588000.SH': '科创50ETF',
        '159665.SZ': '半导体龙头ETF'
    }
    
    print("=" * 80)
    logger.info("🚀 短期动量分析报告")
    print("=" * 80)
    
    for symbol, name in symbols.items():
        logger.info("\n📊 {name} ({symbol})")
        print("-" * 60)
        
        result = analyzer.analyze_symbol(symbol, days=30)
        
        if 'error' in result:
            logger.info("❌ 分析失败: {result['error']}")
            continue
        
        # 基本信息
        logger.info("💰 最新价格: {result['latest_price']:.4f}")
        logger.info("📅 数据日期: {result['latest_date']}")
        
        # 各期收益率
        logger.info("\n📈 各期收益率:")
        periods = ['1d', '3d', '5d', '1w', '2w']
        for period in periods:
            ret = result.get(f'return_{period}')
            if ret is not None:
                color = "🟢" if ret > 0 else "🔴" if ret < 0 else "⚪"
                logger.info("   {period}: {color} {ret:+.2f}%")
        
        # 连续涨跌情况
        logger.info("\n📊 连续走势:")
        if result['consecutive_up'] > 0:
            logger.info("   🟢 连续上涨: {result['consecutive_up']} 天")
        elif result['consecutive_down'] > 0:
            logger.info("   🔴 连续下跌: {result['consecutive_down']} 天")
        else:
            logger.info("   ⚪ 无明显连续走势")
        
        # 成交量情况
        if result['volume_expansion']:
            logger.info("\n📊 成交量:")
            logger.info("   近期放量: {result['volume_expansion']:.2f}x")
            logger.info("   今日量比: {result['avg_volume_ratio']:.2f}x")
        
        # 突破情况
        if result['breakout_high']:
            logger.info("   🚀 突破20日高点!")
        elif result['breakout_low']:
            logger.info("   📉 跌破20日低点!")
        
        # 趋势强度
        trend_strength = result['trend_strength']
        direction = result['trend_direction']
        logger.info("\n📈 趋势分析:")
        logger.info("   强度得分: {trend_strength:.2f}")
        logger.info("   趋势方向: {direction}")
        
        # 综合评分和建议
        logger.info("\n🎯 短期动量评分: {result['momentum_score']}/100")
        logger.info("🎯 短期操作建议: {result['short_term_signal']}")


if __name__ == "__main__":
    main()
