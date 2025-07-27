# 量化交易系统入口脚本

本目录包含量化交易系统的入口脚本：

## 📊 脚本概览

### 🚀 `run.py` - 统一入口（推荐）
整合所有功能的统一CLI入口，支持交易策略、新闻分析和系统管理。

### `trading_strategy.py` - 交易策略专用工具
专门的交易策略入口脚本，支持策略回测、参数优化和模拟交易。

### `investment_news.py` - 新闻分析专用工具  
专门的投资新闻分析入口脚本，支持新闻收集、分析和投资报告生成。

### `generate_daily_investment_report.py` - 每日投资报告生成器
专门用于生成每日投资品新闻分析报告的工具脚本。

## 🚀 快速开始

⚡ **推荐使用统一入口**: `python bin/run.py --help`

### 安装依赖
```bash
pip install -r requirements.txt
```

### 环境配置
确保已配置 `.env` 文件：
```bash
cp env_example_unified.txt .env
# 编辑 .env 文件，配置必要的API密钥
```

## 🎯 统一入口使用指南

### 基本命令结构
```bash
python bin/run.py <模块> <操作> [参数]
```

### 快速示例
```bash
# 🔍 系统状态检查
python bin/run.py system status

# 📊 交易策略
python bin/run.py trading list                        # 列出可用策略
python bin/run.py trading backtest grid 000001.SZ     # 网格策略回测

# 📰 新闻分析
python bin/run.py news collect                        # 收集新闻
python bin/run.py news report                         # 生成投资日报

# ⚙️ 系统管理
python bin/run.py system clean --type cache           # 清理缓存
```

## 📈 交易策略工具使用指南

### 基本命令

#### 列出可用策略
```bash
python bin/trading_strategy.py list
```

#### 运行策略回测
```bash
# 基础网格策略回测
python bin/trading_strategy.py backtest grid 000001.SZ

# 指定时间范围和参数
python bin/trading_strategy.py backtest grid 000001.SZ \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --initial-balance 100000 \
    --grid-spacing 0.02 \
    --grid-levels 10

# 增强网格策略回测
python bin/trading_strategy.py backtest enhanced_grid 000001.SZ \
    --start-date 2024-01-01
```

#### 优化策略参数
```bash
# 优化网格策略参数
python bin/trading_strategy.py optimize grid 000001.SZ \
    --start-date 2024-01-01 \
    --end-date 2024-06-30

# 优化增强网格策略
python bin/trading_strategy.py optimize enhanced_grid 002594.SZ
```

#### 启动模拟交易
```bash
# 启动网格策略模拟交易
python bin/trading_strategy.py live grid 000001.SZ \
    --initial-balance 50000 \
    --grid-spacing 0.03 \
    --grid-levels 8
```

### 支持的策略

| 策略名称 | 描述 | 特点 |
|---------|------|------|
| `grid` | 基础网格交易策略 | 固定网格间距，适合震荡市场 |
| `enhanced_grid` | 增强网格交易策略 | 支持动态调整，适应性更强 |

### 参数说明

- `--start-date`: 回测开始日期 (YYYY-MM-DD)
- `--end-date`: 回测结束日期 (YYYY-MM-DD) 
- `--initial-balance`: 初始资金 (默认: 100000)
- `--grid-spacing`: 网格间距 (默认: 0.02)
- `--grid-levels`: 网格层数 (默认: 10)
- `--log-level`: 日志级别 (DEBUG/INFO/WARNING/ERROR)

## 📰 投资新闻分析工具使用指南

### 基本命令

#### 列出投资分析目标
```bash
python bin/investment_news.py list
```

#### 生成投资分析日报
```bash
# 生成全部目标的日报
python bin/investment_news.py report

# 生成指定目标的日报
python bin/investment_news.py report --targets NASDAQ GOLD

# 指定分析周期
python bin/investment_news.py report --days-back 3
```

#### 收集新闻数据
```bash
# 从所有源收集新闻
python bin/investment_news.py collect

# 从指定源收集新闻
python bin/investment_news.py collect --sources sina eastmoney

# 指定收集周期
python bin/investment_news.py collect --days-back 5
```

#### 分析新闻数据
```bash
# 分析现有新闻数据
python bin/investment_news.py analyze

# 分析指定目标的新闻
python bin/investment_news.py analyze --targets NASDAQ CSI300

# 分析最近3天的新闻
python bin/investment_news.py analyze --days-back 3
```

