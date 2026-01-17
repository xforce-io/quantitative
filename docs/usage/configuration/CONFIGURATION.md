# 配置说明 (Configuration Guide)

本文档详细介绍量化交易系统的配置选项，包括环境变量、YAML配置文件和系统参数的设置方法。

## 🔧 环境变量配置

### 1. 环境变量文件

系统使用统一的环境变量文件 `env_example_unified.txt`，复制为 `.env` 后进行配置：

```bash
cp env_example_unified.txt .env
```

### 2. 数据源配置

#### Tushare配置
```bash
# Tushare API配置（用于A股数据和新闻）
TUSHARE_TOKEN=your_tushare_token_here
```

获取方式：
1. 注册Tushare Pro账户：https://tushare.pro/
2. 获取API Token
3. 配置到环境变量中

#### Yahoo Finance
无需额外配置，系统自动支持全球股票市场数据。

### 3. LLM模型配置

#### 高质量模型（精细分析）
```bash
LLM_API_KEY=your_premium_llm_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4
```

#### 廉价模型（粗分析）
```bash
CHEAP_LLM_API_KEY=your_cheap_llm_api_key_here
CHEAP_LLM_BASE_URL=https://api.deepseek.com/v1
CHEAP_LLM_MODEL=deepseek-chat
```

支持的模型提供商：
- **OpenAI**: GPT-4, GPT-3.5-turbo
- **DeepSeek**: deepseek-chat
- **Claude**: claude-3-sonnet, claude-3-haiku
- **本地模型**: 支持兼容OpenAI API的本地部署

### 4. 数据库配置（可选）

#### MySQL配置
```bash
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=quant_trading
```

#### Redis配置
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
```

### 5. 通知配置（可选）

#### 邮件通知
```bash
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=recipient@gmail.com
```

#### Webhook通知
```bash
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=your_token
WECHAT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_key
```

### 6. 系统配置

#### 运行环境
```bash
ENVIRONMENT=production  # development, testing, production
LOG_LEVEL=INFO         # DEBUG, INFO, WARNING, ERROR
MAX_WORKERS=4          # 并发处理数量
```

#### 安全配置
```bash
SECRET_KEY=your_secret_key_for_encryption
JWT_SECRET=your_jwt_secret_key
JWT_EXPIRATION=3600
```

## 📁 YAML配置文件

### 1. 系统总配置 (system_config.yaml)

```yaml
# 系统版本和模块配置
system:
  version: "1.0"
  modules: ["trading", "news_analysis"]
  
# 默认设置
defaults:
  data_provider: "auto"  # auto, tushare, yahoo
  cache_enabled: true
  log_level: "INFO"
  
# 性能配置
performance:
  max_workers: 4
  chunk_size: 100
  timeout_seconds: 30
```

### 2. 数据源配置 (data_sources.yaml)

```yaml
# 数据提供商配置
providers:
  tushare:
    name: "Tushare Pro"
    priority: 1
    enabled: true
    api_key_env: "TUSHARE_TOKEN"
    rate_limits:
      requests_per_minute: 200
      daily_limit: 10000
    
  yahoo:
    name: "Yahoo Finance"
    priority: 2
    enabled: true
    rate_limits:
      requests_per_minute: 100
      
# 自动切换配置
auto_switching:
  enabled: true
  fallback_order: ["tushare", "yahoo"]
  health_check_interval: 300  # seconds
```

### 3. 交易策略配置 (trading_config.yaml)

```yaml
# 网格策略默认参数
grid_strategy:
  default_params:
    grid_levels: 10
    grid_spacing: 0.02  # 2%
    max_position: 100000
    commission: 0.0003  # 0.03%
    slippage: 0.001     # 0.1%
    
  # 参数优化范围
  optimization_ranges:
    grid_levels: [8, 10, 12, 15]
    grid_spacing: [0.015, 0.02, 0.025, 0.03]
    max_position: [80000, 100000, 120000]

# 风险管理配置
risk_management:
  max_drawdown: 0.15      # 最大回撤15%
  stop_loss: 0.10         # 单笔止损10%
  position_limit: 0.30    # 单个股票最大仓位30%
  volatility_limit: 0.25  # 波动率限制25%

# 回测配置
backtest:
  default_period: "1Y"    # 默认回测周期
  benchmark: "000300.SH"  # 基准指数
  initial_capital: 100000 # 初始资金
