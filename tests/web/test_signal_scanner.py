"""E2E tests for Scanner modes."""

from playwright.sync_api import Page, expect


class TestSignalScannerPageLoad:
    """Basic page load and structure."""

    def test_page_title(self, page: Page, app_url: str, streamlit_helper):
        """Scanner should display its title."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("Scanner").first).to_be_attached()

    def test_ai_panel_removed(self, page: Page, app_url: str, streamlit_helper):
        """Scanner should not render the removed AI analyst panel."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        assert page.get_by_text("AI 分析师").count() == 0


class TestAshareScanMode:
    """A-share scanner tab."""

    def test_ashare_mode_has_parameters(self, page: Page, app_url: str, streamlit_helper):
        """A-share scan should expose box breakout parameters."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("箱体参数").first).to_be_attached()
        expect(page.get_by_text("箱体周期").first).to_be_attached()

    def test_ashare_mode_has_period_selector(self, page: Page, app_url: str, streamlit_helper):
        """A-share scan should expose the shared period selector."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        expect(page.get_by_text("近1月").first).to_be_attached()


class TestUsValueScanMode:
    """US value scanner tab."""

    def test_us_value_tab_can_be_selected(self, page: Page, app_url: str, streamlit_helper):
        """US value tab should show stock-selection controls."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        page.locator('[role="tab"]:has-text("US Value Scan")').first.click()
        page.wait_for_timeout(1000)

        has_input = (
            page.get_by_text("选股方式").count() > 0
            or page.get_by_text("候选池").count() > 0
            or page.get_by_text("手动输入").count() > 0
        )
        assert has_input


class TestCommodityScanMode:
    """Gold and commodity scanner tab."""

    def test_commodity_tab_can_be_selected(self, page: Page, app_url: str, streamlit_helper):
        """Commodity tab should render the planned integration notice."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        page.locator('[role="tab"]:has-text("Gold & Commodity Scan")').first.click()
        page.wait_for_timeout(1000)

        expect(page.get_by_text("Gold & Commodity Scan").first).to_be_attached()
        assert page.locator('[data-testid="stException"]').count() == 0


class TestScannerModeSwitching:
    """Switching between tabs should not crash."""

    def test_cycle_all_tabs(self, page: Page, app_url: str, streamlit_helper):
        """Cycle through scanner tabs and verify no Streamlit exception appears."""
        page.goto(f"{app_url}/Scanner")
        streamlit_helper.wait_for_app_loaded()

        for tab_text in ["A-Share Scan", "US Value Scan", "Gold & Commodity Scan"]:
            page.locator(f'[role="tab"]:has-text("{tab_text}")').first.click()
            page.wait_for_timeout(1000)

            app_container = page.locator('[data-testid="stAppViewContainer"]')
            expect(app_container).to_be_visible()
            assert page.locator('[data-testid="stException"]').count() == 0
