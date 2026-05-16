"""Tests for PreTradeChecker."""
import pandas as pd
from unittest.mock import MagicMock

from quant.analysis.rotation.precheck import PreTradeChecker, PreCheckReport


def _make_checker(price_513100=2.00, price_159941=2.00, nav_513100=2.00, quota_ok=True):
    """Build a PreTradeChecker with injected data helpers."""
    ds = MagicMock()

    def get_price(request):
        today = pd.Timestamp("2026-05-30")
        if request.symbol == "513100.SH":
            return pd.DataFrame({"close": [price_513100]}, index=[today])
        if request.symbol == "159941.SZ":
            return pd.DataFrame({"close": [price_159941]}, index=[today])
        return pd.DataFrame({"close": [1.0]}, index=[today])

    ds.get_price.side_effect = get_price
    checker = PreTradeChecker(data_service=ds)
    checker._get_qdii_nav = lambda: nav_513100
    checker._get_qdii_quota_ok = lambda: quota_ok
    return checker


def test_all_checks_pass():
    """No warnings when premium is low and quota is fine."""
    checker = _make_checker(price_513100=2.00, price_159941=2.00, nav_513100=2.00)
    targets = {"513100.SH": 0.33, "511880.SH": 0.33, "512800.SH": 0.34}
    report = checker.run(targets)

    assert not report.has_errors
    assert not report.has_warnings
    assert report.adjusted_targets == targets


def test_qdii_premium_warn_threshold():
    """Premium > 1% triggers WARN but does not substitute."""
    # price = 2.022 → premium = 1.1%
    checker = _make_checker(price_513100=2.022, nav_513100=2.00)
    targets = {"513100.SH": 0.33, "511880.SH": 0.33, "512800.SH": 0.34}
    report = checker.run(targets)

    assert report.has_warnings
    assert not report.has_errors
    assert "513100.SH" in report.adjusted_targets


def test_qdii_premium_error_threshold_substitutes():
    """Premium > 2% triggers ERROR and substitutes 513100.SH with 511880.SH."""
    # price = 2.05 → premium = 2.5%
    checker = _make_checker(price_513100=2.05, nav_513100=2.00)
    targets = {"513100.SH": 0.33, "511880.SH": 0.33, "512800.SH": 0.34}
    report = checker.run(targets)

    assert report.has_errors
    assert "513100.SH" not in report.adjusted_targets
    assert abs(report.adjusted_targets.get("511880.SH", 0) - 0.66) < 1e-9


def test_cross_etf_spread_warn():
    """Price spread > 1% between 513100.SH and 159941.SZ triggers WARN."""
    # 513100 = 2.00, 159941 = 1.97 → spread = 1.5%
    checker = _make_checker(price_513100=2.00, price_159941=1.97)
    targets = {"513100.SH": 0.33, "511880.SH": 0.33, "512800.SH": 0.34}
    report = checker.run(targets)

    assert report.has_warnings
    assert "513100.SH" in report.adjusted_targets  # only warns, does not substitute
    spread_check = next(c for c in report.checks if c.name == "跨ETF价差")
    assert spread_check.status == "warn"


def test_qdii_quota_suspended_substitutes():
    """QDII quota suspended triggers ERROR and substitutes."""
    checker = _make_checker(quota_ok=False)
    targets = {"513100.SH": 0.33, "511880.SH": 0.33, "512800.SH": 0.34}
    report = checker.run(targets)

    assert report.has_errors
    assert "513100.SH" not in report.adjusted_targets
    assert abs(report.adjusted_targets.get("511880.SH", 0) - 0.66) < 1e-9


def test_no_qdii_in_targets_skips_qdii_checks():
    """If 513100.SH is not in targets, all QDII checks are skipped."""
    checker = _make_checker()
    targets = {"511880.SH": 0.50, "512800.SH": 0.50}
    report = checker.run(targets)

    assert not report.has_errors
    assert not report.has_warnings
    assert report.adjusted_targets == targets


def test_nav_unavailable_emits_warn_not_error():
    """If IOPV data is unavailable (None), emit WARN and leave targets unchanged."""
    checker = _make_checker(nav_513100=None)
    targets = {"513100.SH": 0.33, "511880.SH": 0.33, "512800.SH": 0.34}
    report = checker.run(targets)

    assert report.has_warnings
    assert not report.has_errors
    assert "513100.SH" in report.adjusted_targets
