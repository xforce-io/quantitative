# 系统性风险状态机（Systemic Risk State Machine）

**Date**: 2026-07-11  
**Status**: Draft  
**Related**:
- `docs/superpowers/specs/2026-03-23-global-usd-liquidity-confidence-design.md`（Alice A0007 流动性置信度）
- `docs/superpowers/specs/2026-04-12-leading-indicators-design.md`（MomentumDelta + 领先指标）
- `docs/superpowers/specs/2026-04-12-macro-enhancement-design.md`（铜金比 / 原油 / 收益率曲线）
- `docs/superpowers/specs/2026-04-12-decision-cockpit-design.md`（Verdict / Regime；本文不替换资产池 regime）
- `docs/superpowers/specs/2026-04-17-continuous-regime-scorer-design.md`（连续 regime 分数；资产池级，与本文正交）

---

## 1. Context / Motivation

### 1.1 现象

当前宏观风险模块（`MacroLiquidityAnalyzer` 八维加权分 + Dashboard 灯色）**无法在风险飙升前给出可用预警**。典型对照：石磊 Alice 系统约在 **2025-01-23** 确认全球流动性/系统性风险，而表面资产（如黄金）仍处动量上涨——现有系统在此类「表面繁荣、底层收紧」场景下天然偏绿/黄。

### 1.2 根因（已诊断，非猜测）

| # | 根因 | 表现 |
|---|------|------|
| 1 | **范式错误** | 绝对水平阈值（SOFR≥5.5、MOVE≥130）≈ 同步/滞后确认，不是领先控制变量 |
| 2 | **线性加权冲淡** | 单维 crisis 被其余「正常」维平均掉，总分难进 Crisis(≥75) |
| 3 | **领先层未入决策核** | VIX/信用/曲线/MomentumDelta 多为展示，不决定行动状态 |
| 4 | **符号错误（Alice 案例）** | 黄金维度以「金跌」为风险；金涨+金融条件紧时反而降风险分 |
| 5 | **双系统未统一** | `GlobalUsdLiquidity`（更合理的代理）仅占 15% 权重，被粗糙阈值维稀释 |
| 6 | **无事件校准** | 阈值拍脑袋；无 lead time / miss / FP 的历史回放 |
| 7 | **缺数装正常** | 维度失败 → `risk_score=50`，主动掩盖信息缺失 |

### 1.3 数据源结论

**FRED + Yahoo + Tushare 足以支撑 v1 可验证预警**；瓶颈是框架与用法，不是数据商。  
付费 basis / 私募信贷 / 实时拥挤度可提升上限，**不阻塞 v1**。

---

## 2. Goals / Non-Goals

### 2.1 Goals

1. 输出可行动的 **`SystemicRiskState`**，而非仅 0–100 装饰分：
   ```text
   normal | building | confirmed | releasing | degraded
   ```
2. 用 **非补偿聚合 + 领先/确认双层**，避免「多绿灯否决一红灯」。
3. 修正 **钱货/动量背离**（金涨 + 金融条件紧 → 风险积累，非安全）。
4. **事件回放可验证**：固定事件协议，报告 lead time / hit / miss / FP，并对照 legacy。
5. **复用现有模块**（`GlobalUsdLiquidity`、`LeadingIndicators`、`MomentumDelta`），不平行再造一套宏观宇宙。
6. 配置外置（`config/systemic_risk.yaml`），禁止阈值散落硬编码。

### 2.2 Non-Goals（本设计明确不做）

- 复刻 Alice 全量私有指标与语义层
- 采购 Bloomberg / 交叉货币 basis / 私募信贷数据（Phase 5 可选再议）
- 替换四资产池 `RegimeDetector` / `ContinuousRegimeScorer` 的语义（本文是**全球系统性风险**，正交输入）
- 实时推送 / Telegram
- 用 ML 黑盒替代可解释状态机（可后续作 backend，非 v1）
- 大改多页 UI（Dashboard 仅最小状态行 + drivers）

