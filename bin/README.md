# 快捷脚本使用指南

本目录包含常用功能的快捷脚本，提供便捷的命令行访问方式。

## 📋 可用脚本

| 脚本 | 功能 | 对应CLI命令 |
|------|------|------------|
| `screen_etfs.py` | ETF筛选与估值 | `python -m quant etf` |
| `analyze_portfolio.py` | 投资组合分析 | `python -m quant portfolio` |
| `advisor.py` | 投资顾问分析 | `python -m quant advisor` |
| `backtest.py` | 策略回测 | `python -m quant strategy` |
| `momentum_analyzer.py` | **动能分析工具** | 独立工具 |
| `regression_analyzer.py` | **回归拟合分析** | 独立工具 |
| `system_check.py` | 系统状态检查 | `python -m quant system` |


## 🚀 使用方式

### 1. ETF筛选 (`screen_etfs.py`)

```bash
# 筛选宽基ETF
python bin/screen_etfs.py --types broad_market --save

# 从配置篮子筛选
python bin/screen_etfs.py --from-config INDUSTRY_ETF --save

# 分析单只ETF
python bin/screen_etfs.py --single 510300.SH

# 查看配置
python bin/screen_etfs.py --config-show
python bin/screen_etfs.py --list-config
```

**等价于**:
```bash
python -m quant etf screen --types broad_market --save
python -m quant etf screen --from-config INDUSTRY_ETF --save
python -m quant etf single 510300.SH
python -m quant etf config --show
```

---

### 2. 投资组合分析 (`analyze_portfolio.py`)

```bash
# 分析指定组合
python bin/analyze_portfolio.py USER_REAL_PORTFOLIO

# 详细分析
python bin/analyze_portfolio.py USER_REAL_PORTFOLIO --detail

# 列出可用组合
python bin/analyze_portfolio.py --list
```

**等价于**:
```bash
python -m quant portfolio analyze USER_REAL_PORTFOLIO
python -m quant portfolio analyze USER_REAL_PORTFOLIO --detail
python -m quant portfolio list
```

---

### 3. 投资顾问 (`advisor.py`)

```bash
# 单标的分析
python bin/advisor.py 002594.SZ

# 综合分析（包含策略回测）
python bin/advisor.py 002594.SZ --comprehensive

# 指定数据源
python bin/advisor.py 002594.SZ --provider tushare

# 自定义历史数据天数
python bin/advisor.py 002594.SZ -c --days 1000
```

**等价于**:
```bash
python -m quant advisor single 002594.SZ
python -m quant advisor comprehensive 002594.SZ
python -m quant advisor single 002594.SZ --provider tushare
python -m quant advisor comprehensive 002594.SZ --days 1000
```

---

### 4. 策略回测 (`backtest.py`)

```bash
# 回测均线交叉策略
python bin/backtest.py ma_crossover 002594.SZ

# 回测动量策略
python bin/backtest.py momentum 002594.SZ

# 自定义回测时间
python bin/backtest.py ma_crossover 002594.SZ --start 20240101 --end 20241201

# 列出可用策略
python bin/backtest.py --list
```

**等价于**:
```bash
python -m quant strategy backtest ma_crossover 002594.SZ
python -m quant strategy backtest momentum 002594.SZ
python -m quant strategy backtest ma_crossover 002594.SZ --start 20240101 --end 20241201
python -m quant strategy list
```

---

### 5. 动能分析工具 (`momentum_analyzer.py`) ⭐新增

```bash
# 单只标的动能分析（详细模式）
python bin/momentum_analyzer.py 002594.SZ

# 批量分析（简洁模式）
python bin/momentum_analyzer.py 002594.SZ 000001.SZ 510300.SH --compact

# 对比多个标的（表格模式）
python bin/momentum_analyzer.py 510300.SH 510050.SH 159915.SZ --compare

# 自定义分析周期
python bin/momentum_analyzer.py 002594.SZ --days 60

# 保存分析结果
python bin/momentum_analyzer.py 002594.SZ --save --output json
python bin/momentum_analyzer.py 002594.SZ 000001.SZ --save --output csv

# 指定输出文件名
python bin/momentum_analyzer.py 002594.SZ --save --filename my_momentum_report.json

# 详细输出模式
python bin/momentum_analyzer.py 002594.SZ --verbose
```

**功能特点**:
- ✅ 多周期收益率分析（1日/3日/5日/1周/2周）
- ✅ 连续上涨/下跌天数统计
- ✅ 成交量放大倍数分析
- ✅ 价格突破信号检测
- ✅ 短期趋势强度评估
- ✅ **综合动量评分（0-100分）**
- ✅ 智能操作建议
- ✅ 支持批量对比分析
- ✅ 支持JSON/CSV导出

**注意**: 这是独立工具，直接调用底层动量分析器，不依赖统一CLI。

---

### 6. 回归拟合分析工具 (`regression_analyzer.py`) ⭐新增

```bash
# 基础回归分析（四种模型对比）
python bin/regression_analyzer.py 002594.SZ

# 指定回归类型
python bin/regression_analyzer.py 002594.SZ --type linear
python bin/regression_analyzer.py 002594.SZ --type poly --degree 3
python bin/regression_analyzer.py 002594.SZ --type exp
python bin/regression_analyzer.py 002594.SZ --type log

# 指定分析周期
python bin/regression_analyzer.py 002594.SZ --days 60
python bin/regression_analyzer.py 002594.SZ --days 250  # 约一年

# 预测未来价格
python bin/regression_analyzer.py 002594.SZ --predict 10

# 绘制图表并保存
python bin/regression_analyzer.py 002594.SZ --plot --save

# 完整示例：120天数据、二次多项式、预测5天、保存结果和图表
python bin/regression_analyzer.py 002594.SZ --days 120 --type poly --degree 2 --predict 5 --plot --save
```

