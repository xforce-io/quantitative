回测完成。以下是 run-007 完整结果：

---

## run-007 回测结果汇总

**exit_code: 0 | gate_failures: []**

| 口径 | coverage | 候选年化 | 候选 MDD | 候选 Sharpe | 基线年化 | 超额 |
|---|---|---|---|---|---|---|
| index_proxy | 16.0yr / 28折 | **12.11%** | -19.89% | 0.22 | 6.86% | +5.25pp |
| real_etf_subset | 10.0yr / 16折 | **9.74%** | -18.74% | 0.16 | 5.09% | +4.65pp |
| real_etf_full | 8.0yr / 12折 | **23.64%** | -10.52% | 0.45 | 10.56% | +13.08pp |

### 验收检查（全部通过）

- ✅ index_proxy = 12.11%（与 run-006 完全一致）
- ✅ real_etf_subset = 9.74%（P1e 消融预测 9.74%，偏差 0.00pp）
- ✅ real_etf_full = 23.64%（P1e 消融预测 23.64%，偏差 0.00pp）
- ✅ index_proxy 覆盖 16.0yr ≥ 10yr
- ✅ 所有口径 MDD > −25%（floor 通过）
- ✅ 最佳口径年化 23.64% ≥ 12%（floor 通过）

三口径数字与 P1e 消融结果精确吻合，shares_momentum 删除后 alpha 无损失，run-007 3 因子版本可确认为生产基线。原始回测数据保存于 `data/backtest_results/run_20260518_233409.json`。