### 2.3 Success Criteria（v1 验收口径）

| 门槛 | 标准 |
|------|------|
| 规格单测 S1–S6 | 全过（见 §8） |
| 无前视单测 | 全过 |
| 事件 Hit（building 或 confirmed） | ≥ 5/6 约定事件 |
| 核心事件 Hard miss | covid / SVB / alice_2025_01 不得全程 normal |
| Median lead(`first_confirmed` → `anchor`) | 优于 legacy；目标 ≤ −5 交易日（校准后写入冻结值） |
| 平静期 FP | 不显著差于 legacy 基线（基线在 Phase 0 测量） |
| 线上一致性 | Dashboard 与 eval 脚本同日状态一致（抽检 3 日） |

具体数值在 Phase 0/3 测量后冻结进配置与报告，**先写门槛再调参**，禁止为单事件特判。

---

## 3. Architecture

### 3.1 总览

```text
 FRED / Yahoo / Tushare
           │
           ▼
 ┌─────────────────────────────┐
 │  systemic_risk.features     │  拉数 + 标准化 + stress∈[0,1]
 │  systemic_risk.panel        │  as_of 对齐，无前视
 └──────────────┬──────────────┘
                │ FeaturePanel
                ▼
 ┌─────────────────────────────┐
 │  systemic_risk.state_machine │  非补偿：领先层 → 确认层
 │  → SystemicRiskState        │  唯一「系统性风险」语义出口
 └──────────────┬──────────────┘
                │
     ┌──────────┼──────────┬──────────────┐
     ▼          ▼          ▼              ▼
 VerdictEngine  Dashboard  event_eval   旧宏观页钻取
                           (研究评估)
```

### 3.2 与现有模块关系

| 模块 | 新角色 |
|------|--------|
| `GlobalUsdLiquidityAnalyzer` | L1/L2 主输入（在岸溢价、NFCI/STLFSI、净流动性） |
| `LeadingIndicatorsAnalyzer` | 信用利差、VIX、收益率曲线 → L1/L3 |
| `MomentumDelta` | 全体特征 velocity / acceleration |
| `MacroLiquidityAnalyzer` | **兼容层 / drill-down**；主结论不再由其线性总分决定 |
| `RegimeDetector` / `ContinuousRegimeScorer` | 资产池环境；可消费 SystemicRiskState 作宏观先验，**不互相覆盖** |
| `VerdictEngine` | Phase 4：building/confirmed 约束加仓与风险提示 |

### 3.3 设计约束

- **单一语义出口**：全局「现在有没有系统性风险」只看 `SystemicRiskState`。
- **展示分可保留**：可另算 0–100 的 `display_score` 供图表，**不得**单独驱动 Crisis 判定。
- **缺数降级**：关键 L1 缺失 → `degraded`，禁止默认中性 50。
- **可回放**：所有打分路径支持 `as_of` / snapshot，禁止只能 `analyze()→now`。

---

## 4. Feature Panel v1

### 4.1 特征分组

