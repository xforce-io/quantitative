# 配置纪律辅助工具 (Allocation Monitor) - 设计文档

**日期**：2026-04-19
**作者**：xupeng（与 Claude 协作）
**依赖文档**：`docs/superpowers/specs/2026-04-19-portfolio-reallocation-design.md`（投资策略文档）
**范围**：Level 2 决策助手
**预期工作量**：约 1 周（分 4 个子模块，可独立交付）

---

## 1. 目标

让"方案 2"配置方案的**纪律执行自动化**。不做预测、不做择时、不做个股推荐。

### 1.1 核心哲学

- **代码是纪律工具，不是预测工具** —— 战略由人定（方案 2 权重表），代码负责让执行不走样
- **规则优于判断** —— QDII 溢价、再平衡阈值、资金分配都走硬规则
- **黑屏也能用** —— 输出是 markdown / 表格，不依赖 UI。等功能稳定后再考虑接入 Dashboard

### 1.2 覆盖的决策场景

| 场景 | 功能 | 频率 |
|---|---|---|
| "现在配置偏离目标多少？" | ① 权重监控 | 每日/每周打开一次 |
| "想买 X 现在能买吗？" | ② QDII 溢价雷达 | 买入前查一次 |
| "新增资金投哪？" | ③ 资金分配器 | 每次有新钱时 |
| "季末要不要动仓位？" | ④ 季度 review | 每季度一次 |

---

## 2. 范围

### 2.1 包含

- 4 个核心功能（权重监控 / QDII 溢价 / 资金分配 / 季度 review）
- CLI 命令行入口（`quant portfolio ...`）
- 基于 YAML 的配置（目标权重 + 当前持仓）
- Tushare 数据集成（ETF 价格 + 净值）
- 纯文本 / markdown 输出

### 2.2 不包含（YAGNI）

- ❌ Web UI / Dashboard 集成（等 Level 3 / 后续独立项目）
- ❌ 券商 API 直连（持仓手工维护即可，绝大多数情况足够）
- ❌ 价格预测 / 择时信号
- ❌ 个股级别分析
- ❌ 历史归因图表 / 年度战略 review（Level 3）
- ❌ 实时推送 / 告警（季度频率足够）

---

## 3. 架构

### 3.1 模块布局

新建子包：`quant/portfolio/allocation_monitor/`

```
allocation_monitor/
├── __init__.py
├── config_loader.py      # 读取目标权重 YAML + 持仓 YAML
├── weight_monitor.py     # ① 权重偏离计算
├── qdii_premium.py       # ② QDII 溢价计算（tushare 取价 + 净值）
├── allocator.py          # ③ 新增资金分配算法
├── quarterly_review.py   # ④ 季度 review 报告生成
└── cli.py                # CLI 入口
```

### 3.2 复用现有代码

| 现有模块 | 复用方式 |
|---|---|
| `quant/portfolio/rebalancer.py::Rebalancer` | 季度 review 的买卖清单计算 |
| `quant/portfolio/portfolio_analyzer.py::PortfolioAnalyzer` | 季度 review 的收益/波动指标 |
| `quant/data_providers/data_provider.py` | Tushare 数据拉取 |

**不重写任何已有逻辑**。`Rebalancer.calculate(current, target)` 返回的 `RebalanceResult` 直接作为季度 review 报告的核心。

### 3.3 数据流

```
holdings.yaml ─┐
               ├─→ weight_monitor ─→ drift table
target.yaml ───┤                            │
               │                            ▼
tushare ───────┼─→ qdii_premium ─→ premium table
               │                            │
               ├─→ allocator (combines drift + premium + new_money) ─→ buy list
               │
               └─→ quarterly_review (combines all + returns) ─→ markdown report
```

---

## 4. 数据契约

### 4.1 目标权重（`config/allocation_target.yaml`）

