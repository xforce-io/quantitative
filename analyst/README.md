# 📊 Analyst: Investment Analysis Toolkit

Analyst 提供面向投研与交易模拟的一整套分析工具，包括单标的深度分析、组合权重聚合、策略回测比较、筛选与报告生成。本目录基于 `quant` 包实现，可脚本化执行或作为模块使用。

重要更新（组合与选股篮子分离）
- Portfolio 与 Screen 明确分离：
  - Portfolio（组合）用于执行与回测，包含目标权重、再平衡策略与指数→ETF 代理。
  - Screen（选股篮子）用于分类与候选清单，不含权重，可一键生成组合权重（等权/逆波动等）。
- 配置外置至 `config/`：
  - `config/portfolios.yaml`：组合与元数据（含推荐权重）+ 指数代理映射。
  - `config/screens.yaml`：选股篮子与元数据。
  - 支持 YAML/JSON 与 `${ENV}` 环境变量展开；不存在时回退到内置默认。

## 🚀 Core Tools

### 🎯 Investment Advisors

| Tool | Description | Key Features |
| --- | --- | --- |
| `advisor.py` | 统一投资顾问，整合 `SmartAdvisor` 与 `InvestmentAdvisor` | 单标的、组合（含权重聚合）、从 Screen 动态生成组合、批量与综合分析 |
| `smart_advisor.py` | 智能顾问，平衡风险与收益视角 | 历史位置、风险评估、概率分析、基本面分析、**资金流向分析** |
| `investment_advisor.py` | 传统顾问，多策略回测与 CANSLIM | 多周期回测、实时信号、组合策略优化 |
| `capital_flow_analyzer.py` | 资金流向专业分析器 | 主力资金、北向资金、板块资金流向、机构关注度分析 |

### 🔬 Specialized Analysis

| Tool | Description | Key Features |
| --- | --- | --- |
| `strategy_correlation_analyzer.py` | 策略相关性分析 | 历史回测、相关矩阵、组合策略相关性洞察 |
| `multi_strategy_comparator.py` | 多策略对比 | MA/动量/网格等策略的绩效对比 |
| `parameter_sensitivity_analyzer.py` | 参数敏感性 | 单参数/二维参数扫、交互影响分析 |
| `strategy_performance_analyzer.py` | 策略表现分析 | 高收益策略、类型表现、参数影响 |
| `short_term_momentum_analyzer.py` | 短线动量 | 周期收益、连涨连跌、量能扩张、突破信号 |
| `peak_analyzer.py` | 高位风险 | O'Neil 分布/停滞日、背离、过度延伸、假突破 |
| `capital_flow_analyzer.py` | **资金流向深度分析** | **主力资金/大单趋势/机构关注度/北向资金/板块资金流向** |

### 🔍 Screeners

| Tool | Description | Key Features |
| --- | --- | --- |
| `company_screener.py` | 基于 CANSLIM 的股票筛选 | 可配置规则、严格与增强模式、行业适配 |
| `etf_momentum_screener.py` | ETF 动量筛选 | ETF 分类、质量指标、单一 ETF 深度分析 |
| `screening_analyzer.py` | 筛选结果分析 | 质量分、行业/区域分析、Top Picks |

## 🧩 Concepts

- Portfolio（组合）
  - 定义：可执行的权重配置与再平衡策略；组合级绩效聚合与风控的最小单元。
  - 位置：`analyst/portfolios.py`（管理器），配置优先从 `config/portfolios.yaml` 加载。
  - 当前内置组合：`DEFAULT`（你的个人配置，保持不变），含 `recommended_weights` 用于聚合展示。

- Screen（选股篮子）
  - 定义：候选清单（不含权重），可按方法（等权/逆波动）即时生成组合权重。
  - 位置：`analyst/screens.py`（管理器），配置优先从 `config/screens.yaml` 加载。

- 指数→ETF 代理
  - 映射：在分析层允许指数（如 `IXIC/HSI`），执行层统一映射为可交易 ETF（如 `513100.SH/159920.SZ`）。
  - 配置：`config/portfolios.yaml` 的 `index_proxy_map`；也支持独立文件 `config/index_proxies.yaml|json`。

## ⚙️ Configuration

- `config/portfolios.yaml`
  - `portfolios.DEFAULT`：符号清单与元数据（含 `recommended_weights`）
  - `portfolio_meta.DEFAULT`：描述/风险/风格/再平衡/类型
  - `index_proxy_map`：指数→ETF 映射

- `config/screens.yaml`
  - `screens.{NAME}`：篮子成员清单
  - `screens_meta.{NAME}`：描述/风险/风格/更新频率

两者均支持 JSON 与 `${ENV}` 展开。未配置时回退使用代码内置默认。

严格配置模式
- 通过环境变量 `STRICT_CONFIG=true` 启用严格模式（默认即严格）。在严格模式下：
  - 未加载到任何组合或篮子、元数据缺失、类型不匹配、推荐权重不归一等都会报错中止。
  - 可用 `python analyst/check_config.py` 进行一次性健康检查。

## 💰 Capital Flow Analysis (New!)

Advisor工具现已整合资金流向分析能力，为A股投资决策提供更强大的支持：

### 核心功能

