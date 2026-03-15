"""
E2E tests for Home page.

Covers: page rendering, navigation cards, sidebar system status,
and feature detail expander.
"""

import pytest
from playwright.sync_api import Page, expect


class TestHomeRendering:
    """Home page core rendering."""

    def test_page_title_displayed(self, page: Page, app_url: str, streamlit_helper):
        """Home page should display the platform title."""
        page.goto(app_url)
        streamlit_helper.wait_for_app_loaded()

        title = page.get_by_text("Quantitative Trading Platform")
        expect(title.first).to_be_attached()

    def test_welcome_subtitle(self, page: Page, app_url: str, streamlit_helper):
        """Home page should display the welcome subtitle."""
        page.goto(app_url)
        streamlit_helper.wait_for_app_loaded()

        subtitle = page.get_by_text("欢迎使用量化交易分析平台")
        expect(subtitle.first).to_be_attached()


class TestHomeNavigationCards:
    """Quick entry cards linking to sub-pages."""

    def test_money_flow_card_visible(self, page: Page, app_url: str, streamlit_helper):
        """Money Flow navigation card should be visible."""
        page.goto(app_url)
        streamlit_helper.wait_for_app_loaded()

        card = page.get_by_text("资金流向分析")
        expect(card.first).to_be_attached()

    def test_watchlist_card_visible(self, page: Page, app_url: str, streamlit_helper):
        """Watchlist navigation card should be visible."""
        page.goto(app_url)
        streamlit_helper.wait_for_app_loaded()

        card = page.get_by_text("自选股监控")
        expect(card.first).to_be_attached()

    def test_ranking_card_visible(self, page: Page, app_url: str, streamlit_helper):
        """Ranking navigation card should be visible."""
        page.goto(app_url)
        streamlit_helper.wait_for_app_loaded()

        card = page.get_by_text("风向排行榜")
        expect(card.first).to_be_attached()

    def test_event_graph_card_visible(self, page: Page, app_url: str, streamlit_helper):
        """Event Graph navigation card should be visible."""
        page.goto(app_url)
        streamlit_helper.wait_for_app_loaded()

        card = page.get_by_text("新闻事件概率图")
        expect(card.first).to_be_attached()


class TestHomeSidebar:
    """Sidebar system status display."""

    def test_sidebar_shows_system_status(self, page: Page, app_url: str, streamlit_helper):
        """Sidebar should show system load status (success or failure)."""
        page.goto(app_url)
        streamlit_helper.wait_for_app_loaded()

        sidebar = page.locator('[data-testid="stSidebar"]')
        expect(sidebar).to_be_visible()

        # Should show either success or failure status
        has_status = (
            page.get_by_text("Core System Loaded").count() > 0
            or page.get_by_text("System Import Failed").count() > 0
        )
        assert has_status, "Sidebar should display system status"


class TestHomeFeatureDetails:
    """Feature details expander."""

    def test_feature_expander_exists(self, page: Page, app_url: str, streamlit_helper):
        """Feature details expander should be present."""
        page.goto(app_url)
        streamlit_helper.wait_for_app_loaded()

        expander = page.get_by_text("功能详情")
        expect(expander.first).to_be_attached()
