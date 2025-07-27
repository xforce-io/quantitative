#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
招商银行策略适配性分析工具
CMB Strategy Compatibility Analyzer

分析招商银行适合采用什么样的交易策略
Analyze which trading strategies are suitable for China Merchants Bank
"""

import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class CMBStrategyAnalyzer:
    """招商银行策略分析器"""
    
    def __init__(self, data_dir: str = "quant/data"):
        self.dataDir = Path(data_dir)
        self.symbol = "600036.SH"
        self.stockData = None
        self.config = None
        
    def loadStockData(self) -> None:
        """加载招商银行股票数据"""
        print(f"📊 加载招商银行股票数据...")
        
        # 查找最新的数据文件
        data_files = list(self.dataDir.glob(f"{self.symbol}_*.csv"))
        if not data_files:
            print(f"❌ 未找到招商银行数据文件")
            return
        
        # 选择最新的数据文件
        latest_file = max(data_files, key=lambda x: x.stat().st_mtime)
        print(f"✅ 使用数据文件: {latest_file.name}")
        
        try:
            # 读取数据
            self.stockData = pd.read_csv(latest_file)
            
            # 处理日期列
            if 'date' in self.stockData.columns:
                self.stockData['date'] = pd.to_datetime(self.stockData['date'])
                self.stockData.set_index('date', inplace=True)
            
            # 计算技术指标
            self.calculateTechnicalIndicators()
            
            print(f"✅ 数据加载完成: {len(self.stockData)} 个交易日")
            
        except Exception as e:
            print(f"❌ 数据加载失败: {e}")
    
    def loadConfig(self) -> None:
        """加载招商银行配置"""
        config_file = Path("config/stocks/600036.SH.json")
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            print(f"✅ 配置加载完成: {self.config['name']}")
        else:
            print(f"❌ 配置文件不存在: {config_file}")
    
    def calculateTechnicalIndicators(self) -> None:
        """计算技术指标"""
        if self.stockData is None:
            return
        
        # 计算移动平均线
        self.stockData['MA5'] = self.stockData['close'].rolling(window=5).mean()
        self.stockData['MA10'] = self.stockData['close'].rolling(window=10).mean()
        self.stockData['MA20'] = self.stockData['close'].rolling(window=20).mean()
        self.stockData['MA60'] = self.stockData['close'].rolling(window=60).mean()
        
        # 计算收益率
        self.stockData['daily_return'] = self.stockData['close'].pct_change()
        self.stockData['cumulative_return'] = (1 + self.stockData['daily_return']).cumprod() - 1
        
        # 计算波动率
        self.stockData['volatility_20d'] = self.stockData['daily_return'].rolling(window=20).std() * np.sqrt(252)
        
        # 计算最大回撤
        self.stockData['peak'] = self.stockData['close'].expanding().max()
        self.stockData['drawdown'] = (self.stockData['close'] - self.stockData['peak']) / self.stockData['peak']
        self.stockData['max_drawdown'] = self.stockData['drawdown'].expanding().min()
        
        # 计算RSI
        delta = self.stockData['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        self.stockData['RSI'] = 100 - (100 / (1 + rs))
        
        # 计算布林带
        self.stockData['BB_middle'] = self.stockData['close'].rolling(window=20).mean()
        bb_std = self.stockData['close'].rolling(window=20).std()
        self.stockData['BB_upper'] = self.stockData['BB_middle'] + (bb_std * 2)
        self.stockData['BB_lower'] = self.stockData['BB_middle'] - (bb_std * 2)
        
        # 计算成交量指标
        self.stockData['volume_ma'] = self.stockData['volume'].rolling(window=20).mean()
        self.stockData['volume_ratio'] = self.stockData['volume'] / self.stockData['volume_ma']
    
    def analyzeStockCharacteristics(self) -> Dict:
        """分析股票特征"""
        if self.stockData is None:
            return {}
        
        # 基本统计
        total_return = (self.stockData['close'].iloc[-1] / self.stockData['close'].iloc[0]) - 1
        annual_return = (1 + total_return) ** (252 / len(self.stockData)) - 1
        volatility = self.stockData['daily_return'].std() * np.sqrt(252)
        max_drawdown = self.stockData['max_drawdown'].min()
        sharpe_ratio = annual_return / volatility if volatility > 0 else 0
        
        # 价格特征
        price_range = (self.stockData['high'].max() - self.stockData['low'].min()) / self.stockData['close'].mean()
        avg_price = self.stockData['close'].mean()
        price_std = self.stockData['close'].std()
        price_cv = price_std / avg_price  # 变异系数
        
        # 交易特征
        avg_volume = self.stockData['volume'].mean()
        volume_volatility = self.stockData['volume'].std() / avg_volume
        
        # 趋势特征
        trend_strength = abs(self.stockData['MA20'].iloc[-1] - self.stockData['MA20'].iloc[0]) / self.stockData['MA20'].iloc[0]
        
        # 震荡特征
        rsi_avg = self.stockData['RSI'].mean()
        rsi_std = self.stockData['RSI'].std()
        
        characteristics = {
            'total_return': total_return,
            'annual_return': annual_return,
            'volatility': volatility,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'price_range': price_range,
            'price_cv': price_cv,
            'volume_volatility': volume_volatility,
            'trend_strength': trend_strength,
            'rsi_avg': rsi_avg,
            'rsi_std': rsi_std,
            'avg_price': avg_price,
            'avg_volume': avg_volume
        }
        
        print(f"\n📈 招商银行股票特征分析:")
        print("=" * 60)
        print(f"总收益率: {total_return:.2%}")
        print(f"年化收益率: {annual_return:.2%}")
        print(f"年化波动率: {volatility:.2%}")
        print(f"最大回撤: {max_drawdown:.2%}")
        print(f"夏普比率: {sharpe_ratio:.3f}")
        print(f"价格区间: {price_range:.2%}")
        print(f"价格变异系数: {price_cv:.3f}")
        print(f"成交量波动率: {volume_volatility:.3f}")
        print(f"趋势强度: {trend_strength:.2%}")
        print(f"RSI均值: {rsi_avg:.1f}")
        print(f"RSI标准差: {rsi_std:.1f}")
        
        return characteristics
    
    def analyzeStrategyCompatibility(self, characteristics: Dict) -> Dict:
        """分析策略适配性"""
        if not characteristics:
            return {}
        
        # 策略评分标准
        strategy_scores = {
            'dca': 0,
            'grid': 0,
            'momentum': 0
        }
        
        # DCA策略评分
        dca_score = 0
        if characteristics['volatility'] < 0.3:  # 低波动率适合DCA
            dca_score += 30
        elif characteristics['volatility'] < 0.5:
            dca_score += 20
        else:
            dca_score += 10
            
        if characteristics['trend_strength'] > 0.5:  # 强趋势适合DCA
            dca_score += 25
        elif characteristics['trend_strength'] > 0.2:
            dca_score += 15
        else:
            dca_score += 5
            
        if characteristics['sharpe_ratio'] > 0.5:  # 高夏普比率
            dca_score += 20
            
        if characteristics['price_cv'] < 0.3:  # 价格稳定
            dca_score += 15
            
        if characteristics['rsi_avg'] < 60:  # RSI适中
            dca_score += 10
            
        strategy_scores['dca'] = min(dca_score, 100)
        
        # 网格策略评分
        grid_score = 0
        if 0.2 < characteristics['volatility'] < 0.6:  # 中等波动率适合网格
            grid_score += 30
        elif characteristics['volatility'] < 0.8:
            grid_score += 20
        else:
            grid_score += 10
            
        if characteristics['trend_strength'] < 0.3:  # 弱趋势适合网格
            grid_score += 25
        elif characteristics['trend_strength'] < 0.6:
            grid_score += 15
        else:
            grid_score += 5
            
        if characteristics['price_cv'] > 0.2:  # 价格波动适中
            grid_score += 20
            
        if 40 < characteristics['rsi_avg'] < 70:  # RSI在合理区间
            grid_score += 15
            
        if characteristics['volume_volatility'] < 1.0:  # 成交量稳定
            grid_score += 10
            
        strategy_scores['grid'] = min(grid_score, 100)
        
        # 动量策略评分
        momentum_score = 0
        if characteristics['volatility'] > 0.4:  # 高波动率适合动量
            momentum_score += 25
        elif characteristics['volatility'] > 0.2:
            momentum_score += 15
        else:
            momentum_score += 5
            
        if characteristics['trend_strength'] > 0.4:  # 强趋势适合动量
            momentum_score += 30
        elif characteristics['trend_strength'] > 0.2:
            momentum_score += 20
        else:
            momentum_score += 10
            
        if characteristics['volume_volatility'] > 0.5:  # 成交量活跃
            momentum_score += 20
            
        if characteristics['rsi_std'] > 10:  # RSI波动大
            momentum_score += 15
            
        if characteristics['sharpe_ratio'] > 0.3:  # 有一定收益
            momentum_score += 10
            
        strategy_scores['momentum'] = min(momentum_score, 100)
        
        print(f"\n🎯 策略适配性评分:")
        print("=" * 60)
        print(f"DCA策略: {strategy_scores['dca']}/100")
        print(f"网格策略: {strategy_scores['grid']}/100")
        print(f"动量策略: {strategy_scores['momentum']}/100")
        
        return strategy_scores
    
    def recommendOptimalParameters(self, strategy_scores: Dict) -> Dict:
        """推荐最优参数"""
        recommendations = {}
        
        # 基于股票特征推荐参数
        if self.stockData is not None:
            avg_price = self.stockData['close'].mean()
            price_std = self.stockData['close'].std()
            volatility = self.stockData['daily_return'].std() * np.sqrt(252)
            
            # DCA策略推荐
            if strategy_scores['dca'] > 70:
                recommendations['dca'] = {
                    'interval': 'monthly',
                    'amount': int(avg_price * 100),  # 约1手股票
                    'base_ratio': 0.6,
                    'max_position': 100000,
                    'reason': '招商银行波动率适中，趋势稳定，适合定期定额投资'
                }
            
            # 网格策略推荐
            if strategy_scores['grid'] > 70:
                grid_spacing = max(0.02, min(0.05, volatility / 10))  # 基于波动率调整
                recommendations['grid'] = {
                    'grid_levels': 8,
                    'grid_spacing': grid_spacing,
                    'base_ratio': 0.4,
                    'max_position': 80000,
                    'commission': 0.0003,
                    'slippage': 0.001,
                    'reason': f'招商银行价格波动适中，建议{grid_spacing:.1%}网格间距'
                }
            
            # 动量策略推荐
            if strategy_scores['momentum'] > 70:
                recommendations['momentum'] = {
                    'lookback_period': 20,
                    'threshold': max(0.03, volatility / 20),
                    'base_ratio': 0.2,
                    'max_position': 50000,
                    'reason': '招商银行有一定趋势性，适合动量策略'
                }
        
        return recommendations
    
    def generateVisualizations(self, output_dir: str = "reports/cmb_analysis") -> None:
        """生成可视化图表"""
        if self.stockData is None:
            return
        
        # 创建输出目录
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 设置图表样式
        plt.style.use('seaborn-v0_8')
        fig_size = (12, 8)
        
        # 1. 价格走势图
        plt.figure(figsize=fig_size)
        plt.plot(self.stockData.index, self.stockData['close'], label='收盘价', linewidth=2)
        plt.plot(self.stockData.index, self.stockData['MA20'], label='MA20', alpha=0.7)
        plt.plot(self.stockData.index, self.stockData['MA60'], label='MA60', alpha=0.7)
        plt.fill_between(self.stockData.index, self.stockData['BB_upper'], 
                        self.stockData['BB_lower'], alpha=0.2, label='布林带')
        plt.title('招商银行价格走势与技术指标', fontsize=14, fontweight='bold')
        plt.xlabel('日期')
        plt.ylabel('价格 (元)')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(output_path / 'cmb_price_trend.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. 收益率分布
        plt.figure(figsize=fig_size)
        returns = self.stockData['daily_return'].dropna()
        plt.hist(returns, bins=50, alpha=0.7, edgecolor='black')
        plt.axvline(returns.mean(), color='red', linestyle='--', label=f'均值: {returns.mean():.3f}')
        plt.axvline(returns.std(), color='orange', linestyle='--', label=f'标准差: {returns.std():.3f}')
        plt.title('招商银行日收益率分布', fontsize=14, fontweight='bold')
        plt.xlabel('日收益率')
        plt.ylabel('频次')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path / 'cmb_return_distribution.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 3. 波动率变化
        plt.figure(figsize=fig_size)
        plt.plot(self.stockData.index, self.stockData['volatility_20d'], linewidth=2)
        plt.axhline(self.stockData['volatility_20d'].mean(), color='red', linestyle='--', 
                   label=f'平均波动率: {self.stockData["volatility_20d"].mean():.2%}')
        plt.title('招商银行20日滚动波动率', fontsize=14, fontweight='bold')
        plt.xlabel('日期')
        plt.ylabel('年化波动率')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(output_path / 'cmb_volatility.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 4. RSI指标
        plt.figure(figsize=fig_size)
        plt.plot(self.stockData.index, self.stockData['RSI'], linewidth=2)
        plt.axhline(70, color='red', linestyle='--', alpha=0.7, label='超买线')
        plt.axhline(30, color='green', linestyle='--', alpha=0.7, label='超卖线')
        plt.axhline(50, color='gray', linestyle='-', alpha=0.5, label='中线')
        plt.title('招商银行RSI指标', fontsize=14, fontweight='bold')
        plt.xlabel('日期')
        plt.ylabel('RSI')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(output_path / 'cmb_rsi.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"📊 可视化图表已保存到: {output_path}")
    
    def generateReport(self, characteristics: Dict, strategy_scores: Dict, 
                      recommendations: Dict, output_file: str = "reports/cmb_strategy_report.md") -> None:
        """生成分析报告"""
        # 确保输出目录存在
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 生成报告内容
        report_content = f"""# 招商银行策略适配性分析报告

