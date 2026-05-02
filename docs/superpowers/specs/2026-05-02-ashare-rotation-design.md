# A 股中低频量化交易：行业 ETF 轮动系统设计

**Date**: 2026-05-02
**Branch**: refactor/ashare-lowfreq-core
**Status**: Draft, awaiting user review

---

## 1. Goal

构建一个**月频、ETF 维度的行业 / 风格轮动系统**，作为个人 A 股中低频决策工具的 alpha 主引擎，叠加一个 regime multiplier 作为风险旋钮。系统每月末输出一份"目标持仓清单"——给个人按表手动下单，不做自动化交易接入。

### 1.1 Two-layer architecture

```
B 层（alpha 引擎）：行业 ETF 截面动量排名 → 月度 top-5 等权权重向量 (sum = 1)
A 层（风险旋钮）  ：现有 LowFrequencyRegimeScorer 输出的 multiplier ∈ [0, 1]
最终持仓          ：positions = multiplier × weights，未投部分为现金
```

### 1.2 Non-goals

- **个股择时**：明确不做。个股噪声远高于 ETF 层，对个人决策工具不增收益。
- **高频 / 日内**：调仓频率最低半月，正常月度。
- **自动化下单**：本期只产出"该买 / 该卖"清单，不接券商 API。
- **多因子选股（估值 / 景气度 / 财务）**：留作后续 spec，当前 alpha 信号只用价格动量。
- **宏观驱动的风格切换（cockpit TransmissionGraph 接入）**：预留接口，本期不实现。

### 1.3 Success criteria

1. 2018-01 至今的样本外回测，**净值曲线优于沪深 300，且优于等权 universe**（后者证明 alpha 来自"选行业"而非"行业 ETF 池本身贵"）。
2. 最大回撤显著优于沪深 300（量化目标：max drawdown 不超过沪深 300 的 70%）。
3. 端到端可执行：`uv run rotation backtest --from 2018-01 --to 2026-05` 一条命令出结果，月末跑一次 `rotation latest` 直接拿到目标清单。
4. 单测 + 集成测覆盖 ranker / overlay / portfolio / backtest 四个模块。

---

## 2. System architecture

```
config/rotation_universe.yaml
        │
        ▼
RotationService.run_backtest / RotationService.latest_targets
        │
        ├──► DataService.get_price (batch over universe)
        │
        ▼
┌────────────────────────────────────────────────────────────┐
│  Pipeline                                                  │
│                                                            │
│  ┌────────────┐    ┌──────────────────┐    ┌────────────┐ │
│  │ MomentumRanker │ │  RegimeOverlay   │    │ Portfolio  │ │
│  │ (B 层)      │──▶│  (A 层)           │──▶│ Combiner   │ │
│  │ weights     │    │  multiplier       │    │ positions  │ │
│  └────────────┘    └──────────────────┘    └─────┬──────┘ │
│                                                  │        │
│                              ┌───────────────────┘        │
│                              ▼                            │
│                  ┌──────────────────────┐                 │
│                  │ RotationBacktester   │                 │
│                  │ (multi-asset 月频)    │                 │
│                  └──────────────────────┘                 │
└────────────────────────────────────────────────────────────┘
        │
        ▼
RotationBacktestResult: metrics + equity + 持仓变化
```

### 2.1 Module layout

```
quant/analysis/rotation/
├── __init__.py            # 公开 API: MomentumRanker, RegimeOverlay, PortfolioCombiner, RotationBacktester
├── ranker.py              # B 层：cross-sectional momentum ranker
├── regime_overlay.py      # A 层：包装 LowFrequencyRegimeScorer，预留 cockpit 替换接口
├── portfolio.py           # 组合器：multiplier × weights → final positions
└── backtest.py            # 多资产月频再平衡回测器

quant/services/rotation_service.py
                           # universe 加载 → DataService 批量取价 → pipeline → 输出

config/rotation_universe.yaml
                           # ETF 清单 + 类别标签 + 元数据

tests/unit/
├── test_rotation_ranker.py
├── test_rotation_overlay.py
├── test_rotation_portfolio.py
└── test_rotation_backtest.py

tests/integration/test_rotation_pipeline.py
                           # 端到端：固定 fixture → 期望持仓清单
```

### 2.2 与现有 lowfreq 的关系

- `lowfreq/regime.py::LowFrequencyRegimeScorer` 不动，`rotation/regime_overlay.py` 包一层适配。
- `lowfreq/backtest.py` 是单资产逻辑，**不复用**——cross-sectional 多资产回测差异大，强行抽象会让两边都难读。
- `lowfreq/signal_builder.py` 不复用——B 用截面排名，不需要月度 MA + 波动率目标。
- `LowFrequencyService` 保留，用于"我就想看一个指数 / 一只 ETF 怎么走"。

