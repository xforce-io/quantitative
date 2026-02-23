# AI 分析师 E2E 测试套件

本目录包含 AI 分析师面板的端到端 (E2E) 自动化测试，使用 **Playwright** 进行浏览器自动化。

## 📋 测试覆盖

### 1. UI 测试 (`TestAIPanelUI`)
- ✅ `test_panel_renders_correctly` - AI 面板正确渲染
- ✅ `test_welcome_card_displayed` - 欢迎卡片显示
- ✅ `test_chat_input_available` - 聊天输入框可用
- ✅ `test_action_buttons_visible` - 操作按钮可见

### 2. 交互测试 (`TestAIPanelInteraction`)
- ✅ `test_panel_collapse_expand` - 面板折叠/展开
- ✅ `test_clear_history` - 清空历史功能
- ✅ `test_context_bar_shows_stock_count` - 上下文信息栏显示

### 3. 多轮对话测试 (`TestAIPanelMultiTurn`) [标记为 slow]
- ✅ `test_first_conversation` - 首次对话
- ❓ `test_multi_turn_conversation` - 多轮对话（依赖 AI 服务）
- ❓ `test_conversation_history_persists` - 对话历史保持

### 4. 工具调用可视化测试 (`TestAIPanelToolVisualization`) [标记为 slow]
- ❓ `test_tool_call_status_displayed` - 工具调用状态显示
- ❓ `test_tool_result_collapsible` - 工具结果折叠显示

### 5. 跨页面测试 (`TestAIPanelOnDifferentPages`)
- ✅ `test_ai_panel_on_money_flow_page` - 资金流向页面
- ✅ `test_ai_panel_on_watchlist_page` - 自选股页面
- ✅ `test_ai_panel_on_ranking_page` - 排行榜页面

## 🚀 运行测试

### 前置条件
确保 Streamlit 服务正在运行：
```bash
./scripts/run_web.sh start
```

### 快速测试 (不含 AI 调用)
```bash
# 运行所有非 slow 标记的测试
uv run pytest tests/e2e/test_ai_panel.py -m "not slow" -v

# 只运行 UI 测试
uv run pytest tests/e2e/test_ai_panel.py -k "TestAIPanelUI" -v

# 只运行交互测试
uv run pytest tests/e2e/test_ai_panel.py -k "TestAIPanelInteraction" -v
```

### 完整测试 (含 AI 调用，较慢)
```bash
# 运行所有测试
uv run pytest tests/e2e/test_ai_panel.py -v

# 使用有头模式（显示浏览器）
uv run pytest tests/e2e/test_ai_panel.py --headed -v

# 运行多轮对话测试
uv run pytest tests/e2e/test_ai_panel.py -k "TestAIPanelMultiTurn" -v
```

### 使用便捷脚本
```bash
# 快速测试（无头模式）
python tests/e2e/run_tests.py --ui-only

# 有头模式查看执行过程
python tests/e2e/run_tests.py --headed --ui-only

# 生成测试报告
python tests/e2e/run_tests.py --report

# 多轮对话测试
python tests/e2e/run_tests.py --multi-turn
```

## 📁 文件结构

```
tests/e2e/
├── conftest.py          # Pytest fixtures 和辅助类
├── test_ai_panel.py     # AI 面板测试用例
├── run_tests.py         # 便捷测试运行脚本
├── screenshots/         # 测试截图目录
└── README.md            # 本文档
```

## 🔧 技术栈

- **Playwright** - 浏览器自动化
- **pytest-playwright** - Playwright 的 pytest 插件
- **pytest** - 测试框架

## 💡 开发提示

### 添加新测试
1. 在 `test_ai_panel.py` 中添加测试方法
2. 使用 `streamlit_helper` fixture 进行常用操作
3. 耗时测试添加 `@pytest.mark.slow` 标记

### Streamlit 特殊处理
- Streamlit 组件通过 `st.markdown` 注入的 HTML 不会包含 Streamlit 的按钮等组件
- 使用 `.all()` + 可见性检查来处理多个同名按钮
- 使用 `wait_for_timeout()` 等待 Streamlit 的 fragment 刷新

### 调试技巧
```bash
# 有头模式 + 慢速执行
uv run pytest tests/e2e/test_ai_panel.py -k "test_name" --headed --slowmo 500

# 失败时暂停
uv run pytest tests/e2e/test_ai_panel.py -k "test_name" --headed --pause-on-failure
```
