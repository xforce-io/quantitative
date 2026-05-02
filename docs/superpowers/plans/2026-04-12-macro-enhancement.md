# Macro Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add yield curve, copper/gold ratio, and crude oil dimensions to the macro monitoring system.

**Architecture:** Two new dimensions (`_fetch_copper_gold_ratio`, `_fetch_crude_oil`) added to `MacroLiquidityAnalyzer` (6→8 dimensions with rebalanced weights). One new method (`analyze_yield_curve`) added to `LeadingIndicatorsAnalyzer`. Dashboard "Leading Signals" row expanded from 3 to 4 columns. Leading indicators cache TTL increased from 1h to 4h.

**Tech Stack:** Yahoo Finance (`yfinance`), FRED API (`fredapi`), pandas, Streamlit

**Spec:** `docs/superpowers/specs/2026-04-12-macro-enhancement-design.md`

---

### Task 1: Copper/Gold Ratio Dimension

**Files:**
- Modify: `quant/analysis/indicators/macro_liquidity_analyzer.py` — add `_fetch_copper_gold_ratio()`, update `THRESHOLDS`, `DIMENSION_WEIGHTS`
- Modify: `tests/analysis/test_gold_anomaly.py` — update weight assertions, add copper/gold tests

- [ ] **Step 1: Update existing test for new weights**

In `tests/analysis/test_gold_anomaly.py`, update `TestGoldAnomalyConstants`:

```python
class TestGoldAnomalyConstants:
    def test_dimension_weights_sum_to_one(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import DIMENSION_WEIGHTS
        assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9

    def test_gold_dimension_weight_exists(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import DIMENSION_WEIGHTS
        assert 'gold' in DIMENSION_WEIGHTS
        assert DIMENSION_WEIGHTS['gold'] == 0.08  # was 0.15, now 0.08

    def test_copper_gold_dimension_weight_exists(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import DIMENSION_WEIGHTS
        assert 'copper_gold' in DIMENSION_WEIGHTS
        assert DIMENSION_WEIGHTS['copper_gold'] == 0.10

    def test_crude_oil_dimension_weight_exists(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import DIMENSION_WEIGHTS
        assert 'crude_oil' in DIMENSION_WEIGHTS
        assert DIMENSION_WEIGHTS['crude_oil'] == 0.10

    def test_copper_gold_thresholds_exist(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import THRESHOLDS
        assert 'copper_gold_percentile_extreme' in THRESHOLDS
        assert 'copper_gold_percentile_high' in THRESHOLDS
        assert 'copper_gold_percentile_elevated' in THRESHOLDS
        assert 'copper_gold_weekly_drop_pct' in THRESHOLDS

    def test_crude_thresholds_exist(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import THRESHOLDS
        assert 'crude_weekly_surge_pct' in THRESHOLDS
        assert 'crude_weekly_rise_pct' in THRESHOLDS
        assert 'crude_weekly_crash_pct' in THRESHOLDS
        assert 'crude_high_price' in THRESHOLDS
        assert 'crude_elevated_price' in THRESHOLDS
```

- [ ] **Step 2: Write copper/gold ratio tests**

Add to `tests/analysis/test_gold_anomaly.py`:

