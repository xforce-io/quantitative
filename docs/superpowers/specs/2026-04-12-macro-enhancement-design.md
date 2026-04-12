# 宏观评估增强 — 收益率曲线 + 原油/铜金比

## 目标

增强现有宏观监控体系，补充"定价锚"和"通胀预期"两个缺失维度：

1. **MacroLiquidityAnalyzer** — 新增铜金比、原油两个维度（6 维 → 8 维）
2. **LeadingIndicatorsAnalyzer** — 新增收益率曲线（2s10s 利差）作为领先信号
3. **Dashboard** — 领先信号行从 3 列扩展为 4 列
4. **缓存优化** — 宏观相关 TTL 从 1h 统一调至 4h

## 1. MacroLiquidityAnalyzer 新增维度

### 1.1 铜金比 (Copper/Gold Ratio)

**投资逻辑：** 铜 = 工业需求（经济扩张），金 = 避险需求（风险规避）。铜金比下行 = risk-off，比 VIX 更早更稳定。

**数据源：**
- 铜期货：Yahoo Finance `HG=F`（COMEX 铜期货）
- 黄金期货：Yahoo Finance `GC=F`（已有）

**计算方法：**
- `ratio = copper_close / gold_close`
- 60 日滚动百分位：`percentile = rank(ratio, window=60)`

**风险评分逻辑：**

| 百分位 | 风险分 | 含义 |
|--------|--------|------|
| < 10% | 90 | 极端 risk-off |
| < 20% | 70 | 高风险 |
| < 40% | 45 | 偏紧 |
| ≥ 40% | 15 | 正常/扩张 |

**信号触发：**
- 百分位 < 20%：`🔴 铜金比跌至近期底部（百分位 X%），risk-off 信号`
- 周跌幅 > 5%：`🟠 铜金比周跌 X%，经济预期转弱`

**方法签名：** `_fetch_copper_gold_ratio(lookback_days: int) -> Dict[str, Any]`

### 1.2 原油通胀 (Crude Oil / Inflation Proxy)

**投资逻辑：** 油价飙涨 → 通胀预期上修 → 加息预期 → 流动性收紧。原油是现有流动性框架的领先变量。

**数据源：** Yahoo Finance `CL=F`（WTI 原油期货）

**风险评分逻辑：**

| 条件 | 风险分 |
|------|--------|
| 周涨 > 10% | 85 |
| 周涨 > 5% | 60 |
| 价格 > $100 且周涨 > 0 | 50 |
| 价格 > $90 | 35 |
| 周跌 > 10%（需求崩塌信号） | 70 |
| 其他 | 15 |

注意：油价暴跌也是风险信号（需求崩塌），不是单纯的"油涨=危险"。

**信号触发：**
- 周涨 > 10%：`🔴 原油周涨 X%，通胀预期急升`
- 周涨 > 5%：`🟠 原油周涨 X%，关注通胀压力`
- 周跌 > 10%：`🟠 原油周跌 X%，需求崩塌信号`
- 价格 > $100：`🟡 油价突破 $100，持续关注`

**方法签名：** `_fetch_crude_oil(lookback_days: int) -> Dict[str, Any]`

### 1.3 权重重新分配

```python
DIMENSION_WEIGHTS = {
    'net_liquidity':   0.25,  # was 0.30
    'sofr':            0.12,  # was 0.15
    'move':            0.12,  # was 0.15
    'yen_carry':       0.08,  # was 0.10
    'gold':            0.08,  # was 0.10
    'liquidity_trend': 0.15,  # was 0.20
    'copper_gold':     0.10,  # NEW
    'crude_oil':       0.10,  # NEW
}
```

原则：核心维度（净流动性、流动性趋势）仍占最大权重，每个维度等比例缩减，腾出 20% 给新维度。

### 1.4 阈值常量

