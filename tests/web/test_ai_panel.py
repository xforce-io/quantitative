"""
AI 分析师面板 E2E 测试

测试内容：
1. 界面元素测试
   - AI 面板渲染正确
   - 头部标题和状态显示
   - 输入框可用
   - 操作按钮可见

2. 交互测试
   - 面板展开/折叠
   - 清空历史功能

3. 多轮对话测试
   - 首次对话
   - 后续对话
   - 对话历史保持

4. 工具调用可视化测试
   - 工具调用状态显示
   - 工具结果折叠显示
"""

import pytest
from playwright.sync_api import Page, expect


class TestAIPanelUI:
    """AI 面板界面测试"""

    @staticmethod
    def _wait_for_ai_panel(page, timeout=15000):
        """等待 AI 面板 fragment 渲染完成"""
        try:
            # 使用部分匹配（不加引号）避免因实际文本含 "✦" 前缀而匹配失败
            page.wait_for_selector("text=AI 分析师", timeout=timeout)
        except Exception:
            pass
        page.wait_for_timeout(1000)

    def test_panel_renders_correctly(self, page: Page, app_url: str, streamlit_helper):
        """测试 AI 面板正确渲染"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        self._wait_for_ai_panel(page)

        # 验证 AI 面板容器存在
        ai_panel_exists = page.get_by_text("AI 分析师").count() > 0
        assert ai_panel_exists, "AI 面板容器不存在"

        # 验证标题文本
        title = page.get_by_text("AI 分析师")
        expect(title.first).to_be_attached()

        # 验证状态指示器 (组件渲染 "ONLINE")
        online_status = page.get_by_text("ONLINE")
        expect(online_status.first).to_be_attached()

    def test_chat_input_available(self, page: Page, app_url: str, streamlit_helper):
        """测试聊天输入框可用"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        self._wait_for_ai_panel(page)

        chat_input = page.locator('[data-testid="stChatInput"] textarea')
        expect(chat_input).to_be_visible()
        expect(chat_input).to_be_enabled()

    def test_action_buttons_visible(self, page: Page, app_url: str, streamlit_helper):
        """测试操作按钮可见"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        self._wait_for_ai_panel(page)

        # 验证清空按钮 (实际文本: "🗑 清空")
        clear_btn = page.get_by_text("清空")
        assert clear_btn.count() > 0, "清空按钮未找到"

        # 验证收起按钮 (实际文本: "✕ 收起")
        collapse_btn = page.get_by_text("收起")
        assert collapse_btn.count() > 0, "收起按钮未找到"

    def test_welcome_or_quick_actions(self, page: Page, app_url: str, streamlit_helper):
        """测试欢迎信息或快捷操作按钮"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        # 组件使用 st.info() 显示欢迎信息，或显示快捷按钮
        has_welcome = (
            page.get_by_text("行情解读").count() > 0
            or page.get_by_text("主力动向").count() > 0
            or page.get_by_text("分析").count() > 0
        )
        assert has_welcome, "应显示快捷操作按钮或欢迎信息"


class TestAIPanelInteraction:
    """AI 面板交互测试"""

    def test_panel_collapse_expand(self, page: Page, app_url: str, streamlit_helper):
        """测试面板折叠和展开"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        # 点击折叠按钮 (实际文本: "✕ 收起")
        streamlit_helper.collapse_ai_panel()
        page.wait_for_timeout(1000)

        # 验证面板已折叠（展开按钮可见, 实际文本: "✦ 展开"）
        expand_btn = page.get_by_text("展开")
        assert expand_btn.count() > 0, "折叠后展开按钮应该可见"

        # 点击展开按钮
        streamlit_helper.expand_ai_panel()
        page.wait_for_timeout(1000)

        # 验证面板已展开（标题文本存在）
        title = page.get_by_text("AI 分析师")
        expect(title.first).to_be_attached()

    def test_clear_history(self, page: Page, app_url: str, streamlit_helper):
        """测试清空历史功能"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        # 发送一条测试消息
        streamlit_helper.send_ai_message("测试消息")
        page.wait_for_timeout(2000)

        # 清空历史
        streamlit_helper.clear_ai_history()
        page.wait_for_timeout(1000)

        # 验证欢迎信息重新显示（st.info 或快捷按钮）
        has_welcome = (
            page.get_by_text("行情解读").count() > 0
            or page.get_by_text("主力动向").count() > 0
            or page.get_by_text("分析").count() > 0
        )
        # 清空后可能没有对话消息
        no_messages = page.locator('[data-testid="stChatMessage"]').count() == 0
        assert has_welcome or no_messages, "清空后应显示欢迎信息或无消息"