## 📊 股票基本信息
- **股票代码**: 600036.SH
- **股票名称**: 招商银行
- **行业**: 银行
- **风险等级**: 低风险
- **分析期间**: {self.stockData.index[0].strftime('%Y-%m-%d')} 至 {self.stockData.index[-1].strftime('%Y-%m-%d')}
- **交易天数**: {len(self.stockData)} 天

## 📈 股票特征分析

### 收益特征
- **总收益率**: {characteristics['total_return']:.2%}
- **年化收益率**: {characteristics['annual_return']:.2%}
- **年化波动率**: {characteristics['volatility']:.2%}
- **最大回撤**: {characteristics['max_drawdown']:.2%}
- **夏普比率**: {characteristics['sharpe_ratio']:.3f}

### 价格特征
- **平均价格**: ¥{characteristics['avg_price']:.2f}
- **价格区间**: {characteristics['price_range']:.2%}
- **价格变异系数**: {characteristics['price_cv']:.3f}

### 技术特征
- **趋势强度**: {characteristics['trend_strength']:.2%}
- **RSI均值**: {characteristics['rsi_avg']:.1f}
- **RSI标准差**: {characteristics['rsi_std']:.1f}
- **成交量波动率**: {characteristics['volume_volatility']:.3f}

## 🎯 策略适配性评分