---

## 3. Components

### 3.1 `MomentumRanker` (B 层)

**职责**：拿到 universe 内所有 ETF 的月末价格序列，输出每个再平衡日的 top-K 权重向量。

**接口**：
```python
@dataclass(frozen=True)
class RankerConfig:
    lookback_months: int = 6         # 6-1 动量（见 §5.3 验证）
    skip_recent_months: int = 1      # 跳最近 1 个月（避开短期反转）
    top_k: int = 3
    cash_threshold: float = 0.0      # top-K 平均动量 < 此值则全切现金

class MomentumRanker:
    def __init__(self, config: RankerConfig | None = None) -> None: ...

    def rank(
        self,
        monthly_prices: pd.DataFrame,    # index: month-end dates, columns: ETF symbols
        rebalance_date: pd.Timestamp,
    ) -> dict[str, float]:
        """Return {symbol: weight} for the rebalance date.

        Sum of weights = 1.0 when momentum signals fire; returns {} when cash filter
        triggers (top-K mean momentum below cash_threshold).
        """
```

**关键行为**：
- 6-1 月动量公式：`momentum_t = price_{t-1} / price_{t-7} - 1`，跳掉最近 1 月避免短期反转。
- 数据不足（ETF 上市晚、价格序列不到 7 个月）的标的当期不参与排名——不是 NaN 兜底而是直接剔除。
- 现金过滤：top-K 的**平均**动量 < `cash_threshold` 则返回空 dict（全现金），不是 top-K 各自看是否 > 0。
- 等权：top-K 内每个 = `1/K`。

**依赖**：仅 pandas / numpy，不 import DataService（保持纯计算）。

### 3.2 `RegimeOverlay` (A 层)

**职责**：把 `LowFrequencyRegimeScorer` 的输出（per-row multiplier）暴露成单值 `[0, 1]`，给 portfolio combiner 用。预留替换接口给后续 cockpit 接入。

**接口**：
```python
class RegimeOverlay(Protocol):
    """Protocol allowing future cockpit-based overlay to drop in."""
    def multiplier_at(self, date: pd.Timestamp, context: pd.DataFrame) -> float: ...

class SimpleRegimeOverlay:
    """Wraps LowFrequencyRegimeScorer for a single-benchmark regime read.

    Uses 沪深 300 (or configurable benchmark) as the regime input series — not the
    rotation universe — because regime is a market-wide signal, not a per-ETF signal.
    """
    def __init__(self, benchmark_symbol: str = "000300.SH") -> None: ...
    def multiplier_at(self, date: pd.Timestamp, context: pd.DataFrame) -> float: ...
```

**关键行为**：
- benchmark 默认沪深 300——regime 是市场层面信号，不该用 universe 自己的横截面平均（会出现"轮动到防守行业 → multiplier 反而升高"的反向反馈）。
- `context` 参数预留：cockpit overlay 接入时需要 multi-indicator 上下文（regime detector 的多极投票 + 美元流动性置信度），简单 overlay 暂时忽略。
- 输出严格 clip 到 `[0, 1]`。

**依赖**：`quant.analysis.lowfreq.regime.LowFrequencyRegimeScorer`、DataService（取 benchmark 价格）。

### 3.3 `PortfolioCombiner`

**职责**：把 A 层的 multiplier 和 B 层的 weights 合成最终持仓。

**接口**：
```python
class PortfolioCombiner:
    def combine(
        self,
        weights: dict[str, float],   # B 层输出，sum = 1 或空 dict（现金信号）
        multiplier: float,           # A 层输出，[0, 1]
    ) -> dict[str, float]:
        """Return {symbol: final_position}, where total invested = multiplier * 1,
        cash = 1 - sum(positions). Empty input weights → all-cash regardless of multiplier.
        """
```

**关键行为**：
- B 空 dict → 全现金，**A 不会"救"它**（B 已判断没机会）。
- 否则 `final[symbol] = weights[symbol] * multiplier`。
- 不做 ETF-level rounding（持仓比例最小不限）；调仓时按金额下单近似即可。

### 3.4 `RotationBacktester`

**职责**：多资产月频再平衡回测。

