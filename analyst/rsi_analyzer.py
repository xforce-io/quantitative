#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RSI分析工具
基于StockStrategyAnalyzer的RSI专项分析
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Dict, List, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from analyst.stock_strategy_analyzer import StockStrategyAnalyzer

class RSIAnalyzer:
    """RSI专项分析器"""
    
    def __init__(self):
        self.analyzer = StockStrategyAnalyzer()
    
    def analyze_rsi(self, symbol: str, name: str = None) -> Optional[Dict]:
        """分析单只股票的RSI"""
        # 使用基础分析器加载数据
        self.analyzer.loadStockData(symbol)
        
        if self.analyzer.stockData is None or self.analyzer.stockData.empty:
            print(f"❌ 无法获取 {symbol} 的数据")
            return None
        
        # 获取RSI数据
        rsi_data = self.analyzer.stockData['RSI'].dropna()
        if rsi_data.empty:
            print(f"❌ {symbol} 无RSI数据")
            return None
        
        # 获取基本信息
        latest_rsi = rsi_data.iloc[-1]
        latest_price = self.analyzer.stockData['close'].iloc[-1]
        latest_date = self.analyzer.stockData.index[-1]
        
        # 确定股票名称
        if name is None:
            name = symbol
        
        # 显示分析结果
        print(f"\n🎯 {name} ({symbol}) RSI分析:")
        print("=" * 60)
        print(f"📅 数据日期: {latest_date.strftime('%Y-%m-%d')}")
        print(f"💰 最新价格: ¥{latest_price:.2f}")
        print(f"📊 当前RSI: {latest_rsi:.1f}")
        
        # RSI解读
        signal, action = self._interpret_rsi(latest_rsi)
        
        # 显示最近趋势
        self._show_rsi_trend(rsi_data, self.analyzer.stockData)
        
        # 交易建议
        self._show_trading_suggestions(signal, action)
        
        return {
            'symbol': symbol,
            'name': name,
            'date': latest_date,
            'price': latest_price,
            'rsi': latest_rsi,
            'signal': signal,
            'action': action
        }
    
    def _interpret_rsi(self, rsi_value: float) -> tuple:
        """解读RSI值"""
        print(f"\n📈 RSI指标解读:")
        print("-" * 40)
        
        if rsi_value >= 70:
            print("🔴 RSI ≥ 70 - 超买状态")
            print("💡 操作建议: 谨慎追高，考虑减仓或观望")
            return "超买", "减仓/观望"
        elif rsi_value >= 50:
            print("🟡 RSI 50-70 - 强势区间")
            print("💡 操作建议: 可适量持有，关注回调机会")
            return "强势", "持有"
        elif rsi_value >= 30:
            print("🟢 RSI 30-50 - 中性区间")
            print("💡 操作建议: 均衡配置，等待明确信号")
            return "中性", "均衡配置"
        else:
            print("🔵 RSI ≤ 30 - 超卖状态")
            print("💡 操作建议: 考虑逢低买入机会")
            return "超卖", "逢低买入"
    
    def _show_rsi_trend(self, rsi_data: pd.Series, stock_data: pd.DataFrame):
        """显示RSI趋势"""
        print(f"\n📊 最近5天RSI趋势:")
        print("-" * 40)
        
        # 获取最近5天数据
        recent_rsi = rsi_data.tail(5)
        recent_dates = stock_data.index[-5:]
        recent_prices = stock_data['close'].tail(5)
        
        for i, (date, price, rsi_val) in enumerate(zip(recent_dates, recent_prices, recent_rsi)):
            if i == len(recent_rsi) - 1:
                print(f"📅 {date.strftime('%m-%d')} | ¥{price:.2f} | RSI: {rsi_val:.1f} ← 最新")
            else:
                print(f"📅 {date.strftime('%m-%d')} | ¥{price:.2f} | RSI: {rsi_val:.1f}")
        
        # 计算RSI变化趋势
        if len(recent_rsi) >= 2:
            rsi_change = recent_rsi.iloc[-1] - recent_rsi.iloc[-2]
            print(f"\n📈 RSI变化: {rsi_change:+.1f} (较前一日)")
            
            if rsi_change > 1:
                print("📈 RSI上升趋势，动量增强")
            elif rsi_change < -1:
                print("📉 RSI下降趋势，动量减弱")
            else:
                print("➡️ RSI变化较小，维持现状")
    
    def _show_trading_suggestions(self, signal: str, action: str):
        """显示交易建议"""
        print(f"\n💡 基于RSI的交易策略:")
        print("-" * 40)
        
        if signal == "超买":
            print("🔴 超买信号 - 短线风险较高")
            print("  📋 建议操作:")
            print("  • 已持有：考虑分批减仓")
            print("  • 空仓：等待回调至RSI 50以下")
            print("  • 止损：设置在最近支撑位")
        
        elif signal == "强势":
            print("🟡 强势信号 - 上升趋势中")
            print("  📋 建议操作:")
            print("  • 已持有：可继续持有，关注RSI 70")
            print("  • 空仓：可在回调时适量介入")
            print("  • 止损：设置在RSI 45以下")
        
        elif signal == "中性":
            print("🟢 中性信号 - 方向不明")
            print("  📋 建议操作:")
            print("  • 已持有：观望为主")
            print("  • 空仓：等待RSI突破30或70")
            print("  • 止损：根据技术面设置")
        
        elif signal == "超卖":
            print("🔵 超卖信号 - 可能存在反弹机会")
            print("  📋 建议操作:")
            print("  • 已持有：可考虑补仓")
            print("  • 空仓：关注RSI回升至35以上")
            print("  • 止损：设置在前低位置")
    
    def analyze_multiple_stocks(self, stocks: List[tuple]) -> List[Dict]:
        """分析多只股票的RSI"""
        results = []
        
        for symbol, name in stocks:
            result = self.analyze_rsi(symbol, name)
            if result:
                results.append(result)
            print("\n" + "="*80 + "\n")
        
        # 对比分析
        if len(results) >= 2:
            print("📊 RSI对比分析:")
            print("=" * 60)
            
            for result in results:
                print(f"{result['name']} ({result['symbol']})")
                print(f"  📊 RSI: {result['rsi']:.1f}")
                print(f"  🎯 信号: {result['signal']}")
                print(f"  💡 建议: {result['action']}")
                print()
            
            # 按RSI排序
            results.sort(key=lambda x: x['rsi'], reverse=True)
            print("📈 RSI排序 (高到低):")
            for i, result in enumerate(results, 1):
                print(f"{i}. {result['name']}: RSI {result['rsi']:.1f}")
        
        return results

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python rsi_analyzer.py <股票代码> [股票名称]")
        print("  python rsi_analyzer.py 600000.SH 浦发银行")
        return
    
    symbol = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else None
    
    analyzer = RSIAnalyzer()
    result = analyzer.analyze_rsi(symbol, name)
    
    if result:
        print(f"\n✅ {result['name']} RSI分析完成")
        print(f"📊 当前RSI: {result['rsi']:.1f}")
        print(f"🎯 操作建议: {result['action']}")

if __name__ == "__main__":
    main()