| 组 | 角色 | 特征 | 源 | 极性（↑=更危险） |
|----|------|------|-----|------------------|
| **L1 金融条件（领先）** | 领先层核心 | `sofr_iorb_spread` | FRED SOFR−IORB | 高→紧 |
| | | `effr_iorb_spread` | FRED EFFR−IORB | 高→紧 |
| | | `cp_tbill_spread` | FRED DCPF3M−DGS3MO | 高→紧 |
| | | `nfcirisk` | FRED NFCIRISK | 高→紧 |
| | | `stlfsi4` | FRED STLFSI4 | 高→紧 |
| | | `hy_oas` + `hy_oas_d20` | FRED BAMLH0A0HYM2 | 水平高/走阔→紧 |
| **L2 流动性存量** | 慢变量确认 | `net_liquidity_pct` + `net_liq_d20` | WALCL−TGA−RRP | 低/下降→紧 |
| **L3 波动尾部** | 确认层（不作唯一领先） | `vix` + `vix_roc20` | Yahoo ^VIX | 高/飙升→确认 |
| | | `move` + `move_roc20` | Yahoo ^MOVE | 高/飙升→确认 |
| **L4 钱货/背离** | Alice 型场景 | `copper_gold_pct` | Yahoo HG=F/GC=F | 低→ risk-off |
| | | `gold_fc_divergence` | 金动量 vs L1 应力 | **金涨且 L1 紧 → 危险** |
| | | `real_yield_d5` | FRED DFII10 | 急升→压制风险资产（确认辅助） |
| **L5 跨境代理** | 套利压力 | `usdjpy_wchg` + `dgs2` | Yahoo JPY=X + FRED | 日元急升/利差收窄→压力 |
| **L6 A 股本地** | 仅 A 池叠加 | `margin_velocity` | Tushare | 负加速→本地风险；**不单独决定全球 confirmed** |

### 4.2 标准化规则

每个特征输出统一结构：

```python
@dataclass
class FeaturePoint:
    name: str
    value: float | None
    percentile: float | None   # 滚动窗内百分位 0–100；不足窗则 None
    zscore: float | None
    velocity: float | None     # MomentumDelta 一阶
    acceleration: float | None
    stress: float | None       # 映射到 [0, 1]，1=极端压力
    as_of: str                 # ISO date
    stale: bool                # 超过该序列 freshness 阈值
```

映射原则：

- **水平类**：滚动百分位或 z-score → `stress`（考虑 inverted）
- **变化类**：20 日变化 / ROC → z-score → `stress`
- **禁止**用跨周期绝对阈值（如 SOFR≥5.5）作为 L1 主应力；SOFR 绝对水平可保留注释字段但不进状态机核心
- 滚动窗默认：百分位 252 交易日（可配置）；velocity 窗 5；z 窗 60
- 周频序列：按交易日 ffill，**标记 frequency**，评估时知晓信息滞后

### 4.3 关键派生特征：`gold_fc_divergence`

```text
gold_mom = sign/velocity of gold close (e.g. 20d return > 0 or velocity > 0)
l1_stress = aggregate L1 stress (e.g. mean or max of core L1 stresses)

if gold_mom > 0 and l1_stress >= θ_div:
    divergence_stress = f(l1_stress, gold_mom)  # ∈ [0,1]，抬升 building 权重
else:
    divergence_stress = 0
```

语义：**表面避险/动量繁荣 + 底层金融条件收紧** = 风险积累信号（对应 2025-01 Alice 场景）。  
旧「金跌才危险」逻辑不得进入状态机核心；旧黄金异动分析器可留在 drill-down。

### 4.4 复用实现

| 数据 | 复用 |
|------|------|
| 在岸/离岸/净流动性 | `global_usd_liquidity.INDICATOR_CONFIG` 与拉取逻辑 |
| HY、VIX、曲线 | `LeadingIndicatorsAnalyzer` 或共享 fetch 函数 |
| velocity | `MomentumDelta.compute` |
| 铜金、原油 | 可从 `MacroLiquidityAnalyzer` 抽纯函数，避免双份 yfinance 逻辑长期分叉 |

优先 **抽 shared fetch + pure score**，而不是 analyzer 互相 import 成环。

---

## 5. State Machine

### 5.1 状态定义

| 状态 | 含义 | 行动暗示（Phase 4） |
|------|------|---------------------|
| `normal` | 未检测到系统性压力积累 | 常规 |
| `building` | 领先层压力积累，尚未全面确认 | 限制新增风险、提高警戒 |
| `confirmed` | 领先 + 确认层共振，系统性风险确认 | 降杠杆 / 对冲优先 |
| `releasing` | 压力缓解中 | 谨慎恢复，防二次探底 |
| `degraded` | 关键数据缺失或过期，**不可装正常** | 不自动加仓；提示数据问题 |

