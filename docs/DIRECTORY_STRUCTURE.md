# 项目目录结构说明

本文档描述量化交易项目的目录结构和各目录用途。架构详情见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 顶级结构

```
quantitative_trading/
├── README.md              # 项目说明文档
├── AGENTS.md              # 智能体协作规则（代码 / 文档规范）
├── pyproject.toml         # 项目元数据与依赖
├── requirements.txt       # pip 依赖清单
├── uv.lock                # uv 依赖锁文件
├── mypy.ini               # MyPy 类型检查配置
├── pytest.ini             # Pytest 测试配置
├── .env                   # 环境变量（API key，不进版本控制）
│
├── quant/                 # 核心量化交易包（8 层架构）
├── web/                   # Streamlit Web 平台
├── bin/                   # 快捷脚本入口
├── scripts/               # 运维与研究脚本
├── tui/                   # 终端 UI
│
├── config/                # 配置文件
├── docs/                  # 项目文档
├── tests/                 # 测试（unit / integration / web）
│
├── data/                  # 市场数据存储（不进版本控制）
├── cache/                 # API 缓存（不进版本控制）
├── logs/ · log/           # 运行日志
├── reports/               # 生成的分析报告
├── experiments/           # 策略研究实验记录
└── baks/                  # 阶段性 / 归档文档（逐步淘汰）
```

## 各目录说明

### `quant/` — 核心代码

按 8 层架构组织（详见 ARCHITECTURE.md）：

- `__main__.py` — 统一 CLI 入口
- `cli/` — 9 个 CLI 命令模块
- `core/` — Layer 0 基础设施
- `data/` — Layer 1 数据层（`data_providers/` 为旧版实现，保留兼容）
- `analysis/` — Layer 2 分析层（估值、技术面、Alpha、轮动、事件推演等）
- `portfolio/` — Layer 3 组合层
- `risk/` — Layer 4 风控层
- `strategies/` — Layer 5 策略层
- `engines/` — Layer 6 执行引擎
- `agents/` — Layer 7 智能体（可选）
- `services/` — 服务层，封装跨层业务流程
- `knowledge/` — 事件知识图谱
- `environments/` · `skills/` — 交易环境与技能封装

### `web/` — Web 平台

基于 Streamlit 的决策驾驶舱，`pages/` 下含 Dashboard / Watchlist / Scanner 三个页面，另含 `api/` FastAPI 服务。

### `bin/` — 快捷脚本

常用操作的入口脚本：`advisor.py`、`backtest.py`、`analyze_portfolio.py`、`screen_etfs.py`、`system_check.py` 等。

### `scripts/` — 运维与研究脚本

`run_web.sh`（Web 平台管理）、`run_api.sh`（FastAPI 服务）、`refresh_factors.py`（因子刷新）、`long_rotation_discovery.py`、`live_advisor.py` 等。

### `config/` — 配置文件

`config.yaml`（主配置）、`portfolios.yaml`（组合）、`screens.yaml`（筛选篮子）、`ranking_profiles.yaml`（排名权重）、`rotation_universe.yaml`、`etf_categories.yaml`、`industry_taxonomy.yaml`、`regime_*`（市场状态）、`strategies/`（策略配置）、`candidates/`（候选标的）等。

### `docs/` — 文档

- `README.md` — 文档导航入口
- `ARCHITECTURE.md` · `DIRECTORY_STRUCTURE.md` — 架构与目录
- `usage/` — 使用文档（英文：quick_start / guides / configuration）
- `design/` — 设计文档（中文）
- `incidents/` — 故障复盘记录

### `tests/` — 测试

按类型分层：`unit/`（单元）、`integration/`（集成）、`web/`（端到端 Playwright）。统一入口 `tests/run_tests.sh`。

### 数据与产物目录

- `data/` · `cache/` — 市场数据与 API 缓存，不进版本控制
- `logs/` · `log/` — 运行日志
- `reports/` — 生成的分析报告（按类型 / 日期归档）
- `experiments/` — 策略研究实验记录
- `baks/` — 阶段性 / 归档文档，按 AGENTS.md 约定逐步淘汰

## 开发约定

- **新功能模块** → `quant/` 对应分层子目录
- **快捷脚本** → `bin/`；**运维 / 研究脚本** → `scripts/`
- **配置文件** → `config/`
- **稳定文档** → `docs/`；**阶段性文档** → `baks/`
- 避免在根目录创建临时文件

---

**最后更新**: 2026-05-21
