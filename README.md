# 量化交易系统 (Quantitative Trading System)

基于多数据源的量化交易策略回测与投资分析系统。整合 ETF 筛选、组合分析、投资顾问、策略回测、行业轮动、A 股低频策略、新闻事件概率推演于统一架构（v2.2.0）。

系统提供两套入口：

- **统一 CLI**：`python -m quant <command> <subcommand>` —— 适合脚本与自动化
- **Streamlit Web 平台**：决策驾驶舱，适合日常投研

---

## 🚀 快速开始

### 1. 安装依赖

**推荐使用 uv**：

```bash
# 安装 uv（如未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 同步依赖（自动创建虚拟环境）
uv sync

# 运行命令
uv run python -m quant system status
```

**或使用 pip**：

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

要求 Python ≥ 3.10。

### 2. 环境配置

在项目根目录创建 `.env` 文件，按需配置以下变量：

| 变量 | 用途 |
|------|------|
| `TUSHARE_TOKEN` | Tushare 数据源 token（A 股 / ETF / 指数主数据源） |
| `FRED_API_KEY` | FRED 宏观数据 API（流动性 / 利率分析） |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | LLM 集成（AI 分析、新闻事件解析） |
| `CHEAP_LLM_API_KEY` / `CHEAP_LLM_BASE_URL` / `CHEAP_LLM_MODEL` | 低成本 LLM（轻量调用） |
| `NEWS_EXTERNAL_PATH` | 外部新闻数据路径（可选） |

未配置 `TUSHARE_TOKEN` 时数据源回退到 Yahoo Finance（对 `.OF` 场外基金可能无数据）。

### 3. 系统检查

```bash
python -m quant system status
```

---

## 🧭 统一 CLI

入口：`python -m quant <command> <subcommand> [options]`。共 9 个命令模块。

| 命令 | 功能 | 主要子命令 |
|------|------|-----------|
| `data` | 数据层管理 | `status`、`price` |
| `etf` | ETF 筛选与估值 | `screen`、`single`、`config` |
| `screener` | 股票多因子排名 | `rank`、`profiles` |
| `rotation` | A 股行业 ETF 轮动 | `backtest`、`latest`、`precheck` |
| `lowfreq` | A 股月频低频策略 | `signals`、`backtest` |
| `portfolio` | 投资组合分析 | `analyze`、`list` |
| `advisor` | 投资顾问分析 | `single`、`comprehensive` |
| `strategy` | 交易策略回测 | `backtest`、`list` |
| `system` | 系统管理 | `status`、`clean`、`version` |

查看帮助：`python -m quant --help`、`python -m quant <command> --help`。

### data — 数据层

```bash
# 数据源与缓存状态
python -m quant data status

# 获取标准化价格数据
python -m quant data price 000300.SH --asset-type index --start 20240101 --end 20241231
```

### etf — ETF 筛选与估值

动量筛选（多周期收益率、RSI、MACD）+ 估值分析（历史分位数、均值回归、估值区间）+ 综合评分（高估降分、低估加分）。

```bash
# 按类型筛选（可选 broad_market / sector / thematic / bonds / commodities / international）
python -m quant etf screen --types broad_market --save

# 从配置篮子筛选（config/screens.yaml 中定义，如 INDUSTRY_ETF）
python -m quant etf screen --from-config INDUSTRY_ETF --save

# 分析单只 ETF（含估值）
python -m quant etf single 510300.SH

# 查看筛选配置 / 列出可用篮子
python -m quant etf config --show
python -m quant etf config --list
```

### screener — 股票多因子排名

```bash
# 对指定股票列表排名
python -m quant screener rank --symbols "000001.SZ,002594.SZ,600036.SH" --profile balanced

# 对配置股票池排名（如 BANK、SEMICONDUCTOR），取前 10
python -m quant screener rank --pool BANK --profile value --top 10

# 列出可用排名权重配置（config/ranking_profiles.yaml）
python -m quant screener profiles
```