```yaml
# 来源：docs/superpowers/specs/2026-04-19-portfolio-reallocation-design.md §3.1
version: "2026-04-19"
total_must_equal: 1.0

categories:
  纳指100:
    weight: 0.25
    instruments: [513100, 159941]    # 二选一，优先溢价低的
    prefer_premium_below: 0.03

  标普500:
    weight: 0.10
    instruments: [513500]

  恒生科技:
    weight: 0.10
    instruments: [03033.HK]          # 港股通直买

  A股科技成长:
    weight: 0.15
    instruments: [159915, 588000, 512480]   # 按权重分配或等权

  A股红利现金流:
    weight: 0.15
    instruments: [512890, 563020]

  黄金黄金股:
    weight: 0.15
    instruments: [518880, 517520]

  现金:
    weight: 0.10
    instruments: [CASH]              # 特殊值，不走 tushare

rebalance:
  threshold: 0.05          # §5.2：偏离 ±5% 才动
  premium_rules:            # §5.1：QDII 溢价规则
    normal: 0.03
    reduced: 0.05
    switch: 0.10
```

### 4.2 当前持仓（`config/allocation_holdings.yaml`）

用户手工维护。格式简单：

```yaml
as_of: "2026-04-19"
total_value_cny: 1000000    # 可选；不填则按持仓自动算

holdings:
  - code: 513100
    shares: 10000
    cost_basis: 1.25         # 可选，用于季度归因
  - code: 159941
    shares: 8000
  - code: 03033.HK
    shares: 2000
    currency: HKD            # 港股通需标注
  - code: CASH
    amount_cny: 50000        # 现金直接填金额
```

---

## 5. 子模块设计

### 5.1 weight_monitor（功能 ①）

**输入**：target.yaml + holdings.yaml + tushare 价格

**输出**：drift 表 + 再平衡建议

**核心逻辑**（伪代码）：

```
for each category in target:
    actual_value = sum(holding.shares * current_price for holding in that category)
    actual_weight = actual_value / total_portfolio_value
    drift = actual_weight - target_weight
    status = {
      |drift| < 2%:  🟢 正常
      2% ≤ |drift| < 5%: 🟡 关注
      |drift| ≥ 5%: 🔴 触发再平衡
    }
```

**输出示例**：

```
Portfolio Status (as of 2026-04-19)
Total Value: ¥1,000,000

Category              Target   Actual   Drift    Status
纳指100               25.0%    18.2%    -6.8%    🔴 低配
标普500               10.0%    11.5%    +1.5%    🟢 正常
恒生科技              10.0%     0.0%   -10.0%    🔴 严重低配
A股科技成长           15.0%    19.8%    +4.8%    🟡 超配
A股红利现金流         15.0%    14.2%    -0.8%    🟢 正常
黄金黄金股            15.0%    25.1%   +10.1%    🔴 严重超配
现金                  10.0%    11.2%    +1.2%    🟢 正常

Triggered rebalance categories: 纳指100, 恒生科技, 黄金黄金股
```

### 5.2 qdii_premium（功能 ②）

**输入**：一组 ETF 代码（来自 target.yaml 中所有 QDII 类别）

**输出**：每只 ETF 的溢价 + 行动建议

**数据源**：
- 价格：tushare `fund_daily`（日收盘价）
- 基准净值：tushare `fund_nav`（单位净值）
- **MVP 用净值算溢价**：`premium = (price - nav) / nav`
- **Phase 2**：若需要实时 IOPV（盘中决策），用 akshare `fund_etf_spot_em` 或其他源（spec 不强制 tushare）

**核心逻辑**：

```
premium = (price - nav) / nav
status:
  premium < 0.03:      🟢 可买
  0.03 ≤ premium < 0.05: 🟡 减量（计划金额 × 50%）
  0.05 ≤ premium < 0.10: 🔴 换同类低溢价标的
  premium ≥ 0.10:       ⛔ 不买
```

**输出示例**：

