#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
资金流向分析示例
Money Flow Analysis Demo

演示如何使用 Tushare 接口分析:
1. A股行业资金流向 (同花顺/东方财富)
2. 机构 vs 散户资金博弈
3. 北向资金流向
4. 市场整体资金情绪

使用方法:
    python bin/money_flow_demo.py --date 20260108
    python bin/money_flow_demo.py --symbol 000001.SZ --start 20251201 --end 20260108
"""

import argparse
import json
from datetime import datetime, timedelta

# Add project root to path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quant.data.implementations.tushare_provider import TushareProvider


def demo_industry_money_flow(provider, trade_date):
    """演示行业资金流向分析"""
    print("\n" + "=" * 60)
    print(f"📊 同花顺行业资金流向分析 - {trade_date}")
    print("=" * 60)
    
    df = provider.get_industry_money_flow_ths(trade_date=trade_date)
    
    if df.empty:
        print("⚠️ 未获取到数据，请检查日期是否为交易日")
        return
    
    print(f"\n共获取 {len(df)} 个行业数据\n")
    
    # Top 10 净流入行业
    print("🔺 资金净流入 TOP 10 行业:")
    print("-" * 50)
    if 'net_amount' in df.columns:
        top_inflow = df.nlargest(10, 'net_amount')[['name', 'net_amount', 'pct_change']]
        for i, row in top_inflow.iterrows():
            pct = row.get('pct_change', 0) or 0
            net = row.get('net_amount', 0) or 0
            print(f"  {row['name']:12} | 净流入: {net:>10.2f} 万 | 涨跌: {pct:>6.2f}%")
    
    # Top 10 净流出行业
    print("\n🔻 资金净流出 TOP 10 行业:")
    print("-" * 50)
    if 'net_amount' in df.columns:
        top_outflow = df.nsmallest(10, 'net_amount')[['name', 'net_amount', 'pct_change']]
        for i, row in top_outflow.iterrows():
            pct = row.get('pct_change', 0) or 0
            net = row.get('net_amount', 0) or 0
            print(f"  {row['name']:12} | 净流出: {net:>10.2f} 万 | 涨跌: {pct:>6.2f}%")
    
    # 机构 vs 散户汇总
    if 'institutional_net' in df.columns and 'retail_net' in df.columns:
        inst_total = df['institutional_net'].sum()
        retail_total = df['retail_net'].sum()
        
        print("\n📈 机构 vs 散户资金汇总:")
        print("-" * 50)
        print(f"  机构净流入(特大单+大单): {inst_total:>12.2f} 万")
        print(f"  散户净流入(中单+小单):   {retail_total:>12.2f} 万")
        
        if inst_total > 0 and retail_total < 0:
            print("\n  💡 解读: 机构买入，散户卖出 - 可能是积极信号")
        elif inst_total < 0 and retail_total > 0:
            print("\n  ⚠️ 解读: 机构卖出，散户买入 - 需要警惕")


def demo_market_summary(provider, trade_date):
    """演示市场资金汇总分析"""
    print("\n" + "=" * 60)
    print(f"📊 市场资金流向汇总分析 - {trade_date}")
    print("=" * 60)
    
    summary = provider.get_market_money_flow_summary(trade_date)
    
    if 'error' in summary:
        print(f"⚠️ 获取数据失败: {summary['error']}")
        return
    
    # 市场情绪
    sentiment = summary.get('market_sentiment', {})
    print(f"\n🎯 市场情绪: {sentiment.get('sentiment', 'N/A')}")
    print(f"   解读: {sentiment.get('reason', 'N/A')}")
    print(f"   机构净流入: {sentiment.get('institutional_net', 0):,.2f} 万")
    print(f"   散户净流入: {sentiment.get('retail_net', 0):,.2f} 万")
    print(f"   北向资金:   {sentiment.get('north_money_net', 0):,.2f} 万")
    
    # 行业排名
    ranking = summary.get('industry_ranking', {})
    if ranking:
        print("\n🔺 资金净流入 TOP 5 行业:")
        for item in ranking.get('top_10_inflow', [])[:5]:
            print(f"   {item.get('name', 'N/A'):12} | 净流入: {item.get('net_amount', 0):>10.2f} 万")
        
        print("\n🔻 资金净流出 TOP 5 行业:")
        for item in ranking.get('top_10_outflow', [])[:5]:
            print(f"   {item.get('name', 'N/A'):12} | 净流出: {item.get('net_amount', 0):>10.2f} 万")


def demo_stock_money_flow(provider, symbol, start_date, end_date):
    """演示个股资金流向分析"""
    print("\n" + "=" * 60)
    print(f"📊 个股资金流向分析 - {symbol}")
    print(f"   分析期间: {start_date} ~ {end_date}")
    print("=" * 60)
    
    result = provider.analyze_institutional_vs_retail(symbol, start_date, end_date)
    
    if 'error' in result:
        print(f"⚠️ 获取数据失败: {result['error']}")
        return
    
    print(f"\n📈 分析结果 (共 {result['total_days']} 个交易日):")
    print("-" * 50)
    
    # 机构分析
    inst = result['institutional']
    print(f"\n🏢 机构资金 (特大单 + 大单):")
    print(f"   累计净流入:   {inst['total_net_flow']:>12.2f} 万")
    print(f"   日均净流入:   {inst['avg_daily_net']:>12.2f} 万")
    print(f"   净流入天数:   {inst['net_inflow_days']:>5} 天")
    print(f"   净流出天数:   {inst['net_outflow_days']:>5} 天")
    
    # 散户分析
    retail = result['retail']
    print(f"\n👥 散户资金 (中单 + 小单):")
    print(f"   累计净流入:   {retail['total_net_flow']:>12.2f} 万")
    print(f"   日均净流入:   {retail['avg_daily_net']:>12.2f} 万")
    print(f"   净流入天数:   {retail['net_inflow_days']:>5} 天")
    print(f"   净流出天数:   {retail['net_outflow_days']:>5} 天")
    
    # 趋势判断
    print(f"\n🎯 资金趋势: {result['trend']}")
    print(f"   💡 解读: {result['interpretation']}")


def demo_hsgt_flow(provider, start_date, end_date):
    """演示沪深港通资金流向"""
    print("\n" + "=" * 60)
    print(f"📊 沪深港通资金流向分析")
    print(f"   分析期间: {start_date} ~ {end_date}")
    print("=" * 60)
    
    df = provider.get_hsgt_flow(start_date, end_date)
    
    if df.empty:
        print("⚠️ 未获取到数据")
        return
    
    print(f"\n共获取 {len(df)} 个交易日数据\n")
    
    # 显示最近5天数据
    print("最近5个交易日北向资金流向:")
    print("-" * 50)
    
    recent = df.head(5)
    for idx, row in recent.iterrows():
        date_str = idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)
        north = row.get('north_money', 0) or 0
        south = row.get('south_money', 0) or 0
        print(f"  {date_str} | 北向: {north:>10.2f} 亿 | 南向: {south:>10.2f} 亿")


def main():
    parser = argparse.ArgumentParser(description='资金流向分析示例')
    parser.add_argument('--date', type=str, help='分析日期 (YYYYMMDD)')
    parser.add_argument('--symbol', type=str, help='股票代码 (如 000001.SZ)')
    parser.add_argument('--start', type=str, help='开始日期 (YYYYMMDD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYYMMDD)')
    parser.add_argument('--demo', choices=['all', 'industry', 'market', 'stock', 'hsgt'], 
                        default='all', help='演示类型')
    
    args = parser.parse_args()
    
    # 默认日期
    if not args.date:
        # 使用最近一个交易日
        today = datetime.now()
        if today.weekday() >= 5:  # 周末
            args.date = (today - timedelta(days=today.weekday() - 4)).strftime('%Y%m%d')
        else:
            args.date = today.strftime('%Y%m%d')
    
    if not args.start:
        args.start = (datetime.strptime(args.date, '%Y%m%d') - timedelta(days=30)).strftime('%Y%m%d')
    if not args.end:
        args.end = args.date
    
    print("\n🚀 资金流向分析工具 v1.0")
    print("=" * 60)
    
    # 初始化数据提供者
    provider = TushareProvider()
    print(f"✅ 已连接 Tushare Pro")
    
    # 运行演示
    if args.demo in ['all', 'industry']:
        demo_industry_money_flow(provider, args.date)
    
    if args.demo in ['all', 'market']:
        demo_market_summary(provider, args.date)
    
    if args.demo in ['all', 'hsgt']:
        demo_hsgt_flow(provider, args.start, args.end)
    
    if args.demo in ['all', 'stock'] and args.symbol:
        demo_stock_money_flow(provider, args.symbol, args.start, args.end)
    elif args.demo == 'stock' and not args.symbol:
        print("\n⚠️ 分析个股资金流向需要指定 --symbol 参数")
    
    print("\n" + "=" * 60)
    print("✅ 分析完成!")


if __name__ == '__main__':
    main()
