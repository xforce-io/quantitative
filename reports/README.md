# 📁 分析结果文件组织说明

## 📊 目录结构

从 2025年8月24日开始，分析系统采用了新的文件组织结构，将不同类型的输出文件分类存放：

### 📄 reports/ - 分析报告目录
```
reports/
├── README.md                               # 本说明文档
├── etf_screening/                         # ETF筛选报告 🆕
│   └── YYYYMMDD/                          # 按日期组织
│       ├── etf_screening_*.csv           # 筛选结果CSV
│       └── etf_screening_*_report.md     # 详细分析报告
├── capital_flow/                          # 资金流向分析
│   ├── industry_flow_data_*.json         # 行业资金流数据
│   └── industry_flow_report_*.html       # 资金流可视化报告
├── YYYYMMDD/                              # 按日期的分析报告
│   └── *_analysis_*.json                 # 组合分析结果
├── semiconductor_analysis_summary.md        # 半导体行业分析总结 ⭐
├── semiconductor_industry_analysis_report.md # 半导体行业完整分析报告 ⭐
├── china_banks_momentum_report.md          # 银行动量分析报告
├── zijin_momentum_analysis.md              # 紫金矿业动量分析
└── *.xlsx                                  # Excel格式报告文件
```

**📌 存放内容**：
- ✅ Markdown格式的分析报告 (*.md)
- ✅ Excel格式的分析结果 (*.xlsx) 
- ✅ ETF筛选报告（按日期组织）🆕
- ✅ 资金流向分析报告
- ✅ 人类可读的投资建议和总结

### 📊 data/backtest_results/ - 回测数据目录
```
data/backtest_results/
├── semiconductor_*.json                    # 半导体分析原始数据 🔬
├── ma_backtest_*.json                     # 均线策略回测数据
├── momentum_backtest_*.json               # 动量策略回测数据
├── turtle_backtest_*.json                 # 海龟策略回测数据
├── seykota_backtest_*.json                # 塞柯塔策略回测数据
└── advisor_results_*.json                 # 统一顾问分析数据
```

**📌 存放内容**：
- ✅ JSON格式的原始分析数据
- ✅ 策略回测的详细结果  
- ✅ 机器可读的结构化数据

## 🎯 使用建议

### 📖 对于投资者
- **首选阅读**: `reports/` 目录下的 `.md` 文件
- **重点关注**: `*_summary.md` (快速总结) 和 `*_report.md` (详细报告)
- **投资参考**: 报告中的投资建议和风险提示

### 🔧 对于开发者
- **数据分析**: `data/backtest_results/` 目录下的 `.json` 文件
- **结果验证**: 对比JSON原始数据与报告结论
- **系统集成**: 使用JSON数据进行二次开发

## 📱 统一投资顾问新特性

从统一投资顾问系统开始，JSON文件**自动保存**到 `data/backtest_results/` 目录：

### 🔄 自动路径处理
```bash
# 简单文件名 - 自动保存到 data/backtest_results/
python analyst/advisor.py --mode single --symbol 002049.SZ --save my_analysis.json

# 完整路径 - 保存到指定位置  
python analyst/advisor.py --mode single --symbol 002049.SZ --save /path/to/custom/location.json
```

### 📊 文件命名规范
- **顾问分析**: `advisor_results_YYYYMMDD_HHMMSS.json`
- **行业分析**: `{行业名}_analysis_YYYYMMDD.json` 
- **回测数据**: `{策略名}_backtest_{标的}_{参数}_{时间}.json`

## 🎉 优势

### ✅ 清晰分离
- 报告与数据文件各司其职
- 便于投资者快速获取结论
- 便于开发者深度分析数据

### ✅ 易于管理
- 避免重要报告被数据文件淹没
- 支持自动化文件归档
- 便于版本控制和备份

### ✅ 向后兼容
- 现有脚本和工具无缝支持
- 旧的分析结果保持可访问
- 渐进式迁移策略

## 📂 ETF筛选报告组织

从 2025年10月1日开始，ETF筛选报告迁移到 `reports/etf_screening/` 目录：

### 🆕 新路径结构
```
reports/etf_screening/
└── 20251001/                                    # 按日期自动创建
    ├── etf_screening_INDUSTRY_ETF_*.csv        # 筛选结果CSV
    └── etf_screening_INDUSTRY_ETF_*_report.md  # 详细分析报告
```

### 🔄 路径变化
- **旧路径**: `cache/etf_screener/` （已弃用）
- **新路径**: `reports/etf_screening/YYYYMMDD/` （推荐使用）

### 📋 命名规范
- **CSV文件**: `etf_screening_{配置名}_{时间戳}.csv`
- **报告文件**: `etf_screening_{配置名}_{时间戳}_report.md`
- **时间戳格式**: `YYYYMMDD_HHMMSS`

### 💡 优势
- ✅ 按日期自动归档，便于历史对比
- ✅ 与其他报告统一管理
- ✅ 清晰区分缓存数据与正式报告
- ✅ 支持版本控制和长期保存

---

**📝 更新记录**: 
- 2025-10-01: ETF筛选报告迁移到 reports/etf_screening/ 🆕
- 2025-08-24: 实施新文件组织结构
- 2025-08-24: 统一投资顾问支持自动路径处理