### 5.2 转移逻辑（v1）

```text
                    ┌──────────────┐
                    │   degraded   │ ◄── 关键 L1 缺失/过期
                    └──────┬───────┘
                           │ 数据恢复
                           ▼
 ┌─────────┐  L1 持续     ┌──────────┐  确认层     ┌───────────┐
 │ normal  │ ───────────► │ building │ ─────────► │ confirmed │
 └────▲────┘  ≥k 特征     └────┬─────┘  满足      └─────┬─────┘
      │       ≥d 日            │                         │
      │                        │ L1 回落且               │ 应力回落
      │                        │ 未确认                  │ + velocity 改善
      │                        ▼                         ▼
      │                   (回 normal)              ┌───────────┐
      └──────────────────────────────────────────│ releasing │
                    冷却 m 日全平静                └───────────┘
```

### 5.3 非补偿规则（必须实现）

1. **关键子图 veto**  
   若 `credit_widening`（`hy_oas_d20` stress 高）且 `onshore_funding`（SOFR−IORB 或 CP 溢价 stress 高）同时成立并持续 `d` 日 → **至少 `building`**，不得被黄金大涨、原油平静、MOVE 不高拉回 `normal`。

2. **背离加成**  
   `gold_fc_divergence.stress` 高 → 降低进入 `building` 所需的 k，或直接计为 1 个 L1 有效票。

3. **确认层不可单独 CONFIRMED**  
   仅 VIX/MOVE 毛刺、L1 安静 → 最多内部 warning，**不进 `confirmed`**。

4. **L6 不单独确认全球状态**  
   融资余额恶化只影响 A 股叠加提示，不单独触发全球 `confirmed`。

5. **线性均值禁止作为状态判定**  
   `display_score = weighted_mean(stress)` 仅展示；状态只走规则 1–4。

### 5.4 输出结构

```python
@dataclass
class SystemicRiskState:
    state: str                 # normal|building|confirmed|releasing|degraded
    as_of: str                 # ISO date
    confidence: float          # 0–1，规则强度/持续天数映射
    days_in_state: int
    l1_stress: float           # 汇总 0–1
    confirm_stress: float      # 确认层 0–1
    divergence_stress: float
    drivers: list[str]         # 人话，最多 5 条，按重要性排序
    feature_snapshot: dict     # 可序列化关键特征值（debug/报告）
    display_score: float | None  # 可选 0–100 展示分
    data_quality: str          # ok|partial|degraded
    updated_at: str            # ISO timestamp
```

### 5.5 配置（`config/systemic_risk.yaml`）

```yaml
windows:
  percentile: 252
  velocity: 5
  zscore: 60
  change: 20

state_machine:
  l1_stress_threshold: 0.65      # 单特征 stress 入选
  l1_min_features: 2             # k
  l1_persist_days: 3             # d
  confirm_stress_threshold: 0.60
  confirm_min_features: 1
  releasing_persist_days: 5      # m
  divergence_threshold: 0.55
  critical_l1:                   # 缺失则 degraded
    - sofr_iorb_spread
    - hy_oas
  freshness_days:
    daily: 3
    weekly: 10

display_score_weights:           # 仅展示，不驱动状态
  l1: 0.50
  l2: 0.20
  l3: 0.15
  l4: 0.10
  l5: 0.05
```

参数个数保持精简；**校准后冻结**，变更必须重跑 event eval。

---

## 6. Validation & Testing

### 6.1 三层验证

| 层 | 目的 | 载体 | CI |
|----|------|------|-----|
| **L0 正确性** | 公式、状态机、无前视 | `tests/unit/test_systemic_risk_*.py` | 是 |
| **L1 有效性** | 历史能否提前预警 | `scripts/systemic_risk_event_eval.py` + 报告 | 否（可 smoke） |
| **L2 在线可信** | 影子对照、可解释 | 日志 + 人工勾选 | 否 |

