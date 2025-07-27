# Quantitative Trading Project Agent Guide

## 项目概述

这是一个专业的量化交易系统，集成了多种交易策略、数据管理、回测引擎和分析工具。项目采用模块化设计，支持DCA、网格、动量等多种策略，并提供完整的分析框架。

## 核心架构

### 目录结构
```
quantitative_trading/
├── bin/                    # 主要执行脚本
│   ├── run.py             # 统一入口脚本（推荐）
│   ├── trading_strategy.py # 交易策略专用脚本
│   └── investment_news.py  # 投资新闻分析脚本
├── quant/                  # 核心量化交易模块
│   ├── strategies/         # 交易策略实现
│   ├── engines/           # 回测和优化引擎
│   ├── data_providers/    # 数据提供者
│   ├── agents/            # 智能代理
│   ├── news/              # 新闻分析模块
│   └── config/            # 配置管理
├── analyst/               # 分析工具包
│   ├── stock_strategy_analyzer.py  # 通用股票策略分析器
│   └── README.md          # 分析工具使用说明
├── config/                # 配置文件
│   ├── stocks/            # 个股配置
│   └── *.yaml             # 系统配置
├── data/                  # 数据存储
│   ├── news/              # 新闻数据
│   └── tushare/           # 股票数据
├── reports/               # 报告输出
├── cache/                 # API缓存
└── tools/                 # 辅助工具
```

### 主要模块

#### 1. 交易策略 (quant/strategies/)
- **UnifiedGridTradingStrategy**: 统一网格交易策略
- **AdaptiveGridStrategy**: 自适应网格策略  
- **MACrossoverStrategy**: 均线交叉策略 - 基于移动平均线交叉信号的趋势跟踪策略
- 支持动态网格中心调整和仓位管理

#### 2. 回测引擎 (quant/engines/)
- **BacktestEngine**: 回测引擎
- **StrategyOptimizer**: 策略优化器
- 支持多种优化算法（随机搜索、遗传算法、粒子群优化）

#### 3. 数据管理 (quant/data_providers/)
- **DataProviderFactory**: 数据提供者工厂
- **CachedProvider**: 缓存数据提供者
- 支持Tushare、Yahoo等数据源

#### 4. 智能代理 (quant/agents/)
- **AgentManager**: 代理管理器
- **StrategyAgent**: 策略代理基类
- **MomentumAgent**: 动量策略代理
- 支持多策略组合和自动优化

#### 5. 分析工具 (analyst/)
- **StockStrategyAnalyzer**: 通用股票策略分析器
- 支持DCA、网格、动量策略的适配性评分
- 自动生成分析报告和可视化图表

## 开发规范

### 代码风格
1. **中文注释**: 所有注释、日志、异常信息使用中文
2. **驼峰命名**: 函数名和变量名采用驼峰风格 (camelCase)
3. **英文标识**: 类名、模块名、文件名使用英文
4. **统一错误处理**: 使用 `quant.core.utils` 中的统一错误处理机制

### 配置管理
- **环境变量**: 使用 `.env` 文件管理API密钥
- **YAML配置**: 使用 `config/` 目录下的YAML文件管理系统配置
- **股票配置**: 单独的股票配置文件存储在 `config/stocks/` 目录

### 数据管理
- **缓存机制**: 使用 `cache/` 目录缓存API响应，避免重复请求
- **数据存储**: 原始数据存储在 `data/` 目录，按提供者分类
- **报告输出**: 分析结果统一输出到 `reports/` 目录

## 策略分析指南

### 策略适配性评分体系

#### 1. DCA策略评分标准
- **低波动率** (<0.3): 30分，适合定期投资
- **强趋势** (>0.5): 25分，长期上涨趋势
- **高夏普比率** (>0.5): 20分，风险调整收益
- **价格稳定性** (CV<0.3): 15分，价格波动可控
- **RSI适中** (<60): 10分，技术指标健康

#### 2. 网格策略评分标准
- **中等波动率** (0.2-0.6): 30分，适合网格交易
- **弱趋势** (<0.3): 25分，震荡市场
- **价格波动适中** (CV>0.2): 20分，提供套利机会
- **RSI合理区间** (40-70): 15分，技术指标平衡
- **成交量稳定** (<1.0): 10分，流动性充足

#### 3. 动量策略评分标准
- **高波动率** (>0.4): 25分，价格变化剧烈
- **强趋势** (>0.4): 30分，明确方向性
- **成交量活跃** (>0.5): 20分，市场参与度高
- **RSI高波动** (>10): 15分，技术指标敏感
- **收益性** (>0.3): 10分，有盈利潜力

### 为什么A股不适合动量策略？

基于对比亚迪、招商银行、长江电力、紫金矿业四支代表性股票的分析，发现A股市场普遍不适合动量策略的原因：

#### 1. 市场特征不匹配
- **震荡为主**: 四支股票均显示为"震荡"市场环境，缺乏明确的单向趋势
- **趋势强度不足**: 所有股票的趋势强度都低于动量策略要求的0.4阈值
- **波动性质不佳**: 虽然部分股票波动率较高，但多为无序波动而非趋势性波动

#### 2. 技术指标特征
- **RSI均值集中**: 四支股票的RSI均值都在40-60区间，缺乏极端值
- **RSI标准差偏低**: 大多数股票RSI标准差低于动量策略要求的10
- **成交量波动适中**: 成交量活跃度未达到动量策略要求的0.5阈值

