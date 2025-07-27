# 量化交易系统 (Quantitative Trading System)

基于多数据源的量化交易策略回测和投资新闻分析系统，包含网格交易策略和智能新闻投资分析两大核心功能模块。

## 🎯 核心功能

### 1. 交易策略系统
- **多数据源支持**: 支持Tushare、Yahoo Finance等多种数据API，自动切换最佳可用数据源
- **智能缓存系统**: 按provider和API类型分层缓存，避免重复API调用，显著提升性能
- **网格策略**: 实现完整的网格交易策略逻辑，支持震荡市场获利
- **均线交叉策略**: 基于移动平均线交叉信号的趋势跟踪策略，适合趋势市场
- **回测引擎**: 支持历史数据回测和性能分析
- **智能优化**: 集成多种AI优化算法（随机搜索、遗传算法、粒子群优化、综合优化）
- **参数空间**: 支持连续、离散、分类参数的自动优化搜索
- **可视化分析**: 提供交互式图表和详细报告
- **Excel导出**: 支持结果导出到Excel文件

### 2. 投资新闻分析系统
- **自动新闻收集**: 从Tushare Pro、新浪财经、东方财富等多源收集财经新闻
- **大模型分析**: 集成GPT-4等大语言模型进行投资分析
- **多维度评估**: 市场情绪、价格影响、风险评估、投资建议
- **统一数据格式**: 支持API和本地文件两种数据来源，统一中间格式存储
- **两阶段分析**: 粗分析筛选相关新闻，精细分析生成投资建议
- **定时报告**: 自动化每日报告生成（支持JSON和Markdown格式）

## 🚀 快速开始

⚡ **5分钟上手**: 查看 [QUICK_START.md](docs/QUICK_START.md) 快速开始指南

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 环境配置

#### 统一环境变量配置
复制 `env_example_unified.txt` 为 `.env` 并配置：

```bash
cp env_example_unified.txt .env
```

配置内容：
```bash
# === 网格交易系统配置 ===
# Tushare配置 (推荐用于A股)
TUSHARE_TOKEN=your_tushare_token_here

# === 新闻分析系统配置 ===
# 昂贵模型配置 (用于精细分析)
LLM_API_KEY=your_premium_llm_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4

# 廉价模型配置 (用于粗分析)
CHEAP_LLM_API_KEY=your_cheap_llm_api_key_here
CHEAP_LLM_BASE_URL=https://your-cheap-provider.com/v1
CHEAP_LLM_MODEL=gpt-3.5-turbo

# 外部新闻数据路径 (可选)
NEWS_EXTERNAL_PATH=/path/to/external/news/data
```

#### 数据源说明
- **Tushare**: 注册账号 https://tushare.pro/ 获取Token，用于A股数据和新闻
- **Yahoo Finance**: 免费，支持全球股票市场，无需额外配置
- **大模型API**: 支持OpenAI、Claude等，用于新闻分析

### 3. 系统入口使用

#### 🚀 统一CLI入口（推荐）
```bash
# 查看所有可用功能
python bin/run.py --help

# 🔍 系统状态检查
python bin/run.py system status

# 📊 交易策略功能
python bin/run.py trading list                        # 列出可用策略
python bin/trading_strategy.py backtest unified_grid 000001.SZ     # 网格策略回测
python bin/trading_strategy.py backtest ma_crossover 002594.SZ     # 均线交叉策略回测

# 🚀 高级优化功能
python bin/trading_strategy.py optimize unified_grid 002594.SZ --optimization-method comprehensive  # 综合优化（随机+遗传+粒子群）
python bin/trading_strategy.py optimize unified_grid 002594.SZ --optimization-method random        # 随机搜索优化
python bin/trading_strategy.py optimize unified_grid 002594.SZ --optimization-method genetic       # 遗传算法优化
python bin/trading_strategy.py optimize unified_grid 002594.SZ --optimization-method pso           # 粒子群优化

# 注：均线交叉策略暂不支持自动优化，建议手动测试不同参数组合

# 📰 新闻分析功能
python bin/run.py news list                           # 列出投资目标
python bin/run.py news collect --sources sina eastmoney  # 收集新闻
python bin/run.py news analyze --targets NASDAQ GOLD   # 分析新闻
python bin/run.py news report --days-back 3           # 生成投资日报

# ⚙️ 系统管理功能
python bin/run.py system config list                  # 列出配置
python bin/run.py system clean --type cache           # 清理缓存
```

