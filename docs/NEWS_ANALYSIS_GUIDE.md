# 新闻分析指南 (News Analysis Guide)

本指南介绍量化交易系统中的新闻收集和投资分析功能，包括两阶段分析流程、配置方法和最佳实践。

## 🎯 核心功能

### 1. 新闻收集系统
- **多数据源支持**: 从Tushare Pro、新浪财经、东方财富等多源收集财经新闻
- **统一数据格式**: 支持API和本地文件两种数据来源，统一中间格式存储
- **智能去重**: 基于标题和内容的智能去重机制
- **关键词匹配**: 根据投资品关键词自动筛选相关新闻

### 2. 两阶段分析系统
- **粗分析阶段**: 使用廉价模型进行情感分析、相关性评分和关键词提取
- **精细分析阶段**: 使用高质量模型进行深度分析和投资建议生成
- **成本优化**: 通过两阶段设计显著降低LLM使用成本
- **质量保证**: 精细分析确保投资建议的准确性和可靠性

### 3. 投资分析维度
- **市场情绪**: positive/negative/neutral
- **价格影响**: strong_positive/positive/neutral/negative/strong_negative
- **风险评估**: low/medium/high
- **投资建议**: strong_buy/buy/hold/sell/strong_sell
- **置信度**: 0.0-1.0

## 🚀 快速开始

### 1. 环境配置

#### 环境变量设置
```bash
# 复制环境变量模板
cp env_example_unified.txt .env

# 编辑.env文件，配置以下变量：
# 高质量模型配置（用于精细分析）
LLM_API_KEY=your_premium_llm_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4

# 廉价模型配置（用于粗分析）
CHEAP_LLM_API_KEY=your_cheap_llm_api_key_here
CHEAP_LLM_BASE_URL=https://api.deepseek.com/v1
CHEAP_LLM_MODEL=deepseek-chat

# Tushare配置
TUSHARE_TOKEN=your_tushare_token_here
```

#### 投资品配置
在 `config/investment_targets.yaml` 中配置关注的投资品：

```yaml
targets:
  - name: "纳斯达克指数"
    symbol: "NASDAQ"
    keywords: ["NASDAQ", "纳斯达克", "科技股", "QQQ", "TQQQ"]
    category: "index"
    weight: 0.3
    
  - name: "印度股票"
    symbol: "INDIA_STOCKS"
    keywords: ["印度股市", "孟买", "NSE", "BSE", "印度经济"]
    category: "international_equity"
    weight: 0.3
    
  - name: "黄金"
    symbol: "GOLD"
    keywords: ["黄金", "Gold", "贵金属", "GLD", "IAU"]
    category: "commodity"
    weight: 0.25
```

### 2. 基础使用

#### CLI命令行方式（推荐）
```bash
# 收集新闻数据
python -m quant news collect --sources sina,eastmoney --days 3

# 分析新闻数据
python -m quant news analyze --targets nasdaq,gold,csi300 --mode two_stage

# 生成报告
python -m quant news analyze --output reports/ --format markdown
```

#### 编程接口方式

##### 新闻收集
```python
from quant.news import UnifiedNewsCollector

# 初始化收集器
collector = UnifiedNewsCollector()

# 收集所有新闻
all_news = collector.collectAllNews()
print(f"收集到 {len(all_news)} 篇新闻")

# 根据投资品收集相关新闻
target_news = collector.collectForInvestmentTargets()
for target_name, articles in target_news.items():
    print(f"{target_name}: {len(articles)} 篇相关文章")
```

##### 两阶段分析
```python
from quant.news import TwoStageNewsAnalyzer

# 初始化分析器
analyzer = TwoStageNewsAnalyzer()

# 运行完整分析流程
result = analyzer.runFullAnalysis()

# 查看投资建议
recommendations = result.get('overall_recommendations', {})
for symbol, rec in recommendations.items():
    print(f"{symbol}: {rec['recommended_action']} (置信度: {rec['confidence']:.1%})")
```

## 📊 分析流程详解

### 阶段1：粗分析（廉价模型）

#### 处理任务
1. **情感分析**: 判断新闻的整体情感倾向
2. **相关性评分**: 评估新闻与各投资品的相关性
3. **关键词提取**: 提取新闻中的重要关键词
4. **分类标记**: 对新闻进行主题分类
5. **摘要生成**: 生成新闻摘要

