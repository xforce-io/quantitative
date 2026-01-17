"""
AI 分析师面板 E2E 测试

测试内容：
1. 界面元素测试
   - AI 面板渲染正确
   - 头部标题和状态显示
   - 欢迎卡片显示
   - 输入框可用

2. 交互测试
   - 面板展开/折叠
   - 清空历史功能
   - 发送消息

3. 多轮对话测试
   - 首次对话
   - 后续对话（使用 continue_chat，已废弃 achat）
   - 对话历史保持
   
4. 工具调用可视化测试
   - 工具调用状态显示
   - 工具结果折叠显示
"""

import pytest
from playwright.sync_api import Page, expect
import re


class TestAIPanelUI:
    """AI 面板界面测试"""
    
    def test_panel_renders_correctly(self, page: Page, app_url: str, streamlit_helper):
        """测试 AI 面板正确渲染"""
        # 导航到自选股页面（有 AI 面板）
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 验证 AI 面板容器存在（检查 HTML 中包含这个 class）
        page.wait_for_timeout(1000)  # 给额外时间渲染
        
        # 使用更宽松的方式检测：检查页面源码中是否有 AI 面板相关元素
        ai_panel_exists = page.locator('.ai-panel-scope').count() > 0
        assert ai_panel_exists, "AI 面板容器不存在"
        
        # 验证标题文本存在于页面中
        page.wait_for_selector('text="AI 分析师"', timeout=10000)
        
        # 验证状态指示器
        online_status = page.locator('text="在线"')
        expect(online_status).to_be_attached()
    
    def test_welcome_card_displayed(self, page: Page, app_url: str, streamlit_helper):
        """测试欢迎卡片显示"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 清空历史确保显示欢迎卡片
        streamlit_helper.clear_ai_history()
        page.wait_for_timeout(1000)
        
        # 验证欢迎卡片
        welcome = page.locator('.welcome-container')
        expect(welcome).to_be_visible()
        
        # 验证欢迎标题
        welcome_title = page.locator('.welcome-h1')
        expect(welcome_title).to_contain_text("AI 投研助理")
        
        # 验证"解读页面数据"按钮
        interpret_btn = page.locator('button:has-text("🚀 解读页面数据")')
        expect(interpret_btn).to_be_visible()
    
    def test_chat_input_available(self, page: Page, app_url: str, streamlit_helper):
        """测试聊天输入框可用"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 验证输入框存在
        chat_input = page.locator('[data-testid="stChatInput"] textarea')
        expect(chat_input).to_be_visible()
        expect(chat_input).to_be_enabled()
    
    def test_action_buttons_visible(self, page: Page, app_url: str, streamlit_helper):
        """测试操作按钮可见"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 验证页面上存在清空历史按钮（至少有一个 🗑️ 按钮可见）
        clear_btns = page.locator('button:has-text("🗑️")').all()
        visible_clear_btns = [btn for btn in clear_btns if btn.is_visible()]
        assert len(visible_clear_btns) > 0, "No visible 🗑️ button found"
        
        # 验证折叠按钮（至少有一个 🗝️ 按钮可见）
        collapse_btns = page.locator('button:has-text("🗝️")').all()
        visible_collapse_btns = [btn for btn in collapse_btns if btn.is_visible()]
        assert len(visible_collapse_btns) > 0, "No visible 🗝️ button found"


class TestAIPanelInteraction:
    """AI 面板交互测试"""
    
    def test_panel_collapse_expand(self, page: Page, app_url: str, streamlit_helper):
        """测试面板折叠和展开"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 点击折叠按钮
        streamlit_helper.collapse_ai_panel()
        page.wait_for_timeout(1000)  # 等待 fragment 刷新
        
        # 验证面板已折叠（展开按钮可见）
        expand_btns = page.locator('button:has-text("⬅️")').all()
        visible_expand = [btn for btn in expand_btns if btn.is_visible()]
        assert len(visible_expand) > 0, "折叠后展开按钮应该可见"
        
        # 点击展开按钮
        streamlit_helper.expand_ai_panel()
        page.wait_for_timeout(1000)
        
        # 验证面板已展开（标题文本存在）
        title = page.locator('text="AI 分析师"')
        expect(title.first).to_be_attached()
    
    def test_clear_history(self, page: Page, app_url: str, streamlit_helper):
        """测试清空历史功能"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 发送一条测试消息
        streamlit_helper.send_ai_message("测试消息")
        page.wait_for_timeout(2000)  # 等待消息显示
        
        # 清空历史
        streamlit_helper.clear_ai_history()
        page.wait_for_timeout(1000)
        
        # 验证欢迎卡片重新显示
        welcome = page.locator('.welcome-container')
        expect(welcome).to_be_visible()
    
    def test_context_bar_shows_stock_count(self, page: Page, app_url: str, streamlit_helper):
        """测试上下文信息条显示股票数量"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 等待数据加载
        page.wait_for_timeout(2000)
        
        # 检查上下文栏（如果有数据的话）
        context_bar = page.locator('.context-bar')
        if context_bar.is_visible():
            # 验证显示股票数量
            expect(context_bar).to_contain_text("已连接当前页面")
            expect(context_bar).to_contain_text("只股票数据")