**接口**：
```python
@dataclass(frozen=True)
class RotationBacktestConfig:
    transaction_cost: float = 0.002   # 0.2% 双边
    risk_free: float = 0.03

@dataclass(frozen=True)
class RotationBacktestResult:
    metrics: dict                     # total/annual return, vol, sharpe, MDD (strategy + benchmarks)
    equity_curve: pd.DataFrame        # columns: strategy, hs300, equal_weight_universe
    monthly_returns: pd.DataFrame     # columns: strategy, hs300, equal_weight, turnover
    holdings: pd.DataFrame            # 每月末实际持仓矩阵 (rebalance dates × symbols)

class RotationBacktester:
    def __init__(self, config: RotationBacktestConfig | None = None) -> None: ...

    def run(
        self,
        universe_prices: pd.DataFrame,      # daily prices, columns = universe symbols
        benchmark_prices: pd.Series,        # 沪深 300 daily
        ranker: MomentumRanker,
        overlay: RegimeOverlay,
        combiner: PortfolioCombiner,
    ) -> RotationBacktestResult: ...
```

**关键行为**：
- 月末重采样到月度收益。每月末持仓 = 上月末决策的 final positions。
- Turnover 按权重 L1 距离计算：`turnover_t = 0.5 * sum(|w_t - w_{t-1}|)`（双边、单向计 0.5 防重复扣费）。
- 交易成本：`strategy_return_t = sum(w_{t-1} * r_t) - turnover_t * tc`。
- **现金部分回报视为 0**：当 `multiplier < 1` 或现金过滤触发时，`1 - sum(positions)` 那部分对当月收益贡献为 0（不计入短期 risk-free 利息——简化模型，避免引入额外参数；risk-free 仅在 Sharpe 分母里使用）。
- 三条净值线同时跑：strategy / 沪深 300 / 等权 universe。

### 3.5 `RotationService`

**职责**：把 universe yaml + DataService + pipeline 串起来。

**接口**：
```python
@dataclass(frozen=True)
class RotationRequest:
    start: str
    end: str
    universe_path: str | None = None     # 默认 config/rotation_universe.yaml
    ranker_config: RankerConfig | None = None
    overlay_benchmark: str = "000300.SH"
    transaction_cost: float = 0.002

class RotationService:
    def __init__(self, data_service: DataService | None = None) -> None: ...

    def run_backtest(self, request: RotationRequest) -> RotationBacktestResult: ...

    def latest_targets(self, request: RotationRequest) -> dict:
        """Return {as_of, multiplier, weights, final_positions, top_5_momentum} for the
        most recent month-end ≤ today. Pure decision output — no equity curve."""
```

---

## 4. Data flow（单次月末调仓决策）

```
1. RotationService.latest_targets(request)
2. ├─ 加载 universe yaml → list[symbol, name, category]
3. ├─ DataService.get_price(batch) → 取每只 ETF 的日线（lookback ≥ 14 个月）
4. ├─ DataService.get_price(沪深 300) → 给 overlay 用
5. ├─ 月末重采样 → monthly_prices: DataFrame
6. ├─ rebalance_date = 最近一个月末
7. ├─ MomentumRanker.rank(monthly_prices, rebalance_date) → weights
8. ├─ SimpleRegimeOverlay.multiplier_at(rebalance_date, hs300_context) → multiplier
9. ├─ PortfolioCombiner.combine(weights, multiplier) → final_positions
10.└─ 输出 {as_of, multiplier, weights, final_positions, top_5_momentum 表}
```

**回测时**：步骤 6 改成"对每个月末迭代"，其他不变。

---

## 5. Configuration

### 5.1 `config/rotation_universe.yaml`

```yaml
# A 股 ETF 轮动 universe
# 格式：每条 ETF 包含交易代码、名称、类别标签
# 维护原则：流动性 > 5e8/日均成交、规模 > 5e9 总规模、剔除概念重复
schema_version: 1
updated_at: "2026-05-02"

industry_etfs:
  - { symbol: "510050.SH", name: "上证50ETF",     category: "大盘" }
  - { symbol: "512000.SH", name: "券商ETF",       category: "金融" }
  - { symbol: "512800.SH", name: "银行ETF",       category: "金融" }
  - { symbol: "512170.SH", name: "医疗ETF",       category: "医药" }
  - { symbol: "512010.SH", name: "医药ETF",       category: "医药" }
  - { symbol: "159995.SZ", name: "芯片ETF",       category: "科技" }
  - { symbol: "515050.SH", name: "5G ETF",        category: "科技" }
  - { symbol: "512720.SH", name: "计算机ETF",     category: "科技" }
  - { symbol: "159928.SZ", name: "消费ETF",       category: "消费" }
  - { symbol: "159825.SZ", name: "农业ETF",       category: "消费" }
  - { symbol: "512400.SH", name: "有色ETF",       category: "周期" }
  - { symbol: "515220.SH", name: "煤炭ETF",       category: "周期" }
  - { symbol: "515210.SH", name: "钢铁ETF",       category: "周期" }
  - { symbol: "159611.SZ", name: "电力ETF",       category: "公用事业" }
  - { symbol: "159930.SZ", name: "能源ETF",       category: "周期" }
  - { symbol: "512660.SH", name: "军工ETF",       category: "军工" }
  - { symbol: "515030.SH", name: "新能源车ETF",   category: "新能源" }
  - { symbol: "515790.SH", name: "光伏ETF",       category: "新能源" }
  - { symbol: "159870.SZ", name: "化工ETF",       category: "周期" }
  - { symbol: "512200.SH", name: "房地产ETF",     category: "金融" }

style_etfs:
  - { symbol: "510880.SH", name: "红利ETF",       category: "风格-红利" }
  - { symbol: "159949.SZ", name: "创业板50",      category: "风格-成长" }
  - { symbol: "510310.SH", name: "沪深300",       category: "风格-大盘" }
  - { symbol: "159922.SZ", name: "中证500",       category: "风格-中盘" }
```

