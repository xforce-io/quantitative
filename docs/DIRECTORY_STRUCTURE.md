# 项目目录结构说明

本文档描述了量化交易项目的目录结构和各目录的用途。

## 顶级目录结构

```
quantitative_trading/
├── README.md              # 项目说明文档
├── GEMINI.md              # Gemini AI助手配置
├── CLAUDE.md              # Claude AI助手配置
├── requirements.txt       # Python依赖包列表
├── mypy.ini               # MyPy类型检查配置
├── pytest.ini             # Pytest测试配置
│
├── bin/                   # 脚本和工具目录
│   ├── examples/          # 演示脚本
│   └── *.py / *.sh        # CLI工具脚本
│
├── config/                # 配置文件目录
│   ├── config.yaml        # 主配置文件
│   ├── portfolios.yaml    # 投资组合配置
│   └── ...                # 其他配置
│
├── quant/                 # 核心代码目录
├── tests/                 # 单元测试目录
├── docs/                  # 项目文档目录
│
├── data/                  # 数据存储目录
├── cache/                 # API缓存目录
├── logs/                  # 日志目录
├── reports/               # 分析报告目录
│
└── venv/                  # Python虚拟环境
```

## 各目录详细说明

### `/bin/` - 脚本和工具
存放所有可执行脚本和工具：
- **入口脚本**: `advisor.py`, `backtest.py`, `analyze_portfolio.py`
- **分析工具**: `momentum_analyzer.py`, `screen_etfs.py`
- **辅助工具**: `system_check.py`, `verify_etf_codes.py`, `calculate_returns.py`
- **演示脚本**: `examples/` 子目录

### `/config/` - 配置文件
所有配置文件统一存放：
- `config.yaml` - 系统主配置
- `portfolios.yaml` - 投资组合配置
- `screens.yaml` - 筛选器配置
- `etf_categories.yaml` - ETF分类
- `industry_taxonomy.yaml` - 行业分类

### `/quant/` - 核心代码
核心量化分析代码，按功能模块组织：
- `agents/` - 智能代理
- `analysis/` - 分析模块
- `cli/` - 命令行接口
- `config/` - 配置加载器
- `core/` - 核心基础设施
- `data_providers/` - 数据提供者
- `engines/` - 执行引擎
- `strategies/` - 交易策略

### `/docs/` - 项目文档
所有项目文档：
- 架构设计、使用指南、功能说明
- 开发规范、任务计划

### `/tests/` - 单元测试
项目测试代码。

### `/data/` - 数据存储
股价、ETF等市场数据。

### `/cache/` - 缓存
API响应缓存，避免重复调用。

### `/logs/` - 日志
系统运行日志。

### `/reports/` - 报告
生成的分析报告。

## 开发建议

- **新工具** → `bin/`
- **演示脚本** → `bin/examples/`
- **功能模块** → `quant/` 对应子目录
- **配置文件** → `config/`
- **文档** → `docs/`
- 避免在根目录创建临时文件