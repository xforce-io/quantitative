# Gold Anomaly Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "gold anomaly" dimension to `MacroLiquidityAnalyzer` with early-warning + confirmation dual-layer signals, and display it in the Signal Scanner UI.

**Architecture:** New `_fetch_gold_anomaly()` method in `MacroLiquidityAnalyzer`, following the same pattern as existing dimensions (`_fetch_net_liquidity`, `_fetch_sofr`, etc). Two-layer scoring: early warning (max 40 pts from consecutive decline, MA20 crossover, RSI) + confirmation (max 60 pts from weekly drop, gold-USD divergence, real yield spike). UI adds a 5th metric column and a 3rd chart row.

**Tech Stack:** Python, yfinance (Yahoo Finance), fredapi (FRED), pandas, Streamlit, Plotly

**Spec:** `docs/superpowers/specs/2026-03-19-gold-anomaly-detection-design.md`

---

## File Structure

| File | Role |
|------|------|
| `quant/analysis/indicators/macro_liquidity_analyzer.py` | Core analyzer — add `_fetch_gold_anomaly()`, update weights/thresholds/`analyze()` |
| `web/pages/4_🔍_Signal_Scanner.py` | UI — extend `_render_macro_liquidity_mode()` with gold metrics + charts |
| `tests/analysis/test_gold_anomaly.py` | Unit tests for the gold anomaly dimension (NEW) |

---

### Task 1: Update constants (weights + thresholds)

**Files:**
- Modify: `quant/analysis/indicators/macro_liquidity_analyzer.py:34-49`

- [ ] **Step 1: Write failing test for new weights**

Create file `tests/analysis/test_gold_anomaly.py`:

```python
"""Unit tests for gold anomaly detection dimension."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestGoldAnomalyConstants:
    """Verify weight and threshold constants."""

    def test_dimension_weights_sum_to_one(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import DIMENSION_WEIGHTS
        assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9

    def test_gold_dimension_weight_exists(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import DIMENSION_WEIGHTS
        assert 'gold' in DIMENSION_WEIGHTS
        assert DIMENSION_WEIGHTS['gold'] == 0.15

    def test_gold_thresholds_exist(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import THRESHOLDS
        assert 'gold_weekly_drop_pct' in THRESHOLDS
        assert 'gold_weekly_drop_severe_pct' in THRESHOLDS
        assert 'gold_consecutive_down_days' in THRESHOLDS
        assert 'gold_rsi_weak' in THRESHOLDS
        assert 'gold_usd_divergence_gold_drop' in THRESHOLDS
        assert 'gold_usd_divergence_usd_max' in THRESHOLDS
        assert 'real_yield_spike_bp' in THRESHOLDS
        assert 'real_yield_spike_moderate_bp' in THRESHOLDS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/analysis/test_gold_anomaly.py::TestGoldAnomalyConstants -v`
Expected: FAIL — `gold` not in `DIMENSION_WEIGHTS`

- [ ] **Step 3: Update constants in analyzer**

In `macro_liquidity_analyzer.py`, update `THRESHOLDS` (line 35) to add gold entries:

```python
THRESHOLDS = {
    'net_liquidity_drop_pct': 5.0,
    'sofr_high': 5.5,
    'move_high': 130,
    'yen_drop_weekly_pct': 3.0,
    'yield_spread_narrow': 1.0,
    # Gold anomaly thresholds
    'gold_weekly_drop_pct': 3.0,
    'gold_weekly_drop_severe_pct': 5.0,
    'gold_consecutive_down_days': 3,
    'gold_rsi_weak': 40,
    'gold_usd_divergence_gold_drop': 2.0,
    'gold_usd_divergence_usd_max': 0.5,
    'real_yield_spike_bp': 30,
    'real_yield_spike_moderate_bp': 15,
}
```

Update `DIMENSION_WEIGHTS` (line 44):

```python
DIMENSION_WEIGHTS = {
    'net_liquidity': 0.35,
    'sofr': 0.20,
    'move': 0.15,
    'yen_carry': 0.15,
    'gold': 0.15,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/analysis/test_gold_anomaly.py::TestGoldAnomalyConstants -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/indicators/macro_liquidity_analyzer.py tests/analysis/test_gold_anomaly.py
git commit -m "feat(gold): add gold anomaly thresholds and dimension weight"
```

---

### Task 2: Implement `_fetch_gold_anomaly()` — early warning layer

**Files:**
- Modify: `quant/analysis/indicators/macro_liquidity_analyzer.py`
- Test: `tests/analysis/test_gold_anomaly.py`