### 6.2 事件协议（`config/systemic_risk_events.yaml`）

固定事件集（可增不可默默改锚点）：

| id | anchor（主） | 说明 |
|----|--------------|------|
| `vol_2018q4` | 2018-12-24（或 stress_start 2018-10-03） | 流动性/贸易冲击 |
| `covid_2020` | 2020-03-23 | COVID 流动性危机 |
| `tightening_2022` | 2022-09-30 一带 | 紧缩 + 英债压力 |
| `svb_2023` | 2023-03-13 | 银行压力 |
| `yen_2024_08` | 2024-08-05 | 日元套利波动 |
| `alice_2025_01` | **2025-01-23** | Alice 系统性风险确认对照；secondary 2025-02-18 |

每条含：`window`, `market_proxy`（默认 SPY）, `tags`。

### 6.3 回放指标

| 指标 | 定义 |
|------|------|
| `lead_confirmed` | `first_confirmed - anchor`（交易日；负=领先） |
| `lead_building` | `first_building - anchor` |
| `hit` | 窗内出现 building 或 confirmed |
| `miss` | 全程 normal |
| `fp_rate` | 非事件平静期 confirmed 日占比 |
| `flicker` | 状态切换次数 / 窗长 |
| `post_state_dd` | 进入 confirmed 后 N 日 max drawdown（经济含义） |

**对照模型（必须同协议）**：

- A: legacy `MacroLiquidityAnalyzer` 分（映射：≥75 confirmed，≥50 building）
- B: `GlobalUsdLiquidity.confidence` 分位映射
- C: 本状态机 v1
- D（可选消融）: 仅 L1

### 6.4 规格场景单测（S1–S6）

| ID | 构造 | 期望 |
|----|------|------|
| S1 | 金涨 + L1 紧 | ≥ building，非 normal |
| S2 | 仅 VIX 单日毛刺，L1 静 | 非 confirmed |
| S3 | L1 持续 d 日 + 确认层抬升 | building → confirmed |
| S4 | 应力回落 | confirmed/building → releasing → normal |
| S5 | 关键 L1 为 NaN | degraded |
| S6 | 一维极差、其余极好 | 仍 building（非补偿）；对照线性均值会 normal |

### 6.5 无前视

`panel(as_of=T)` / `state(as_of=T)` 仅使用 `index <= T` 的观测。  
单测：T 之后植入极端值，结果必须与截断序列一致。

### 6.6 过拟合纪律

- 校准集与检查集分离：建议 2018/2020/2022/2023 校准，**2024-08 与 2025-01 作最终检查**
- 新特征必须带来 eval 表上的 lead/FP 改善，否则不加
- 禁止日期特判

---

## 7. Integration

### 7.1 代码落点

```text
quant/analysis/indicators/systemic_risk/
  __init__.py
  types.py              # FeaturePoint, SystemicRiskState
  features.py           # 特征计算与 stress 映射
  panel.py              # as_of 对齐面板
  state_machine.py      # 状态转移
  legacy_map.py         # legacy score → 伪状态（评估对照）
  actions.py            # action_hint 文案（Phase 4）

config/
  systemic_risk.yaml
  systemic_risk_events.yaml

scripts/
  systemic_risk_event_eval.py
  # Phase 0 可先实现 legacy-only 子集

tests/unit/
  test_systemic_risk_features.py
  test_systemic_risk_state_machine.py
  test_systemic_risk_no_lookahead.py

web/data_service.py       # get_systemic_risk_state()
web/pages/...Dashboard    # 一行状态 + drivers + 新鲜度
```

### 7.2 data_service

```python
def get_systemic_risk_state(as_of: date | None = None, force_refresh: bool = False) -> dict:
    """Return SystemicRiskState as plain dict; cache TTL aligned with macro (4h)."""
```

