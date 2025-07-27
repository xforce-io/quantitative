#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Momentum Strategy Stock Screener
动量策略股票筛选器

批量筛选适合动量策略的股票
Batch screening stocks suitable for momentum strategies
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')

# 添加项目根目录到路径以支持绝对导入
import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from analyst.stock_strategy_analyzer import StockStrategyAnalyzer

@dataclass
class StockScreenResult:
    """股票筛选结果"""
    symbol: str
    name: str
    momentum_score: int
    volatility: float
    trend_strength: float
    volume_volatility: float
    rsi_std: float
    price_cv: float
    market_environment: str
    recommendation: str
    reasons: List[str]

class MomentumStockScreener:
    """动量策略股票筛选器"""
    
    def __init__(self, data_dir: str = "quant/data", config_dir: str = "config/stocks"):
        self.dataDir = Path(data_dir)
        self.configDir = Path(config_dir)
        self.analyzer = StockStrategyAnalyzer(data_dir, config_dir)
        self.results = []
        
        # 动量策略筛选标准
        self.momentum_criteria = {
            'min_volatility': 0.30,      # 最低波动率30%
            'min_trend_strength': 0.20,  # 最低趋势强度20%
            'min_volume_volatility': 0.5, # 最低成交量波动0.5
            'min_rsi_std': 12,           # 最低RSI标准差12
            'min_price_cv': 0.15,        # 最低价格变异系数0.15
            'min_momentum_score': 60     # 最低动量策略评分60
        }
        
        # 预定义的股票池
        self.stock_pools = {
            'tech_growth': [
                '002594.SZ',  # 比亚迪
                '300059.SZ',  # 东方财富
                '300750.SZ',  # 宁德时代
                '300468.SZ',  # 四方精创
                '002475.SZ',  # 立讯精密
                '000858.SZ',  # 五粮液
                '300015.SZ',  # 爱尔眼科
            ],
            'concept_stocks': [
                '300468.SZ',  # 四方精创 - 数字货币
                '002230.SZ',  # 科大讯飞 - 人工智能
                '300124.SZ',  # 汇川技术 - 工业互联网
                '002415.SZ',  # 海康威视 - 安防监控
                '300014.SZ',  # 亿纬锂能 - 新能源
                '300274.SZ',  # 阳光电源 - 光伏
            ],
            'cyclical_stocks': [
                '601899.SH',  # 紫金矿业
                '000831.SZ',  # 五矿稀土
                '002460.SZ',  # 赣锋锂业
                '000969.SZ',  # 安泰科技
                '600111.SH',  # 北方稀土
                '002756.SZ',  # 永兴材料
            ],
            'blue_chips': [
                '600036.SH',  # 招商银行
                '600900.SH',  # 长江电力
                '000001.SZ',  # 平安银行
                '600519.SH',  # 贵州茅台
                '000002.SZ',  # 万科A
                '600000.SH',  # 浦发银行
            ]
        }
    
    def screen_stock_pool(self, pool_name: str) -> List[StockScreenResult]:
        """筛选指定股票池"""
        if pool_name not in self.stock_pools:
            print(f"❌ 股票池 '{pool_name}' 不存在")
            return []
        
        symbols = self.stock_pools[pool_name]
        print(f"📊 开始筛选股票池: {pool_name} ({len(symbols)} 只股票)")
        
        results = []
        for symbol in symbols:
            try:
                result = self.analyze_single_stock(symbol)
                if result:
                    results.append(result)
                    print(f"✅ {symbol}: 动量评分 {result.momentum_score}/100")
                else:
                    print(f"❌ {symbol}: 分析失败")
            except Exception as e:
                print(f"❌ {symbol}: {str(e)}")
        
        # 按动量评分排序
        results.sort(key=lambda x: x.momentum_score, reverse=True)
        self.results.extend(results)
        
        return results
    
    def screen_custom_stocks(self, symbols: List[str]) -> List[StockScreenResult]:
        """筛选自定义股票列表"""
        print(f"📊 开始筛选自定义股票列表 ({len(symbols)} 只股票)")
        
        results = []
        for symbol in symbols:
            try:
                result = self.analyze_single_stock(symbol)
                if result:
                    results.append(result)
                    print(f"✅ {symbol}: 动量评分 {result.momentum_score}/100")
                else:
                    print(f"❌ {symbol}: 分析失败")
            except Exception as e:
                print(f"❌ {symbol}: {str(e)}")
        
        # 按动量评分排序
        results.sort(key=lambda x: x.momentum_score, reverse=True)
        self.results.extend(results)
        
        return results
    
    def analyze_single_stock(self, symbol: str) -> Optional[StockScreenResult]:
        """分析单只股票"""
        # 加载数据和配置
        self.analyzer.loadStockData(symbol)
        
        # 检查数据是否加载成功
        if self.analyzer.stockData is None:
            print(f"❌ {symbol}: 数据加载失败，跳过分析")
            return None
        
        # 检查数据是否为空
        if self.analyzer.stockData.empty:
            print(f"❌ {symbol}: 数据为空，跳过分析")
            return None
        
        # 检查数据的股票代码是否匹配（防止使用错误的数据）
        if self.analyzer.symbol != symbol:
            print(f"❌ {symbol}: 数据不匹配（期望 {symbol}，实际 {self.analyzer.symbol}），跳过分析")
            return None
        
        self.analyzer.loadConfig(symbol)
        
        # 分析股票特征
        characteristics = self.analyzer.analyzeStockCharacteristics()
        if not characteristics:
            print(f"❌ {symbol}: 特征分析失败，跳过分析")
            return None
        
        # 分析策略适配性
        strategy_scores = self.analyzer.analyzeStrategyCompatibility(characteristics)
        momentum_score = strategy_scores.get('momentum', 0)
        
        # 获取股票名称
        stock_name = self.analyzer.config.get('name', symbol) if self.analyzer.config else symbol
        
        # 生成推荐和原因
        recommendation, reasons = self.generate_recommendation(characteristics, momentum_score)
        
        return StockScreenResult(
            symbol=symbol,
            name=stock_name,
            momentum_score=momentum_score,
            volatility=characteristics['volatility'],
            trend_strength=characteristics['trend_strength'],
            volume_volatility=characteristics['volume_volatility'],
            rsi_std=characteristics['rsi_std'],
            price_cv=characteristics['price_cv'],
            market_environment=characteristics['market_environment'],
            recommendation=recommendation,
            reasons=reasons
        )
    
    def generate_recommendation(self, characteristics: Dict, momentum_score: int) -> Tuple[str, List[str]]:
        """生成推荐和原因"""
        reasons = []
        
        # 检查各项指标
        if characteristics['volatility'] < self.momentum_criteria['min_volatility']:
            reasons.append(f"波动率偏低({characteristics['volatility']:.1%})")
        
        if characteristics['trend_strength'] < self.momentum_criteria['min_trend_strength']:
            reasons.append(f"趋势强度不足({characteristics['trend_strength']:.1%})")
        
        if characteristics['volume_volatility'] < self.momentum_criteria['min_volume_volatility']:
            reasons.append(f"成交量波动偏低({characteristics['volume_volatility']:.2f})")
        
        if characteristics['rsi_std'] < self.momentum_criteria['min_rsi_std']:
            reasons.append(f"RSI波动偏小({characteristics['rsi_std']:.1f})")
        
        if characteristics['price_cv'] < self.momentum_criteria['min_price_cv']:
            reasons.append(f"价格过于稳定({characteristics['price_cv']:.3f})")
        
        # 生成推荐
        if momentum_score >= 80:
            recommendation = "强烈推荐"
        elif momentum_score >= 60:
            recommendation = "推荐"
        elif momentum_score >= 40:
            recommendation = "一般"
        else:
            recommendation = "不推荐"
        
        return recommendation, reasons
    
    def filter_by_criteria(self, results: List[StockScreenResult], 
                          min_score: int = None) -> List[StockScreenResult]:
        """根据标准过滤结果"""
        if min_score is None:
            min_score = self.momentum_criteria['min_momentum_score']
        
        filtered = [r for r in results if r.momentum_score >= min_score]
        print(f"🔍 过滤结果: {len(filtered)}/{len(results)} 只股票符合标准")
        
        return filtered
    
    def generate_screening_report(self, results: List[StockScreenResult], 
                                output_file: str = None) -> str:
        """生成筛选报告"""
        if not results:
            return "没有筛选结果"
        
        # 按评分分类
        excellent = [r for r in results if r.momentum_score >= 80]
        good = [r for r in results if 60 <= r.momentum_score < 80]
        average = [r for r in results if 40 <= r.momentum_score < 60]
        poor = [r for r in results if r.momentum_score < 40]
        
        report = f"""
# 动量策略股票筛选报告

*生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}*

## 📊 筛选结果概览

- **总筛选股票数**: {len(results)} 只
- **强烈推荐**: {len(excellent)} 只 (评分≥80)
- **推荐**: {len(good)} 只 (评分60-79)
- **一般**: {len(average)} 只 (评分40-59)
- **不推荐**: {len(poor)} 只 (评分<40)

## 🎯 动量策略筛选标准

- **最低波动率**: {self.momentum_criteria['min_volatility']:.0%}
- **最低趋势强度**: {self.momentum_criteria['min_trend_strength']:.0%}
- **最低成交量波动**: {self.momentum_criteria['min_volume_volatility']:.1f}
- **最低RSI标准差**: {self.momentum_criteria['min_rsi_std']:.0f}
- **最低价格变异系数**: {self.momentum_criteria['min_price_cv']:.3f}
- **最低动量评分**: {self.momentum_criteria['min_momentum_score']}

## 🏆 强烈推荐股票 (评分≥80)

"""
        
        if excellent:
            report += "| 股票代码 | 股票名称 | 动量评分 | 波动率 | 趋势强度 | 市场环境 |\n"
            report += "|----------|----------|----------|--------|----------|----------|\n"
            for stock in excellent:
                report += f"| {stock.symbol} | {stock.name} | {stock.momentum_score}/100 | {stock.volatility:.1%} | {stock.trend_strength:.1%} | {stock.market_environment} |\n"
        else:
            report += "暂无强烈推荐的股票\n"
        
        report += "\n## 👍 推荐股票 (评分60-79)\n\n"
        
        if good:
            report += "| 股票代码 | 股票名称 | 动量评分 | 波动率 | 趋势强度 | 市场环境 |\n"
            report += "|----------|----------|----------|--------|----------|----------|\n"
            for stock in good:
                report += f"| {stock.symbol} | {stock.name} | {stock.momentum_score}/100 | {stock.volatility:.1%} | {stock.trend_strength:.1%} | {stock.market_environment} |\n"
        else:
            report += "暂无推荐的股票\n"
        
        report += "\n## 🔍 详细分析\n\n"
        
        # 对于高分股票，提供详细分析
        top_stocks = [r for r in results if r.momentum_score >= 60]
        for stock in top_stocks:
            report += f"""
### {stock.name} ({stock.symbol})

**动量策略评分**: {stock.momentum_score}/100 - {stock.recommendation}

**关键指标**:
- 波动率: {stock.volatility:.1%}
- 趋势强度: {stock.trend_strength:.1%}
- 成交量波动: {stock.volume_volatility:.2f}
- RSI标准差: {stock.rsi_std:.1f}
- 价格变异系数: {stock.price_cv:.3f}
- 市场环境: {stock.market_environment}

"""
            if stock.reasons:
                report += "**需要关注的问题**:\n"
                for reason in stock.reasons:
                    report += f"- {reason}\n"
            report += "\n"
        
        # 总结建议
        report += """
## 💡 投资建议

### 适合动量策略的股票特征
1. **高波动率** (>30%) - 提供足够的交易机会
2. **强趋势性** (>20%) - 价格有明确方向
3. **活跃成交** (>0.5) - 保证流动性
4. **技术敏感** (RSI标准差>12) - 技术指标有效

### 风险提示
- 动量策略适合短期交易，不适合长期投资
- 高波动率意味着高风险，需要严格止损
- 政策变化可能快速改变股票的动量特征
- 建议分散投资，单股仓位不超过10%

### 操作建议
- 关注技术突破信号，如突破关键阻力位
- 确认成交量配合，避免虚假突破
- 设置合理止损，建议15-20%
- 定期复评，动量特征可能发生变化
"""
        
        # 保存报告
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"📄 筛选报告已保存至: {output_file}")
        
        return report
    
    def export_to_excel(self, results: List[StockScreenResult], 
                       output_file: str = "reports/momentum_screening_results.xlsx") -> None:
        """导出结果到Excel"""
        if not results:
            print("❌ 没有结果可导出")
            return
        
        # 创建DataFrame
        data = []
        for result in results:
            data.append({
                '股票代码': result.symbol,
                '股票名称': result.name,
                '动量评分': result.momentum_score,
                '推荐等级': result.recommendation,
                '波动率': f"{result.volatility:.1%}",
                '趋势强度': f"{result.trend_strength:.1%}",
                '成交量波动': f"{result.volume_volatility:.2f}",
                'RSI标准差': f"{result.rsi_std:.1f}",
                '价格变异系数': f"{result.price_cv:.3f}",
                '市场环境': result.market_environment,
                '问题点': '; '.join(result.reasons) if result.reasons else '无'
            })
        
        df = pd.DataFrame(data)
        
        # 确保输出目录存在
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存到Excel
        df.to_excel(output_path, index=False, engine='openpyxl')
        print(f"📊 筛选结果已导出至: {output_file}")

