# 策略设计技能

## 目标

产出一份结构化的策略假设规格，作为本轮回测的输入。

## 执行步骤

### 1. 检查上轮反馈

尝试读取 `review/reviewer/verdict.json`。

- 若文件不存在（第一次迭代）：使用 soul 中描述的默认起点假设。
- 若 `decision == "REVISE"`：根据 `feedback.improvement_suggestions` 对参数或逻辑进行有针对性调整，每次只改一个维度。
- 若 `decision == "REJECT"`：放弃当前方向，尝试不同的 sleeve 组合或 risk-on 过滤规则。

### 2. 设计本轮策略假设

明确以下要素，每项都需要有可解释的理由：

**Risk-on 过滤规则（Regime Filter）**
- 使用哪个宽基指数作为环境过滤器（沪深300、中证500等）
- 动量窗口（建议先用6个月）
- 顺风条件阈值（建议 > 0）

**Risk-on Sleeve（顺风期）**
- 资产池：A 股行业 ETF
- 动量参数：lookback（月）, skip（月）, top_k（选几只）
- 再平衡频率

**Risk-off Sleeve（逆风期）**
- 候选资产：红利低波 ETF、黄金 ETF、纳指100 ETF、债券/货币 ETF
- 动量参数：lookback, top_k
- 是否固定配置（vs 动量轮转）

### 3. 写出 ETF 代码映射

列出每个 sleeve 用到的真实 ETF 代码（或指数代理代码）以及数据起始日期。

### 4. 写入 artifact

将策略规格写入 `design/strategy_designer/strategy_spec.json`，格式如下（必须完全匹配此 JSON 结构供回测脚本解析）：

```json
{
  "iteration": 1,
  "hypothesis": "A股趋势过滤 + 行业轮动进攻 + 防守资产动量防守",
  "strategy_type": "multi_sleeve_rotation",
  "risk_on_rule": {
    "benchmark": "000300.SH",
    "lookback_months": 6,
    "min_return": 0.0
  },
  "risk_on_allocation": {
    "sleeve": "industry",
    "lookback_months": 9,
    "skip_months": 1,
    "top_k": 3,
    "min_hold_months": 1
  },
  "risk_off_allocation": {
    "sleeve": "defensive_global",
    "lookback_months": 6,
    "top_k": 1,
    "min_hold_months": 1
  },
  "change_from_prev": "initial",
  "rationale": "逆风期不再空仓或持有沪深300，而是从红利/黄金/纳指/债券中动量选1只，期望改善逆风期收益"
}
```

## 输出检查

确认 JSON 的根级别包含 `strategy_type: "multi_sleeve_rotation"`，并且 `risk_on_rule`、`risk_on_allocation`、`risk_off_allocation` 这三个字段严格存在，artifact 写入成功后本阶段完成。

