"""E2E tests for the Scanner page.

The legacy Ranking page has been folded into Scanner.  This file retains its
name for continuity while covering the current opportunity-discovery page.
"""

from playwright.sync_api import Page, expect


class TestScannerPageLoad:
    """Basic page load and structure."""

    def test_page_title(self, page: Page, app_url: str, streamlit_helper):
        """Scanner page should display its title."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("Scanner").first).to_be_attached()

    def test_page_caption(self, page: Page, app_url: str, streamlit_helper):
        """Page should show the description caption."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("Find opportunities across asset pools").first).to_be_attached()

    def test_ai_panel_removed(self, page: Page, app_url: str, streamlit_helper):
        """Scanner should not render the removed AI analyst panel."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        assert page.get_by_text("AI 分析师").count() == 0


class TestScannerTabs:
    """Main scanner tabs."""

    def test_ashare_tab_exists(self, page: Page, app_url: str, streamlit_helper):
        """A-share scan tab should be present."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("A-Share Scan").first).to_be_attached()

    def test_us_value_tab_exists(self, page: Page, app_url: str, streamlit_helper):
        """US value scan tab should be present."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("US Value Scan").first).to_be_attached()

    def test_commodity_tab_exists(self, page: Page, app_url: str, streamlit_helper):
        """Commodity scan tab should be present."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("Gold & Commodity Scan").first).to_be_attached()


class TestScannerContent:
    """Scanner page content."""

    def test_sidebar_candidate_controls_present(self, page: Page, app_url: str, streamlit_helper):
        """Sidebar should expose scanner controls."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("候选池").first).to_be_attached()

    def test_scanner_renders_without_exception(self, page: Page, app_url: str, streamlit_helper):
        """Scanner should render without Streamlit exceptions."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        error = page.locator('[data-testid="stException"]')
        assert error.count() == 0
