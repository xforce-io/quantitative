# Leading Indicators Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Momentum Delta Engine (velocity/acceleration/z-score on any time series) and 3 leading indicators (VIX, credit spread, margin balance) to detect changes before they become obvious, integrated into Dashboard.

**Architecture:** Three-layer separation: (1) Data layer — TushareProvider.get_margin_data() + LeadingIndicatorsDataFetcher for VIX/credit spread via Yahoo/FRED, (2) Analysis layer — MomentumDelta pure computation engine + LeadingIndicatorsAnalyzer that combines fetching with analysis, (3) Web layer — data_service functions + Dashboard page integration. Each layer depends only on the layer below.

**Tech Stack:** pandas, numpy, fredapi, yfinance, streamlit, pytest

---

## File Structure

| Action | File | Layer | Responsibility |
|--------|------|-------|----------------|
| Create | `quant/analysis/indicators/momentum_delta.py` | Analysis | Pure computation: velocity, acceleration, z-score, status, alert |
| Create | `tests/test_momentum_delta.py` | Test | Unit tests with synthetic data (no API calls) |
| Create | `quant/analysis/indicators/leading_indicators.py` | Analysis | Fetch VIX/credit spread/margin + analyze with MomentumDelta |
| Create | `tests/test_leading_indicators.py` | Test | Unit tests with mock data |
| Modify | `quant/data/implementations/tushare_provider.py` | Data | Add `get_margin_data()` |
| Modify | `web/data_service.py` | Web-Data | Add `get_leading_indicators()` with caching |
| Modify | `web/pages/1_📊_Dashboard.py` | Web-UI | Add leading signals row + velocity annotations |

---

### Task 1: MomentumDelta — Pure Computation Engine

**Files:**
- Create: `quant/analysis/indicators/momentum_delta.py`
- Create: `tests/test_momentum_delta.py`

- [ ] **Step 1: Write tests**

Create `tests/test_momentum_delta.py`:

```python
"""Tests for MomentumDelta — pure computation, no API calls."""

import pandas as pd
import numpy as np
import pytest

from quant.analysis.indicators.momentum_delta import MomentumDelta


def _make_series(values: list, name: str = "test") -> pd.Series:
    """Helper: build a DatetimeIndex series from a list of values."""
    idx = pd.date_range("2026-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx, name=name)


class TestCompute:
    """MomentumDelta.compute() behaviour."""

    def test_rising_series_positive_velocity(self):
        # Linearly rising: 50, 52, 54, ..., 68 (10 values)
        s = _make_series([50 + 2 * i for i in range(10)])
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=5)
        assert result["velocity"] > 0
        assert result["status"] in ("accelerating_up", "decelerating_up", "stable")

    def test_falling_series_negative_velocity(self):
        s = _make_series([80 - 3 * i for i in range(10)])
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=5)
        assert result["velocity"] < 0

    def test_constant_series_stable(self):
        s = _make_series([50.0] * 20)
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=10)
        assert result["status"] == "stable"
        assert result["alert"] is None

    def test_acceleration_detects_speedup(self):
        # Quadratic rise: accelerating
        s = _make_series([50 + i**2 * 0.5 for i in range(15)])
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=10)
        assert result["acceleration"] > 0

    def test_streak_counts_consecutive_days(self):
        # 5 flat then 5 rising
        values = [50.0] * 5 + [51, 52, 53, 54, 55]
        s = _make_series(values)
        result = MomentumDelta.compute(s, velocity_window=3, zscore_window=5)
        assert result["streak"] > 0

    def test_zscore_anomaly_generates_alert(self):
        # 60 flat days then a sudden spike
        values = [50.0] * 60 + [50, 52, 58, 70, 85]
        s = _make_series(values)
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=60)
        assert result["alert"] is not None
        assert "标准差" in result["alert"]

    def test_short_series_returns_safe_defaults(self):
        s = _make_series([50, 51])
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=60)
        assert result["velocity"] == 0.0
        assert result["status"] == "stable"

    def test_velocity_series_returned(self):
        s = _make_series([50 + i for i in range(20)])
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=10)
        assert isinstance(result["velocity_series"], pd.Series)
        assert len(result["velocity_series"]) == len(s)

    def test_status_decelerating_up(self):
        # Rise that slows down: large increments then small
        values = [50, 55, 60, 65, 70, 74, 77, 79, 80, 80.5, 80.8, 81, 81, 81, 81]
        s = _make_series(values)
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=10)
        # velocity > 0 but acceleration <= 0
        assert result["velocity"] >= 0
        # Could be decelerating_up or stable depending on thresholds

    def test_status_accelerating_down(self):
        # Fall that speeds up
        values = [80, 79, 77, 74, 70, 65, 59, 52, 44, 35]
        s = _make_series(values)
        result = MomentumDelta.compute(s, velocity_window=5, zscore_window=5)
        assert result["velocity"] < 0
        assert result["acceleration"] < 0


class TestComputeBatch:
    """MomentumDelta.compute_batch() behaviour."""

    def test_batch_returns_dict_per_key(self):
        data = {
            "rsi": _make_series([50 + i for i in range(20)]),
            "volume": _make_series([1000 + i * 100 for i in range(20)]),
        }
        results = MomentumDelta.compute_batch(data)
        assert set(results.keys()) == {"rsi", "volume"}
        assert results["rsi"]["velocity"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_momentum_delta.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quant.analysis.indicators.momentum_delta'`

