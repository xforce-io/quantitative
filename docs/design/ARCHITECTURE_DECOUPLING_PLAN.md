# 系统前后端解耦与智能体技能化架构设计

## 1. 背景与问题描述 (Background & Problem Statement)

目前量化交易系统的架构中，业务逻辑层（Backend）与展现层（Frontend/TUI）存在严重的耦合。

* **业务逻辑掺杂格式化输出**：在诸如 `etf_screener.py`、`peg_valuation_analyzer.py` 等分析器内部，大量核心计算函数不仅返回分析数据，还同时调用了 `print()` 打印结果或处理终端格式化字符串（带有颜色的终端输出等）。
* **CLI 层定位模糊**：目前的 `quant/cli/` 以及 `bin/` 脚本，不仅充当了命令行的入口角色，还在里面杂糅了大量的业务流水线控制、甚至是部分格式化报告的拼接工作。
* **智能体兼容性差**：系统正在向“智能体增强（Agentic）”发展。大部分智能体的应用场景需要的是“工具（Skills）”。大模型调用的 Tools 需要返回纯粹的结构化数据（JSON / dict / Pydantic对象），而非混杂着转义控制符的终端字符串。这使得现有包含 `print` 逻辑和紧耦合格式的系统难以将其作为技能直接外露给大语言模型（LLM）。

**熵减诉求 (Entropy Reduction)**：需彻底消除数据分析核心层的副作用（如终端渲染），将控制权与展现权移交，使分析器成为**纯净的数据处理管道**。

---

## 2. 目标架构设计 (Target Architecture)

重构的核心是将原有的庞杂入口彻底划分为清晰独立的三层互操作结构：**`tui` \ `web` \ `skills`**。

### 2.1 整体目录树映射

```text
quant_trading/
├── quant/
│   ├── core/           # 核心领域模型（指标计算、数据抓取、特征器等）
│   ├── analysis/       # 纯净的分析逻辑引擎（移除所有 print() 控制流）
│   ├── skills/         # 🌟 [新增] 面向智能体的标准能力接口层
│   └── ...
├── tui/                # 🌟 [新增] 命令行与终端可视化界面 (Terminal UI)
├── web/                # 网页可视化界面 (Streamlit/FastAPI, 现存)
└── bin/                # 逐渐弱化为轻量快捷启停脚本，不再放置逻辑代码
```

### 2.2 核心角色职责详解

#### 1. `quant/skills/` (智能体能力层 / Facade层)
- **定位**：无副作用、高度一致的业务操作外观模式（Facade）集合。
- **职责**：
  - 包装并聚合 `core/` 和 `analysis/` 的底层细粒度实现。
  - **接口契约明确**：提供符合 OpenAI / MCP Tool Call 标准的入参签名和函数文档（Docstring）。
  - **返回值受限**：只能返回纯洁的结构化数据字典结构、DataFrame、或 Pydantic 模型，绝对不允许存在任何的标准输出（STDOUT `print`） 或控制流拦截。
  - **核心地位**：除了作为 Agent 的唯一 Tool 调用入口，也是 `tui/` 和 `web/` 的统一后端 API 层。

#### 2. `tui/` (Terminal User Interface 层)
- **定位**：高颜值的命令行交互系统。
- **职责**：
  - 接管老架构中的 `quant/cli/` 与大部分 `bin/` 脚本的入口。
  - 借助 `argparse` / `Typer` / `Click` 来收集用户意图。
  - 请求 `skills/` 接口拿到 JSON 数据后，结合如 `rich` 等终端库，渲染出具备进度条、动态高亮、格式化表格的专业 TUI 界面。

#### 3. `web/` (Web User Interface 层)
- **定位**：供人类沉浸式探索与操作的仪表盘界面（目前居于 Streamlit）。
- **职责**：
  - 采集用户的表单与点击交互。
  - 请求 `skills/` 接口获取纯净数据集。
  - 利用 Python 图表库（Plotly, Echarts）将冷冰冰的数据转化为可直观交互的市场全景看板。

