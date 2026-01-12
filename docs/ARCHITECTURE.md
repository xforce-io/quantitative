# 系统架构文档 (ARCHITECTURE)

> 本文档描述量化交易系统的分层架构设计、核心流程以及重构计划。

---

## 📋 目录

1. [当前架构问题分析](#当前架构问题分析)
   - [数据层重复问题详解](#数据层重复问题详解)
2. [目标架构设计](#目标架构设计)
3. [分层架构详解](#分层架构详解)
   - [数据层统一方案](#数据层统一方案-layer-1)
   - [组合层设计](#组合层设计-layer-3-新增)
   - [风控层设计](#风控层设计-layer-4-新增)
4. [核心数据流程](#核心数据流程)
5. [现有工具兼容性设计](#现有工具兼容性设计)
6. [模块依赖关系](#模块依赖关系)
7. [重构迁移计划](#重构迁移计划)

---

## 🔍 当前架构问题分析

### 现状结构图

```
quantitative_trading/
├── bin/                           # ❌ 混合了脚本入口和业务逻辑
│   ├── regression_analyzer.py     #    → 应该是 quant/analysis/valuation/
│   ├── momentum_analyzer.py       #    → 应该是 quant/analysis/technical/
│   ├── advisor.py                 #    → 与 quant/cli/advisor.py 重复
│   └── screen_etfs.py             #    → 核心逻辑应在 quant/ 中
│
├── quant/
│   ├── config/                    # ❌ 与 core/config.py 功能重叠
│   │
│   ├── analysis/
│   │   ├── etf_valuation_analyzer.py      # ❌ 应该在 valuation/ 子目录
│   │   ├── etf_fundamental_analyzer.py    # ❌ 应该在 valuation/ 子目录
│   │   └── screener/
│   │       └── peg_valuation_analyzer.py  # ❌ 估值分析不应在 screener 下
│   │
│   └── company_analysis/          # ❌ 与 analysis/ 功能重复
│       └── stock_analyzer.py
```

### 核心问题

| 问题 | 影响 | 严重度 |
|------|------|--------|
| **估值分析分散** | 相似功能散落在 3+ 个位置，难以复用和维护 | 🔴 高 |
| **bin/ 承载业务逻辑** | 核心分析类在 bin/ 中，无法被其他模块 import | 🔴 高 |
| **数据层重复实现** | `data/` 和 `data_providers/` 两套数据层并存 | 🔴 高 |
| **职责边界模糊** | screener/ 同时做筛选和估值，company_analysis/ 与 analysis/ 重复 | 🟡 中 |
| **配置管理分散** | config/ 目录和 core/config.py 功能重叠 | 🟡 中 |
| **ETF vs 个股混杂** | 缺乏统一的资产抽象，每种资产类型独立实现 | 🟡 中 |

### 数据层重复问题详解

当前存在两套数据层实现：

```
┌──────────────────────────────────┐    ┌──────────────────────────────────┐
│   quant/data/ (新架构)           │    │   quant/data_providers/ (旧架构) │
├──────────────────────────────────┤    ├──────────────────────────────────┤
│                                  │    │                                  │
│   providers.py                   │    │   base_data_provider.py          │
│   └── class DataProvider         │    │   └── class BaseDataProvider     │
│       ├── _fetch_tushare_data()  │    │       (抽象基类)                  │
│       ├── _fetch_yahoo_data()    │    │                                  │
│       └── 内置缓存逻辑            │    │   data_provider.py               │
│                                  │    │   └── class TushareDataProvider  │
│   一个类包含所有逻辑              │    │                                  │
│   (Monolithic 单体设计)          │    │   yahoo_data_provider.py         │
│                                  │    │   └── class YahooDataProvider    │
│                                  │    │                                  │
│                                  │    │   data_provider_factory.py       │
│                                  │    │   └── class DataProviderFactory  │
│                                  │    │                                  │
│                                  │    │   策略模式 + 工厂模式             │
│                                  │    │   (Strategy + Factory Pattern)   │
└──────────────────────────────────┘    └──────────────────────────────────┘
```

**问题**:
- 两处都实现了 tushare/yahoo 调用逻辑（代码重复）
- 命名风格不一致：`get_stock_data()` vs `getStockData()`
- 新旧代码混用，维护成本高
- 修复 bug 需要改两个地方

---

## 🎯 目标架构设计

### 设计原则

1. **单一职责**: 每个模块只做一件事
2. **分层清晰**: 上层依赖下层，禁止反向依赖
3. **入口与逻辑分离**: bin/ 和 cli/ 只做入口，核心逻辑在 quant/ 中
4. **按功能域组织**: 而非按资产类型组织
5. **Fail Fast**: 错误快速暴露，避免无休止的 fallback

### 目标结构图

```
quantitative_trading/
│
├── bin/                           # 🟢 命令行入口 (仅入口)
│   ├── regression.py              #    → 调用 quant.analysis.valuation
│   ├── momentum.py                #    → 调用 quant.analysis.technical
│   ├── advisor.py                 #    → 调用 quant.analysis.advisor
│   └── screen.py                  #    → 调用 quant.analysis.screener
│
├── cli/                           # 🟢 Typer CLI 入口
│   └── main.py
│
├── config/                        # 🟢 配置文件 (YAML/JSON)
│   ├── config.yaml
│   ├── portfolios.yaml
│   └── screens.yaml
│
└── quant/                         # 🟢 核心业务逻辑
    │
    ├── core/                      # Layer 0: 基础设施层
    │   ├── config.py              #   配置管理
    │   ├── logging_config.py      #   日志配置
    │   ├── exceptions.py          #   异常定义
    │   ├── utils.py               #   通用工具
    │   ├── indicators.py          #   技术指标计算
    │   └── metrics.py             #   绩效指标计算
    │
    ├── data/                      # Layer 1: 数据层 (统一)
    │   ├── __init__.py            #   模块入口
    │   ├── base_provider.py       #   抽象基类 (Strategy Pattern)
    │   ├── provider_factory.py    #   工厂函数 (Factory Pattern)
    │   ├── cache_manager.py       #   缓存管理
    │   └── implementations/       #   具体提供者实现
    │       ├── __init__.py
    │       ├── tushare_provider.py
    │       └── yahoo_provider.py
    │
    │   # ❌ 废弃: data_providers/ → 迁移到 data/implementations/
    │
    ├── analysis/                  # Layer 2: 分析层 (重构重点)
    │   │
    │   ├── valuation/             # 📍 估值分析 (统一)
    │   │   ├── __init__.py
    │   │   ├── price_valuation.py         # 价格分位数估值
    │   │   ├── fundamental_valuation.py   # 基本面估值 (PE/PB/ROE)
    │   │   ├── peg_valuation.py           # PEG 估值
    │   │   ├── regression_analyzer.py     # 回归拟合分析
    │   │   └── systemic_undervalue.py     # 🆕 系统性低估判断
    │   │
    │   ├── technical/             # 📍 技术分析
    │   │   ├── __init__.py
    │   │   ├── momentum_analyzer.py       # 动量分析
    │   │   ├── trend_analyzer.py          # 趋势分析
    │   │   └── relative_strength.py       # 相对强弱
    │   │
    │   ├── fundamental/           # 📍 基本面分析
    │   │   ├── __init__.py
    │   │   ├── financial_analyzer.py      # 财务分析
    │   │   └── industry_analyzer.py       # 行业分析
    │   │
    │   ├── screener/              # 📍 筛选器 (纯筛选逻辑)
    │   │   ├── __init__.py
    │   │   ├── etf_screener.py
    │   │   ├── stock_screener.py
    │   │   └── industry_classifier.py
    │   │
    │   ├── alpha/                 # 🆕 Alpha模型 (信号生成)
    │   │   ├── __init__.py
    │   │   ├── base_alpha.py              # Alpha基类
    │   │   ├── momentum_alpha.py          # 动量Alpha
    │   │   ├── mean_reversion_alpha.py    # 均值回归Alpha
    │   │   └── multi_factor_alpha.py      # 多因子Alpha
    │   │
    │   ├── advisor/               # 📍 投资顾问
    │   │   ├── __init__.py
    │   │   ├── investment_advisor.py
    │   │   └── unified_advisor.py
    │   │
    │   └── strategy/              # 📍 策略分析
    │       ├── __init__.py
    │       ├── strategy_comparator.py
    │       └── performance_analyzer.py
    │
    ├── portfolio/                 # 🆕 Layer 3: 组合层 (新增)
    │   ├── __init__.py
    │   ├── base_constructor.py            # 组合构建基类
    │   ├── mean_variance.py               # 均值方差优化
    │   ├── risk_parity.py                 # 风险平价
    │   ├── rebalancer.py                  # 再平衡逻辑
    │   └── portfolio_analyzer.py          # 投资组合分析 (从 analysis/ 迁移)
    │
    ├── risk/                      # 🆕 Layer 4: 风控层 (新增)
    │   ├── __init__.py
    │   ├── base_risk_model.py             # 风控模型基类
    │   ├── position_limits.py             # 仓位限制
    │   ├── var_calculator.py              # VaR计算
    │   └── drawdown_monitor.py            # 回撤监控
    │
    ├── strategies/                # Layer 5: 策略层 (✅ 完全保留)
    │   ├── base_strategy.py
    │   ├── unified_grid_strategy.py
    │   ├── dca_strategy.py
    │   ├── momentum_strategy.py
    │   ├── mean_reversion_strategy.py
    │   └── ...其他策略
    │
    ├── engines/                   # Layer 6: 执行引擎层
    │   ├── backtest_engine.py             # ✅ 保留 (支持全功能策略)
    │   ├── algorithm_engine.py            # 🆕 新增 (支持组件化策略)
    │   ├── backtest_executor.py
    │   └── strategy_optimizer.py
    │
    └── agents/                    # Layer 7: 代理层 (可选)
        ├── agent_manager.py
        └── strategy_agent.py
```

---

## 📚 分层架构详解

### 架构分层图 (行业标准4层架构)

> **设计说明**: 参考 QuantConnect LEAN、Zipline 等顶级量化框架，将原有的"策略层"拆分为
> **Alpha/Analysis → Portfolio → Risk → Execution** 四个独立层，实现单一职责和可插拔设计。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Layer 8: 入口层 (Entry)                          │
│                      bin/ | cli/ | notebooks/                           │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                   │
│   │ regression  │   │   advisor   │   │   screen    │                   │
│   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘                   │
└──────────┼─────────────────┼─────────────────┼──────────────────────────┘
           │                 │                 │
           ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Layer 7: 代理层 (Agents)                           │
│                      (可选 - 用于复杂策略协调)                            │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                      AgentManager                               │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Layer 6: 执行引擎层 (Engines)                      │
│                                                                         │
│   ┌──────────────────────────────┐  ┌──────────────────────────────┐    │
│   │ BacktestEngine (保留)        │  │ AlgorithmEngine (🆕 新增)    │    │
│   │ 支持全功能策略               │  │ 支持组件化策略                │    │
│   │                              │  │                              │    │
│   │ engine.run(strategy)         │  │ engine.run(algorithm)        │    │
│   │   ↳ 策略自己决定买卖         │  │   ↳ Alpha→Portfolio→Risk    │    │
│   └──────────────────────────────┘  └──────────────────────────────┘    │
│                                                                         │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                   │
│   │  Executor   │   │  Validator  │   │  Optimizer  │                   │
│   └─────────────┘   └─────────────┘   └─────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                 Layer 5: 策略层 (Strategies) ✅ 完全保留                 │
│                                                                         │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│   │    Grid    │  │    DCA     │  │  Momentum  │  │ MeanRevert │        │
│   │  Strategy  │  │  Strategy  │  │  Strategy  │  │  Strategy  │        │
│   └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘        │
│         │               │               │               │               │
│         └───────────────┴───────────────┴───────────────┘               │
│                                │                                         │
│                     ┌──────────┴──────────┐                              │
│                     │    BaseStrategy     │  ← 全功能策略 (现有模式)      │
│                     └─────────────────────┘                              │
│                                                                         │
│   说明: 现有策略完全保留，不需要任何修改                                   │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Layer 4: 风控层 (Risk) 🆕                          │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                      BaseRiskModel (抽象基类)                    │   │
│   │  + check_position(symbol, weight) -> adjusted_weight            │   │
│   │  + check_portfolio(positions) -> adjusted_positions             │   │
│   │  + get_risk_metrics() -> Dict                                   │   │
│   └───────────────────────────┬─────────────────────────────────────┘   │
│                               │                                         │
│         ┌─────────────────────┼─────────────────────────────────────┐   │
│         ▼                     ▼                     ▼               ▼   │
│   ┌───────────┐         ┌───────────┐         ┌───────────┐  ┌──────────┐
│   │ Position  │         │    VaR    │         │ Drawdown  │  │ Sector   │
│   │  Limits   │         │Calculator │         │  Monitor  │  │ Exposure │
│   │           │         │           │         │           │  │          │
│   │ max 10%   │         │ 95% VaR   │         │ max 20%   │  │ max 30%  │
│   │ per pos   │         │           │         │ drawdown  │  │ per sect │
│   └───────────┘         └───────────┘         └───────────┘  └──────────┘
│                                                                         │
│   输入: target_positions = {symbol: weight}                             │
│   输出: adjusted_positions (风控调整后的仓位)                            │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Layer 3: 组合层 (Portfolio) 🆕                     │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              BasePortfolioConstructor (抽象基类)                 │   │
│   │  + construct(insights) -> target_positions                      │   │
│   │  + rebalance(current, target, threshold) -> orders              │   │
│   └───────────────────────────┬─────────────────────────────────────┘   │
│                               │                                         │
│         ┌─────────────────────┼─────────────────────────────────────┐   │
│         ▼                     ▼                     ▼               ▼   │
│   ┌───────────┐         ┌───────────┐         ┌───────────┐  ┌──────────┐
│   │   Mean    │         │   Risk    │         │  Equal    │  │ Portfolio│
│   │ Variance  │         │  Parity   │         │  Weight   │  │ Analyzer │
│   │           │         │           │         │           │  │          │
│   │ 均值方差  │         │ 风险平价  │         │ 等权重    │  │ 分析工具 │
│   └───────────┘         └───────────┘         └───────────┘  └──────────┘
│                                                                         │
│   输入: List[Insight] (来自Alpha层)                                      │
│   输出: target_positions = {symbol: weight}                             │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Layer 2: 分析/Alpha层 (Analysis)                   │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │  valuation/  │  │  technical/  │  │ fundamental/ │  │  screener/  │  │
│  │              │  │              │  │              │  │             │  │
│  │ - price      │  │ - momentum   │  │ - financial  │  │ - etf       │  │
│  │ - peg        │  │ - trend      │  │ - industry   │  │ - stock     │  │
│  │ - regression │  │ - rs         │  │              │  │ - classify  │  │
│  │ - undervalue │  │              │  │              │  │             │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘  │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐   │
│  │   advisor/   │  │  strategy/   │  │       alpha/ (🆕)            │   │
│  │              │  │              │  │                              │   │
│  │ - investment │  │ - comparator │  │ - base_alpha.py              │   │
│  │ - unified    │  │ - performance│  │ - momentum_alpha.py          │   │
│  │              │  │              │  │ - mean_reversion_alpha.py    │   │
│  │              │  │              │  │ - multi_factor_alpha.py      │   │
│  └──────────────┘  └──────────────┘  └──────────────────────────────┘   │
│                                                                         │
│   输出: Insight = {symbol, direction, magnitude, confidence}            │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Layer 1: 数据层 (Data)                             │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              create_data_provider() 工厂函数                     │   │
│   └───────────────────────────┬─────────────────────────────────────┘   │
│                               │                                         │
│                               ▼                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                  BaseDataProvider (抽象基类)                     │   │
│   │  + get_stock_data(symbol, start, end, freq) -> DataFrame        │   │
│   │  + get_index_data(...)                                          │   │
│   │  + get_financial_data(...)                                      │   │
│   └───────────────────────────┬─────────────────────────────────────┘   │
│                               │                                         │
│         ┌─────────────────────┼─────────────────────────────────────┐   │
│         ▼                     ▼                     ▼               │   │
│   ┌───────────┐         ┌───────────┐         ┌───────────┐         │   │
│   │  Tushare  │         │   Yahoo   │         │   Cache   │         │   │
│   │  Provider │         │  Provider │         │  Manager  │         │   │
│   │ (A-share) │         │ (Global)  │         │ (Wrapper) │         │   │
│   └───────────┘         └───────────┘         └───────────┘         │   │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Layer 0: 基础设施层 (Core)                         │
│                                                                         │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│   │ Config  │  │ Logging │  │ Errors  │  │  Utils  │  │ Metrics │       │
│   └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘       │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    TechnicalIndicators                          │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3层 vs 4层对比

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    原设计 (3层) vs 新设计 (4层)                          │
└─────────────────────────────────────────────────────────────────────────┘

原 3 层设计 (策略层职责过重):
═══════════════════════════════════════

   分析层                    策略层                    执行层
   ───────                   ───────                   ───────
   
   ┌──────────┐             ┌──────────┐             ┌──────────┐
   │ 估值分析  │────────────►│ 策略生成  │────────────►│ 回测执行  │
   │ 技术分析  │   信号      │ ❌同时负责: │   订单      │ 撮合     │
   │ 基本面   │             │ • 信号生成  │             │          │
   │          │             │ • 仓位决策  │             │          │
   │          │             │ • 风险控制  │             │          │
   └──────────┘             └──────────┘             └──────────┘


新 4 层设计 (单一职责):
═══════════════════════════════════════

   Alpha层              组合层               风控层              执行层
   ──────              ──────               ──────              ──────
   
┌──────────┐        ┌──────────┐        ┌──────────┐        ┌──────────┐
│ Analysis │───────►│ Portfolio│───────►│   Risk   │───────►│ Execution│
│  /Alpha  │Insight │ Construct│ Target │  Model   │ Checked│  Engine  │
│          │        │          │Position│          │Position│          │
│ 信号生成  │        │ 仓位配置  │        │ 风险检查  │        │ 订单执行  │
└──────────┘        └──────────┘        └──────────┘        └──────────┘
```

### 各层职责定义

| 层级 | 名称 | 职责 | 输入 → 输出 | 依赖 |
|------|------|------|------------|------|
| **Layer 0** | Core | 基础工具、配置、日志、异常、指标计算 | - | 无外部依赖 |
| **Layer 1** | Data | 数据获取、缓存、标准化 | symbol → DataFrame | Layer 0 |
| **Layer 2** | Analysis/Alpha | 因子计算、信号生成、估值分析 | DataFrame → Insight | Layer 0, 1 |
| **Layer 3** | Portfolio 🆕 | 组合构建、权重优化、再平衡 | Insight → Positions | Layer 0, 1, 2 |
| **Layer 4** | Risk 🆕 | 仓位限制、VaR检查、回撤监控 | Positions → Checked Positions | Layer 0, 1, 2, 3 |
| **Layer 5** | Strategies | 交易策略实现 (全功能策略，保留) | DataFrame → Orders | Layer 0, 1, 2 |
| **Layer 6** | Engines | 回测执行、订单撮合、优化 | Strategy/Algorithm → Result | Layer 0~5 |
| **Layer 7** | Agents | 策略协调、多策略管理 | - | All layers |
| **Layer 8** | Entry | 命令行入口、脚本 | - | All layers |

#### Insight 数据结构 (Alpha层输出)

```python
@dataclass
class Insight:
    """Alpha模型产生的交易洞察"""
    symbol: str           # 股票代码
    direction: int        # 方向: 1=多, -1=空, 0=平
    magnitude: float      # 信号强度: 0.0 ~ 1.0
    confidence: float     # 置信度: 0.0 ~ 1.0
    period: timedelta     # 预期持有周期
    source: str           # 来源Alpha模型名称
    generated_at: datetime
```

### 数据层统一方案 (Layer 1)

#### 目标结构

```
quant/data/                        # 统一数据层
├── __init__.py                    # 模块入口，导出公共接口
│   from .provider_factory import create_data_provider
│   from .base_provider import BaseDataProvider
│
├── base_provider.py               # 抽象基类
│   class BaseDataProvider(ABC):
│       @abstractmethod
│       def get_stock_data(...) -> pd.DataFrame
│       @abstractmethod
│       def get_index_data(...) -> pd.DataFrame
│       def add_technical_indicators(...)  # 通用方法
│
├── provider_factory.py            # 工厂函数
│   def create_data_provider(provider: str, config: dict) -> BaseDataProvider
│
├── cache_manager.py               # 缓存管理
│   class CacheManager:
│       def get(key) -> Optional[DataFrame]
│       def set(key, data, ttl_hours)
│       def invalidate(pattern)
│
└── implementations/               # 具体提供者实现
    ├── __init__.py
    ├── tushare_provider.py        # Tushare 实现 (A股)
    │   class TushareDataProvider(BaseDataProvider)
    ├── yahoo_provider.py          # Yahoo 实现 (全球)
    │   class YahooDataProvider(BaseDataProvider)
    └── cached_provider.py         # 缓存装饰器
        class CachedDataProvider(BaseDataProvider)  # Decorator Pattern
```

#### 设计模式

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         数据层设计模式                                   │
└─────────────────────────────────────────────────────────────────────────┘

1. Strategy Pattern (策略模式)
   ─────────────────────────────
   
   ┌─────────────────────┐
   │  BaseDataProvider   │ ◄─── 抽象接口
   │  (Abstract Class)   │
   └──────────┬──────────┘
              │
    ┌─────────┼─────────┐
    │         │         │
    ▼         ▼         ▼
┌────────┐ ┌────────┐ ┌────────┐
│Tushare │ │ Yahoo  │ │ Mock   │  ◄─── 具体策略
│Provider│ │Provider│ │Provider│
└────────┘ └────────┘ └────────┘


2. Factory Pattern (工厂模式)
   ─────────────────────────────
   
   create_data_provider('tushare', config)
           │
           ▼
   ┌─────────────────────────────────────┐
   │  if provider == 'tushare':          │
   │      return TushareDataProvider()   │
   │  elif provider == 'yahoo':          │
   │      return YahooDataProvider()     │
   │  elif provider == 'auto':           │
   │      return _select_best_provider() │
   └─────────────────────────────────────┘


3. Decorator Pattern (装饰器模式 - 缓存)
   ─────────────────────────────────────
   
   ┌────────────────────────────────────────────────────────────────┐
   │  CachedDataProvider                                            │
   │  ┌──────────────────────────────────────────────────────────┐  │
   │  │  inner: BaseDataProvider  (被装饰的提供者)                │  │
   │  └──────────────────────────────────────────────────────────┘  │
   │                                                                │
   │  def get_stock_data(self, ...):                               │
   │      cache_key = self._build_key(...)                         │
   │      if cached := self.cache.get(cache_key):                  │
   │          return cached  # 缓存命中                             │
   │      data = self.inner.get_stock_data(...)  # 调用内层        │
   │      self.cache.set(cache_key, data)                          │
   │      return data                                               │
   └────────────────────────────────────────────────────────────────┘
```

#### 统一接口规范

```python
class BaseDataProvider(ABC):
    """数据提供者抽象基类"""
    
    @abstractmethod
    def get_stock_data(
        self,
        symbol: str,           # 股票代码: '000001.SZ', '600036.SH'
        start_date: str,       # 开始日期: 'YYYYMMDD' 或 'YYYY-MM-DD'
        end_date: str,         # 结束日期
        freq: str = 'D'        # 频率: 'D'(日), 'W'(周), 'M'(月)
    ) -> pd.DataFrame:
        """
        获取股票行情数据
        
        Returns:
            DataFrame with columns: [open, high, low, close, volume]
            Index: DatetimeIndex
        """
        pass
    
    @abstractmethod
    def get_index_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        freq: str = 'D'
    ) -> pd.DataFrame:
        """获取指数数据"""
        pass
    
    def get_financial_data(
        self,
        symbol: str,
        report_type: str = 'income'  # 'income', 'balance', 'cashflow'
    ) -> pd.DataFrame:
        """获取财务数据 (可选实现)"""
        raise NotImplementedError("Financial data not supported by this provider")
    
    def get_valuation_data(
        self,
        symbol: str,
        trade_date: str = None
    ) -> Dict:
        """获取估值数据 PE/PB/PS (可选实现)"""
        raise NotImplementedError("Valuation data not supported by this provider")
```

#### 迁移步骤

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 创建 `quant/data/implementations/` 目录 | 放置具体提供者 |
| 2 | 从 `data_providers/` 迁移实现类 | 保持向后兼容 |
| 3 | 将 `data/providers.py` 中的逻辑拆分 | 单体类 → 策略模式 |
| 4 | 在 `data_providers/__init__.py` 添加 deprecated 警告 | 引导用户迁移 |
| 5 | 更新所有调用方使用新接口 | 统一使用 `quant.data` |

#### 向后兼容

```python
# quant/data_providers/__init__.py (过渡期保留)
import warnings

def _deprecated_import():
    warnings.warn(
        "quant.data_providers is deprecated. Use quant.data instead.",
        DeprecationWarning,
        stacklevel=3
    )

# Re-export for backward compatibility
from quant.data import create_data_provider
from quant.data.implementations import TushareDataProvider, YahooDataProvider

_deprecated_import()
```

### 组合层设计 (Layer 3 🆕)

组合层负责将 Alpha 信号转化为具体的仓位配置，实现组合优化和再平衡逻辑。

#### 目标结构

```
quant/portfolio/                   # 组合层
├── __init__.py                    # 模块入口
│   from .base_constructor import BasePortfolioConstructor
│   from .mean_variance import MeanVarianceConstructor
│   from .risk_parity import RiskParityConstructor
│
├── base_constructor.py            # 抽象基类
│   class BasePortfolioConstructor(ABC):
│       @abstractmethod
│       def construct(insights: List[Insight]) -> Dict[str, float]
│       @abstractmethod
│       def rebalance(current, target, threshold) -> List[Order]
│
├── mean_variance.py               # 均值方差优化
│   class MeanVarianceConstructor(BasePortfolioConstructor)
│
├── risk_parity.py                 # 风险平价
│   class RiskParityConstructor(BasePortfolioConstructor)
│
├── equal_weight.py                # 等权重
│   class EqualWeightConstructor(BasePortfolioConstructor)
│
├── rebalancer.py                  # 再平衡逻辑
│   class Rebalancer:
│       def calculate_trades(current, target, threshold)
│
└── portfolio_analyzer.py          # 投资组合分析 (从 analysis/ 迁移)
    class PortfolioAnalyzer
```

#### 核心接口

```python
class BasePortfolioConstructor(ABC):
    """组合构建器抽象基类"""
    
    @abstractmethod
    def construct(
        self,
        insights: List[Insight],
        current_positions: Dict[str, float] = None
    ) -> Dict[str, float]:
        """
        根据 Alpha 信号构建目标组合
        
        Args:
            insights: Alpha模型产生的信号列表
            current_positions: 当前持仓 {symbol: weight}
            
        Returns:
            目标持仓 {symbol: target_weight}
        """
        pass
    
    def rebalance(
        self,
        current: Dict[str, float],
        target: Dict[str, float],
        threshold: float = 0.05
    ) -> List[Order]:
        """
        计算再平衡订单
        
        Args:
            current: 当前持仓权重
            target: 目标持仓权重
            threshold: 偏离阈值，低于此值不调整
            
        Returns:
            需要执行的订单列表
        """
        orders = []
        all_symbols = set(current.keys()) | set(target.keys())
        
        for symbol in all_symbols:
            curr_weight = current.get(symbol, 0.0)
            tgt_weight = target.get(symbol, 0.0)
            diff = tgt_weight - curr_weight
            
            if abs(diff) >= threshold:
                orders.append(Order(
                    symbol=symbol,
                    direction='BUY' if diff > 0 else 'SELL',
                    weight_change=abs(diff)
                ))
        
        return orders
```

### 风控层设计 (Layer 4 🆕)

风控层对组合层输出的目标仓位进行约束检查和调整，确保符合风险管理要求。

#### 目标结构

```
quant/risk/                        # 风控层
├── __init__.py                    # 模块入口
│   from .base_risk_model import BaseRiskModel
│   from .position_limits import PositionLimits
│   from .var_calculator import VaRCalculator
│
├── base_risk_model.py             # 抽象基类
│   class BaseRiskModel(ABC):
│       @abstractmethod
│       def check(positions) -> AdjustedPositions
│
├── position_limits.py             # 仓位限制
│   class PositionLimits(BaseRiskModel):
│       - max_single_position: float = 0.10  # 单仓位上限 10%
│       - max_sector_exposure: float = 0.30  # 行业敞口上限 30%
│       - max_total_exposure: float = 1.00   # 总敞口上限 100%
│
├── var_calculator.py              # VaR计算
│   class VaRCalculator(BaseRiskModel):
│       - var_confidence: float = 0.95       # VaR置信度
│       - var_limit: float = 0.05            # 日VaR上限 5%
│
├── drawdown_monitor.py            # 回撤监控
│   class DrawdownMonitor(BaseRiskModel):
│       - max_drawdown: float = 0.20         # 最大回撤 20%
│       - drawdown_action: str = 'reduce'    # 触发动作
│
└── composite_risk.py              # 组合风控
    class CompositeRiskModel(BaseRiskModel):
        # 组合多个风控模型
```

#### 核心接口

```python
class BaseRiskModel(ABC):
    """风控模型抽象基类"""
    
    @abstractmethod
    def check(
        self,
        positions: Dict[str, float],
        market_data: pd.DataFrame = None
    ) -> RiskCheckResult:
        """
        检查仓位是否符合风控要求
        
        Args:
            positions: 目标仓位 {symbol: weight}
            market_data: 市场数据 (用于计算风险指标)
            
        Returns:
            RiskCheckResult:
                - passed: bool
                - adjusted_positions: Dict[str, float]
                - violations: List[str]
                - risk_metrics: Dict
        """
        pass


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    passed: bool                           # 是否通过检查
    adjusted_positions: Dict[str, float]   # 调整后的仓位
    violations: List[str]                  # 违反的规则列表
    risk_metrics: Dict                     # 风险指标


class PositionLimits(BaseRiskModel):
    """仓位限制风控"""
    
    def __init__(
        self,
        max_single_position: float = 0.10,
        max_sector_exposure: float = 0.30,
        max_total_exposure: float = 1.00
    ):
        self.max_single_position = max_single_position
        self.max_sector_exposure = max_sector_exposure
        self.max_total_exposure = max_total_exposure
    
    def check(self, positions: Dict[str, float], **kwargs) -> RiskCheckResult:
        violations = []
        adjusted = positions.copy()
        
        # 检查单仓位限制
        for symbol, weight in positions.items():
            if weight > self.max_single_position:
                violations.append(
                    f"{symbol}: {weight:.1%} exceeds limit {self.max_single_position:.1%}"
                )
                adjusted[symbol] = self.max_single_position
        
        # 检查总敞口
        total = sum(adjusted.values())
        if total > self.max_total_exposure:
            violations.append(f"Total exposure {total:.1%} exceeds limit")
            # 等比例缩放
            scale = self.max_total_exposure / total
            adjusted = {k: v * scale for k, v in adjusted.items()}
        
        return RiskCheckResult(
            passed=len(violations) == 0,
            adjusted_positions=adjusted,
            violations=violations,
            risk_metrics={'total_exposure': sum(adjusted.values())}
        )
```

---

## 🔄 核心数据流程

### 1. 回测流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           回测执行流程                                   │
└─────────────────────────────────────────────────────────────────────────┘

  User Input                    System Processing                   Output
  ──────────                    ─────────────────                   ──────

┌──────────┐
│ CLI/API  │
│ 参数输入  │
│ - symbol │
│ - dates  │
│ - config │
└────┬─────┘
     │
     ▼
┌────────────────┐
│  ConfigManager │──────────────────────────────────────────┐
│  加载配置       │                                          │
└────────┬───────┘                                          │
         │                                                  │
         ▼                                                  │
┌────────────────┐      ┌────────────────┐                  │
│  DataProvider  │◄─────│   CacheManager │                  │
│  获取行情数据   │      │   查询/更新缓存 │                  │
└────────┬───────┘      └────────────────┘                  │
         │                                                  │
         │  price_data: DataFrame                           │
         ▼                                                  │
┌────────────────┐                                          │
│ TechnicalIndi- │                                          │
│ cators.add()   │                                          │
│ 计算技术指标    │                                          │
└────────┬───────┘                                          │
         │                                                  │
         │  data_with_indicators: DataFrame                 │
         ▼                                                  ▼
┌────────────────┐      ┌────────────────┐      ┌────────────────┐
│   Strategy     │◄─────│ StrategyConfig │◄─────│    Config      │
│   实例化策略    │      │   策略参数      │      │    YAML        │
└────────┬───────┘      └────────────────┘      └────────────────┘
         │
         │  strategy: BaseStrategy
         ▼
┌────────────────┐
│ BacktestEngine │
│ 执行回测        │
│                │
│ for each bar:  │
│   1. update    │
│      market    │
│      state     │
│   2. strategy  │
│      .decide() │
│   3. execute   │
│      trades    │
│   4. update    │
│      portfolio │
└────────┬───────┘
         │
         │  BacktestResult
         ▼
┌────────────────┐      ┌────────────────┐
│ BacktestAnaly- │─────►│    Report      │
│ zer 分析结果    │      │  JSON/MD/PNG   │
└────────────────┘      └────────────────┘
```

### 2. 估值分析流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        估值分析流程 (Valuation)                          │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────┐
│  Input   │
│ - symbol │
│ - period │
└────┬─────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         SystemicUndervalueAnalyzer                      │
└─────────────────────────────────────────────────────────────────────────┘
     │
     ├──────────────────────┬──────────────────────┬──────────────────────┐
     ▼                      ▼                      ▼                      ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐      ┌───────────────┐
│   Price      │      │ Fundamental  │      │     PEG      │      │  Regression   │
│  Valuation   │      │  Valuation   │      │  Valuation   │      │   Analyzer    │
│              │      │              │      │              │      │               │
│ • percentile │      │ • PE/PB/PS   │      │ • PEG ratio  │      │ • linear fit  │
│ • z-score    │      │ • ROE/ROA    │      │ • growth est │      │ • deviation   │
│ • mean rever │      │ • margins    │      │ • industry   │      │ • trend       │
└──────┬───────┘      └──────┬───────┘      └──────┬───────┘      └───────┬───────┘
       │                     │                     │                      │
       │ score: -3~+3        │ score: -3~+3        │ score: -3~+3         │ score: -3~+3
       │                     │                     │                      │
       └─────────────────────┴─────────────────────┴──────────────────────┘
                                       │
                                       ▼
                          ┌────────────────────────┐
                          │   Composite Scoring    │
                          │   综合评分加权          │
                          │                        │
                          │   score = Σ(w_i × s_i) │
                          │                        │
                          │   confidence =         │
                          │     agreement_ratio    │
                          └───────────┬────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │  Undervalue Judgment   │
                          │                        │
                          │  if score < -6 and     │
                          │     confidence > 70%:  │
                          │    → 系统性严重低估     │
                          │                        │
                          │  elif score < -3:      │
                          │    → 低估               │
                          │                        │
                          │  else:                 │
                          │    → 合理/高估          │
                          └───────────┬────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │   Value Trap Check     │
                          │   价值陷阱检测          │
                          │                        │
                          │  • revenue_trend < 0   │
                          │  • margin_declining    │
                          │  • high_debt           │
                          │  • cyclical_peak       │
                          └───────────┬────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │      Final Report      │
                          │                        │
                          │  {                     │
                          │    is_undervalued: T/F │
                          │    confidence: 0-100%  │
                          │    composite_score:    │
                          │    signals: [...]      │
                          │    warnings: [...]     │
                          │    recommendation: ... │
                          │  }                     │
                          └────────────────────────┘
```

### 3. 投资组合分析流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      投资组合分析流程 (Portfolio)                        │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────┐
│ portfolios.  │
│    yaml      │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ PortfolioConfig  │
│ - sleeves[]      │
│ - holdings[]     │
│ - target_return  │
└────────┬─────────┘
         │
         ├─────────────────────────────────────────────────────────────┐
         │                                                             │
         ▼                                                             ▼
┌────────────────────────┐                                 ┌─────────────────────┐
│   For each holding:    │                                 │ Portfolio Metrics   │
│                        │                                 │                     │
│   1. Fetch price data  │                                 │ • total_value       │
│   2. Calculate return  │                                 │ • weighted_return   │
│   3. Run valuation     │                                 │ • risk_assessment   │
│   4. Check allocation  │                                 │ • rebalance_needed  │
└────────────┬───────────┘                                 └──────────┬──────────┘
             │                                                        │
             │  holdings_analysis[]                                   │
             │                                                        │
             ▼                                                        ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           Portfolio Report                               │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Sleeve Analysis                                                     │ │
│  │  • ETF: 40% → return: +5.2% → valuation: 合理                       │ │
│  │  • Stock: 30% → return: +12.1% → valuation: 偏高                    │ │
│  │  • Bond: 30% → return: +2.1% → valuation: 低估                      │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Valuation Summary                                                   │ │
│  │  🟢 低估: 510500.SH, 159915.SZ                                       │ │
│  │  🟡 合理: 510300.SH                                                  │ │
│  │  🔴 高估: 512480.SH                                                  │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Recommendations                                                     │ │
│  │  • 减持: 512480.SH (高估警告)                                        │ │
│  │  • 加仓: 510500.SH (低估机会)                                        │ │
│  │  • 再平衡: ETF配置超标 5%                                            │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4. 组件化策略回测流程 (🆕 新增)

```
┌─────────────────────────────────────────────────────────────────────────┐
│               组件化策略回测流程 (AlgorithmEngine)                       │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                          Algorithm 定义                                  │
│  algorithm = Algorithm(                                                  │
│      alpha_models=[MomentumAlpha(), MeanReversionAlpha()],              │
│      portfolio_model=RiskParityConstructor(),                           │
│      risk_model=PositionLimits(max_single=0.1)                          │
│  )                                                                       │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     AlgorithmEngine.run() 主循环                         │
│                                                                          │
│  for each bar in data:                                                   │
│      │                                                                   │
│      ▼                                                                   │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ Step 1: Alpha Layer (生成信号)                                     │  │
│  │                                                                    │  │
│  │   insights = []                                                    │  │
│  │   for alpha_model in algorithm.alpha_models:                       │  │
│  │       insights += alpha_model.generate_insights(data)              │  │
│  │                                                                    │  │
│  │   Output: List[Insight] with direction, magnitude, confidence      │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│      │                                                                   │
│      ▼                                                                   │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ Step 2: Portfolio Layer (构建组合)                                 │  │
│  │                                                                    │  │
│  │   target_positions = algorithm.portfolio_model.construct(          │  │
│  │       insights=insights,                                           │  │
│  │       current_positions=current_holdings                           │  │
│  │   )                                                                │  │
│  │                                                                    │  │
│  │   Output: Dict[symbol, target_weight]                              │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│      │                                                                   │
│      ▼                                                                   │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ Step 3: Risk Layer (风险检查)                                      │  │
│  │                                                                    │  │
│  │   risk_result = algorithm.risk_model.check(                        │  │
│  │       positions=target_positions,                                  │  │
│  │       market_data=data                                             │  │
│  │   )                                                                │  │
│  │   adjusted_positions = risk_result.adjusted_positions              │  │
│  │                                                                    │  │
│  │   Output: Dict[symbol, adjusted_weight] + violations               │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│      │                                                                   │
│      ▼                                                                   │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ Step 4: Execution (执行订单)                                       │  │
│  │                                                                    │  │
│  │   orders = self.rebalancer.calculate_orders(                       │  │
│  │       current=current_holdings,                                    │  │
│  │       target=adjusted_positions                                    │  │
│  │   )                                                                │  │
│  │   for order in orders:                                             │  │
│  │       self.executor.execute(order)                                 │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 现有工具兼容性设计

> **设计原则**: 现有的 10+ 个策略和回测引擎**完全保留**，不需要任何修改。
> 新增的组合层和风控层是**可选的高级功能**，采用渐进式迁移方式。

### 两种策略模式并存

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        策略层兼容设计                                    │
└─────────────────────────────────────────────────────────────────────────┘

方案1: 全功能策略 (现有模式，✅ 完全保留)
═══════════════════════════════════════════

   ┌─────────────────────────────────────────────────────────────────────┐
   │  UnifiedGridStrategy / DCAStrategy / MomentumStrategy               │
   │                                                                     │
   │  一个类包含所有逻辑:                                                  │
   │  • 信号生成 (什么时候买卖)                                            │
   │  • 仓位决策 (买卖多少)                                               │
   │  • 执行逻辑 (如何下单)                                               │
   │                                                                     │
   │  适用场景: 简单策略、快速开发、回测                                    │
   └─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    BacktestEngine.run(strategy)  ← 现有引擎


方案2: 组件化策略 (🆕 新模式，推荐复杂场景)
═══════════════════════════════════════════

   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
   │ Alpha Model  │───►│  Portfolio   │───►│ Risk Model   │
   │ (信号生成)    │    │ Constructor  │    │ (风险过滤)    │
   └──────────────┘    └──────────────┘    └──────────────┘
                              │
                              ▼
                    AlgorithmEngine.run(algorithm)  ← 🆕 新引擎
   
   适用场景: 多因子策略、组合策略、机构级应用
```

### 代码示例

```python
# ═══════════════════════════════════════════════════════════════════════
# 方案1: 现有策略直接使用 (完全兼容，不需要任何修改)
# ═══════════════════════════════════════════════════════════════════════

from quant.strategies import UnifiedGridStrategy
from quant.engines import BacktestEngine

strategy = UnifiedGridStrategy(symbol='000001.SZ', config={...})
engine = BacktestEngine(data_provider)
result = engine.run(strategy, start_date, end_date)  # ✅ 照常工作


# ═══════════════════════════════════════════════════════════════════════
# 方案2: 组件化策略 (🆕 新模式)
# ═══════════════════════════════════════════════════════════════════════

from quant.analysis.alpha import MomentumAlpha, MeanReversionAlpha
from quant.portfolio import RiskParityConstructor
from quant.risk import PositionLimits, VaRCalculator
from quant.engines import AlgorithmEngine, Algorithm  # 🆕

# 组装组件
algorithm = Algorithm(
    alpha_models=[
        MomentumAlpha(lookback=20, weight=0.6),
        MeanReversionAlpha(threshold=2.0, weight=0.4),
    ],
    portfolio_model=RiskParityConstructor(
        rebalance_threshold=0.05
    ),
    risk_model=PositionLimits(
        max_single_position=0.10,
        max_sector_exposure=0.30
    ),
)

engine = AlgorithmEngine(data_provider)
result = engine.run(algorithm, start_date, end_date)
```

### 现有工具映射表

| 现有工具 | 位置 | 处理方式 | 新位置 |
|---------|------|---------|--------|
| **策略类** ||||
| `unified_grid_strategy.py` | `strategies/` | ✅ 完全保留 | 不动 |
| `dca_strategy.py` | `strategies/` | ✅ 完全保留 | 不动 |
| `momentum_strategy.py` | `strategies/` | ✅ 完全保留 | 不动 |
| `mean_reversion_strategy.py` | `strategies/` | ✅ 完全保留 | 不动 |
| `ma_crossover_strategy.py` | `strategies/` | ✅ 完全保留 | 不动 |
| **引擎类** ||||
| `backtest_engine.py` | `engines/` | ✅ 完全保留 | 不动 |
| `backtest_executor.py` | `engines/` | ✅ 完全保留 | 不动 |
| `strategy_optimizer.py` | `engines/` | ✅ 完全保留 | 不动 |
| **分析类** ||||
| `etf_valuation_analyzer.py` | `analysis/` | 🔄 迁移 | `analysis/valuation/` |
| `etf_fundamental_analyzer.py` | `analysis/` | 🔄 迁移 | `analysis/valuation/` |
| `peg_valuation_analyzer.py` | `analysis/screener/` | 🔄 迁移 | `analysis/valuation/` |
| `regression_analyzer.py` | `bin/` | 🔄 提取核心类 | `analysis/valuation/` |
| `momentum_analyzer.py` | `bin/` | 🔄 提取核心类 | `analysis/technical/` |
| `portfolio_analyzer.py` | `analysis/portfolio/` | 🔄 迁移 | `portfolio/` |
| **新增** ||||
| `algorithm_engine.py` | - | 🆕 新增 | `engines/` |
| `base_alpha.py` | - | 🆕 新增 | `analysis/alpha/` |
| `base_constructor.py` | - | 🆕 新增 | `portfolio/` |
| `base_risk_model.py` | - | 🆕 新增 | `risk/` |

### 兼容性保证

1. **现有策略不受影响**: `strategies/` 目录下的所有策略类保持原样
2. **现有引擎不受影响**: `BacktestEngine` 继续支持全功能策略
3. **渐进式新增**: 新的 `portfolio/` 和 `risk/` 层是增量添加
4. **向后兼容导入**: 旧的导入路径继续工作，添加 deprecation 警告

```python
# 向后兼容示例
# quant/analysis/portfolio/__init__.py
import warnings

def _deprecated_import():
    warnings.warn(
        "quant.analysis.portfolio is deprecated. Use quant.portfolio instead.",
        DeprecationWarning,
        stacklevel=3
    )

# Re-export for backward compatibility
from quant.portfolio import PortfolioAnalyzer
_deprecated_import()
```

---

## 🔗 模块依赖关系

### 依赖矩阵 (更新为8层)

```
                       依赖方向 →
         ┌────────────────────────────────────────────────────────────────┐
         │  core  data  analysis  portfolio  risk  strategies  engines   │
    ─────┼────────────────────────────────────────────────────────────────┤
    core │   -     ✗       ✗          ✗        ✗       ✗          ✗      │
    data │   ✓     -       ✗          ✗        ✗       ✗          ✗      │
analysis │   ✓     ✓       -          ✗        ✗       ✗          ✗      │
portfolio│   ✓     ✓       ✓          -        ✗       ✗          ✗      │
    risk │   ✓     ✓       ✓          ✓        -       ✗          ✗      │
strategy │   ✓     ✓       ✓          ✗        ✗       -          ✗      │
 engines │   ✓     ✓       ✓          ✓        ✓       ✓          -      │
    ─────┴────────────────────────────────────────────────────────────────┘
    
    ✓ = 允许依赖    ✗ = 禁止依赖 (反向依赖)
    
    注: strategies 不依赖 portfolio/risk (保持全功能策略独立性)
        engines 依赖所有层 (协调全功能策略和组件化策略)
```

### Analysis 子模块依赖

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         quant/analysis/                                 │
└─────────────────────────────────────────────────────────────────────────┘

                              ┌───────────┐
                              │  advisor  │
                              └─────┬─────┘
                                    │ 聚合
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
    ┌───────────┐            ┌───────────┐            ┌───────────┐
    │ valuation │            │ technical │            │fundamental│
    └─────┬─────┘            └─────┬─────┘            └─────┬─────┘
          │                        │                        │
          │                        │                        │
          └────────────────────────┼────────────────────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │    screener     │
                          │  (uses filters) │
                          └─────────────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │   portfolio     │
                          └─────────────────┘

    ────────────────────────────────────────────────────────────────
    允许的依赖: advisor → valuation, technical, fundamental
               screener → valuation, technical
               portfolio → valuation, advisor, screener
    
    禁止的依赖: valuation ↛ advisor (反向)
               technical ↛ screener (反向)
```

---

## 📋 重构迁移计划

> **迁移原则**: 渐进式迁移，保持向后兼容，每个阶段独立可测试。

### Phase 1: 统一数据层 (Week 1)

```bash
# 创建数据层新结构
mkdir -p quant/data/implementations

# 迁移和重构
# 1. 将 data_providers/ 中的类迁移到 data/implementations/
# 2. 创建统一的 base_provider.py
# 3. 更新 provider_factory.py
```

| 源文件 | 目标文件 | 操作 |
|--------|----------|------|
| `data_providers/base_data_provider.py` | `data/base_provider.py` | 移动 + 优化 |
| `data_providers/data_provider.py` | `data/implementations/tushare_provider.py` | 提取类 |
| `data_providers/yahoo_data_provider.py` | `data/implementations/yahoo_provider.py` | 移动 |
| `data/providers.py` | 拆分到上述文件 | 拆分单体类 |
| `data_providers/cache_manager.py` | `data/cache_manager.py` | 移动 |

### Phase 2: 创建 Analysis 目录结构 (Week 2)

```bash
# 创建 analysis 子目录
mkdir -p quant/analysis/valuation
mkdir -p quant/analysis/technical
mkdir -p quant/analysis/fundamental
mkdir -p quant/analysis/alpha

# 创建 __init__.py
touch quant/analysis/valuation/__init__.py
touch quant/analysis/technical/__init__.py
touch quant/analysis/fundamental/__init__.py
touch quant/analysis/alpha/__init__.py
```

### Phase 3: 迁移估值分析模块 (Week 3)

| 源文件 | 目标文件 | 操作 |
|--------|----------|------|
| `analysis/etf_valuation_analyzer.py` | `analysis/valuation/price_valuation.py` | 移动 + 重命名 |
| `analysis/etf_fundamental_analyzer.py` | `analysis/valuation/fundamental_valuation.py` | 移动 + 重命名 |
| `analysis/screener/peg_valuation_analyzer.py` | `analysis/valuation/peg_valuation.py` | 移动 |
| `bin/regression_analyzer.py` | `analysis/valuation/regression_analyzer.py` | 提取核心类 |
| *(新建)* | `analysis/valuation/systemic_undervalue.py` | 新建 |

### Phase 4: 迁移技术分析模块 (Week 4)

| 源文件 | 目标文件 | 操作 |
|--------|----------|------|
| `bin/momentum_analyzer.py` | `analysis/technical/momentum_analyzer.py` | 提取核心类 |
| `analysis/screener/relative_strength_analyzer.py` | `analysis/technical/relative_strength.py` | 移动 |
| `analysis/indicators/technical_analyzer.py` | `analysis/technical/` | 整合 |

### Phase 5: 创建组合层 (Week 5) 🆕

```bash
# 创建组合层目录
mkdir -p quant/portfolio

# 创建核心文件
touch quant/portfolio/__init__.py
touch quant/portfolio/base_constructor.py
touch quant/portfolio/mean_variance.py
touch quant/portfolio/risk_parity.py
touch quant/portfolio/equal_weight.py
touch quant/portfolio/rebalancer.py
```

| 文件 | 操作 | 说明 |
|------|------|------|
| `portfolio/base_constructor.py` | 🆕 新建 | 组合构建抽象基类 |
| `portfolio/mean_variance.py` | 🆕 新建 | 均值方差优化实现 |
| `portfolio/risk_parity.py` | 🆕 新建 | 风险平价实现 |
| `portfolio/equal_weight.py` | 🆕 新建 | 等权重实现 |
| `portfolio/rebalancer.py` | 🆕 新建 | 再平衡逻辑 |
| `analysis/portfolio/portfolio_analyzer.py` | 迁移 | 迁移到 `portfolio/` |

### Phase 6: 创建风控层 (Week 6) 🆕

```bash
# 创建风控层目录
mkdir -p quant/risk

# 创建核心文件
touch quant/risk/__init__.py
touch quant/risk/base_risk_model.py
touch quant/risk/position_limits.py
touch quant/risk/var_calculator.py
touch quant/risk/drawdown_monitor.py
```

| 文件 | 操作 | 说明 |
|------|------|------|
| `risk/base_risk_model.py` | 🆕 新建 | 风控模型抽象基类 |
| `risk/position_limits.py` | 🆕 新建 | 仓位限制检查 |
| `risk/var_calculator.py` | 🆕 新建 | VaR 计算 |
| `risk/drawdown_monitor.py` | 🆕 新建 | 回撤监控 |
| `risk/composite_risk.py` | 🆕 新建 | 组合风控模型 |

### Phase 7: 创建 Alpha 层和新引擎 (Week 7) 🆕

```bash
# Alpha 模型
touch quant/analysis/alpha/base_alpha.py
touch quant/analysis/alpha/momentum_alpha.py
touch quant/analysis/alpha/mean_reversion_alpha.py

# 新引擎
touch quant/engines/algorithm_engine.py
```

| 文件 | 操作 | 说明 |
|------|------|------|
| `analysis/alpha/base_alpha.py` | 🆕 新建 | Alpha 模型抽象基类 |
| `analysis/alpha/momentum_alpha.py` | 🆕 新建 | 动量 Alpha |
| `analysis/alpha/mean_reversion_alpha.py` | 🆕 新建 | 均值回归 Alpha |
| `engines/algorithm_engine.py` | 🆕 新建 | 支持组件化策略的引擎 |

**Alpha 模型与现有策略的关系**:
```python
# 从现有策略提取信号生成逻辑
class MomentumAlpha(BaseAlpha):
    """提取自 momentum_strategy.py 的信号生成部分"""
    
    def generate_insights(self, data: pd.DataFrame) -> List[Insight]:
        # 复用 momentum_strategy 的计算逻辑
        # 但只返回 Insight，不包含仓位决策
        pass
```

### Phase 8: 清理和收尾 (Week 8)

| 操作 | 说明 |
|------|------|
| 删除 `quant/company_analysis/` | 功能已合并到 `analysis/` |
| 删除 `quant/config/` | 使用 `core/config.py` |
| 标记 `quant/data_providers/` deprecated | 保留 re-export，添加警告 |
| 简化 `bin/` 脚本 | 只保留入口，核心逻辑调用 `quant.analysis` |
| 更新 `__init__.py` | 导出新模块 |
| 更新测试 | 添加 portfolio/ 和 risk/ 的单元测试 |

```python
# 更新 quant/__init__.py
from .analysis import (
    PriceValuationAnalyzer,
    FundamentalValuationAnalyzer,
    PEGValuationAnalyzer,
    RegressionAnalyzer,
    SystemicUndervalueAnalyzer,
    MomentumAnalyzer,
    RelativeStrengthAnalyzer,
)
from .analysis.alpha import (
    BaseAlpha,
    MomentumAlpha,
    MeanReversionAlpha,
)
from .portfolio import (
    BasePortfolioConstructor,
    MeanVarianceConstructor,
    RiskParityConstructor,
)
from .risk import (
    BaseRiskModel,
    PositionLimits,
    VaRCalculator,
)
from .engines import (
    BacktestEngine,      # 保留 - 全功能策略
    AlgorithmEngine,     # 🆕 - 组件化策略
)
```

### 迁移原则

1. **向后兼容**: 在旧位置保留 re-export 别名，逐步废弃
2. **渐进式**: 每次只迁移一个模块，确保测试通过
3. **文档同步**: 每次迁移后更新相关文档

---

## 📊 附录: 核心类设计

### SystemicUndervalueAnalyzer (新增)

```python
class SystemicUndervalueAnalyzer:
    """
    系统性低估判断器
    
    综合多个维度判断公司是否被系统性严重低估
    """
    
    def __init__(self, data_provider: DataProvider):
        self.price_analyzer = PriceValuationAnalyzer()
        self.fundamental_analyzer = FundamentalValuationAnalyzer(data_provider)
        self.peg_analyzer = PEGValuationAnalyzer()
        self.regression_analyzer = RegressionAnalyzer()
    
    def analyze(self, symbol: str, period_days: int = 756) -> Dict:
        """
        执行系统性低估分析
        
        Returns:
            {
                'is_undervalued': bool,           # 是否低估
                'is_severely_undervalued': bool,  # 是否严重低估
                'confidence': float,              # 置信度 0-100%
                'composite_score': float,         # 综合评分 -12 ~ +12
                'dimension_scores': {
                    'price_percentile': float,    # -3 ~ +3
                    'fundamental': float,         # -3 ~ +3
                    'peg': float,                 # -3 ~ +3
                    'regression': float,          # -3 ~ +3
                },
                'quality_checks': {...},          # 基本面质量检查
                'value_trap_warnings': [...],     # 价值陷阱警告
                'signals': [...],                 # 支撑判断的信号
                'recommendation': str,            # 投资建议
            }
        """
        pass
```

---

## 📝 变更日志

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-01-01 | v2.0 | **重大更新**: 采用行业标准4层架构 (Alpha→Portfolio→Risk→Execution)，新增组合层和风控层设计，添加现有工具兼容性设计，扩展迁移计划至8个阶段 |
| 2026-01-01 | v1.1 | 新增数据层统一方案、设计模式说明、更新迁移计划 |
| 2026-01-01 | v1.0 | 初始架构设计文档 |

---

*本文档由量化交易系统团队维护，如有问题请提交 Issue。*
