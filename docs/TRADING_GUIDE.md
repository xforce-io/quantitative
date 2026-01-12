# 交易策略指南 (Trading Strategy Guide)

本指南介绍量化交易系统中的各种交易策略，重点介绍基于 Agent 的智能交易架构和网格交易策略的使用方法。

## 🤖 基于 Agent 的智能交易架构

### 新架构概述

我们引入了基于 Agent 的智能交易架构，将传统的策略参数优化升级为智能代理系统：

```
传统方式: stock-analyzer → 策略参数 → 回测结果
新架构:   stock-analyzer → AgentManager → 多种 Agent → 智能优化 → 推荐策略
```

### Agent 类型

#### 1. Grid Trading Agent (网格交易代理)
- **策略特点**: 震荡市场低买高卖
- **参数空间**: 网格层数、间距、基础仓位比例
- **适用场景**: 价格震荡、高流动性股票

#### 2. DCA Agent (定投代理)
- **策略特点**: 定期定额投资
- **参数空间**: 投资频率、投资金额、基础仓位比例  
- **适用场景**: 长期投资、分散风险

#### 3. Momentum Agent (动量代理)
- **策略特点**: 趋势跟随交易
- **参数空间**: 回望期、触发阈值、基础仓位比例
- **适用场景**: 趋势明确的市场

#### 4. Hybrid Agent (混合代理)
- **策略特点**: 多策略组合
- **参数空间**: 各策略权重组合
- **适用场景**: 复杂市场环境

## 🚀 快速开始

### 1. 基于 Agent 的分析（推荐）

```python
from quant.agents.agent_manager import AgentManager, AgentOptimizationConfig

# 初始化 Agent 管理器
agentManager = AgentManager('tushare')

# 生成网格交易代理变体
gridConfig = AgentOptimizationConfig(
    agentType='grid',
    parameterRanges={
        'gridLevels': [8, 10, 12],
        'gridSpacing': [0.015, 0.02, 0.025],
        'baseRatio': [0.3, 0.4],
        'maxPosition': [100000]
    },
    riskProfile='moderate',
    maxVariants=10
)

# 生成代理变体
gridAgents = agentManager.generateAgentVariants('grid', '002594.SZ', gridConfig)

# 执行多 Agent 优化
results = agentManager.optimizeAgents(
    symbol='002594.SZ',
    startDate='20230101',
    endDate='20241201',
    agentConfigs=gridAgents[:5],  # 测试前5个
    initialCapital=100000
)

# 生成智能推荐
report = agentManager.generateOptimizationReport('002594.SZ', results)
print(f"最佳代理: {report['bestOverall']['name']}")
print(f"收益率: {report['bestOverall']['performance']['totalReturn']:.2%}")
```

### 2. 多策略 Agent 对比

```python
# 生成多种类型的 Agent
allAgents = []

# 网格策略 Agent
gridAgents = agentManager.generateAgentVariants('grid', symbol, gridConfig)
allAgents.extend(gridAgents[:3])

# 定投策略 Agent  
dcaConfig = AgentOptimizationConfig(
    agentType='dca',
    parameterRanges={
        'interval': ['weekly', 'monthly'],
        'amount': [1000, 2000],
        'baseRatio': [0.3, 0.5]
    },
    riskProfile='conservative'
)
dcaAgents = agentManager.generateAgentVariants('dca', symbol, dcaConfig)
allAgents.extend(dcaAgents[:2])

# 动量策略 Agent
momentumConfig = AgentOptimizationConfig(
    agentType='momentum',
    parameterRanges={
        'lookbackPeriod': [15, 20, 30],
        'threshold': [0.05, 0.07],
        'baseRatio': [0.2, 0.3]
    },
    riskProfile='aggressive'
)
momentumAgents = agentManager.generateAgentVariants('momentum', symbol, momentumConfig)
allAgents.extend(momentumAgents[:2])

# 执行综合优化
results = agentManager.optimizeAgents(symbol, startDate, endDate, allAgents, 100000)
report = agentManager.generateOptimizationReport(symbol, results)

# 查看各策略类型最佳表现
for strategyType, info in report['bestByStrategy'].items():
    print(f"{strategyType}: {info['performance']['totalReturn']:.2%}")
```

