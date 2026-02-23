"""
E2E tests for Watchlist page.

Covers: page layout, sidebar stock/industry management,
stock monitoring tab, industry monitoring tab, detail cards.
"""

import pytest
from playwright.sync_api import Page, expect


class TestWatchlistPageLoad:
    """Basic page load and structure."""

    def test_page_title(self, page: Page, app_url: str, streamlit_helper):
        """Watchlist page should display the dashboard title."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        title = page.get_by_text("自选监控驾驶舱")
        expect(title.first).to_be_attached()

    def test_sidebar_control_panel(self, page: Page, app_url: str, streamlit_helper):
        """Sidebar should show the control panel header."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        panel = page.get_by_text("指挥面板")
        expect(panel.first).to_be_attached()

    def test_ai_panel_present(self, page: Page, app_url: str, streamlit_helper):
        """AI panel should be integrated."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        ai_panel = page.get_by_text("AI 分析师")
        assert ai_panel.count() > 0


class TestWatchlistSidebar:
    """Sidebar stock and industry management widgets."""

    def test_stock_management_expander(self, page: Page, app_url: str, streamlit_helper):
        """Sidebar should have stock management expander."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        expander = page.get_by_text("管理关注股票")
        expect(expander.first).to_be_attached()

    def test_industry_management_expander(self, page: Page, app_url: str, streamlit_helper):
        """Sidebar should have industry management expander."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        expander = page.get_by_text("管理关注行业")
        expect(expander.first).to_be_attached()

    def test_period_selector_present(self, page: Page, app_url: str, streamlit_helper):
        """Time period selector should be in sidebar."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        period = page.get_by_text("时间维度")
        expect(period.first).to_be_attached()


class TestWatchlistTabs:
    """Main content tabs: stock monitoring + industry monitoring."""

    def test_stock_monitoring_tab_exists(self, page: Page, app_url: str, streamlit_helper):
        """Stock monitoring tab should be present."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        tab = page.get_by_text("个股监控")
        expect(tab.first).to_be_attached()

    def test_industry_monitoring_tab_exists(self, page: Page, app_url: str, streamlit_helper):
        """Industry monitoring tab should be present."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        tab = page.get_by_text("赛道监控")
        expect(tab.first).to_be_attached()

    def test_empty_watchlist_shows_hint(self, page: Page, app_url: str, streamlit_helper):
        """Empty watchlist should show a hint to add stocks."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        # If watchlist is empty, expect a guidance message
        hint = page.get_by_text("请在侧边栏添加")
        has_hint = hint.count() > 0

        # Or the watchlist already has stocks showing data
        has_data = (
            page.get_by_text("重点持仓").count() > 0
            or page.locator('[data-testid="stPlotlyChart"]').count() > 0
        )

        assert has_hint or has_data, "Should show either empty hint or stock data"

    def test_switch_to_industry_tab(self, page: Page, app_url: str, streamlit_helper):
        """Clicking industry tab should switch view."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        tabs = page.locator('[data-testid="stTabs"]')
        if tabs.count() > 0:
            industry_tab = page.locator('[role="tab"]:has-text("赛道监控")')
            if industry_tab.count() > 0:
                industry_tab.click()
                page.wait_for_timeout(2000)

                # Should show industry-related content or empty hint
                has_content = (
                    page.get_by_text("赛道追踪").count() > 0
                    or page.get_by_text("请在侧边栏添加").count() > 0
                )
                assert has_content, "Industry tab should show content or hint"


class TestWatchlistStockDetail:
    """Stock detail card rendering (when stocks are in watchlist)."""

    @pytest.mark.slow
    def test_stock_detail_has_analysis_tabs(self, page: Page, app_url: str, streamlit_helper):
        """Stock detail card should have multi-tab analysis."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        page.wait_for_timeout(5000)

        # Only test if watchlist has stocks (detail cards are visible)
        expanders = page.locator('[data-testid="stExpander"]')
        if expanders.count() > 1:
            # Click the first stock detail expander
            expanders.nth(1).click()
            page.wait_for_timeout(2000)

            # Detail card should have analysis tabs
            has_tabs = (
                page.get_by_text("资金流向").count() > 0
                or page.get_by_text("技术形态").count() > 0
                or page.get_by_text("估值分析").count() > 0
            )
            assert has_tabs, "Stock detail should have analysis tabs"