- [ ] **Step 1: Write failing tests for early warning scoring**

Append to `tests/analysis/test_gold_anomaly.py`:

```python
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


class TestEarlyWarningScoring:
    """Test the early warning layer scoring logic using synthetic data."""

    def _make_analyzer(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import MacroLiquidityAnalyzer
        return MacroLiquidityAnalyzer.__new__(MacroLiquidityAnalyzer)

    def _make_gold_series(self, prices: list) -> pd.Series:
        """Create a gold price series with DatetimeIndex."""
        dates = pd.bdate_range(end=datetime.now(), periods=len(prices))
        return pd.Series(prices, index=dates, name='Close')

    def test_consecutive_down_3_days(self):
        """3 consecutive down days should score +15."""
        analyzer = self._make_analyzer()
        # Last 25 prices: flat then 3 consecutive drops
        prices = [100.0] * 22 + [99.0, 98.0, 97.0]
        gold_close = self._make_gold_series(prices)
        result = analyzer._calc_early_warning(gold_close)
        assert result['consecutive_down'] is True
        assert result['score'] >= 15

    def test_no_consecutive_down(self):
        """Alternating up/down should not trigger consecutive down signal."""
        analyzer = self._make_analyzer()
        prices = [100.0] * 22 + [99.0, 100.0, 99.0]
        gold_close = self._make_gold_series(prices)
        result = analyzer._calc_early_warning(gold_close)
        assert result['consecutive_down'] is False

    def test_ma20_crossover(self):
        """Price crossing below MA20 for the first time should score +15."""
        analyzer = self._make_analyzer()
        # 20 days at 100, then 1 day still above (101), then drop below (95)
        prices = [100.0] * 20 + [101.0, 95.0]
        gold_close = self._make_gold_series(prices)
        result = analyzer._calc_early_warning(gold_close)
        assert result['below_ma20'] is True
        assert result['score'] >= 15

    def test_ma20_already_below_no_trigger(self):
        """Already below MA20 for multiple days should NOT trigger MA20 signal."""
        analyzer = self._make_analyzer()
        # Long decline — already well below MA20
        prices = list(np.linspace(100, 80, 25))
        gold_close = self._make_gold_series(prices)
        result = analyzer._calc_early_warning(gold_close)
        assert result['below_ma20'] is False

    def test_rsi_weak(self):
        """RSI below 40 should score +10."""
        analyzer = self._make_analyzer()
        # Sharp decline to push RSI below 40
        prices = [100.0] * 10 + [100 - i * 2 for i in range(15)]
        gold_close = self._make_gold_series(prices)
        result = analyzer._calc_early_warning(gold_close)
        assert result['rsi_weak'] is True
        assert result['rsi'] < 40

    def test_triple_resonance(self):
        """All 3 early warning signals should produce triple_resonance=True and score=40."""
        analyzer = self._make_analyzer()
        # Need: 3+ consecutive down, just crossed below MA20, RSI < 40
        # Build: 20 days flat at 100, then sharp 5-day drop
        prices = [100.0] * 20 + [96.0, 92.0, 88.0, 84.0, 80.0]
        gold_close = self._make_gold_series(prices)
        result = analyzer._calc_early_warning(gold_close)
        assert result['triple_resonance'] is True
        assert result['score'] == 40
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/analysis/test_gold_anomaly.py::TestEarlyWarningScoring -v`
Expected: FAIL — `_calc_early_warning` does not exist

- [ ] **Step 3: Implement `_calc_early_warning` and `_calc_rsi` helper**

Add to `MacroLiquidityAnalyzer` class in `macro_liquidity_analyzer.py`:

```python
@staticmethod
def _calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI using Wilder smoothing."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def _calc_early_warning(self, gold_close: pd.Series) -> dict:
    """
    Calculate early warning layer (max 40 points).

    Signals:
    - Consecutive down days >= 3: +15
    - First MA20 crossover (close drops below MA20): +15
    - RSI(14) < 40: +10
    """
    score = 0
    result = {
        'consecutive_down': False,
        'below_ma20': False,
        'rsi_weak': False,
        'triple_resonance': False,
        'consecutive_down_days': 0,
        'rsi': None,
        'score': 0,
    }

    if len(gold_close) < 22:
        return result

    # 1. Consecutive down days
    daily_ret = gold_close.pct_change()
    streak = 0
    for ret in reversed(daily_ret.dropna().values):
        if ret < 0:
            streak += 1
        else:
            break
    result['consecutive_down_days'] = streak
    if streak >= THRESHOLDS['gold_consecutive_down_days']:
        result['consecutive_down'] = True
        score += 15

    # 2. MA20 crossover (first-cross only)
    ma20 = gold_close.rolling(20).mean()
    if len(gold_close) >= 22 and not pd.isna(ma20.iloc[-1]) and not pd.isna(ma20.iloc[-2]):
        today_below = gold_close.iloc[-1] < ma20.iloc[-1]
        yesterday_above = gold_close.iloc[-2] >= ma20.iloc[-2]
        if today_below and yesterday_above:
            result['below_ma20'] = True
            score += 15

    # 3. RSI
    rsi = self._calc_rsi(gold_close)
    current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else None
    result['rsi'] = round(current_rsi, 1) if current_rsi is not None else None
    if current_rsi is not None and current_rsi < THRESHOLDS['gold_rsi_weak']:
        result['rsi_weak'] = True
        score += 10

    # Triple resonance
    if result['consecutive_down'] and result['below_ma20'] and result['rsi_weak']:
        result['triple_resonance'] = True

    result['score'] = min(score, 40)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/analysis/test_gold_anomaly.py::TestEarlyWarningScoring -v`