### 3. CLI 命令行方式

```bash
# 运行多 Agent 演示
python demo/byd_multi_agent_demo.py

# 使用统一入口
python bin/run.py trading list                    # 列出可用策略
python bin/run.py trading backtest grid 002594.SZ # 传统网格回测
```

## 🎯 支持的交易策略

### 1. 网格交易策略 (Grid Trading Strategy)

网格交易是一种量化交易策略，通过在预设的价格网格上进行买入和卖出操作来获利。

#### 策略原理
1. **网格设置**: 在当前价格上下设置多个买入和卖出价格网格
2. **低买高卖**: 当价格下跌触发买入网格时买入股票，当价格上涨触发卖出网格时卖出股票
3. **震荡获利**: 在价格震荡的市场中通过频繁的低买高卖获取收益

#### 适用场景
- **震荡市场**: 价格在一定区间内波动的市场环境
- **高流动性股票**: 交易活跃、价格波动相对稳定的股票
- **中长期投资**: 适合持有周期较长的投资策略

#### 策略参数
- `gridLevels`: 网格层数（默认10层，建议8-15层）
- `gridSpacing`: 网格间距百分比（默认2%，建议1.5%-3%）
- `maxPosition`: 最大仓位金额（默认10万，根据资金量调整）
- `commission`: 手续费率（默认0.03%，根据券商实际费率设置）
- `slippage`: 滑点率（默认0.1%，根据市场流动性调整）

## 🚀 快速开始

### 1. 配置化公司分析（推荐）

```python
# 使用新的分析模块 (推荐)
from quant.analysis.valuation import SystemicUndervalueAnalyzer
from quant.analysis.advisor import UnifiedAdvisor
from quant import create_data_provider, get_config

# 创建数据提供者和分析器
config = get_config()
provider = create_data_provider('tushare', config.get_providers_config())

# 使用系统性低估分析器
analyzer = SystemicUndervalueAnalyzer(provider)
result = analyzer.analyze('002594.SZ', period_days=756)

print(f"综合评分: {result['composite_score']}")
print(f"是否低估: {result['is_undervalued']}")
print(f"投资建议: {result['recommendation']}")
```

### 2. 传统回测方式

```python
from quant.engines.backtest_engine import BacktestEngine

# 创建回测引擎
engine = BacktestEngine('tushare')

# 运行回测
result = engine.runBacktest(
    symbol='000001.SZ',       # A股代码
    startDate='20230101',     # 开始日期
    endDate='20241201',       # 结束日期
    initialCapital=100000     # 初始资金10万
)

# 查看结果
print(f"总收益率: {result['performance']['totalReturn']:.2%}")
print(f"夏普比率: {result['performance']['sharpeRatio']:.2f}")
print(f"最大回撤: {result['performance']['maxDrawdown']:.2%}")
```

### 3. CLI命令行方式

```bash
# 分析特定股票的网格策略
python -m quant trading analyze --symbol 002594.SZ --strategy grid

# 运行回测
python -m quant trading backtest --symbol 000001.SZ --config config/trading.yaml
```

## 📊 参数优化

### 网格搜索优化

```python
# 定义参数搜索范围
parameterRanges = {
    'gridLevels': [8, 10, 12],
    'gridSpacing': [0.015, 0.02, 0.025],
    'maxPosition': [80000, 100000, 120000]
}

# 运行参数优化
result = engine.optimizeParameters(
    symbol='000001.SZ',
    startDate='20230101',
    endDate='20241201',
    parameterRanges=parameterRanges
)

print(f"最优参数: {result['bestParameters']}")
```

### 参数调优建议

#### 网格层数 (gridLevels)
- **8-10层**: 适合波动较小的蓝筹股
- **10-12层**: 适合中等波动的成长股
- **12-15层**: 适合波动较大的小盘股

#### 网格间距 (gridSpacing)
- **1.5%-2%**: 适合波动较小的股票
- **2%-2.5%**: 适合中等波动的股票
- **2.5%-3%**: 适合波动较大的股票

