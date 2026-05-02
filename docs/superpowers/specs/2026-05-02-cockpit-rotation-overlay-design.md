# Cockpit Regime Overlay for A-share Rotation — Design

**日期**：2026-05-02
**状态**：approved → 待 implementation plan

## 0. Context

A 股行业 ETF 轮动策略（spec `2026-05-02-ashare-rotation-design.md`）已落定，2018-2024 真实数据回测表明：**真正的 alpha 来源是 cash filter 在熊市的避险能力**（2018 / 2022 共救 ~50pp），而非 momentum selection。

当前 cash filter 由 `SimpleRegimeOverlay`（包 `LowFrequencyRegimeScorer`）驱动，仅基于沪深 300 的 MA200 + drawdown，信号粗糙；2024 OOS 完全踏空政策反弹。

并行 Decision Cockpit 项目（`2026-04-12-decision-cockpit-design.md`）已完成 Track 2，其中 `RegimeDetector` 是按 4 池 × 多指标投票的成熟分类器。本 spec 把 a_shares 池的 RegimeDetector 接入 rotation overlay，作为 SimpleRegimeOverlay 的高质量替代。

---

## 1. Goal

把 cockpit 的 `RegimeDetector("a_shares")` 包装成 `RegimeOverlay` Protocol 的实现，可在 RotationService 中作为 `SimpleRegimeOverlay` 的对照/替代使用，从而：

- 提升 cash filter 信号质量（更多指标投票，而不是单一 MA + DD）
- 验证 cockpit 在 rotation 场景的实际增益
- 为后续多池/跨资产 overlay 留出扩展点

### 1.1 Non-goals

- 不接入 cockpit `VerdictEngine` 的完整 add/hold/reduce/avoid 输出（需要 signals/transmissions 历史回放，复杂度爆炸，留给后续）
- 不做多池聚合（不引入 us_stocks regime 作为跨资产风险信号）
- 不动 cockpit 既有代码（RegimeDetector / 现有 analyzer 一行不改）
- 不替换 SimpleRegimeOverlay；新 overlay 与既有并行，opt-in 切换

### 1.2 Success criteria

- `CockpitRegimeOverlay` 实现 `RegimeOverlay` Protocol，可与 `RotationBacktester` 直接配合
- `RotationRequest.overlay_type = "cockpit"` 端到端跑通真实数据回测
- 单元测试 + 1 个 integration 用例全过
- 与 Simple overlay 在 2018-2024 真实数据上做对比（手工 validation 脚本，非 CI）

---

## 2. Architecture

3 层模块，2 个新文件 + 3 处既有文件改动。

### 2.1 模块布局

```
quant/services/
  data_service.py             [改] 新增 get_margin_balance / get_northbound_flow

quant/data/implementations/
  tushare_provider.py         [改] 新增对应底层方法（如缺失）

quant/analysis/regime/
  regime_detector.py          [不动]
  historical_indicators.py    [新] AshareHistoricalIndicators

quant/analysis/rotation/
  cockpit_overlay.py          [新] CockpitRegimeOverlay
  regime_overlay.py           [不动] SimpleRegimeOverlay 仍是默认
  __init__.py                 [改] 导出 CockpitRegimeOverlay

quant/services/rotation_service.py     [改] overlay_type 分支
quant/cli/rotation.py                  [改] --overlay 参数
```

### 2.2 总体数据流

```
RotationService.run_backtest(req with overlay_type="cockpit")
  │
  ├─ overlay = CockpitRegimeOverlay(data_service)
  │   └─ overlay.precompute(start, end):
  │       ├─ panel = AshareHistoricalIndicators(ds).build(start, end)
  │       │   ├─ ds.get_margin_balance → 30 日 trend
  │       │   └─ ds.get_northbound_flow → 20 日累计
  │       └─ for each trading_day in panel.index:
  │             state = RegimeDetector.classify_pool(
  │                       "a_shares", panel.loc[date].dropna().to_dict())
  │             multipliers[date] = config.multiplier_map[state.regime]
  │
  └─ RotationBacktester.run(..., overlay=overlay, ...)
       └─ for each rebalance month-end:
            multiplier = overlay.multiplier_at(rebalance_date)
            ... 既有逻辑不变
```

### 2.3 与现有架构的关系