#### 查看数据汇总
```bash
python bin/investment_news.py summary
```

#### 配置投资目标
```bash
# 列出当前配置的投资目标
python bin/investment_news.py config list

# 查看配置文件位置（需手动编辑）
python bin/investment_news.py config edit
```

### 支持的投资分析目标

| 目标代码 | 名称 | 类别 | 关键词示例 |
|---------|------|------|-----------|
| `NASDAQ` | 纳斯达克科技股 | 指数 | NASDAQ, 科技股, 苹果, 微软 |
| `INDIA_STOCKS` | 印度股市 | 国际股票 | 印度, India, 孟买, 新兴市场 |
| `GOLD` | 黄金贵金属 | 商品 | 黄金, 贵金属, 避险资产 |
| `CSI300` | 沪深300指数 | 指数 | 沪深300, A股, 中国股市 |

### 参数说明

- `--targets`: 指定分析目标 (多个用空格分隔)
- `--days-back`: 回溯天数 (默认: 2)
- `--sources`: 新闻数据源 (sina/eastmoney/wallstreetcn)
- `--log-level`: 日志级别 (DEBUG/INFO/WARNING/ERROR)

## 📁 输出文件

### 交易策略结果
- 回测结果: `reports/backtest_<symbol>_<strategy>_<timestamp>.json`
- 优化结果: `reports/optimization_<symbol>_<strategy>_<timestamp>.json`

### 投资新闻分析结果
- 日报: `reports/<date>/investment_analysis.md` 和 `.json`
- 新闻分析: `reports/news_analysis_<timestamp>.json`

### 日志文件
- 交易策略日志: `logs/trading_strategy_<date>.log`
- 新闻分析日志: `logs/investment_news_<date>.log`
- 每日报告日志: `logs/daily_report_<date>.log`

## 📊 每日投资报告生成器使用指南

### 基本使用
```bash
# 生成当日投资报告（分析最近2天新闻）
python bin/generate_daily_investment_report.py
```

### 功能特点
- 🔍 自动分析最近几天的投资新闻
- 📈 生成市场情绪和投资建议分析
- 📄 输出详细的投资分析报告
- 🎯 支持多种投资标的分析

### 报告内容
- 市场整体展望和情绪分析
- 各投资标的具体分析和建议
- 投资建议分布统计
- 新闻数量和置信度评估

### 输出位置
- 详细报告：`reports/<date>/`
- 日志文件：`logs/daily_report_<date>.log`

## 🔧 高级用法

### 批量操作示例

#### 多股票回测
```bash
#!/bin/bash
# 批量回测多个股票
STOCKS=("000001.SZ" "002594.SZ" "000002.SZ")
for stock in "${STOCKS[@]}"; do
    echo "回测股票: $stock"
    python bin/trading_strategy.py backtest grid $stock --start-date 2024-01-01
done
```

#### 定时生成投资报告
```bash
#!/bin/bash
# 每日自动生成投资报告
python bin/investment_news.py collect
python bin/investment_news.py report
```

### 与其他工具集成

#### 结合 cron 定时任务
```bash
# 每日早上8点生成投资报告
0 8 * * * cd /path/to/quantitative_trading && python bin/investment_news.py report
```

## ⚠️ 注意事项

1. **API限制**: 
   - Tushare API有调用频率限制
   - 建议使用缓存数据避免重复调用

2. **模拟交易**:
   - `live` 命令仅为模拟，不会产生真实交易
   - 如需实盘交易，请谨慎评估风险

3. **数据依赖**:
   - 确保网络连接正常
   - 检查API密钥配置是否正确

4. **性能考虑**:
   - 大量数据分析可能需要较长时间
   - 建议分批处理大数据集

## 🐛 故障排除

### 常见问题

1. **导入错误**: 确保已安装所有依赖包
2. **API调用失败**: 检查 `.env` 文件中的API密钥配置
3. **数据为空**: 确认股票代码格式正确，数据源可用
4. **权限错误**: 确保脚本有执行权限 (`chmod +x bin/*.py`)

### 获取帮助
```bash
# 查看具体命令的帮助
python bin/trading_strategy.py <command> --help
python bin/investment_news.py <command> --help
```

---

🎯 **提示**: 建议在正式使用前，先在测试环境中验证所有功能。 