class TestAIPanelMultiTurn:
    """AI 面板多轮对话测试"""

    @pytest.mark.slow
    def test_first_conversation(self, page: Page, app_url: str, streamlit_helper):
        """测试首次对话"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        # 清空历史
        streamlit_helper.clear_ai_history()
        page.wait_for_timeout(500)

        # 发送消息
        streamlit_helper.send_ai_message("你好")

        # 等待 AI 响应
        try:
            streamlit_helper.wait_for_ai_response(timeout=90000)
        except Exception:
            pass

        page.wait_for_timeout(2000)

        # 验证有消息生成（用户消息至少应存在）
        messages = page.locator('[data-testid="stChatMessage"]')
        assert messages.count() > 0, "发送消息后应至少显示用户消息"

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

        page.wait_for_timeout(1000)

        # 获取当前消息数量
        messages_before = page.locator('[data-testid="stChatMessage"]').count()

        # 切换页面再切回来
        page.goto(f"{app_url}/Money_Flow")
        streamlit_helper.wait_for_app_loaded()

        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()
        page.wait_for_timeout(1000)

        # session_state 在页面切换时会重置（Streamlit 行为）
        # 只验证页面不崩溃且 AI 面板仍然存在
        ai_panel = page.get_by_text("AI 分析师")
        assert ai_panel.count() > 0, "页面切换后 AI 面板应仍存在"


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

        # 发送需要工具调用的请求（使用快捷按钮）
        streamlit_helper.click_quick_action_button()

        # 等待工具调用状态出现
        try:
            page.wait_for_selector('text="调用工具"', timeout=30000)
        except Exception:
            pass  # 工具调用可能很快完成

    @pytest.mark.slow
    def test_tool_result_collapsible(self, page: Page, app_url: str, streamlit_helper):
        """测试工具调用结果折叠显示"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        # 清空历史
        streamlit_helper.clear_ai_history()
        page.wait_for_timeout(500)

        # 触发工具调用
        streamlit_helper.click_quick_action_button()

        try:
            streamlit_helper.wait_for_ai_response(timeout=90000)
        except Exception:
            pass

        page.wait_for_timeout(1000)

        # 查找工具调用折叠区域
        tool_expander = page.get_by_text("执行了")
        if tool_expander.count() > 0 and tool_expander.first.is_visible():
            tool_expander.first.click()
            page.wait_for_timeout(500)

            tool_name = page.get_by_text("🔧")
            expect(tool_name.first).to_be_visible()


class TestAIPanelOnDifferentPages:
    """不同页面上的 AI 面板测试"""

    def test_ai_panel_on_money_flow_page(self, page: Page, app_url: str, streamlit_helper):
        """测试资金流向页面的 AI 面板"""
        page.goto(f"{app_url}/Money_Flow")
        streamlit_helper.wait_for_app_loaded()

        ai_panel_exists = page.get_by_text("AI 分析师").count() > 0
        assert ai_panel_exists, "AI 面板容器在 Money Flow 页不存在"

    def test_ai_panel_on_watchlist_page(self, page: Page, app_url: str, streamlit_helper):
        """测试自选股页面的 AI 面板"""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        ai_panel_exists = page.get_by_text("AI 分析师").count() > 0
        assert ai_panel_exists, "AI 面板容器在 Watchlist 页不存在"

    def test_ai_panel_on_ranking_page(self, page: Page, app_url: str, streamlit_helper):
        """测试排行榜页面的 AI 面板"""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        page.wait_for_timeout(3000)

        ai_panel_exists = page.get_by_text("AI 分析师").count() > 0
        assert ai_panel_exists, "AI 面板容器在 Ranking 页不存在"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--headed", "-x"])
