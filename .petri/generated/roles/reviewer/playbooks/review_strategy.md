# 策略评审技能

## 目标

基于真实回测数据，对本轮策略做出 KEEP / REVISE / REJECT 决定，输出结构化评审报告，驱动下一轮迭代方向。

## 执行步骤

### 1. 读取回测结果

你运行时的当前目录是 `.petri/artifacts/review/reviewer/`。

读取 `../../backtest/backtester/backtest_results.json`，记录：
- 各数据口径的 candidate_metrics、baseline_metrics、return_improvement
- 每种模式的 coverage_years 和 status
- data_modes_run 数量

同时读取 `../../design/strategy_designer/strategy_spec.json` 了解本轮假设。

**读取历史 KEEP 记录（用于计算实盘口径不退步）**：

从仓库根目录读取 `experiments/history.json`，找到最近一条 `decision == "KEEP"` 的记录（按 `started_at` 倒序，跳过当前 run），取出：
- `last_keep_run_id`
- `last_keep_real_etf_full_annual_return`

若 history.json 为空或没有任何 KEEP 记录（首轮基线），将 `last_keep_real_etf_full_annual_return` 视为 None。

**关于 `_cleanliness_boundary` 字段**：history.json 顶层可能有 `_cleanliness_boundary` 元数据（记录数据质量边界、上一次清零原因）。该字段不参与查找，直接忽略；如果存在该字段且 `experiments` 数组为空，按"首轮基线"处理。新增 experiment 条目时**保留**该字段不动。

### 2. 计算汇总指标

**long_proxy_coverage_years**：`results.index_proxy.coverage_years`；若 status != "success" 则为 0。

**best_oos_annual_return**：所有 status == "success" 的模式中，candidate_metrics.annual_return 的最大值。

**best_oos_max_drawdown**：所有 status == "success" 的模式中，candidate_metrics.max_drawdown 的最大值（注意：-0.15 > -0.25，取最大值即最浅回撤）。

**return_improvement_vs_baseline**：同口径比较，优先使用 index_proxy 的 return_improvement；若 index_proxy 失败则取成功模式中最大的 improvement。

**real_etf_modes_validated_count**：统计 real_etf_subset 和 real_etf_full 中，candidate_metrics.annual_return > baseline_metrics.annual_return 的数量。

**regression_vs_last_keep_pp（real_etf_full 实盘口径退步检查）**：
- 若 `last_keep_real_etf_full_annual_return` is None（首轮）→ 填 `0.0`
- 若 real_etf_full.status != "success" → 填 `-99.0`（强制 fail，触发 REVISE 补跑缺失口径）
- 否则 → `(real_etf_full.candidate_annual_return - last_keep_real_etf_full_annual_return) * 100`
- 例：当前 12.76%、上一 KEEP 14.45% → `(0.1276 - 0.1445) * 100 = -1.69`

### 3. 评审决策逻辑

**直接 REJECT（任一条触发）：**
- best_oos_max_drawdown < -0.20（超过硬护栏）
- index_proxy 或 real_etf_full 任一 status==success 的 candidate_mdd < -0.25（核心口径 MDD 硬底线）
- real_etf_subset 暂不参与 REJECT 硬护栏（pre-existing 2021 单折异常待 P0-2 修复），但若其 MDD < -0.25 必须在 weaknesses 中显式列出且 next_iteration_direction 必须包含"调查 real_etf_subset 异常折"
- results.index_proxy.status != "success"（index_proxy 回测失败）
- long_proxy_coverage_years < 5（覆盖太短，无意义）

**KEEP（全部满足）：**
- best_oos_annual_return >= 0.12
- best_oos_max_drawdown >= -0.20
- return_improvement_vs_baseline >= 0.01
- long_proxy_coverage_years >= 10
- real_etf_modes_validated_count >= 1
- **regression_vs_last_keep_pp >= -0.5（实盘口径不退步，首轮 prior KEEP 缺失时此条空过）**
- 无严重代理/真实 ETF 结果分歧（代理 annual_return 与真实 ETF 差距不超过 5 个百分点）

**REVISE（其余情况）：**
- 必须给出具体且可操作的改进建议

### 4. 写入 artifact

写入当前目录下的 `verdict.json`：

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
    "execution_audit_passed": true,
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
        "status": "success|failed|skipped",
        "last_keep_run_id": "run-XXX|null",
        "last_keep_annual_return": 0.0,
        "regression_vs_last_keep_pp": 0.0
      }
    }
  },
  "meets_all_criteria": {
    "annual_return_gte_12pct": false,
    "mdd_gte_neg20pct": false,
    "return_improvement_gte_1pct": false,
    "coverage_gte_10years": false,
    "real_etf_validated": false,
    "real_etf_full_no_regression": false
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
- 对于 status != "success" 的模式，candidate_mdd 必须填 `0.0`（而不是 -0.99），以使全口径 MDD 硬护栏 gate 检查能空过，避免缺失数据误判为违规
- real_etf_full 的 `last_keep_run_id` / `last_keep_annual_return` / `regression_vs_last_keep_pp` 三字段必须填齐；首轮（history.json 无 KEEP 记录）填 `null / 0.0 / 0.0`

### 5. 更新 experiments/history.json

无论 decision 结果如何，本轮评审完成后**必须**追加一条记录到仓库根目录的 `experiments/history.json`：

```json
{
  "experiments": [
    {
      "run_id": "run-030",
      "started_at": "2026-05-18T03:15:07.832Z",
      "decision": "KEEP",
      "hypothesis": "<本轮假设一句话>",
      "index_proxy_annual_return": 0.1689,
      "index_proxy_mdd": -0.1989,
      "real_etf_full_annual_return": 0.1276,
      "real_etf_full_mdd": -0.0958,
      "real_etf_subset_annual_return": 0.0516,
      "real_etf_subset_mdd": -0.4872,
      "long_proxy_coverage_years": 16.0
    }
  ],
  "total_experiments": 1
}
```

- 读现有 `experiments/history.json`，append 新条目，更新 `total_experiments` 计数
- 若某 mode status != "success"，对应字段填 `null`
- `run_id` 从当前工作目录路径推断（`.petri/runs/run-XXX/...`）
