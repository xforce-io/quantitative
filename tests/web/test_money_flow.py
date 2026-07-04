"""E2E tests for the Dashboard page.

The previous Money Flow page was replaced by the decision Dashboard.  These
tests keep the legacy file name but verify the current first page.
"""

from playwright.sync_api import Page, expect


class TestDashboardPageLoad:
    """Basic page load and layout."""

    def test_page_title(self, page: Page, app_url: str, streamlit_helper):
        """Dashboard should display the decision cockpit title."""
        page.goto(f"{app_url}/Dashboard")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("决策驾驶舱").first).to_be_attached()

    def test_ai_panel_removed(self, page: Page, app_url: str, streamlit_helper):
        """Dashboard should not render the removed AI analyst panel."""
        page.goto(f"{app_url}/Dashboard")
        streamlit_helper.wait_for_app_loaded()

        assert page.get_by_text("AI 分析师").count() == 0


class TestDashboardSections:
    """Dashboard core sections."""

    def test_verdict_sections_present(self, page: Page, app_url: str, streamlit_helper):
        """Dashboard should show the main decision sections."""
        page.goto(f"{app_url}/Dashboard")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("决策总览").first).to_be_attached()
        expect(page.get_by_text("资产池状态").first).to_be_attached()
        expect(page.get_by_text("持仓提示").first).to_be_attached()

    def test_pool_cards_or_warning_render(self, page: Page, app_url: str, streamlit_helper):
        """Dashboard should render pool content or a recoverable warning."""
        page.goto(f"{app_url}/Dashboard")
        streamlit_helper.wait_for_app_loaded()
        page.wait_for_timeout(3000)

        has_pool_content = (
            page.get_by_text("A 股").count() > 0
            or page.get_by_text("美股").count() > 0
            or page.get_by_text("无法获取资产池数据").count() > 0
        )
        assert has_pool_content
