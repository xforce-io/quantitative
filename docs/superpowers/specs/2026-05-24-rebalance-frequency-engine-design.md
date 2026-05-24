# Rebalance-Frequency-Parametrized Backtest Engine Design

**Date:** 2026-05-24
**Scope:** 把 `scripts/long_rotation_discovery.py` 及其依赖的 `quant/analysis/rotation/*` 模块从硬编码月频改造成 frequency-参数化引擎，使 petri 能够把"换仓频率"作为一个真正的搜索轴。
**Status:** Draft — awaiting review before plan decomposition.

---

## 背景

`run_007_production` 是当前 SOTA（real_etf_full 23.64%），月频换仓。两个 petri 搜索分支（`factor-weight-search` / `risk-on-structure-search`）已穷尽因子权重和 `top_k`，5 次 REJECT 全部成立 —— 参数空间已耗尽。

下一个未被检验的轴是**换仓频率**（月频 vs 双周 vs 周频）。但当前实现存在结构性阻塞：

- `candidates/*.json` 中 `rebalance_frequency` 字段**完全没有被读取**（grep 验证：`long_rotation_discovery.py` 与 `quant/analysis/rotation/*` 无任何引用）
- 数据层只提供月频 bar（`fetch_proxy_monthly_prices` / `fetch_etf_monthly_prices`）
- Ranker 接口签名是 `rank(monthly_prices, rebalance_date)`，单位是月数（`monthly_prices.iloc[loc - lookback]`）
- 全局共 193 处 `month` / `monthly` 引用，所有循环、warmup、fold 切分都以月为单位
- `long_rotation_discovery.py` 顶部常量 `TRAIN_MONTHS=24 / TEST_MONTHS=6 / STEP_MONTHS=6 / WARMUP_MONTHS=15` 都是月

petri 无论调度多少次，结果不会变化。**这是引擎能力问题，不是策略问题。** 引擎升级是 petri 能继续迭代的前置条件。

---

## 目标

构建一个**单一引擎**，通过 `frequency` 参数支持月频、双周、周频三种换仓节奏；月频路径必须**严格复现** `run_007` 的现有数字（差异 < 0.01pp，作为重构正确性的 golden test）。

非目标（明确排除）：

- 日频换仓 — 交易成本和噪声不在本期讨论范围
- 引入新因子或新策略 — 本期是引擎层重构，因子定义保持不变
- 改动 petri pipeline / candidate JSON schema — 升级后 `rebalance_frequency` 字段从死字段变成活字段，向后兼容
- 改动数据存储层 — 已有日频 CSV 足够，不需要新数据源

---

## 设计原则

1. **单一引擎，参数化频率**。不为周频另起一套并行代码。月频/双周/周频走同一份代码路径，区别仅在 `frequency` 与对应的日历窗口换算。
2. **日历窗口语义，不是 bar 计数**。"6 个月动量"在所有频率下都等于"过去约 126 个交易日的收益率"；不允许出现"周频时 lookback=6 个 bar = 6 周"这种语义滑动。
3. **月频可复现性是一票否决**。重构后 `frequency=monthly` 必须复现 run-007 在 3 个 universe 上的年化收益与 MDD，差异 < 0.01pp。否则视为重构失败，必须修复或回滚。
4. **不动 petri pipeline schema**。candidate JSON 字段不变；`rebalance_frequency` 从死字段升级为活字段，老 candidate（值为 `"monthly"`）行为不变。
5. **单一数据源**。底层数据加载切到日频 CSV，按 `frequency` 重采样得到回测 bar；不维护"月频 CSV / 周频 CSV"两份并行数据。

---

## 设计

### 1. Frequency 抽象

引入 `BacktestFrequency` 枚举（或简单字符串 + 校验），值 ∈ `{"monthly", "biweekly", "weekly"}`。每个 frequency 关联一组派生常量：

| frequency  | bars/year | calendar_days/bar | trading_days/bar | rebalance_anchor      |
|------------|-----------|-------------------|------------------|-----------------------|
| `monthly`  | 12        | ~30               | ~21              | month-end last TD     |
| `biweekly` | 26        | ~14               | ~10              | every other Friday    |
| `weekly`   | 52        | ~7                | ~5               | every Friday          |
|

派生关系（避免硬编码到多个地方）：
- `bars_per_year(freq)` → 12 / 26 / 52
- `trading_days_per_bar(freq)` → 21 / 10 / 5（仅供因子日历窗口换算用，不参与 bar 切分）
- `resample_rule(freq)` → pandas 重采样规则，分别为 `"M"` / `"2W-FRI"` / `"W-FRI"`