- **`RegimeOverlay` 是已有的 Protocol**（`quant/analysis/rotation/regime_overlay.py`）— 设计时已留出扩展点，新 overlay 只需实现 `multiplier_at(date) -> float`。
- **RegimeDetector 一行不改**：cockpit 实时分类逻辑保持稳定。
- **SimpleRegimeOverlay 是默认值**：保守迁移，新 overlay 通过 `overlay_type="cockpit"` 显式启用。
- **RotationBacktester / Ranker / Combiner 不动**：overlay 是注入依赖，对它们透明。

---

## 3. Components

### 3.1 `DataService` 扩展

**位置**：`quant/services/data_service.py`

新增两个方法，与既有 `get_money_flow` 同模式：

```python
def get_margin_balance(
    self,
    start: str,
    end: str,
    provider: Any | None = None,
    provider_name: str = "tushare",
) -> pd.DataFrame:
    """两市融资融券余额日频汇总。

    Returns DataFrame with columns:
      - trade_date (pd.Timestamp)
      - rzye       (融资余额, 元)
      - rqye       (融券余额, 元)
      - total      (rzye + rqye)
    """
    data_provider = provider or self._create_provider(provider_name)
    if not hasattr(data_provider, "get_margin_balance"):
        raise NotImplementedError("Margin balance is not supported by this provider")
    return data_provider.get_margin_balance(start, end)


def get_northbound_flow(
    self,
    start: str,
    end: str,
    provider: Any | None = None,
    provider_name: str = "tushare",
) -> pd.DataFrame:
    """沪股通+深股通日频净买入。

    Returns DataFrame with columns:
      - trade_date (pd.Timestamp)
      - hgt_net    (沪股通净买入, 亿元)
      - sgt_net    (深股通净买入, 亿元)
      - total_net  (hgt_net + sgt_net)
    """
    data_provider = provider or self._create_provider(provider_name)
    if not hasattr(data_provider, "get_northbound_flow"):
        raise NotImplementedError("Northbound flow is not supported by this provider")
    return data_provider.get_northbound_flow(start, end)
```

### 3.2 `TushareProvider` 底层方法（如缺失则补）

**位置**：`quant/data/implementations/tushare_provider.py`

```python
def get_margin_balance(self, start: str, end: str) -> pd.DataFrame:
    """薄包 pro.margin(start_date, end_date) — 沪深两市汇总后返回。"""
    ...

def get_northbound_flow(self, start: str, end: str) -> pd.DataFrame:
    """薄包 pro.moneyflow_hsgt(start_date, end_date)。"""
    ...
```

实现细节按 Tushare API 文档；返回 DataFrame 的列名按 §3.1 规范。

### 3.3 `AshareHistoricalIndicators`

**位置**：`quant/analysis/regime/historical_indicators.py`

```python
@dataclass(frozen=True)
class IndicatorPanelConfig:
    margin_trend_lookback_days: int = 30
    northbound_flow_window_days: int = 20

class AshareHistoricalIndicators:
    """构建 a_shares regime 所需的历史指标时序面板。"""

    def __init__(
        self,
        data_service,
        config: IndicatorPanelConfig | None = None,
    ) -> None: ...

    def build(self, start: str, end: str) -> pd.DataFrame:
        """返回 DataFrame：
          index   : DatetimeIndex（自然日，ffill 自交易日）
          columns : ['margin_debt_trend', 'northbound_flow']

        - margin_debt_trend = (margin_total_t / margin_total_{t-30d} - 1) * 100
        - northbound_flow   = sum(total_net) over last 20 trading days

        某指标拉数据失败 → 该列全 NaN，logger.warning。
        两个都失败 → 返回空 DataFrame。
        """
```

**关键行为**：
- 交易日数据 → 自然日索引 ffill（保证月末若是周末仍能取到上一交易日值）
- 不缓存（缓存归调用方/测试夹具）
- 指标缺失用 NaN 而非 0 或省略，让 RegimeDetector 自己跳过

### 3.4 `CockpitRegimeOverlay`

**位置**：`quant/analysis/rotation/cockpit_overlay.py`

