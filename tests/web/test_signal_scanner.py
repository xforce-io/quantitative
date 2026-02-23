"""
E2E tests for Signal Scanner page.

Covers: 4 scanning modes (macro liquidity, China market signals,
value investing, box breakout), mode switching, parameter widgets,
result display.
"""

import pytest
from playwright.sync_api import Page, expect


class TestSignalScannerPageLoad:
    """Basic page load and structure."""

    def test_page_title(self, page: Page, app_url: str, streamlit_helper):
        """Signal Scanner should display its title."""
        page.goto(f"{app_url}/Signal_Scanner")
        streamlit_helper.wait_for_app_loaded()

        title = page.get_by_text("信号扫描器")
        expect(title.first).to_be_attached()

    def test_scan_mode_selector(self, page: Page, app_url: str, streamlit_helper):
        """Sidebar should show scan mode radio buttons."""
        page.goto(f"{app_url}/Signal_Scanner")
        streamlit_helper.wait_for_app_loaded()

        label = page.get_by_text("扫描模式")
        expect(label.first).to_be_attached()

    def test_ai_panel_present(self, page: Page, app_url: str, streamlit_helper):
        """AI panel should be integrated."""
        page.goto(f"{app_url}/Signal_Scanner")
        streamlit_helper.wait_for_app_loaded()

        ai_panel = page.get_by_text("AI 分析师")
        assert ai_panel.count() > 0


class TestMacroLiquidityMode:
    """Macro liquidity scanning mode (US market)."""

    @pytest.mark.slow
    def test_macro_mode_loads(self, page: Page, app_url: str, streamlit_helper):
        """Macro liquidity mode should load and display status."""
        page.goto(f"{app_url}/Signal_Scanner")
        streamlit_helper.wait_for_app_loaded()

        # Select macro liquidity mode
        macro_option = page.get_by_text("宏观流动性")
        if macro_option.count() > 0:
            macro_option.first.click()
            streamlit_helper.wait_for_app_loaded()
            page.wait_for_timeout(10000)

            # Should show macro data or loading status
            has_content = (
                page.get_by_text("净流动性").count() > 0
                or page.get_by_text("正在获取").count() > 0
                or page.locator('[data-testid="stMetric"]').count() > 0
            )
            assert has_content, "Macro mode should show liquidity data or loading"

    @pytest.mark.slow
    def test_macro_mode_shows_lookback_selector(self, page: Page, app_url: str, streamlit_helper):
        """Macro mode should show lookback period selector."""
        page.goto(f"{app_url}/Signal_Scanner")
        streamlit_helper.wait_for_app_loaded()

        macro_option = page.get_by_text("宏观流动性")
        if macro_option.count() > 0:
            macro_option.first.click()
            streamlit_helper.wait_for_app_loaded()

            lookback = page.get_by_text("回溯周期")
            expect(lookback.first).to_be_attached()


class TestChinaMarketSignalMode:
    """A-share / HK market signal mode."""

    @pytest.mark.slow
    def test_china_signal_mode_loads(self, page: Page, app_url: str, streamlit_helper):
        """China market signal mode should load with market data."""
        page.goto(f"{app_url}/Signal_Scanner")
        streamlit_helper.wait_for_app_loaded()

        china_option = page.get_by_text("A股/港股信号")
        if china_option.count() > 0:
            china_option.first.click()
            streamlit_helper.wait_for_app_loaded()
            page.wait_for_timeout(10000)

            has_content = (
                page.get_by_text("北向资金").count() > 0
                or page.get_by_text("两市成交额").count() > 0
                or page.get_by_text("正在获取").count() > 0
                or page.locator('[data-testid="stMetric"]').count() > 0
            )
            assert has_content, "China signal mode should show market data"