```

### 4. 投资品配置 (investment_targets.yaml)

```yaml
# 投资品定义
targets:
  - name: "纳斯达克指数"
    symbol: "NASDAQ"
    keywords: ["NASDAQ", "纳斯达克", "科技股", "QQQ", "TQQQ"]
    category: "index"
    weight: 0.3
    region: "US"
    currency: "USD"
    
  - name: "印度股票"
    symbol: "INDIA_STOCKS"
    keywords: ["印度股市", "孟买", "NSE", "BSE", "印度经济", "INDA"]
    category: "international_equity"
    weight: 0.3
    region: "IN"
    currency: "INR"
    
  - name: "黄金"
    symbol: "GOLD"
    keywords: ["黄金", "Gold", "贵金属", "GLD", "IAU", "黄金价格"]
    category: "commodity"
    weight: 0.25
    region: "Global"
    currency: "USD"
    
  - name: "沪深三百"
    symbol: "CSI300"
    keywords: ["沪深300", "沪深三百", "CSI300", "中国股市", "A股指数"]
    category: "index"
    weight: 0.25
    region: "CN"
    currency: "CNY"

# 分类配置
categories:
  index:
    description: "股票指数"
    risk_level: "medium"
    
  international_equity:
    description: "国际股票"
    risk_level: "high"
    
  commodity:
    description: "商品"
    risk_level: "medium"
```

### 5. 新闻分析配置 (news_analysis_config.yaml)

#### 两阶段分析配置
```yaml
analysis_stages:
  # 阶段1：粗分析
  stage1_coarse:
    enabled: true
    model_type: "cheap"
    batch_size: 50
    max_tokens: 1000
    temperature: 0.3
    relevance_threshold: 0.7
    
  # 阶段2：精细分析
  stage2_fine:
    enabled: true
    model_type: "premium"
    max_articles_per_target: 5
    max_tokens: 2000
    temperature: 0.2
```

#### LLM配置
```yaml
llm_configs:
  cheap_model:
    provider: "openai"
    api_key: "${CHEAP_LLM_API_KEY}"
    base_url: "${CHEAP_LLM_BASE_URL}"
    model: "${CHEAP_LLM_MODEL}"
    max_requests_per_minute: 50
    cost_per_1k_tokens: 0.001
    
  premium_model:
    provider: "openai"
    api_key: "${LLM_API_KEY}"
    base_url: "${LLM_BASE_URL}"
    model: "${LLM_MODEL}"
    max_requests_per_minute: 10
    cost_per_1k_tokens: 0.03
```

#### 数据处理配置
```yaml
data_processing:
  preprocessing:
    clean_html: true
    remove_ads: true
    normalize_text: true
    extract_entities: true
    
  deduplication:
    enabled: true
    method: "title_content"
    similarity_threshold: 0.8
    
  filtering:
    min_content_length: 50
    max_content_length: 10000
    exclude_keywords: ["广告", "推广", "赞助"]
```

#### 缓存配置
```yaml
cache_config:
  enable_stage1_cache: true
  enable_stage2_cache: true
  cache_expiry_hours: 24
  cache_dir: "cache/news_analysis"
  enable_aggressive_cache: true
```

#### 性能配置
```yaml
performance:
  parallel_processing: true
  max_workers: 4
  chunk_size: 10
  rate_limiting:
    stage1_requests_per_minute: 30
    stage2_requests_per_minute: 10
```

## 🔧 配置管理

### 1. 配置验证

#### CLI验证
```bash
# 验证所有配置
python -m quant config validate

# 验证特定配置
python -m quant config validate --config news_analysis_config
```

#### 编程验证
```python
from quant.core.config_manager import ConfigManager

config_manager = ConfigManager()

# 验证特定配置
is_valid = config_manager.validate_config("news_analysis_config")
if not is_valid:
    print("Configuration is invalid")

# 列出所有可用配置
configs = config_manager.list_available_configs()
print("Available configs:", configs)
```

### 2. 配置合并

```python
# 合并多个配置文件
merged_config = config_manager.merge_configs(
    "system_config", 
    "trading_config", 
    "news_analysis_config"
)
```

### 3. 环境变量替换

配置文件中可以使用环境变量：

```yaml
# 在YAML中使用环境变量
api_config:
  api_key: "${LLM_API_KEY}"
  base_url: "${LLM_BASE_URL}"
  model: "${LLM_MODEL}"