```python
@dataclass(frozen=True)
class CockpitOverlayConfig:
    pool: str = "a_shares"
    multiplier_map: dict[str, float] = field(default_factory=lambda: {
        "risk-on":    1.0,
        "transition": 0.5,
        "risk-off":   0.0,
    })

class CockpitRegimeOverlay:
    """实现 RegimeOverlay Protocol。"""

    def __init__(
        self,
        data_service,
        regime_detector: RegimeDetector | None = None,
        indicators: AshareHistoricalIndicators | None = None,
        config: CockpitOverlayConfig | None = None,
    ) -> None: ...

    def precompute(self, start: str, end: str) -> None:
        """构建 indicator panel + 逐 trading day 调 RegimeDetector，
        把 multiplier 序列存到 self.multipliers (pd.Series)。"""

    def multiplier_at(self, date: pd.Timestamp) -> float:
        """与 SimpleRegimeOverlay 一致：
        - date < self.multipliers.index[0] → 0.0
        - 否则取 ≤date 的最近一条 multiplier"""

    @property
    def regime_history(self) -> pd.DataFrame:
        """调试用：(date, regime, confidence, multiplier, drivers_str)。
        不影响主流程；用于 spec validation 脚本和 UI 可视化。"""
```

### 3.5 `RotationService` / CLI 改动

**`quant/services/rotation_service.py`**：

```python
@dataclass(frozen=True)
class RotationRequest:
    # ... 既有字段
    overlay_type: str = "simple"   # "simple" | "cockpit"

class RotationService:
    def _build_overlay(self, request: RotationRequest):
        if request.overlay_type == "simple":
            overlay = SimpleRegimeOverlay(
                data_service=self.data_service,
                benchmark_symbol=request.overlay_benchmark,
            )
        elif request.overlay_type == "cockpit":
            # overlay_benchmark 字段仅 simple 用，cockpit 不依赖 benchmark
            overlay = CockpitRegimeOverlay(data_service=self.data_service)
        else:
            raise ValueError(f"unknown overlay_type: {request.overlay_type}")
        overlay.precompute(start=request.start, end=request.end)
        return overlay
```

**`quant/cli/rotation.py`**：
```python
parser.add_argument("--overlay", choices=["simple", "cockpit"], default="simple",
                    help="风险 overlay 选择，默认 simple")
```
然后传递给 `RotationRequest.overlay_type`。

---

## 4. Data flow（一次月末调仓）

时序保证（无 look-ahead）：

| 时点 | 数据状态 |
|------|---------|
| 月末 T 收盘后 | margin balance / northbound 当日 EOD 已发布 |
| `multiplier_at(T)` 调用 | 取 ≤T 的最近一条 multiplier，所有上游指标基于 T 及之前的数据 |
| `margin_debt_trend` | T 时点的值 = T 当日余额 / (T-30d) 当日余额 - 1，纯历史 |
| `northbound_flow` | T 时点的值 = 过去 20 个交易日累计净买入，纯历史 |
| ranker.rank(T) | 按月线动量选股，不受 overlay 影响 |
| combiner.combine(weights, multiplier) | 合并 |

---

## 5. Configuration

| 参数 | 默认值 | 来源 |
|------|-------|------|
| `IndicatorPanelConfig.margin_trend_lookback_days` | 30 | 月度变化反映融资情绪转向，与月度调仓周期匹配 |
| `IndicatorPanelConfig.northbound_flow_window_days` | 20 | ~1 个月交易日，平滑日波动 |
| `CockpitOverlayConfig.multiplier_map` | `{risk-on:1.0, transition:0.5, risk-off:0.0}` | 与 RegimeDetector 三档输出一对一；risk-off=0.0 提供独立的全空仓避险，与 ranker 的 cash_threshold 形成双保险 |
| `CockpitOverlayConfig.pool` | `"a_shares"` | 当前 spec 范围 |
| `RotationRequest.overlay_type` | `"simple"` | 保守迁移，cockpit opt-in |

`config/regime_thresholds.yaml`（cockpit 既有）的 `a_shares` 区段需要包含 `margin_debt_trend` 和 `northbound_flow` 的阈值；如缺失，本 spec 不修改既有配置（cockpit 项目维护），由 implementation 阶段验证后视情况增补。

---

## 6. Error handling