**Universe 总数 ~24**，K=5 ≈ top 20%。该清单作为初始版本，后续运维时直接改 yaml，不改代码。

### 5.2 默认参数（已在 dataclasses 中）

| 参数 | 默认值 | 来源 |
|------|-------|------|
| `lookback_months` | 6 | 2018-2024 验证：6-1 vs 12-1 全期收益 +14pp / MDD 折半（见 §5.3）|
| `skip_recent_months` | 1 | 跳最近 1 月避免短期反转，与学界标准一致 |
| `top_k` | 3 | 2018-2024 验证：K=3 在 walk-forward 4 折中 3 折胜出（见 §5.3）|
| `cash_threshold` | 0.0 | top-K 平均动量为负则切现金 |
| `transaction_cost` | 0.002 | 0.2% 双边，A 股 ETF 实际佣金+滑点保守估计 |
| `risk_free` | 0.03 | Sharpe 计算用 |
| `overlay_benchmark` | `000300.SH` | regime 用市场层信号，不用 universe 自身 |

### 5.3 默认参数验证（2018-2024 实跑数据）

完成基础实现后用真实 Tushare 数据跑了 walk-forward + regime split + lookback sweep，结果：

**Walk-forward（3 年训练选 K，1 年 OOS）**：K=3 在 4 折训练 Sharpe 中赢 3 折；K=12-1 default 从未被选中。
**Regime split（牛/熊/震荡分段）**：每段 K=3 都最优，**不是 2024 单段过拟合**。
**Lookback sweep**：6-1 在全期总收益 +53.95% / MDD -8.87% / Sharpe 0.319，全面碾压 12-1（+39.99% / -21.64% / 0.195）。9-1 第二名但 MDD 更深。

**关键发现 — 真实 alpha 来源是 cash filter，不是 momentum selection**：
- 2018 / 2022 两段熊市 cash filter 全期空仓，避了 -29.59% 和 -21.63% 的 bench 损失（共救 ~50pp）
- 2019-21 牛市策略 +62.29% 但仍跑输 bench +64.10% 与等权 universe +59.17%
- 2024 OOS 仅 +0.83% vs bench +14.68% — 12-1 月动量在 2024 是反指标
- 即剔除 2024 两个热门 ETF（512200 / 510310），K=3 仍领先 K=5、K=8

**含义**：策略本质是"行业池子 + 熊市避险"，不是"持续选出强势板块"。后续接 cockpit 多极投票替换 SimpleRegimeOverlay 大概率提升。

验证脚本归档在 `/tmp/rotation_validation.py`（一次性分析，不入库）。

---

## 6. Error handling

| 场景 | 处理 |
|------|------|
| Universe 内某 ETF 在 rebalance_date 之前数据不足（< 13 个月）| 当期排名时直接剔除该标的，不参与；记录 `skipped_symbols` 到回测日志 |
| 整个 universe 都数据不足 | `MomentumRanker.rank()` 抛 `InsufficientDataError`；`RotationBacktester` 跳过该月，equity 持平 |
| benchmark 数据缺失 | `SimpleRegimeOverlay` 返回 multiplier = 0（最保守）+ logger.warning |
| Universe yaml 格式错误 | `RotationService.__init__` 直接抛 `ValueError`，不静默兜底 |
| DataService 拉数据失败 | 透传异常，不在 RotationService 层吞 |
| `cash_threshold` 触发但用户调仓时仍想持有最强 K 只 | 不支持——cash filter 是设计决策；用户要覆盖，改 `RankerConfig.cash_threshold = -inf` |