### rotation — 行业 ETF 轮动

```bash
# 回测行业 ETF 轮动策略
python -m quant rotation backtest

# 生成最近月末目标持仓
python -m quant rotation latest

# 调仓日 T-1 实盘前置检查
python -m quant rotation precheck --from-latest
```

### lowfreq — A 股月频低频策略

```bash
# 生成月频趋势 / 波动率仓位信号
python -m quant lowfreq signals 000300.SH --start 20150101 --end 20241231

# 回测月频策略
python -m quant lowfreq backtest 000300.SH --start 20150101 --end 20241231
```

### portfolio — 投资组合分析

基于 `config/portfolios.yaml` 的 Sleeve 分层（现金 / 债券 / 防守 / 进攻）做组合级分析与再平衡建议。

```bash
# 分析已配置组合
python -m quant portfolio analyze USER_REAL_PORTFOLIO

# 保存 JSON + Markdown 报告到 reports/portfolio/YYYYMMDD
python -m quant portfolio analyze USER_REAL_PORTFOLIO --save

# 列出可用组合
python -m quant portfolio list
```

### advisor — 投资顾问

```bash
# 单标的深度分析（技术面 + 策略适配，不跑回测）
python -m quant advisor single 002594.SZ

# 综合分析（含策略回测）
python -m quant advisor comprehensive 002594.SZ
```

### strategy — 策略回测

```bash
# 回测指定策略
python -m quant strategy backtest ma_crossover 002594.SZ
python -m quant strategy backtest momentum 002594.SZ --start 20230101 --end 20241201

# 列出可用策略
python -m quant strategy list
```

内置策略（`STRATEGY_REGISTRY`）：

| 名称 | 适用场景 |
|------|---------|
| `ma_crossover` | 趋势市场，均线金叉 / 死叉 |
| `momentum` | 强势 / 突破行情 |
| `grid`（别名 `unified_grid`） | 震荡市场，区间套利 |
| `seykota_ma` | 趋势跟随（Ed Seykota 风格） |
| `dca` | 定额定投 |
| `pyramid_dca` | 金字塔加权定投 |
| `hold` | 买入持有基准 |

### system — 系统管理

```bash
python -m quant system status                 # 系统状态检查
python -m quant system clean --type all       # 清理缓存（all / etf / data ...）
python -m quant system version                # 版本信息
```

### 快捷脚本

`bin/` 目录提供常用操作的快捷脚本：

```bash
python bin/screen_etfs.py --types broad_market --save
python bin/analyze_portfolio.py USER_REAL_PORTFOLIO
python bin/advisor.py 002594.SZ
python bin/backtest.py ma_crossover 002594.SZ
python bin/system_check.py
```

---

## 🖥️ Web 可视化平台

基于 Streamlit 的决策驾驶舱，3 个核心页面：

| 页面 | 功能 |
|------|------|
| 📊 Dashboard | 总体研判、跨资产告警、资产池状态——一页看清该做什么 |
| 👀 Watchlist | 按资产池组织的持仓监控，含市场状态上下文与操作建议 |
| 🔍 Scanner | 机会扫描：A 股箱体突破、美股价值五因子、黄金与大宗商品 |

### 启动 Web 平台

```bash
scripts/run_web.sh start      # 后台启动
scripts/run_web.sh status     # 查看状态
scripts/run_web.sh logs       # 查看日志
scripts/run_web.sh restart    # 重启
scripts/run_web.sh stop       # 停止
```

启动后访问 http://localhost:8501

此外 `scripts/run_api.sh` 提供 FastAPI 服务入口（`start` / `dev` / `bg` / `stop` / `logs`）。

---

## 📰 新闻事件概率图

将自由文本新闻结构化为事件，沿因果知识图谱推演，输出 Bull / Base / Bear 三情景概率与受益 / 受损资产名单。

