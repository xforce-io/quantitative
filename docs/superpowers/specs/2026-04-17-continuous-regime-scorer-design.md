# Continuous Regime Scorer Design

**Date**: 2026-04-17
**Pool scope**: us_stocks only (其他 pool 后续推广)
**Status**: Approved

## Problem

当前 RegimeDetector 和 RegimeValidator 中的分类器都基于投票制（每个指标投 bullish/bearish 一票，多数决定 regime）。存在三个信息损失：

1. **阈值截断**: VIX ROC +80% 和 +16% 都是一票 bearish，信号强度丢失
2. **交互效应缺失**: VIX 飙升 + 信用利差同时走扩应比单独出现严重得多，但投票制无法表达
3. **权重拍脑袋**: 技术面 weight=2、宏观 weight=1 和各阈值 (15%, 0.10, 0.15) 未经数据验证

## Approach

新建独立的 `ContinuousRegimeScorer`，与现有 `RegimeDetector` 并行运行。将所有指标归一化为连续特征，通过加权求和得到连续分数，再映射为 `RegimeState`。

- 不修改现有线上逻辑
- 输出与 `RegimeState` 完全兼容，下游无需改动
- 架构预留 ML Backend 替换点，后续引入 sklearn/xgboost 只需新增一个类

## Architecture

```
┌─────────────────────────────────────────────────┐
│              ContinuousRegimeScorer              │
│  (新模块，与 RegimeDetector 并行，不替换)          │
├─────────────────────────────────────────────────┤
│                                                  │
│  FeaturePipeline                                 │
│    raw indicators + history → 归一化特征 [-1, +1]  │
│                                                  │
│  ScoringBackend (抽象)                            │
│    ├── WeightedLinearBackend  ← 本次实现           │
│    └── MLBackend             ← 未来扩展            │
│                                                  │
│  score → tanh → [-1, +1]                         │
│  score → RegimeState (标签 + confidence)           │
└─────────────────────────────────────────────────┘
         │
         ▼
  RegimeState (与现有格式完全兼容)
         │
    ┌────┴────┐
    ▼         ▼
VerdictEngine  Dashboard UI (无需改动)
```

## FeaturePipeline

无状态模块。输入原始指标 + 历史时序，输出标准化特征向量。

### 特征列表 (us_stocks)

| 特征 | 计算方式 | 语义 |
|------|---------|------|
| `vix_level` | z-score(当前VIX, 滚动60日均值/标准差), tanh 压缩 | VIX 相对历史高低 |
| `vix_roc` | (VIX_now / VIX_20d_ago - 1), z-score + tanh | 恐慌加速度 |
| `cs_level` | z-score(信用利差, 滚动60日), tanh | 信用环境松紧 |
| `cs_change` | 20日变化量, z-score + tanh | 信用恶化/改善速度 |
| `yc_level` | z-score(2s10s, 滚动60日), tanh | 曲线形态 |
| `yc_change` | 20日变化量, z-score + tanh | 曲线变化方向 |
| `price_vs_ma200` | (price - MA200) / MA200, tanh | 趋势位置 |
| `ma50_vs_ma200` | (MA50 - MA200) / MA200, tanh | 趋势强度 |
| `rsi_norm` | (RSI - 50) / 50 | 动量方向 |

### 归一化策略

- **绝对水平类**: z-score (滚动 60 交易日均值/标准差) → tanh 压缩到 [-1, +1]
- **变化率类**: 计算变化量 → z-score → tanh
- **技术面**: 有天然范围的 (RSI 0-100) 做线性映射；比率类做 z-score + tanh
- **极端值**: z-score 超过 ±3 时 tanh 自然饱和，无需额外 clamp

### 配置

特征定义存放在 `config/regime_features.yaml`，不硬编码。包含：
- 特征名、来源指标、归一化方法、滚动窗口大小
- polarity (正值 = bullish 还是 bearish)

## ScoringBackend

### 抽象接口