#### 📦 模块化CLI（兼容）
```bash
# 使用quant模块入口（与上述功能相同）
python -m quant news analyze --targets nasdaq,gold
python -m quant trading backtest --symbol 002594.SZ
python -m quant config validate
```

#### 🎯 功能模块演示
```bash
# 网格策略分析演示
python demo/main.py
python demo/demo_new_architecture.py

# 完整策略发现和回测工作流程演示
python demo/experiment_backtest_workflow_demo.py
python demo/comprehensive_report_demo.py

# 新闻收集和分析演示
python demo/news_collection_demo.py
python demo/investment_analysis_demo.py
python demo/unified_news_analysis_demo.py
```

#### 🔧 独立功能入口（高级用户）
```bash
# 直接使用专门的功能脚本
python bin/trading_strategy.py backtest grid 000001.SZ
python bin/investment_news.py report --targets NASDAQ
```

## 📁 系统架构

```
quantitative_trading/
├── quant/                              # 核心量化模块
│   ├── core/                           # 核心模块
│   │   ├── config_manager.py          # 统一配置管理
│   │   ├── data_manager.py            # 统一数据管理
│   │   └── report_generator.py        # 统一报告生成
│   ├── data_providers/                # 数据提供者模块
│   │   ├── cache_manager.py           # 缓存管理器
│   │   ├── cached_provider.py         # 缓存代理类
│   │   └── data_provider_factory.py   # 数据提供者工厂
│   ├── strategies/                     # 交易策略模块
│   │   └── grid_strategy.py           # 网格策略实现
│   ├── engines/                        # 回测引擎模块
│   │   ├── backtest_engine.py         # 回测引擎
│   │   └── strategy_optimizer.py      # 高级策略优化器（含智能优化算法）
│   ├── company_analysis/              # 公司分析模块
│   │   ├── company_configs.py         # 公司配置管理
│   │   └── stock_analyzer.py          # 通用股票分析器
│   └── news/                          # 新闻分析模块
│       ├── news_collector.py          # 新闻收集器
│       ├── news_analyzer.py           # 新闻分析器
│       └── investment_analyzer.py     # 投资分析器
├── config/                            # 配置文件目录
│   ├── system_config.yaml            # 系统总配置
│   ├── data_sources.yaml             # 数据源配置
│   ├── investment_targets.yaml       # 投资品配置
│   ├── trading_config.yaml           # 交易策略配置
│   └── news_analysis_config.yaml     # 新闻分析配置
├── demo/                              # 演示脚本目录
│   ├── main.py                        # 网格策略演示
│   ├── news_collection_demo.py        # 新闻收集演示
│   ├── investment_analysis_demo.py    # 投资分析演示
│   └── unified_news_analysis_demo.py  # 统一新闻分析演示
├── cache/                             # API缓存目录
│   ├── tushare/                       # Tushare数据缓存
│   │   └── news/                      # 新闻数据缓存
│   ├── yahoo/                         # Yahoo Finance数据缓存
│   └── news_analysis/                 # LLM分析缓存
├── data/                              # 本地数据存储目录
│   ├── news_unified/                  # 统一格式的新闻数据
│   └── news_processed/                # 处理后的新闻数据
├── reports/                           # 分析报告目录
│   ├── daily/                         # 按分析类型组织
│   │   ├── grid_strategy/             # 网格策略报告
│   │   ├── technical_analysis/        # 技术分析报告
│   │   └── investment_analysis/       # 投资分析报告
│   └── YYYYMMDD_HHMM/                # 按时间戳组织（兼容旧格式）
├── docs/                              # 文档目录
│   ├── GETTING_STARTED.md             # 快速开始指南
│   ├── TRADING_GUIDE.md               # 交易策略指南 (含 Agent 架构)
│   ├── NEWS_ANALYSIS_GUIDE.md         # 新闻分析指南
│   ├── CONFIGURATION.md               # 配置说明
│   ├── ARCHITECTURE.md                # 技术架构文档
│   └── AGENT_ARCHITECTURE.md          # Agent 智能交易架构指南
├── requirements.txt                   # 依赖包
└── env_example_unified.txt           # 统一环境变量示例
```