### 2. 因子日历窗口换算

当前因子规格（每个 candidate JSON 内）:
```json
{ "name": "momentum",         "lookback_months": 6, "skip_months": 1 }
{ "name": "low_volatility",   "lookback_months": 6 }
{ "name": "relative_strength","lookback_months": 6, "benchmark": "000300.SH" }
```

`lookback_months` 与 `skip_months` 字段保留原语义（含义是"日历月数"），引擎内部按以下规则换算成当前 frequency 下的 bar 数：

```
lookback_bars = round(lookback_months × bars_per_year(freq) / 12)
skip_bars     = round(skip_months     × bars_per_year(freq) / 12)
```

实际值：

| 频率       | 6 个月 lookback | 1 个月 skip |
|-----------|----------------|------------|
| monthly   | 6              | 1          |
| biweekly  | 13             | 2          |
| weekly    | 26             | 4          |

注意：`min_hold_months` 同样按上式换算成 `min_hold_bars`。

替代方案（已否决）：将字段重命名为 `lookback_days` / `lookback_calendar_units`。**否决理由**：会破坏所有现存 candidate JSON（包括 run-007 SOTA spec）的向后兼容；用户心智模型本身就是"几个月"，无需强迫重命名。

### 3. 数据加载层重写

当前两个函数 `fetch_proxy_monthly_prices()` / `fetch_etf_monthly_prices()` 直接返回月频 DataFrame。改造：

- 改名为 `fetch_proxy_prices(freq)` / `fetch_etf_prices(freq)`（保留旧函数名作为 `freq="monthly"` 的薄包装，避免调用方爆炸式改动）
- 内部流程：
  1. 始终先加载**日频** close price（从 `data/tushare/*.csv` 与 yahoo 缓存）
  2. 应用 `MAX_SINGLE_DAY_ABS_RET=0.25` 异常 ETF 过滤（**在日频上做**，不能滞后到重采样后）
  3. 按 `resample_rule(freq)` 重采样到目标频率，规则统一为"period 内最后一个有效 TD 的 close"
- 输出仍是同样 schema 的 `DataFrame[index=Period-end Timestamp, columns=symbols]`

> ⚠️ **不变量**：所有 ranker、regime overlay、portfolio combiner 接收的 `prices` 参数语义是"按当前 frequency 重采样后的 bar"。变量名从 `monthly_prices` 改为 `prices`（IDE rename）。函数签名内不再出现 `monthly` 字样。

### 4. Ranker / Overlay 适配

**MultiFactorRanker / MomentumRanker / RegimeOverlay / PortfolioCombiner** 当前内部使用 `monthly_prices.iloc[loc - lookback_months]`。改造：

- 构造函数接收 `lookback_bars` / `skip_bars` / `min_hold_bars`（在引擎入口处完成换算）
- 函数内不再出现 `_months` 后缀的局部变量
- 接口签名：`rank(prices: DataFrame, rebalance_date: Timestamp) -> dict[str, float]` —— `prices` 是当前频率的 bar

**Regime filter** 的 `benchmark_lookback_months` / `industry_momentum_lookback_months` 同样按上式换算成 bar 数。

### 5. Fold 切分与 Warmup

当前：`TRAIN_MONTHS=24 / TEST_MONTHS=6 / STEP_MONTHS=6 / WARMUP_MONTHS=15`。

改造：以"日历月"为锚定单位（不是 bar 数），按 frequency 换算成 bar 数后用于切片：

- `TRAIN_CAL_MONTHS = 24` → `train_bars = round(24 × bars_per_year / 12)`
- 同理 `TEST_CAL_MONTHS=6 / STEP_CAL_MONTHS=6 / WARMUP_CAL_MONTHS=15`

**理由**：fold 在日历时间上对齐才能在跨频率间公平比较（"过去 2 年训练 / 半年测试"应该对所有 frequency 含义相同），不能因为频率不同导致样本期错位。

### 6. CLI 与 candidate JSON

- `long_rotation_discovery.py` 新增 `--frequency` 参数（可选，默认 `monthly`，向后兼容现有 petri 调用）
- candidate JSON 中已存在的 `risk_on_allocation.rebalance_frequency` 字段被真正消费；如果 `--frequency` 与 JSON 字段冲突，**JSON 字段优先**（candidate 内一致性更重要）
- `risk_off_allocation.rebalance_frequency`（若存在）独立读取；不要求两个 sleeve 同频，但本期 petri 实验会保持两个 sleeve 频率一致

---

## 验收标准

### A. 月频复现（一票否决）