```python
class TestCopperGoldRatio:
    """Test _fetch_copper_gold_ratio with mocked Yahoo data."""

    def _make_analyzer(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import MacroLiquidityAnalyzer
        return MacroLiquidityAnalyzer()

    def _make_mock_df(self, prices: list) -> pd.DataFrame:
        dates = pd.bdate_range(end=datetime.now(), periods=len(prices))
        return pd.DataFrame({'Close': prices}, index=dates)

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_returns_expected_structure(self, mock_yf):
        copper_prices = [4.0 + i * 0.01 for i in range(65)]
        gold_prices = [2000.0] * 65

        def download_side_effect(ticker, **kwargs):
            if ticker == 'HG=F':
                return self._make_mock_df(copper_prices)
            elif ticker == 'GC=F':
                return self._make_mock_df(gold_prices)
            return pd.DataFrame()

        mock_yf.download.side_effect = download_side_effect

        analyzer = self._make_analyzer()
        result = analyzer._fetch_copper_gold_ratio(90)

        assert 'ratio' in result
        assert 'percentile' in result
        assert 'risk_score' in result
        assert 'signals' in result
        assert 'series' in result
        assert isinstance(result['signals'], list)
        assert 0 <= result['risk_score'] <= 100

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_low_percentile_high_risk(self, mock_yf):
        """Declining copper/gold ratio should produce high risk score."""
        # Copper declining sharply, gold stable = ratio dropping = risk-off
        copper_prices = [4.5] * 55 + [4.0, 3.8, 3.6, 3.4, 3.2, 3.0, 2.8, 2.6, 2.4, 2.2]
        gold_prices = [2000.0] * 65

        def download_side_effect(ticker, **kwargs):
            if ticker == 'HG=F':
                return self._make_mock_df(copper_prices)
            elif ticker == 'GC=F':
                return self._make_mock_df(gold_prices)
            return pd.DataFrame()

        mock_yf.download.side_effect = download_side_effect

        analyzer = self._make_analyzer()
        result = analyzer._fetch_copper_gold_ratio(90)

        assert result['risk_score'] >= 70  # low percentile = high risk

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_empty_data_returns_error(self, mock_yf):
        mock_yf.download.return_value = pd.DataFrame()

        analyzer = self._make_analyzer()
        result = analyzer._fetch_copper_gold_ratio(90)

        assert 'error' in result
        assert result['risk_score'] == 50
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/analysis/test_gold_anomaly.py -v`
Expected: FAIL — `_fetch_copper_gold_ratio` not defined, weight assertions fail

- [ ] **Step 4: Update constants in macro_liquidity_analyzer.py**

In `quant/analysis/indicators/macro_liquidity_analyzer.py`, update `THRESHOLDS` and `DIMENSION_WEIGHTS`:

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
    # Copper/Gold ratio thresholds
    'copper_gold_percentile_extreme': 10,
    'copper_gold_percentile_high': 20,
    'copper_gold_percentile_elevated': 40,
    'copper_gold_weekly_drop_pct': 5.0,
    # Crude oil thresholds
    'crude_weekly_surge_pct': 10.0,
    'crude_weekly_rise_pct': 5.0,
    'crude_weekly_crash_pct': 10.0,
    'crude_high_price': 100,
    'crude_elevated_price': 90,
}

DIMENSION_WEIGHTS = {
    'net_liquidity': 0.25,
    'sofr': 0.12,
    'move': 0.12,
    'yen_carry': 0.08,
    'gold': 0.08,
    'liquidity_trend': 0.15,
    'copper_gold': 0.10,
    'crude_oil': 0.10,
}
```

- [ ] **Step 5: Implement `_fetch_copper_gold_ratio`**

Add to `MacroLiquidityAnalyzer` class in `quant/analysis/indicators/macro_liquidity_analyzer.py`:

```python
def _fetch_copper_gold_ratio(self, lookback_days: int = 365) -> Dict[str, Any]:
    """
    铜金比 — 经济体温计

    铜 = 工业需求 = 经济扩张，金 = 避险需求 = 风险规避。
    比值下行 = risk-off，用 60 日滚动百分位评估。
    """
    end = datetime.now()
    start = end - timedelta(days=lookback_days + 90)  # extra days for percentile window

    copper = yf.download('HG=F', start=start, end=end, progress=False)
    gold = yf.download('GC=F', start=start, end=end, progress=False)

    if copper is None or copper.empty or gold is None or gold.empty:
        return {'error': '铜或黄金数据为空', 'risk_score': 50}

    # Handle MultiIndex columns
    for df in [copper, gold]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    close_col = 'Close' if 'Close' in copper.columns else 'close'

    # Align dates
    ratio_df = pd.DataFrame({
        'copper': copper[close_col],
        'gold': gold[close_col],
    }).dropna()

    if len(ratio_df) < 60:
        return {'error': '铜金比数据不足（需要至少60天）', 'risk_score': 50}

    ratio_df['ratio'] = ratio_df['copper'] / ratio_df['gold']

    # Rolling 60-day percentile
    ratio_series = ratio_df['ratio']
    rolling_rank = ratio_series.rolling(60).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False
    )
    ratio_df['percentile'] = rolling_rank

    current_ratio = float(ratio_series.iloc[-1])
    current_percentile = float(ratio_df['percentile'].iloc[-1])

    # Weekly change
    if len(ratio_series) >= 5:
        week_ago = float(ratio_series.iloc[-5])
        weekly_change_pct = (current_ratio - week_ago) / abs(week_ago) * 100 if week_ago != 0 else 0
    else:
        weekly_change_pct = 0

    # Risk scoring based on percentile
    risk_score = 0
    signals = []

    if current_percentile < THRESHOLDS['copper_gold_percentile_extreme']:
        risk_score = 90
        signals.append(f'🔴 铜金比极端低位（百分位 {current_percentile:.0f}%），强烈 risk-off')
    elif current_percentile < THRESHOLDS['copper_gold_percentile_high']:
        risk_score = 70
        signals.append(f'🟠 铜金比低位（百分位 {current_percentile:.0f}%），risk-off 信号')
    elif current_percentile < THRESHOLDS['copper_gold_percentile_elevated']:
        risk_score = 45
    else:
        risk_score = 15

    if weekly_change_pct < -THRESHOLDS['copper_gold_weekly_drop_pct']:
        risk_score = min(risk_score + 15, 100)
        signals.append(f'🟠 铜金比周跌 {weekly_change_pct:.1f}%，经济预期转弱')

    if not signals:
        signals.append(f'🟢 铜金比正常（百分位 {current_percentile:.0f}%）')

    cutoff = end - timedelta(days=lookback_days)
    series = ratio_df[ratio_df.index >= cutoff][['ratio']].copy()

    return {
        'ratio': round(current_ratio, 6),
        'percentile': round(current_percentile, 1),
        'weekly_change_pct': round(weekly_change_pct, 2),
        'risk_score': risk_score,
        'signals': signals,
        'series': series,
    }
