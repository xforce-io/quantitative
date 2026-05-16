"""Pre-trade execution checks for monthly ETF rotation rebalancing."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from quant.services.data_service import DataService, PriceRequest

logger = logging.getLogger(__name__)

QDII_SYMBOL = "513100.SH"
QDII_ALT = "511880.SH"
CROSS_ETF = "159941.SZ"

WARN_THRESHOLD = 0.01    # 1%: defer buy
ERROR_THRESHOLD = 0.02   # 2%: substitute with short bond
CROSS_SPREAD_THRESHOLD = 0.01  # 1%: warn only


@dataclass
class CheckResult:
    name: str
    status: str    # "ok" | "warn" | "error"
    message: str


@dataclass
class PreCheckReport:
    checks: list[CheckResult]
    original_targets: dict[str, float]
    adjusted_targets: dict[str, float]
    has_errors: bool = field(init=False)
    has_warnings: bool = field(init=False)

    def __post_init__(self):
        self.has_errors = any(c.status == "error" for c in self.checks)
        self.has_warnings = any(c.status == "warn" for c in self.checks)


class PreTradeChecker:
    """Run pre-trade checks on target positions before monthly rebalancing.

    Checks (only when 513100.SH is in targets):
    1. QDII premium vs IOPV — warn >1%, substitute >2%
    2. Cross-ETF spread vs 159941.SZ — warn >1%
    3. QDII quota / creation status — substitute if suspended
    """

    def __init__(self, data_service: DataService | None = None) -> None:
        self.data_service = data_service or DataService()

    def run(self, targets: dict[str, float]) -> PreCheckReport:
        checks: list[CheckResult] = []
        adjusted = dict(targets)

        if QDII_SYMBOL in targets:
            check, adjusted = self._check_qdii_premium(adjusted)
            checks.append(check)

            if QDII_SYMBOL in adjusted:
                checks.append(self._check_cross_etf_spread())

            check, adjusted = self._check_qdii_quota(adjusted)
            checks.append(check)

        return PreCheckReport(
            checks=checks,
            original_targets=targets,
            adjusted_targets=adjusted,
        )

    def _check_qdii_premium(
        self, targets: dict[str, float]
    ) -> tuple[CheckResult, dict[str, float]]:
        nav = self._get_qdii_nav()
        if nav is None:
            return (
                CheckResult("QDII溢价", "warn", "IOPV数据不可用，跳过溢价检查"),
                targets,
            )

        price = self._get_latest_price(QDII_SYMBOL)
        if price is None:
            return (
                CheckResult("QDII溢价", "warn", "无法获取513100.SH最新价格"),
                targets,
            )

        premium = (price - nav) / nav
        msg_base = f"溢价 {premium:+.2%}（价格 {price:.4f}，IOPV {nav:.4f}）"

        if premium > ERROR_THRESHOLD:
            weight = targets.pop(QDII_SYMBOL)
            targets[QDII_ALT] = targets.get(QDII_ALT, 0.0) + weight
            return (
                CheckResult("QDII溢价", "error", f"{msg_base} > {ERROR_THRESHOLD:.0%}，已替换为{QDII_ALT}"),
                targets,
            )
        if premium > WARN_THRESHOLD:
            return (
                CheckResult("QDII溢价", "warn", f"{msg_base} > {WARN_THRESHOLD:.0%}，建议延迟买入"),
                targets,
            )
        return (
            CheckResult("QDII溢价", "ok", f"{msg_base}，正常"),
            targets,
        )

    def _check_cross_etf_spread(self) -> CheckResult:
        p1 = self._get_latest_price(QDII_SYMBOL)
        p2 = self._get_latest_price(CROSS_ETF)
        if p1 is None or p2 is None:
            return CheckResult("跨ETF价差", "warn", "无法获取比价数据")

        spread = abs(p1 - p2) / p2
        if spread > CROSS_SPREAD_THRESHOLD:
            return CheckResult(
                "跨ETF价差",
                "warn",
                f"{QDII_SYMBOL}/{CROSS_ETF} 价差 {spread:.2%} > {CROSS_SPREAD_THRESHOLD:.0%}，建议等价差收窄",
            )
        return CheckResult("跨ETF价差", "ok", f"价差 {spread:.2%}，正常")

    def _check_qdii_quota(
        self, targets: dict[str, float]
    ) -> tuple[CheckResult, dict[str, float]]:
        if QDII_SYMBOL not in targets:
            return CheckResult("QDII额度", "ok", "513100.SH已替换，跳过额度检查"), targets

        quota_ok = self._get_qdii_quota_ok()
        if quota_ok is None:
            return CheckResult("QDII额度", "warn", "无法获取额度状态，请手动核查"), targets
        if not quota_ok:
            weight = targets.pop(QDII_SYMBOL)
            targets[QDII_ALT] = targets.get(QDII_ALT, 0.0) + weight
            return (
                CheckResult("QDII额度", "error", f"513100.SH申购暂停，已替换为{QDII_ALT}"),
                targets,
            )
        return CheckResult("QDII额度", "ok", "申购正常"), targets

    def _get_latest_price(self, symbol: str) -> float | None:
        try:
            df = self.data_service.get_price(
                PriceRequest(symbol=symbol, start="20260101", end="20991231", asset_type="etf")
            )
            if df is None or df.empty or "close" not in df.columns:
                return None
            return float(df["close"].iloc[-1])
        except Exception as exc:
            logger.warning("Failed to fetch price for %s: %s", symbol, exc)
            return None

    def _get_qdii_nav(self) -> float | None:
        """Return T-1 NAV of 513100.SH from Tushare fund_nav (best-effort).

        Tushare fund_nav endpoint returns T-1 unit NAV; used as IOPV proxy.
        Returns None when data is unavailable.
        """
        try:
            import tushare as ts  # type: ignore
            token = os.getenv("TUSHARE_TOKEN", "")
            if not token:
                return None
            pro = ts.pro_api(token)
            df = pro.fund_nav(ts_code="513100.SH", fields="nav_date,unit_nav")
            if df is None or df.empty:
                return None
            return float(df.sort_values("nav_date").iloc[-1]["unit_nav"])
        except Exception as exc:
            logger.warning("fund_nav fetch failed: %s", exc)
            return None

    def _get_qdii_quota_ok(self) -> bool | None:
        """Return True if 513100.SH primary-market creation is open, None if unknown.

        Treats share count flat for 3+ consecutive trading days as halted.
        """
        try:
            import tushare as ts  # type: ignore
            from datetime import date, timedelta
            token = os.getenv("TUSHARE_TOKEN", "")
            if not token:
                return None
            pro = ts.pro_api(token)
            end = date.today().strftime("%Y%m%d")
            start = (date.today() - timedelta(days=7)).strftime("%Y%m%d")
            df = pro.fund_share(ts_code="513100.SH", start_date=start, end_date=end)
            if df is None or df.empty:
                return None
            if len(df) >= 3 and df["fd_share"].nunique() == 1:
                return False
            return True
        except Exception as exc:
            logger.warning("fund_share fetch failed: %s", exc)
            return None