Expected: PASS (6 tests). Note: `test_triple_resonance` and `test_ma20_already_below_no_trigger` may need minor price array tuning if RSI/MA20 don't align perfectly with synthetic data — adjust prices if needed.

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/indicators/macro_liquidity_analyzer.py tests/analysis/test_gold_anomaly.py
git commit -m "feat(gold): implement early warning scoring layer"
```

---

### Task 3: Implement `_fetch_gold_anomaly()` — confirmation layer + full method

**Files:**
- Modify: `quant/analysis/indicators/macro_liquidity_analyzer.py`
- Test: `tests/analysis/test_gold_anomaly.py`

- [ ] **Step 1: Write failing tests for confirmation scoring**

Append to `tests/analysis/test_gold_anomaly.py`:

```python
class TestConfirmationScoring:
    """Test the confirmation layer scoring logic."""

    def _make_analyzer(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import MacroLiquidityAnalyzer
        return MacroLiquidityAnalyzer.__new__(MacroLiquidityAnalyzer)

    def test_weekly_drop_severe(self):
        """Weekly drop > 5% should score 40."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-6.0,
            usd_weekly_change_pct=1.0,
            real_yield_weekly_change_bp=5.0,
        )
        assert result['weekly_drop'] is True
        assert result['score'] >= 40

    def test_weekly_drop_moderate(self):
        """Weekly drop 3-5% should score 25."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-4.0,
            usd_weekly_change_pct=2.0,
            real_yield_weekly_change_bp=0.0,
        )
        assert result['weekly_drop'] is True
        assert result['score'] == 25

    def test_gold_usd_divergence(self):
        """Gold down >2% + USD not up should score +10."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-3.0,
            usd_weekly_change_pct=-0.5,
            real_yield_weekly_change_bp=0.0,
        )
        assert result['gold_usd_divergence'] is True
        assert result['score'] == 25 + 10  # weekly_drop(25) + divergence(10)

    def test_no_divergence_when_usd_strong(self):
        """Gold down but USD up strongly should NOT trigger divergence."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-3.0,
            usd_weekly_change_pct=1.5,
            real_yield_weekly_change_bp=0.0,
        )
        assert result['gold_usd_divergence'] is False

    def test_weekly_drop_mild(self):
        """Weekly drop 1-3% should score 10 (no weekly_drop flag)."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-1.5,
            usd_weekly_change_pct=0.0,
            real_yield_weekly_change_bp=0.0,
        )
        assert result['weekly_drop'] is False
        assert result['score'] == 10

    def test_real_yield_spike(self):
        """Real yield spike > 30bp should score +10."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-1.0,
            usd_weekly_change_pct=0.0,
            real_yield_weekly_change_bp=35.0,
        )
        assert result['real_rate_spike'] is True
        assert result['score'] >= 10

    def test_real_yield_spike_moderate(self):
        """Real yield spike 15-30bp should score +5."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=0.5,
            usd_weekly_change_pct=0.0,
            real_yield_weekly_change_bp=20.0,
        )
        assert result['real_rate_spike'] is True
        assert result['score'] == 5

    def test_risk_score_capped_at_60(self):
        """Confirmation score should be capped at 60."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-6.0,       # 40 pts
            usd_weekly_change_pct=-1.0,         # +10 pts (divergence)
            real_yield_weekly_change_bp=35.0,    # +10 pts
        )
        assert result['score'] == 60  # capped

    def test_no_signals(self):
        """No trigger conditions should score 0."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=0.5,
            usd_weekly_change_pct=0.0,
            real_yield_weekly_change_bp=0.0,
        )
        assert result['score'] == 0

    def test_confirmation_with_none_usd(self):
        """Missing USD data should skip divergence signal."""
        analyzer = self._make_analyzer()
        result = analyzer._calc_confirmation(
            gold_weekly_change_pct=-4.0,
            usd_weekly_change_pct=None,
            real_yield_weekly_change_bp=None,
        )
        assert result['gold_usd_divergence'] is False
        assert result['real_rate_spike'] is False
        assert result['score'] == 25  # only weekly_drop
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/analysis/test_gold_anomaly.py::TestConfirmationScoring -v`
Expected: FAIL — `_calc_confirmation` does not exist

- [ ] **Step 3: Implement `_calc_confirmation`**

Add to `MacroLiquidityAnalyzer` class:

```python
def _calc_confirmation(
    self,
    gold_weekly_change_pct: float,
    usd_weekly_change_pct: float | None,
    real_yield_weekly_change_bp: float | None,
) -> dict:
    """
    Calculate confirmation layer (max 60 points).

    Signals:
    - Weekly gold drop: >5% → 40, >3% → 25, >1% → 10
    - Gold-USD divergence: gold down >2% + USD <+0.5% → +10
    - Real yield spike: >30bp → +10, >15bp → +5
    """
    score = 0
    result = {
        'weekly_drop': False,
        'gold_usd_divergence': False,
        'real_rate_spike': False,
        'score': 0,
    }

    # 1. Weekly gold drop
    if gold_weekly_change_pct < -THRESHOLDS['gold_weekly_drop_severe_pct']:
        result['weekly_drop'] = True
        score += 40
    elif gold_weekly_change_pct < -THRESHOLDS['gold_weekly_drop_pct']:
        result['weekly_drop'] = True
        score += 25
    elif gold_weekly_change_pct < -1.0:
        score += 10

    # 2. Gold-USD divergence
    if (
        usd_weekly_change_pct is not None
        and gold_weekly_change_pct < -THRESHOLDS['gold_usd_divergence_gold_drop']
        and usd_weekly_change_pct < THRESHOLDS['gold_usd_divergence_usd_max']
    ):
        result['gold_usd_divergence'] = True
        score += 10

    # 3. Real yield spike
    if real_yield_weekly_change_bp is not None:
        if real_yield_weekly_change_bp > THRESHOLDS['real_yield_spike_bp']:
            result['real_rate_spike'] = True
            score += 10
        elif real_yield_weekly_change_bp > THRESHOLDS['real_yield_spike_moderate_bp']:
            result['real_rate_spike'] = True
            score += 5

    result['score'] = min(score, 60)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/analysis/test_gold_anomaly.py::TestConfirmationScoring -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/indicators/macro_liquidity_analyzer.py tests/analysis/test_gold_anomaly.py
git commit -m "feat(gold): implement confirmation scoring layer"
```

---

### Task 4: Implement full `_fetch_gold_anomaly()` and integrate into `analyze()`

**Files:**
- Modify: `quant/analysis/indicators/macro_liquidity_analyzer.py`
- Test: `tests/analysis/test_gold_anomaly.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/analysis/test_gold_anomaly.py`:

```python
from unittest.mock import patch, MagicMock


class TestFetchGoldAnomaly:
    """Test the full _fetch_gold_anomaly method with mocked data."""

    def _make_analyzer(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import MacroLiquidityAnalyzer
        return MacroLiquidityAnalyzer()

    def _make_mock_gold_df(self, prices: list) -> pd.DataFrame:
        """Create a mock yfinance DataFrame."""
        dates = pd.bdate_range(end=datetime.now(), periods=len(prices))
        return pd.DataFrame({
            'Close': prices,
            'High': [p * 1.01 for p in prices],
            'Low': [p * 0.99 for p in prices],
        }, index=dates)

    def _make_mock_usd_df(self, prices: list) -> pd.DataFrame:
        dates = pd.bdate_range(end=datetime.now(), periods=len(prices))
        return pd.DataFrame({'Close': prices}, index=dates)

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_fetch_returns_expected_structure(self, mock_yf):
        """_fetch_gold_anomaly should return dict with required keys."""
        gold_prices = [100.0] * 20 + [99, 98, 97, 96, 95]
        usd_prices = [100.0] * 25

        def download_side_effect(ticker, **kwargs):
            if ticker == 'GC=F':
                return self._make_mock_gold_df(gold_prices)
            elif ticker == 'DX-Y.NYB':
                return self._make_mock_usd_df(usd_prices)
            return pd.DataFrame()

        mock_yf.download.side_effect = download_side_effect

        analyzer = self._make_analyzer()
        analyzer._fred_api_key = 'fake'  # avoid FRED call
        with patch.object(analyzer, '_get_fred') as mock_fred:
            mock_series = pd.Series([1.8, 1.82, 1.85, 1.83, 1.80],
                                     index=pd.bdate_range(end=datetime.now(), periods=5))
            mock_fred.return_value.get_series.return_value = mock_series
            result = analyzer._fetch_gold_anomaly(90)

        assert 'current_price' in result
        assert 'weekly_change_pct' in result
        assert 'early_warning' in result
        assert 'confirmation' in result
        assert 'risk_score' in result
        assert 'signals' in result
        assert 'series' in result
        assert isinstance(result['signals'], list)
        assert 0 <= result['risk_score'] <= 100

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_fetch_handles_gold_data_failure(self, mock_yf):
        """When GC=F returns empty, should return error with risk_score 50."""
        mock_yf.download.return_value = pd.DataFrame()

        analyzer = self._make_analyzer()
        result = analyzer._fetch_gold_anomaly(90)

        assert 'error' in result
        assert result['risk_score'] == 50

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_fetch_stale_data_warning(self, mock_yf):
        """When latest gold data is > 3 days old, should add staleness warning."""
        # Create data ending 5 business days ago
        old_end = datetime.now() - timedelta(days=7)
        prices = [100.0] * 25
        dates = pd.bdate_range(end=old_end, periods=25)
        gold_df = pd.DataFrame({
            'Close': prices,
            'High': [p * 1.01 for p in prices],
            'Low': [p * 0.99 for p in prices],
        }, index=dates)

        mock_yf.download.return_value = gold_df

        analyzer = self._make_analyzer()
        result = analyzer._fetch_gold_anomaly(90)

        assert any('数据延迟' in s or '延迟' in s for s in result.get('signals', []))

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_fetch_usd_failure_skips_divergence(self, mock_yf):
        """When DX-Y.NYB fails but GC=F succeeds, divergence should be skipped."""
        gold_prices = [100.0] * 20 + [99, 98, 97, 96, 95]

        def download_side_effect(ticker, **kwargs):
            if ticker == 'GC=F':
                dates = pd.bdate_range(end=datetime.now(), periods=len(gold_prices))
                return pd.DataFrame({
                    'Close': gold_prices,
                    'High': [p * 1.01 for p in gold_prices],
                    'Low': [p * 0.99 for p in gold_prices],
                }, index=dates)
            return pd.DataFrame()  # USD fails

        mock_yf.download.side_effect = download_side_effect

        analyzer = self._make_analyzer()
        with patch.object(analyzer, '_get_fred', side_effect=Exception("no FRED")):
            result = analyzer._fetch_gold_anomaly(90)

        assert result['confirmation']['gold_usd_divergence'] is False
        assert 'error' not in result  # should succeed despite USD/FRED failure
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/analysis/test_gold_anomaly.py::TestFetchGoldAnomaly -v`
Expected: FAIL — `_fetch_gold_anomaly` does not exist

- [ ] **Step 3: Implement `_fetch_gold_anomaly`**

Add `import yfinance as yf` at the top of the method (lazy import pattern, same as `_fetch_move_index`). Add to `MacroLiquidityAnalyzer` class:

```python
def _fetch_gold_anomaly(self, lookback_days: int = 365) -> Dict[str, Any]:
    """
    Fetch gold anomaly data and calculate dual-layer risk score.

    Data sources:
    - GC=F (COMEX gold futures) via Yahoo Finance
    - DX-Y.NYB (USD index) via Yahoo Finance
    - DFII10 (10Y TIPS real yield) via FRED
    """
    import yfinance as yf

    end = datetime.now()
    start = end - timedelta(days=lookback_days + 60)  # extra buffer for MA20

    # === Gold price (required) ===
    gold = yf.download('GC=F', start=start, end=end, progress=False)
    if gold is None or gold.empty:
        return {'error': '黄金数据为空', 'risk_score': 50}

    if isinstance(gold.columns, pd.MultiIndex):
        gold.columns = gold.columns.get_level_values(0)

    close_col = 'Close' if 'Close' in gold.columns else 'close'
    if close_col not in gold.columns:
        return {'error': '黄金数据缺少 Close 列', 'risk_score': 50}

    gold_close = gold[close_col].dropna()
    if len(gold_close) < 25:
        return {'error': '黄金数据不足', 'risk_score': 50}

    current_price = float(gold_close.iloc[-1])
    ma20 = gold_close.rolling(20).mean()
    current_ma20 = float(ma20.iloc[-1]) if not pd.isna(ma20.iloc[-1]) else None

    # Weekly change (5 trading days)
    gold_weekly_change_pct = (
        (gold_close.iloc[-1] - gold_close.iloc[-5]) / gold_close.iloc[-5] * 100
        if len(gold_close) >= 5 else 0
    )

    # === USD index (optional) ===
    usd_weekly_change_pct = None
    usd_current = None
    try:
        usd = yf.download('DX-Y.NYB', start=start, end=end, progress=False)
        if usd is not None and not usd.empty:
            if isinstance(usd.columns, pd.MultiIndex):
                usd.columns = usd.columns.get_level_values(0)
            usd_col = 'Close' if 'Close' in usd.columns else 'close'
            if usd_col in usd.columns:
                usd_close = usd[usd_col].dropna()
                if len(usd_close) >= 5:
                    usd_current = float(usd_close.iloc[-1])
                    usd_weekly_change_pct = (
                        (usd_close.iloc[-1] - usd_close.iloc[-5]) / usd_close.iloc[-5] * 100
                    )
    except Exception as e:
        logger.warning(f"获取美元指数失败: {e}")

    # === Real yield (optional) ===
    real_yield = None
    real_yield_weekly_change_bp = None
    try:
        fred = self._get_fred()
        tips = fred.get_series('DFII10', observation_start=start)
        if tips is not None and not tips.empty:
            tips = tips.dropna()
            if len(tips) >= 5:
                real_yield = float(tips.iloc[-1])
                real_yield_weekly_change_bp = (tips.iloc[-1] - tips.iloc[-5]) * 100
    except Exception as e:
        logger.warning(f"获取 TIPS 实际利率失败: {e}")

    # === Scoring ===
    early_warning = self._calc_early_warning(gold_close)
    confirmation = self._calc_confirmation(
        gold_weekly_change_pct=gold_weekly_change_pct,
        usd_weekly_change_pct=usd_weekly_change_pct,
        real_yield_weekly_change_bp=real_yield_weekly_change_bp,
    )
    risk_score = min(early_warning['score'] + confirmation['score'], 100)

    # === Signal messages ===
    signals = []

    # Early warning signals
    if early_warning['triple_resonance']:
        signals.append(
            f'🔴 黄金三重前兆共振：连跌{early_warning["consecutive_down_days"]}天'
            f'+破MA20+RSI弱势({early_warning["rsi"]})，高度警惕'
        )
    else:
        if early_warning['consecutive_down']:
            cum_ret = (gold_close.iloc[-1] / gold_close.iloc[-early_warning['consecutive_down_days']] - 1) * 100
            signals.append(
                f'🟠 黄金连跌{early_warning["consecutive_down_days"]}天'
                f' (累计{cum_ret:.1f}%)，趋势转弱'
            )
        if early_warning['below_ma20']:
            signals.append(
                f'🟠 黄金跌破20日均线 ({current_price:.0f} < MA20 {current_ma20:.0f})'
            )
        if early_warning['rsi_weak']:
            signals.append(f'🟠 黄金RSI跌入弱势区间 ({early_warning["rsi"]})')

    # Confirmation signals
    if confirmation['weekly_drop']:
        if gold_weekly_change_pct < -THRESHOLDS['gold_weekly_drop_severe_pct']:
            signals.append(f'🔴 黄金周暴跌 {gold_weekly_change_pct:.1f}%（阈值 -{THRESHOLDS["gold_weekly_drop_pct"]}%）')
        else:
            signals.append(f'🟠 黄金周跌 {gold_weekly_change_pct:.1f}%')

    if confirmation['gold_usd_divergence']:
        signals.append('🔴 黄金-美元背离：金跌但美元未涨，非美元驱动的抛售')

    if confirmation['real_rate_spike']:
        signals.append(f'🟠 实际利率周升{real_yield_weekly_change_bp:.0f}bp，压制黄金')

    # Data staleness check
    latest_date = gold_close.index[-1]
    days_stale = (datetime.now() - latest_date.to_pydatetime().replace(tzinfo=None)).days
    if days_stale > 3:
        signals.append(f'⚠️ 黄金数据延迟 {days_stale} 天（最新: {latest_date.strftime("%m-%d")}）')

    if not signals:
        signals.append(f'🟢 黄金走势平稳 (${current_price:.0f}, 周变化{gold_weekly_change_pct:+.1f}%)')

    # === Time series for charts ===
    cutoff = end - timedelta(days=lookback_days)
    gold_df = gold_close[gold_close.index >= cutoff].to_frame(name='gold_price')
    gold_df['gold_ma20'] = ma20[ma20.index >= cutoff]

    series = gold_df
    if usd_current is not None:
        try:
            usd_series = usd[usd_col][usd[usd_col].index >= cutoff].to_frame(name='usd_index')
            series = gold_df.join(usd_series, how='outer').ffill()
        except Exception:
            pass

    return {
        'current_price': round(current_price, 2),
        'weekly_change_pct': round(gold_weekly_change_pct, 2),
        'consecutive_down_days': early_warning['consecutive_down_days'],
        'ma20': round(current_ma20, 2) if current_ma20 else None,
        'rsi': early_warning['rsi'],
        'usd_index': round(usd_current, 2) if usd_current else None,
        'usd_weekly_change_pct': round(usd_weekly_change_pct, 2) if usd_weekly_change_pct is not None else None,
        'real_yield': round(real_yield, 2) if real_yield is not None else None,
        'real_yield_weekly_change': round(real_yield_weekly_change_bp, 1) if real_yield_weekly_change_bp is not None else None,
        'early_warning': early_warning,
        'confirmation': confirmation,
        'risk_score': risk_score,
        'signals': signals,
        'series': series,
    }
```

- [ ] **Step 4: Integrate into `analyze()` method**

In the `analyze()` method (after the yen_carry block, around line 150), add:

```python
        # 5. 黄金异动
        try:
            gold_result = self._fetch_gold_anomaly(lookback_days)
            dimensions['gold'] = gold_result
            dimension_scores['gold'] = gold_result.get('risk_score', 50)
            signals.extend(gold_result.get('signals', []))
        except Exception as e:
            logger.error(f"获取黄金异动数据失败: {e}")
            dimensions['gold'] = {'error': str(e)}
            dimension_scores['gold'] = 50
```

Also update the module docstring (lines 5-17) to mention the gold dimension: add a row to the table:

```
| 黄金异动 | Yahoo: GC=F + DX-Y.NYB, FRED: DFII10 | 连跌3天/破MA20/RSI弱势/周跌>3% | 15%  |
```

And change "四维度监控" to "五维度监控".

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/python -m pytest tests/analysis/test_gold_anomaly.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add quant/analysis/indicators/macro_liquidity_analyzer.py tests/analysis/test_gold_anomaly.py
git commit -m "feat(gold): implement _fetch_gold_anomaly and integrate into analyze()"
```

---

### Task 5: Update Signal Scanner UI

**Files:**
- Modify: `web/pages/4_🔍_Signal_Scanner.py:792-962`

- [ ] **Step 1: Update page subtitle and dimension weight labels**

In `_render_macro_liquidity_mode()`, change line 806:

```python
# Old:
st.caption("宏观流动性模式 — 监控净流动性、SOFR、MOVE指数、日元套利交易")
# New:
st.caption("宏观流动性模式 — 监控净流动性、SOFR、MOVE指数、日元套利交易、黄金异动")
```

Also update the hardcoded weight percentages in dimension headers to match new weights:
- Line ~886: `"#### 净流动性 (40%)"` → `"#### 净流动性 (35%)"`
- Line ~905: `"#### SOFR (25%)"` → `"#### SOFR (20%)"`
- Line ~920: `"#### MOVE指数 (20%)"` → `"#### MOVE指数 (15%)"`
- Line ~933: `"#### 日元套利 (15%)"` stays the same

- [ ] **Step 2: Add gold metric to top row**

Change the metrics section (around line 869). Replace `sc1, sc2, sc3, sc4 = st.columns(4)` with 5 columns:

```python
        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
```

After `sc4.metric(...)` (line 878), add:

```python
        gold = dimensions.get('gold', {})
        sc5.metric("黄金",
                   f"${gold.get('current_price', 0):.0f}" if 'current_price' in gold else "N/A",
                   delta=f"{gold.get('weekly_change_pct', 0):+.1f}% 周变化" if 'weekly_change_pct' in gold else None,
                   delta_color="normal")
```

- [ ] **Step 3: Add gold charts (Row 3)**

After the `row2_col1, row2_col2` block (after line ~947), add:

```python
        # Row 3: Gold
        row3_col1, row3_col2 = st.columns(2)

        with row3_col1:
            st.markdown(f"#### 黄金异动 (15%) — 风险 {dim_scores.get('gold', 0):.0f}")
            gold_series = gold.get('series')
            if isinstance(gold_series, pd.DataFrame) and not gold_series.empty and 'gold_price' in gold_series.columns:
                # Gold price with MA20
                fig_gold = go.Figure()
                gp = gold_series['gold_price'].dropna()
                fig_gold.add_trace(go.Scatter(
                    x=gp.index, y=gp.values,
                    mode='lines', name='黄金期货',
                    line=dict(color='#f1c40f', width=2),
                ))
                if 'gold_ma20' in gold_series.columns:
                    gma = gold_series['gold_ma20'].dropna()
                    fig_gold.add_trace(go.Scatter(
                        x=gma.index, y=gma.values,
                        mode='lines', name='MA20',
                        line=dict(color='#e74c3c', width=1.5, dash='dash'),
                    ))
                fig_gold.update_layout(
                    title='黄金期货价格 + MA20', height=300,
                    margin=dict(l=10, r=10, t=40, b=10),
                    yaxis_title='USD', showlegend=True, hovermode='x unified',
                    legend=dict(x=0, y=1.15, orientation='h'),
                )
                st.plotly_chart(fig_gold, use_container_width=True, key="macro_gold_price")

                # Early warning / confirmation details
                ew = gold.get('early_warning', {})
                cf = gold.get('confirmation', {})
                e1, e2 = st.columns(2)
                e1.metric("前兆分", f"{ew.get('score', 0)}/40")
                e2.metric("确认分", f"{cf.get('score', 0)}/60")
            else:
                st.info(f"黄金数据不可用{': ' + gold['error'] if 'error' in gold else ''}")

        with row3_col2:
            st.markdown("#### 金价-美元对比")
            gold_series = gold.get('series')
            if isinstance(gold_series, pd.DataFrame) and not gold_series.empty:
                has_gold = 'gold_price' in gold_series.columns
                has_usd = 'usd_index' in gold_series.columns
                if has_gold and has_usd:
                    _render_dual_axis_chart(
                        gold_series, col1='gold_price', col2='usd_index',
                        label1='黄金期货(USD)', label2='美元指数',
                        title='黄金 vs 美元指数',
                        color1='#f1c40f', color2='#3498db', key='gold_usd',
                    )
                elif has_gold:
                    _render_trend_chart(
                        gold_series, 'gold_price', '黄金期货价格',
                        y_title='USD', color='#f1c40f', key='gold_only',
                    )
                else:
                    st.info("黄金/美元数据不可用")
            else:
                st.info("黄金图表数据不可用")
```

- [ ] **Step 4: Update AI Context injection**

In the `registry.register_data` call for `liquidity_status` (around line 950), add the gold dimension to the summary extractor. Add this line inside the lambda:

```python
                "gold": {k: v for k, v in data.get('dimensions', {}).get('gold', {}).items() if k != 'series'},
```

- [ ] **Step 5: Run existing E2E test to verify no crash**

Run: `.venv/bin/python -m pytest tests/web/test_signal_scanner.py::TestScannerModeSwitching -v`
Expected: PASS (mode cycling doesn't crash)

- [ ] **Step 6: Commit**

```bash
git add "web/pages/4_🔍_Signal_Scanner.py"
git commit -m "feat(gold): add gold anomaly UI to macro liquidity mode"
```

---

### Task 6: Manual smoke test

- [ ] **Step 1: Run the web app locally**

```bash
.venv/bin/python -m streamlit run web/Home.py
```

- [ ] **Step 2: Verify gold dimension in Signal Scanner**

Navigate to Signal Scanner → 宏观流动性 mode. Verify:
- 5 metric columns at top (including 黄金)
- Gold price + MA20 chart in Row 3
- Gold-USD dual axis chart
- Signal messages include gold warnings if applicable
- No Streamlit errors

- [ ] **Step 3: Run full test suite**

```bash
.venv/bin/python -m pytest tests/analysis/test_gold_anomaly.py -v
```

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -u
git commit -m "fix(gold): address smoke test issues"
```