```

- [ ] **Step 6: Wire into `analyze()` method**

In `MacroLiquidityAnalyzer.analyze()`, add after the gold dimension block (after dimension 5):

```python
# 7. 铜金比
try:
    cg_result = self._fetch_copper_gold_ratio(lookback_days)
    dimensions['copper_gold'] = cg_result
    dimension_scores['copper_gold'] = cg_result.get('risk_score', 50)
    signals.extend(cg_result.get('signals', []))
except Exception as e:
    logger.error(f"获取铜金比数据失败: {e}")
    dimensions['copper_gold'] = {'error': str(e)}
    dimension_scores['copper_gold'] = 50
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/analysis/test_gold_anomaly.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add quant/analysis/indicators/macro_liquidity_analyzer.py tests/analysis/test_gold_anomaly.py
git commit -m "feat(macro): add copper/gold ratio dimension to liquidity analyzer"
```

---

### Task 2: Crude Oil Dimension

**Files:**
- Modify: `quant/analysis/indicators/macro_liquidity_analyzer.py` — add `_fetch_crude_oil()`
- Modify: `tests/analysis/test_gold_anomaly.py` — add crude oil tests

- [ ] **Step 1: Write crude oil tests**

Add to `tests/analysis/test_gold_anomaly.py`:

```python
class TestCrudeOil:
    """Test _fetch_crude_oil with mocked Yahoo data."""

    def _make_analyzer(self):
        from quant.analysis.indicators.macro_liquidity_analyzer import MacroLiquidityAnalyzer
        return MacroLiquidityAnalyzer()

    def _make_mock_df(self, prices: list) -> pd.DataFrame:
        dates = pd.bdate_range(end=datetime.now(), periods=len(prices))
        return pd.DataFrame({'Close': prices}, index=dates)

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_returns_expected_structure(self, mock_yf):
        prices = [75.0 + i * 0.1 for i in range(30)]
        mock_yf.download.return_value = self._make_mock_df(prices)

        analyzer = self._make_analyzer()
        result = analyzer._fetch_crude_oil(90)

        assert 'current_price' in result
        assert 'weekly_change_pct' in result
        assert 'risk_score' in result
        assert 'signals' in result
        assert 'series' in result
        assert 0 <= result['risk_score'] <= 100

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_weekly_surge_high_risk(self, mock_yf):
        """Weekly price surge > 10% should produce high risk score."""
        prices = [70.0] * 25 + [72, 74, 76, 78, 80]  # ~14% surge last 5 days
        mock_yf.download.return_value = self._make_mock_df(prices)

        analyzer = self._make_analyzer()
        result = analyzer._fetch_crude_oil(90)

        assert result['risk_score'] >= 80

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_weekly_crash_also_risk(self, mock_yf):
        """Weekly crash > 10% is also a risk signal (demand collapse)."""
        prices = [80.0] * 25 + [78, 75, 73, 71, 68]  # ~15% crash
        mock_yf.download.return_value = self._make_mock_df(prices)

        analyzer = self._make_analyzer()
        result = analyzer._fetch_crude_oil(90)

        assert result['risk_score'] >= 60

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_high_price_elevated_risk(self, mock_yf):
        """Oil above $100 should have elevated risk."""
        prices = [105.0] * 30
        mock_yf.download.return_value = self._make_mock_df(prices)

        analyzer = self._make_analyzer()
        result = analyzer._fetch_crude_oil(90)

        assert result['risk_score'] >= 35

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_stable_moderate_price_low_risk(self, mock_yf):
        """Stable oil at moderate price should be low risk."""
        prices = [70.0] * 30
        mock_yf.download.return_value = self._make_mock_df(prices)

        analyzer = self._make_analyzer()
        result = analyzer._fetch_crude_oil(90)

        assert result['risk_score'] <= 20

    @patch('quant.analysis.indicators.macro_liquidity_analyzer.yf')
    def test_empty_data_returns_error(self, mock_yf):
        mock_yf.download.return_value = pd.DataFrame()

        analyzer = self._make_analyzer()
        result = analyzer._fetch_crude_oil(90)

        assert 'error' in result
        assert result['risk_score'] == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/analysis/test_gold_anomaly.py::TestCrudeOil -v`
Expected: FAIL — `_fetch_crude_oil` not defined

- [ ] **Step 3: Implement `_fetch_crude_oil`**

Add to `MacroLiquidityAnalyzer` class:

```python
def _fetch_crude_oil(self, lookback_days: int = 365) -> Dict[str, Any]:
    """
    原油通胀代理

    油价飙涨 → 通胀预期 → 加息预期 → 流动性收紧。
    油价暴跌也是风险（需求崩塌）。
    """
    end = datetime.now()
    start = end - timedelta(days=lookback_days + 30)

    crude = yf.download('CL=F', start=start, end=end, progress=False)

    if crude is None or crude.empty:
        return {'error': '原油数据为空', 'risk_score': 50}

    if isinstance(crude.columns, pd.MultiIndex):
        crude.columns = crude.columns.get_level_values(0)

    close_col = 'Close' if 'Close' in crude.columns else 'close'
    if close_col not in crude.columns:
        return {'error': '原油数据缺少 Close 列', 'risk_score': 50}

    close = crude[close_col].dropna()
    current_price = float(close.iloc[-1])

    # Weekly change
    if len(close) >= 5:
        week_ago = float(close.iloc[-5])
        weekly_change_pct = (current_price - week_ago) / abs(week_ago) * 100 if week_ago != 0 else 0
    else:
        weekly_change_pct = 0

    # Risk scoring
    risk_score = 0
    signals = []

    # Surge risk (inflation pressure)
    if weekly_change_pct > THRESHOLDS['crude_weekly_surge_pct']:
        risk_score = 85
        signals.append(f'🔴 原油周涨 {weekly_change_pct:.1f}%，通胀预期急升')
    elif weekly_change_pct > THRESHOLDS['crude_weekly_rise_pct']:
        risk_score = 60
        signals.append(f'🟠 原油周涨 {weekly_change_pct:.1f}%，关注通胀压力')
    # Crash risk (demand collapse)
    elif weekly_change_pct < -THRESHOLDS['crude_weekly_crash_pct']:
        risk_score = 70
        signals.append(f'🟠 原油周跌 {weekly_change_pct:.1f}%，需求崩塌信号')
    # Price level risk
    elif current_price > THRESHOLDS['crude_high_price']:
        risk_score = 50
        if weekly_change_pct > 0:
            signals.append(f'🟡 油价 ${current_price:.0f} 突破 $100，通胀风险持续')
        else:
            risk_score = 40
    elif current_price > THRESHOLDS['crude_elevated_price']:
        risk_score = 35
    else:
        risk_score = 15

    if not signals:
        signals.append(f'🟢 原油价格稳定（${current_price:.1f}，周变化 {weekly_change_pct:+.1f}%）')

    cutoff = end - timedelta(days=lookback_days)
    series = close[close.index >= cutoff].to_frame(name='crude_oil')

    return {
        'current_price': round(current_price, 2),
        'weekly_change_pct': round(weekly_change_pct, 2),
        'risk_score': risk_score,
        'signals': signals,
        'series': series,
    }
