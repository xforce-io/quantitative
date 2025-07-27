# 量化交易系统 Quantitative Trading System

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

一个集成了交易策略分析和新闻投资建议的量化交易系统。系统采用模块化设计，支持多种策略回测、新闻情感分析和智能投资建议生成。

## 🎯 核心功能

### 1. 交易策略分析
- **网格交易策略**：支持股票和基金的网格交易策略分析
- **技术指标分析**：集成多种技术指标进行趋势分析
- **策略回测**：基于历史数据的策略回测和性能评估
- **参数优化**：使用遗传算法等方法进行策略参数优化

### 2. 新闻投资分析
- **多源新闻收集**：支持Tushare API和本地新闻数据
- **智能内容分析**：使用大语言模型进行新闻内容分析
- **情感分析**：评估新闻对投资品的情感倾向
- **投资建议生成**：基于新闻分析生成投资建议

### 3. 投资品支持
- **股票指数**：纳斯达克指数、沪深300等
- **国际股票**：印度股票等新兴市场
- **商品期货**：黄金等避险资产
- **ETF基金**：相关ETF产品分析

## 🚀 快速开始

### 环境要求
- Python 3.8+
- 推荐使用虚拟环境

### 安装依赖
```bash
pip install -r requirements.txt
```

### 配置环境变量
复制环境变量示例文件并配置：
```bash
cp env_example_unified.txt .env
```

编辑 `.env` 文件，配置必要的API密钥：
- `TUSHARE_TOKEN`: Tushare数据源API密钥
- `LLM_API_KEY`: 大语言模型API密钥
- `CHEAP_LLM_API_KEY`: 廉价模型API密钥（可选）

### 统一CLI入口
```bash
# 查看帮助
python -m quant --help

# 新闻分析
python -m quant news analyze --targets nasdaq,gold --days 7

# 交易策略分析
python -m quant trading analyze --symbol 002594.SZ --strategy grid

# 配置验证
python -m quant config validate
```

### 快速示例
```bash
# 运行新闻投资分析示例
python demo/investment_news_analysis_demo.py

# 运行交易策略回测示例
python demo/grid_trading_demo.py
```

## 📁 项目结构

```
quantitative_trading/
├── quant/                          # 核心模块
│   ├── core/                       # 核心功能
│   │   ├── config_manager.py       # 配置管理
│   │   ├── data_manager.py         # 数据管理
│   │   └── report_generator.py     # 报告生成
│   ├── trading/                    # 交易策略模块
│   │   ├── strategies/             # 策略实现
│   │   ├── backtesting/           # 回测引擎
│   │   └── optimization/          # 参数优化
│   ├── news/                       # 新闻分析模块
│   │   ├── collectors/            # 新闻收集
│   │   ├── analyzers/             # 新闻分析
│   │   └── investment/            # 投资建议
│   └── utils/                      # 工具模块
├── config/                         # 配置文件
│   ├── system_config.yaml         # 系统总配置
│   ├── data_sources.yaml          # 数据源配置
│   ├── investment_targets.yaml    # 投资品配置
│   ├── trading.yaml               # 交易配置
│   └── news_analysis_config.yaml  # 新闻分析配置
├── demo/                           # 示例脚本
├── data/                           # 数据目录
├── cache/                          # 缓存目录
├── reports/                        # 报告输出
├── logs/                           # 日志文件
└── docs/                           # 文档
```

## 📊 系统架构

系统采用模块化设计，主要包含以下组件：

### 配置管理层
- **ConfigManager**: 统一配置管理，支持多文件配置和环境变量替换
- **环境变量管理**: 统一的环境变量配置和验证

### 数据管理层
- **DataManager**: 统一数据接口，支持多数据源
- **缓存机制**: 智能缓存策略，减少API调用成本
- **数据标准化**: 统一的数据格式和验证

### 业务逻辑层
- **交易策略模块**: 策略实现、回测、优化
- **新闻分析模块**: 新闻收集、分析、投资建议
- **报告生成**: 多格式报告输出

### 工具支持层
- **日志管理**: 分级日志和日志轮转
- **错误处理**: 统一异常处理和重试机制
- **性能监控**: 系统性能指标监控

## 🔧 配置说明

### 系统配置
主要配置文件位于 `config/` 目录：

1. **system_config.yaml**: 系统总配置
2. **data_sources.yaml**: 数据源配置  
3. **investment_targets.yaml**: 投资品配置
4. **trading.yaml**: 交易策略配置
5. **news_analysis_config.yaml**: 新闻分析配置

### 投资品配置
在 `config/investment_targets.yaml` 中配置关注的投资品：
```yaml
targets:
  - name: "纳斯达克指数"
    symbol: "NASDAQ"
    keywords: ["NASDAQ", "纳斯达克", "科技股"]
    weight: 0.3
```

### 新闻分析配置
支持两阶段分析模式：
- **阶段1**: 使用廉价模型进行粗分析
- **阶段2**: 使用高质量模型进行精细分析

## 📈 使用示例

### 新闻投资分析
```python
from quant.core.config_manager import ConfigManager
from quant.core.data_manager import DataManager
from quant.news.analyzers.news_analyzer import NewsAnalyzer

# 初始化管理器
config_manager = ConfigManager()
data_manager = DataManager(config_manager)

# 获取新闻数据
news_data = data_manager.get_news_data(days_back=7)

# 分析新闻
analyzer = NewsAnalyzer(config_manager)
analysis_results = analyzer.analyze_news_batch(news_data)
```

### 交易策略回测
```python
from quant.trading.strategies.grid_strategy import GridStrategy
from quant.trading.backtesting.backtest_engine import BacktestEngine

# 创建策略
strategy = GridStrategy(
    grid_levels=10,
    grid_spacing=0.02,
    max_position=100000
)

# 运行回测
engine = BacktestEngine()
results = engine.run_backtest(
    strategy=strategy,
    symbol="002594.SZ",
    start_date="2023-01-01",
    end_date="2024-01-01"
)
```

## 🔌 扩展开发

### 添加新的交易策略
1. 在 `quant/trading/strategies/` 下创建策略类
2. 继承 `BaseStrategy` 基类
3. 实现必要的接口方法

### 添加新的数据源
1. 在 `quant/data/` 下创建数据源适配器
2. 实现统一的数据接口
3. 在配置文件中添加数据源配置

### 添加新的分析模块
1. 在相应模块目录下创建分析器
2. 实现标准的分析接口
3. 集成到主分析流程中

## 📝 开发指南

### 代码规范
- 使用驼峰命名法命名函数和变量
- 注释、日志、异常信息使用英文
- 遵循PEP 8编码规范

### 测试
```bash
# 运行单元测试
python -m pytest tests/

# 运行集成测试
python -m pytest tests/integration/
```

### 文档
- API文档：`docs/API_REFERENCE.md`
- 配置文档：`docs/CONFIGURATION.md`
- 架构文档：`docs/ARCHITECTURE.md`

## 🤝 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

## 📄 许可证

本项目使用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 📞 联系我们

- 项目Issues: [GitHub Issues](https://github.com/your-username/quantitative_trading/issues)
- 电子邮件: your-email@example.com

## 🙏 致谢

感谢以下开源项目和服务：
- [Tushare](https://tushare.pro/) - 金融数据服务
- [OpenAI](https://openai.com/) - 大语言模型服务
- [Pandas](https://pandas.pydata.org/) - 数据分析库
- [Plotly](https://plotly.com/) - 数据可视化

---

**注意**: 本系统仅用于研究和教育目的，不构成投资建议。投资有风险，入市需谨慎。 