## 💡 使用示例

### 网格交易策略分析

#### 配置化公司分析（推荐）
```python
from quant.company_analysis import UniversalStockAnalyzer, listAvailableCompanies

# 查看可用的公司配置
companies = listAvailableCompanies()
for company in companies:
    print(f"{company['name']} ({company['symbol']}) - {company['industry']}")

# 创建分析器
analyzer = UniversalStockAnalyzer('tushare')

# 分析比亚迪股票（自动使用预配置参数）
results = analyzer.analyzeCompany('BYD', saveReports=True)
print(f"分析完成，报告保存在 reports/ 目录")
```

#### 传统回测方式
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

### 新闻投资分析

#### 完整两阶段分析
```python
from quant.news import TwoStageNewsAnalyzer

# 初始化分析器
analyzer = TwoStageNewsAnalyzer()

# 运行完整分析流程
result = analyzer.runFullAnalysis()

# 查看投资建议
recommendations = result.get('overall_recommendations', {})
for symbol, rec in recommendations.items():
    print(f"{symbol}: {rec['recommended_action']} (置信度: {rec['confidence']:.1%})")
```

#### 新闻收集
```python
from quant.news import UnifiedNewsCollector

# 初始化收集器
collector = UnifiedNewsCollector()

# 收集所有新闻
all_news = collector.collectAllNews()
print(f"收集到 {len(all_news)} 篇新闻")

# 根据投资品收集相关新闻
target_news = collector.collectForInvestmentTargets()
for target_name, articles in target_news.items():
    print(f"{target_name}: {len(articles)} 篇相关文章")
```

## 🧠 智能优化算法

系统集成了多种先进的AI优化算法，用于自动寻找最优策略参数：

### 优化方法对比
- **随机搜索优化**: 在参数空间中随机采样，适合快速探索
- **遗传算法优化**: 模拟自然进化过程，包含选择、交叉、变异操作
- **粒子群优化**: 模拟鸟群觅食行为，全局搜索能力强
- **综合优化**: 同时运行多种算法并比较结果，获得最优解

### 参数空间定义
- **连续参数**: 如网格间距（0.01-0.05），支持浮点数范围
- **离散参数**: 如网格层数（6,8,10,12,15），支持固定数值列表
- **分类参数**: 如投资间隔（daily/weekly/monthly），支持类别选择

### 智能评分函数
综合考虑多个指标：
- 总收益率权重：100%
- 回撤控制奖励：基于 1/max_drawdown
- 胜率奖励：20%
- 夏普比率奖励：15%（限制上限为3）
- 适度交易奖励：基于交易频次

## 🔧 交易策略说明

### 网格交易策略

网格交易是一种量化交易策略，通过在预设的价格网格上进行买入和卖出操作来获利：

#### 策略原理
1. **网格设置**: 在当前价格上下设置多个买入和卖出价格网格
2. **低买高卖**: 当价格下跌触发买入网格时买入股票，当价格上涨触发卖出网格时卖出股票
3. **震荡获利**: 在价格震荡的市场中通过频繁的低买高卖获取收益

#### 策略参数
- `gridLevels`: 网格层数（默认10层）
- `gridSpacing`: 网格间距百分比（默认2%）
- `maxPosition`: 最大仓位金额（默认10万）
- `commission`: 手续费率（默认0.03%）
- `slippage`: 滑点率（默认0.1%）

### 均线交叉策略 🎆

均线交叉策略是一种基于技术分析的趋势跟踪策略，通过判断短期均线和长期均线的交叉信号进行交易：

#### 策略原理
1. **金叉买入**: 当短期均线上穿长期均线时，视为买入信号
2. **死叉卖出**: 当短期均线下穿长期均线时，视为卖出信号
3. **趋势跟踪**: 适合有明确趋势的市场，能够捕捉价格运动方向

#### 策略参数
- `ma_short`: 短期均线周期（默认5日）
- `ma_long`: 长期均线周期（默认10日）
- `commission`: 手续费率（默认0.03%）
- `slippage`: 滑点率（默认0.1%）
- `position_size`: 仓位比例（默认全仓）

