# Gold Anomaly Detection — 黄金异动检测维度

## Summary

在宏观流动性分析器 (`MacroLiquidityAnalyzer`) 中新增第5个维度"黄金异动"，采用**前兆+确认**双层信号架构，实现提前预警和事后确认两级告警。

## Motivation

2026年3月黄金大跌（2周跌幅 -10%），现有 Signal Scanner 四个维度均未覆盖黄金/贵金属价格监控。回溯分析发现暴跌前6天已有明确的趋势转弱前兆（连跌3天 + 跌破MA20 + RSI跌破40），可提前预警。

## Architecture

### 定位

作为 `MacroLiquidityAnalyzer` 的第5个维度，与净流动性、SOFR、MOVE、日元套利并列。遵循现有维度的接口模式：返回 `risk_score`、`signals`、`series`。

### 权重调整

```python
DIMENSION_WEIGHTS = {
    'net_liquidity': 0.35,  # was 0.40
    'sofr': 0.20,           # was 0.25
    'move': 0.15,           # was 0.20
    'yen_carry': 0.15,      # unchanged
    'gold': 0.15,           # new
}
```

## Signal Design

### Layer 1: 前兆信号 (Early Warning, max 40 points)

捕捉趋势转弱的早期迹象，在暴跌发生前触发。

| 信号 | 数据源 | 条件 | 分数 |
|------|--------|------|------|
| 连跌天数 | Yahoo: `GC=F` | ≥ 3个交易日连续收阴 | +15 |
| 跌破MA20 | Yahoo: `GC=F` | 收盘价 < 20日均线（且前日在上方或已连续3日在下方） | +15 |
| RSI跌入弱势 | Yahoo: `GC=F` | RSI(14) < 40 | +10 |

- 三重共振（全部触发）时额外标记为 🔴 强预警
- 单独触发时为 🟠 关注

### Layer 2: 确认信号 (Confirmation, max 60 points)

确认已发生的大幅异动，提供定性判断。

| 信号 | 数据源 | 条件 | 分数 |
|------|--------|------|------|
| 金价周跌幅 | Yahoo: `GC=F` | >5%→40, >3%→25, >1%→10 | max 40 |
| 金价-美元背离 | Yahoo: `GC=F` + `DX-Y.NYB` | 金价周跌>2% 且 美元周变化<+0.5% | +10 |
| 实际利率飙升 | FRED: `DFII10` | 周升>30bp→10, >15bp→5 | max 10 |

### 总分

`risk_score = min(layer1 + layer2, 100)`

### 信号文案示例

**前兆信号：**
- `🟠 黄金连跌3天 (累计-3.4%)，趋势转弱`
- `🟠 黄金跌破20日均线 (4994 < MA20 5113)`
- `🔴 黄金三重前兆共振：连跌+破MA20+RSI弱势(38.8)，高度警惕`

**确认信号：**
- `🔴 黄金周暴跌 -8.2%（阈值 -3%）`
- `🔴 黄金-美元背离：金跌但美元未涨，非美元驱动的抛售`
- `🟠 实际利率周升18bp，压制黄金`

## Data Sources

| 数据 | 来源 | 频率 | Ticker/Series |
|------|------|------|---------------|
| 黄金期货价格 | Yahoo Finance | 日频 | `GC=F` |
| 美元指数 | Yahoo Finance | 日频 | `DX-Y.NYB` |
| 10Y TIPS实际利率 | FRED | 日频 | `DFII10` |

黄金和美元来自 Yahoo Finance（无需额外 API key），实际利率复用现有 FRED 连接。

## Implementation

### Method: `_fetch_gold_anomaly(lookback_days: int) -> Dict[str, Any]`

新增在 `MacroLiquidityAnalyzer` 中，返回格式与其他4个维度一致：

```python
{
    'current_price': float,          # 最新金价
    'weekly_change_pct': float,      # 周涨跌幅
    'consecutive_down_days': int,    # 当前连跌天数
    'ma20': float,                   # 20日均线
    'rsi': float,                    # RSI(14)
    'usd_index': float,              # 美元指数
    'usd_weekly_change_pct': float,  # 美元周变化
    'real_yield': float,             # TIPS实际利率
    'real_yield_weekly_change': float,# 实际利率周变化(bp)
    'early_warning': {               # 前兆层
        'consecutive_down': bool,
        'below_ma20': bool,
        'rsi_weak': bool,
        'triple_resonance': bool,
        'score': int,                # 0-40
    },
    'confirmation': {                # 确认层
        'weekly_drop': bool,
        'gold_usd_divergence': bool,
        'real_rate_spike': bool,
        'score': int,                # 0-60
    },
    'risk_score': int,               # 0-100
    'signals': List[str],
    'series': pd.DataFrame,          # columns: gold_price, usd_index
}
```

### Thresholds (new constants)

```python
THRESHOLDS = {
    # ... existing ...
    'gold_weekly_drop_pct': 3.0,       # 金价周跌幅预警阈值
    'gold_weekly_drop_severe_pct': 5.0, # 金价暴跌阈值
    'gold_consecutive_down_days': 3,    # 连跌天数阈值
    'gold_rsi_weak': 40,               # RSI弱势阈值
    'gold_usd_divergence_gold_drop': 2.0,  # 背离检测：金价跌幅
    'gold_usd_divergence_usd_max': 0.5,   # 背离检测：美元最大涨幅
    'real_yield_spike_bp': 30,          # 实际利率飙升阈值(bp)
    'real_yield_spike_moderate_bp': 15, # 实际利率温和上升阈值(bp)
}
```

### UI Changes in Signal Scanner

`_render_macro_liquidity_mode()` 中：

1. **顶部 metrics**: 4列 → 5列，新增黄金 (金价 + 周变化)
2. **图表布局**: 2×2 → 3行布局
   - Row 1: 净流动性 | SOFR（不变）
   - Row 2: MOVE | 日元套利（不变）
   - Row 3: 黄金价格趋势图（带MA20线） | 金价-美元双轴对比图
3. **信号列表**: 自动包含黄金维度的前兆/确认信号

### Files Changed

| File | Change |
|------|--------|
| `quant/analysis/indicators/macro_liquidity_analyzer.py` | 新增 `_fetch_gold_anomaly()`, 修改 `DIMENSION_WEIGHTS`, `THRESHOLDS`, `analyze()` |
| `web/pages/4_🔍_Signal_Scanner.py` | 扩展 `_render_macro_liquidity_mode()` UI 布局 |

共改 2 个文件，不新增文件。

## Backtesting Validation

基于2026年3月数据的预期行为：

| 日期 | 预期信号 | 风险分 |
|------|---------|-------|
| 03-12 | 无 | ~0 |
| 03-13 | 🟠 连跌3天, 🟠 跌破MA20, 🟠 RSI<40 → 🔴 三重共振 | ~40 |
| 03-16 | 前兆持续 + 🟠 周跌>3% | ~65 |
| 03-18 | 前兆持续 + 🔴 周跌>5% | ~80 |
| 03-19 | 全面触发 + 🔴 金美背离 | ~90 |