| 策略类型 | 适配性评分 | 推荐等级 | 说明 |
|----------|------------|----------|------|
| DCA策略 | {strategy_scores['dca']}/100 | {'⭐' * (strategy_scores['dca'] // 20)} | {'非常适合' if strategy_scores['dca'] > 80 else '适合' if strategy_scores['dca'] > 60 else '一般' if strategy_scores['dca'] > 40 else '不适合'} |
| 网格策略 | {strategy_scores['grid']}/100 | {'⭐' * (strategy_scores['grid'] // 20)} | {'非常适合' if strategy_scores['grid'] > 80 else '适合' if strategy_scores['grid'] > 60 else '一般' if strategy_scores['grid'] > 40 else '不适合'} |
| 动量策略 | {strategy_scores['momentum']}/100 | {'⭐' * (strategy_scores['momentum'] // 20)} | {'非常适合' if strategy_scores['momentum'] > 80 else '适合' if strategy_scores['momentum'] > 60 else '一般' if strategy_scores['momentum'] > 40 else '不适合'} |

## 💡 策略推荐

"""
        
        # 添加策略推荐
        for strategy, params in recommendations.items():
            strategy_name = {'dca': 'DCA策略', 'grid': '网格策略', 'momentum': '动量策略'}[strategy]
            report_content += f"""
### {strategy_name}
**推荐理由**: {params['reason']}

**推荐参数**:
"""
            for key, value in params.items():
                if key != 'reason':
                    if isinstance(value, float):
                        report_content += f"- {key}: {value:.3f}\n"
                    else:
                        report_content += f"- {key}: {value}\n"
        
        report_content += f"""
## 📊 投资建议

### 1. 策略优先级
1. **首选策略**: {max(strategy_scores, key=strategy_scores.get).upper()}
2. **备选策略**: {sorted(strategy_scores.items(), key=lambda x: x[1], reverse=True)[1][0].upper()}

### 2. 风险控制建议
- 建议最大回撤控制在 {abs(characteristics['max_drawdown'] * 0.8):.1%} 以内
- 夏普比率目标: {max(1.0, characteristics['sharpe_ratio'] * 1.2):.2f}
- 单次投资金额不超过总资金的 20%

### 3. 市场环境适配
- **震荡市场**: 优先考虑网格策略
- **趋势市场**: 优先考虑DCA策略
- **高波动市场**: 谨慎使用动量策略

## 📈 可视化图表
相关图表已生成并保存到 `reports/cmb_analysis/` 目录。

---
*报告生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        # 保存报告
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        print(f"📄 分析报告已保存到: {output_path}")

def main():
    """主函数"""
    print("🚀 招商银行策略适配性分析工具启动")
    print("=" * 60)
    
    # 创建分析器
    analyzer = CMBStrategyAnalyzer()
    
    # 加载数据
    analyzer.loadStockData()
    analyzer.loadConfig()
    
    if analyzer.stockData is None:
        print("❌ 无法加载股票数据")
        return
    
    # 执行分析
    print("\n" + "="*60)
    print("📊 开始招商银行策略适配性分析")
    print("="*60)
    
    # 分析股票特征
    characteristics = analyzer.analyzeStockCharacteristics()
    
    # 分析策略适配性
    strategy_scores = analyzer.analyzeStrategyCompatibility(characteristics)
    
    # 推荐最优参数
    recommendations = analyzer.recommendOptimalParameters(strategy_scores)
    
    # 生成可视化
    analyzer.generateVisualizations()
    
    # 生成报告
    analyzer.generateReport(characteristics, strategy_scores, recommendations)
    
    print("\n✅ 分析完成！")
    print("📊 可视化图表: reports/cmb_analysis/")
    print("📄 详细报告: reports/cmb_strategy_report.md")

if __name__ == "__main__":
    main() 