#### 使用示例
```bash
# 基本回测（默认MA5/MA10）
python bin/trading_strategy.py backtest ma_crossover 002594.SZ

# 自定义参数回测
python bin/trading_strategy.py backtest ma_crossover 002594.SZ \
    --ma-short 10 --ma-long 20 --initial-balance 50000

# 指定回测期间
python bin/trading_strategy.py backtest ma_crossover 002594.SZ \
    --start-date 2023-01-01 --end-date 2024-12-31
```

#### 参数优化建议
- **MA5/MA10**: 反应灵敏，适合短线交易
- **MA10/MA20**: 较为稳健，适合中线交易
- **MA20/MA60**: 过滤噪音，适合长线交易

#### 实战案例
基于比亚迪股票（2023-2025）的回测结果：
- **MA5/MA10**: 49.45%收益率，超越基准19.72%
- **MA10/MA20**: -12.12%收益率，表现不佳
- **MA5/MA20**: -23.22%收益率，表现较差

**结论**: 对于比亚迪这类成长股，短周期均线组合(MA5/MA10)表现最佳

## 📊 新闻分析维度

- **市场情绪**: positive/negative/neutral
- **价格影响**: strong_positive/positive/neutral/negative/strong_negative
- **风险评估**: low/medium/high
- **投资建议**: strong_buy/buy/hold/sell/strong_sell
- **置信度**: 0.0-1.0

## 🎯 支持的投资品类

### 网格交易策略
- **A股**: 上交所、深交所所有股票
- **港股**: 支持通过Yahoo Finance
- **美股**: 支持主要美股标的

### 新闻投资分析
- **股票指数**: 纳斯达克、标普500、沪深300等
- **国际股票**: 印度股市、中国A股、港股等
- **商品**: 黄金、原油、农产品等
- **加密货币**: 比特币、以太坊等（可扩展）

## 📈 报告示例

### 网格策略回测报告
```
总收益率: 15.30%
夏普比率: 1.85
最大回撤: -8.20%
胜率: 68.5%
交易次数: 45
```

### 投资分析日报
```markdown
# 投资分析日报

**报告日期**: 2024-01-15
**分析时间**: 2024-01-15T09:00:00

## 整体概览
- **市场展望**: optimistic
- **投资建议分布**: {'buy': 2, 'hold': 1}

## 个股分析
### 纳斯达克指数 (NASDAQ)
- **新闻数量**: 15
- **市场情绪**: positive
- **投资建议**: buy
- **置信度**: 0.85
```

## 🔄 定时任务

系统支持自动化运行：
- **生产模式**: 每天9:00和18:00自动分析
- **测试模式**: 每2分钟执行一次（用于测试）
- **手动模式**: 按需执行分析

## 📚 详细文档

- [快速开始指南](docs/QUICK_START.md)
- [完整工作流程演示](docs/COMPLETE_WORKFLOW_DEMO.md) - **推荐** 策略发现和回测完整流程
- [实验工作流程](docs/EXPERIMENT_WORKFLOW.md) - Agent 实验和回测详细说明
- [交易策略指南](docs/TRADING_GUIDE.md) - 包含基于 Agent 的智能交易架构
- [Agent 架构指南](docs/AGENT_ARCHITECTURE.md) - 详细的 Agent 系统设计和使用
- [新闻分析指南](docs/NEWS_ANALYSIS_GUIDE.md)
- [配置说明](docs/CONFIGURATION.md)
- [技术架构文档](docs/ARCHITECTURE.md)
- [项目优化报告](docs/PROJECT_OPTIMIZATION_REPORT.md)

## 📝 系统要求

- Python 3.8+
- 有效的Tushare Pro账户（用于A股数据和新闻）
- 大模型API密钥（OpenAI/Claude等，用于新闻分析）
- 稳定的网络连接

## 🎯 使用场景

### 网格交易策略
- **个人投资者**: 震荡市场的量化交易策略
- **机构投资者**: 策略回测和参数优化
- **量化研究**: 策略有效性验证

### 新闻投资分析
- **个人投资者**: 每日投资决策参考
- **投资机构**: 市场情绪监控和风险评估
- **研究机构**: 新闻事件对市场影响的量化分析

## ⚠️ 免责声明

本系统仅提供投资分析和建议参考，不构成具体的投资指导。投资有风险，决策需谨慎。请结合多方面信息和专业建议进行投资决策。

---

欢迎使用量化交易系统！如有问题或建议，请查看详细文档或提交Issue。 