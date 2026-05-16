# Pre-Live Execution Guards Design

**Date:** 2026-05-16  
**Status:** Approved  
**Context:** run-019 审计通过，上线前两项必做项

---

## 背景

run-019（实盘可执行性审计）结论为 KEEP_WITH_WARNINGS，要求上线前完成两项：

1. **成交量过滤器**：在 rotation ranker 打分前动态过滤低流动性 ETF，防止持仓无法成交
2. **QDII 溢价守卫**：调仓日 T-1 检查 513100.SH（纳指ETF）溢价，超阈值自动替换为 511880.SH（短债）

---

## 方案选型

- Volume filter：动态计算（trailing 3M 月均量），阈值在 universe YAML 配置
- Precheck：独立 CLI 命令 `quant rotation precheck`，不修改 `latest` 逻辑
- 不引入 PreTradeCheckService 抽象层（当前只有两项检查，过度设计）

---

## 设计一：成交量过滤器

### 改动文件

- `config/rotation_universe.yaml` — 新增全局 + per-ETF 阈值字段
- `quant/analysis/rotation/ranker.py` — `rank()` 入口前插入过滤逻辑

### rotation_universe.yaml 新增结构

```yaml
schema_version: 2
volume_filter:
  enabled: true
  min_avg_monthly_volume_shares: 1000000   # 全局默认，trailing 3M 月均量
  lookback_months: 3

industry_etfs:
  - symbol: "159930.SZ"
    name: "能源ETF"
    category: "周期"
    min_avg_monthly_volume_shares: 1000000  # 可选，覆盖全局默认
```

`defensive_global_etfs` 和 `style_etfs` 不做成交量过滤（均为流动性充足的核心标的）。过滤逻辑只对 `industry_etfs` 分类下的 symbol 生效；其余分类的 symbol 直接通过。

### Ranker 改动

在 `MomentumRanker.rank()` 和 `MultiFactorRanker.rank()` 最开头调用 `_apply_volume_filter()`：

```python
def _apply_volume_filter(
    self,
    universe_prices: pd.DataFrame,   # index=date, columns=symbols, values=close
    monthly_volumes: pd.DataFrame,    # index=date, columns=symbols, values=volume
    rebalance_date: pd.Timestamp,
    universe_config: dict,
) -> list[str]:
    """Return symbols passing trailing-3M average monthly volume threshold."""
    filter_cfg = universe_config.get("volume_filter", {})
    if not filter_cfg.get("enabled", False):
        return list(universe_prices.columns)

    lookback = filter_cfg.get("lookback_months", 3)
    global_threshold = filter_cfg.get("min_avg_monthly_volume_shares", 1_000_000)
    per_etf_thresholds = {e["symbol"]: e.get("min_avg_monthly_volume_shares", global_threshold)
                          for e in universe_config.get("industry_etfs", [])}

    cutoff = rebalance_date - pd.DateOffset(months=lookback)
    window = monthly_volumes.loc[cutoff:rebalance_date]

    passed, filtered = [], []
    for sym in universe_prices.columns:
        threshold = per_etf_thresholds.get(sym, global_threshold)
        avg_vol = window[sym].mean() if sym in window.columns else 0
        if avg_vol >= threshold:
            passed.append(sym)
        else:
            filtered.append((sym, avg_vol, threshold))

    if filtered:
        for sym, vol, thr in filtered:
            logger.warning(f"Volume filter: {sym} excluded (avg {vol:,.0f} < {thr:,.0f} shares/month)")

    return passed
```

### 数据来源

`monthly_volumes` 从 `DataService.get_price()` 的日成交量（volume 列）按月求和得到月度总成交量（单位：股）。RotationService 在调用 `ranker.rank()` 前预拉 volume，和 price 数据同步获取，避免 ranker 内部依赖 DataService（保持 ranker 可测试性）。

**选择：** RotationService 在调用 `ranker.rank()` 前预拉 volume，和 price 数据同步获取，避免 ranker 内部依赖 DataService（保持 ranker 可测试性）。