新引擎 `--frequency monthly` 跑 `run_007_production.json` 必须产出：

| Universe        | run-007 数字（baseline）| 容差 |
|-----------------|------------------------|------|
| index_proxy ann. return | 0.1211          | < 0.0001 (0.01pp) |
| index_proxy MDD         | -0.1989         | < 0.0001 |
| real_etf_full ann.      | 0.2364          | < 0.0001 |
| real_etf_full MDD       | -0.1052         | < 0.0001 |
| real_etf_subset ann.    | 0.0974          | < 0.0001 |
| real_etf_subset MDD     | -0.1874         | < 0.0001 |

任何一项超出容差，重构未通过。

### B. 双周 / 周频可执行性

`--frequency biweekly` 和 `--frequency weekly` 跑同一份 `run_007_production.json`：

- 全程无 exception
- 三个 universe 都产出有效年化收益率与 MDD
- 结果合理性检查（不是验收，但应自查）：
  - 双周/周频年化偏离月频 < 10pp 量级（否则可能有 bug）
  - 持仓换手率随频率上升而上升

### C. petri 兼容

- 现有 3 个老 candidate（`top-k-2.json` 等）继续跑出与历史归档一致的结果
- `factor_weight_search` 与 `risk-on-structure-search` branch 不需要重跑（它们已 closed）；只需确认对应历史 `result.json` 不被新引擎破坏

### D. 单测覆盖

- frequency 抽象的换算函数（`bars_per_year` / `lookback_bars_from_months`）有单测覆盖三档频率
- 数据加载层的重采样规则有单测验证 period-end 对齐
- Ranker 在月频下的输出与旧实现 bit-for-bit 一致（fixture 对比）

---

## 不做的事（YAGNI）

- 日频换仓
- 跨频率混合（risk_on 周频 + risk_off 月频）—— schema 允许但 petri 实验不会用
- 自适应频率（依据 volatility regime 切换）—— 是未来研究项，与本期无关
- 周频专用因子（如 5 日反转）—— 本期只换 bar 切分，不动因子定义
- 交易成本/滑点建模升级 —— 现有月频用的是零成本回测，周频也保持同口径；想公平比较"加成本后周频是否仍占优"是另一个 spec

---

## 后续工作

引擎升级合入后，启动新 petri branch `rebalance-frequency-search`（baseline = run_007）。候选三只：

| candidate            | 改动                            | 假设                                  |
|----------------------|---------------------------------|---------------------------------------|
| `frequency-weekly`   | rebalance_frequency = weekly    | 提升频率能更快捕捉行业动量切换         |
| `frequency-biweekly` | rebalance_frequency = biweekly  | 双周是月频与周频的中间地带，可能 trade-off 最佳 |
| `frequency-weekly-skip-tightened` | weekly + skip_months 1→0 | 周频下"跳过最近 1 个月"的反转过滤可能不必要 |

Gate 标准沿用现有：`real_etf_full ann. ≥ +1.0pp`，MDD/subset 不退化超过 0.5pp。

预期结果不一定是 ACCEPT —— 如果三只候选全部 REJECT，本期产出的负结果价值在于**彻底关闭"换仓频率"这条心结**，把策略迭代精力释放给真正的结构性创新（新因子、新 universe、新 regime 模型）。

---

## 风险

| 风险                                            | 应对                                   |
|------------------------------------------------|----------------------------------------|
| 重采样规则细节差异导致月频复现失败              | golden test 早跑早暴露；必要时按行 diff 月度 bar 序列定位偏差 |
| 周频/双周下样本不足导致 factor rank 不稳定      | 检查每个 rebalance date 的有效 symbol 数 ≥ top_k × 2 |
| Yahoo / Tushare 日频缓存里有 split 异常未被检测 | 当前 `MAX_SINGLE_DAY_ABS_RET=0.25` 仍在日频做过滤，沿用既有保护 |
| 引擎重构破坏 petri pipeline 的 candidate 老兼容 | 保留旧函数名作为薄包装；run-007 golden test 覆盖 |

---

## Open Questions

1. **`risk_off_allocation` 是否需要独立 frequency？** 当前所有 candidate 两个 sleeve 同频；schema 允许独立但本期不构造异频候选。倾向：**允许，但不强制**。
2. **`STEP_CAL_MONTHS=6` 是否在更高频下变得太粗？** 月频下 6 个月 step = 6 个 bar，周频下 = 26 个 bar，区别不大。**保持不变。**
3. **重采样规则的周锚定日 = Friday，对不对？** A 股周五是当周最后一个交易日，没有歧义。**确认 Friday。**
