# 网格交易策略

## 概述

本模块提供了统一的网格交易策略实现，整合了基础网格交易和高级功能。

## 重构说明

为了减少代码重复和提高维护性，我们已经：

1. **合并了重复代码**：将原来的 `GridTradingStrategy` 和 `UnifiedGridTradingStrategy` 合并
2. **保持向后兼容**：`GridTradingStrategy` 现在是 `UnifiedGridTradingStrategy` 的别名
3. **统一入口**：所有网格策略功能都通过 `UnifiedGridTradingStrategy` 提供

## 使用方法

### 基础用法

```python
from quant.strategies import GridTradingStrategy

# 创建策略实例（现在指向统一策略）
strategy = GridTradingStrategy(symbol='000001.SZ')

# 或者直接使用统一策略
from quant.strategies import UnifiedGridTradingStrategy
strategy = UnifiedGridTradingStrategy(symbol='000001.SZ')
```

### 配置参数

```python
config = {
    'gridLevels': 10,           # 网格级数
    'gridSpacing': 0.02,        # 网格间距（2%）
    'maxPosition': 100000,      # 最大持仓金额
    'baseRatio': 0.3,          # 基础持仓比例（30%）
    'commission': 0.0003,       # 手续费率
    'slippage': 0.001,         # 滑点率
    'dynamicEnabled': True      # 启用动态网格调整
}

strategy = UnifiedGridTradingStrategy(symbol='000001.SZ', config=config)
```

## 主要功能

1. **基础网格交易**：自动在设定价格区间内买低卖高
2. **基础持仓管理**：支持价值投资基础持仓 + 网格交易组合
3. **动态网格调整**：根据价格趋势动态调整网格中心
4. **风险控制**：完善的安全检查和持仓验证
5. **性能分析**：详细的交易统计和风险指标

## 数据结构

- `GridLevel`：网格级别数据结构
- `Trade`：交易记录数据结构

## 注意事项

- 所有交易量必须是100股的整数倍（A股最小交易单位）
- 策略包含完善的安全检查，防止异常交易
- 支持动态网格调整以适应市场变化

## 核心特性

- **仓位占比管理**: 支持基础仓位 + 网格交易仓位的分配
- **动态网格调整**: 根据价格变动自动调整网格中心位置
- **风险控制**: 基础仓位与网格交易仓位分离，保护长期投资
- **灵活配置**: 支持多种参数配置和调整策略

## 完整示例

```python
from quant.strategies import UnifiedGridTradingStrategy

# 创建策略实例
strategy = UnifiedGridTradingStrategy('000001.SZ', config)

# 初始化资金
strategy.reset(100000)

# 设置网格
strategy.setupGrids(referencePrice=50.0)

# 处理市场数据
strategy.onMarketData(timestamp, price, volume)

# 获取性能指标
metrics = strategy.getPerformanceMetrics(initialCapital)
```

## 重构改进

为了简化代码结构和提高维护性，已完成以下优化：

- ✅ **删除重复代码**：移除了旧的 `grid_strategy.py`
- ✅ **统一接口**：`GridTradingStrategy` 现在是 `UnifiedGridTradingStrategy` 的别名
- ✅ **保持兼容性**：现有代码无需修改，自动使用增强功能
- ✅ **简化维护**：单一策略文件，减少维护成本

## 更新日志

- **2024-12**: 整合重复的网格策略代码
- **2024-12**: 删除冗余的 `grid_strategy.py` 文件  
- **2024-12**: 更新导入接口，保持向后兼容性 