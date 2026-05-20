# Global USD Liquidity Confidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a "-100% to +100%" global USD liquidity confidence indicator (replicating Attractor Alice [A0007]) with a dedicated Streamlit page.

**Architecture:** A standalone `GlobalUsdLiquidityAnalyzer` fetches 9 sub-indicators from FRED, computes rolling 2-year percentile ranks, maps them to confidence scores with polarity handling, and aggregates into 3 groups (onshore 40%, offshore/stress 30%, net liquidity 30%). A Streamlit page renders the confidence curve and sub-indicator breakdown.

**Tech Stack:** Python, fredapi, scipy, pandas, numpy, Streamlit, plotly

**Spec:** `docs/superpowers/specs/2026-03-23-global-usd-liquidity-confidence-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `quant/analysis/indicators/global_usd_liquidity.py` | Core analyzer: fetch FRED data, compute percentile confidence, aggregate |
| `tests/analysis/test_global_usd_liquidity.py` | Unit tests for confidence calculation logic |
| `web/data_service.py` | Add `get_global_usd_liquidity()` with caching (modify existing) |
| `web/pages/6_💧_USD_Liquidity.py` | Streamlit page: confidence chart + sub-indicator details |

---

### Task 1: Core Confidence Calculation Engine

**Files:**
- Create: `tests/analysis/test_global_usd_liquidity.py`
- Create: `quant/analysis/indicators/global_usd_liquidity.py`

This task builds the pure calculation logic (no FRED calls). The analyzer's internal methods for percentile ranking, polarity inversion, and group aggregation.

- [ ] **Step 1: Write failing tests for percentile-to-confidence conversion**

```python
# tests/analysis/test_global_usd_liquidity.py
import pytest
import numpy as np
import pandas as pd
from quant.analysis.indicators.global_usd_liquidity import (
    percentile_to_confidence,
    compute_rolling_confidence,
    aggregate_group_confidence,
    aggregate_total_confidence,
    INDICATOR_CONFIG,
    GROUP_WEIGHTS,
)


class TestPercentileToConfidence:
    """百分位 → 置信度映射"""

    def test_median_gives_zero(self):
        assert percentile_to_confidence(50.0) == 0.0

    def test_max_gives_positive_100(self):
        assert percentile_to_confidence(100.0) == 100.0

    def test_min_gives_negative_100(self):
        assert percentile_to_confidence(0.0) == -100.0

    def test_75th_percentile(self):
        assert percentile_to_confidence(75.0) == 50.0

    def test_inverted_polarity(self):
        # For inverted indicators: high percentile → negative confidence
        assert percentile_to_confidence(75.0, inverted=True) == -50.0
        assert percentile_to_confidence(25.0, inverted=True) == 50.0
        assert percentile_to_confidence(50.0, inverted=True) == 0.0


class TestComputeRollingConfidence:
    """滚动窗口百分位置信度计算"""

    def test_basic_rolling(self):
        # 100 data points, linearly increasing
        data = pd.Series(range(100), index=pd.date_range('2024-01-01', periods=100, freq='B'))
        result = compute_rolling_confidence(data, window=50, inverted=False)
        valid = result.dropna()
        # First value with window is at index 50, its value is 50 (max in 0..49 window)
        # → percentile ~100% → confidence near +100
        assert valid.iloc[0] > 90.0
        # Last value (99) is also max in its window → near +100
        assert valid.iloc[-1] > 90.0

    def test_inverted_rolling(self):
        data = pd.Series(range(100), index=pd.date_range('2024-01-01', periods=100))
        result = compute_rolling_confidence(data, window=50, inverted=True)
        # Last value (max) → inverted → near -100
        assert result.iloc[-1] < -90.0

    def test_constant_series_gives_zero(self):
        data = pd.Series([5.0] * 100, index=pd.date_range('2024-01-01', periods=100))
        result = compute_rolling_confidence(data, window=50, inverted=False)
        # All same → percentile ~50 → confidence ~0
        assert abs(result.iloc[-1]) < 1.0

    def test_insufficient_data_returns_nan(self):
        data = pd.Series([1, 2, 3], index=pd.date_range('2024-01-01', periods=3))
        result = compute_rolling_confidence(data, window=504, inverted=False)
        # Not enough data for window, should be all NaN
        assert result.isna().all()