#### 配置参数
```yaml
stage1_coarse:
  enabled: true
  model_type: "cheap"
  batch_size: 50
  max_tokens: 1000
  temperature: 0.3
  relevance_threshold: 0.7  # 进入第二阶段的相关性阈值
```

### 阶段2：精细分析（高质量模型）

#### 处理任务
1. **深度情感分析**: 更精确的情感分析和强度评估
2. **市场影响评估**: 评估新闻对市场价格的潜在影响
3. **投资建议生成**: 基于分析结果生成具体投资建议
4. **风险分析**: 识别和评估相关投资风险

#### 配置参数
```yaml
stage2_fine:
  enabled: true
  model_type: "premium"
  relevance_threshold: 0.7
  max_articles_per_target: 5
  max_tokens: 2000
  temperature: 0.2
```

## 🔧 高级配置

### 1. 数据源配置

#### 新闻源优先级
```yaml
news_sources:
  tushare_sources:
    - "sina"          # 新浪财经 - 每天2次
    - "eastmoney"     # 东方财富 - 每分钟1次
    - "wallstreetcn"  # 华尔街见闻 - 每分钟1次
  
  search_config:
    max_articles_per_target: 10
    days_back: 3
    languages: ["en", "zh"]
    batch_delay_seconds: 120
```

#### 外部数据源
```yaml
data_sources:
  external_crawler:
    enabled: true
    path: "/path/to/external/news"
    format: "json"
```

### 2. 缓存优化

#### 缓存配置
```yaml
cache_config:
  news_cache_days: 14
  analysis_cache_days: 7
  enable_aggressive_cache: true
  cache_dir: "cache/news_analysis"
```

#### 缓存管理
```bash
# 查看缓存状态
python -m quant cache stats

# 清理新闻分析缓存
python -m quant cache clear --type news

# 清理所有缓存
python -m quant cache clear --type all
```

### 3. 性能优化

#### 并行处理配置
```yaml
performance:
  parallel_processing: true
  max_workers: 4
  chunk_size: 10
  rate_limiting:
    stage1_requests_per_minute: 30
    stage2_requests_per_minute: 10
```

#### API限制管理
```yaml
api_limits:
  tushare_pro:
    daily_limit: 2
    minute_limit: 1
    retry_delay: 300
    enable_backoff: true
```

## 📈 报告生成

### 1. 日报格式

#### Markdown报告示例
```markdown
# 投资分析日报

**报告日期**: 2024-01-15
**分析时间**: 2024-01-15T09:00:00
**分析周期**: 最近 3 天

## 整体概览
- **市场展望**: optimistic
- **投资建议分布**: {'buy': 2, 'hold': 1}
- **市场情绪分布**: {'positive': 2, 'neutral': 1}

## 个股分析

### 纳斯达克指数 (NASDAQ)
- **类别**: index
- **新闻数量**: 15
- **市场情绪**: positive
- **投资建议**: buy
- **置信度**: 0.85
- **关键新闻**: 
  - 科技股强势反弹，纳指创新高
  - AI概念股集体上涨
```

#### JSON报告结构
```json
{
  "report_metadata": {
    "generated_at": "2024-01-15T09:00:00",
    "analysis_period": "2024-01-12 to 2024-01-15",
    "total_articles_analyzed": 45
  },
  "overall_summary": {
    "market_outlook": "optimistic",
    "recommendation_distribution": {"buy": 2, "hold": 1},
    "sentiment_distribution": {"positive": 2, "neutral": 1}
  },
  "target_analysis": {
    "NASDAQ": {
      "recommendation": "buy",
      "confidence": 0.85,
      "sentiment": "positive",
      "key_factors": ["tech rally", "AI momentum"]
    }
  }
}
```

### 2. 自定义报告

#### 报告模板配置
```yaml
reporting:
  generate_daily_report: true
  generate_source_analysis: true
  generate_trend_analysis: true
  output_formats: ["markdown", "json", "html"]
  report_dir: "reports/news_analysis"
  
  custom_templates:
    daily_template: "templates/daily_report.md"
    summary_template: "templates/summary_report.md"
```

## 🎯 最佳实践

### 1. 成本控制