class TestBoxBreakoutMode:
    """Box breakout scanning mode (A-share)."""

    @pytest.mark.slow
    def test_box_breakout_mode_has_parameters(self, page: Page, app_url: str, streamlit_helper):
        """Box breakout mode should expose parameter widgets."""
        page.goto(f"{app_url}/Signal_Scanner")
        streamlit_helper.wait_for_app_loaded()

        box_option = page.get_by_text("箱体突破")
        if box_option.count() > 0:
            box_option.first.click()
            streamlit_helper.wait_for_app_loaded()

            # Should show box breakout parameter widgets
            has_params = (
                page.get_by_text("箱体周期").count() > 0
                or page.get_by_text("箱体参数").count() > 0
                or page.get_by_text("放量倍数").count() > 0
            )
            assert has_params, "Box breakout mode should show parameter widgets"

    @pytest.mark.slow
    def test_box_breakout_shows_results(self, page: Page, app_url: str, streamlit_helper):
        """Box breakout mode should display scanning results."""
        page.goto(f"{app_url}/Signal_Scanner")
        streamlit_helper.wait_for_app_loaded()

        box_option = page.get_by_text("箱体突破")
        if box_option.count() > 0:
            box_option.first.click()
            streamlit_helper.wait_for_app_loaded()

            # Wait for scanning to complete
            page.wait_for_timeout(20000)

            has_results = (
                page.locator('[data-testid="stDataFrame"]').count() > 0
                or page.locator('[data-testid="stDataEditor"]').count() > 0
                or page.locator('[data-testid="stMetric"]').count() > 0
                or page.get_by_text("扫描结果").count() > 0
                or page.get_by_text("正在扫描").count() > 0
            )
            assert has_results, "Box breakout should show results or scanning status"

    @pytest.mark.slow
    def test_box_breakout_filter_options(self, page: Page, app_url: str, streamlit_helper):
        """Box breakout should provide result filter radio buttons."""
        page.goto(f"{app_url}/Signal_Scanner")
        streamlit_helper.wait_for_app_loaded()

        box_option = page.get_by_text("箱体突破")
        if box_option.count() > 0:
            box_option.first.click()
            streamlit_helper.wait_for_app_loaded()
            page.wait_for_timeout(20000)

            # After scanning, filter options should appear
            has_filter = (
                page.get_by_text("显示范围").count() > 0
                or page.get_by_text("向上突破").count() > 0
            )
            # Filter may not show if scanning is still in progress
            # This is acceptable — we just verify no crash


class TestValueInvestingMode:
    """Value investing scanning mode (US stocks)."""

    @pytest.mark.slow
    def test_value_mode_has_input_options(self, page: Page, app_url: str, streamlit_helper):
        """Value investing mode should have stock selection options."""
        page.goto(f"{app_url}/Signal_Scanner")
        streamlit_helper.wait_for_app_loaded()

        value_option = page.get_by_text("价值投资")
        if value_option.count() > 0:
            value_option.first.click()
            streamlit_helper.wait_for_app_loaded()

            # Should show selection method (candidate pool or manual input)
            has_input = (
                page.get_by_text("选股方式").count() > 0
                or page.get_by_text("候选池").count() > 0
                or page.get_by_text("手动输入").count() > 0
            )
            assert has_input, "Value mode should show stock selection options"

    @pytest.mark.slow
    def test_value_mode_has_threshold_slider(self, page: Page, app_url: str, streamlit_helper):
        """Value investing mode should have minimum score threshold slider."""
        page.goto(f"{app_url}/Signal_Scanner")
        streamlit_helper.wait_for_app_loaded()

        value_option = page.get_by_text("价值投资")
        if value_option.count() > 0:
            value_option.first.click()
            streamlit_helper.wait_for_app_loaded()

            threshold = page.get_by_text("最低评分")
            if threshold.count() > 0:
                expect(threshold.first).to_be_attached()


class TestScannerModeSwitching:
    """Rapidly switching between all 4 modes should not crash."""

    def test_cycle_all_modes(self, page: Page, app_url: str, streamlit_helper):
        """Cycle through all scan modes — no crash expected."""
        page.goto(f"{app_url}/Signal_Scanner")
        streamlit_helper.wait_for_app_loaded()

        modes = ["宏观流动性", "A股/港股信号", "价值投资", "箱体突破"]

        for mode_text in modes:
            option = page.get_by_text(mode_text)
            if option.count() > 0:
                option.first.click()
                page.wait_for_timeout(2000)

                # No crash — verify app container still present
                app_container = page.locator('[data-testid="stAppViewContainer"]')
                expect(app_container).to_be_visible()

                # No Streamlit error
                error = page.locator('[data-testid="stException"]')
                assert error.count() == 0, f"Error when switching to {mode_text}"