```

- [ ] **Step 4: Wire into `analyze()` method**

Add after copper/gold block (dimension 7):

```python
# 8. 原油通胀
try:
    crude_result = self._fetch_crude_oil(lookback_days)
    dimensions['crude_oil'] = crude_result
    dimension_scores['crude_oil'] = crude_result.get('risk_score', 50)
    signals.extend(crude_result.get('signals', []))
except Exception as e:
    logger.error(f"获取原油数据失败: {e}")
    dimensions['crude_oil'] = {'error': str(e)}
    dimension_scores['crude_oil'] = 50
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/analysis/test_gold_anomaly.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add quant/analysis/indicators/macro_liquidity_analyzer.py tests/analysis/test_gold_anomaly.py
git commit -m "feat(macro): add crude oil inflation dimension to liquidity analyzer"
```

---

### Task 3: Yield Curve Leading Indicator

**Files:**
- Modify: `quant/analysis/indicators/leading_indicators.py` — add `analyze_yield_curve()`, update `analyze_all()`
- Modify: `tests/test_leading_indicators.py` — add yield curve tests

- [ ] **Step 1: Write yield curve tests**

Add to `tests/test_leading_indicators.py`:

```python
class TestAnalyzeYieldCurve:
    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_returns_yield_curve_with_delta(self, mock_get_fred):
        mock_fred = MagicMock()
        # T10Y2Y: 2s10s spread, declining toward zero
        spread_values = _make_daily_series([0.5 - i * 0.015 for i in range(30)])
        # DFII10: real yield
        real_yield_values = _make_daily_series([2.0 + i * 0.01 for i in range(30)])
        mock_fred.get_series.side_effect = [spread_values, real_yield_values]
        mock_get_fred.return_value = mock_fred

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_yield_curve(lookback_days=30)

        assert "spread" in result
        assert "level" in result
        assert "level_cn" in result
        assert "emoji" in result
        assert "real_yield" in result
        assert "delta" in result
        assert result["level"] in ("normal", "flattening", "inverted", "deeply_inverted")

    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_inverted_curve(self, mock_get_fred):
        mock_fred = MagicMock()
        spread_values = _make_daily_series([-0.3] * 30)
        real_yield_values = _make_daily_series([2.5] * 30)
        mock_fred.get_series.side_effect = [spread_values, real_yield_values]
        mock_get_fred.return_value = mock_fred

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_yield_curve(lookback_days=30)

        assert result["level"] == "inverted"
        assert result["emoji"] == "🟠"

    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_deeply_inverted_curve(self, mock_get_fred):
        mock_fred = MagicMock()
        spread_values = _make_daily_series([-0.8] * 30)
        real_yield_values = _make_daily_series([2.0] * 30)
        mock_fred.get_series.side_effect = [spread_values, real_yield_values]
        mock_get_fred.return_value = mock_fred

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_yield_curve(lookback_days=30)

        assert result["level"] == "deeply_inverted"
        assert result["emoji"] == "🔴"

    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_normal_curve(self, mock_get_fred):
        mock_fred = MagicMock()
        spread_values = _make_daily_series([1.0] * 30)
        real_yield_values = _make_daily_series([1.5] * 30)
        mock_fred.get_series.side_effect = [spread_values, real_yield_values]
        mock_get_fred.return_value = mock_fred

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_yield_curve(lookback_days=30)

        assert result["level"] == "normal"
        assert result["emoji"] == "🟢"

    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_fred_failure_returns_error(self, mock_get_fred):
        mock_get_fred.side_effect = Exception("FRED unavailable")

        analyzer = LeadingIndicatorsAnalyzer()
        result = analyzer.analyze_yield_curve()

        assert "error" in result