---

## 3. 实施迁移计划 (Migration Strategy)

由于代码库庞大，重构需要按模块**渐进式**推进，保证中间状态时刻处于可运行与可测试状态。

### 阶段 1 (Phase 1) - 核心逻辑“去副作用化”
- 盘点 `quant/analysis/` 下所有存在的 `*.print_*` 等展现方法（如 `etf_screener.py` 中的控制台打印）。
- 将格式化输出的逻辑直接提取或删除，必须强制让底层的 `analyze_xxx` 方法将一切该知道的信息作为属性写入返回的字典或实体类中。

### 阶段 2 (Phase 2) - `skills` 标准接口定义
- 新建 `quant/skills/` 目录。
- 开始提供标准技能，如：`skill_screen_etfs()`, `skill_analyze_stock_valuation()`, `skill_generate_portfolio_report()` 等。
- 确保调用者能在一行代码里，拿到完整的特征结构结果。

### 阶段 3 (Phase 3) - `tui` 的新建与 `cli` 的淘汰
- 在根目录建立 `tui/` 文件夹（或者在 `quant/tui` 下统辖应用）。
- 利用现代化的终端库重写以往由 `print` 拼接的报表逻辑。
- 将功能对齐后，更新 `AGENTS.md` 和 `README.md` 的可用命令提示，随后清理冗余老旧的 `bin/*_analyzer.py` 和 `quant/cli/` 的遗留代码。

### 阶段 4 (Phase 4) - `web` 层与 `agents` 层的适配
- `web/` 页面直接导入并开始调用 `skills` 方法，完成与 `tui` 等对齐的最新底层实现。
- `quant/agents` 原本自行封装的 tool 调用逻辑，顺滑接入到统一、高可用并专门为 LLMs 定制的 `skills` API 中。

---

## 3.5 实施进度 (Progress)

> 最后更新: 2026-03-22T16:52

| 阶段 | 模块 | 状态 | 说明 |
|------|------|------|------|
| Phase 2 | `quant/skills/__init__.py` | ✅ Done | 骨架与导出 (11 个 API) |
| Phase 2 | `quant/skills/etf_screening.py` | ✅ Done | 5 个无副作用 API：`screen_etfs`, `screen_symbols`, `analyze_etf`, `get_screening_config`, `list_etf_pools` |
| Phase 2 | `quant/skills/stock_analysis.py` | ✅ Done | 6 个无副作用 API：`fetch_full_analysis`, `get_stock_money_flow`, `get_stock_technical_data`, `get_stock_valuation`, `get_trend_strength`, `resolve_symbol` |
| Phase 1 | `quant/analysis/screener/etf_screener.py` | ✅ Done | `print_screening_results` 标记 deprecated，委托到 `tui.etf`；`main()` 也使用 TUI 层 |
| Phase 3 | `tui/` | ✅ Done | `tui/__init__.py` + `tui/formatters.py`(Rich 工具集) + `tui/etf.py`(ETF 筛选结果渲染) |
| Phase 4 | `web/data_service.py` 适配 | ✅ Done | `fetch_stock_full_analysis` → 薄委托 `quant.skills.fetch_full_analysis` (减 ~70 行) |
| Phase 4 | `web/skillkits` 适配 | ✅ Done | `PageDataSkillkit.fetch_stock_analysis` 直接调用 `quant.skills`，不再经过 `web.data_service` |

---

## 4. 预期收益 (Expected Value)

1. **显著降低耦合熵增**：后端只需专心吐出准确数据，前端自由决定是在 Web 画图还是在 Terminal 制表。任何一方的修改绝不会再影响到另一方。
2. **AI Native**：专门设立的 `skills/` 层是智能体的天然温床。它使得编写大模型工具或者接入标准 MCP 框架变得极其轻量，不再需要为系统原有难以剥离的副作用而头痛。
3. **接口契约明晰**：提升代码可测试性，对 `skills/` API 可以通过简单的 JSON mock 来分别对接口、TUI 及 Web 侧撰写单元和集成测试。