- [ ] **Step 3: Implement MomentumDelta**

Create `quant/analysis/indicators/momentum_delta.py`:

```python
"""
Momentum Delta Engine — 变化率检测

纯计算模块，不依赖任何数据源。对任意时间序列计算：
- velocity:     一阶导（N日变化率）
- acceleration:  二阶导（velocity 的变化率）
- zscore:        velocity 相对历史的标准差偏离
- streak:        连续同方向变化天数
- status:        人可读的状态标签
- alert:         异动时的人话描述
"""

from typing import Dict, Optional

import numpy as np
import pandas as pd


# velocity 低于此阈值视为 stable
_STABLE_THRESHOLD = 0.5

# zscore 超过此值生成 alert
_ZSCORE_ALERT_THRESHOLD = 2.0

_STATUS_LABELS = {
    "accelerating_up": "加速上行",
    "decelerating_up": "减速上行",
    "accelerating_down": "加速下行",
    "decelerating_down": "减速下行",
    "stable": "平稳",
}


class MomentumDelta:
    """对任意时间序列计算变化率指标。"""

    @staticmethod
    def compute(
        series: pd.Series,
        velocity_window: int = 5,
        zscore_window: int = 60,
    ) -> dict:
        """
        计算变化率指标。

        Args:
            series: 时间序列（如 RSI、资金流净额、置信度分数等）
            velocity_window: 一阶导计算窗口（默认 5 日）
            zscore_window: z-score 参考窗口（默认 60 日）

        Returns:
            dict with keys: velocity, acceleration, zscore, streak,
                            velocity_series, status, status_cn, alert
        """
        if len(series) < velocity_window + 1:
            return {
                "velocity": 0.0,
                "acceleration": 0.0,
                "zscore": 0.0,
                "streak": 0,
                "velocity_series": pd.Series(np.nan, index=series.index),
                "status": "stable",
                "status_cn": _STATUS_LABELS["stable"],
                "alert": None,
            }

        # --- velocity: N-day diff ---
        vel_series = series.diff(velocity_window)
        velocity = float(vel_series.iloc[-1]) if not pd.isna(vel_series.iloc[-1]) else 0.0

        # --- acceleration: velocity diff ---
        acc_series = vel_series.diff(velocity_window)
        acceleration = float(acc_series.iloc[-1]) if not pd.isna(acc_series.iloc[-1]) else 0.0

        # --- z-score of velocity ---
        if len(vel_series.dropna()) >= zscore_window:
            lookback = vel_series.dropna().iloc[-zscore_window:]
            mean = lookback.mean()
            std = lookback.std()
            zscore = float((velocity - mean) / std) if std > 0 else 0.0
        else:
            zscore = 0.0

        # --- streak: consecutive same-direction changes ---
        diffs = series.diff().dropna()
        streak = 0
        if len(diffs) > 0:
            last_sign = np.sign(diffs.iloc[-1])
            if last_sign != 0:
                for val in reversed(diffs.values):
                    if np.sign(val) == last_sign:
                        streak += 1
                    else:
                        break
                streak = int(streak * last_sign)  # negative streak for falling

        # --- status ---
        if abs(velocity) < _STABLE_THRESHOLD:
            status = "stable"
        elif velocity > 0:
            status = "accelerating_up" if acceleration > 0 else "decelerating_up"
        else:
            status = "accelerating_down" if acceleration < 0 else "decelerating_down"

        # --- alert ---
        alert = None
        if abs(zscore) >= _ZSCORE_ALERT_THRESHOLD:
            direction = "加速" if zscore > 0 else "减速"
            alert = f"异常{direction}，偏离均值 {abs(zscore):.1f} 个标准差"

        return {
            "velocity": round(velocity, 4),
            "acceleration": round(acceleration, 4),
            "zscore": round(zscore, 2),
            "streak": streak,
            "velocity_series": vel_series,
            "status": status,
            "status_cn": _STATUS_LABELS[status],
            "alert": alert,
        }

    @staticmethod
    def compute_batch(
        series_dict: Dict[str, pd.Series],
        velocity_window: int = 5,
        zscore_window: int = 60,
    ) -> Dict[str, dict]:
        """对多个序列批量计算。

        Args:
            series_dict: {name: pd.Series} 字典

        Returns:
            {name: compute_result} 字典
        """
        return {
            name: MomentumDelta.compute(s, velocity_window, zscore_window)
            for name, s in series_dict.items()
        }
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_momentum_delta.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/indicators/momentum_delta.py tests/test_momentum_delta.py
git commit -m "feat(analysis): add MomentumDelta engine — velocity/acceleration/zscore"
```

