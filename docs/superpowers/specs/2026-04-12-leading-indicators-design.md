# Leading Indicators: Momentum Delta Engine + 领先信号

## 目标

解决"信号迟于实际感知"问题。人类感知敏感的是**变化速度**而非绝对水平，但系统只展示状态值。本设计在现有指标上加一层变化率检测引擎，并补充 3 个可从已有数据源获取的领先指标。

## 架构

两层设计：

1. **Momentum Delta Engine** — 通用变化率计算模块，对任意时间序列输出 velocity / acceleration / z-score
2. **3 个领先指标** — VIX(Yahoo)、信用利差(FRED)、融资余额变化率(Tushare margin API)

日频运行，不需要实时数据流。

## 第一层：Momentum Delta Engine

### 模块

`quant/analysis/indicators/momentum_delta.py`

### 接口

```python
class MomentumDelta:
    """对任意时间序列计算变化率指标。"""

    @staticmethod
    def compute(series: pd.Series, velocity_window: int = 5, zscore_window: int = 60) -> dict:
        """
        Args:
            series: 时间序列（如 RSI、资金流净额、置信度分数等）
            velocity_window: 一阶导计算窗口（默认 5 日）
            zscore_window: z-score 参考窗口（默认 60 日）

        Returns:
            {
                'velocity': float,       # 5日变化率（一阶导）
                'acceleration': float,   # velocity 的变化率（二阶导）
                'zscore': float,         # velocity 相对 zscore_window 的标准差偏离
                'streak': int,           # 连续同方向变化天数（正=连续上升，负=连续下降）
                'velocity_series': pd.Series,  # 完整 velocity 序列（用于画图）
                'status': str,           # 'accelerating_up' | 'decelerating_up' | 'accelerating_down' | 'decelerating_down' | 'stable'
                'alert': str | None,     # 异动描述，zscore > 2 时生成人话
            }
        """
```

### status 判定逻辑

```
velocity > 0 且 acceleration > 0 → accelerating_up（加速上行）
velocity > 0 且 acceleration <= 0 → decelerating_up（减速上行，可能见顶）
velocity < 0 且 acceleration < 0 → accelerating_down（加速下行）
velocity < 0 且 acceleration >= 0 → decelerating_down（减速下行，可能见底）
abs(velocity) < threshold → stable（平稳）
```

### alert 生成逻辑

当 `abs(zscore) >= 2.0` 时生成人话描述：
- zscore > 2: "异常加速，偏离均值 {zscore:.1f} 个标准差"
- zscore < -2: "异常减速，偏离均值 {zscore:.1f} 个标准差"

### 应用场景

| 被分析的指标 | 输入 series | velocity 含义 |
|-------------|-------------|--------------|
| USD Liquidity confidence | 每日 confidence 值 | 流动性收紧/宽松在加速吗 |
| Macro risk score | 每日 weighted_score | 风险在升温还是降温 |
| 个股 RSI | 每日 RSI 值 | RSI 在加速上升（动能增强）还是减速 |
| 个股资金净流入 | 每日 net_flow | 资金流入在加速还是减速 |
| 个股成交量 | 每日 volume | 量能在放大还是萎缩 |

## 第二层：3 个领先指标

### 2.1 VIX 恐慌指数

- **数据源**: Yahoo Finance `^VIX`
- **获取方式**: `yfinance.download("^VIX")` — 已有 Yahoo provider
- **计算**: 取收盘价，通过 MomentumDelta 计算 velocity/acceleration
- **展示**:
  - 当前值 + 趋势箭头
  - 状态标签: <20 正常(🟢) / 20-30 偏高(🟡) / 30-40 恐慌(🟠) / >40 极度恐慌(🔴)
  - velocity 异动提示: "VIX 连续 3 日加速上行"

### 2.2 信用利差 (HY-IG Spread)

- **数据源**: FRED
  - `BAMLH0A0HYM2` — ICE BofA US High Yield Option-Adjusted Spread
  - `BAMLC0A4CBBB` — ICE BofA BBB US Corporate Bond OAS
  - 利差 = HY - BBB
- **获取方式**: 已有 FRED API 集成，直接加新 series
- **计算**: 利差值通过 MomentumDelta 计算 velocity
- **展示**:
  - 利差值 + 趋势
  - 状态: <3% 正常(🟢) / 3-5% 偏高(🟡) / 5-8% 紧缩(🟠) / >8% 危机(🔴)
  - 利差快速扩大是股市下跌的领先信号

### 2.3 融资余额变化率（A股杠杆情绪）

- **数据源**: Tushare `margin` 或 `margin_detail` API
- **获取方式**: 通过 TushareProvider 新增 `get_margin_data()` 方法
  - `pro.margin(trade_date=xxx)` 返回全市场融资融券数据
  - 关键字段: `rzye`(融资余额)、`rzmre`(融资买入额)、`rzche`(融资偿还额)
- **计算**:
  - 融资余额日变化量 = 今日 rzye - 昨日 rzye
  - 通过 MomentumDelta 计算 velocity（余额变化在加速还是减速）
- **展示**:
  - 融资余额绝对值 + 变化趋势
  - velocity 含义: 正加速=杠杆资金加速进场 / 负加速=杠杆资金加速撤退
  - 融资余额连续 5 日下降通常领先 A 股调整

## Dashboard 集成

### 宏观环境（已有，增加 velocity 标注）

现有 3 灯不变，但每个灯增加趋势箭头和 velocity：
```
美元流动性: +12.3% ⬆️加速宽松
宏观流动性: 🟡 正常 → 趋紧中
A股情绪:    🟢 看多 ⬆️加速
```

### 领先信号（新增一行）

Dashboard 在宏观环境下方新增一行 3 列：
```
VIX:     18.5 🟢 正常 →平稳
信用利差: 3.2% 🟡 偏高 ⬆️扩大中
融资余额: 1.82万亿 ⬆️连续3日增加
```

### 持仓预警（增强）

每只股票的预警信息增加 velocity 维度的触发原因：
- "RSI ⬆️加速上行（5日velocity +8.3，z-score 2.1）"
- "资金净流入 ⬆️连续5日放大"
- "成交量异动：放量加速（z-score 2.5）"

这些作为新的 reason 类型加入 `_analyze_stock_signals()` 的 reasons 列表。

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `quant/analysis/indicators/momentum_delta.py` | 通用变化率计算引擎 |
| 新建 | `quant/analysis/indicators/leading_indicators.py` | VIX + 信用利差 + 融资余额的获取与分析 |
| 新建 | `tests/test_momentum_delta.py` | MomentumDelta 单元测试 |
| 新建 | `tests/test_leading_indicators.py` | LeadingIndicators 单元测试（mock 数据源） |
| 修改 | `quant/data/implementations/tushare_provider.py` | 新增 `get_margin_data()` |
| 修改 | `web/data_service.py` | 新增 `get_leading_indicators()`, `get_momentum_delta()` |
| 修改 | `web/pages/1_📊_Dashboard.py` | 增加领先信号行 + 宏观灯 velocity 标注 + 持仓 velocity reasons |

## 不做的事情

- 不做期权数据（Tushare 没有相关 API）
- 不做实时/盘中推送（日频足够）
- 不做 Telegram 通知（后续 P0 单独做）
- 不做 VIX 期限结构（只看 VIX 当前值和变化率，够用）
- 不新增独立页面（全部集成到 Dashboard）
