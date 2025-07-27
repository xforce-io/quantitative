# 静态网格+回收机制使用指南

## 🎯 概述

静态网格+回收机制是解决传统静态网格策略"锁死"问题的**行业标准解决方案**。它保持了静态网格的稳定性，同时通过智能回收机制显著提升交易活跃度。

## 🚀 快速开始

### 方法一：使用快速脚本

```bash
python use_static_grid_recycling.py
```

### 方法二：使用详细演示

```bash
python demo/static_grid_recycling_demo.py
```

## ⚙️ 配置说明

### 基础配置 (`config/trading_config.yaml`)

```yaml
static_grid_recycling:
  # 基础网格参数
  gridLevels: 8                    # 网格层数
  gridSpacing: 0.025              # 2.5% 网格间距
  baseRatio: 0.3                  # 30% 基础仓位
  
  # 关键：保持静态特性
  dynamicEnabled: false           # 禁用动态调整
  
  # 网格回收机制 - 核心功能
  enableGridRecycling: true       # 启用网格回收
  recyclingProfitThreshold: 0.008 # 0.8%盈利触发回收
  maxFilledGridRatio: 0.75        # 75%网格被填充时触发回收
  recyclingCooldown: 600          # 10分钟回收冷却期
```

### 预设配置类型

| 配置类型 | 特点 | 适用场景 |
|---------|------|---------|
| `static_grid_recycling` | 平衡型 | 大多数市场环境 |
| `conservative_grid` | 保守型 | 低风险偏好 |
| `aggressive_grid` | 激进型 | 高风险高收益 |

## 📊 核心机制

### 网格回收触发条件

1. **盈利触发**：累计盈利达到设定阈值
2. **填充率触发**：已填充网格比例超过阈值
3. **冷却期控制**：防止频繁回收

### 回收逻辑

```python
# 智能回收：只回收接近当前价格的已填充网格
for grid in self.buyGrids:
    if grid.isFilled and abs(currentPrice - grid.price) / currentPrice < self.gridSpacing * 2:
        grid.isFilled = False  # 重置填充状态
```

## 🔄 工作流程

1. **初始化**：设置静态网格结构
2. **交易执行**：按网格逻辑执行买卖
3. **监控状态**：实时监控网格填充率和盈利水平
4. **智能回收**：满足条件时回收已填充网格
5. **继续交易**：回收后的网格重新参与交易

## 📈 性能优势

### 对比传统静态网格

| 指标 | 传统静态网格 | 静态网格+回收 | 改善 |
|------|-------------|---------------|------|
| 交易活跃度 | 逐渐降低 | 持续保持 | ✅ 显著改善 |
| 盈利机会 | 有限 | 持续捕获 | ✅ 大幅提升 |
| 风险控制 | 好 | 好 | ✅ 保持优势 |
| 策略稳定性 | 高 | 高 | ✅ 保持优势 |

## 💡 使用建议

### 参数调优

1. **网格间距**：
   - 高波动性股票：2.0-3.0%
   - 中等波动性股票：2.5-3.5%
   - 低波动性股票：1.5-2.5%

2. **回收阈值**：
   - 保守型：盈利1.0%，填充率80%
   - 平衡型：盈利0.8%，填充率75%
   - 激进型：盈利0.5%，填充率70%

3. **冷却期**：
   - 短线交易：5-10分钟
   - 中线交易：10-30分钟
   - 长线交易：30分钟-1小时

### 适用场景

✅ **适合的市场**：
- 震荡市场
- 箱体整理
- 区间波动

⚠️ **谨慎使用**：
- 强烈单边趋势
- 重大消息面冲击
- 极端波动期

## 🛠️ 自定义配置

### 创建自定义配置

```python
custom_config = {
    'gridLevels': 10,               # 根据资金量调整
    'gridSpacing': 0.03,           # 根据波动率调整
    'baseRatio': 0.4,              # 根据风险偏好调整
    'enableGridRecycling': True,    # 必须启用
    'recyclingProfitThreshold': 0.01,  # 根据预期调整
    'maxFilledGridRatio': 0.8,     # 根据活跃度需求调整
    'recyclingCooldown': 900,      # 根据交易频率调整
}
```

### 运行自定义配置

```python
from quant.engines.backtest_engine import BacktestEngine

engine = BacktestEngine()
results = engine.runBacktest(
    symbol='您的股票代码',
    startDate='开始日期',
    endDate='结束日期',
    initialCapital=100000,
    strategyConfig=custom_config
)
```

## 📋 监控指标

### 关键监控点

1. **网格状态**：
   - 已填充网格数量
   - 填充率百分比
   - 回收触发次数

2. **盈利指标**：
   - 累计收益率
   - 单笔交易盈亏
   - 回收带来的额外收益

3. **风险指标**：
   - 最大回撤
   - 持仓风险敞口
   - 资金利用率

## ❓ 常见问题

### Q: 与动态网格有什么区别？
A: 静态网格+回收保持了网格结构的稳定性，只是智能回收已填充的网格，而动态网格会重新计算整个网格结构。

### Q: 回收机制会增加风险吗？
A: 不会。回收机制有严格的触发条件和冷却期，且只在盈利状态下触发，实际上是在降低机会成本。

### Q: 如何选择合适的回收参数？
A: 建议从保守参数开始（盈利1%，填充率80%），根据回测结果和实际表现逐步优化。

### Q: 适合哪些类型的股票？
A: 最适合有一定波动性但不是强单边趋势的股票，如蓝筹股、成长股等。

## 📞 技术支持

如有问题，请查看：
- `docs/GRID_TRADING_INDUSTRY_SOLUTIONS.md` - 详细技术文档
- `demo/static_grid_recycling_demo.py` - 完整演示代码
- 或在项目中提交 Issue

---

**🎉 开始使用静态网格+回收机制，体验行业标准的网格交易解决方案！** 