---

### Task 2: Data Layer — TushareProvider.get_margin_data()

**Files:**
- Modify: `quant/data/implementations/tushare_provider.py`
- Create: `tests/test_tushare_margin.py`

- [ ] **Step 1: Write test**

Create `tests/test_tushare_margin.py`:

```python
"""Tests for TushareProvider.get_margin_data() — integration test with real API."""

import pytest
import pandas as pd
from quant.data.implementations.tushare_provider import TushareProvider


@pytest.fixture
def provider():
    return TushareProvider()


class TestGetMarginData:
    def test_returns_dataframe(self, provider):
        df = provider.get_margin_data(lookback_days=30)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_has_required_columns(self, provider):
        df = provider.get_margin_data(lookback_days=10)
        for col in ["trade_date", "rzye"]:
            assert col in df.columns, f"Missing column: {col}"

    def test_sorted_by_date(self, provider):
        df = provider.get_margin_data(lookback_days=30)
        dates = df["trade_date"].tolist()
        assert dates == sorted(dates)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tushare_margin.py -v`
Expected: FAIL — `AttributeError: 'TushareProvider' object has no attribute 'get_margin_data'`

- [ ] **Step 3: Implement get_margin_data()**

Append to `quant/data/implementations/tushare_provider.py`, inside the `TushareProvider` class:

```python
    def get_margin_data(self, lookback_days: int = 90, exchange: str = "SSE") -> pd.DataFrame:
        """
        获取全市场融资融券数据。

        Args:
            lookback_days: 回溯天数
            exchange: 交易所代码，SSE(上交所) 或 SZSE(深交所)

        Returns:
            DataFrame with columns: trade_date, exchange_id, rzye, rzmre, rzche, rqye, ...
            Sorted by trade_date ascending.
        """
        from datetime import datetime, timedelta

        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=lookback_days + 10)
        start_str = start_dt.strftime("%Y%m%d")
        end_str = end_dt.strftime("%Y%m%d")

        try:
            df = self.pro.margin(
                exchange_id=exchange,
                start_date=start_str,
                end_date=end_str,
            )
            if df is None or df.empty:
                return pd.DataFrame()
            return df.sort_values("trade_date").reset_index(drop=True)
        except Exception as e:
            logger.error(f"获取融资融券数据失败: {e}")
            return pd.DataFrame()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_tushare_margin.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add quant/data/implementations/tushare_provider.py tests/test_tushare_margin.py
git commit -m "feat(data): add TushareProvider.get_margin_data() for margin trading data"
```

---

### Task 3: Analysis Layer — LeadingIndicatorsAnalyzer

**Files:**
- Create: `quant/analysis/indicators/leading_indicators.py`
- Create: `tests/test_leading_indicators.py`

- [ ] **Step 1: Write tests**

Create `tests/test_leading_indicators.py`:

```python
"""Tests for LeadingIndicatorsAnalyzer — mock all external data sources."""

import pandas as pd
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from quant.analysis.indicators.leading_indicators import LeadingIndicatorsAnalyzer


def _make_daily_series(values: list, start: str = "2026-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, index=idx)


class TestAnalyzeVix:
    @patch("quant.analysis.indicators.leading_indicators.yf")
    def test_returns_vix_with_delta(self, mock_yf):
        prices = [18.0 + i * 0.3 for i in range(30)]
        mock_df = pd.DataFrame(
            {"Close": prices},
            index=pd.date_range("2026-01-01", periods=30, freq="D"),
        )
        mock_yf.download.return_value = mock_df

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_vix(lookback_days=30)

        assert "value" in result
        assert "delta" in result
        assert result["delta"]["velocity"] > 0  # rising VIX
        assert result["level"] in ("normal", "elevated", "fear", "panic")

    @patch("quant.analysis.indicators.leading_indicators.yf")
    def test_vix_empty_data(self, mock_yf):
        mock_yf.download.return_value = pd.DataFrame()
        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_vix()
        assert "error" in result


class TestAnalyzeCreditSpread:
    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_returns_spread_with_delta(self, mock_get_fred):
        mock_fred = MagicMock()
        hy_values = _make_daily_series([4.5 + i * 0.02 for i in range(30)])
        bbb_values = _make_daily_series([1.5 + i * 0.005 for i in range(30)])
        mock_fred.get_series.side_effect = [hy_values, bbb_values]
        mock_get_fred.return_value = mock_fred

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_credit_spread(lookback_days=30)

        assert "spread" in result
        assert "delta" in result
        assert result["level"] in ("normal", "elevated", "stress", "crisis")

    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_credit_spread_error(self, mock_get_fred):
        mock_get_fred.side_effect = Exception("FRED unavailable")
        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_credit_spread()
        assert "error" in result


class TestAnalyzeMarginBalance:
    def test_returns_margin_with_delta(self):
        dates = pd.date_range("2026-01-01", periods=30, freq="D")
        margin_df = pd.DataFrame({
            "trade_date": [d.strftime("%Y%m%d") for d in dates],
            "rzye": [1.3e12 + i * 1e9 for i in range(30)],
            "rzmre": [5e9] * 30,
            "rzche": [4e9] * 30,
        })

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_margin_balance(margin_df=margin_df)

        assert "balance_yi" in result  # 亿元
        assert "delta" in result
        assert result["delta"]["velocity"] > 0  # rising balance


class TestAnalyzeAll:
    @patch("quant.analysis.indicators.leading_indicators.yf")
    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_analyze_all_returns_three_indicators(self, mock_get_fred, mock_yf):
        # VIX
        mock_yf.download.return_value = pd.DataFrame(
            {"Close": [20.0] * 30},
            index=pd.date_range("2026-01-01", periods=30, freq="D"),
        )

        # Credit spread
        mock_fred = MagicMock()
        mock_fred.get_series.return_value = _make_daily_series([3.0] * 30)
        mock_get_fred.return_value = mock_fred

        # Margin (pass directly)
        dates = pd.date_range("2026-01-01", periods=30, freq="D")
        margin_df = pd.DataFrame({
            "trade_date": [d.strftime("%Y%m%d") for d in dates],
            "rzye": [1.3e12] * 30,
        })

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_all(margin_df=margin_df, lookback_days=30)

        assert "vix" in result
        assert "credit_spread" in result
        assert "margin" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_leading_indicators.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement LeadingIndicatorsAnalyzer**

Create `quant/analysis/indicators/leading_indicators.py`:

```python
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

# VIX 分级阈值
_VIX_LEVELS = [
    (40, "panic", "极度恐慌", "🔴"),
    (30, "fear", "恐慌", "🟠"),
    (20, "elevated", "偏高", "🟡"),
    (0, "normal", "正常", "🟢"),
]

# 信用利差分级阈值 (HY - BBB, percentage points)
_CREDIT_LEVELS = [
    (8.0, "crisis", "危机", "🔴"),
    (5.0, "stress", "紧缩", "🟠"),
    (3.0, "elevated", "偏高", "🟡"),
    (0.0, "normal", "正常", "🟢"),
]


def _classify(value: float, levels: list) -> tuple:
    """Match value against threshold levels, return (level, label_cn, emoji)."""
    for threshold, level, label_cn, emoji in levels:
        if value >= threshold:
            return level, label_cn, emoji
    last = levels[-1]
    return last[1], last[2], last[3]


