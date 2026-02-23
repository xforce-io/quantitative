#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
箱体突破分析器 (Box Breakout Analyzer)

基于唐奇安通道的箱体突破检测与评分模型。

核心逻辑：
1. 使用 Donchian Channel 计算箱体上下轨（前一日值避免自我突破）
2. 检测收盘价是否突破箱体 + 成交量放大确认
3. 三因子加权评分：突破强度(40%) + 量能放大(30%) + 箱体紧度(30%)

适用场景：
- 从候选池中筛选出突破箱体整理区间的股票
- 配合量能确认，过滤假突破
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

# 确保项目路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from quant.core.logging_config import get_logger
from quant.core.indicators import TechnicalIndicators
from quant.analysis.base_scorer import ScorerMixin

logger = get_logger(__name__)


class BoxBreakoutAnalyzer:
    """
    箱体突破分析器

    基于唐奇安通道的箱体突破检测，支持批量扫描。
    """

    def __init__(self, data_provider: str = 'auto'):
        """
        初始化箱体突破分析器

        Args:
            data_provider: 数据源 ('auto', 'tushare', 'yahoo')
        """
        from quant.data_providers.data_provider_factory import createDataProvider
        self.provider = createDataProvider(data_provider)

    def analyze(self, symbol: str, period: int = 20, days: int = 120,
                volume_threshold: float = 1.5) -> Dict:
        """
        分析单个标的的箱体突破状态

        Args:
            symbol: 标的代码
            period: 箱体计算周期（天）
            days: 获取的历史数据天数
            volume_threshold: 放量确认倍数阈值

        Returns:
            分析结果字典
        """
        try:
            data = self._get_data(symbol, days)
            if data is None or len(data) < period + 5:
                return {
                    'symbol': symbol,
                    'error': f'数据不足，需要至少{period + 5}个交易日'
                            f'（当前:{len(data) if data is not None else 0}）'
                }

            return self.analyze_from_dataframe(data, symbol, period, volume_threshold)

        except Exception as e:
            logger.error(f"分析 {symbol} 箱体突破失败: {e}")
            return {'symbol': symbol, 'error': str(e)}

    def analyze_from_dataframe(self, df: pd.DataFrame, symbol: str = "unknown",
                                period: int = 20, volume_threshold: float = 1.5) -> Dict:
        """
        从 DataFrame 分析箱体突破（核心逻辑）

        Args:
            df: 包含 high, low, close, volume 列的 DataFrame
            symbol: 标的代码（仅用于结果标识）
            period: 箱体计算周期
            volume_threshold: 放量确认倍数阈值

        Returns:
            分析结果字典
        """
        required_cols = ['high', 'low', 'close', 'volume']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            return {'symbol': symbol, 'error': f'数据缺少必要列: {missing}'}

        if len(df) < period + 5:
            return {
                'symbol': symbol,
                'error': f'数据不足，需要至少{period + 5}个交易日（当前:{len(df)}）'
            }

        data = df.copy()

        # === Step 1: 计算箱体（唐奇安通道） ===
        donchian = TechnicalIndicators.calculate_donchian_channels(data, period)
        data['box_high'] = donchian['Donchian_High'].shift(1)  # 前一日值，避免自我突破
        data['box_low'] = donchian['Donchian_Low'].shift(1)

        # === Step 2: 计算量能指标 ===
        data['avg_volume'] = data['volume'].rolling(window=period).mean()
        data['volume_ratio'] = data['volume'] / data['avg_volume']

        # 取最新一行进行判断
        latest = data.iloc[-1]

        box_high = latest['box_high']
        box_low = latest['box_low']
        close = latest['close']
        volume_ratio = latest['volume_ratio']

        if pd.isna(box_high) or pd.isna(box_low) or pd.isna(volume_ratio):
            return {'symbol': symbol, 'error': '指标计算结果含空值，数据可能不足'}

        box_range_pct = (box_high - box_low) / box_low * 100 if box_low > 0 else 0

        # === Step 3: 检测突破（仅基于价格位置） ===
        breakout_type = 'none'
        breakout_pct = 0.0
        volume_confirmed = volume_ratio >= volume_threshold

        if close > box_high:
            breakout_type = 'up'
            breakout_pct = (close - box_high) / box_high * 100
        elif close < box_low:
            breakout_type = 'down'
            breakout_pct = (box_low - close) / box_low * 100

        # === Step 4: 三因子评分 (0-100) ===
        # 即使在箱体内，也计算一个"接近突破"的分数
        if breakout_type == 'none':
            # 箱体内：计算距离上轨的接近程度作为参考分
            if box_high > box_low:
                proximity = (close - box_low) / (box_high - box_low)  # 0~1
            else:
                proximity = 0.5
            # 箱体内给一个较低的基础分（0-30），体现"接近突破"的程度
            strength_score = proximity * 30
            volume_score = ScorerMixin.normalize_score(
                volume_ratio, min_val=0.5, max_val=3.0
            )
            tightness_score = ScorerMixin.normalize_score(
                box_range_pct, min_val=0, max_val=30, inverse=True
            )
            score = round(
                strength_score * 0.4 + volume_score * 0.3 + tightness_score * 0.3,
                1
            )
            # 箱体内分数上限 30，避免与真正突破混淆
            score = min(score, 30.0)
        else:
            # 因子1: 突破强度 (40%) — 突破幅度归一化到 0-100
            strength_score = ScorerMixin.normalize_score(
                breakout_pct, min_val=0, max_val=10  # 10%以上满分
            )

            # 因子2: 量能放大 (30%) — 量比归一化到 0-100
            volume_score = ScorerMixin.normalize_score(
                volume_ratio, min_val=0.5, max_val=5.0  # 0.5x起评，5x满分
            )

            # 因子3: 箱体紧度 (30%) — 越窄越好(inverse)
            tightness_score = ScorerMixin.normalize_score(
                box_range_pct, min_val=0, max_val=30,  # 30%以上最差
                inverse=True
            )

            score = round(
                strength_score * 0.4 + volume_score * 0.3 + tightness_score * 0.3,
                1
            )
            # 未放量确认的突破打折（×0.7），但仍显示为突破
            if not volume_confirmed:
                score = round(score * 0.7, 1)

        # === Step 5: 确定等级和建议 ===
        level, level_icon = self._determine_level(score, breakout_type, volume_confirmed)
        signals = self._generate_signals(breakout_type, breakout_pct, volume_ratio,
                                          box_range_pct, box_high, box_low,
                                          volume_confirmed, volume_threshold)
        recommendation = self._generate_recommendation(score, breakout_type, volume_confirmed)

        return {
            'symbol': symbol,
            'score': score,
            'breakout_type': breakout_type,
            'volume_confirmed': volume_confirmed,
            'box_high': round(box_high, 2),
            'box_low': round(box_low, 2),
            'box_range_pct': round(box_range_pct, 2),
            'latest_close': round(close, 2),
            'breakout_pct': round(breakout_pct, 2),
            'volume_ratio': round(volume_ratio, 2),
            'details': {
                'strength_score': round(strength_score, 1),
                'volume_score': round(volume_score, 1),
                'tightness_score': round(tightness_score, 1),
            },
            'signals': signals,
            'recommendation': recommendation,
            'level': level,
            'level_icon': level_icon,
            'data_points': len(data),
        }

    def scan_breakouts(self, symbols: List[str], period: int = 20, days: int = 120,
                        volume_threshold: float = 1.5,
                        proximity_pct: float = 0.0,
                        max_workers: int = 3) -> List[Dict]:
        """
        批量扫描箱体突破（并发执行）

        并发度故意控制在较低水平（默认 3），因为：
        - 两层缓存（CachedDataProvider 240h + 磁盘 1h）覆盖绝大多数请求
        - 只有首次无缓存时才真正调用 tushare API
        - 低并发确保不会触发 tushare 的频率限制

        Args:
            symbols: 标的代码列表
            period: 箱体计算周期
            days: 历史数据天数
            volume_threshold: 放量倍数阈值
            proximity_pct: 接近突破阈值（%），0 表示不启用
            max_workers: 并发线程数（默认 3，避免触发 tushare 限流）

        Returns:
            分析结果列表（按 score 降序排列）
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _analyze_one(symbol):
            return self.analyze(symbol, period, days, volume_threshold)

        results = []
        workers = min(max_workers, len(symbols))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_analyze_one, s): s for s in symbols}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    sym = futures[future]
                    logger.error(f"扫描 {sym} 异常: {e}")
                    results.append({'symbol': sym, 'error': str(e)})

        # 标记"接近突破"
        if proximity_pct > 0:
            for r in results:
                if r.get('breakout_type') == 'none' and 'box_high' in r and 'latest_close' in r:
                    box_high = r['box_high']
                    close = r['latest_close']
                    if box_high > 0:
                        distance = (box_high - close) / box_high * 100
                        if 0 < distance <= proximity_pct:
                            r['breakout_type'] = 'near_up'
                            r['breakout_pct'] = round(distance, 2)
                            r['level'] = '临近突破'
                            r['level_icon'] = '⏳'

        # 按评分降序排序（有 error 的排最后）
        results.sort(key=lambda x: x.get('score', -1), reverse=True)
        return results

    def _get_data(self, symbol: str, days: int) -> Optional[pd.DataFrame]:
        """获取股票数据"""
        try:
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')

            df = self.provider.getStockData(symbol, start_date, end_date)

            if df is not None and not df.empty:
                if 'trade_date' in df.columns:
                    df = df.sort_values('trade_date')
                else:
                    df = df.sort_index()
                return df.tail(days)
            return None

        except Exception as e:
            logger.error(f"获取 {symbol} 数据失败: {e}")
            return None

    @staticmethod
    def _determine_level(score: float, breakout_type: str, volume_confirmed: bool = True):
        """根据得分和突破类型确定等级"""
        if breakout_type == 'none':
            if score >= 20:
                return ('临近突破', '⏳')
            return ('箱体内', '📦')

        vol_tag = "" if volume_confirmed else "(缩量)"

        if breakout_type == 'up':
            if score >= 70:
                return (f'强势突破{vol_tag}', '🚀')
            elif score >= 50:
                return (f'有效突破{vol_tag}', '📈')
            elif score >= 30:
                return (f'弱突破{vol_tag}', '↗️')
            else:
                return (f'勉强突破{vol_tag}', '➡️')
        else:  # down
            if score >= 70:
                return (f'强势破位{vol_tag}', '💥')
            elif score >= 50:
                return (f'有效破位{vol_tag}', '📉')
            elif score >= 30:
                return (f'弱破位{vol_tag}', '↘️')
            else:
                return (f'勉强破位{vol_tag}', '➡️')

    @staticmethod
    def _generate_signals(breakout_type, breakout_pct, volume_ratio,
                           box_range_pct, box_high, box_low,
                           volume_confirmed=True, volume_threshold=1.5):
        """生成信号文字描述"""
        signals = []
        if breakout_type == 'up':
            signals.append(f"📈 向上突破箱体上轨 {box_high:.2f}，突破幅度 {breakout_pct:.2f}%")
        elif breakout_type == 'down':
            signals.append(f"📉 向下突破箱体下轨 {box_low:.2f}，突破幅度 {breakout_pct:.2f}%")
        else:
            signals.append(f"📦 价格在箱体内运行 ({box_low:.2f} ~ {box_high:.2f})")

        vol_status = "放量" if volume_confirmed else f"缩量(未达{volume_threshold:.1f}x)"
        signals.append(f"📊 成交量为均量的 {volume_ratio:.2f} 倍 — {vol_status}")
        signals.append(f"📐 箱体宽度 {box_range_pct:.2f}%")
        return signals

    @staticmethod
    def _generate_recommendation(score, breakout_type, volume_confirmed=True):
        """生成综合建议"""
        if breakout_type == 'none':
            if score >= 20:
                return "⏳ 价格接近箱体上轨，关注是否放量突破"
            return "📦 无突破信号，价格在箱体内运行，可关注后续方向选择"

        vol_warn = "" if volume_confirmed else "（注意：未放量确认，需观察后续量能）"

        if breakout_type == 'up':
            if score >= 70:
                return f"🟢 强势突破，可积极跟进，注意回踩确认{vol_warn}"
            elif score >= 50:
                return f"🟡 有效突破，可适度参与，关注量能持续性{vol_warn}"
            elif score >= 30:
                return f"⚪ 突破力度一般，建议等待回踩确认后再介入{vol_warn}"
            else:
                return f"⚠️ 勉强突破，箱体过宽或幅度不足{vol_warn}"
        else:
            if score >= 70:
                return f"🔴 强势破位，建议果断止损或回避{vol_warn}"
            elif score >= 50:
                return f"🟠 有效破位，建议减仓控制风险{vol_warn}"
            elif score >= 30:
                return f"⚪ 弱破位，可观察是否为假跌破{vol_warn}"
            else:
                return f"⚠️ 勉强破位，可能是假跌破{vol_warn}"


# ==================== 便捷函数 ====================

def get_box_breakout(symbol: str, period: int = 20, days: int = 120,
                      volume_threshold: float = 1.5) -> Dict:
    """
    便捷函数：获取单个标的的箱体突破分析

    Args:
        symbol: 标的代码
        period: 箱体周期
        days: 历史天数
        volume_threshold: 放量阈值

    Returns:
        箱体突破分析结果
    """
    analyzer = BoxBreakoutAnalyzer()
    return analyzer.analyze(symbol, period, days, volume_threshold)


def scan_box_breakouts(symbols: List[str], period: int = 20, days: int = 120,
                        volume_threshold: float = 1.5) -> List[Dict]:
    """
    便捷函数：批量扫描箱体突破

    Args:
        symbols: 标的代码列表
        period: 箱体周期
        days: 历史天数
        volume_threshold: 放量阈值

    Returns:
        分析结果列表（按评分降序）
    """
    analyzer = BoxBreakoutAnalyzer()
    return analyzer.scan_breakouts(symbols, period, days, volume_threshold)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    analyzer = BoxBreakoutAnalyzer()

    test_symbols = ['600519.SH', '000001.SZ', '300750.SZ']

    print("=" * 80)
    print("📦 箱体突破分析测试")
    print("=" * 80)

    for symbol in test_symbols:
        print(f"\n📊 {symbol}")
        print("-" * 60)

        result = analyzer.analyze(symbol)

        if 'error' in result:
            print(f"❌ 分析失败: {result['error']}")
            continue

        print(f"突破状态: {result['level_icon']} {result['level']} (评分: {result['score']})")
        print(f"突破类型: {result['breakout_type']}")
        print(f"最新价格: ¥{result['latest_close']}")
        print(f"箱体区间: {result['box_low']} ~ {result['box_high']} (宽度: {result['box_range_pct']}%)")
        print(f"突破幅度: {result['breakout_pct']}%")
        print(f"量比: {result['volume_ratio']}x")

        print(f"\n📋 评分明细:")
        details = result['details']
        print(f"  突破强度(40%): {details['strength_score']}")
        print(f"  量能放大(30%): {details['volume_score']}")
        print(f"  箱体紧度(30%): {details['tightness_score']}")

        print(f"\n📡 信号:")
        for sig in result['signals']:
            print(f"  {sig}")

        print(f"\n💡 建议: {result['recommendation']}")
