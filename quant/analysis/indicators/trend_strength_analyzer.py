#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
趋势强度分析器 (Trend Strength Analyzer)

基于经典均线系统的多条件评分模型，评估当前趋势的强度。

评分标准（满分4分）：
1. 股价在20日均线上方 (+1分)
2. 20日均线上行 (+1分)
3. 60日均线上行 (+1分)
4. 20日均线在60日均线上方 (+1分)

技术依据：
- 多头排列理论：当短期均线在长期均线上方且均线都向上倾斜时，表明市场处于上升趋势
- 均线斜率：斜率越陡，趋势强度越高
- 价格与均线关系：价格持续在均线上方运行表明多头控盘
"""

import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd

# 确保项目路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from quant.core.logging_config import get_logger

logger = get_logger(__name__)


class TrendStrengthAnalyzer:
    """
    趋势强度分析器
    
    基于均线系统的四条件评分模型，返回 0-4 分的趋势强度评分。
    """
    
    def __init__(self, data_provider: str = 'auto'):
        """
        初始化趋势强度分析器
        
        Args:
            data_provider: 数据源 ('auto', 'tushare', 'yahoo')
        """
        from quant.data_providers.data_provider_factory import createDataProvider
        self.provider = createDataProvider(data_provider)
        
        # 评分权重配置（每条规则1分）
        self.criteria = {
            'price_above_ma20': {
                'name': '股价在20日均线上方',
                'weight': 1,
                'bullish_desc': '价格站稳短期均线',
                'bearish_desc': '价格跌破短期均线'
            },
            'ma20_trending_up': {
                'name': '20日均线上行',
                'weight': 1,
                'bullish_desc': '短期趋势向上',
                'bearish_desc': '短期趋势向下'
            },
            'ma60_trending_up': {
                'name': '60日均线上行',
                'weight': 1,
                'bullish_desc': '中期趋势向上',
                'bearish_desc': '中期趋势向下'
            },
            'ma20_above_ma60': {
                'name': '20日均线在60日均线上方',
                'weight': 1,
                'bullish_desc': '多头排列',
                'bearish_desc': '空头排列'
            }
        }
    
    def analyze(self, symbol: str, days: int = 90) -> Dict:
        """
        分析单个标的的趋势强度
        
        Args:
            symbol: 标的代码
            days: 获取的历史数据天数（需要足够计算60日均线）
        
        Returns:
            分析结果字典，包含：
            - score: 趋势强度评分 (0-4)
            - max_score: 最大可能分数 (4)
            - level: 趋势等级 (强势上涨/上涨/震荡/下跌/强势下跌)
            - details: 各条件的详细判断
            - signals: 信号文字描述列表
            - recommendation: 综合建议
        """
        try:
            # 获取数据
            data = self._get_data(symbol, days)
            if data is None or len(data) < 60:
                return {'error': f'数据不足，需要至少60个交易日（当前:{len(data) if data is not None else 0}）'}
            
            # 计算均线
            data = self._calculate_moving_averages(data)
            
            # 获取最新数据
            latest = data.iloc[-1]
            
            # 计算各条件
            details = {}
            score = 0
            signals = []
            
            # 条件1: 股价在20日均线上方
            price_above_ma20 = latest['close'] > latest['MA20']
            details['price_above_ma20'] = {
                'passed': price_above_ma20,
                'name': self.criteria['price_above_ma20']['name'],
                'value': f"收盘价 {latest['close']:.2f} vs MA20 {latest['MA20']:.2f}"
            }
            if price_above_ma20:
                score += self.criteria['price_above_ma20']['weight']
                signals.append(f"📈 {self.criteria['price_above_ma20']['bullish_desc']}")
            else:
                signals.append(f"📉 {self.criteria['price_above_ma20']['bearish_desc']}")
            
            # 条件2: 20日均线上行（对比5日前）
            ma20_slope = self._calculate_slope(data['MA20'].tail(10))
            ma20_trending_up = ma20_slope > 0
            details['ma20_trending_up'] = {
                'passed': ma20_trending_up,
                'name': self.criteria['ma20_trending_up']['name'],
                'value': f"斜率: {ma20_slope:.4f}"
            }
            if ma20_trending_up:
                score += self.criteria['ma20_trending_up']['weight']
                signals.append(f"📈 {self.criteria['ma20_trending_up']['bullish_desc']}")
            else:
                signals.append(f"📉 {self.criteria['ma20_trending_up']['bearish_desc']}")
            
            # 条件3: 60日均线上行
            ma60_slope = self._calculate_slope(data['MA60'].tail(10))
            ma60_trending_up = ma60_slope > 0
            details['ma60_trending_up'] = {
                'passed': ma60_trending_up,
                'name': self.criteria['ma60_trending_up']['name'],
                'value': f"斜率: {ma60_slope:.4f}"
            }
            if ma60_trending_up:
                score += self.criteria['ma60_trending_up']['weight']
                signals.append(f"📈 {self.criteria['ma60_trending_up']['bullish_desc']}")
            else:
                signals.append(f"📉 {self.criteria['ma60_trending_up']['bearish_desc']}")
            
            # 条件4: 20日均线在60日均线上方
            ma20_above_ma60 = latest['MA20'] > latest['MA60']
            details['ma20_above_ma60'] = {
                'passed': ma20_above_ma60,
                'name': self.criteria['ma20_above_ma60']['name'],
                'value': f"MA20 {latest['MA20']:.2f} vs MA60 {latest['MA60']:.2f}"
            }
            if ma20_above_ma60:
                score += self.criteria['ma20_above_ma60']['weight']
                signals.append(f"📈 {self.criteria['ma20_above_ma60']['bullish_desc']}")
            else:
                signals.append(f"📉 {self.criteria['ma20_above_ma60']['bearish_desc']}")
            
            # 确定趋势等级
            level, level_icon, level_color = self._determine_level(score)
            
            # 生成综合建议
            recommendation = self._generate_recommendation(score, details, ma20_slope, ma60_slope)
            
            return {
                'symbol': symbol,
                'score': score,
                'max_score': 4,
                'score_pct': score / 4 * 100,
                'level': level,
                'level_icon': level_icon,
                'level_color': level_color,
                'details': details,
                'signals': signals,
                'recommendation': recommendation,
                'latest_price': round(latest['close'], 2),
                'ma20': round(latest['MA20'], 2),
                'ma60': round(latest['MA60'], 2),
                'ma20_slope': round(ma20_slope, 4),
                'ma60_slope': round(ma60_slope, 4),
                'data_points': len(data)
            }
            
        except Exception as e:
            logger.error(f"分析 {symbol} 趋势强度失败: {e}")
            return {'error': str(e)}
    
    def analyze_from_dataframe(self, df: pd.DataFrame, symbol: str = "unknown") -> Dict:
        """
        从 DataFrame 分析趋势强度（用于已有数据的场景）
        
        Args:
            df: 包含 close 列的 DataFrame
            symbol: 标的代码（仅用于结果标识）
        
        Returns:
            分析结果字典
        """
        if df is None or len(df) < 60:
            return {'error': f'数据不足，需要至少60个交易日（当前:{len(df) if df is not None else 0}）'}
        
        # 确保有 close 列
        if 'close' not in df.columns:
            return {'error': '数据中缺少 close 列'}
        
        # 复制数据避免修改原始数据
        data = df.copy()
        
        # 计算均线
        data = self._calculate_moving_averages(data)
        
        # 获取最新数据
        latest = data.iloc[-1]
        
        # 计算各条件
        details = {}
        score = 0
        signals = []
        
        # 条件1: 股价在20日均线上方
        price_above_ma20 = latest['close'] > latest['MA20']
        details['price_above_ma20'] = {
            'passed': price_above_ma20,
            'name': self.criteria['price_above_ma20']['name'],
            'value': f"收盘价 {latest['close']:.2f} vs MA20 {latest['MA20']:.2f}"
        }
        if price_above_ma20:
            score += self.criteria['price_above_ma20']['weight']
            signals.append(f"📈 {self.criteria['price_above_ma20']['bullish_desc']}")
        else:
            signals.append(f"📉 {self.criteria['price_above_ma20']['bearish_desc']}")
        
        # 条件2: 20日均线上行
        ma20_slope = self._calculate_slope(data['MA20'].tail(10))
        ma20_trending_up = ma20_slope > 0
        details['ma20_trending_up'] = {
            'passed': ma20_trending_up,
            'name': self.criteria['ma20_trending_up']['name'],
            'value': f"斜率: {ma20_slope:.4f}"
        }
        if ma20_trending_up:
            score += self.criteria['ma20_trending_up']['weight']
            signals.append(f"📈 {self.criteria['ma20_trending_up']['bullish_desc']}")
        else:
            signals.append(f"📉 {self.criteria['ma20_trending_up']['bearish_desc']}")
        
        # 条件3: 60日均线上行
        ma60_slope = self._calculate_slope(data['MA60'].tail(10))
        ma60_trending_up = ma60_slope > 0
        details['ma60_trending_up'] = {
            'passed': ma60_trending_up,
            'name': self.criteria['ma60_trending_up']['name'],
            'value': f"斜率: {ma60_slope:.4f}"
        }
        if ma60_trending_up:
            score += self.criteria['ma60_trending_up']['weight']
            signals.append(f"📈 {self.criteria['ma60_trending_up']['bullish_desc']}")
        else:
            signals.append(f"📉 {self.criteria['ma60_trending_up']['bearish_desc']}")
        
        # 条件4: 20日均线在60日均线上方
        ma20_above_ma60 = latest['MA20'] > latest['MA60']
        details['ma20_above_ma60'] = {
            'passed': ma20_above_ma60,
            'name': self.criteria['ma20_above_ma60']['name'],
            'value': f"MA20 {latest['MA20']:.2f} vs MA60 {latest['MA60']:.2f}"
        }
        if ma20_above_ma60:
            score += self.criteria['ma20_above_ma60']['weight']
            signals.append(f"📈 {self.criteria['ma20_above_ma60']['bullish_desc']}")
        else:
            signals.append(f"📉 {self.criteria['ma20_above_ma60']['bearish_desc']}")
        
        # 确定趋势等级
        level, level_icon, level_color = self._determine_level(score)
        
        # 生成综合建议
        recommendation = self._generate_recommendation(score, details, ma20_slope, ma60_slope)
        
        return {
            'symbol': symbol,
            'score': score,
            'max_score': 4,
            'score_pct': score / 4 * 100,
            'level': level,
            'level_icon': level_icon,
            'level_color': level_color,
            'details': details,
            'signals': signals,
            'recommendation': recommendation,
            'latest_price': round(latest['close'], 2),
            'ma20': round(latest['MA20'], 2),
            'ma60': round(latest['MA60'], 2),
            'ma20_slope': round(ma20_slope, 4),
            'ma60_slope': round(ma60_slope, 4),
            'data_points': len(data)
        }
    
    def _get_data(self, symbol: str, days: int) -> Optional[pd.DataFrame]:
        """获取股票数据"""
        try:
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')
            
            # 使用 getStockData 方法（驼峰命名）
            df = self.provider.getStockData(symbol, start_date, end_date)
            
            if df is not None and not df.empty:
                # 确保数据按日期排序
                if 'trade_date' in df.columns:
                    df = df.sort_values('trade_date')
                else:
                    df = df.sort_index()
                return df.tail(days)
            return None
            
        except Exception as e:
            logger.error(f"获取 {symbol} 数据失败: {e}")
            return None
    
    def _calculate_moving_averages(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算移动平均线"""
        df = data.copy()
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['MA60'] = df['close'].rolling(window=60).mean()
        return df
    
    def _calculate_slope(self, series: pd.Series) -> float:
        """
        计算序列的斜率（标准化后的）
        
        使用线性回归斜率，并用均值标准化以便比较
        """
        if len(series) < 5:
            return 0.0
        
        valid_data = series.dropna()
        if len(valid_data) < 5:
            return 0.0
        
        x = np.arange(len(valid_data))
        y = valid_data.values
        
        # 线性回归
        slope = np.polyfit(x, y, 1)[0]
        
        # 标准化（除以均值）
        mean_val = y.mean()
        if mean_val != 0:
            normalized_slope = slope / mean_val
        else:
            normalized_slope = 0
        
        return normalized_slope
    
    def _determine_level(self, score: int) -> Tuple[str, str, str]:
        """
        根据得分确定趋势等级
        
        Returns:
            (等级名称, 图标, 颜色代码)
        """
        if score == 4:
            return ('强势上涨', '🔥', '#ff4444')
        elif score == 3:
            return ('上涨趋势', '📈', '#00cc66')
        elif score == 2:
            return ('震荡整理', '↔️', '#ffaa00')
        elif score == 1:
            return ('下跌趋势', '📉', '#ff8800')
        else:
            return ('强势下跌', '💨', '#cc0000')
    
    def _generate_recommendation(self, score: int, details: Dict, 
                                  ma20_slope: float, ma60_slope: float) -> str:
        """生成综合建议"""
        if score == 4:
            return "✅ 趋势强劲，短中期均线齐头向上，可积极持有或适度加仓"
        elif score == 3:
            if not details['price_above_ma20']['passed']:
                return "🟡 趋势偏强但价格回调至均线下方，可等待企稳后介入"
            elif not details['ma20_above_ma60']['passed']:
                return "🟡 短期趋势向好但中期排列尚未形成，注意持仓节奏"
            else:
                return "🟢 趋势中等偏强，可轻仓参与"
        elif score == 2:
            return "⚪ 趋势不明朗，震荡整理阶段，建议观望或减仓"
        elif score == 1:
            return "🟠 趋势偏弱，仅有一项条件满足，建议谨慎或回避"
        else:
            return "🔴 趋势极弱，四条件均不满足，建议回避或止损"


