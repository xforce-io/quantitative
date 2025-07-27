# 量化分析工具集 (Analyst)

本目录包含各种股票分析工具，所有分析类工具统一放置在此目录中。

## 🎯 TrendAnalyzer - 趋势分析器 (已整合)

### 功能特点

`TrendAnalyzer` 是一个综合的趋势分析工具，整合了以下功能：
- ✅ **缓存数据模式** - 使用本地缓存数据进行快速分析
- ✅ **最新数据模式** - 强制从Tushare获取最新数据进行实时分析
- ✅ **多技术指标分析** - MA、EMA、RSI、MACD、动量、突破点等
- ✅ **综合评分体系** - 基于多指标的智能评分和趋势判断
- ✅ **批量股票分析** - 支持多只股票对比分析

### 使用方法

#### 1. 命令行使用

```bash
# 使用缓存数据分析
python analyst/trend_analyzer.py 002594.SZ 比亚迪

# 强制获取最新数据分析
python analyst/trend_analyzer.py 002594.SZ 比亚迪 --latest
```

#### 2. 程序化调用

```python
from analyst.trend_analyzer import TrendAnalyzer

# 缓存数据模式（快速）
analyzer = TrendAnalyzer(use_latest_data=False)
result = analyzer.analyze_trend('002594.SZ', '比亚迪')

# 最新数据模式（实时）
analyzer_latest = TrendAnalyzer(use_latest_data=True)
result = analyzer_latest.analyze_trend('600036.SH', '招商银行')

# 批量分析
stocks = [('002594.SZ', '比亚迪'), ('600036.SH', '招商银行')]

# 使用缓存数据
results = analyzer.analyze_multiple_stocks(stocks)

# 使用最新数据
results = analyzer_latest.analyze_multiple_stocks_latest(stocks, days=250)
```

#### 3. 演示示例

```bash
# 运行综合演示
python demo/trend_analysis_demo.py
```

### 技术指标权重

| 指标类型 | 权重 | 用途 |
|---------|------|------|
| 移动平均线 (MA/EMA) | 30% | 趋势方向和支撑阻力 |
| 动量指标 (Momentum/MACD) | 30% | 价格变化速度和力度 |
| 突破分析 (Breakout) | 25% | 关键价位突破 |
| RSI指标 | 15% | 超买超卖状态 |

### 评分体系

| 分数范围 | 趋势判断 | 置信度 | 建议操作 |
|---------|---------|--------|---------|
| > 60分 | 强烈上涨趋势 | 高 | 积极买入 |
| 30-60分 | 上涨趋势 | 中 | 适量买入 |
| -30至30分 | 震荡趋势 | 低 | 区间操作 |
| -60至-30分 | 下跌趋势 | 中 | 减仓观望 |
| < -60分 | 强烈下跌趋势 | 高 | 避险出场 |

## 🔧 其他分析工具

### RSI分析器 (rsi_analyzer.py)
- 专门的RSI超买超卖分析
- 支持批量股票RSI对比

### 动量筛选器 (momentum_stock_screener.py)
- 基于动量指标的股票筛选
- 识别强势和弱势股票

### 策略兼容性分析器 (stock_strategy_analyzer.py)
- 分析股票特征与交易策略的匹配度
- 提供策略推荐

### 策略绩效分析器 (strategy_performance_analyzer.py)
- 分析历史策略表现
- 识别高收益策略

### 招商银行策略分析器 (cmb_strategy_analyzer.py)
- 专门针对招商银行的策略分析
- 展示行业特定分析方法

## 📁 目录整合说明

根据项目架构最佳实践，所有分析类工具已统一整合到 `analyst/` 目录：

- ✅ **集中管理** - 所有分析工具统一放置，便于维护
- ✅ **功能整合** - 避免重复代码，提高代码复用性
- ✅ **架构清晰** - 分析工具与演示脚本分离

### 迁移说明

原 `demo/latest_trend_analysis.py` 的功能已完全整合到 `analyst/trend_analyzer.py`：
- 保留了强制获取最新数据的功能
- 增加了数据模式选择（缓存 vs 最新）
- 提供了更灵活的API接口

## 🚀 快速开始

1. **安装依赖**
```bash
pip install -r requirements.txt
```

2. **配置数据源**
```bash
# 确保.env文件中配置了Tushare API密钥
TUSHARE_TOKEN=your_tushare_token
```

3. **运行示例**
```bash
# 快速分析（使用缓存数据）
python analyst/trend_analyzer.py 002594.SZ 比亚迪

# 实时分析（获取最新数据）
python analyst/trend_analyzer.py 002594.SZ 比亚迪 --latest

# 运行演示
python demo/trend_analysis_demo.py
```

## 📖 最佳实践

1. **日常分析** - 使用缓存数据模式，快速获得分析结果
2. **重要决策** - 使用最新数据模式，确保数据时效性
3. **对比分析** - 利用批量分析功能发现相对强势股票
4. **风险控制** - 结合评分体系和置信度进行仓位管理

## ⚠️ 注意事项

- 技术分析需结合基本面分析
- 严格执行止损和风险管理
- 市场环境变化时及时调整策略
- 定期验证和优化分析参数 