```

系统会自动替换为实际的环境变量值。

## 📊 配置最佳实践

### 1. 开发环境配置

```bash
# .env for development
ENVIRONMENT=development
LOG_LEVEL=DEBUG
MAX_WORKERS=2

# 使用免费或廉价的API
CHEAP_LLM_API_KEY=your_dev_api_key
CHEAP_LLM_BASE_URL=https://api.deepseek.com/v1
```

### 2. 生产环境配置

```bash
# .env for production
ENVIRONMENT=production
LOG_LEVEL=INFO
MAX_WORKERS=8

# 使用高质量API
LLM_API_KEY=your_production_api_key
LLM_BASE_URL=https://api.openai.com/v1
```

### 3. 测试环境配置

```bash
# .env for testing
ENVIRONMENT=testing
LOG_LEVEL=WARNING
MAX_WORKERS=1

# 使用模拟数据
USE_MOCK_DATA=true
CACHE_ENABLED=false
```

## 🔒 安全配置

### 1. API密钥管理

- **不要在代码中硬编码API密钥**
- **使用环境变量存储敏感信息**
- **定期轮换API密钥**
- **为不同环境使用不同的密钥**

### 2. 配置文件权限

```bash
# 设置适当的文件权限
chmod 600 .env config/*.yaml
```

### 3. 密钥加密

```python
# 使用加密存储敏感配置
from quant.core.security import encrypt_config, decrypt_config

# 加密配置
encrypted_config = encrypt_config(sensitive_data, SECRET_KEY)

# 解密配置
decrypted_config = decrypt_config(encrypted_config, SECRET_KEY)
```

## 🔄 配置热重载

### 1. 重载配置

```python
# 重新加载特定配置
config_manager.reload_config("news_analysis_config")

# 清理配置缓存
config_manager.clear_cache()
```

### 2. 监控配置变化

```python
from quant.core.config_watcher import ConfigWatcher

# 监控配置文件变化
watcher = ConfigWatcher("config/")
watcher.on_change(lambda path: print(f"Config changed: {path}"))
watcher.start()
```

## 📝 配置模板

### 1. 新投资品模板

```yaml
# 添加新投资品的模板
- name: "新投资品名称"
  symbol: "SYMBOL"
  keywords: ["关键词1", "关键词2", "关键词3"]
  category: "category_type"  # index, equity, commodity, crypto
  weight: 0.2
  region: "地区代码"  # US, CN, EU, Global
  currency: "货币代码"  # USD, CNY, EUR
  
  # 可选配置
  risk_level: "medium"  # low, medium, high
  sector: "行业分类"
  market_cap: "large"   # large, medium, small
```

### 2. 新策略模板

```yaml
# 添加新交易策略的模板
new_strategy:
  name: "策略名称"
  description: "策略描述"
  
  default_params:
    param1: value1
    param2: value2
    
  optimization_ranges:
    param1: [min, max, step]
    param2: [value1, value2, value3]
    
  risk_management:
    max_drawdown: 0.15
    stop_loss: 0.10
```

## 🐛 配置故障排除

### 常见问题

#### 1. 环境变量未生效
```bash
# 检查环境变量是否正确加载
python -c "import os; print(os.getenv('TUSHARE_TOKEN'))"
```

#### 2. 配置文件格式错误
```bash
# 验证YAML语法
python -c "import yaml; yaml.safe_load(open('config/system_config.yaml'))"
```

#### 3. 权限问题
```bash
# 检查文件权限
ls -la .env config/
```

### 调试配置

```python
# 启用配置调试
import logging
logging.getLogger('quant.core.config_manager').setLevel(logging.DEBUG)

# 查看配置加载过程
config_manager = ConfigManager()
config = config_manager.load_config("system_config")
```

## 📚 相关文档

- [快速开始指南](GETTING_STARTED.md)
- [交易策略指南](TRADING_GUIDE.md)
- [新闻分析指南](NEWS_ANALYSIS_GUIDE.md)
- [技术架构文档](ARCHITECTURE.md)

## ⚠️ 注意事项

1. **备份配置**: 修改配置前请备份原始文件
2. **测试配置**: 在生产环境使用前请在测试环境验证
3. **版本控制**: 不要将包含敏感信息的.env文件提交到版本控制
4. **文档同步**: 修改配置时请同步更新相关文档 