class TestAnalyzeAllWithYieldCurve:
    @patch("quant.analysis.indicators.leading_indicators.yf")
    @patch("quant.analysis.indicators.leading_indicators.LeadingIndicatorsAnalyzer._get_fred")
    def test_analyze_all_returns_four_indicators(self, mock_get_fred, mock_yf):
        mock_yf.download.return_value = pd.DataFrame(
            {"Close": [20.0] * 30},
            index=pd.date_range("2026-01-01", periods=30, freq="D"),
        )

        mock_fred = MagicMock()
        mock_fred.get_series.return_value = _make_daily_series([3.0] * 30)
        mock_get_fred.return_value = mock_fred

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
        assert "yield_curve" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_leading_indicators.py -v`
Expected: FAIL — `analyze_yield_curve` not defined, `analyze_all` missing `yield_curve`

- [ ] **Step 3: Add yield curve levels and implement `analyze_yield_curve`**

In `quant/analysis/indicators/leading_indicators.py`, add the level constants after `_CREDIT_LEVELS`:

```python
_YIELD_CURVE_LEVELS = [
    (0.5, "normal", "正常", "🟢"),
    (0.0, "flattening", "趋平", "🟡"),
    (-0.5, "inverted", "倒挂", "🟠"),
    (-999, "deeply_inverted", "深度倒挂", "🔴"),
]
```

Add method to `LeadingIndicatorsAnalyzer`:

```python
def analyze_yield_curve(self, lookback_days: int = 365) -> Dict[str, Any]:
    """
    收益率曲线 — 2s10s 利差 + 实际利率注释

    倒挂是最强的衰退前瞻指标。
    """
    try:
        fred = self._get_fred()
        start = datetime.now() - timedelta(days=lookback_days + 30)

        # 2s10s spread (FRED provides this directly)
        spread_series = fred.get_series("T10Y2Y", observation_start=start)

        if spread_series is None or spread_series.empty:
            return {"error": "收益率曲线数据为空"}

        spread_series = spread_series.dropna()
        spread_value = float(spread_series.iloc[-1])
        level, level_cn, emoji = _classify(spread_value, _YIELD_CURVE_LEVELS)
        delta = MomentumDelta.compute(spread_series, velocity_window=5, zscore_window=60)

        # Real yield annotation (best-effort)
        real_yield = None
        try:
            ry_series = fred.get_series("DFII10", observation_start=start)
            if ry_series is not None and not ry_series.empty:
                real_yield = round(float(ry_series.dropna().iloc[-1]), 2)
        except Exception:
            pass

        return {
            "spread": round(spread_value, 2),
            "level": level,
            "level_cn": level_cn,
            "emoji": emoji,
            "real_yield": real_yield,
            "delta": delta,
            "series": spread_series,
        }
    except Exception as e:
        logger.error(f"收益率曲线分析失败: {e}")
        return {"error": str(e)}