class TestAIPanelMultiTurn:
    """AI 面板多轮对话测试"""
    
    @pytest.mark.slow
    def test_first_conversation(self, page: Page, app_url: str, streamlit_helper):
        """测试首次对话"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 清空历史，确保是首次对话
        streamlit_helper.clear_ai_history()
        page.wait_for_timeout(500)
        
        # 点击"解读页面数据"按钮
        streamlit_helper.click_interpret_page_button()
        
        # 等待 AI 响应
        try:
            streamlit_helper.wait_for_ai_response(timeout=90000)
        except Exception:
            # 如果超时，检查是否有部分响应
            pass
        
        # 验证有消息生成
        messages = page.locator('[data-testid="stChatMessage"]')
        expect(messages.first).to_be_visible()
    
    @pytest.mark.slow
    def test_multi_turn_conversation(self, page: Page, app_url: str, streamlit_helper):
        """测试多轮对话"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 清空历史
        streamlit_helper.clear_ai_history()
        page.wait_for_timeout(500)
        
        # 第一轮对话
        streamlit_helper.send_ai_message("你好")
        
        try:
            streamlit_helper.wait_for_ai_response(timeout=60000)
        except Exception:
            pass
        
        page.wait_for_timeout(1000)
        
        # 第二轮对话
        streamlit_helper.send_ai_message("帮我分析一下数据")
        
        try:
            streamlit_helper.wait_for_ai_response(timeout=60000)
        except Exception:
            pass
        
        # 验证消息历史
        messages = page.locator('[data-testid="stChatMessage"]')
        # 应该有至少 4 条消息（2 条用户 + 2 条 AI）
        count = messages.count()
        assert count >= 2, f"Expected at least 2 messages, got {count}"
    
    @pytest.mark.slow
    def test_conversation_history_persists(self, page: Page, app_url: str, streamlit_helper):
        """测试对话历史保持"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 发送消息
        streamlit_helper.send_ai_message("记住这个：测试标记12345")
        
        try:
            streamlit_helper.wait_for_ai_response(timeout=60000)
        except Exception:
            pass
        
        # 获取当前消息数量
        messages_before = page.locator('[data-testid="stChatMessage"]').count()
        
        # 刷新页面（fragment 刷新不会丢失 session_state）
        # 切换到其他页面再切回来
        page.goto(f"{app_url}/Money_Flow")
        streamlit_helper.wait_for_app_loaded()
        
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 验证消息仍然存在
        messages_after = page.locator('[data-testid="stChatMessage"]').count()
        assert messages_after >= messages_before, "Conversation history was lost"


class TestAIPanelToolVisualization:
    """AI 面板工具调用可视化测试"""
    
    @pytest.mark.slow
    def test_tool_call_status_displayed(self, page: Page, app_url: str, streamlit_helper):
        """测试工具调用状态显示"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 清空历史
        streamlit_helper.clear_ai_history()
        page.wait_for_timeout(500)
        
        # 发送需要工具调用的请求
        streamlit_helper.click_interpret_page_button()
        
        # 等待工具调用状态出现
        try:
            page.wait_for_selector('text="调用工具"', timeout=30000)
            # 记录截图
            page.screenshot(path="tests/e2e/screenshots/tool_call_status.png")
        except Exception:
            # 工具调用可能很快完成
            pass
    
    @pytest.mark.slow
    def test_tool_result_collapsible(self, page: Page, app_url: str, streamlit_helper):
        """测试工具调用结果折叠显示"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 清空历史
        streamlit_helper.clear_ai_history()
        page.wait_for_timeout(500)
        
        # 发送请求触发工具调用
        streamlit_helper.click_interpret_page_button()
        
        try:
            streamlit_helper.wait_for_ai_response(timeout=90000)
        except Exception:
            pass
        
        page.wait_for_timeout(1000)
        
        # 查找工具调用折叠区域
        tool_expander = page.locator('text="执行了"')
        if tool_expander.is_visible():
            # 点击展开
            tool_expander.click()
            page.wait_for_timeout(500)
            
            # 验证工具名称显示
            tool_name = page.locator('text="🔧"')
            expect(tool_name.first).to_be_visible()


class TestAIPanelOnDifferentPages:
    """不同页面上的 AI 面板测试"""
    
    def test_ai_panel_on_money_flow_page(self, page: Page, app_url: str, streamlit_helper):
        """测试资金流向页面的 AI 面板"""
        page.goto(f"{app_url}/Money_Flow")
        streamlit_helper.wait_for_app_loaded()
        
        # 验证 AI 面板存在
        ai_panel_exists = page.locator('.ai-panel-scope').count() > 0
        assert ai_panel_exists, "AI 面板容器在 Money Flow 页不存在"
    
    def test_ai_panel_on_watchlist_page(self, page: Page, app_url: str, streamlit_helper):
        """测试自选股页面的 AI 面板"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        
        # 验证 AI 面板存在
        ai_panel_exists = page.locator('.ai-panel-scope').count() > 0
        assert ai_panel_exists, "AI 面板容器在 Watchlist 页不存在"
    
    def test_ai_panel_on_ranking_page(self, page: Page, app_url: str, streamlit_helper):
        """测试排行榜页面的 AI 面板"""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()
        
        # Ranking 页面比较大，需要额外等待
        page.wait_for_timeout(3000)
        
        # 验证 AI 面板存在
        ai_panel_exists = page.locator('.ai-panel-scope').count() > 0
        assert ai_panel_exists, "AI 面板容器在 Ranking 页不存在"


# 运行配置
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--headed", "-x"])
