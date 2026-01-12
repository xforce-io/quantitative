#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
股票/ETF动能分析工具

提供单只或批量标的的短期动量分析，支持多种输出格式。

用法示例:
    # 单只标的分析
    python bin/momentum_analyzer.py 002594.SZ

    # 批量分析
    python bin/momentum_analyzer.py 002594.SZ 000001.SZ 510300.SH

    # 指定分析周期
    python bin/momentum_analyzer.py 002594.SZ --days 60

    # 保存为JSON
    python bin/momentum_analyzer.py 002594.SZ --output json --save

    # 简洁输出模式
    python bin/momentum_analyzer.py 002594.SZ 000001.SZ --compact

    # 对比模式（表格显示）
    python bin/momentum_analyzer.py 002594.SZ 000001.SZ 510300.SH --compare
"""

import sys
import os
import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import pandas as pd

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from quant.analysis.indicators.momentum_analyzer import ShortTermMomentumAnalyzer
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


def format_percentage(value, width=7):
    """格式化百分比显示"""
    if value is None:
        return ' ' * width
    color_prefix = '🟢' if value > 0 else '🔴' if value < 0 else '⚪'
    return f"{color_prefix} {value:+{width-2}.2f}%"


def format_signal_emoji(signal: str) -> str:
    """将信号文本转换为更直观的表情"""
    emoji_map = {
        '强势急涨': '🔥',
        '动量强劲': '🚀',
        '趋势向好': '🟢',
        '偏强': '🟡',
        '中性': '⚪',
        '偏弱': '🟠',
        '走弱': '🔴',
        '急跌': '⚫'
    }

    for key, emoji in emoji_map.items():
        if key in signal:
            return emoji
    return '📊'


def print_single_analysis(symbol: str, result: Dict, verbose: bool = True):
    """打印单个标的的分析结果（支持高级指标）"""
    if 'error' in result:
        logger.error(f"❌ {symbol} 分析失败: {result['error']}")
        return

    is_advanced = result.get('analysis_mode') == 'advanced'

    print(f"\n{'=' * 80}")
    print(f"📊 动能分析报告: {symbol} {'(增强版)' if is_advanced else ''}")
    print(f"{'=' * 80}")

    # 基本信息
    print(f"\n💰 最新价格: {result['latest_price']:.4f}")
    print(f"📅 数据日期: {result['latest_date']}")
    print(f"📈 数据点数: {result['data_points']}")

    # 各期收益率
    print(f"\n📊 各期收益率:")
    periods = [
        ('1d', '1日'),
        ('3d', '3日'),
        ('5d', '5日'),
        ('1w', '1周'),
        ('2w', '2周')
    ]

    for period_key, period_name in periods:
        ret = result.get(f'return_{period_key}')
        if ret is not None:
            print(f"   {period_name}: {format_percentage(ret)}")

    # 连续走势
    print(f"\n📈 连续走势:")
    if result.get('consecutive_up', 0) > 0:
        print(f"   🟢 连续上涨: {result['consecutive_up']} 天")
    elif result.get('consecutive_down', 0) > 0:
        print(f"   🔴 连续下跌: {result['consecutive_down']} 天")
    else:
        print(f"   ⚪ 无明显连续走势")

    # 成交量分析
    if result.get('volume_expansion'):
        print(f"\n📊 成交量分析:")
        vol_exp = result['volume_expansion']
        vol_emoji = '🔥' if vol_exp > 2 else '📈' if vol_exp > 1.5 else '📊' if vol_exp > 0.8 else '📉'
        print(f"   {vol_emoji} 近期放量: {vol_exp:.2f}x")

        avg_ratio = result.get('avg_volume_ratio', 0)
        ratio_emoji = '🔥' if avg_ratio > 2 else '📈' if avg_ratio > 1.2 else '📊' if avg_ratio > 0.8 else '📉'
        print(f"   {ratio_emoji} 今日量比: {avg_ratio:.2f}x")

    # === 高级指标显示（仅advanced模式） ===
    if is_advanced:
        # ADX 趋势强度
        adx = result.get('adx')
        if adx is not None:
            print(f"\n🎯 ADX 趋势强度:")
            adx_trend_map = {
                'strong_uptrend': '🚀 强势上涨趋势',
                'uptrend': '📈 上涨趋势',
                'strong_downtrend': '📉 强势下跌趋势',
                'downtrend': '📊 下跌趋势',
                'sideways': '➖ 横盘震荡'
            }
            adx_trend = result.get('adx_trend', 'unknown')
            adx_desc = adx_trend_map.get(adx_trend, adx_trend)
            print(f"   ADX: {adx:.1f} - {adx_desc}")

            plus_di = result.get('plus_di')
            minus_di = result.get('minus_di')
            if plus_di and minus_di:
                print(f"   +DI: {plus_di:.1f}, -DI: {minus_di:.1f}")

        # OBV 能量潮
        obv_signal = result.get('obv_signal')
        if obv_signal:
            print(f"\n💹 OBV 能量潮:")
            obv_emoji_map = {
                '强势上涨': '🔥',
                '蓄势待发': '💪',
                '正常': '📊',
                '量价背离': '⚠️'
            }
            obv_emoji = obv_emoji_map.get(obv_signal, '📊')
            print(f"   {obv_emoji} 信号: {obv_signal}")

        # MFI 资金流量
        mfi = result.get('mfi')
        if mfi is not None:
            print(f"\n💰 MFI 资金流量:")
            mfi_signal_map = {
                'overbought': '⚠️ 超买（资金大量流入）',
                'bullish': '🟢 资金流入',
                'bearish': '🔴 资金流出',
                'oversold': '🔵 超卖（资金大量流出）'
            }
            mfi_signal = result.get('mfi_signal', 'unknown')
            mfi_desc = mfi_signal_map.get(mfi_signal, mfi_signal)
            print(f"   MFI: {mfi:.1f} - {mfi_desc}")

        # EMA均线系统
        ema_system = result.get('ema_system')
        if ema_system and ema_system not in ['insufficient_data', 'error']:
            print(f"\n📏 EMA 均线系统:")
            ema_system_map = {
                'bullish_alignment': '🚀 完美多头排列',
                'above_ema20': '🟢 价格在短期均线之上',
                'bearish_alignment': '📉 空头排列',
                'below_ema20': '🔴 价格在短期均线之下',
                'neutral': '➖ 中性'
            }
            ema_desc = ema_system_map.get(ema_system, ema_system)
            print(f"   {ema_desc}")

            ema20 = result.get('ema20')
            ema60 = result.get('ema60')
            ema200 = result.get('ema200')
            if ema20 and ema60 and ema200:
                print(f"   EMA20: {ema20:.2f}, EMA60: {ema60:.2f}, EMA200: {ema200:.2f}")

        # 相对强度（RS Rating）
        relative_performance = result.get('relative_performance')
        if relative_performance is not None:
            print(f"\n📊 相对强度（vs 沪深300）:")
            rs_trend = result.get('rs_trend', 'unknown')
            rs_trend_map = {
                'strengthening': '💪 相对强度增强',
                'stable': '➖ 相对强度稳定',
                'weakening': '📉 相对强度减弱'
            }
            rs_desc = rs_trend_map.get(rs_trend, rs_trend)

            perf_emoji = '🟢' if relative_performance > 0 else '🔴'
            print(f"   {perf_emoji} 相对表现: {relative_performance:+.2f}%")
            print(f"   趋势: {rs_desc}")

        # 背离检测
        divergence_type = result.get('divergence_type', 'none')
        divergence_signal = result.get('divergence_signal')
        if divergence_type != 'none' and divergence_signal:
            print(f"\n⚠️  背离检测:")
            div_emoji = '🟢' if divergence_type == 'bullish' else '🔴'
            print(f"   {div_emoji} {divergence_signal}")

        # 动能生命周期
        lifecycle = result.get('momentum_lifecycle')
        if lifecycle:
            print(f"\n🔄 动能生命周期:")
            lifecycle_map = {
                'startup': '🌱 启动期：OBV先行，趋势形成',
                'explosive': '🚀 爆发期：动能强劲，主升浪',
                'accumulation': '📦 蓄积期：盘整蓄势',
                'decline': '📉 衰退期：顶背离，警惕回调',
                'weak': '😴 弱势期：动能不足',
                'unknown': '❓ 未知'
            }
            lifecycle_desc = lifecycle_map.get(lifecycle, lifecycle)
            print(f"   {lifecycle_desc}")

    # 突破信号
    if verbose:
        print(f"\n🎯 技术信号:")
        if result.get('breakout_high'):
            print(f"   🚀 突破20日高点!")
        elif result.get('breakout_low'):
            print(f"   📉 跌破20日低点!")
        else:
            print(f"   ➖ 未突破关键位")

    # 基础趋势分析
    trend_strength = result.get('trend_strength', 0)
    trend_direction = result.get('trend_direction', 'neutral')

    trend_emoji_map = {
        'strong_up': '🚀',
        'up': '📈',
        'neutral': '➖',
        'down': '📉',
        'strong_down': '📊'
    }
    trend_emoji = trend_emoji_map.get(trend_direction, '📊')

    print(f"\n📈 短期趋势:")
    print(f"   {trend_emoji} 趋势强度: {trend_strength:.2f}")
    print(f"   方向: {trend_direction}")

    # 综合评分和建议
    score = result.get('momentum_score', 50)
    signal = result.get('short_term_signal', '')
    signal_emoji = format_signal_emoji(signal)

    print(f"\n{'=' * 80}")
    print(f"💯 综合动量评分: {score}/100 {'(多因子模型)' if is_advanced else ''}")

    # 评分条形图
    filled = int(score / 5)
    bar = '█' * filled + '░' * (20 - filled)
    print(f"   [{bar}]")

    print(f"\n{signal_emoji} 操作建议: {signal}")
    print(f"{'=' * 80}\n")


def print_compact_analysis(symbol: str, result: Dict):
    """打印简洁版分析结果"""
    if 'error' in result:
        print(f"❌ {symbol:12s} | 分析失败: {result['error']}")
        return

    score = result.get('momentum_score', 50)
    ret_1w = result.get('return_1w', 0)
    signal = result.get('short_term_signal', '')
    signal_emoji = format_signal_emoji(signal)

    # 简洁一行输出
    print(f"{signal_emoji} {symbol:12s} | 评分: {score:3d}/100 | "
          f"周涨幅: {format_percentage(ret_1w, 7)} | {signal}")


def print_comparison_table(results: Dict[str, Dict]):
    """打印对比表格"""
    print(f"\n{'=' * 120}")
    print(f"{'标的代码':^12s} | {'评分':^5s} | {'1日':^8s} | {'3日':^8s} | {'5日':^8s} | "
          f"{'1周':^8s} | {'2周':^8s} | {'连涨':^4s} | {'连跌':^4s} | {'趋势':^12s} | {'信号':^15s}")
    print(f"{'-' * 120}")

    for symbol, result in results.items():
        if 'error' in result:
            print(f"{symbol:^12s} | {'数据获取失败':^100s}")
            continue

        score = result.get('momentum_score', 0)
        r1d = result.get('return_1d')
        r3d = result.get('return_3d')
        r5d = result.get('return_5d')
        r1w = result.get('return_1w')
        r2w = result.get('return_2w')

        consecutive_up = result.get('consecutive_up', 0)
        consecutive_down = result.get('consecutive_down', 0)

        trend = result.get('trend_direction', 'N/A')[:10]
        signal = result.get('short_term_signal', '')
        signal_emoji = format_signal_emoji(signal)

        # 格式化百分比
        def fmt_pct(v):
            if v is None:
                return '   --   '
            return f"{v:+6.2f}%"

        print(f"{symbol:^12s} | {score:^5d} | {fmt_pct(r1d):^8s} | {fmt_pct(r3d):^8s} | "
              f"{fmt_pct(r5d):^8s} | {fmt_pct(r1w):^8s} | {fmt_pct(r2w):^8s} | "
              f"{consecutive_up:^4d} | {consecutive_down:^4d} | {trend:^12s} | {signal_emoji} {signal[:10]}")

    print(f"{'=' * 120}\n")


def save_results(results: Dict[str, Dict], output_format: str, filename: str = None):
    """保存分析结果"""
    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"momentum_analysis_{timestamp}.{output_format}"

    output_path = project_root / 'reports' / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_format == 'json':
        # 保存为JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"✅ 结果已保存至: {output_path}")

    elif output_format == 'csv':
        # 转换为DataFrame并保存为CSV
        rows = []
        for symbol, result in results.items():
            if 'error' not in result:
                row = {
                    'symbol': symbol,
                    'date': result.get('latest_date'),
                    'price': result.get('latest_price'),
                    'momentum_score': result.get('momentum_score'),
                    'return_1d': result.get('return_1d'),
                    'return_3d': result.get('return_3d'),
                    'return_5d': result.get('return_5d'),
                    'return_1w': result.get('return_1w'),
                    'return_2w': result.get('return_2w'),
                    'consecutive_up': result.get('consecutive_up'),
                    'consecutive_down': result.get('consecutive_down'),
                    'volume_expansion': result.get('volume_expansion'),
                    'avg_volume_ratio': result.get('avg_volume_ratio'),
                    'trend_strength': result.get('trend_strength'),
                    'trend_direction': result.get('trend_direction'),
                    'signal': result.get('short_term_signal')
                }
                rows.append(row)

        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        logger.info(f"✅ 结果已保存至: {output_path}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='股票/ETF动能分析工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python bin/momentum_analyzer.py 002594.SZ
  python bin/momentum_analyzer.py 002594.SZ 000001.SZ 510300.SH --compare
  python bin/momentum_analyzer.py 002594.SZ --days 60 --save --output json
  python bin/momentum_analyzer.py 002594.SZ 000001.SZ --compact
        """
    )

    parser.add_argument('symbols', nargs='+', help='股票/ETF代码（支持多个）')
    parser.add_argument('--days', type=int, default=30,
                       help='分析的历史数据天数 (默认: 30)')
    parser.add_argument('--provider', default='auto',
                       help='数据源 (tushare/yahoo/auto, 默认: auto)')
    parser.add_argument('--compact', action='store_true',
                       help='简洁输出模式（一行一个标的）')
    parser.add_argument('--compare', action='store_true',
                       help='对比模式（表格显示所有标的）')
    parser.add_argument('--save', action='store_true',
                       help='保存结果到文件')
    parser.add_argument('--output', choices=['json', 'csv'], default='json',
                       help='输出格式 (json/csv, 默认: json)')
    parser.add_argument('--filename', help='指定输出文件名')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='详细输出模式')

    args = parser.parse_args()

    # 创建分析器
    logger.info("🚀 初始化动能分析器...")
    analyzer = ShortTermMomentumAnalyzer(data_provider=args.provider)

    # 批量分析
    results = {}
    logger.info(f"📊 开始分析 {len(args.symbols)} 个标的...")

    for symbol in args.symbols:
        logger.info(f"   分析 {symbol}...")
        result = analyzer.analyze_symbol(symbol, days=args.days)
        results[symbol] = result

    # 输出结果
    if args.compare and len(args.symbols) > 1:
        # 对比表格模式
        print_comparison_table(results)
    elif args.compact:
        # 简洁模式
        print(f"\n{'=' * 100}")
        print("动能分析结果（简洁模式）")
        print(f"{'=' * 100}")
        for symbol in args.symbols:
            print_compact_analysis(symbol, results[symbol])
        print(f"{'=' * 100}\n")
    else:
        # 详细模式
        for symbol in args.symbols:
            print_single_analysis(symbol, results[symbol], verbose=args.verbose)

    # 保存结果
    if args.save:
        save_results(results, args.output, args.filename)

    # 统计信息
    success_count = sum(1 for r in results.values() if 'error' not in r)
    logger.info(f"\n✅ 分析完成: {success_count}/{len(args.symbols)} 个标的成功")

    return 0


if __name__ == '__main__':
    sys.exit(main())