# 便捷函数
def get_trend_strength(symbol: str, days: int = 90) -> Dict:
    """
    便捷函数：获取标的趋势强度
    
    Args:
        symbol: 标的代码
        days: 分析天数
    
    Returns:
        趋势强度分析结果
    """
    analyzer = TrendStrengthAnalyzer()
    return analyzer.analyze(symbol, days)


def get_trend_strength_from_df(df: pd.DataFrame, symbol: str = "unknown") -> Dict:
    """
    便捷函数：从 DataFrame 获取趋势强度
    
    Args:
        df: 包含 close 列的价格数据
        symbol: 标的代码
    
    Returns:
        趋势强度分析结果
    """
    analyzer = TrendStrengthAnalyzer()
    return analyzer.analyze_from_dataframe(df, symbol)


if __name__ == "__main__":
    # 测试
    import logging
    logging.basicConfig(level=logging.INFO)
    
    analyzer = TrendStrengthAnalyzer()
    
    test_symbols = ['600519.SH', '000001.SZ', '300750.SZ']
    
    print("=" * 80)
    print("🎯 趋势强度分析测试")
    print("=" * 80)
    
    for symbol in test_symbols:
        print(f"\n📊 {symbol}")
        print("-" * 60)
        
        result = analyzer.analyze(symbol)
        
        if 'error' in result:
            print(f"❌ 分析失败: {result['error']}")
            continue
        
        print(f"趋势强度: {result['level_icon']} {result['level']} ({result['score']}/{result['max_score']})")
        print(f"最新价格: ¥{result['latest_price']}")
        print(f"MA20: {result['ma20']} (斜率: {result['ma20_slope']})")
        print(f"MA60: {result['ma60']} (斜率: {result['ma60_slope']})")
        print(f"\n📋 条件检查:")
        for key, detail in result['details'].items():
            status = "✅" if detail['passed'] else "❌"
            print(f"  {status} {detail['name']}: {detail['value']}")
        print(f"\n💡 建议: {result['recommendation']}")