class TestAggregateGroupConfidence:
    """组内等权平均"""

    def test_simple_average(self):
        values = {'a': 40.0, 'b': 60.0, 'c': -20.0}
        result = aggregate_group_confidence(values)
        assert abs(result - 26.67) < 0.1

    def test_single_value(self):
        values = {'a': -50.0}
        result = aggregate_group_confidence(values)
        assert result == -50.0

    def test_empty_returns_none(self):
        result = aggregate_group_confidence({})
        assert result is None

    def test_skips_none_values(self):
        values = {'a': 40.0, 'b': None, 'c': -20.0}
        result = aggregate_group_confidence(values)
        assert abs(result - 10.0) < 0.1


class TestAggregateTotalConfidence:
    """组间加权聚合 + 失败组重归一化"""

    def test_normal_aggregation(self):
        groups = {
            'onshore': -42.0,
            'offshore': -65.0,
            'net_liquidity': -28.0,
        }
        # -42*0.4 + -65*0.3 + -28*0.3 = -16.8 + -19.5 + -8.4 = -44.7
        result = aggregate_total_confidence(groups, GROUP_WEIGHTS)
        assert abs(result - (-44.7)) < 0.1

    def test_one_group_failed(self):
        groups = {
            'onshore': -42.0,
            'offshore': None,  # failed
            'net_liquidity': -28.0,
        }
        # Renormalize: onshore 0.4/(0.4+0.3)=0.571, net_liq 0.3/(0.4+0.3)=0.429
        # -42*0.571 + -28*0.429 = -23.98 + -12.01 = -35.99
        result = aggregate_total_confidence(groups, GROUP_WEIGHTS)
        assert abs(result - (-36.0)) < 0.5

    def test_all_groups_failed(self):
        groups = {'onshore': None, 'offshore': None, 'net_liquidity': None}
        result = aggregate_total_confidence(groups, GROUP_WEIGHTS)
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/analysis/test_global_usd_liquidity.py -v`
Expected: ImportError — module does not exist yet.

- [ ] **Step 3: Implement the core calculation functions**

```python
# quant/analysis/indicators/global_usd_liquidity.py
"""
全球美元流动性置信度分析器 (Global USD Liquidity Confidence Analyzer)

复刻吸引子 Alice 系统 [A0007]，将多维美元流动性子指标通过百分位排名法
合成为 -100% ~ +100% 的置信度值。

正值 = 流动性宽松趋势
负值 = 流动性收紧趋势
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from scipy.stats import percentileofscore

project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from quant.core.logging_config import get_logger

logger = get_logger(__name__)

# --- Configuration ---

# Each indicator: FRED series, computation, polarity, group, frequency
INDICATOR_CONFIG = {
    # Onshore USD liquidity premium
    'cp_treasury_spread': {
        'fred_series': ['DCPF3M', 'DGS3MO'],
        'compute': 'subtract',  # DCPF3M - DGS3MO
        'inverted': True,       # higher spread → tighter
        'group': 'onshore',
        'frequency': 'daily',
        'label': '商票-美债溢价',
    },
    'sofr': {
        'fred_series': ['SOFR'],
        'compute': 'direct',
        'inverted': True,
        'group': 'onshore',
        'frequency': 'daily',
        'label': 'SOFR',
    },
    'effr_iorb_spread': {
        'fred_series': ['EFFR', 'IORB'],
        'compute': 'subtract',  # EFFR - IORB
        'inverted': True,
        'group': 'onshore',
        'frequency': 'daily',
        'label': 'EFFR-IORB 溢价',
    },
    'sofr_iorb_spread': {
        'fred_series': ['SOFR', 'IORB'],
        'compute': 'subtract',  # SOFR - IORB
        'inverted': True,
        'group': 'onshore',
        'frequency': 'daily',
        'label': 'SOFR-IORB 溢价',
    },
    # Offshore / financial stress (proxies for basis swaps)
    'nfcirisk': {
        'fred_series': ['NFCIRISK'],
        'compute': 'direct',
        'inverted': True,  # positive = tighter than average
        'group': 'offshore',
        'frequency': 'weekly',
        'label': 'NFCI 风险子指数',
    },
    'stlfsi4': {
        'fred_series': ['STLFSI4'],
        'compute': 'direct',
        'inverted': True,  # positive = stress above average
        'group': 'offshore',
        'frequency': 'weekly',
        'label': '金融压力指数',
    },
    # Net liquidity fundamentals
    'net_liquidity': {
        'fred_series': ['WALCL', 'WTREGEN', 'RRPONTSYD'],
        'compute': 'net_liquidity',  # WALCL - WTREGEN - RRPONTSYD
        'inverted': False,  # higher = more liquidity = positive
        'group': 'net_liquidity',
        'frequency': 'weekly',
        'label': '净流动性',
    },
}

GROUP_WEIGHTS = {
    'onshore': 0.40,
    'offshore': 0.30,
    'net_liquidity': 0.30,
}

GROUP_LABELS = {
    'onshore': '在岸美元流动性溢价',
    'offshore': '离岸/资金面压力',
    'net_liquidity': '净流动性基本面',
}

# Rolling percentile window: ~2 years of trading days
PERCENTILE_WINDOW = 504


# --- Pure Calculation Functions ---

def percentile_to_confidence(percentile: float, inverted: bool = False) -> float:
    """
    Convert a 0-100 percentile to -100% to +100% confidence.

    Args:
        percentile: 0-100 percentile rank
        inverted: If True, high percentile → negative confidence (tighter)
    """
    confidence = (percentile - 50) * 2
    if inverted:
        confidence = -confidence
    return round(confidence, 2)


def compute_rolling_confidence(
    series: pd.Series,
    window: int = PERCENTILE_WINDOW,
    inverted: bool = False,
) -> pd.Series:
    """
    Compute rolling percentile-based confidence for a time series.

    For each date, calculates the percentile rank of the current value
    within the preceding `window` observations, then maps to confidence.

    Args:
        series: Daily time series (DatetimeIndex)
        window: Rolling lookback window in observations
        inverted: Whether to invert polarity

    Returns:
        Series of confidence values (-100 to +100), NaN where insufficient data
    """
    result = pd.Series(np.nan, index=series.index)

    for i in range(window, len(series)):
        lookback = series.iloc[i - window + 1:i + 1]  # inclusive of current value
        current = series.iloc[i]
        if pd.isna(current) or lookback.dropna().empty:
            continue
        pctile = percentileofscore(lookback.dropna().values, current, kind='rank')
        result.iloc[i] = percentile_to_confidence(pctile, inverted=inverted)

    return result


def aggregate_group_confidence(values: Dict[str, Optional[float]]) -> Optional[float]:
    """
    Equal-weight average of confidence values within a group.
    Skips None values. Returns None if all values are None.
    """
    valid = [v for v in values.values() if v is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 2)


def aggregate_total_confidence(
    groups: Dict[str, Optional[float]],
    weights: Dict[str, float],
) -> Optional[float]:
    """
    Weighted aggregation of group confidences with renormalization on failure.

    If a group's confidence is None, its weight is redistributed
    proportionally among remaining groups.
    """
    valid_groups = {k: v for k, v in groups.items() if v is not None}
    if not valid_groups:
        return None

    total_weight = sum(weights[k] for k in valid_groups)
    result = sum(
        v * (weights[k] / total_weight)
        for k, v in valid_groups.items()
    )
    return round(result, 2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/analysis/test_global_usd_liquidity.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/indicators/global_usd_liquidity.py tests/analysis/test_global_usd_liquidity.py
git commit -m "feat: add core confidence calculation for global USD liquidity

Implements percentile-to-confidence mapping, rolling window calculation,
and group-level aggregation with weight renormalization."
```

---

### Task 2: FRED Data Fetching Layer

**Files:**
- Modify: `quant/analysis/indicators/global_usd_liquidity.py`
- Modify: `tests/analysis/test_global_usd_liquidity.py`

Add the `GlobalUsdLiquidityAnalyzer` class that fetches FRED data and computes per-indicator raw series.

- [ ] **Step 1: Write failing test for FRED data fetching**

```python
# Append to tests/analysis/test_global_usd_liquidity.py
from unittest.mock import patch, MagicMock


class TestFetchIndicatorSeries:
    """FRED data fetch → raw series computation"""

    def _make_fred_series(self, values, start='2023-01-01'):
        """Helper: create a pandas Series mimicking FRED output."""
        dates = pd.date_range(start, periods=len(values), freq='B')
        return pd.Series(values, index=dates)

    @patch.object(GlobalUsdLiquidityAnalyzer, '_get_fred')
    def test_direct_indicator(self, mock_get_fred):
        """SOFR: single series, direct use"""
        mock_fred = MagicMock()
        sofr_data = self._make_fred_series([4.3] * 100)
        mock_fred.get_series.return_value = sofr_data
        mock_get_fred.return_value = mock_fred

        analyzer = GlobalUsdLiquidityAnalyzer(fred_api_key='fake')
        result = analyzer._fetch_indicator_series('sofr', lookback_days=365)
        assert isinstance(result, pd.Series)
        assert len(result) == 100

    @patch.object(GlobalUsdLiquidityAnalyzer, '_get_fred')
    def test_subtract_indicator(self, mock_get_fred):
        """CP-Treasury spread: two series subtracted"""
        mock_fred = MagicMock()
        cp_data = self._make_fred_series([5.0] * 100)
        tsy_data = self._make_fred_series([4.3] * 100)
        mock_fred.get_series.side_effect = [cp_data, tsy_data]
        mock_get_fred.return_value = mock_fred

        analyzer = GlobalUsdLiquidityAnalyzer(fred_api_key='fake')
        result = analyzer._fetch_indicator_series('cp_treasury_spread', lookback_days=365)
        assert isinstance(result, pd.Series)
        assert abs(result.iloc[-1] - 0.7) < 0.01

    @patch.object(GlobalUsdLiquidityAnalyzer, '_get_fred')
    def test_net_liquidity_indicator(self, mock_get_fred):
        """Net liquidity: WALCL - WTREGEN - RRPONTSYD"""
        mock_fred = MagicMock()
        walcl = self._make_fred_series([8_000_000] * 50)  # Weekly, in millions
        wtregen = self._make_fred_series([800_000] * 50)
        rrp = self._make_fred_series([500_000] * 100)  # Daily
        mock_fred.get_series.side_effect = [walcl, wtregen, rrp]
        mock_get_fred.return_value = mock_fred

        analyzer = GlobalUsdLiquidityAnalyzer(fred_api_key='fake')
        result = analyzer._fetch_indicator_series('net_liquidity', lookback_days=365)
        assert isinstance(result, pd.Series)
        # Should be forward-filled and aligned to daily
```

Add import at top of test file:
```python
from quant.analysis.indicators.global_usd_liquidity import GlobalUsdLiquidityAnalyzer
```

- [ ] **Step 2: Run tests to verify the new tests fail**

Run: `PYTHONPATH=. pytest tests/analysis/test_global_usd_liquidity.py::TestFetchIndicatorSeries -v`
Expected: FAIL — `GlobalUsdLiquidityAnalyzer` not defined.

- [ ] **Step 3: Implement the analyzer class with FRED fetching**

Append to `quant/analysis/indicators/global_usd_liquidity.py`:

```python
class GlobalUsdLiquidityAnalyzer:
    """
    全球美元流动性置信度分析器

    Fetches FRED data for 7 sub-indicators across 3 groups,
    computes rolling percentile-based confidence scores.
    """

    def __init__(self, fred_api_key: Optional[str] = None):
        self._fred = None
        self._fred_api_key = fred_api_key

    def _get_fred(self):
        """Lazy-load FRED client (same pattern as MacroLiquidityAnalyzer)."""
        if self._fred is None:
            from fredapi import Fred
            import os
            from dotenv import load_dotenv
            load_dotenv()
            api_key = self._fred_api_key or os.environ.get('FRED_API_KEY')
            if not api_key:
                raise ValueError(
                    "需要 FRED API Key，请设置环境变量 FRED_API_KEY 或传入参数。"
                )
            self._fred = Fred(api_key=api_key)
        return self._fred

    def _fetch_indicator_series(
        self, indicator_name: str, lookback_days: int = 1095
    ) -> pd.Series:
        """
        Fetch raw time series for a single indicator from FRED.

        Args:
            indicator_name: Key from INDICATOR_CONFIG
            lookback_days: How many days of history to fetch (default 3 years)

        Returns:
            Daily-frequency pd.Series (forward-filled if weekly source)
        """
        config = INDICATOR_CONFIG[indicator_name]
        fred = self._get_fred()
        start_date = datetime.now() - timedelta(days=lookback_days)

        series_list = []
        for series_id in config['fred_series']:
            data = fred.get_series(series_id, observation_start=start_date)
            if data is not None:
                data = data.dropna()
            series_list.append(data)

        # Compute the indicator value
        compute = config['compute']
        if compute == 'direct':
            result = series_list[0]
        elif compute == 'subtract':
            # Align two series and subtract
            s1, s2 = series_list[0], series_list[1]
            combined = pd.DataFrame({'s1': s1, 's2': s2})
            combined = combined.ffill().dropna()
            result = combined['s1'] - combined['s2']
        elif compute == 'net_liquidity':
            # WALCL - WTREGEN - RRPONTSYD
            walcl, wtregen, rrp = series_list
            combined = pd.DataFrame({
                'walcl': walcl, 'wtregen': wtregen, 'rrp': rrp
            })
            combined = combined.ffill().dropna()
            result = combined['walcl'] - combined['wtregen'] - combined['rrp']
        else:
            raise ValueError(f"Unknown compute type: {compute}")

        # Forward-fill to daily frequency
        result = result.asfreq('D').ffill()

        return result.dropna()

    def analyze(self, lookback_days: int = 1095, display_days: int = 365) -> Dict[str, Any]:
        """
        Run full analysis: fetch all indicators, compute confidence.

        Args:
            lookback_days: Total data to fetch (default 3 years for 2yr window + 1yr display)
            display_days: How many days of confidence history to return

        Returns:
            Dict with total confidence, group confidences, indicator details, and time series
        """
        indicator_results = {}
        indicator_series = {}

        # Phase 1: Fetch all indicator series
        for name, config in INDICATOR_CONFIG.items():
            try:
                series = self._fetch_indicator_series(name, lookback_days)
                indicator_series[name] = series
                logger.info(f"✅ {config['label']}: {len(series)} data points")
            except Exception as e:
                logger.error(f"❌ {config['label']} 获取失败: {e}")
                indicator_results[name] = {
                    'error': str(e),
                    'label': config['label'],
                    'group': config['group'],
                }

        # Phase 2: Compute rolling confidence for each indicator
        confidence_series = {}
        for name, series in indicator_series.items():
            config = INDICATOR_CONFIG[name]
            conf_series = compute_rolling_confidence(
                series, window=PERCENTILE_WINDOW, inverted=config['inverted']
            )
            confidence_series[name] = conf_series

            # Extract latest values
            latest_conf = conf_series.dropna()
            if not latest_conf.empty:
                current_value = series.iloc[-1]
                pctile = percentileofscore(
                    series.iloc[-PERCENTILE_WINDOW:].dropna().values,
                    current_value,
                    kind='rank',
                )
                indicator_results[name] = {
                    'label': config['label'],
                    'group': config['group'],
                    'current_value': round(float(current_value), 4),
                    'percentile': round(pctile, 1),
                    'confidence': float(latest_conf.iloc[-1]),
                    'series': conf_series,
                }
            else:
                indicator_results[name] = {
                    'label': config['label'],
                    'group': config['group'],
                    'error': '数据不足，无法计算置信度',
                }

        # Phase 3: Aggregate by group
        group_confidences = {}
        group_details = {}
        for group_name in GROUP_WEIGHTS:
            group_indicators = {
                k: v.get('confidence')
                for k, v in indicator_results.items()
                if v.get('group') == group_name and 'confidence' in v
            }
            group_conf = aggregate_group_confidence(group_indicators)
            group_confidences[group_name] = group_conf
            group_details[group_name] = {
                'label': GROUP_LABELS[group_name],
                'confidence': group_conf,
                'weight': GROUP_WEIGHTS[group_name],
                'indicators': {
                    k: v for k, v in indicator_results.items()
                    if v.get('group') == group_name
                },
            }

        # Phase 4: Total confidence
        total_confidence = aggregate_total_confidence(group_confidences, GROUP_WEIGHTS)

        # Phase 5: Build composite confidence time series (for chart)
        composite_series = self._build_composite_series(
            confidence_series, display_days
        )

        # Week-over-week change (5 trading days)
        wow_change = None
        if composite_series is not None and len(composite_series.dropna()) > 5:
            valid = composite_series.dropna()
            wow_change = round(float(valid.iloc[-1] - valid.iloc[-6]), 2)

        return {
            'confidence': total_confidence,
            'wow_change': wow_change,
            'groups': group_details,
            'indicators': indicator_results,
            'composite_series': composite_series,
            'analyzed_at': datetime.now().isoformat(),
        }

    def _build_composite_series(
        self,
        confidence_series: Dict[str, pd.Series],
        display_days: int = 365,
    ) -> Optional[pd.Series]:
        """
        Build the composite confidence time series by aggregating
        all indicator confidence series day-by-day.
        """
        if not confidence_series:
            return None

        # Align all series to common index
        df = pd.DataFrame(confidence_series)

        # Group columns by their group
        group_cols = {}
        for name, config in INDICATOR_CONFIG.items():
            if name in df.columns:
                group = config['group']
                group_cols.setdefault(group, []).append(name)

        # Per-day: compute group means, then weighted total
        group_means = pd.DataFrame()
        for group_name, cols in group_cols.items():
            group_means[group_name] = df[cols].mean(axis=1)

        # Weighted sum with renormalization for missing groups
        def weighted_row(row):
            valid = {k: v for k, v in row.items() if pd.notna(v)}
            if not valid:
                return np.nan
            total_w = sum(GROUP_WEIGHTS[k] for k in valid)
            return sum(v * GROUP_WEIGHTS[k] / total_w for k, v in valid.items())

        composite = group_means.apply(weighted_row, axis=1)

        # Trim to display period
        cutoff = datetime.now() - timedelta(days=display_days)
        composite = composite[composite.index >= cutoff]

        return composite
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/analysis/test_global_usd_liquidity.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/indicators/global_usd_liquidity.py tests/analysis/test_global_usd_liquidity.py
git commit -m "feat: add FRED data fetching and full analyzer for USD liquidity confidence

GlobalUsdLiquidityAnalyzer fetches 7 indicators from 11 FRED series,
computes rolling 2-year percentile confidence, and aggregates into
3 groups (onshore 40%, offshore 30%, net liquidity 30%)."
```

---

### Task 3: Data Service Integration with Caching

**Files:**
- Modify: `web/data_service.py` — add `get_global_usd_liquidity()` function

- [ ] **Step 1: Write the data service function**

Add to the end of `web/data_service.py`:

```python
def get_global_usd_liquidity(
    display_days: int = 365,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    获取全球美元流动性置信度（带缓存）

    缓存策略：缓存完整分析结果（不含 series），12 小时过期。
    总是尝试获取最新数据，缓存作为 fallback。
    """
    from quant.analysis.indicators.global_usd_liquidity import (
        GlobalUsdLiquidityAnalyzer,
    )
    from quant.data.cache_manager import get_cache_manager

    cache = get_cache_manager()
    CACHE_PROVIDER = 'global_usd_liquidity'
    CACHE_API_TYPE = 'result'
    CACHE_SYMBOL = 'composite'
    CACHE_EXPIRY_HOURS = 12

    # Try to load cached result as fallback
    cached_result = None
    if not force_refresh:
        cached_result = cache.get(
            CACHE_PROVIDER, CACHE_API_TYPE, CACHE_SYMBOL,
            expiry_hours=CACHE_EXPIRY_HOURS,
        )

    # Always try fresh data (need series for charts)
    try:
        analyzer = GlobalUsdLiquidityAnalyzer()
        result = analyzer.analyze(display_days=display_days)

        # Cache non-series fields
        cache_data = {
            'confidence': result['confidence'],
            'wow_change': result['wow_change'],
            'groups': {
                k: {kk: vv for kk, vv in v.items() if kk != 'indicators'}
                for k, v in result['groups'].items()
            },
            'indicators': {
                k: {kk: vv for kk, vv in v.items() if kk != 'series'}
                for k, v in result['indicators'].items()
            },
            'analyzed_at': result['analyzed_at'],
        }
        cache.set(CACHE_PROVIDER, CACHE_API_TYPE, CACHE_SYMBOL, cache_data)

        return result
    except Exception as e:
        logger.error(f"全球美元流动性分析失败: {e}")
        if cached_result:
            cached_result['from_cache'] = True
            return cached_result
        return {'error': str(e)}
