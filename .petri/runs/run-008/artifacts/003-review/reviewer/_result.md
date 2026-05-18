---

## 评审结论：KEEP ✅

### 决策依据

| 检查项 | 要求 | 实测 | 结果 |
|--------|------|------|------|
| 长期年化收益 | ≥ 12% | **23.64%** (real_etf_full) | ✅ |
| 最大回撤 | ≥ −20% | **−18.74%** (worst across modes) | ✅ |
| 相对 baseline 提升 | ≥ 1pp | **+5.25pp** (index_proxy) | ✅ |
| OOS 覆盖年数 | ≥ 10 年 | **16.0 年** (index_proxy) | ✅ |
| 真实 ETF 验证 | ≥ 1 种 | **2 种**（subset +4.65pp, full +13.08pp） | ✅ |
| 实盘口径不退步 | ≥ −0.5pp vs run-006 | **−0.42pp** (23.64% vs 24.06%) | ✅ |

### 可迁移性评估摘要

3 因子版本**生产就绪**。index_proxy（12.11%，16yr）与 real_etf_subset（9.74%，10yr）仅差 2.37pp，信号有效传导。real_etf_full（23.64%）与代理口径差距 11.53pp 主要由样本区间差异驱动（非过拟合），与 run-006 格局一致。删除 `shares_momentum` 后消除了 T+1~T+3 数据延迟风险，月末实盘决策可完全依赖当月收盘数据。

### 关注点（不影响 KEEP）

- **real_etf_subset MDD -18.74%**：相比同口径 baseline（-9.55%）扩大明显，实盘中需持续监控
- **index_proxy Sharpe 0.22**：盈利质量偏低，后续迭代可从 risk_off 候选池优化入手

### 已更新文件
- `verdict.json` → `approved: true`
- `experiments/history.json` → 追加 run-007（total_experiments: 7）