# Agent 实验-回测工作流程指南

本指南详细说明如何使用Agent实验优化策略，然后从实验结果加载配置进行回测的完整工作流程。

## 🎯 工作流程概览

```
Agent实验 → 最佳策略保存 → 从实验配置回测 → 详细交易分析
    ↓              ↓              ↓              ↓
 多策略测试   → data/expr目录 → 命令行回测   → 交易过程展示
```

## 📋 Step 1: 查看可用实验配置

```bash
# 列出所有预配置的实验
python bin/run.py trading agent list
```

## 📊 Step 2: 运行Agent实验

```bash
# 运行比亚迪多策略实验
python bin/run.py trading agent run byd_multi_strategy
```

这个命令会：
- 测试多种策略类型（网格、定投、动量）
- 为每种策略生成多个参数变体
- 运行完整的回测优化
- 找到最佳策略配置
- 自动保存实验结果到 `data/expr/StrategyType_YYMMDDHHNN/` 目录

## 💾 实验结果保存结构

```
data/expr/GridTrading_2506071614/
├── best_strategy_config.json    # 最佳策略配置文件
├── experiment_meta.json         # 实验描述文件
└── all_results.json            # 所有Agent结果详情
```

## 📂 Step 3: 查看保存的实验结果

```bash
# 列出所有已保存的实验结果
python bin/run.py trading agent list-results
```

## 🔄 Step 4: 从实验结果进行回测

### 基本用法

```bash
# 使用实验中的配置进行回测
python bin/run.py trading backtest-from-experiment data/expr/GridTrading_2506071614
```

### 自定义参数

```bash
# 覆盖实验配置中的参数
python bin/run.py trading backtest-from-experiment data/expr/GridTrading_2506071614 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --initial-balance 200000 \
    --output-format excel
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--start-date` | 回测开始日期 | 实验配置中的日期 |
| `--end-date` | 回测结束日期 | 实验配置中的日期 |
| `--initial-balance` | 初始资金 | 实验配置中的金额 |
| `--output-format` | 输出格式 | `both` (JSON和Excel) |

## 📈 回测输出详解

### 控制台输出包括：
- 策略基本信息
- 详细性能指标
- 交易过程概览
- 生成的报告文件路径

### 生成的文件：
- JSON报告：完整的技术细节
- Excel报告：适合人工分析的多工作表格式

## 🎯 完整使用流程

```bash
# 1. 查看可用实验
python bin/run.py trading agent list

# 2. 运行实验
python bin/run.py trading agent run byd_multi_strategy

# 3. 查看实验结果
python bin/run.py trading agent list-results

# 4. 从实验进行回测
python bin/run.py trading backtest-from-experiment data/expr/GridTrading_2506071614

# 5. 自定义时间段回测
python bin/run.py trading backtest-from-experiment data/expr/GridTrading_2506071614 \
    --start-date 2024-01-01 --end-date 2024-12-31
```

## 📊 快速体验

```bash
# 运行演示脚本
python demo/experiment_backtest_workflow_demo.py
```

## 📝 注意事项

- 实验结果自动保存到 `data/expr/` 目录
- 回测会优先使用命令行参数
- 策略参数在回测时不能修改
- 支持JSON和Excel两种输出格式 