失败路径：返回 `state=degraded` + error drivers，**永不**静默 normal。

### 7.3 Dashboard（最小）

- 主结论一行：`🔴 CONFIRMED` / `🟠 BUILDING` / … + `as_of` + 数据质量
- 最多 3 条 drivers
- 旧八维灯折叠为「维度钻取」，不与主结论并列争夺注意力

### 7.4 VerdictEngine（Phase 4）

| 状态 | 建议行为 |
|------|----------|
| building | 提高风险提示权重；限制「加仓类」verdict |
| confirmed | 注入 defensive bias；组合风险提示升级 |
| degraded | 标注数据不可用，不做方向性加仓建议 |
| releasing/normal | 不额外压制（releasing 可保留谨慎文案） |

---

## 8. Implementation Phases

| Phase | 内容 | 产出 | 建议工期 |
|-------|------|------|----------|
| **0 基线** | 事件表 + legacy/usd_liq 回放 | `reports/macro_risk_baseline_*.md` | 1–2 天 |
| **1 特征面板** | features + panel + 单测 | 可 `as_of` 的 FeaturePanel | 2–3 天 |
| **2 状态机** | 非补偿规则 + S1–S6 | `SystemicRiskState` | 3–4 天 |
| **3 校准** | event eval 全模型 + 冻参 | `systemic_risk.yaml` 冻结 + 校准报告 | 2–3 天 |
| **4 接入** | data_service + Dashboard + Verdict | 线上主结论切换 | 2 天 |
| **5 可选增强** | VIX 期限、ANFCI、ETF 代理、CFTC… | 每次加一类并重跑 eval | 按需 |

**推荐最小闭环**：0 → 1 → 2 → 3；UI 可后置。  
**禁止**：未完成 Phase 0/3 就大改 Dashboard 灯色。

---

## 9. Risks & Mitigations

| 风险 | 缓解 |
|------|------|
| 事件样本少、过拟合 | 少参、校准/检查分离、禁特判 |
| FRED 发布滞后导致「假领先」 | 文档标明；可选 conservative shift；宁慢勿偷看 |
| 与资产池 regime 概念混淆 | 命名与 UI 文案固定为「全球系统性风险」 |
| 旧分与新状态打架 | UI 只突出新状态；旧分 drill-down |
| 继续堆指标 | 特征准入 = eval 改善，否则拒绝 |
| yfinance/FRED 不稳 | degraded 路径 + 缓存；关键序列失败可见 |

---

## 10. Open Questions

1. `anchor_date` 统一用价格极值还是「政策/流动性事件日」？建议：**主表两者都存**（`anchor_price` + `anchor_stress`），lead 分列报告。  
2. `display_score` 是否在 v1 Dashboard 展示？建议：**可隐藏**，先只展示状态枚举。  
3. A 股 L6 是否进入全局 drivers？建议：全局状态不算票，Dashboard 在 A 股区块单独标注。  
4. Phase 0 是否抽 `MacroLiquidityAnalyzer.score_from_snapshot`？建议：**值得做**，否则 legacy 回放只能近似。

---

## 11. Decision Log

| 日期 | 决策 |
|------|------|
| 2026-07-11 | 不换数据商；先状态机 + 事件验证 |
| 2026-07-11 | 主出口为离散状态，非线性风险分 |
| 2026-07-11 | 全球系统性风险与资产池 regime 正交 |
| 2026-07-11 | 黄金逻辑改为背离特征，废除「金跌=风险」作为核心 |
| 2026-07-11 | 缺数 → degraded，废除失败默认 50 |

---

## 12. References

- 吸引子 Alice / 全球美元流动性置信度设计：`2026-03-23-global-usd-liquidity-confidence-design.md`
- 领先指标与 MomentumDelta：`2026-04-12-leading-indicators-design.md`
- Decision Cockpit 痛点（signals not trustworthy / insufficient lead time）：`2026-04-12-decision-cockpit-design.md`