```
QDII Premium Radar (as of 2026-04-19 close)

Code      Name          Price   NAV     Premium   Status    Action
513100    纳指100 ETF   1.650   1.540   +7.1%     🔴        换 159941
159941    纳指100 ETF   1.580   1.555   +1.6%     🟢        正常买入
513500    标普500 ETF   2.120   2.085   +1.7%     🟢        正常买入
518880    华安黄金 ETF  4.512   4.500   +0.3%     🟢        正常买入
```

**降级策略**：若 tushare 接口失败 / 净值滞后，返回 warning 而不是让整个功能崩溃。

### 5.3 allocator（功能 ③）

**输入**：新增资金金额 `amount_cny`

**输出**：按"偏离优先 + 溢价规则"的分配清单

**算法**（两阶段）：

```
阶段 1：按偏离度排序
  candidates = [(cat, drift) for cat, drift in drift_table if drift < 0]
  candidates.sort(by |drift|, desc)  # 低配最严重的优先

阶段 2：逐类别分配
  remaining = amount_cny
  for (cat, drift) in candidates:
      needed = |drift| * total_portfolio_value  # 该类别还差多少钱
      allocate = min(needed, remaining * 0.4)   # 单类最多分 40%，避免集中
      
      # 如果该类别是 QDII，检查溢价
      instrument = pick_lowest_premium(cat.instruments)
      if instrument.premium >= 0.10:
          skip  # 不买，记入 warning
      elif instrument.premium >= 0.05:
          allocate *= 0.5  # 减量
      
      orders.append((instrument, allocate))
      remaining -= allocate
      
      if remaining < min_order_size: break

阶段 3：剩余资金进现金仓
  if remaining > 0: orders.append((CASH, remaining))
```

**输出示例**：

```
Allocation Plan for ¥20,000 (as of 2026-04-19)

Order   Instrument              Amount     Reason
1       03033.HK (恒生科技)      6,000     严重低配 -10%
2       159941 (纳指100)         5,000     低配 -6.8%，溢价 1.6% 可买
3       512890 (红利低波)        4,000     略低配，平稳加仓
4       563020 (现金流 ETF)      3,000     略低配，平稳加仓
5       CASH                     2,000     剩余入货币基金

⚠️ Skipped: 513100 溢价 7.1%，建议改买 159941（已执行）
⚠️ Skipped: 518880 黄金已严重超配 +10.1%，本次不买
```

### 5.4 quarterly_review（功能 ④）

**输入**：季度起止日期 + 历史持仓快照（可选）

**输出**：markdown 格式季度报告

**报告结构**：

```markdown
# Portfolio Review: Q1 2026

## 1. 季度表现
- 期初 vs 期末总值: ¥X → ¥Y (+Z%)
- 基准对比（沪深300 / 标普500 / 纳指100）
- 各类别贡献度（基于起始权重 × 各类涨跌幅）

## 2. 权重漂移
[drift table: 季初权重 / 季末权重 / 漂移方向]

## 3. 再平衡决策
Trigger 规则：偏离 ≥ 5%
- 触发类别: [...]
- 未触发类别: [...]

## 4. 建议交易（若触发）
使用现有 Rebalancer.calculate() 生成买卖清单
- 预估交易成本
- 溢价检查后的可执行性

## 5. 异常 / 注意事项
- QDII 额度是否有变化
- 恒生科技港股通是否正常
- 任何类别 -20% 以上需要 review 假设？
```

**复用 `PortfolioAnalyzer`** 计算收益/波动/回撤；**复用 `Rebalancer`** 生成买卖清单。

---

## 6. CLI 接口

统一入口：`quant portfolio` 子命令

```bash
# ① 权重监控
quant portfolio status
quant portfolio status --holdings config/my_holdings.yaml

# ② QDII 溢价
quant portfolio premium
quant portfolio premium --code 513100,159941

# ③ 资金分配
quant portfolio allocate 20000
quant portfolio allocate 20000 --dry-run

# ④ 季度 review
quant portfolio review --quarter 2026Q1
quant portfolio review --from 2026-01-01 --to 2026-03-31 --out reports/
```

