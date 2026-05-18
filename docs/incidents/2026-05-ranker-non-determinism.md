# 2026-05-18 — MultiFactorRanker 非确定性引起 index_proxy 收益波动

## 摘要

`docs/incidents/2026-05-etf-split-data-anomaly.md` 落地后启动新基线 run-001，发现 index_proxy 年化（10.92%）比 pre-cleanliness 时代 run-029（16.42%）低了 5.5pp。逐 fold 对比显示部分 fold 差 30-100pp，且差异主要集中在 2019 年之后。

为定位原因，分别用相同 spec 跑了 4 次再现实验：

| run | 编码改动 | PYTHONHASHSEED | index_proxy 年化 | real_etf_subset | real_etf_full |
|---|---|---|---|---|---|
| run-001 | 原始 | random（默认） | 10.92% | 0.22% | 17.53% |
| run-002 | 原始 | random | 12.18% | 0.22% | 17.53% |
| run-003 | 原始 | 0 | 11.72% | 0.22% | 17.53% |
| run-004 | 修复后 | random | **12.11%** | 0.22% | 17.53% |
| run-005 | 修复后 | random | **12.11%** | 0.22% | 17.53% |

real_etf_subset / real_etf_full 始终稳定，但 index_proxy 在原始代码下每次结果都不同；PYTHONHASHSEED=0 也无法消除（说明 hash 随机化不是唯一根因）。修复后 run-004 == run-005 = 12.11%，复现稳定。

## 根因（两处）

### Bug 1：`np.argsort` 默认非稳定排序

`quant/analysis/rotation/ranker.py:125` — `_cross_sectional_percentile_rank`：

```python
order = np.argsort(values)  # 默认 quicksort
```

NumPy 的 `argsort` 默认使用 quicksort，对相等值的相对位置**未定义**。当多个 ETF 因子分数相同（例如低波动因子在低波动期常出现并列），它们被分配到的 rank 顺序在不同进程间不一致。

### Bug 2：`set` 迭代顺序受 PYTHONHASHSEED 影响

`quant/analysis/rotation/ranker.py:208` — `MultiFactorRanker.rank()`：

```python
valid: set[str] = set(monthly_prices.columns)
...
composite: dict[str, float] = {s: 0.0 for s in valid}   # 插入顺序 = set 迭代顺序
filtered = {s: raw[name][s] for s in valid}
```

Python 默认 `PYTHONHASHSEED=random`，导致字符串 set 的迭代顺序每个进程不同。`composite` / `filtered` 字典的插入顺序跟着变，并通过 `_cross_sectional_percentile_rank` 的并列 tie-breaking 把这种顺序差异放大到最终选股。

## 为什么 real_etf 模式不受影响

`scripts/long_rotation_discovery.py` 的 anomaly filter（commit a9d7bad）剔除了 11/12 只数据污染 ETF，real_etf_subset 缩到 7 只、real_etf_full 缩到 27 只。**剔除的恰好是因子分数容易并列的"边缘"ETF**（这些 ETF 数据频繁错位 → 因子值在拆分前后跨数量级跳变 → 截面 rank 紧邻位置容易并列）。剩下的干净候选集中，并列出现频率低，bug 不触发。

index_proxy 用代理指数（不受 anomaly filter 影响），保留全部 37 只。2019+ 期间 shares_momentum 因子上线，使 4 因子复合分数更容易出现并列（特别是 weight=0.10 的 shares_momentum 让 0.10 量级的微小差异被 round-off 抹平），bug 触发频繁。

## 修复

`commit 23b5665 fix(rotation): remove two sources of non-determinism in MultiFactorRanker`

1. `_cross_sectional_percentile_rank` 用 `np.argsort(values, kind="stable")`
2. `MultiFactorRanker.rank()` 把 `valid` set 转 `sorted(valid_set)` 后再用于下游 dict 构造

## 影响范围

- **历史 KEEP runs（pre-cleanliness 时代 run-001 ~ run-030）的 index_proxy 数字都受影响**。这些数字本来就在每次重跑都会变，所以"年化 16.42%"等历史记录不能视为该策略的稳定基线
- 现在的 deterministic 新基线（run-005）：index_proxy 12.11%、real_etf_full 17.53%、real_etf_subset 0.22%
- 后续所有迭代必须以 run-005 为对比基准；reviewer gate 的 `regression_vs_last_keep_pp` 检查在 real_etf_full 维度上一直有效（17.53% 稳定）

## 调查证据

| 文件 | 作用 |
|---|---|
| `.petri/runs/run-001..005/` | 5 次相同 spec 的回测产出 |
| `.petri/runs/run-001/artifacts/002-backtest/backtester/backtest_results.json` 等 | 每次 fold 级 candidate_oos_annual_return 对比 |
| 本 doc 表格 | 五次 run 数字汇总 |

## 验证脚本（可重跑）

```bash
# 任意两次相同 spec 的 deterministic check
diff <(jq '.results.index_proxy.candidate_oos_annual_return' \
  data/backtest_results/run_XXXXXX.json) \
     <(jq '.results.index_proxy.candidate_oos_annual_return' \
  data/backtest_results/run_YYYYYY.json)
# 修复后应为空（数字完全一致）
```

## 时间线

- 2026-05-18 18:04 — run-001 完成，发现 index_proxy 比 pre-cleanliness 低 5.5pp
- 2026-05-18 18:37 — run-002 同 spec 重跑，发现 index_proxy 与 run-001 差 1.26pp（real_etf 完全相同）
- 2026-05-18 19:00 — P1a/P1b/P1c 侦察排除 universe / 缓存 / proxy data 变化
- 2026-05-18 19:15 — run-003 用 PYTHONHASHSEED=0 跑，仍给出第三个数字 11.72%，证明非 hash seed 唯一根因
- 2026-05-18 19:30 — 代码审查发现 `np.argsort` quicksort + `set` 迭代两处 bug
- 2026-05-18 19:50 — run-004（修复后）= 12.11%
- 2026-05-18 20:00 — run-005 复现 12.11%，确认确定性恢复
- 2026-05-18 20:10 — commit 23b5665 落地两行修复
