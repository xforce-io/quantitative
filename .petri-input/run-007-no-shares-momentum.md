# run-007 — 删除 shares_momentum 因子后的清洁基线

## 背景

run-006 (commit 614f798 fund_adj 修复后) 已确立 4 因子版本的 verified_baseline，三口径数字 12.11% / 8.78% / 24.06%。

随后做的 P1e 消融测试（直接调用 `scripts/long_rotation_discovery.py` 跑 spec_with_shares_momentum_weight=0）显示该因子是装饰性的：

| 口径 | run-006 (4 因子) | 消融 (3 因子) | Δ |
|---|---|---|---|
| index_proxy | 12.11% | 12.11% | 0.00pp |
| real_etf_subset | 8.78% | 9.74% | **+0.96pp** |
| real_etf_full | 24.06% | 23.64% | -0.42pp |

三口径都在 1pp 噪声内，real_etf_subset 甚至略有改善。

## 本轮目标

**正式删除 shares_momentum 因子**，建立 3 因子版本作为生产基线。两个动机：

1. **去除运维依赖** — shares_momentum 用 Tushare `fund_share` 数据，T+1~T+3 延迟，月末决策时可能拿不到当月最新值。删除后实盘月末决策不再依赖该数据源。
2. **消融已证实** — 见上表，因子已被实测为装饰性，删除后 alpha 不损失。

## 策略 spec

完整 spec 见 `.petri-input/run-007/strategy_spec.json`，关键变化：

- `risk_on_allocation.multi_factor_config.factors` 从 4 个减至 3 个：
  - momentum (weight=0.40)
  - low_volatility (weight=0.32)
  - relative_strength (weight=0.18)
  - ~~shares_momentum (weight=0.10)~~  ← 删除
- 总权重和现为 0.90，MultiFactorRanker 内部 `composite[s] / total_weight` 会自动归一，等效于按比例放大其他三因子 (≈ 0.444 / 0.356 / 0.200)

其他全部不变（risk_off allocation、regime filter、CB、universe 等）。

## 验收

- 三口径数字与 P1e 消融结果一致（±0.5pp 容忍）
- 全部 gate 项通过
- reviewer 在 `transferability_assessment` 中明确说明：3 因子版本的 production-readiness

## 后续动作（reviewer 不需要做，仅作记录）

- 若 gate 通过且三口径与 P1e 一致，将 `history.json` 的 `_determinism_fix.verified_baseline_run` 更新为 run-007
- 后续 live trading advisor (`scripts/live_advisor.py`) 默认指向 `.petri-input/run-007/strategy_spec.json`