```python
from quant.analysis.event_investment import EventProbabilityService

svc = EventProbabilityService()
result = svc.analyze_news("美国扩大 AI 芯片出口限制，涵盖先进封装和服务器链条")
```

设计文档见 [docs/design/NEWS_EVENT_INVESTMENT_PROBABILITY_GRAPH_DESIGN.md](docs/design/NEWS_EVENT_INVESTMENT_PROBABILITY_GRAPH_DESIGN.md)。

---

## 💡 Python API

包顶层导出统一入口（详见 `quant/__init__.py`）：

```python
from quant import (
    get_config,              # 统一配置管理
    create_data_provider,    # 统一数据源
    STRATEGY_REGISTRY,       # 策略注册表
    BacktestEngine,          # 回测引擎
    PortfolioAnalyzer,       # 组合分析
    UnifiedAdvisor,          # 投资顾问
)
```

具体类的方法签名以源码为准（API 仍在演进中），CLI 是当前最稳定的使用接口。

---

## 🏗️ 架构与目录

系统采用 8 层分层架构：

```
Layer 0  core/         基础设施（配置、日志、异常、工具）
Layer 1  data/         数据层（Tushare / Yahoo，统一 Provider）
Layer 2  analysis/     分析层（估值、技术面、Alpha、轮动、事件推演等）
Layer 3  portfolio/    组合构建（等权、风险平价、再平衡）
Layer 4  risk/         风控（仓位限制、VaR、回撤监控）
Layer 5  strategies/   传统一体化策略
Layer 6  engines/      执行引擎（回测、优化）
Layer 7  agents/       智能体协调（可选）
Layer 8  bin/ + cli/   入口
```

顶层目录：

```
quantitative_trading/
├── quant/              核心量化交易包
│   ├── __main__.py     统一 CLI 入口
│   ├── cli/            9 个 CLI 命令模块
│   ├── core/           基础设施
│   ├── data/           数据层（providers、factor_store、fetchers）
│   ├── data_providers/ 数据源实现（Tushare、Yahoo、缓存）
│   ├── analysis/       分析层
│   ├── portfolio/      组合构建
│   ├── risk/           风控
│   ├── strategies/     交易策略
│   ├── engines/        执行引擎
│   ├── services/       服务层
│   ├── knowledge/      事件知识图谱
│   └── agents/         智能体
├── bin/                快捷脚本
├── scripts/            运维与研究脚本（run_web.sh、refresh_factors.py 等）
├── config/             配置文件（config.yaml、portfolios.yaml、screens.yaml ...）
├── web/                Streamlit Web 平台
├── tests/              测试（unit / integration / web）
├── docs/               文档
├── data/ cache/        数据与缓存（不进版本控制）
├── reports/            分析报告输出
└── experiments/        策略研究实验记录
```

---

## 🧪 测试

```bash
tests/run_tests.sh unit              # 单元测试
tests/run_tests.sh integration       # 集成测试
tests/run_tests.sh web               # 端到端测试（Playwright）
tests/run_tests.sh all --coverage    # 全量 + 覆盖率
```

---

## 📚 文档

- [文档导航](docs/README.md) — 全部文档入口
- [快速开始](docs/usage/quick_start/GETTING_STARTED.md) — 5 分钟上手
- [系统架构](docs/ARCHITECTURE.md) — 分层架构说明
- [目录结构](docs/DIRECTORY_STRUCTURE.md) — 项目目录布局
- [配置参考](docs/usage/configuration/CONFIGURATION.md) — 配置文件详解
- [交易指南](docs/usage/guides/TRADING_GUIDE.md) — 策略开发与使用
- [组合管理指南](docs/usage/guides/USER_PORTFOLIO_GUIDE.md)
- [协作规则](AGENTS.md) — 代码规范与文档约定

---

## ⚠️ 免责声明

本系统仅提供投资分析与建议参考，不构成具体投资指导。投资有风险，决策需谨慎。
