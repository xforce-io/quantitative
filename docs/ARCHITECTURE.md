# 系统架构文档 (ARCHITECTURE)

> 本文档描述量化交易系统当前的分层架构与核心数据流程。
>
> 系统版本 v2.2.0。架构重构已完成，本文档反映**当前实际结构**。

---

## 📋 目录

1. [架构总览](#架构总览)
2. [分层职责](#分层职责)
3. [各层详解](#各层详解)
4. [核心数据流程](#核心数据流程)
5. [模块依赖规则](#模块依赖规则)

---

## 架构总览

系统采用 8 层分层架构，上层依赖下层，禁止反向依赖：

```
Layer 8  bin/ + quant/cli/   入口层    命令行入口、快捷脚本
Layer 7  quant/agents/       代理层    智能体协调（可选）
Layer 6  quant/engines/      执行引擎  回测、优化
Layer 5  quant/strategies/   策略层    传统一体化策略
Layer 4  quant/risk/         风控层    仓位限制、VaR、回撤监控
Layer 3  quant/portfolio/    组合层    组合构建、再平衡
Layer 2  quant/analysis/     分析层    估值、技术面、Alpha、轮动、事件推演
Layer 1  quant/data/         数据层    数据获取、缓存、因子存储
Layer 0  quant/core/         基础设施  配置、日志、异常、指标、工具
```

此外：

- `quant/services/` — 服务层，封装跨层业务流程供 CLI / Web 复用
- `quant/knowledge/` — 事件知识图谱（因果边、事件分类、行业资产映射）
- `web/` — Streamlit Web 平台，跨层调用 services 与 analysis

---

## 分层职责

| 层级 | 名称 | 职责 | 依赖 |
|------|------|------|------|
| Layer 0 | Core | 配置、日志、异常、技术指标、绩效指标、工具 | 无 |
| Layer 1 | Data | 数据获取、缓存、标准化、因子存储 | L0 |
| Layer 2 | Analysis | 因子计算、估值、技术面、Alpha 信号、轮动、事件推演 | L0–1 |
| Layer 3 | Portfolio | 组合构建、权重优化、再平衡 | L0–2 |
| Layer 4 | Risk | 仓位限制、VaR、回撤监控 | L0–3 |
| Layer 5 | Strategies | 传统一体化交易策略 | L0–2 |
| Layer 6 | Engines | 回测执行、策略优化 | L0–5 |
| Layer 7 | Agents | 多策略协调（可选） | 所有层 |
| Layer 8 | Entry | CLI、快捷脚本 | 所有层 |

设计原则：单一职责、分层清晰（禁止反向依赖）、入口与逻辑分离、Fail Fast。

---

## 各层详解

### Layer 0 — Core (`quant/core/`)

基础设施层，无外部依赖。

- `config.py` / `config_manager.py` / `simple_config.py` — 配置管理
- `logging_config.py` — 日志配置
- `exceptions.py` — 异常定义
- `indicators.py` — 技术指标计算
- `metrics.py` — 绩效指标计算
- `data_manager.py` / `data_validator.py` — 数据管理与校验
- `symbol_resolver.py` — 标的代码解析
- `report_generator.py` / `enhanced_report_generator.py` — 报告生成

### Layer 1 — Data (`quant/data/`)

统一数据层，采用 Strategy + Factory + Decorator 模式。

- `base_provider.py` — 数据提供者抽象基类
- `provider_factory.py` — `create_data_provider()` 工厂函数
- `providers.py` — `DataProvider` 统一入口
- `cache_manager.py` — 缓存管理
- `db.py` — 本地数据库存储
- `factor_store.py` — 因子数据查询接口
- `implementations/` — 具体实现（`tushare_provider.py`、`yahoo_provider.py`）
- `fetchers/` — 专项数据抓取（ETF 份额、宏观 PMI、估值、代理扩展）

> 注：`quant/data_providers/` 为旧版数据层实现，仍保留供历史代码引用；新代码统一使用 `quant/data/`。

### Layer 2 — Analysis (`quant/analysis/`)

分析层，按功能域组织：

- `valuation/` — 估值分析（价格分位、基本面、PEG、回归、系统性低估）
- `technical/` — 技术分析
- `fundamental/` — 基本面分析
- `indicators/` — 指标分析（含资金流向）
- `alpha/` — Alpha 模型（动量、均值回归，输出 `Insight`）
- `screener/` — 多因子筛选与排名
- `rotation/` — 行业 ETF 轮动（多因子排名器）
- `lowfreq/` — A 股月频低频策略
- `regime/` — 市场状态判别
- `position_sizing/` — 仓位测算
- `event_investment/` — 新闻事件概率推演
- `transmission/` — 因果传导分析
- `verdict/` — 综合研判
- `advisor/` — 投资顾问（`UnifiedAdvisor` 等）
- `portfolio/` — 组合分析（Sleeve 分层）
- `strategy/` — 策略对比分析

### Layer 3 — Portfolio (`quant/portfolio/`)

组合构建层，将 Alpha 信号转化为目标仓位。

- `base_constructor.py` — 组合构建器抽象基类
- `equal_weight.py` — 等权重构建
- `risk_parity.py` — 风险平价构建
- `rebalancer.py` — 再平衡逻辑
- `portfolio_analyzer.py` — 组合分析

### Layer 4 — Risk (`quant/risk/`)

风控层，对目标仓位做约束检查与调整。

- `base_risk_model.py` — 风控模型抽象基类
- `position_limits.py` — 仓位限制
- `var_calculator.py` — VaR 计算
- `drawdown_monitor.py` — 回撤监控
- `composite_risk.py` — 组合风控

### Layer 5 — Strategies (`quant/strategies/`)

传统一体化策略，一个类内完成信号生成 + 仓位决策。注册于 `STRATEGY_REGISTRY`：

`ma_crossover`、`momentum`、`grid`（别名 `unified_grid`）、`seykota_ma`、`dca`、`pyramid_dca`、`hold`。

此外还有 `adaptive_grid`、`mean_reversion`、`etf_rotation` 等策略实现。

### Layer 6 — Engines (`quant/engines/`)

执行引擎层。

- `backtest_engine.py` — 回测引擎（支持一体化策略）
- `algorithm_engine.py` — 组件化算法引擎（Alpha → Portfolio → Risk）
- `backtest_executor.py` / `backtest_analyzer.py` / `backtest_validator.py` — 执行、分析、校验
- `strategy_optimizer.py` — 策略参数优化

### Layer 7 — Agents (`quant/agents/`)

可选的智能体协调层（`agent_manager.py`、`strategy_agent.py`）。

### Layer 8 — Entry (`bin/` + `quant/cli/`)

入口层，仅做参数解析与路由，核心逻辑均在 `quant/` 内。`quant/__main__.py` 注册 9 个 CLI 模块（见 [README](../README.md)）。

---

## 核心数据流程

### 回测流程

```
CLI 参数 → 加载配置 → DataProvider 取行情(经缓存) → 计算技术指标
        → 实例化 Strategy → BacktestEngine 逐 bar 执行
        → BacktestAnalyzer 分析 → JSON / Markdown 报告
```

### 组件化算法流程（AlgorithmEngine）

```
逐 bar:
  Alpha 层    生成 Insight 信号（方向 / 强度 / 置信度）
  Portfolio 层 construct() 构建目标仓位
  Risk 层     check() 风控调整仓位
  执行层      rebalancer 计算订单并执行
```

### 估值分析流程

```
标的 → valuation/ 多维度评分（价格分位 / 基本面 / PEG / 回归）
    → 综合评分加权 → 低估/合理/高估判断 → 价值陷阱检测 → 报告
```

### 组合分析流程

```
config/portfolios.yaml → 解析 Sleeve / 持仓 / 目标收益
    → 逐持仓取价、算收益、估值、检查配置偏离
    → Sleeve 分析 + 估值汇总 + 再平衡建议
```

---

## 模块依赖规则

```
              core  data  analysis  portfolio  risk  strategies  engines
core           -     ✗       ✗          ✗        ✗       ✗          ✗
data           ✓     -       ✗          ✗        ✗       ✗          ✗
analysis       ✓     ✓       -          ✗        ✗       ✗          ✗
portfolio      ✓     ✓       ✓          -        ✗       ✗          ✗
risk           ✓     ✓       ✓          ✓        -       ✗          ✗
strategies     ✓     ✓       ✓          ✗        ✗       -          ✗
engines        ✓     ✓       ✓          ✓        ✓       ✓          -

✓ 允许依赖   ✗ 禁止依赖（反向 / 跨界）
```

- `strategies` 不依赖 `portfolio` / `risk`，保持一体化策略的独立性。
- `engines` 协调一体化策略与组件化算法，可依赖所有下层。
- 新增模块须遵循该依赖方向；引入新依赖模式时需说明收益与迁移策略。

---

**最后更新**: 2026-05-21