```python
THRESHOLDS.update({
    # Copper/Gold ratio
    'copper_gold_percentile_extreme': 10,
    'copper_gold_percentile_high': 20,
    'copper_gold_percentile_elevated': 40,
    'copper_gold_weekly_drop_pct': 5.0,
    # Crude oil
    'crude_weekly_surge_pct': 10.0,
    'crude_weekly_rise_pct': 5.0,
    'crude_weekly_crash_pct': 10.0,
    'crude_high_price': 100,
    'crude_elevated_price': 90,
})
```

## 2. LeadingIndicatorsAnalyzer 新增收益率曲线

### 2.1 2s10s 利差

**投资逻辑：** 收益率曲线倒挂是最强的衰退前瞻指标，历史准确率极高。

**数据源：** FRED `T10Y2Y`（10 年 - 2 年利差，直接可用，无需自行计算）

**分级：**

| 利差 | 级别 | Emoji |
|------|------|-------|
| > 0.5% | 正常 | 🟢 |
| > 0% | 趋平 | 🟡 |
| > -0.5% | 倒挂 | 🟠 |
| ≤ -0.5% | 深度倒挂 | 🔴 |

**MomentumDelta 集成：** 与 VIX 相同，计算 velocity/acceleration/zscore/streak。

**实际利率注释：** 同时读取 FRED `DFII10`，在 caption 中补充显示（如 `实际利率 2.1%`），不单独评分。

**方法签名：** `analyze_yield_curve(lookback_days: int) -> Dict[str, Any]`

**返回结构：**
```python
{
    "spread": 0.12,          # 当前 2s10s 利差
    "level": "flattening",   # normal / flattening / inverted / deeply_inverted
    "level_cn": "趋平",
    "emoji": "🟡",
    "real_yield": 2.1,       # 10Y TIPS 实际利率
    "delta": {               # MomentumDelta 输出
        "velocity": -0.02,
        "acceleration": -0.01,
        "zscore": -1.2,
        "streak": -5,
        "status": "accelerating_down",
        "status_cn": "加速下行",
        "alert": None,
    },
}
```

## 3. Dashboard 展示

### 领先信号行：3 列 → 4 列

```python
col1, col2, col3, col4 = st.columns(4)
```

| 列 | 指标 | 展示 |
|----|------|------|
| col1 | VIX 恐慌指数 | 不变 |
| col2 | 信用利差 HY-IG | 不变 |
| col3 | **收益率曲线 2s10s** | `🟡 +0.12%` + `↘️ 趋平` + caption `实际利率 2.1%` |
| col4 | 融资余额 | 不变 |

## 4. 缓存优化

`data_service.py` 中宏观相关函数 TTL 调整：

| 函数 | 当前 | 调整为 |
|------|------|--------|
| `get_global_usd_liquidity()` | 3600s (1h) | **14400s (4h)** |
| `get_macro_liquidity()` | 3600s (1h) | **14400s (4h)** |
| `get_leading_indicators()` | 3600s (1h) | **14400s (4h)** |

理由：宏观数据（FRED/Yahoo）基本日频更新，4h 在"减少重复拉取"和"盘中可刷新"之间取平衡。

## 5. 改动文件清单

| 文件 | 改动 |
|------|------|
| `quant/analysis/indicators/macro_liquidity_analyzer.py` | 新增 `_fetch_copper_gold_ratio()`, `_fetch_crude_oil()`；更新 `DIMENSION_WEIGHTS`, `THRESHOLDS`；`analyze()` 增加维度 7、8 |
| `quant/analysis/indicators/leading_indicators.py` | 新增 `analyze_yield_curve()` |
| `web/pages/1_📊_Dashboard.py` | `_render_leading_signals()` 从 3 列改 4 列，新增收益率曲线渲染 |
| `web/data_service.py` | 缓存 TTL 3600 → 14400（3 个函数）；`get_leading_indicators()` 透传新字段 |

## 6. 不做的事

- 不加农产品/天然气（噪音大，与股票定价关系弱）
- 不加 Put/Call Ratio（VIX 已覆盖恐慌维度）
- 不加 Bitcoin（纳斯达克杠杆版，信息增量有限）
- 不新建数据 provider（直接在分析器中调 Yahoo/FRED，沿用现有模式）
- 不做期货独立看板（本次聚焦嵌入现有框架）
