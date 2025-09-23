#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户真实投资组合分析脚本
只分析可交易的标的，过滤掉现金和开放式基金
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from analyst.advisor import UnifiedAdvisor
from analyst.portfolios import portfolio_manager

def analyze_user_portfolio():
    """分析用户真实投资组合（过滤后的版本）"""

    # 获取原始组合
    portfolio_name = 'USER_REAL_PORTFOLIO'
    original_portfolio = portfolio_manager.get_portfolio(portfolio_name)
    portfolio_meta = portfolio_manager.get_portfolio_meta(portfolio_name)

    # 过滤掉不可交易的标的
    # 排除：CASH（现金）、.OF结尾的开放式基金
    tradable_symbols = []
    excluded_symbols = []

    for symbol in original_portfolio.keys():
        if symbol == 'CASH' or symbol.endswith('.OF'):
            excluded_symbols.append(symbol)
        else:
            tradable_symbols.append(symbol)

    print("=" * 80)
    print("🌟 用户真实投资组合综合分析报告")
    print("=" * 80)
    print(f"\n📚 组合名称: {portfolio_name}")
    print(f"📝 组合描述: {portfolio_meta.get('description', '未知')}")
    print(f"💰 总价值: {portfolio_meta.get('total_value', 0)/10000:.1f}万元")
    print(f"⚠️ 风险等级: {portfolio_meta.get('risk_level', '未知')}")
    print(f"🎯 适合人群: {portfolio_meta.get('suitable_for', '未知')}")

    print(f"\n📊 组合标的概况:")
    print(f"  • 总标的数: {len(original_portfolio)}")
    print(f"  • 可分析标的数: {len(tradable_symbols)}")
    print(f"  • 排除标的数: {len(excluded_symbols)}")

    if excluded_symbols:
        print(f"\n⚠️ 已排除以下无法获取数据的标的:")
        for symbol in excluded_symbols:
            info = original_portfolio[symbol]
            print(f"  • {symbol}: {info.name} ({info.sector})")

    # 显示Sleeve配置信息
    sleeves = portfolio_manager.get_sleeves(portfolio_name)
    if sleeves:
        print(f"\n📊 Sleeve配置结构:")
        total_allocation = 0
        for sleeve in sleeves:
            allocation_pct = sleeve.allocation_ratio * 100
            total_allocation += allocation_pct
            print(f"  • {sleeve.name} ({sleeve.risk_level}): {allocation_pct:.1f}% 配置, 目标收益 {sleeve.target_return*100:.0f}%")
            print(f"    - {sleeve.description}")
        print(f"  • 总配置比例: {total_allocation:.1f}%")

    if not tradable_symbols:
        print("\n❌ 没有可分析的标的，请检查组合配置")
        return

    print(f"\n🔍 开始分析 {len(tradable_symbols)} 个可交易标的...")
    print("-" * 60)

    # 创建顾问实例并执行分析
    advisor = UnifiedAdvisor(use_cache=True, enable_fundamental=True)

    # 执行组合分析（使用sleeve权重）
    result = advisor.analyze_portfolio(
        symbols=tradable_symbols,
        portfolio_name=portfolio_name,
        use_sleeves=True,  # 使用sleeve配置的权重
        current_days=300
    )

    # 输出分析结果摘要
    if result.get('success'):
        print("\n" + "=" * 80)
        print("📈 分析结果汇总")
        print("=" * 80)

        if 'summary' in result:
            summary = result['summary']

            # 显示组合整体建议
            if 'portfolio_recommendation' in summary:
                rec = summary['portfolio_recommendation']
                print(f"\n🎯 组合整体建议:")
                print(f"  • 综合信号: {rec.get('overall_signal', '未知')}")
                print(f"  • 建议操作: {rec.get('action', '未知')}")
                if 'reasoning' in rec:
                    print(f"  • 操作理由: {rec['reasoning']}")

            # 显示个股信号统计
            if 'signals_summary' in summary:
                signals = summary['signals_summary']
                print(f"\n📊 个股信号统计:")
                print(f"  • 强烈买入: {signals.get('strong_buy', 0)} 只")
                print(f"  • 买入: {signals.get('buy', 0)} 只")
                print(f"  • 持有: {signals.get('hold', 0)} 只")
                print(f"  • 卖出: {signals.get('sell', 0)} 只")
                print(f"  • 强烈卖出: {signals.get('strong_sell', 0)} 只")
                print(f"  • 数据不足: {signals.get('no_data', 0)} 只")

            # 显示风险评估
            if 'risk_assessment' in summary:
                risk = summary['risk_assessment']
                print(f"\n⚠️ 风险评估:")
                print(f"  • 风险等级: {risk.get('level', '未知')}")
                print(f"  • 风险描述: {risk.get('description', '无')}")
                if 'high_risk_symbols' in risk:
                    high_risk = risk['high_risk_symbols']
                    if high_risk:
                        print(f"  • 高风险标的: {', '.join(high_risk[:5])}")

            # 显示机会发现
            if 'opportunities' in summary:
                opp = summary['opportunities']
                if 'top_opportunities' in opp:
                    top_opps = opp['top_opportunities']
                    if top_opps:
                        print(f"\n💎 投资机会 (前5):")
                        for i, (symbol, score) in enumerate(top_opps[:5], 1):
                            print(f"  {i}. {symbol}: 评分 {score}")

        # 显示基于Sleeve的权重配置
        weights = portfolio_manager.get_weights(portfolio_name, use_sleeves=True)
        if weights:
            print(f"\n📊 基于Sleeve的推荐权重配置:")
            # 只显示可交易标的的权重
            tradable_weights = {k: v for k, v in weights.items() if k in tradable_symbols}
            # 归一化权重
            total_weight = sum(tradable_weights.values())
            if total_weight > 0:
                normalized_weights = {k: v/total_weight for k, v in tradable_weights.items()}
                # 按权重排序
                sorted_weights = sorted(normalized_weights.items(), key=lambda x: x[1], reverse=True)
                for symbol, weight in sorted_weights[:10]:  # 显示前10个
                    info = original_portfolio[symbol]
                    print(f"  • {symbol} ({info.name}): {weight*100:.1f}%")

        print("\n✅ 分析完成！")

        # 保存结果到文件
        import json
        from datetime import datetime

        output_file = f"reports/user_portfolio_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_path = project_root / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n📁 详细结果已保存至: {output_file}")

    else:
        print("\n❌ 分析失败")
        if 'error' in result:
            print(f"错误信息: {result['error']}")

if __name__ == '__main__':
    analyze_user_portfolio()