#### 模型选择策略
- **粗分析**: 使用成本较低的模型（如GPT-3.5、DeepSeek等）
- **精细分析**: 使用高质量模型（如GPT-4、Claude等）
- **批量处理**: 合理设置批次大小，提高处理效率

#### 缓存策略
- **启用激进缓存**: 避免重复分析相同新闻
- **合理设置过期时间**: 平衡数据新鲜度和缓存效果
- **分层缓存**: 对不同类型的数据设置不同的缓存策略

### 2. 质量控制

#### 置信度阈值
```yaml
quality_control:
  min_confidence_score: 0.6
  enable_human_review: false
  alert_thresholds:
    high_relevance: 0.9
    extreme_sentiment: 0.8
```

#### 数据验证
- **内容长度检查**: 过滤过短或过长的新闻
- **关键词过滤**: 排除广告和推广内容
- **重复检测**: 基于相似度的去重机制

### 3. 监控和告警

#### 异常检测
```python
# 监控分析质量
def monitor_analysis_quality(results):
    low_confidence_count = sum(1 for r in results if r['confidence'] < 0.6)
    if low_confidence_count > len(results) * 0.3:
        logger.warning("High proportion of low-confidence results")
    
    # 监控极端情感
    extreme_sentiment = [r for r in results if abs(r['sentiment_score']) > 0.8]
    if extreme_sentiment:
        logger.info(f"Detected {len(extreme_sentiment)} extreme sentiment articles")
```

#### 性能监控
```python
# 监控API使用情况
def monitor_api_usage():
    daily_usage = get_daily_api_usage()
    if daily_usage > API_DAILY_LIMIT * 0.8:
        logger.warning("Approaching daily API limit")
```

## 🔄 定时任务

### 1. 自动化分析

#### 生产模式
```bash
# 每天9:00和18:00自动分析
0 9,18 * * * cd /path/to/project && python -m quant news analyze --mode two_stage
```

#### 测试模式
```bash
# 每2分钟执行一次（用于测试）
*/2 * * * * cd /path/to/project && python -m quant news analyze --mode simple
```

### 2. 调度器配置

```python
from quant.news import ScheduledAnalyzer

# 创建调度器
scheduler = ScheduledAnalyzer()

# 设置生产模式
scheduler.set_production_mode(
    analysis_times=["09:00", "18:00"],
    timezone="Asia/Shanghai"
)

# 启动调度器
scheduler.start()
```

## 📚 扩展功能

### 1. 自定义分析器

```python
from quant.news.analyzers.base_analyzer import BaseAnalyzer

class CustomNewsAnalyzer(BaseAnalyzer):
    def __init__(self, **config):
        super().__init__(**config)
    
    def analyze_sentiment(self, text):
        # 自定义情感分析逻辑
        pass
    
    def generate_recommendation(self, analysis_result):
        # 自定义投资建议生成逻辑
        pass
```

### 2. 新数据源集成

```python
from quant.news.collectors.base_collector import BaseCollector

class CustomNewsCollector(BaseCollector):
    def __init__(self, **config):
        super().__init__(**config)
    
    def collect_news(self, start_date, end_date):
        # 自定义新闻收集逻辑
        pass
    
    def parse_article(self, raw_data):
        # 自定义文章解析逻辑
        pass
```

## 📝 故障排除

### 常见问题

#### 1. API限制问题
```
错误: API rate limit exceeded
解决: 调整api_limits配置，增加retry_delay
```

#### 2. 缓存问题
```
错误: Cache corruption detected
解决: 清理缓存 python -m quant cache clear
```

#### 3. 模型配置问题
```
错误: Invalid model configuration
解决: 检查环境变量和模型配置
```

### 调试模式

```bash
# 启用调试日志
export LOG_LEVEL=DEBUG
python -m quant news analyze --targets nasdaq --days 1
```

## 📚 相关文档

- [快速开始指南](GETTING_STARTED.md)
- [交易策略指南](TRADING_GUIDE.md)
- [配置说明](CONFIGURATION.md)
- [技术架构文档](ARCHITECTURE.md)

## ⚠️ 免责声明

本系统仅提供投资分析和建议参考，不构成具体的投资指导。投资有风险，决策需谨慎。请结合多方面信息和专业建议进行投资决策。新闻分析结果可能存在偏差，请谨慎使用。 