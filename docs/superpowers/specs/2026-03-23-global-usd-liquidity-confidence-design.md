# 全球美元流动性置信度指标

## Summary

复刻"吸引子 Alice 系统 [A0007]"的全球美元流动性置信度指标。将多维美元流动性子指标通过百分位排名法合成为一个 -100% ~ +100% 的置信度值，正值表示流动性宽松趋势，负值表示收紧趋势。作为独立新页面展示。

## Motivation

现有 `MacroLiquidityAnalyzer` 输出 0-100 的风险评分，缺少两个关键特性：

1. **方向性**：风险分只有高低，没有"从紧转松"的方向判断
2. **离岸视角**：完全缺失在岸/离岸美元流动性溢价的分解

Alice 系统的置信度曲线呈现明显的周期性和预见性，是因为它用百分位排名（而非静态阈值）捕捉了流动性的相对位置和趋势变化。

## Data Sources

### 在岸美元流动性溢价（4 个子指标）

| 指标 | FRED Series | 计算方式 | 频率 |
|------|-------------|----------|------|
| 商票-美债溢价 | `DCPF3M`, `DGS3MO` | `DCPF3M - DGS3MO` | Daily |
| SOFR | `SOFR` | 直接使用 | Daily |
| EFFR-IORB 溢价 | `EFFR`, `IORB` | `EFFR - IORB` | Daily |
| SOFR-IORB 溢价 | `SOFR`, `IORB` | `SOFR - IORB` | Daily |

### 离岸/资金面压力（2 个子指标）

| 指标 | FRED Series | 说明 | 频率 |
|------|-------------|------|------|
| NFCIRISK | `NFCIRISK` | 芝加哥联储金融条件-风险子指数 | Weekly |
| STLFSI4 | `STLFSI4` | 圣路易斯联储金融压力指数 | Weekly |

**备注**：Alice 原版使用 EUR/USD 和 JPY/USD 3M Basis Swap，但这是 Bloomberg 付费数据。NFCIRISK 和 STLFSI4 是最佳免费替代，覆盖了资金面压力和金融压力。如果将来获得 basis swap 数据源，可以无缝替换这一层。

### 净流动性基本面（3 个子指标）

| 指标 | FRED Series | 计算方式 | 频率 |
|------|-------------|----------|------|
| Fed 资产负债表 | `WALCL` | 直接使用 | Weekly |
| TGA 余额 | `WTREGEN` | 直接使用 | Weekly |
| 隔夜逆回购 | `RRPONTSYD` | 直接使用 | Daily |

净流动性 = WALCL - WTREGEN - RRPONTSYD（已有代码可复用）。

## Architecture

### 指标树结构

```
全球美元流动性置信度 (composite)
├── 在岸美元流动性溢价 (40%)  ← 最灵敏的资金面领先指标
│   ├── 商票-美债溢价 (DCPF3M - DGS3MO)
│   ├── SOFR
│   ├── EFFR-IORB 溢价
│   └── SOFR-IORB 溢价
├── 离岸/资金面压力 (30%)  ← 替代 basis swap，捕捉全球金融条件
│   ├── NFCIRISK
│   └── STLFSI4
└── 净流动性基本面 (30%)  ← 央行资产负债表驱动的慢变量
    └── Net Liquidity (WALCL - WTREGEN - RRPONTSYD)
```

### 文件结构

```
quant/analysis/indicators/
  global_usd_liquidity.py          # 核心分析器

web/pages/
  6_💧_USD_Liquidity.py            # Streamlit 页面

web/data_service.py                # 新增 get_global_usd_liquidity() 函数
```

### 与现有系统的关系

- **独立运行**：不修改 `MacroLiquidityAnalyzer`，两个系统并行
- **共享基础设施**：复用 FRED API client (`fredapi`)、`CacheManager`、Streamlit 主题
- **数据复用**：净流动性的 FRED 数据（WALCL/WTREGEN/RRPONTSYD）和 SOFR 与现有分析器有重叠，但各自独立获取和缓存，避免耦合

## Confidence Calculation

### Step 1: 获取原始数据

每个子指标获取过去 **3 年** 的历史日频/周频数据。其中 2 年用于百分位排名的滚动窗口，额外 1 年确保能生成完整的 1 年历史置信度曲线。

**频率对齐**：周频数据（NFCIRISK、STLFSI4、WALCL、WTREGEN）forward-fill 到日频后再计算百分位排名，确保所有指标在同一时间轴上。

### Step 2: 百分位排名

对每个子指标，计算当前值在过去 2 年（约 504 个交易日）中的百分位排名：

```python
from scipy.stats import percentileofscore
percentile = percentileofscore(rolling_2yr_data, current_value, kind='rank')
# 结果: 0 ~ 100，50 = 中位数
# kind='rank' 对并列值取平均排名，适合 EFFR-IORB 等离散分布的指标
```

### Step 3: 方向映射

将百分位映射到 -100% ~ +100%：

```python
confidence = (percentile - 50) * 2
# 百分位 0 → 置信度 -100%
# 百分位 50 → 置信度 0%
# 百分位 100 → 置信度 +100%
```

### Step 4: 极性处理

对"越高表示越紧"的指标取反：