| 场景 | 处理 |
|------|------|
| `get_margin_balance` 或 `get_northbound_flow` 抛异常 | `build()` 该列填 NaN，logger.warning |
| 两个底层数据全失败 | `build()` 返回空 DataFrame；`precompute()` 空 Series；`multiplier_at` 全返回 0.0（最保守，全空仓） |
| 某交易日两个指标都 NaN | RegimeDetector 投票总数=0 → regime="transition" → multiplier=0.5 |
| RegimeDetector 抛异常（yaml 缺失） | `precompute()` 直接抛，setup 错误不静默 |
| 某指标 yaml 没 threshold 项 | RegimeDetector 既有逻辑跳过，不报错 |
| `multiplier_at(date)` date < precompute 起点 | 返回 0.0 |
| `precompute()` 未调就 `multiplier_at()` | self.multipliers 空 → 返回 0.0（防御性） |
| `multiplier_map` 没覆盖 RegimeDetector 输出的某 regime | KeyError 直接抛（配置 bug fail loud） |
| `overlay_type` 是无效字符串 | `_build_overlay` 抛 ValueError |

**原则**：
- 数据缺失 → 中性 multiplier 0.5
- 完全无数据 → 0.0 全空仓
- 配置错误 → fail loud

---

## 7. Testing strategy

### 7.1 Unit tests

**`tests/unit/test_ashare_historical_indicators.py`**
- `test_margin_debt_trend_computes_30day_pct_change` — stub 固定 margin 序列，断言指定日期 trend 值
- `test_northbound_flow_rolls_20_trading_days` — stub 30 日数据，断言 20 日滚动求和
- `test_missing_margin_data_results_in_nan_column` — `get_margin_balance` 抛异常 → margin 列 NaN，northbound 列正常
- `test_both_sources_fail_returns_empty_dataframe`
- `test_natural_day_index_with_ffill` — stub 仅交易日，验证周末 ffill
- `test_config_overrides_lookback_windows`

**`tests/unit/test_cockpit_overlay.py`**
- `test_precompute_classifies_each_trading_day` — multipliers 长度 == panel 长度
- `test_risk_on_maps_to_1_0` — stub 触发 risk-on 投票
- `test_risk_off_maps_to_0_0` — 反向 stub
- `test_transition_maps_to_0_5` — 投票分散
- `test_multiplier_at_returns_latest_le_date` — 跨周末取 ≤date 最近
- `test_multiplier_at_before_series_returns_zero`
- `test_regime_history_property_exposes_drivers`

**`tests/unit/test_data_service.py`**（在已有文件加 ~3 用例）
- `test_get_margin_balance_delegates_to_provider`
- `test_get_margin_balance_raises_when_provider_missing`
- `test_get_northbound_flow_delegates_and_raises`

### 7.2 Integration test

**`tests/integration/test_rotation_pipeline.py`**（在已有文件加 1 用例）
- `test_pipeline_runs_with_cockpit_overlay` — 扩展 `_DeterministicDataService` 加 stub 的 margin/northbound 方法，跑 `overlay_type="cockpit"` 端到端
  - 不抛异常
  - equity_curve 有数据
  - holdings 矩阵 max(per row) ≤ top_k

### 7.3 不做的测试

- 不写真实 Tushare 数据的 unit/integration 测试（外部依赖、慢、CI 不稳）
- 真数据回测对比 Simple vs Cockpit 是 implementation 阶段的手工验证，归一次性脚本（参考 `/tmp/rotation_validation.py` 模式），不入库
- 不重测 RegimeDetector（cockpit 既有 212 项测试已覆盖）
- 不测试不同 `multiplier_map` 配置组合

---

## 8. Out of scope / Future work

- 多池聚合（us_stocks/gold/commodities regime 作为跨资产 overlay）
- 接入 `VerdictEngine` 的 add/hold/reduce/avoid 完整决策（需要 signals/transmissions 历史回放）
- 把 `market_breadth` 和 `china_risk_score` 这两个复合指标的历史化版本加进来
- multiplier_map 的 in-sample 调优（先用直觉默认值，等真数据验证后再说）
- 实时 cockpit overlay 通过 RotationService.latest_targets 输出每日决策（当前 spec 仅服务回测/月末决策）

---

## 9. 风险与局限