**1. 个股资金流向分析**
- 主力净流入比例分析 - 识别主力资金动向
- 大单趋势分析 - 追踪大资金流向趋势
- 资金流向一致性 - 评估各类资金流向的协调性
- 机构关注度评估 - 基于大单活跃度判断机构参与度

**2. 北向资金关注度分析**
- HSGT Top10出现频率分析
- 北向资金整体流向趋势
- 相对偏好程度评估

**3. 板块资金流向分析** 
- 板块整体资金流向统计
- 个股贡献度排序
- 板块资金流向一致性评估
- 热点强度评分

**4. 风险评估整合**
- 资金流向风险权重15%（新增维度）
- 主力流入降低风险评分，主力流出提高风险评分
- 机构关注度调整风险系数

### 智能特性

- **自动检测**：仅对A股启用资金流分析（.SH/.SZ结尾）
- **缓存优化**：避免重复API调用，提升分析效率
- **容错处理**：资金流数据缺失时自动回退到技术分析
- **综合评分**：40%主力资金 + 25%大单趋势 + 20%一致性 + 15%机构关注度

### 分析示例

```bash
# 启用资金流分析的单标的分析（默认启用）
python analyst/smart_advisor.py --symbol 002594.SZ
python analyst/advisor.py --mode single --symbol 002049.SZ

# 使用统一顾问进行综合分析（包含资金流）
python analyst/advisor.py --mode comprehensive --symbol 588000.SH

# 独立资金流分析测试
python analyst/capital_flow_analyzer.py
```

### 输出示例

分析报告中新增资金流向部分：
```
💰 资金流向分析
  主力净流入比例: 3.2%
  大单趋势: bullish
  机构关注度: medium  
  综合评分: 68/100
  ✨ 机会信号: 连续3日主力资金净流入
```

## 🖥️ CLI Usage

- 单标的分析
  - `python analyst/smart_advisor.py --symbol 000300.SH`
  - `python analyst/advisor.py --mode single --symbol 002049.SZ`

- 组合分析（权重聚合）
  - 使用内置组合：`python analyst/advisor.py --mode portfolio --portfolio DEFAULT`
  - 使用选股篮子等权：`python analyst/advisor.py --mode portfolio --screen SEMICONDUCTOR --weight-method equal`
  - 使用选股篮子逆波动：`python analyst/advisor.py --mode portfolio --screen BANK --weight-method inv_vol`

- 批量/综合/全组合分析
  - `python analyst/advisor.py --mode batch --symbols-file semiconductor_stocks.txt`
  - `python analyst/advisor.py --mode comprehensive --symbol 002049.SZ --periods 3Y,5Y`
  - `python analyst/advisor.py --mode all-portfolios --save all_portfolios_report.json`

## 🐍 Python API

- PortfolioManager
  - `from analyst.portfolios import portfolio_manager`
  - `portfolio_manager.get_portfolio('DEFAULT')`
  - `portfolio_manager.get_weights('DEFAULT')  # 推荐或自定义权重`
  - `portfolio_manager.set_weights('DEFAULT', {...})  # 设置自定义权重`
  - `portfolio_manager.apply_index_proxy('IXIC')  # → 513100.SH`
  - `portfolio_manager.build_weights(['600036.SH','512820.SH'], method='inv_vol')`

- ScreenManager
  - `from analyst.screens import screen_manager`
  - `screen_manager.list_screens()`、`screen_manager.get_symbols('BANK')`
  - `screen_manager.build_weights('SEMICONDUCTOR', method='equal')`
  - `screen_manager.get_trade_symbols('GLOBAL', use_proxy=True)`

- CapitalFlowAnalyzer (新增)
  - `from analyst.capital_flow_analyzer import CapitalFlowAnalyzer`
  - `analyzer = CapitalFlowAnalyzer(); analyzer.analyze_stock_money_flow('002594.SZ')`
  - `analyzer.analyze_northbound_flow('000300.SH', days=60)`
  - `analyzer.analyze_sector_flow(['002594.SZ', '002049.SZ'], days=20)`

- UnifiedAdvisor (资金流整合)
  - `from analyst.advisor import UnifiedAdvisor`
  - `advisor = UnifiedAdvisor(); advisor.analyze_single('002594.SZ')  # 自动包含资金流分析`
  - `advisor.analyze_comprehensive('588000.SH')  # 综合分析+资金流`

## ✅ Quick Tests

- `python test_portfolios.py`：展示可用组合/推荐权重、代理映射与保存/加载
- `python test_screens.py`：展示篮子、构建等权/逆波动权重与代理后的交易符号

## 📈 Suggested Workflow

- 使用 Screener 形成初选清单
- 通过 Screen 动态生成组合权重（等权/逆波动/后续可扩展平衡型）
- 使用 `advisor.py` 进行权重聚合的组合分析与报告
- **新增**: A股投资自动整合资金流向分析，提升决策准确性
- （可选）把权重接入多周期回测，输出组合级绩效与再平衡建议

## 🔮 Roadmap

- 组合级回测聚合：年化/回撤/夏普、交易成本/滑点、再平衡偏离阈值
- Screen 规则化（criteria/ranking）与 CI 校验（指数未代理、行业归属、数据缺口）
- 更丰富的权重生成器（风险预算/目标暴露/最小方差）
- **资金流分析增强** (已完成): 支持更多市场数据源、机构资金追踪、资金流预测模型
