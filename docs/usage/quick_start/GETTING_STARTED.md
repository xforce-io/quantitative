# 快速开始指南 Getting Started Guide

本指南将帮助您快速设置和使用重构后的量化交易系统。

## 🚀 环境准备

### 1. 系统要求
- Python 3.8 或更高版本
- 建议使用虚拟环境

### 2. 安装依赖
```bash
# 克隆项目（如果尚未克隆）
git clone <your-repo-url>
cd quantitative_trading

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
```

### 3. 环境变量配置
```bash
# 复制环境变量示例文件
cp env_example_unified.txt .env

# 编辑 .env 文件，配置必要的API密钥
nano .env  # 或使用其他编辑器
```

重要的环境变量：
```bash
# Tushare数据源（如需要API数据）
TUSHARE_TOKEN=your_tushare_token_here

# 大语言模型配置
LLM_API_KEY=your_premium_llm_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4

# 廉价模型配置（可选）
CHEAP_LLM_API_KEY=your_cheap_llm_api_key_here
CHEAP_LLM_BASE_URL=https://api.deepseek.com/v1
CHEAP_LLM_MODEL=deepseek-chat
```

## 📋 配置验证

### 1. 验证系统配置
```bash
# 验证所有配置文件
python -m quant config validate

# 列出可用配置
python -m quant config list

# 验证特定配置
python -m quant config validate --config system_config
```

预期输出：
```
INFO:__main__:Validating all configurations...
INFO:__main__:  data_sources: ✓
INFO:__main__:  investment_analysis: ✓
INFO:__main__:  investment_targets: ✓
INFO:__main__:  news_analysis_config: ✓
INFO:__main__:  system_config: ✓
INFO:__main__:  trading_config: ✓
INFO:__main__:All configurations are valid ✓
```

### 2. 运行系统演示
```bash
# 运行完整的系统演示
python demo/unified_system_demo.py
```

## 📰 新闻分析功能

### 1. 准备新闻数据
确保您有新闻数据文件在 `data/news/` 目录下：
```bash
# 查看数据目录结构
ls -la data/news/

# 示例数据文件格式（JSON）
# data/news/20241221_news.json
```

### 2. 运行新闻分析
```bash
# 基本新闻分析
python -m quant news analyze

# 指定投资品和天数
python -m quant news analyze --targets nasdaq,gold --days 7

# 指定输出格式
python -m quant news analyze --format markdown

# 查看帮助
python -m quant news analyze --help
```

### 3. 查看分析结果
```bash
# 分析结果保存在 reports/ 目录
ls -la reports/

# 按日期和类型组织
# reports/20241221/news_analysis/
```

## 🔧 配置自定义

### 1. 投资品配置
编辑 `config/investment_targets.yaml`：
```yaml
targets:
  - name: "自定义投资品"
    symbol: "CUSTOM"
    keywords: ["关键词1", "关键词2"]
    weight: 0.2
    category: "custom"
```

### 2. 新闻分析配置
编辑 `config/news_analysis_config.yaml`：
```yaml
# 调整分析参数
analysis_stages:
  stage1_coarse:
    batch_size: 20  # 减少批量大小
    max_tokens: 500  # 降低token使用
```

### 3. 数据源配置
编辑 `config/data_sources.yaml`：
```yaml
# 启用/禁用数据源
providers:
  tushare:
    enabled: true
  yahoo:
    enabled: false
```

## 📊 报告和输出

### 1. 报告格式
支持的格式：
- `json`: 结构化数据，便于程序处理
- `markdown`: 人类可读格式
- `html`: 网页格式，支持丰富样式

### 2. 报告结构
```
reports/
├── 20241221/                    # 按日期分组
│   ├── news_analysis/           # 新闻分析报告
│   │   ├── multi_target_*.json
│   │   └── multi_target_*.md
│   └── daily_summary/           # 日度总结
└── charts/                      # 图表文件
```

### 3. 自定义报告
```python
from quant.core.config_manager import ConfigManager
from quant.core.data_manager import DataManager

# 创建自定义报告
config_manager = ConfigManager()
data_manager = DataManager(config_manager)

report_data = {
    "title": "自定义报告",
    "content": "报告内容"
}

report_path = data_manager.save_report(
    report_data=report_data,
    report_type="custom",
    target="my_analysis",
    format_type="markdown"
)
```

## 🛠️ 故障排除

### 1. 常见问题

#### 问题：配置验证失败
```bash
ERROR:quant.core.config_manager:Missing required section in news_analysis config: llm_configs
```

**解决方案**：检查配置文件格式，确保所有必需字段都存在。

#### 问题：找不到新闻数据
```bash
WARNING:__main__:No news data found
```

**解决方案**：
1. 检查 `data/news/` 目录是否存在
2. 确保有有效的JSON格式新闻文件
3. 检查文件时间戳（只处理最近几天的文件）

#### 问题：API密钥未配置
```bash
KeyError: 'LLM_API_KEY'
```

**解决方案**：
1. 确保 `.env` 文件存在
2. 检查环境变量名称是否正确
3. 重启终端会话以加载新的环境变量

### 2. 调试模式
```bash
# 启用详细日志
export LOG_LEVEL=DEBUG
python -m quant news analyze --days 1

# 查看系统日志
tail -f logs/system.log
```

### 3. 清理缓存
```bash
# 清理所有缓存
python -m quant cache clear

# 清理特定类型缓存
python -m quant cache clear --type news
```

## 📚 下一步

1. **阅读详细文档**：
   - [配置说明](CONFIGURATION.md)
   - [API参考](API_REFERENCE.md)
   - [架构文档](ARCHITECTURE.md)

2. **探索示例**：
   ```bash
   # 查看所有演示脚本
   ls demo/
   
   # 运行特定示例
   python demo/investment_news_analysis_demo.py
   ```

3. **自定义开发**：
   - 添加新的投资品
   - 自定义分析逻辑
   - 集成新的数据源

4. **性能优化**：
   - 调整缓存策略
   - 优化API调用频率
   - 配置并行处理

## 💬 获取帮助

如果遇到问题：
1. 查看 [常见问题解答](FAQ.md)
2. 查看项目 Issues
3. 查看日志文件了解详细错误信息

---

恭喜！您已经成功设置了量化交易系统。开始探索强大的分析功能吧！ 🎉 