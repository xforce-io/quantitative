"""
领先指标分析器 (Leading Indicators Analyzer)

三个领先指标：
  1. VIX 恐慌指数   — Yahoo Finance ^VIX
  2. 信用利差 HY-IG — FRED (BAMLH0A0HYM2, BAMLC0A4CBBB)
  3. 融资余额变化率  — Tushare margin API (数据由调用方传入，保持解耦)

每个指标通过 MomentumDelta 计算变化率，输出人可读的状态和异动提示。
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from quant.analysis.indicators.momentum_delta import MomentumDelta
from quant.core.logging_config import get_logger

logger = get_logger(__name__)

_VIX_LEVELS = [
    (40, "panic", "极度恐慌", "🔴"),
    (30, "fear", "恐慌", "🟠"),
    (20, "elevated", "偏高", "🟡"),
    (0, "normal", "正常", "🟢"),
]

_CREDIT_LEVELS = [
    (8.0, "crisis", "危机", "🔴"),
    (5.0, "stress", "紧缩", "🟠"),
    (3.0, "elevated", "偏高", "🟡"),
    (0.0, "normal", "正常", "🟢"),
]


def _classify(value: float, levels: list) -> tuple:
    for threshold, level, label_cn, emoji in levels:
        if value >= threshold:
            return level, label_cn, emoji
    last = levels[-1]
    return last[1], last[2], last[3]


class LeadingIndicatorsAnalyzer:

    def __init__(self, fred_api_key: Optional[str] = None):
        self._fred = None
        self._fred_api_key = fred_api_key

    def _get_fred(self):
        if self._fred is None:
            from fredapi import Fred
            from dotenv import load_dotenv
            load_dotenv()
            api_key = self._fred_api_key or os.environ.get("FRED_API_KEY")
            if not api_key:
                raise ValueError("需要 FRED_API_KEY 环境变量")
            self._fred = Fred(api_key=api_key)
        return self._fred

    def analyze_vix(self, lookback_days: int = 365) -> Dict[str, Any]:
        try:
            end = datetime.now()
            start = end - timedelta(days=lookback_days + 30)
            df = yf.download(
                "^VIX", start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"), progress=False,
            )
            if df.empty:
                return {"error": "VIX 数据为空"}

            close = df["Close"].squeeze()
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close = close.dropna()

            value = float(close.iloc[-1])
            level, level_cn, emoji = _classify(value, _VIX_LEVELS)
            delta = MomentumDelta.compute(close, velocity_window=5, zscore_window=60)

            return {
                "value": round(value, 2),
                "level": level,
                "level_cn": level_cn,
                "emoji": emoji,
                "delta": delta,
                "series": close,
            }
        except Exception as e:
            logger.error(f"VIX 分析失败: {e}")
            return {"error": str(e)}

    def analyze_credit_spread(self, lookback_days: int = 365) -> Dict[str, Any]:
        try:
            fred = self._get_fred()
            start = datetime.now() - timedelta(days=lookback_days + 30)

            hy = fred.get_series("BAMLH0A0HYM2", observation_start=start)
            bbb = fred.get_series("BAMLC0A4CBBB", observation_start=start)

            spread = (hy - bbb).dropna()
            if spread.empty:
                return {"error": "信用利差数据为空"}

            value = float(spread.iloc[-1])
            level, level_cn, emoji = _classify(value, _CREDIT_LEVELS)
            delta = MomentumDelta.compute(spread, velocity_window=5, zscore_window=60)

            return {
                "spread": round(value, 2),
                "level": level,
                "level_cn": level_cn,
                "emoji": emoji,
                "delta": delta,
                "series": spread,
            }
        except Exception as e:
            logger.error(f"信用利差分析失败: {e}")
            return {"error": str(e)}

    def analyze_margin_balance(
        self,
        margin_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        if margin_df is None or margin_df.empty:
            return {"error": "无融资融券数据"}

        if "rzye" not in margin_df.columns:
            return {"error": "数据缺少 rzye 列"}

        df = margin_df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.sort_values("trade_date").set_index("trade_date")

        rzye = df["rzye"].dropna()
        if len(rzye) < 5:
            return {"error": "融资余额数据不足"}

        balance = float(rzye.iloc[-1])
        balance_yi = round(balance / 1e8, 2)

        delta = MomentumDelta.compute(rzye, velocity_window=5, zscore_window=60)

        return {
            "balance": balance,
            "balance_yi": balance_yi,
            "delta": delta,
        }

    def analyze_all(
        self,
        margin_df: Optional[pd.DataFrame] = None,
        lookback_days: int = 365,
    ) -> Dict[str, Any]:
        return {
            "vix": self.analyze_vix(lookback_days=lookback_days),
            "credit_spread": self.analyze_credit_spread(lookback_days=lookback_days),
            "margin": self.analyze_margin_balance(margin_df=margin_df),
        }