#### 3. 具体评分分析
- **比亚迪**: 40分 - 高波动率(30.88%)但趋势不明确
- **招商银行**: 40分 - 中等波动率(22.81%)，趋势强度不足
- **长江电力**: 60分 - 低波动率(15.82%)，稳定型股票
- **紫金矿业**: 50分 - 高波动率(31.64%)但震荡特征明显

#### 4. A股市场特性
- **政策导向**: 受政策影响较大，趋势容易被打断
- **散户主导**: 散户投资者占比高，容易形成羊群效应
- **涨跌停限制**: 10%的涨跌停限制影响动量策略的效果
- **T+1交易**: 当日买入无法卖出，影响动量策略的灵活性

## 常用操作指南

### 1. 快速开始
```bash
# 检查系统状态
python bin/run.py system status

# 列出可用交易策略
python bin/trading_strategy.py list

# 分析股票策略适配性
python analyst/stock_strategy_analyzer.py --symbol 000001.SZ

# 运行网格策略回测
python bin/trading_strategy.py backtest unified_grid 000001.SZ

# 运行均线交叉策略回测
python bin/trading_strategy.py backtest ma_crossover 002594.SZ

# 自定义均线参数回测
python bin/trading_strategy.py backtest ma_crossover 002594.SZ --ma-short 5 --ma-long 20
```

### 2. 策略优化  
```bash
# 网格策略综合优化（推荐）
python bin/trading_strategy.py optimize unified_grid 000001.SZ

# 指定优化方法
python bin/trading_strategy.py optimize unified_grid 000001.SZ --optimization-method genetic

# 注：均线交叉策略暂不支持自动优化，建议手动测试不同参数组合
```

### 3. 数据获取
```bash
# 获取股票数据
python -c "
from quant.data_providers.data_provider_factory import DataProviderFactory
provider = DataProviderFactory.create('tushare')
data = provider.getStockData('000001.SZ', '20240101', '20241231', 'D')
print(data.head())
"
```

### 4. 新闻分析
```bash
# 收集新闻
python bin/investment_news.py collect

# 生成投资分析报告
python bin/investment_news.py report
```

## 配置文件说明

### 环境变量 (.env)
```bash
# 必需配置
TUSHARE_TOKEN=your_tushare_token

# 可选配置
LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4
```

### 系统配置 (config/system_config.yaml)
```yaml
# 数据源配置
data_providers:
  default: tushare
  tushare:
    enabled: true
  yahoo:
    enabled: false

# 缓存配置
cache:
  enabled: true
  ttl: 86400  # 24小时
```

### 交易配置 (config/trading_config.yaml)
```yaml
# 默认策略参数
strategies:
  unified_grid:
    gridLevels: 10
    gridSpacing: 0.025
    baseRatio: 0.5
    commission: 0.0003
```

## AI助手使用指南

### 开发新功能
1. **查看现有代码**: 先了解相关模块的实现
2. **遵循规范**: 按照项目的代码风格和架构模式
3. **测试验证**: 编写测试用例验证功能
4. **文档更新**: 更新相关文档和配置

### 问题诊断
1. **检查日志**: 查看 `logs/` 目录下的日志文件
2. **验证配置**: 使用 `python bin/run.py system status` 检查配置
3. **清理缓存**: 使用 `python tools/cache_manager.py clear` 清理缓存
4. **数据验证**: 确认数据源连接和数据完整性

### 性能优化
1. **使用缓存**: 充分利用缓存机制避免重复API调用
2. **并行处理**: 在适当的地方使用多线程或多进程
3. **内存管理**: 及时释放大数据对象的内存
4. **算法优化**: 选择合适的算法和数据结构

## 项目扩展建议

### 短期改进
1. **策略扩展**: ✅ 均线交叉策略已集成，继续增加均值回归、配对交易等策略
2. **优化用户界面**: 开发Web界面或GUI工具
3. **增强风险管理**: 添加止损、仓位管理等功能
4. **实时交易**: 集成实盘交易接口
5. **均线策略优化**: 为均线交叉策略添加自动参数优化功能

### 长期规划
1. **机器学习**: 集成更多ML算法进行策略优化
2. **多市场支持**: 扩展到港股、美股等市场
3. **云端部署**: 支持云端运行和分布式计算
4. **社区功能**: 策略分享和讨论平台

## 💡 最新功能更新

### 均线交叉策略集成 (2025-07-27)
- ✅ **策略实现**: 完整的MA交叉策略，支持金叉买入、死叉卖出
- ✅ **CLI集成**: 集成到统一CLI工具，避免单独脚本增加项目熵值
- ✅ **参数化**: 支持自定义短期/长期均线周期（默认MA5/MA10）
- ✅ **性能分析**: 完整的回测结果、交易记录、基准对比
- ✅ **实战验证**: 比亚迪股票回测显示49.45%收益率，跑赢基准19.72%

#### 使用示例
```bash
# 基本回测（默认MA5/MA10）
python bin/trading_strategy.py backtest ma_crossover 002594.SZ

# 自定义参数
python bin/trading_strategy.py backtest ma_crossover 002594.SZ --ma-short 10 --ma-long 20 --initial-balance 50000

# 指定回测期间  
python bin/trading_strategy.py backtest ma_crossover 002594.SZ --start-date 2023-01-01 --end-date 2024-12-31
```

---

*最后更新: 2025-07-27*
