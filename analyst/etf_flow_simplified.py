#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版ETF资金流向分析器 (Simplified ETF Capital Flow Analyzer)

基于日线成交量和价格数据分析ETF的资金流向特征
避免频繁调用分钟级API，使用已有的日线数据进行分析

核心功能:
1. 基于日线成交量-价格关系的资金流向分析
2. 成交量相对强度分析
3. 价量配合度评估
4. 资金流向趋势判断
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import warnings
warnings.filterwarnings('ignore')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class SimplifiedETFFlowAnalyzer:
    """简化版ETF资金流向分析器（基于日线数据）"""

    def __init__(self):
        """初始化分析器"""
        pass

    def analyze_etf_flow_from_daily(self, data: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """
        基于日线数据分析ETF资金流向

        Args:
            data: 日线数据DataFrame，包含close, volume, open, high, low等字段
            symbol: ETF代码

        Returns:
            Dict包含成交量活跃度、资金流向趋势、价量关系等指标
        """
        try:
            if data.empty or len(data) < 20:
                return self._get_empty_result("数据不足")

            # 1. 计算价格变化
            data = data.copy()
            data['price_change'] = data['close'] - data['open']
            data['price_change_pct'] = data['price_change'] / data['open'] * 100

            # 2. 成交量分析
            volume_analysis = self._analyze_daily_volume(data)

            # 3. 价量关系分析
            price_volume_relation = self._analyze_daily_price_volume(data)

            # 4. 资金流向趋势分析
            flow_trend = self._analyze_daily_flow_trend(data)

            # 5. 综合评分计算
            comprehensive_score = self._calculate_daily_flow_score(
                volume_analysis, price_volume_relation, flow_trend
            )

            return {
                'symbol': symbol,
                'analysis_method': '日线数据分析',
                'data_quality': {
                    'daily_records': len(data),
                    'analysis_period': f"{data.index[0].strftime('%Y-%m-%d')} 至 {data.index[-1].strftime('%Y-%m-%d')}"
                },
                'volume_analysis': volume_analysis,
                'price_volume_relation': price_volume_relation,
                'flow_trend': flow_trend,
                'comprehensive_score': comprehensive_score,
                'flow_signals': self._identify_daily_flow_signals(data),
                'investment_suggestion': self._generate_daily_suggestion(comprehensive_score, flow_trend)
            }

        except Exception as e:
            print(f"简化版ETF资金流分析失败 {symbol}: {str(e)}")
            return self._get_empty_result(f"分析失败: {str(e)}")

    def _analyze_daily_volume(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析日线成交量特征"""
        # 成交量统计
        recent_20d_vol = data['volume'].tail(20).mean()
        historical_avg_vol = data['volume'].mean()
        vol_std = data['volume'].std()
        vol_cv = vol_std / historical_avg_vol if historical_avg_vol > 0 else 0

        # 计算成交量移动平均
        data['vol_ma5'] = data['volume'].rolling(5).mean()
        data['vol_ma20'] = data['volume'].rolling(20).mean()

        # 成交量活跃度评估
        vol_ratio = recent_20d_vol / historical_avg_vol if historical_avg_vol > 0 else 1.0

        # 大成交量日占比（前20%）
        high_vol_threshold = data['volume'].quantile(0.8)
        high_vol_days = len(data[data['volume'] >= high_vol_threshold])
        high_vol_ratio = high_vol_days / len(data)

        # 活跃度等级判断
        if vol_ratio > 1.3 and high_vol_ratio > 0.25:
            activity_level = 'very_high'
        elif vol_ratio > 1.2 and high_vol_ratio > 0.2:
            activity_level = 'high'
        elif vol_ratio > 1.0 and high_vol_ratio > 0.15:
            activity_level = 'medium'
        elif vol_ratio > 0.8:
            activity_level = 'low'
        else:
            activity_level = 'very_low'

        return {
            'activity_level': activity_level,
            'recent_vs_avg_ratio': float(vol_ratio),
            'volume_volatility': float(vol_cv),
            'high_vol_ratio': float(high_vol_ratio),
            'avg_volume_20d': float(recent_20d_vol),
            'avg_volume_total': float(historical_avg_vol)
        }

    def _analyze_daily_price_volume(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析日线价量关系"""
        # 分别计算上涨和下跌日的平均成交量
        up_days = data[data['price_change'] > 0]
        down_days = data[data['price_change'] < 0]
        flat_days = data[data['price_change'] == 0]

        avg_vol_up = up_days['volume'].mean() if len(up_days) > 0 else 0
        avg_vol_down = down_days['volume'].mean() if len(down_days) > 0 else 0
        avg_vol_flat = flat_days['volume'].mean() if len(flat_days) > 0 else 0

        # 计算价量相关性
        correlation = data['price_change_pct'].corr(data['volume'])

        # 判断资金流向模式
        up_down_ratio = avg_vol_up / avg_vol_down if avg_vol_down > 0 else 1.0

        if up_down_ratio > 1.2:
            pattern = 'bullish'  # 上涨时放量
            pattern_desc = '上涨放量'
        elif up_down_ratio < 0.8:
            pattern = 'bearish'  # 下跌时放量
            pattern_desc = '下跌放量'
        else:
            pattern = 'neutral'  # 无明显差异
            pattern_desc = '价量平衡'

        # 大涨大跌日的成交量分析
        big_up_days = data[data['price_change_pct'] > 2.0]  # 涨幅超过2%
        big_down_days = data[data['price_change_pct'] < -2.0]  # 跌幅超过2%

        avg_vol_big_up = big_up_days['volume'].mean() if len(big_up_days) > 0 else 0
        avg_vol_big_down = big_down_days['volume'].mean() if len(big_down_days) > 0 else 0

        return {
            'correlation': float(correlation) if not pd.isna(correlation) else 0,
            'pattern': pattern,
            'pattern_desc': pattern_desc,
            'avg_vol_up_days': float(avg_vol_up),
            'avg_vol_down_days': float(avg_vol_down),
            'up_down_ratio': float(up_down_ratio),
            'up_days_count': len(up_days),
            'down_days_count': len(down_days),
            'big_move_analysis': {
                'big_up_days': len(big_up_days),
                'big_down_days': len(big_down_days),
                'avg_vol_big_up': float(avg_vol_big_up),
                'avg_vol_big_down': float(avg_vol_big_down)
            }
        }

    def _analyze_daily_flow_trend(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析资金流向趋势"""
        if len(data) < 30:
            return {'trend': 'unknown', 'strength': 0}

        # 计算不同周期的成交量均值对比
        recent_10d = data['volume'].tail(10).mean()
        recent_30d = data['volume'].tail(30).mean()
        historical_avg = data['volume'].head(len(data) - 30).mean()

        # 趋势强度计算
        short_trend_strength = (recent_10d - recent_30d) / recent_30d if recent_30d > 0 else 0
        long_trend_strength = (recent_30d - historical_avg) / historical_avg if historical_avg > 0 else 0

        # 趋势判断
        if short_trend_strength > 0.2 and long_trend_strength > 0.1:
            trend = 'strong_increasing'
            trend_desc = '成交量强劲递增'
        elif short_trend_strength > 0.1 or long_trend_strength > 0.1:
            trend = 'increasing'
            trend_desc = '成交量递增'
        elif short_trend_strength < -0.2 and long_trend_strength < -0.1:
            trend = 'strong_decreasing'
            trend_desc = '成交量显著递减'
        elif short_trend_strength < -0.1 or long_trend_strength < -0.1:
            trend = 'decreasing'
            trend_desc = '成交量递减'
        else:
            trend = 'stable'
            trend_desc = '成交量平稳'

        # 计算成交量趋势一致性（最近20天vs前20天）
        if len(data) >= 40:
            recent_20d = data['volume'].tail(20).mean()
            prev_20d = data['volume'].iloc[-40:-20].mean()
            consistency = (recent_20d - prev_20d) / prev_20d if prev_20d > 0 else 0
        else:
            consistency = 0

        return {
            'trend': trend,
            'trend_desc': trend_desc,
            'short_trend_strength': float(short_trend_strength),
            'long_trend_strength': float(long_trend_strength),
            'consistency': float(consistency),
            'recent_10d_avg': float(recent_10d),
            'recent_30d_avg': float(recent_30d),
            'historical_avg': float(historical_avg)
        }

    def _calculate_daily_flow_score(self, volume_analysis: Dict, price_volume_relation: Dict, flow_trend: Dict) -> float:
        """计算日线ETF资金流综合评分"""
        score = 0

        # 成交量活跃度评分 (40%)
        activity_scores = {
            'very_high': 40, 'high': 32, 'medium': 24, 'low': 16, 'very_low': 8
        }
        score += activity_scores.get(volume_analysis['activity_level'], 20)

        # 价量关系评分 (35%)
        if price_volume_relation['pattern'] == 'bullish':
            score += 35
        elif price_volume_relation['pattern'] == 'neutral':
            score += 25
        else:  # bearish
            score += 10

        # 资金流趋势评分 (25%)
        trend_scores = {
            'strong_increasing': 25, 'increasing': 20, 'stable': 15,
            'decreasing': 8, 'strong_decreasing': 3
        }
        score += trend_scores.get(flow_trend['trend'], 12)

        return min(100, max(0, score))

    def _identify_daily_flow_signals(self, data: pd.DataFrame) -> List[str]:
        """识别日线资金流向信号"""
        signals = []

        if data.empty:
            return signals

        recent_data = data.tail(10)  # 最近10天

        # 成交量异常放大信号
        recent_avg_vol = recent_data['volume'].mean()
        historical_avg_vol = data['volume'].mean()
        if recent_avg_vol > historical_avg_vol * 1.5:
            signals.append("近期成交量显著放大")

        # 连续放量上涨信号
        up_vol_days = recent_data[(recent_data['price_change'] > 0) & (recent_data['volume'] > historical_avg_vol)]
        if len(up_vol_days) >= 3:
            signals.append("连续放量上涨")

        # 价量背离信号
        recent_up_days = recent_data[recent_data['price_change'] > 0]
        if len(recent_up_days) >= 3:
            avg_up_vol = recent_up_days['volume'].mean()
            if avg_up_vol < historical_avg_vol * 0.8:
                signals.append("上涨缩量（可能为技术性反弹）")

        # 大幅波动伴随放量
        big_moves = recent_data[abs(recent_data['price_change_pct']) > 2.0]
        if len(big_moves) >= 2:
            avg_big_move_vol = big_moves['volume'].mean()
            if avg_big_move_vol > historical_avg_vol * 1.3:
                signals.append("大幅波动伴随放量")

        return signals

    def _generate_daily_suggestion(self, score: float, flow_trend: Dict) -> str:
        """生成基于日线数据的投资建议"""
        if score >= 80:
            suggestion = "资金流入强劲，适合积极配置"
        elif score >= 65:
            suggestion = "资金流入较好，可适度增持"
        elif score >= 50:
            suggestion = "资金流向中性，建议持有观望"
        elif score >= 35:
            suggestion = "资金流向偏弱，建议控制仓位"
        else:
            suggestion = "资金流向疲弱，建议谨慎操作"

        # 结合趋势调整建议
        trend = flow_trend.get('trend', 'stable')
        if trend in ['strong_decreasing', 'decreasing'] and score < 55:
            suggestion += "，注意规避风险"
        elif trend in ['strong_increasing', 'increasing'] and score > 60:
            suggestion += "，可考虑逐步加仓"

        return suggestion

    def _get_empty_result(self, reason: str) -> Dict[str, Any]:
        """返回空的分析结果"""
        return {
            'volume_analysis': {'activity_level': 'unknown'},
            'price_volume_relation': {'pattern': 'unknown', 'correlation': 0},
            'flow_trend': {'trend': 'unknown', 'strength': 0},
            'comprehensive_score': 0,
            'flow_signals': [],
            'investment_suggestion': '数据不足，无法分析',
            'error': reason
        }


def test_simplified_etf_analyzer():
    """测试简化版ETF资金流分析器"""
    print("🔄 测试简化版ETF资金流分析器...")
    
    # 创建测试数据
    dates = pd.date_range(start='2024-01-01', end='2024-09-01', freq='D')
    test_data = pd.DataFrame({
        'close': np.random.normal(100, 5, len(dates)),
        'open': np.random.normal(100, 5, len(dates)),
        'high': np.random.normal(105, 5, len(dates)),
        'low': np.random.normal(95, 5, len(dates)),
        'volume': np.random.normal(1000000, 300000, len(dates))
    }, index=dates)
    
    # 添加一些趋势性
    test_data['close'] = test_data['close'].cumsum() / 100 + 100
    test_data['volume'] = np.abs(test_data['volume'])
    
    analyzer = SimplifiedETFFlowAnalyzer()
    result = analyzer.analyze_etf_flow_from_daily(test_data, "TEST.ETF")
    
    if 'error' not in result:
        print("✅ 简化版ETF资金流分析成功")
        print(f"  成交量活跃度: {result['volume_analysis']['activity_level']}")
        print(f"  价量关系: {result['price_volume_relation']['pattern_desc']}")
        print(f"  资金流趋势: {result['flow_trend']['trend_desc']}")
        print(f"  综合评分: {result['comprehensive_score']:.0f}/100")
        print(f"  投资建议: {result['investment_suggestion']}")
        
        if result['flow_signals']:
            print(f"  流向信号: {'; '.join(result['flow_signals'])}")
    else:
        print(f"❌ 分析失败: {result['error']}")


if __name__ == '__main__':
    test_simplified_etf_analyzer()