---

## 7. Testing strategy

### 7.1 Unit tests（每个模块对应一个文件）

**`test_rotation_ranker.py`**
- 用合成数据：12 个 ETF 各自有已知动量，验证 top-K 选对了。
- cash_threshold 触发时返回空 dict。
- 数据不足的标的被剔除。
- 12-1 公式正确性：手算 3 个简单例子比对。

**`test_rotation_overlay.py`**
- 包装层正确调用 `LowFrequencyRegimeScorer`。
- multiplier 输出 clip 到 [0, 1]。
- benchmark 数据缺失时返回 0 + warning。

**`test_rotation_portfolio.py`**
- B 空 dict + 任意 multiplier → 全现金。
- multiplier=1 + weights → final = weights。
- multiplier=0.5 + weights → 每个标的 ×0.5，cash = 0.5。

**`test_rotation_backtest.py`**
- 合成多资产数据，验证 turnover 计算（L1 距离公式）。
- 交易成本扣减正确性。
- 三条净值曲线维度正确（strategy / hs300 / equal_weight）。

### 7.2 Integration test

**`test_rotation_pipeline.py`**
- Fixture：`tests/fixtures/rotation_universe_2018_2024.parquet`（约 6 年、24 ETF 的月末价格快照）+ 沪深 300 价格。
- 锁定 ranker / overlay / combiner 的随机性后，回测结果哈希应该稳定。
- 断言：`metrics['annual_return_strategy'] > metrics['annual_return_benchmark']`（在该 fixture 上预期成立，是 sanity check 不是真实业绩证明）。

### 7.3 What we do NOT test

- 不做"策略真实回测业绩好不好"的 unit test——那是研究问题不是软件问题。
- 不做实时数据获取的测试——DataService 自己有覆盖。

---

## 8. Out of scope / Future work

按工程价值从高到低排：

1. **Cockpit overlay 接入**（替换 `SimpleRegimeOverlay`）：用 cockpit 的 regime detector + transmission graph + 美元流动性置信度，把 multiplier 从"单 benchmark 三档"升级成"多极投票连续值"。需要 Track 3 整合先完成。
2. **回测报告 web 视图**：把 `RotationBacktestResult` 接到现有 web app，月度持仓变化 + 累计净值可视化。
3. **多因子扩展**：在 ranker 里加估值反向 / 景气度 overlay；先验证动量基线再加。
4. **逐周调仓变体**：保留接口可调，做对照实验（月度 vs 双周 vs 周）。
5. **Universe 自动维护**：从交易所或 akshare 拉每日 ETF 规模/成交量，自动剔除流动性不足的。

---

## 9. 风险与局限

- **样本量有限**：2018-2026 ≈ 84 个再平衡点。对单一参数组合（lookback=12, K=5）够用，但跑参数 grid search 容易过拟合。**对策**：参数固定，不做 in-sample 调优；后续如要调，用 walk-forward。
- **2015 / 2008 这种极端样本不在训练集**：B 完全没见过。**对策**：靠 A 层 multiplier 兜底——在 vol 高 + drawdown 深时整体压低仓位。
- **行业 ETF 上市时间不一**：早期 universe 实际可用数 < 24，回测前几个月排名结果会不稳。**对策**：回测起点 2018-01 时大部分主流 ETF 已上市；早期 N/A 标的剔除而非填充。
- **Style ETF 和 industry ETF 类别交叉**（沪深 300 既是 universe 成员又是 benchmark）：会让"打败 benchmark"看起来更容易。**对策**：metrics 里同时和"等权 universe"比，这才是诚实对照。

---

## 10. 决策摘要（供 review 时扫一眼）

| 决策项 | 选择 |
|--------|------|
| 主引擎 | B 行业 ETF 截面动量 |
| 风险 overlay | A SimpleRegimeOverlay (包 LowFrequencyRegimeScorer) |
| 个股择时 | 不做 |
| 调仓频率 | 月末 |
| 动量公式 | 6-1 月（lookback=6, skip=1）— 见 §5.3 验证 |
| top K | 3，等权 — 见 §5.3 验证 |
| 现金过滤 | top-K 平均动量 < 0 切全现金 |
| 交易成本 | 0.2% 双边 |
| 回测起点 | 2018-01 |
| 对照基准 | 沪深 300 + 等权 universe |
| Universe | 24 ETF 总计 = 20 行业 + 4 风格 |
| Cockpit 整合 | 预留接口，本期不做 |
| 多因子 | 预留接口，本期不做 |
| 自动下单 | 不做 |