默认配置路径：
- 目标权重：`config/allocation_target.yaml`
- 持仓：`config/allocation_holdings.yaml`

---

## 7. 错误处理

| 场景 | 行为 |
|---|---|
| tushare API 调用失败 | 打印 warning，跳过该标的，不影响其他功能 |
| 净值数据缺失/滞后 | 用最近一个交易日净值，打印 warning 说明 |
| 持仓 YAML 格式错误 | 明确报错指出哪行，不部分运行 |
| 持仓总权重 ≠ 100%（超过 1% 偏差） | 报错，说明可能漏算某标的 |
| 港股通数据不在 tushare | fallback 到 akshare 或提示手工录入价格 |
| 目标权重合计 ≠ 100% | 加载时报错，拒绝运行 |

---

## 8. 测试策略

### 8.1 单元测试

- `weight_monitor.compute_drift()` —— 给定 holdings + prices + target，验证 drift 表
- `qdii_premium.compute_premium()` —— 给定 price + nav，验证分级
- `allocator.allocate()` —— 给定 drift 表 + 溢价表 + 金额，验证分配清单
  - 关键测试：低配严重 + 高溢价 → 跳过那个低配
  - 边界测试：所有类别都超配 → 全部入现金
- `quarterly_review.generate()` —— 给定 fixture 持仓变化，验证报告结构

### 8.2 集成测试

- **Fixture 持仓 + 真实 tushare 价格**：端到端跑一次 status / premium / allocate
- **Mock 数据源失败**：验证降级不崩溃

### 8.3 不做的测试

- ❌ 不做回测 / 历史模拟（这是监控工具，不是回测系统）
- ❌ 不做性能压测（单人用，无并发）

---

## 9. 实施顺序

建议按"功能解耦、可独立验证"分 4 个 PR：

1. **PR 1**：`config_loader` + `weight_monitor`（功能 ①）
   - 最基础，不依赖其他功能
   - 跑通端到端：从 YAML 到 drift 表
2. **PR 2**：`qdii_premium`（功能 ②）
   - 独立于 ①，只依赖 tushare 价格 + 净值
3. **PR 3**：`allocator`（功能 ③）
   - 依赖 ① 和 ② 的输出
   - 核心决策逻辑在这
4. **PR 4**：`quarterly_review`（功能 ④）
   - 复用现有 Rebalancer + PortfolioAnalyzer
   - 最复杂，但大部分工作是组装

每个 PR 完成后都可**独立使用**。

---

## 10. 风险和开放问题

### 10.1 已知风险

| 风险 | 缓解 |
|---|---|
| Tushare QDII 净值延迟 1-2 日 | MVP 接受，Phase 2 用实时 IOPV |
| 港股通标的 03033.HK 不在 tushare 免费版 | 可 fallback akshare，或手工录入价格（单月级不频繁） |
| 持仓维护手动，易出错 | 添加"持仓校验"命令，显示总值和加权查错 |
| 用户不按建议执行 | 工具不强制，只给建议；季度 review 会显示实际 vs 建议偏差 |

### 10.2 开放问题

- 是否需要"历史 drift 曲线"？Level 2 不包含，Level 3 可加
- 季度 review 的"贡献度归因"口径：用起始权重还是时间加权？—— MVP 用起始权重（简单）
- 是否允许"目标权重微调"（比如临时调整 5% 仓位）？—— MVP 不支持，要改必须改 YAML 重新部署

---

## 11. 不做 writing-plans？

这个 spec 会进 writing-plans 生成详细实现计划，因为是**软件项目**（与配置策略文档性质不同）。实现计划将拆解为 4 个独立可执行的 PR，每个 PR 都有自己的 TDD 任务清单。