class LeadingIndicatorsAnalyzer:
    """领先指标分析器。"""

    def __init__(self, fred_api_key: Optional[str] = None):
        self._fred = None
        self._fred_api_key = fred_api_key

    def _get_fred(self):
        """懒加载 FRED 客户端。"""
        if self._fred is None:
            from fredapi import Fred
            from dotenv import load_dotenv
            load_dotenv()
            api_key = self._fred_api_key or os.environ.get("FRED_API_KEY")
            if not api_key:
                raise ValueError("需要 FRED_API_KEY 环境变量")
            self._fred = Fred(api_key=api_key)
        return self._fred

    # ------------------------------------------------------------------
    # 1. VIX
    # ------------------------------------------------------------------

    def analyze_vix(self, lookback_days: int = 365) -> Dict[str, Any]:
        """获取 VIX 并计算变化率。"""
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

    # ------------------------------------------------------------------
    # 2. 信用利差
    # ------------------------------------------------------------------

    def analyze_credit_spread(self, lookback_days: int = 365) -> Dict[str, Any]:
        """获取 HY-BBB 信用利差并计算变化率。"""
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

    # ------------------------------------------------------------------
    # 3. 融资余额
    # ------------------------------------------------------------------

    def analyze_margin_balance(
        self,
        margin_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        分析融资余额变化率。

        Args:
            margin_df: 融资融券 DataFrame (由调用方通过 TushareProvider.get_margin_data() 获取)
                       必须包含 trade_date, rzye 列

        Returns:
            分析结果 dict
        """
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
        balance_yi = round(balance / 1e8, 2)  # 转为亿元

        delta = MomentumDelta.compute(rzye, velocity_window=5, zscore_window=60)

        return {
            "balance": balance,
            "balance_yi": balance_yi,
            "delta": delta,
        }

    # ------------------------------------------------------------------
    # 聚合
    # ------------------------------------------------------------------

    def analyze_all(
        self,
        margin_df: Optional[pd.DataFrame] = None,
        lookback_days: int = 365,
    ) -> Dict[str, Any]:
        """
        分析全部 3 个领先指标。

        Args:
            margin_df: 融资融券 DataFrame (调用方负责获取)
            lookback_days: VIX/信用利差回溯天数

        Returns:
            {"vix": {...}, "credit_spread": {...}, "margin": {...}}
        """
        return {
            "vix": self.analyze_vix(lookback_days=lookback_days),
            "credit_spread": self.analyze_credit_spread(lookback_days=lookback_days),
            "margin": self.analyze_margin_balance(margin_df=margin_df),
        }
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_leading_indicators.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/indicators/leading_indicators.py tests/test_leading_indicators.py
git commit -m "feat(analysis): add LeadingIndicatorsAnalyzer — VIX, credit spread, margin"
```

---

### Task 4: Web Data Service Layer

**Files:**
- Modify: `web/data_service.py`

- [ ] **Step 1: Add `get_leading_indicators()` to data_service.py**

Append to end of `web/data_service.py` (before `get_dashboard_summary`):

```python
@st.cache_data(ttl=3600, show_spinner=False)  # 1 hour cache
def get_leading_indicators(lookback_days: int = 365) -> Dict[str, Any]:
    """
    获取三个领先指标分析结果（VIX / 信用利差 / 融资余额）。
    数据层与分析层解耦：margin 数据从 TushareProvider 获取后传入 analyzer。
    """
    from quant.analysis.indicators.leading_indicators import LeadingIndicatorsAnalyzer

    analyzer = LeadingIndicatorsAnalyzer()

    # 获取融资融券数据（数据层）
    margin_df = None
    try:
        provider = get_provider()
        margin_df = provider.get_margin_data(lookback_days=90)
    except Exception as e:
        logger.warning(f"融资融券数据获取失败: {e}")

    # 分析（能力层）
    result = analyzer.analyze_all(margin_df=margin_df, lookback_days=lookback_days)

    # 过滤掉 series 数据（不能被 st.cache_data 序列化为 hashable）
    for key in result:
        if isinstance(result[key], dict) and "series" in result[key]:
            del result[key]["series"]
        if isinstance(result[key], dict) and "delta" in result[key]:
            delta = result[key]["delta"]
            if "velocity_series" in delta:
                del delta["velocity_series"]

    return result
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from web.data_service import get_leading_indicators; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add web/data_service.py
git commit -m "feat(web): add get_leading_indicators() to data service layer"
```

---

### Task 5: Dashboard Integration — Leading Signals Row + Velocity Annotations

**Files:**
- Modify: `web/pages/1_📊_Dashboard.py`

- [ ] **Step 1: Add leading signals row**

Add import at top of `web/pages/1_📊_Dashboard.py`, alongside existing imports:

```python
from web.data_service import (
    get_global_usd_liquidity,
    get_macro_liquidity,
    get_china_market_signals,
    get_stock_money_flow,
    get_stock_technical_data,
    get_leading_indicators,
)
```

Add new function after `_render_macro_bar()`:

```python
# ==================== 领先信号 ====================

_VELOCITY_ARROWS = {
    "accelerating_up": "⬆️",
    "decelerating_up": "↗️",
    "accelerating_down": "⬇️",
    "decelerating_down": "↘️",
    "stable": "→",
}


def _render_leading_signals():
    """领先信号一行三灯。"""
    st.markdown("### ⚡ 领先信号")

    try:
        data = get_leading_indicators(lookback_days=365)
    except Exception:
        st.warning("领先指标数据获取失败")
        return

    col1, col2, col3 = st.columns(3)

    # VIX
    with col1:
        vix = data.get("vix", {})
        if "error" in vix:
            st.metric("VIX 恐慌指数", "获取失败")
        else:
            value = vix.get("value", 0)
            emoji = vix.get("emoji", "⚪")
            level_cn = vix.get("level_cn", "")
            delta = vix.get("delta", {})
            arrow = _VELOCITY_ARROWS.get(delta.get("status", "stable"), "→")
            status_cn = delta.get("status_cn", "")

            st.metric("VIX 恐慌指数", f"{emoji} {value:.1f}", f"{arrow} {status_cn}")

            alert = delta.get("alert")
            if alert:
                st.caption(f"⚠️ {alert}")
            streak = delta.get("streak", 0)
            if abs(streak) >= 3:
                direction = "上升" if streak > 0 else "下降"
                st.caption(f"连续 {abs(streak)} 日{direction}")

    # 信用利差
    with col2:
        cs = data.get("credit_spread", {})
        if "error" in cs:
            st.metric("信用利差 HY-IG", "获取失败")
        else:
            spread = cs.get("spread", 0)
            emoji = cs.get("emoji", "⚪")
            level_cn = cs.get("level_cn", "")
            delta = cs.get("delta", {})
            arrow = _VELOCITY_ARROWS.get(delta.get("status", "stable"), "→")
            status_cn = delta.get("status_cn", "")

            st.metric("信用利差 HY-IG", f"{emoji} {spread:.2f}%", f"{arrow} {status_cn}")

            alert = delta.get("alert")
            if alert:
                st.caption(f"⚠️ {alert}")

    # 融资余额
    with col3:
        margin = data.get("margin", {})
        if "error" in margin:
            st.metric("融资余额", margin.get("error", "获取失败"))
        else:
            balance_yi = margin.get("balance_yi", 0)
            delta = margin.get("delta", {})
            arrow = _VELOCITY_ARROWS.get(delta.get("status", "stable"), "→")
            status_cn = delta.get("status_cn", "")

            st.metric("融资余额", f"{balance_yi:.0f} 亿", f"{arrow} {status_cn}")

            alert = delta.get("alert")
            if alert:
                st.caption(f"⚠️ {alert}")
            streak = delta.get("streak", 0)
            if abs(streak) >= 3:
                direction = "增加" if streak > 0 else "减少"
                st.caption(f"连续 {abs(streak)} 日{direction}")
```

- [ ] **Step 2: Add velocity annotations to macro bar**

Update `_render_macro_bar()` to show velocity on USD Liquidity metric. Change the USD Liquidity block:

In the existing `_render_macro_bar()`, replace the USD Liquidity `with col1:` block to add velocity:

```python
    with col1:
        try:
            usd = get_global_usd_liquidity()
            confidence = usd.get('confidence')
            wow = usd.get('wow_change')
            velocity = usd.get('velocity')
            if confidence is not None:
                arrow = "↑" if (wow or 0) > 2 else ("↓" if (wow or 0) < -2 else "→")
                delta_text = f"{arrow} 周变化 {wow:+.1f}pp" if wow else None
                st.metric("美元流动性", f"{confidence:+.1f}%", delta_text)
                if velocity is not None and abs(velocity) > 1:
                    v_dir = "加速宽松" if velocity > 0 else "加速收紧"
                    st.caption(f"⚡ {v_dir} (v={velocity:+.1f})")
            else:
                st.metric("美元流动性", "暂无数据")
        except Exception:
            st.metric("美元流动性", "获取失败")
```

- [ ] **Step 3: Add velocity reasons to watchlist alerts**

In `_analyze_stock_signals()`, after the existing volume anomaly section and before the `# 没有任何信号触发` comment, add velocity-based reasons using MomentumDelta:

```python
    # ---------- Velocity 异动 (MomentumDelta) ----------
    from quant.analysis.indicators.momentum_delta import MomentumDelta

    # RSI velocity
    if 'RSI' in df.columns and len(df) >= 10:
        rsi_series = df['RSI'].dropna()
        if len(rsi_series) >= 10:
            rsi_delta = MomentumDelta.compute(rsi_series, velocity_window=5, zscore_window=min(60, len(rsi_series)))
            if rsi_delta['alert']:
                reasons.append((f"RSI {rsi_delta['status_cn']} ({rsi_delta['alert']})", +8, "neutral"))
                score += 8
            elif abs(rsi_delta['streak']) >= 5:
                direction = "上行" if rsi_delta['streak'] > 0 else "下行"
                reasons.append((f"RSI 连续 {abs(rsi_delta['streak'])} 日{direction}", +5, "neutral"))
                score += 5

    # Volume velocity
    if 'volume' in df.columns and len(df) >= 10:
        vol_series = df['volume'].dropna()
        if len(vol_series) >= 10:
            vol_delta = MomentumDelta.compute(vol_series, velocity_window=5, zscore_window=min(60, len(vol_series)))
            if vol_delta['alert']:
                reasons.append((f"量能 {vol_delta['status_cn']} ({vol_delta['alert']})", +8, "neutral"))
                score += 8
```

- [ ] **Step 4: Wire up in main()**

In `main()`, add the leading signals call between macro bar and watchlist alerts:

```python
def main():
    apply_custom_css()

    st.title("📊 总览")
    st.caption("宏观环境 + 领先信号 + 持仓预警 — 打开就知道现在该干什么")

    _render_macro_bar()
    st.divider()
    _render_leading_signals()
    st.divider()
    _render_watchlist_alerts()
    _render_legend()
```

- [ ] **Step 5: Update legend to include velocity explanation**

In `_render_legend()`, add velocity explanation to the markdown:

```python
def _render_legend():
    """显示信号分级图例。"""
    with st.expander("📖 信号分级说明", expanded=False):
        st.markdown("""
| 等级 | 分数 | 含义 |
|------|------|------|
| 🔴 强信号 | 85+ | 多个技术指标同时触发，需要立即关注 |
| 🟠 信号 | 75-84 | 有明确的技术信号，建议查看详情 |
| 🟡 预警 | 60-74 | 出现早期迹象，保持观察 |
| ⚪ 观察 | 40-59 | 有轻微异动，暂不需要行动 |
| 🟢 平静 | <40 | 无明显信号，不展示 |

**信号来源：** RSI 超买超卖、均线排列与突破、MACD 金叉死叉、成交量异动、均线偏离度

**变化率标注：**
| 箭头 | 含义 |
|------|------|
| ⬆️ | 加速上行 — 指标在加速上升 |
| ↗️ | 减速上行 — 仍在上升但动能减弱，可能见顶 |
| ⬇️ | 加速下行 — 指标在加速下降 |
| ↘️ | 减速下行 — 仍在下降但跌势减缓，可能见底 |
| → | 平稳 — 无明显变化 |
        """)
```

- [ ] **Step 6: Verify Dashboard loads**

Open http://localhost:8501 and navigate to Dashboard page. Verify:
- Macro bar shows velocity annotation on USD Liquidity
- Leading signals row shows VIX, credit spread, margin balance with arrows
- Watchlist alerts include velocity reasons where triggered
- No import errors

- [ ] **Step 7: Commit**

```bash
git add web/pages/1_📊_Dashboard.py
git commit -m "feat(dashboard): integrate leading signals + velocity annotations"
```