```python
class ScoringBackend(ABC):
    @abstractmethod
    def score(self, features: Dict[str, float]) -> float:
        """输入归一化特征，输出 raw score"""
        ...

    def fit(self, feature_matrix: np.ndarray, forward_returns: np.ndarray) -> None:
        """用历史数据优化参数（可选，默认 no-op）"""
        pass
```

### WeightedLinearBackend (本次实现)

```
raw_score = Σ (weight_i × feature_i)
final_score = tanh(raw_score) → [-1, +1]
```

- 权重从 `config/regime_weights.json` 加载
- 支持手动设定初始权重，也支持 grid search 自动优化

### Grid Search 优化

1. 从 FeaturePipeline 构建历史特征矩阵（每个评估日一行，9 列特征）
2. 对应每行计算 forward return（复用 RegimeValidator 逻辑）
3. 搜索策略：按类别分组粗搜，再局部细搜
   - 宏观 level 类 (vix_level, cs_level, yc_level): 一组
   - 宏观 momentum 类 (vix_roc, cs_change, yc_change): 一组
   - 技术面类 (price_vs_ma200, ma50_vs_ma200, rsi_norm): 一组
   - 每组 5^3 = 125 组合，三组串行 = 375 次评估
4. 权重搜索空间：每个权重在 [-2, -1, 0, 1, 2] 中取值
5. 优化目标：最大化 hit_rate（方向正确率）
6. 最优权重写入 JSON，附带 hit_rate 和训练区间元信息

### 防过拟合

- 时间序列 split：前 70% 训练，后 30% 验证
- 报告训练集和验证集 hit_rate，差距过大则告警
- 权重搜索空间刻意保持粗粒度，避免过度拟合噪声

### 未来 MLBackend

只需实现 `score()` 调用 `model.predict_proba()` 和 `fit()` 调用 `model.fit()`，从同一个 FeaturePipeline 取特征。

## Score → RegimeState 映射

```
score ∈ (+0.2, +1.0] → "expansion"   confidence = score
score ∈ [-0.2, +0.2] → "transition"  confidence = 1 - abs(score)/0.2
score ∈ [-1.0, -0.2) → "contraction" confidence = abs(score)
```

- 阈值 ±0.2 可配置 (在 `config/regime_features.yaml` 中定义)
- confidence 直接从 score 幅度推导
- 输出 `RegimeState` 格式与现有完全一致

## 回测集成

### RegimeValidator 扩展

新增 `validate_us_stocks_continuous()` 方法，与现有三种分类器并列：

```python
def validate_us_stocks_continuous(
    self, lookback_years=2, forward_days=10,
    eval_frequency="weekly", benchmark="SPY",
    optimize_weights=False,
    weights_path=None,
) -> RegimeValidation
```

`compare_all_us_stocks()` 扩展为四路对比：level / momentum / combined / continuous。

### 输出

同样是 `RegimeValidation`，可直接与现有分类器比较 hit_rate。

## File Organization

```
quant/analysis/regime/
├── regime_detector.py          # 不动
├── regime_validator.py         # 新增 validate_us_stocks_continuous()
├── continuous_scorer.py        # 新文件：ContinuousRegimeScorer
├── feature_pipeline.py         # 新文件：FeaturePipeline
├── scoring_backend.py          # 新文件：ScoringBackend + WeightedLinearBackend
└── __init__.py                 # 导出新类

config/
├── regime_thresholds.yaml      # 不动
├── regime_features.yaml        # 新文件：特征定义 + 归一化参数
└── regime_weights.json         # 新文件：grid search 输出的最优权重

tests/unit/
├── test_feature_pipeline.py    # 归一化正确性、边界值、配置驱动
├── test_scoring_backend.py     # 线性计算正确性、权重加载
└── test_continuous_scorer.py   # 端到端 score → RegimeState 映射
```

## Testing

- `test_feature_pipeline.py`: 归一化正确性、边界值、配置驱动
- `test_scoring_backend.py`: 线性计算正确性、权重加载
- `test_continuous_scorer.py`: 端到端 score → RegimeState 映射
- 现有 `test_regime_detector.py` 不动
