# Per-Dimension Caching for Macro Liquidity Analyzer

## Summary

将宏观流动性分析的缓存从"全部成功才缓存"改为"逐维度独立缓存"，使用已有的 `CacheManager` 做文件持久化。失败的维度用上次成功的缓存兜底，UI 上提供单维度重试按钮。

## Motivation

当前 `_get_macro_liquidity_cached` 使用 `st.cache_data`，任何一个维度的网络请求失败就导致整体不缓存。用户刷新页面时，之前成功加载的维度也可能因网络波动而丢失。在中国大陆访问 FRED/Yahoo Finance 不稳定，这个问题尤为突出。

## Design

### 缓存层位置

在 `web/data_service.py` 中实现，`MacroLiquidityAnalyzer` 保持纯业务逻辑不变。

### 缓存策略

复用 `quant/data/cache_manager.py` 的 `CacheManager`，以 `provider='macro_liquidity'`，`api_type='dimension'`，`symbol=<dimension_name>` 为缓存 key。

```
cache/macro_liquidity/dimension/
  <hash_net_liquidity_365>.pkl
  <hash_sofr_365>.pkl
  <hash_move_365>.pkl
  <hash_yen_carry_365>.pkl
  <hash_gold_365>.pkl
```

**TTL**: 12 小时（`expiry_hours=12`）。宏观数据日频更新，12 小时既保证当天至少刷新一次，又在网络不好时提供充足缓存窗口。

### 数据流

```
get_macro_liquidity(lookback_days):
  1. 调用 analyzer.analyze(lookback_days) 获取完整结果
  2. 遍历 result['dimensions']:
     对每个维度 (name, data):
       if data 无 error:
         cache.set(... name ..., data)        # 写入缓存
       else:
         cached = cache.get(... name ...)     # 尝试读缓存
         if cached:
           data = cached
           data['from_cache'] = True          # 标记来源
           result['dimensions'][name] = data
  3. 用修正后的 dimensions 重算:
     - dimension_scores
     - 加权 risk_score
     - 状态判定
     - 合并 signals
  4. 去掉 st.cache_data 装饰器（文件缓存替代）
  5. 返回结果
```

### 单维度重试

在 `_render_macro_liquidity_mode()` 中，对每个失败的维度（无缓存兜底）：
- 显示 `st.button("🔄 重试", key=f"retry_{dim}")`
- 点击后调用 `analyzer._fetch_<dim>(lookback_days)` 单独重新获取
- 成功则更新缓存和显示

对使用缓存兜底的维度：
- 在标题旁显示 `📦 缓存数据 (HH:MM)` 提示

### 重算逻辑

缓存替换后需要重算加权分数。从 `MacroLiquidityAnalyzer` 中提取 `DIMENSION_WEIGHTS` 和 `STATUS_MAP` 用于 data_service 中的重算，避免重复定义。

```python
from quant.analysis.indicators.macro_liquidity_analyzer import (
    DIMENSION_WEIGHTS, STATUS_MAP
)

def _recalc_risk_score(dimensions: dict) -> tuple:
    """重算加权风险分和状态"""
    dim_scores = {}
    for dim, data in dimensions.items():
        dim_scores[dim] = data.get('risk_score', 50)

    total = sum(
        dim_scores.get(dim, 50) * weight
        for dim, weight in DIMENSION_WEIGHTS.items()
    )
    total = round(total, 1)

    status_en, status_cn, status_icon = 'Normal', '正常', '🟡'
    for threshold, en, cn, icon in STATUS_MAP:
        if total >= threshold:
            status_en, status_cn, status_icon = en, cn, icon
            break

    return total, dim_scores, status_en, status_cn, status_icon
```

## Files Changed

| File | Change |
|------|--------|
| `web/data_service.py` | 重写 `get_macro_liquidity()`，去掉 `_get_macro_liquidity_cached`，加入逐维度文件缓存 + 兜底逻辑 |
| `web/pages/4_🔍_Signal_Scanner.py` | 各维度 block 中加"重试"按钮和缓存标记提示 |

共改 2 个文件。`MacroLiquidityAnalyzer` 不变。

## Edge Cases

| 场景 | 处理 |
|------|------|
| 全部维度失败 + 无任何缓存 | 返回 `{'error': ...}`（现有行为） |
| 全部维度失败 + 全有缓存 | 用缓存结果，所有维度标 `from_cache` |
| 部分失败 + 部分有缓存 | 混合：成功的用新数据，失败的用缓存 |
| 缓存数据结构变更 | pickle 反序列化失败时返回 None，等同无缓存 |