- **指标少于实时 cockpit 版本**：实时 RegimeDetector 用 4 个 a_shares 指标投票，本 spec 只用 2 个。投票 total ≥ 2 时 60% threshold 仍生效，但分辨率低；好处是**无 look-ahead 可严格保证**。
- **regime_thresholds.yaml 当前阈值的分布未在历史日频数据上验证过**：单位与本 spec 计算口径匹配（margin_debt_trend 是 % 变动，northbound_flow 是亿元累计），但 risk_on_above=2.0、risk_off_below=-3.0、北向 ±50/-80 这些具体数字是按实时使用场景校准的，2018-2024 历史日频分布的分位数可能落在阈值之外（导致绝大多数日期都是 transition）。Implementation 阶段必须做：拉历史 panel → 看分布直方图 → 必要时在 spec validation 报告里建议新阈值（不在本 spec 强行预设新值）。
- **margin / northbound 数据 Tushare 历史完整性**：northbound 通从 2014 年开始；2018-2024 应完整，但更早的回测会缺数据。
- **真数据增益未知**：cockpit 信号不一定就比 Simple 好。Implementation 阶段必须做手工对比（同样 2018-2024 区间），如果 cockpit 没显著优于 Simple，spec 价值打折——这是开放风险。

### 9.1 Validation 实测结果（2026-05-02 更新）

Implementation Task 8 跑 2018-01 到 2024-12 真实 Tushare 数据，对比 simple vs cockpit（默认 K=3, lookback=6）：

| overlay | 总收益 | 年化 | MDD | Sharpe |
|---|---|---|---|---|
| simple | +53.95% | +6.36% | -8.87% | 0.319 |
| **cockpit** | **+18.03%** | **+2.40%** | **-30.94%** | **0.031** |

**Cockpit 显著跑输 simple，且 MDD 是 simple 的 3.5 倍**。结论：**当前默认配置下 cockpit 不应替换 simple**。spec 的默认 `overlay_type="simple"` 是正确决策。

诊断信息：
- 指标分布：margin_debt_trend 中位数 -0.08%（2514 个交易日），yaml 阈值 ±2.0/-3.0 落在分位数 25-75% 之间，分类有响应；northbound_flow 数据点只 439 个（vs 期望 ~1750），远低于交易日数——**Tushare HSGT 数据完整性需调查**（怀疑 `_legacy.getHSGTFlow` 有截断或聚合问题）
- regime 分布：transition 40% / risk-on 36% / risk-off 24% — 不是退化分布，overlay 确实在响应数据
- 失败原因推测：(a) 2 个指标信噪比不够；(b) yaml 阈值是按实时使用场景校准的，月线节奏下"风险开关"频率不对；(c) Simple 用沪深 300 自身的 MA200/DD 反而更直接捕捉市场风险

后续需要做的（按优先级）：
1. **查 Tushare HSGT 数据缺失**：439 vs 1750 的差距太大，可能直接影响 northbound_flow 序列长度
2. **加 market_breadth 和 china_risk_score 的历史化版本**（spec §8 已列入 future work）
3. **重新校准 yaml 阈值**：基于真实分布的 60/40 分位数而非实时场景估计
4. 上述 3 项都做完后重跑 validation；仍跑输 simple → cockpit overlay 在 a_shares rotation 场景没有 alpha，应转向"接 VerdictEngine 完整决策"或彻底放弃

---

## 10. 决策摘要

| 决策项 | 选择 |
|--------|------|
| 接 cockpit 的范围 | 仅 a_shares 池的 RegimeDetector |
| 历史指标喂法 | 走 DataService 新增方法，独立 historical_indicators 模块 |
| 初期指标 | margin_debt_trend (30d) + northbound_flow (20d) |
| regime → multiplier 映射 | 离散三档 {1.0, 0.5, 0.0} |
| risk-off multiplier | 0.0（与 ranker cash_threshold 形成双保险） |
| 与 SimpleRegimeOverlay 关系 | 并行，cockpit opt-in，simple 仍是默认 |
| precompute 粒度 | 每 trading day（月末访问 100% 命中） |
| Look-ahead 防护 | margin / northbound 均为 EOD 数据，月末决策可用 |
| 测试范围 | 新模块 unit + 1 integration 用例；不写真数据测试 |
| 真数据对比验证 | 一次性脚本，非 CI |