```

- [ ] **Step 2: Run a quick smoke test**

Run: `PYTHONPATH=. python -c "from web.data_service import get_global_usd_liquidity; print('import ok')"`
Expected: `import ok`

- [ ] **Step 3: Commit**

```bash
git add web/data_service.py
git commit -m "feat: add get_global_usd_liquidity() to data service with caching"
```

---

### Task 4: Streamlit Page — Confidence Chart

**Files:**
- Create: `web/pages/6_💧_USD_Liquidity.py`

- [ ] **Step 1: Create the page with header, KPI, and chart**

```python
# web/pages/6_💧_USD_Liquidity.py
"""
💧 全球美元流动性
Global USD Liquidity Confidence — 复刻吸引子 Alice 系统 [A0007]
"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

from web.data_service import get_global_usd_liquidity

def main():
    st.title("💧 全球美元流动性")
    st.caption("全球美元流动性置信度 — 基于百分位排名的方向性指标")

    # Controls
    col_range, col_refresh = st.columns([3, 1])
    with col_range:
        display_range = st.radio(
            "时间范围", ["3M", "6M", "1Y"],
            index=2, horizontal=True,
        )
    with col_refresh:
        force_refresh = st.button("🔄 刷新数据")

    display_days = {'3M': 90, '6M': 180, '1Y': 365}[display_range]

    # Fetch data
    with st.spinner("正在获取全球美元流动性数据..."):
        result = get_global_usd_liquidity(
            display_days=display_days,
            force_refresh=force_refresh,
        )

    if 'error' in result:
        st.error(f"数据获取失败: {result['error']}")
        return

    _render_header(result)
    _render_confidence_chart(result)
    _render_group_cards(result)
    _render_indicator_details(result)


def _render_header(result: dict):
    """Top KPI: confidence value + trend arrow + wow change."""
    confidence = result.get('confidence')
    wow_change = result.get('wow_change')

    if confidence is None:
        st.warning("置信度数据不可用")
        return

    # Trend arrow
    if wow_change is not None and wow_change > 2:
        arrow = "↑"
        trend = "宽松趋势"
    elif wow_change is not None and wow_change < -2:
        arrow = "↓"
        trend = "收紧趋势"
    else:
        arrow = "→"
        trend = "震荡"

    # Color
    if confidence > 0:
        color = "#1f77b4"  # blue
    else:
        color = "#d62728"  # red

    st.markdown(
        f'<div style="text-align:center; padding: 1rem;">'
        f'<span style="font-size: 3rem; font-weight: bold; color: {color};">'
        f'{confidence:+.2f}%</span>'
        f'<span style="font-size: 1.5rem; margin-left: 0.5rem;">{arrow} {trend}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if wow_change is not None:
        st.caption(f"较上周: {wow_change:+.2f}pp（对比 5 个交易日前）")

    if result.get('from_cache'):
        st.info("📦 使用缓存数据")


def _render_confidence_chart(result: dict):
    """Main area chart: confidence over time, positive blue, negative red."""
    composite = result.get('composite_series')
    if composite is None or composite.dropna().empty:
        st.info("置信度曲线数据不可用")
        return

    series = composite.dropna()

    fig = go.Figure()

    # Positive area (blue)
    positive = series.clip(lower=0)
    fig.add_trace(go.Scatter(
        x=series.index, y=positive,
        fill='tozeroy',
        fillcolor='rgba(31, 119, 180, 0.3)',
        line=dict(color='rgba(31, 119, 180, 0.8)', width=1),
        name='宽松',
        hovertemplate='%{x|%Y-%m-%d}<br>置信度: %{y:.1f}%<extra></extra>',
    ))

    # Negative area (red)
    negative = series.clip(upper=0)
    fig.add_trace(go.Scatter(
        x=series.index, y=negative,
        fill='tozeroy',
        fillcolor='rgba(214, 39, 40, 0.3)',
        line=dict(color='rgba(214, 39, 40, 0.8)', width=1),
        name='收紧',
        hovertemplate='%{x|%Y-%m-%d}<br>置信度: %{y:.1f}%<extra></extra>',
    ))

    # Zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        title="全球美元流动性 (置信度)",
        yaxis_title="置信度 (%)",
        yaxis_range=[-105, 105],
        xaxis_title="",
        height=400,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=50, r=20, t=60, b=40),
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_group_cards(result: dict):
    """Three metric cards for the three groups."""
    groups = result.get('groups', {})
    cols = st.columns(3)

    for col, (group_name, group_data) in zip(cols, groups.items()):
        with col:
            conf = group_data.get('confidence')
            weight = group_data.get('weight', 0)
            label = group_data.get('label', group_name)

            if conf is not None:
                delta_color = "normal" if conf > 0 else "inverse"
                st.metric(
                    label=f"{label} ({int(weight * 100)}%)",
                    value=f"{conf:+.1f}%",
                    delta=None,
                )
            else:
                st.metric(
                    label=f"{label} ({int(weight * 100)}%)",
                    value="N/A",
                )


def _render_indicator_details(result: dict):
    """Expandable table of all sub-indicators."""
    groups = result.get('groups', {})

    with st.expander("📊 子指标详情", expanded=False):
        for group_name, group_data in groups.items():
            st.subheader(group_data.get('label', group_name))

            indicators = group_data.get('indicators', {})
            if not indicators:
                st.caption("无数据")
                continue

            rows = []
            for ind_name, ind_data in indicators.items():
                if 'error' in ind_data:
                    rows.append({
                        '指标': ind_data.get('label', ind_name),
                        '当前值': '❌ ' + ind_data.get('error', ''),
                        '百分位': '',
                        '置信度': '',
                    })
                else:
                    rows.append({
                        '指标': ind_data.get('label', ind_name),
                        '当前值': f"{ind_data.get('current_value', 'N/A')}",
                        '百分位': f"{ind_data.get('percentile', 'N/A')}%",
                        '置信度': f"{ind_data.get('confidence', 'N/A'):+.1f}%"
                                  if isinstance(ind_data.get('confidence'), (int, float))
                                  else 'N/A',
                    })

            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )

        st.caption(f"分析时间: {result.get('analyzed_at', 'N/A')}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('web/pages/6_💧_USD_Liquidity.py', doraise=True); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add "web/pages/6_💧_USD_Liquidity.py"
git commit -m "feat: add Streamlit page for global USD liquidity confidence

Shows confidence KPI, dual-color area chart (blue=loose, red=tight),
group summary cards, and expandable sub-indicator details."
```

---

### Task 5: Integration Test and End-to-End Verification

**Files:**
- Modify: `tests/analysis/test_global_usd_liquidity.py` — add integration test

- [ ] **Step 1: Add integration test (requires FRED_API_KEY)**

```python
# Append to tests/analysis/test_global_usd_liquidity.py
import os


@pytest.mark.skipif(
    not os.environ.get('FRED_API_KEY'),
    reason="FRED_API_KEY not set"
)
class TestIntegration:
    """Integration tests — hit real FRED API"""

    def test_full_analyze(self):
        analyzer = GlobalUsdLiquidityAnalyzer()
        result = analyzer.analyze(lookback_days=1095, display_days=90)

        assert 'confidence' in result
        assert result['confidence'] is None or -100 <= result['confidence'] <= 100
        assert 'groups' in result
        assert 'composite_series' in result

        # At least some indicators should succeed
        successful = [
            v for v in result['indicators'].values()
            if 'confidence' in v
        ]
        assert len(successful) >= 3, f"Only {len(successful)} indicators succeeded"

    def test_individual_indicators(self):
        analyzer = GlobalUsdLiquidityAnalyzer()
        for name in INDICATOR_CONFIG:
            try:
                series = analyzer._fetch_indicator_series(name, lookback_days=400)
                assert len(series) > 50, f"{name}: only {len(series)} data points"
            except Exception as e:
                pytest.skip(f"{name} failed: {e}")
```

- [ ] **Step 2: Run integration tests**

Run: `PYTHONPATH=. pytest tests/analysis/test_global_usd_liquidity.py::TestIntegration -v`
Expected: All tests PASS (with FRED_API_KEY set).

- [ ] **Step 3: Run the Streamlit page manually**

Run: `scripts/run_web.sh restart`
Then visit http://localhost:8501 and navigate to "💧 全球美元流动性" page.
Verify: confidence number shows, chart renders, sub-indicator table displays.

- [ ] **Step 4: Commit**

```bash
git add tests/analysis/test_global_usd_liquidity.py
git commit -m "test: add integration tests for global USD liquidity analyzer"
```

---

## Summary

| Task | What it builds | Files |
|------|---------------|-------|
| 1 | Pure calculation: percentile → confidence, aggregation | `global_usd_liquidity.py`, `test_global_usd_liquidity.py` |
| 2 | FRED data fetching + full `analyze()` method | `global_usd_liquidity.py` |
| 3 | Data service caching integration | `data_service.py` |
| 4 | Streamlit page with chart + details | `6_💧_USD_Liquidity.py` |
| 5 | Integration tests + end-to-end verification | `test_global_usd_liquidity.py` |
