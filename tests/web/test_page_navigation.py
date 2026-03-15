"""
E2E tests for cross-page navigation.

Verifies that navigating between all pages works without errors
and that the Streamlit app remains stable across page transitions.
"""

import pytest
from playwright.sync_api import Page, expect


class TestCrossPageNavigation:
    """Navigate between all pages without crash."""

    def test_navigate_all_pages_sequentially(self, page: Page, app_url: str, streamlit_helper):
        """Visit every page in sequence — none should crash."""
        pages = [
            "/",
            "/Money_Flow",
            "/Watchlist",
            "/Ranking",
            "/Signal_Scanner",
            "/Event_Graph",
        ]

        for path in pages:
            page.goto(f"{app_url}{path}")
            streamlit_helper.wait_for_app_loaded()

            # App container must remain visible
            app_container = page.locator('[data-testid="stAppViewContainer"]')
            expect(app_container).to_be_visible()

            # No Streamlit exception banner
            error = page.locator('[data-testid="stException"]')
            assert error.count() == 0, f"Exception on page {path}"

    def test_navigate_back_and_forth(self, page: Page, app_url: str, streamlit_helper):
        """Navigate from sub-page back to home — app should remain stable."""
        page.goto(f"{app_url}/Ranking")
        streamlit_helper.wait_for_app_loaded()

        page.goto(app_url)
        streamlit_helper.wait_for_app_loaded()

        page.goto(f"{app_url}/Watchlist")
        streamlit_helper.wait_for_app_loaded()

        # Final page should render normally
        error = page.locator('[data-testid="stException"]')
        assert error.count() == 0

    def test_sidebar_visible_on_all_pages(self, page: Page, app_url: str, streamlit_helper):
        """Every page should have a visible sidebar."""
        pages = ["/", "/Money_Flow", "/Watchlist", "/Ranking", "/Signal_Scanner", "/Event_Graph"]

        for path in pages:
            page.goto(f"{app_url}{path}")
            streamlit_helper.wait_for_app_loaded()

            sidebar = page.locator('[data-testid="stSidebar"]')
            expect(sidebar).to_be_visible()