```

- [ ] **Step 4: Update `analyze_all` to include yield curve**

```python
def analyze_all(
    self,
    margin_df: Optional[pd.DataFrame] = None,
    lookback_days: int = 365,
) -> Dict[str, Any]:
    return {
        "vix": self.analyze_vix(lookback_days=lookback_days),
        "credit_spread": self.analyze_credit_spread(lookback_days=lookback_days),
        "margin": self.analyze_margin_balance(margin_df=margin_df),
        "yield_curve": self.analyze_yield_curve(lookback_days=lookback_days),
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_leading_indicators.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add quant/analysis/indicators/leading_indicators.py tests/test_leading_indicators.py
git commit -m "feat(leading): add yield curve (2s10s) to leading indicators analyzer"
```

---

### Task 4: Dashboard — Expand Leading Signals to 4 Columns

**Files:**
- Modify: `web/pages/1_📊_Dashboard.py` — update `_render_leading_signals()` from 3→4 columns
- Modify: `web/data_service.py` — filter yield_curve series from cache

- [ ] **Step 1: Update `get_leading_indicators` in data_service.py**

In `web/data_service.py`, the existing `get_leading_indicators()` at line 764 already iterates over all keys in the result dict and strips `series`/`velocity_series`. Since `analyze_all()` now returns `yield_curve` as a 4th key, the existing filtering loop will handle it automatically. No code change needed here.

Verify by reading the loop logic:
```python
# Already handles any number of indicator keys:
for key in result:
    if isinstance(result[key], dict):
        result[key].pop("series", None)
        delta = result[key].get("delta")
        if isinstance(delta, dict):
            delta.pop("velocity_series", None)
```

No modification needed.

- [ ] **Step 2: Update `_render_leading_signals` in Dashboard.py**

Replace the `_render_leading_signals` function in `web/pages/1_📊_Dashboard.py`:

```python
def _render_leading_signals():
    """领先信号一行四灯。"""
    st.markdown("### ⚡ 领先信号")

    try:
        data = get_leading_indicators(lookback_days=365)
    except Exception:
        st.warning("领先指标数据获取失败")
        return

    col1, col2, col3, col4 = st.columns(4)

    # VIX
    with col1:
        vix = data.get("vix", {})
        if "error" in vix:
            st.metric("VIX 恐慌指数", "获取失败")
        else:
            value = vix.get("value", 0)
            emoji = vix.get("emoji", "⚪")
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
            delta = cs.get("delta", {})
            arrow = _VELOCITY_ARROWS.get(delta.get("status", "stable"), "→")
            status_cn = delta.get("status_cn", "")

            st.metric("信用利差 HY-IG", f"{emoji} {spread:.2f}%", f"{arrow} {status_cn}")

            alert = delta.get("alert")
            if alert:
                st.caption(f"⚠️ {alert}")

    # 收益率曲线
    with col3:
        yc = data.get("yield_curve", {})
        if "error" in yc:
            st.metric("收益率曲线 2s10s", "获取失败")
        else:
            spread = yc.get("spread", 0)
            emoji = yc.get("emoji", "⚪")
            level_cn = yc.get("level_cn", "")
            delta = yc.get("delta", {})
            arrow = _VELOCITY_ARROWS.get(delta.get("status", "stable"), "→")
            status_cn = delta.get("status_cn", "")

            st.metric("收益率曲线 2s10s", f"{emoji} {spread:+.2f}%", f"{arrow} {status_cn}")

            real_yield = yc.get("real_yield")
            if real_yield is not None:
                st.caption(f"实际利率 {real_yield:.1f}%")

            alert = delta.get("alert")
            if alert:
                st.caption(f"⚠️ {alert}")

    # 融资余额
    with col4:
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

- [ ] **Step 3: Commit**

```bash
git add web/pages/1_📊_Dashboard.py
git commit -m "feat(dashboard): expand leading signals row to 4 columns with yield curve"
```

---

### Task 5: Cache TTL Optimization

**Files:**
- Modify: `web/data_service.py` — update TTL for `get_leading_indicators`

- [ ] **Step 1: Update `get_leading_indicators` TTL**

In `web/data_service.py`, change line 763:

```python
# Before:
@st.cache_data(ttl=3600, show_spinner=False)  # 1 hour cache

# After:
@st.cache_data(ttl=14400, show_spinner=False)  # 4 hour cache — macro data is daily frequency
```

Note: `get_macro_liquidity` and `get_global_usd_liquidity` already use file-based caching with 12h expiry (`CACHE_EXPIRY_HOURS = 12`), which is adequate. Only `get_leading_indicators` uses the shorter `st.cache_data` TTL that needs updating.

- [ ] **Step 2: Commit**

```bash
git add web/data_service.py
git commit -m "perf(cache): increase leading indicators TTL from 1h to 4h"
```

---

### Task 6: Smoke Test — Full Dashboard Verification

**Files:** None (read-only verification)

- [ ] **Step 1: Run all unit tests**

Run: `python -m pytest tests/analysis/test_gold_anomaly.py tests/test_leading_indicators.py -v`
Expected: ALL PASS

- [ ] **Step 2: Import smoke test**

Run:
```bash
python -c "
from quant.analysis.indicators.macro_liquidity_analyzer import MacroLiquidityAnalyzer, DIMENSION_WEIGHTS
from quant.analysis.indicators.leading_indicators import LeadingIndicatorsAnalyzer
assert len(DIMENSION_WEIGHTS) == 8
assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9
print('Weights:', DIMENSION_WEIGHTS)
print('✅ Import OK, 8 dimensions, weights sum to 1.0')
"
```

- [ ] **Step 3: Visual test in browser**

Open `http://localhost:8501/Dashboard` and verify:
1. "宏观环境" row shows macro liquidity status (now incorporating 8 dimensions)
2. "领先信号" row shows 4 columns: VIX, 信用利差, 收益率曲线, 融资余额
3. No error messages on any page

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(macro): complete macro enhancement — yield curve, copper/gold, crude oil"
```
