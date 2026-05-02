"""E2E tests for Watchlist page."""

from playwright.sync_api import Page, expect


class TestWatchlistPageLoad:
    """Basic page load and structure."""

    def test_page_title(self, page: Page, app_url: str, streamlit_helper):
        """Watchlist page should display its title."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("自选监控").first).to_be_attached()

    def test_ai_panel_present(self, page: Page, app_url: str, streamlit_helper):
        """AI panel should be integrated."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        assert page.get_by_text("AI 分析师").count() > 0


class TestWatchlistPoolTabs:
    """Pool-based watchlist tabs."""

    def test_pool_tabs_exist(self, page: Page, app_url: str, streamlit_helper):
        """Watchlist should expose pool tabs."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("A股").first).to_be_attached()
        expect(page.get_by_text("美股").first).to_be_attached()
        expect(page.get_by_text("黄金").first).to_be_attached()

    def test_add_symbol_control_present(self, page: Page, app_url: str, streamlit_helper):
        """Each pool tab should provide an add-symbol control."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("+ 添加标的").first).to_be_attached()

    def test_industry_section_present_for_ashares(self, page: Page, app_url: str, streamlit_helper):
        """A-share tab should include the watched industry section."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("关注行业").first).to_be_attached()


class TestWatchlistRendering:
    """Watchlist content rendering."""

    def test_empty_or_populated_state_renders(self, page: Page, app_url: str, streamlit_helper):
        """Watchlist should show either an empty hint or position content."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        has_empty_hint = page.get_by_text("暂无持仓/关注标的").count() > 0
        has_position = page.locator('[data-testid="stExpander"]').count() > 0
        assert has_empty_hint or has_position

    def test_page_renders_without_exception(self, page: Page, app_url: str, streamlit_helper):
        """Watchlist should render without Streamlit exceptions."""
        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        assert page.locator('[data-testid="stException"]').count() == 0