### 回测兼容性

过滤器在回测中同样生效——历史上某月该 ETF 成交量不足，该月即排除，不影响后续月份。确保回测结果与实盘行为一致。

---

## 设计二：`quant rotation precheck` 命令

### 触发场景

月度调仓日 T-1，手动运行。输入为 `latest` 给出的目标仓位，输出为调整后的最终建议仓位。

### 命令接口

```bash
# 方式一：直接传仓位
python -m quant rotation precheck --targets "513100.SH:0.33,511880.SH:0.33,512800.SH:0.34"

# 方式二：从 latest 输出读取
# latest 命令在运行时同时写入 .quant_cache/latest_targets.json
python -m quant rotation precheck --from-latest
```

### 检查项

| 检查项 | 数据 | 触发条件 | 行为 |
|--------|------|---------|------|
| 513100.SH 溢价 vs IOPV | Tushare 实时行情 | >1% | WARN，建议延迟买入 |
| 513100.SH 溢价 vs IOPV | Tushare 实时行情 | >2% | ERROR，替换为 511880.SH |
| 跨 ETF 比价（vs 159941.SZ） | Tushare 实时行情 | 价差 >1% | WARN，建议等待收窄 |
| risk_off sleeve 仓位上限 | 组合权重计算 | 513100.SH >50% of risk_off | 自动拆分，超出部分给 511880.SH |
| QDII 额度（申购状态） | Tushare fund_share 或 fund_nav | 连续 3 日申购暂停 | ERROR，替换为 511880.SH |

### 输出格式

```
=== Pre-Trade Check: 2026-05-30 ===

[OK]   513100.SH 溢价: +0.3%（阈值 >1% 警告，>2% 替换）
[WARN] 159941.SZ 价差: 1.2%（超 1%，建议等价差收窄后买入）
[OK]   仓位上限: 513100.SH 33% of risk_off sleeve（≤50%）
[OK]   QDII 额度：申购正常

调整后建议仓位：
  513100.SH  33%  ← 建议等价差收窄
  511880.SH  33%
  512800.SH  34%

注意：存在 WARN 项，请确认后再下单。
```

### 实现位置

- `quant/cli/rotation.py` — 新增 `precheck` 子命令
- `quant/analysis/rotation/precheck.py` — 检查逻辑（新文件）
  - `PreTradeChecker` 类，方法：`run(targets: dict) -> PreCheckResult`
  - `PreCheckResult`：包含每项检查状态、调整后仓位、是否有阻塞项

### IOPV 数据说明

Tushare `fund_nav` 接口返回 T-1 日 IOPV，非实时。若需盘中实时 IOPV，需使用交易所数据（暂不引入新数据源）。

**短期方案**：用 T-1 日 IOPV + 当日开盘价估算溢价，足以捕捉显著溢价（>2% 阈值）。后续可升级为实时数据源。

---

## 不在本期范围内

- FX 信号（USD/CNY 升值率折价）— 数据依赖复杂，可选项，上线后评估
- real_etf_subset 口径补充验证（2010-2018）— 独立 run，非执行系统改动
- 定时任务 / 自动触发 — 当前保持手动 CLI

---

## 文件改动清单

| 文件 | 类型 |
|------|------|
| `config/rotation_universe.yaml` | 修改：新增 `volume_filter` 块，`schema_version: 2` |
| `quant/analysis/rotation/ranker.py` | 修改：`_apply_volume_filter()` + `rank()` 调用 |
| `quant/services/rotation_service.py` | 修改：拉取 volume 数据，传给 ranker |
| `quant/analysis/rotation/precheck.py` | 新建：`PreTradeChecker`，`PreCheckResult` |
| `quant/cli/rotation.py` | 修改：新增 `precheck` 子命令 |
| `tests/rotation/test_volume_filter.py` | 新建：volume filter 单元测试 |
| `tests/rotation/test_precheck.py` | 新建：precheck 逻辑单元测试 |
