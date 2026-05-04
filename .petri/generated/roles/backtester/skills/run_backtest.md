# 回测执行技能

## 目标

按策略规格运行三种数据口径的 walk-forward 样本外回测，写入结构化结果 artifact。

## 执行步骤

### 1. 检查输入规格

确认 `design/strategy_designer/strategy_spec.json` 文件存在并且包含 `strategy_type: "multi_sleeve_rotation"` 及相应规则。

### 2. 执行统一回测脚本

已有专门的脚本 `scripts/long_rotation_discovery.py`，它会自动执行 index_proxy、real_etf_subset、real_etf_full 三种口径的回测并汇总结果。

运行：

```bash
OUTFILE=data/backtest_results/run_$(date +%Y%m%d_%H%M%S).json
python scripts/long_rotation_discovery.py \
  --mode candidate \
  --params-file design/strategy_designer/strategy_spec.json \
  --output $OUTFILE
```

记录：完整命令行字符串、exit code（`echo $?`）、`$OUTFILE` 路径。
若 exit_code != 0，必须排查修复。禁止自行修改回测脚本的核心逻辑，只能修正输入参数或运行环境。

### 3. 读取真实输出

从生成的 `$OUTFILE` JSON 中读取真实回测数值。该 JSON 会包含：
- `data_modes_validated`
- `results.index_proxy`, `results.real_etf_subset`, `results.real_etf_full`
- 每种模式内的 `candidate_oos_annual_return`, `candidate_oos_max_drawdown`, `candidate_oos_sharpe`
- `baseline_oos_annual_return`, `baseline_oos_max_drawdown` 等字段。

### 4. 写入 artifact

写入 `backtest/backtester/backtest_results.json`，格式如下：

```json
{
  "strategy_iteration": 1,
  "hypothesis": "<从 strategy_spec.json 读取>",
  "data_modes_run": 3,
  "results": {
    "index_proxy": {
      "command": "<执行的命令>",
      "exit_code": 0,
      "source_output_path": "<OUTFILE路径>",
      "data_mode": "index_proxy",
      "coverage_years": "<从文件读取>",
      "baseline_metrics": {
        "annual_return": "<baseline_oos_annual_return>",
        "max_drawdown": "<baseline_oos_max_drawdown>"
      },
      "candidate_metrics": {
        "annual_return": "<candidate_oos_annual_return>",
        "max_drawdown": "<candidate_oos_max_drawdown>",
        "sharpe": "<candidate_oos_sharpe>"
      },
      "return_improvement": "<candidate - baseline annual return>",
      "status": "success"
    },
    "real_etf_subset": {
      "command": "<同上>",
      "exit_code": 0,
      "source_output_path": "<同上>",
      "data_mode": "real_etf_subset",
      "coverage_years": "<从文件读取>",
      "baseline_metrics": { ... },
      "candidate_metrics": { ... },
      "return_improvement": "<计算值>",
      "status": "success"
    },
    "real_etf_full": {
      "command": "<同上>",
      "exit_code": 0,
      "source_output_path": "<同上>",
      "data_mode": "real_etf_full",
      "coverage_years": "<从文件读取>",
      "baseline_metrics": { ... },
      "candidate_metrics": { ... },
      "return_improvement": "<计算值>",
      "status": "success"
    }
  },
  "best_mode": "<annual_return 最高的 data_mode>",
  "notes": "如遇跳过或异常，在此说明"
}
```

## 重要约束

- 所有的指标 (`annual_return`, `max_drawdown`, `coverage_years`) 必须来源于真实脚本输出 JSON，绝对禁止凭空编造！
- index_proxy 模式必须要有 10 年以上的 coverage_years，否则需上报。