| 指标 | 极性 | 逻辑 |
|------|------|------|
| 商票-美债溢价 | 反转 | 溢价越高 → 流动性越紧 → 置信度越低 |
| SOFR | 反转 | 利率越高 → 流动性越紧 |
| EFFR-IORB | 反转 | 溢价越高 → 资金越紧 |
| SOFR-IORB | 反转 | 同上 |
| NFCIRISK | 反转 | NFCI 原始约定：正值=紧于均值，负值=松于均值。反转后正置信度=宽松 |
| STLFSI4 | 反转 | STLFSI 原始约定：正值=压力高于均值。反转后正置信度=宽松 |
| Net Liquidity | 正向 | 流动性越多 → 宽松 |

反转方式：`confidence = -confidence`（即 `(50 - percentile) * 2`）

### Step 5: 层级聚合

```python
onshore_confidence = mean(商票溢价_conf, SOFR_conf, EFFR_IORB_conf, SOFR_IORB_conf)
offshore_confidence = mean(NFCIRISK_conf, STLFSI4_conf)
net_liq_confidence = net_liquidity_conf

total_confidence = (
    onshore_confidence * 0.40 +
    offshore_confidence * 0.30 +
    net_liq_confidence * 0.30
)
```

### Step 6: 时间序列

对每个交易日重复 Step 2-5，生成历史置信度曲线（过去 1 年）。

## UI Design

### 页面：`6_💧_USD_Liquidity.py`

```
┌──────────────────────────────────────────────────┐
│  💧 全球美元流动性                                │
│                                                   │
│  置信度: -58.89%  ↓ 收紧趋势                      │
│  (较上周: -12.3pp，对比 5 个交易日前)               │
│                                                   │
│  ┌───────────────────────────────────────────────┐│
│  │                                               ││
│  │  📈 置信度历史曲线 (可选 3M / 6M / 1Y)         ││
│  │  Y 轴: -100% ~ +100%                         ││
│  │  0% 水平线标注                                 ││
│  │  面积图（正值蓝色填充，负值红色填充）             ││
│  │                                               ││
│  └───────────────────────────────────────────────┘│
│                                                   │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐          │
│  │ 在岸溢价 │  │离岸/压力 │  │净流动性  │          │
│  │  -42%   │  │  -65%   │  │  -28%   │          │
│  │  (40%)  │  │  (30%)  │  │  (30%)  │          │
│  └─────────┘  └─────────┘  └─────────┘          │
│                                                   │
│  📊 子指标详情                                    │
│  ┌───────────────────────────────────────────────┐│
│  │ 在岸美元流动性溢价                             ││
│  │  商票-美债溢价:  18.57bp  百分位 82%  置信度 -64%││
│  │  SOFR:          4.30%   百分位 65%  置信度 -30%││
│  │  EFFR-IORB:     0.08%  百分位 70%  置信度 -40%││
│  │  SOFR-IORB:     0.05%  百分位 55%  置信度 -10%││
│  ├───────────────────────────────────────────────┤│
│  │ 离岸/资金面压力                                ││
│  │  NFCIRISK:     -0.12   百分位 78%  置信度 -56%││
│  │  STLFSI4:       0.85   百分位 72%  置信度 -44%││
│  ├───────────────────────────────────────────────┤│
│  │ 净流动性基本面                                  ││
│  │  Net Liquidity:  5.8T  百分位 36%  置信度 -28%││
│  └───────────────────────────────────────────────┘│
└──────────────────────────────────────────────────┘
```

### 置信度曲线样式

- **面积图**：正值区域填充蓝色（宽松），负值区域填充红色/橙色（收紧）
- **0% 基准线**：水平虚线
- **时间范围**：默认 1 年，可选 3 个月 / 6 个月 / 1 年

### 子系统卡片

每个子系统显示：
- 子系统置信度值
- 权重占比
- 趋势箭头（↑ / ↓ / →）

## Caching Strategy

复用现有 `CacheManager`：

```
Provider: 'global_usd_liquidity'
API Type: 'indicator'
Symbol: <indicator_name>
TTL: 12 hours
```

每个子指标独立缓存，`Symbol` 为指标名（如 `sofr`、`nfcirisk`）。日频数据 `expiry_hours=12`，周频数据 `expiry_hours=24`。

## Error Handling

- 每个子指标独立获取，失败不影响其他指标
- 失败的指标从置信度计算中排除，权重在**组级别**重新归一化。例如在岸 4 个子指标中 1 个失败，则该组内剩余 3 个等权平均；如果整个组全部失败，则该组的权重按比例分配给其他组（如在岸 40% 失败 → 离岸变为 30/(30+30)=50%，净流动性变为 50%）
- 缓存兜底：使用上次成功的数据
- UI 显示哪些指标使用了缓存数据或不可用

## Testing

- 单元测试：百分位计算、极性反转、权重聚合
- 集成测试：FRED API 数据获取（需要 `FRED_API_KEY`）
- 边界情况：不足 2 年历史数据时使用可用范围

## Future Enhancements

- 获得 Bloomberg 数据后，用 EUR/USD 和 JPY/USD Basis Swap 3M 替换 NFCIRISK/STLFSI4
- 添加 GFSIRLIQ 作为独立子系统
- 置信度阈值告警（如从正转负时推送通知）