#### 最大仓位 (maxPosition)
- 建议不超过总资金的30%-50%
- 根据个人风险承受能力调整
- 考虑其他投资组合的分散化需求

## 📈 性能指标说明

### 收益指标
- **总收益率**: 策略相对初始资金的总收益
- **年化收益率**: 按年计算的收益率
- **Alpha**: 相对基准的超额收益
- **Beta**: 与基准的相关性指标

### 风险指标
- **夏普比率**: 风险调整后的收益率指标（>1.0为优秀）
- **最大回撤**: 策略历史最大亏损幅度（<10%为理想）
- **波动率**: 收益率的标准差
- **VaR**: 风险价值，一定置信度下的最大损失

### 交易指标
- **胜率**: 盈利交易占总交易的比例（>60%为良好）
- **盈亏比**: 平均盈利与平均亏损的比值（>1.5为理想）
- **交易次数**: 总交易次数
- **平均持仓时间**: 每笔交易的平均持有时间

## 🔧 高级功能

### 1. 可视化分析

```python
# 绘制回测结果图表
engine.plotResults('000001.SZ')

# 生成详细报告
report = engine.generateReport('000001.SZ')
print(report)

# 导出到Excel
engine.exportResults('000001.SZ', 'backtest_results.xlsx')
```

### 2. 多数据源支持

```python
# 使用新的数据层 (推荐)
from quant import create_data_provider, get_config

config = get_config()

# 自动选择最佳数据源
data_provider = create_data_provider('auto', config.get_providers_config())

# 指定数据源
tushare_provider = create_data_provider('tushare', config.get_providers_config())
yahoo_provider = create_data_provider('yahoo', config.get_providers_config())
```

### 3. 风险管理

```python
# 设置止损条件
riskConfig = {
    'maxDrawdown': 0.15,      # 最大回撤15%
    'stopLoss': 0.10,         # 单笔止损10%
    'positionLimit': 0.30,    # 单个股票最大仓位30%
    'volatilityLimit': 0.25   # 波动率限制25%
}

# 应用风险管理
result = engine.runBacktest(
    symbol='000001.SZ',
    startDate='20230101',
    endDate='20241201',
    riskManagement=riskConfig
)
```

## ⚠️ 注意事项和最佳实践

### 市场适用性
1. **震荡市场**: 网格策略在震荡市场中表现最佳
2. **趋势市场**: 在强烈单边趋势中可能表现不佳
3. **市场选择**: 选择流动性好、波动适中的股票

### 资金管理
1. **分散投资**: 不要将所有资金投入单一策略
2. **仓位控制**: 合理设置最大仓位，避免过度集中
3. **资金预留**: 保留一定现金应对突发情况

### 风险控制
1. **止损机制**: 设置合理的止损条件
2. **定期评估**: 定期检查策略表现，及时调整
3. **市场监控**: 关注市场环境变化，适时暂停策略

### 成本考虑
1. **手续费**: 高频交易会产生较多手续费
2. **滑点**: 考虑实际交易中的滑点成本
3. **税费**: 考虑股票交易的印花税等费用

## 🔮 策略扩展

### 未来功能规划
- **动态网格**: 根据市场波动率动态调整网格间距
- **多品种支持**: 支持期货、期权等其他金融工具
- **机器学习**: 使用ML算法优化网格参数
- **实时交易**: 连接券商API实现实盘交易

### 自定义策略开发
```python
from quant.strategies.base_strategy import BaseStrategy

class CustomGridStrategy(BaseStrategy):
    def __init__(self, **params):
        super().__init__(**params)
        # 自定义初始化逻辑
    
    def generate_signals(self, data):
        # 自定义信号生成逻辑
        pass
    
    def execute_trades(self, signals):
        # 自定义交易执行逻辑
        pass
```

## 📚 相关文档

- [快速开始指南](GETTING_STARTED.md)
- [新闻分析指南](NEWS_ANALYSIS_GUIDE.md)
- [配置说明](CONFIGURATION.md)
- [技术架构文档](ARCHITECTURE.md)

## ⚠️ 免责声明

本指南仅供学习和研究使用，不构成投资建议。实际投资请谨慎决策，风险自负。量化交易存在系统性风险，过往表现不代表未来收益。 