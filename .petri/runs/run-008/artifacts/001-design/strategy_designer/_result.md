策略 spec 已写入 `strategy_spec.json`。

**本轮设计摘要（run-007）**

| 维度 | 变化 |
|---|---|
| **核心变更** | 4 因子 → 3 因子：删除 `shares_momentum (weight=0.10)` |
| **保留因子** | momentum(0.40) + low_volatility(0.32) + relative_strength(0.18)，总和 0.90，MultiFactorRanker 内部自动归一 |
| **Risk-on 规则** | 不变：沪深300 6个月收益 > 0 |
| **Risk-on Sleeve** | 不变：行业 ETF 动量轮动，lookback=6, skip=1, top_k=3 |
| **Risk-off Sleeve** | 不变：4候选防守资产动量 top_k=1，含 floor 规则 + 熔断器 |

**删除动机（双重）**
1. **运维依赖**：`fund_share` 数据 T+1~T+3 延迟，月末决策存在数据获取风险
2. **消融已证实**：P1e 测试三口径均在 1pp 内，`real_etf_subset` 甚至略有改善（+0.96pp）

**验收目标**：三口径与 P1e 消融结果一致（±0.5pp 容忍），index_proxy ≈ 12.11%，real_etf_subset ≈ 9.74%，real_etf_full ≈ 23.64%，全部 gate 通过。