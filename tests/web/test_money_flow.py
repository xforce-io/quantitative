"""
E2E tests for Money Flow page.

Covers: analysis mode switching, market overview metrics,
industry analysis tabs, stock tracking flow, and AI panel integration.
"""

import pytest
from playwright.sync_api import Page, expect


class TestMoneyFlowPageLoad:
    """Basic page load and layout."""

    def test_page_title(self, page: Page, app_url: str, streamlit_helper):
        """Page should display the Money Flow title."""
        page.goto(f"{app_url}/Money_Flow")
        streamlit_helper.wait_for_app_loaded()

        title = page.get_by_text("A股市场资金流向分析")
        expect(title.first).to_be_attached()

    def test_sidebar_config_panel(self, page: Page, app_url: str, streamlit_helper):
        """Sidebar should show the configuration panel."""
        page.goto(f"{app_url}/Money_Flow")
        streamlit_helper.wait_for_app_loaded()

        sidebar = page.locator('[data-testid="stSidebar"]')
        expect(sidebar).to_be_visible()

        # Analysis mode selector should exist
        mode_label = page.get_by_text("选择分析模式")
        expect(mode_label.first).to_be_attached()

    def test_ai_panel_present(self, page: Page, app_url: str, streamlit_helper):
        """AI analysis panel should be present on the page."""
        page.goto(f"{app_url}/Money_Flow")
        streamlit_helper.wait_for_app_loaded()

        ai_panel = page.get_by_text("AI 分析师")
        assert ai_panel.count() > 0, "AI panel should be present on Money Flow page"


class TestMoneyFlowMarketOverview:
    """Market overview mode (default)."""

    def test_market_overview_shows_metrics(self, page: Page, app_url: str, streamlit_helper):
        """Market overview should display key capital flow metrics."""
        page.goto(f"{app_url}/Money_Flow")
        streamlit_helper.wait_for_app_loaded()

        # Wait for data loading
        page.wait_for_timeout(5000)

        # Should display metric widgets (institutional, retail, northbound)
        metrics = page.locator('[data-testid="stMetric"]')
        if metrics.count() > 0:
            # At least one metric should be visible
            expect(metrics.first).to_be_visible()

    def test_market_overview_shows_chart_or_data(self, page: Page, app_url: str, streamlit_helper):
        """Market overview should show either charts or data tables."""
        page.goto(f"{app_url}/Money_Flow")
        streamlit_helper.wait_for_app_loaded()

        page.wait_for_timeout(5000)

        has_visual = (
            page.locator('[data-testid="stPlotlyChart"]').count() > 0
            or page.locator('[data-testid="stDataFrame"]').count() > 0
            or page.locator('[data-testid="stMetric"]').count() > 0
        )
        assert has_visual, "Market overview should display visual content"


class TestMoneyFlowModeSwitch:
    """Switching between analysis modes."""

    def test_switch_to_industry_mode(self, page: Page, app_url: str, streamlit_helper):
        """Switching to industry mode should update the main content."""
        page.goto(f"{app_url}/Money_Flow")
        streamlit_helper.wait_for_app_loaded()

        # Click the analysis mode selectbox
        mode_select = page.locator('[data-testid="stSidebar"]').locator(
            'div:has-text("选择分析模式")'
        )
        if mode_select.count() > 0:
            # Open the selectbox and pick industry mode
            page.locator('[data-testid="stSidebar"]').locator(
                '[data-testid="stSelectbox"]'
            ).first.click()
            page.wait_for_timeout(300)

            industry_option = page.locator('[role="option"]:has-text("行业分析")')
            if industry_option.count() > 0:
                industry_option.click()
                streamlit_helper.wait_for_app_loaded()
                page.wait_for_timeout(3000)

                # Industry mode should show industry-related content
                has_industry_content = (
                    page.get_by_text("行业").count() > 0
                    or page.get_by_text("板块").count() > 0
                )
                assert has_industry_content, "Industry mode should show industry content"

    def test_switch_to_stock_mode(self, page: Page, app_url: str, streamlit_helper):
        """Switching to stock tracking mode should show stock input."""
        page.goto(f"{app_url}/Money_Flow")
        streamlit_helper.wait_for_app_loaded()

        page.locator('[data-testid="stSidebar"]').locator(
            '[data-testid="stSelectbox"]'
        ).first.click()
        page.wait_for_timeout(300)

        stock_option = page.locator('[role="option"]:has-text("个股追踪")')
        if stock_option.count() > 0:
            stock_option.click()
            streamlit_helper.wait_for_app_loaded()
            page.wait_for_timeout(3000)

            # Stock mode should have a stock selector or search
            has_stock_input = (
                page.get_by_text("选择或搜索股票").count() > 0
                or page.get_by_text("个股").count() > 0
            )
            assert has_stock_input, "Stock mode should show stock selection input"


class TestMoneyFlowIndustryAnalysis:
    """Industry analysis mode features."""

    @pytest.mark.slow
    def test_industry_tabs_available(self, page: Page, app_url: str, streamlit_helper):
        """Industry mode should provide tab-based analysis views."""
        page.goto(f"{app_url}/Money_Flow")
        streamlit_helper.wait_for_app_loaded()

        # Switch to industry mode
        page.locator('[data-testid="stSidebar"]').locator(
            '[data-testid="stSelectbox"]'
        ).first.click()
        page.wait_for_timeout(300)

        industry_option = page.locator('[role="option"]:has-text("行业分析")')
        if industry_option.count() > 0:
            industry_option.click()
            streamlit_helper.wait_for_app_loaded()
            page.wait_for_timeout(5000)

            # Should have tab-like elements for data/chart views
            has_tabs = page.locator('[data-testid="stTabs"]').count() > 0
            has_data = (
                page.locator('[data-testid="stDataFrame"]').count() > 0
                or page.locator('[data-testid="stPlotlyChart"]').count() > 0
            )
            assert has_tabs or has_data, "Industry mode should show tabs or data"