def main():
    """主函数 - 演示用法"""
    screener = MomentumStockScreener()
    
    print("🚀 动量策略股票筛选器")
    print("=" * 50)
    
    # 筛选科技成长股
    print("\n📊 筛选科技成长股...")
    tech_results = screener.screen_stock_pool('tech_growth')
    
    # 筛选概念股
    print("\n📊 筛选概念股...")
    concept_results = screener.screen_stock_pool('concept_stocks')
    
    # 筛选周期股
    print("\n📊 筛选周期股...")
    cyclical_results = screener.screen_stock_pool('cyclical_stocks')
    
    # 筛选蓝筹股（作为对比）
    print("\n📊 筛选蓝筹股（对比）...")
    blue_chip_results = screener.screen_stock_pool('blue_chips')
    
    # 合并所有结果
    all_results = tech_results + concept_results + cyclical_results + blue_chip_results
    
    # 过滤高分股票
    high_score_results = screener.filter_by_criteria(all_results, min_score=60)
    
    # 生成报告
    report = screener.generate_screening_report(
        all_results, 
        output_file="reports/momentum_screening_report.md"
    )
    
    # 导出Excel
    screener.export_to_excel(all_results)
    
    print("\n🎯 筛选完成!")
    print(f"总共分析了 {len(all_results)} 只股票")
    print(f"其中 {len(high_score_results)} 只股票适合动量策略")

if __name__ == "__main__":
    main() 