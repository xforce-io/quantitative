# 策略评审技能

## 目标

基于真实回测数据，对本轮策略做出 KEEP / REVISE / REJECT 决定，输出结构化评审报告，驱动下一轮迭代方向。

## 执行步骤

### 1. 读取回测结果

读取 `backtest/backtester/backtest_results.json`，记录：
- 各数据口径的 candidate_metrics、baseline_metrics、return_improvement
- 每种模式的 coverage_years 和 status
- data_modes_run 数量

同时读取 `design/strategy_designer/strategy_spec.json` 了解本轮假设。

### 2. 计算汇总指标

**long_proxy_coverage_years**：`results.index_proxy.coverage_years`；若 status != "success" 则为 0。

**best_oos_annual_return**：所有 status == "success" 的模式中，candidate_metrics.annual_return 的最大值。

**best_oos_max_drawdown**：所有 status == "success" 的模式中，candidate_metrics.max_drawdown 的最大值（注意：-0.15 > -0.25，取最大值即最浅回撤）。

**return_improvement_vs_baseline**：同口径比较，优先使用 index_proxy 的 return_improvement；若 index_proxy 失败则取成功模式中最大的 improvement。

**real_etf_modes_validated_count**：统计 real_etf_subset 和 real_etf_full 中，candidate_metrics.annual_return > baseline_metrics.annual_return 的数量。

### 3. 评审决策逻辑

**直接 REJECT（任一条触发）：**
- best_oos_max_drawdown < -0.20（超过硬护栏）
- results.index_proxy.status != "success"（index_proxy 回测失败）
- long_proxy_coverage_years < 5（覆盖太短，无意义）

**KEEP（全部满足）：**
- best_oos_annual_return >= 0.12
- best_oos_max_drawdown >= -0.20
- return_improvement_vs_baseline >= 0.01
- long_proxy_coverage_years >= 10
- real_etf_modes_validated_count >= 1
- 无严重代理/真实 ETF 结果分歧（代理 annual_return 与真实 ETF 差距不超过 5 个百分点）

**REVISE（其余情况）：**
- 必须给出具体且可操作的改进建议

### 4. 写入 artifact

写入 `review/reviewer/verdict.json`：

```json
{
  "decision": "KEEP|REVISE|REJECT",
  "approved": false,
  "strategy_summary": {
    "hypothesis": "<本轮假设>",
    "regime_filter": {},
    "risk_on_sleeve": {},
    "risk_off_sleeve": {}
  },
  "results": {
    "long_proxy_coverage_years": 0,
    "best_oos_annual_return": 0.0,
    "best_oos_max_drawdown": -0.99,
    "return_improvement_vs_baseline": 0.0,
    "real_etf_modes_validated_count": 0,
    "per_mode_comparison": {
      "index_proxy": {
        "candidate_annual_return": 0.0,
        "baseline_annual_return": 0.0,
        "candidate_mdd": -0.99,
        "baseline_mdd": -0.99,
        "coverage_years": 0,
        "return_improvement": 0.0,
        "status": "success|failed|skipped"
      },
      "real_etf_subset": {
        "candidate_annual_return": 0.0,
        "baseline_annual_return": 0.0,
        "candidate_mdd": -0.99,
        "baseline_mdd": -0.99,
        "coverage_years": 0,
        "return_improvement": 0.0,
        "status": "success|failed|skipped"
      },
      "real_etf_full": {
        "candidate_annual_return": 0.0,
        "baseline_annual_return": 0.0,
        "candidate_mdd": -0.99,
        "baseline_mdd": -0.99,
        "coverage_years": 0,
        "return_improvement": 0.0,
        "status": "success|failed|skipped"
      }
    }
  },
  "meets_all_criteria": {
    "annual_return_gte_12pct": false,
    "mdd_gte_neg20pct": false,
    "return_improvement_gte_1pct": false,
    "coverage_gte_10years": false,
    "real_etf_validated": false
  },
  "transferability_assessment": "<可迁移性评估：代理与真实 ETF 结果是否一致，潜在风险点>",
  "feedback": {
    "strengths": [],
    "weaknesses": [],
    "improvement_suggestions": []
  },
  "next_iteration_direction": "<若 REVISE/REJECT，给出下一轮的明确方向和建议参数>"
}
```

## 关键约束

- `approved: true` 当且仅当 `decision == "KEEP"` 且所有 meets_all_criteria 均为 true
- results.* 所有数值必须来自回测 artifact，禁止自行估算
- REVISE 或 REJECT 时，improvement_suggestions 不能为空列表
- 若 data_modes_run < 3，在 weaknesses 中注明并在 improvement_suggestions 中要求下轮补全
- per_mode_comparison 必须填写所有 status == "success" 的模式的完整字段