**支持的回归模型**:
| 类型 | 公式 | 适用场景 |
|------|------|----------|
| `linear` | y = ax + b | 稳定趋势 |
| `poly` | y = aₙxⁿ + ... + a₀ | 加速/减速趋势 |
| `exp` | y = a·eᵇˣ | 指数增长/衰减 |
| `log` | y = a·ln(x) + b | 逐渐平缓的趋势 |

**功能特点**:
- ✅ 四种回归模型自动对比
- ✅ R² 拟合度评估
- ✅ 年化收益率/增长率计算
- ✅ 未来价格预测
- ✅ 可视化图表输出
- ✅ JSON结果导出

**注意**: 这是独立工具，直接进行价格回归分析，不依赖统一CLI。

---

### 7. 系统检查 (`system_check.py`)


```bash
# 系统状态检查（默认）
python bin/system_check.py

# 显式状态检查
python bin/system_check.py --status

# 清理所有缓存
python bin/system_check.py --clean

# 清理特定类型缓存
python bin/system_check.py --clean --type etf
python bin/system_check.py --clean --type data

# 查看版本信息
python bin/system_check.py --version
```

**等价于**:
```bash
python -m quant system status
python -m quant system status
python -m quant system clean --type all
python -m quant system clean --type etf
python -m quant system clean --type data
python -m quant system version
```

---

## 💡 设计理念

### 为什么使用快捷脚本？

1. **简化命令**: 更短、更直观的命令
2. **向后兼容**: 保持旧脚本可用
3. **用户友好**: 无需记忆完整的CLI命令
4. **快速访问**: 常用功能一键触达

### 快捷脚本 vs 统一CLI

**快捷脚本**（适合日常使用）:
```bash
python bin/screen_etfs.py --types broad_market --save
python bin/advisor.py 002594.SZ
python bin/backtest.py ma_crossover 002594.SZ
```

**统一CLI**（推荐用于脚本和自动化）:
```bash
python -m quant etf screen --types broad_market --save
python -m quant advisor single 002594.SZ
python -m quant strategy backtest ma_crossover 002594.SZ
```

### 工作原理

所有快捷脚本都会：
1. 显示提示信息（告知调用统一CLI）
2. 转换参数为新CLI格式
3. 调用统一CLI的主入口
4. 返回执行结果

示例输出：
```
📢 提示: 这是快捷脚本，实际调用统一CLI
💡 推荐使用: python -m quant <command> <subcommand> [options]

[实际执行结果...]
```

---

## 🔧 开发者说明

### 添加新的快捷脚本

1. 创建新脚本文件: `bin/your_script.py`
2. 参考现有脚本的模板结构
3. 实现 `convert_args_to_cli_format()` 函数
4. 添加执行权限: `chmod +x bin/your_script.py`
5. 更新本 README 文档

### 脚本模板

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
功能描述快捷脚本

推荐使用: python -m quant <command> <subcommand> [options]
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def convert_args_to_cli_format():
    """将参数转换为新CLI格式"""
    import argparse
    
    parser = argparse.ArgumentParser(description='功能描述 (快捷方式)')
    # 添加参数...
    args, unknown = parser.parse_known_args()
    
    cli_args = ['command', 'subcommand']
    # 构建CLI参数...
    
    return cli_args

def main():
    """主函数"""
    print("📢 提示: 这是快捷脚本，实际调用统一CLI")
    print("💡 推荐使用: python -m quant <command> <subcommand> [options]")
    print()
    
    cli_args = convert_args_to_cli_format()
    
    from quant.__main__ import main as cli_main
    original_argv = sys.argv
    sys.argv = ['python -m quant'] + cli_args
    
    try:
        return cli_main()
    finally:
        sys.argv = original_argv

if __name__ == '__main__':
    sys.exit(main())
```

---

## 📂 演示脚本 (`examples/`)

`examples/` 子目录包含各种演示和样例脚本：

| 脚本 | 功能 |
|------|------|
| `enhanced_data_demo.py` | 增强数据获取演示 |
| `etf_valuation_demo.py` | ETF估值分析演示 |
| `portfolio_backtest_demo.py` | 组合回测演示 |
| `pyramid_dca_demo.py` | 金字塔定投演示 |
| `sleeve_portfolio_demo.py` | 袖套组合演示 |
| `trend_analysis_demo.py` | 趋势分析演示 |
| `ma_crossover_analysis.py` | 均线交叉分析 |
| `low_vol_tech_rsi_dca_backtest.py` | 低波技术RSI定投回测 |
| `user_real_portfolio_demo.py` | 用户真实组合演示 |
| `user_updated_portfolio_demo.py` | 用户更新组合演示 |
| `refactored_grid_agent.py` | 重构网格代理演示 |

使用方式：
```bash
python bin/examples/etf_valuation_demo.py
python bin/examples/portfolio_backtest_demo.py
```

---

## 📚 相关文档

- [主README](../README.md) - 系统总体说明
- [ETF估值指南](../docs/ETF_VALUATION_GUIDE.md) - ETF分析详细说明
- [目录结构说明](../docs/DIRECTORY_STRUCTURE.md) - 项目目录说明

---

**享受便捷的量化分析！** 🚀

