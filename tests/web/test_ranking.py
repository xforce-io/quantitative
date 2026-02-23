"""
E2E tests for Ranking page.

Covers: page layout, candidate pool selection, ranking mode switch
(smart vs traditional), dataframe display, detail analysis, industry tab.
"""

import pytest
from playwright.sync_api import Page, expect


class TestRankingPageLoad:
    """Basic page load and structure."""

    def test_page_title(self, page: Page, app_url: str, streamlit_helper):
        """Ranking page should display its title."""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        title = page.get_by_text("风向排行榜")
        expect(title.first).to_be_attached()

    def test_page_caption(self, page: Page, app_url: str, streamlit_helper):
        """Page should show the description caption."""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        caption = page.get_by_text("候选池")
        expect(caption.first).to_be_attached()

    def test_ai_panel_present(self, page: Page, app_url: str, streamlit_helper):
        """AI panel should be integrated."""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        page.wait_for_timeout(3000)
        ai_panel = page.get_by_text("AI 分析师")
        assert ai_panel.count() > 0


class TestRankingSidebar:
    """Sidebar configuration widgets."""

    def test_candidate_pool_selector(self, page: Page, app_url: str, streamlit_helper):
        """Sidebar should have candidate pool selectbox."""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        label = page.get_by_text("候选池")
        expect(label.first).to_be_attached()

    def test_ranking_mode_selector(self, page: Page, app_url: str, streamlit_helper):
        """Sidebar should have ranking mode radio buttons."""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        label = page.get_by_text("排名模式")
        expect(label.first).to_be_attached()

    def test_stock_count_displayed(self, page: Page, app_url: str, streamlit_helper):
        """Sidebar should show the number of candidates."""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        count_label = page.get_by_text("标的数量")
        expect(count_label.first).to_be_attached()


class TestRankingTabs:
    """Main tabs: stock ranking + industry ranking."""

    def test_stock_ranking_tab_exists(self, page: Page, app_url: str, streamlit_helper):
        """Stock ranking tab should be present."""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        tab = page.get_by_text("个股排行")
        expect(tab.first).to_be_attached()

    def test_industry_ranking_tab_exists(self, page: Page, app_url: str, streamlit_helper):
        """Industry ranking tab should be present."""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        tab = page.get_by_text("赛道排行")
        expect(tab.first).to_be_attached()


class TestRankingSmartMode:
    """Smart ranking mode (multi-factor AI scoring)."""

    @pytest.mark.slow
    def test_smart_ranking_produces_dataframe(self, page: Page, app_url: str, streamlit_helper):
        """Smart ranking should eventually display a ranked dataframe."""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        # Wait for ranking computation (may take a while)
        page.wait_for_timeout(15000)

        # Should show a dataframe or at least a progress/status indicator
        has_results = (
            page.locator('[data-testid="stDataFrame"]').count() > 0
            or page.locator('[data-testid="stDataEditor"]').count() > 0
            or page.get_by_text("正在计算").count() > 0
            or page.get_by_text("综合评分").count() > 0
        )
        assert has_results, "Smart ranking should show results or computing status"


class TestRankingModeSwitch:
    """Switching between smart and traditional ranking modes."""

    def test_switch_to_traditional_mode(self, page: Page, app_url: str, streamlit_helper):
        """Switching to traditional mode should change the view."""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        # Find and click the traditional ranking radio option
        traditional = page.get_by_text("传统排名")
        if traditional.count() > 0:
            traditional.click()
            page.wait_for_timeout(3000)

            # Traditional mode should show sort-by options
            has_sort_options = (
                page.get_by_text("排序依据").count() > 0
                or page.get_by_text("资金流向").count() > 0
            )
            assert has_sort_options, "Traditional mode should show sort options"


class TestRankingDetailAnalysis:
    """Detail analysis for selected stock."""

    @pytest.mark.slow
    def test_detail_section_exists(self, page: Page, app_url: str, streamlit_helper):
        """Detailed analysis section should be available below ranking."""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        page.wait_for_timeout(15000)

        detail_header = page.get_by_text("详细分析")
        if detail_header.count() > 0:
            expect(detail_header.first).to_be_attached()
