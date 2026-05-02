# Signal Foundation Implementation Plan (Track 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the analysis backbone — Regime Detector, Signal Registry, Signal Validator, Transmission Graph, Commodity Analyzer, and Verdict Engine — so every signal shown to the user is validated and regime-aware.

**Architecture:** Six new modules layered bottom-up: Regime Detector classifies market state per asset pool, Signal Registry manages signal definitions with regime filters, Signal Validator backtests each signal's hit-rate, Transmission Graph monitors cross-asset causal chains, Commodity Analyzer adds gold/commodity coverage, and Verdict Engine synthesizes everything into per-pool action recommendations. All new modules use the `quant/data/` provider layer and `fredapi` for FRED data.

**Tech Stack:** Python 3.11+, pytest, dataclasses, PyYAML, pandas, fredapi, quant/data/ providers (Tushare + Yahoo)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `quant/analysis/regime/__init__.py` | Package init |
| **Create** | `quant/analysis/regime/regime_detector.py` | RegimeDetector: classifies regime per asset pool |
| **Create** | `quant/analysis/signals/__init__.py` | Package init |
| **Create** | `quant/analysis/signals/signal_registry.py` | SignalDefinition, SignalValidation, ActiveSignal, SignalRegistry |
| **Create** | `quant/analysis/signals/signal_validator.py` | Walk-forward hit-rate validation engine |
| **Create** | `quant/analysis/transmission/__init__.py` | Package init |
| **Create** | `quant/analysis/transmission/transmission_graph.py` | TransmissionEdge, ActiveTransmission, TransmissionGraph |
| **Create** | `quant/analysis/indicators/commodity_analyzer.py` | CommodityAnalyzer for gold & commodities |
| **Create** | `quant/analysis/verdict/__init__.py` | Package init |
| **Create** | `quant/analysis/verdict/verdict_engine.py` | VerdictEngine: synthesizes conclusions |
| **Create** | `config/regime_thresholds.yaml` | Regime classification thresholds |
| **Create** | `config/signals.yaml` | Signal definitions catalog |
| **Create** | `config/transmission_edges.yaml` | Cross-asset causal edges |
| **Create** | `tests/unit/test_regime_detector.py` | Tests for RegimeDetector |
| **Create** | `tests/unit/test_signal_registry.py` | Tests for SignalRegistry |
| **Create** | `tests/unit/test_signal_validator.py` | Tests for SignalValidator |
| **Create** | `tests/unit/test_transmission_graph.py` | Tests for TransmissionGraph |
| **Create** | `tests/unit/test_commodity_analyzer.py` | Tests for CommodityAnalyzer |
| **Create** | `tests/unit/test_verdict_engine.py` | Tests for VerdictEngine |

---

### Task 1: Shared Data Classes and Config Files

**Files:**
- Create: `config/regime_thresholds.yaml`
- Create: `config/signals.yaml`
- Create: `config/transmission_edges.yaml`

These config files define the parameters for all downstream modules. Creating them first ensures every module reads from config rather than hardcoding values.

- [ ] **Step 1: Create regime_thresholds.yaml**

```yaml
# config/regime_thresholds.yaml
# Regime classification thresholds per asset pool.
# Each pool defines indicator thresholds for regime transitions.
# "confirmation_days" prevents whipsaw on noisy data.

a_shares:
  confirmation_days: 2
  indicators:
    margin_debt_trend:
      # 5-day change in margin balance (%)
      risk_on_above: 2.0
      risk_off_below: -3.0
    northbound_flow:
      # 5-day cumulative net flow (亿元)
      risk_on_above: 50.0
      risk_off_below: -80.0
    market_breadth:
      # % of stocks above MA20
      risk_on_above: 60.0
      risk_off_below: 30.0
    china_risk_score:
      # From ChinaMarketSignalAnalyzer (0-100, higher=riskier)
      risk_on_below: 40.0
      risk_off_above: 70.0

us_stocks:
  confirmation_days: 2
  indicators:
    yield_curve_2s10s:
      # 2Y-10Y spread (pp)
      expansion_above: 0.0
      contraction_below: -0.5
    credit_spread:
      # BAA-AAA spread (pp)
      expansion_below: 1.5
      contraction_above: 2.5
    vix:
      # VIX level
      expansion_below: 20.0
      contraction_above: 30.0
    macro_risk_score:
      # From MacroLiquidityAnalyzer (0-100, higher=riskier)
      expansion_below: 40.0
      contraction_above: 65.0

gold:
  confirmation_days: 2
  indicators:
    real_rate_10y:
      # 10Y TIPS yield (%)
      bullish_below: 1.0
      bearish_above: 2.5
    dxy_trend:
      # DXY 20-day rate of change (%)
      bullish_below: -1.0
      bearish_above: 2.0
    gold_silver_ratio:
      # Gold/Silver price ratio
      bullish_above: 85.0
      bearish_below: 65.0

commodities:
  confirmation_days: 3
  indicators:
    copper_gold_ratio:
      # Copper/Gold ratio (normalized)
      reflation_above: 0.0
      deflation_below: -5.0
    crude_oil_trend:
      # Crude oil 20-day rate of change (%)
      reflation_above: 5.0
      deflation_below: -10.0
    dxy_trend:
      # Same as gold
      reflation_below: -1.0
      deflation_above: 2.0
```

- [ ] **Step 2: Create signals.yaml**

```yaml
# config/signals.yaml
# Signal definitions catalog. Each signal must have:
#   - name: unique identifier
#   - asset_pools: which pools this signal applies to
#   - signal_type: category
#   - source_analyzer: which existing analyzer produces the raw data
#   - lookback_days: data window needed
#   - condition: machine-readable condition string
#   - condition_description: human-readable explanation
#   - regime_filter: regimes where this signal is active (empty = always active)
#   - forward_days: horizon for hit-rate validation (default 5)

min_hit_rate: 0.55  # signals below this are suppressed

signals:
  - name: rsi_oversold_bounce
    asset_pools: [a_shares]
    signal_type: mean_reversion
    source_analyzer: TechnicalAnalyzer
    lookback_days: 60
    condition: "RSI < 30"
    condition_description: "RSI drops below 30 (oversold territory)"
    regime_filter:
      a_shares: [risk-on, transition]
    forward_days: 5

  - name: rsi_overbought_warning
    asset_pools: [a_shares]
    signal_type: mean_reversion
    source_analyzer: TechnicalAnalyzer
    lookback_days: 60
    condition: "RSI > 70"
    condition_description: "RSI exceeds 70 (overbought territory)"
    regime_filter:
      a_shares: [risk-on, transition, risk-off]
    forward_days: 5

  - name: box_breakout_up
    asset_pools: [a_shares]
    signal_type: breakout
    source_analyzer: BoxBreakoutAnalyzer
    lookback_days: 120
    condition: "breakout_type == 'up' AND volume_confirmed"
    condition_description: "Price breaks above Donchian Channel with volume confirmation"
    regime_filter:
      a_shares: [risk-on, transition]
    forward_days: 20

  - name: institutional_accumulation
    asset_pools: [a_shares]
    signal_type: momentum
    source_analyzer: CapitalFlowAnalyzer
    lookback_days: 30
    condition: "comprehensive_score > 70"
    condition_description: "Strong institutional net inflow with consistency"
    regime_filter:
      a_shares: [risk-on, transition]
    forward_days: 10

  - name: institutional_distribution
    asset_pools: [a_shares]
    signal_type: momentum
    source_analyzer: CapitalFlowAnalyzer
    lookback_days: 30
    condition: "comprehensive_score < 30"
    condition_description: "Sustained institutional net outflow"
    regime_filter:
      a_shares: [risk-on, transition, risk-off]
    forward_days: 10

  - name: ma_golden_cross
    asset_pools: [a_shares, us_stocks]
    signal_type: trend
    source_analyzer: TechnicalAnalyzer
    lookback_days: 120
    condition: "MA20 crosses above MA60"
    condition_description: "20-day MA crosses above 60-day MA"
    regime_filter:
      a_shares: [risk-on, transition]
      us_stocks: [expansion, transition]
    forward_days: 20

  - name: ma_death_cross
    asset_pools: [a_shares, us_stocks]
    signal_type: trend
    source_analyzer: TechnicalAnalyzer
    lookback_days: 120
    condition: "MA20 crosses below MA60"
    condition_description: "20-day MA crosses below 60-day MA"
    regime_filter:
      a_shares: [risk-on, transition, risk-off]
      us_stocks: [expansion, transition, contraction]
    forward_days: 20

  - name: value_convergence
    asset_pools: [us_stocks]
    signal_type: value
    source_analyzer: ValueInvestingAnalyzer
    lookback_days: 250
    condition: "composite_score > 75"
    condition_description: "Five-factor value score exceeds 75 (strong value)"
    regime_filter:
      us_stocks: [expansion, transition]
    forward_days: 60

  - name: margin_debt_acceleration
    asset_pools: [a_shares]
    signal_type: macro
    source_analyzer: LeadingIndicatorsAnalyzer
    lookback_days: 60
    condition: "margin_5d_change_pct > 3.0"
    condition_description: "A-share margin debt surging (5-day change > 3%)"
    regime_filter: {}
    forward_days: 5

  - name: credit_spread_widening
    asset_pools: [us_stocks]
    signal_type: macro
    source_analyzer: LeadingIndicatorsAnalyzer
    lookback_days: 90
    condition: "credit_spread_change_20d > 0.3"
    condition_description: "Credit spread widening rapidly (20-day change > 0.3pp)"
    regime_filter: {}
    forward_days: 10

  - name: vix_spike
    asset_pools: [us_stocks, gold]
    signal_type: macro
    source_analyzer: LeadingIndicatorsAnalyzer
    lookback_days: 30
    condition: "vix > 25 AND vix_5d_change > 5"
    condition_description: "VIX spikes above 25 with rapid increase"
    regime_filter: {}
    forward_days: 5

  - name: dxy_trend_reversal_down
    asset_pools: [gold, commodities]
    signal_type: macro
    source_analyzer: GlobalUsdLiquidityAnalyzer
    lookback_days: 60
    condition: "dxy_20d_roc < -2.0"
    condition_description: "DXY in sustained decline (20-day ROC < -2%)"
    regime_filter: {}
    forward_days: 10
```

- [ ] **Step 3: Create transmission_edges.yaml**

```yaml
# config/transmission_edges.yaml
# Cross-asset causal edges for the Transmission Graph.
# Each edge defines: source node, target node, direction, lag, threshold.
# "strength" is updated by backtesting — initial values are estimates.

edges:
  - source: DXY
    target: gold
    direction: inverse
    lag_min_days: 0
    lag_max_days: 1
    threshold_pct: 0.8
    initial_strength: 0.72
    source_ticker: DX-Y.NYB
    target_ticker: GC=F

  - source: DXY
    target: copper
    direction: inverse
    lag_min_days: 1
    lag_max_days: 3
    threshold_pct: 1.0
    initial_strength: 0.58
    source_ticker: DX-Y.NYB
    target_ticker: HG=F

  - source: DXY
    target: a_share_northbound
    direction: inverse
    lag_min_days: 1
    lag_max_days: 3
    threshold_pct: 1.0
    initial_strength: 0.55
    source_ticker: DX-Y.NYB
    target_ticker: null  # fetched via Tushare HSGT

  - source: gold
    target: a_share_gold_sector
    direction: direct
    lag_min_days: 0
    lag_max_days: 2
    threshold_pct: 1.5
    initial_strength: 0.65
    source_ticker: GC=F
    target_ticker: null  # sector index

  - source: credit_spread
    target: us_risk_assets
    direction: inverse
    lag_min_days: 3
    lag_max_days: 7
    threshold_pp: 0.15
    initial_strength: 0.61
    source_series: BAMLH0A0HYM2  # FRED series
    target_ticker: SPY

  - source: VIX
    target: risk_assets
    direction: inverse
    lag_min_days: 0
    lag_max_days: 1
    threshold_points: 3.0
    initial_strength: 0.70
    source_ticker: ^VIX
    target_ticker: SPY

  - source: fed_balance_sheet
    target: usd_liquidity
    direction: direct
    lag_min_days: 5
    lag_max_days: 15
    threshold_pct: 1.0
    initial_strength: 0.68
    source_series: WALCL  # FRED series
    target_ticker: null  # composite index

  - source: margin_debt
    target: a_share_sentiment
    direction: direct
    lag_min_days: 1
    lag_max_days: 3
    threshold_pct: 3.0
    initial_strength: 0.64
    source_ticker: null  # Tushare margin data
    target_ticker: null  # composite

  - source: copper_gold_ratio
    target: commodities_regime
    direction: direct
    lag_min_days: 0
    lag_max_days: 5
    threshold_pct: 2.0
    initial_strength: 0.60
    source_ticker: null  # computed HG=F / GC=F
    target_ticker: null

  - source: crude_oil
    target: inflation_expectations
    direction: direct
    lag_min_days: 5
    lag_max_days: 10
    threshold_pct: 5.0
    initial_strength: 0.55
    source_ticker: CL=F
    target_ticker: null  # FRED T5YIE
```

- [ ] **Step 4: Commit config files**

```bash
git add config/regime_thresholds.yaml config/signals.yaml config/transmission_edges.yaml
git commit -m "feat(config): add regime, signal, and transmission config files"
```

---

### Task 2: Regime Detector

**Files:**
- Create: `quant/analysis/regime/__init__.py`
- Create: `quant/analysis/regime/regime_detector.py`
- Create: `tests/unit/test_regime_detector.py`

- [ ] **Step 1: Write tests for RegimeDetector**

```python
# tests/unit/test_regime_detector.py
"""Tests for RegimeDetector — regime classification per asset pool."""
import pytest
from unittest.mock import patch, MagicMock
from quant.analysis.regime.regime_detector import RegimeDetector, RegimeState


class TestRegimeState:
    """RegimeState dataclass basic tests."""

    def test_regime_state_creation(self):
        state = RegimeState(
            pool="a_shares",
            regime="risk-off",
            confidence=0.8,
            days_since_change=3,
            drivers=["margin debt declining", "northbound outflow"],
            updated_at="2026-04-12T09:00:00",
        )
        assert state.pool == "a_shares"
        assert state.regime == "risk-off"
        assert state.confidence == 0.8
        assert len(state.drivers) == 2


class TestRegimeDetectorAShares:
    """Test A-share regime classification."""

    @pytest.fixture
    def detector(self):
        return RegimeDetector()

    def test_risk_on_when_all_bullish(self, detector):
        """All indicators bullish -> risk-on."""
        indicators = {
            "margin_debt_trend": 3.0,       # above 2.0 threshold
            "northbound_flow": 100.0,        # above 50.0 threshold
            "market_breadth": 70.0,          # above 60.0 threshold
            "china_risk_score": 30.0,        # below 40.0 threshold
        }
        state = detector.classify_pool("a_shares", indicators)
        assert state.regime == "risk-on"
        assert state.confidence > 0.5

    def test_risk_off_when_all_bearish(self, detector):
        """All indicators bearish -> risk-off."""
        indicators = {
            "margin_debt_trend": -5.0,
            "northbound_flow": -120.0,
            "market_breadth": 20.0,
            "china_risk_score": 80.0,
        }
        state = detector.classify_pool("a_shares", indicators)
        assert state.regime == "risk-off"
        assert state.confidence > 0.5

    def test_transition_when_mixed(self, detector):
        """Mixed indicators -> transition."""
        indicators = {
            "margin_debt_trend": 1.0,        # neutral
            "northbound_flow": -30.0,         # neutral
            "market_breadth": 45.0,           # neutral
            "china_risk_score": 55.0,         # neutral
        }
        state = detector.classify_pool("a_shares", indicators)
        assert state.regime == "transition"

    def test_drivers_list_populated(self, detector):
        """Drivers explain which indicators drove the regime call."""
        indicators = {
            "margin_debt_trend": -5.0,
            "northbound_flow": -120.0,
            "market_breadth": 20.0,
            "china_risk_score": 80.0,
        }
        state = detector.classify_pool("a_shares", indicators)
        assert len(state.drivers) > 0
        assert any("margin" in d.lower() for d in state.drivers)


class TestRegimeDetectorUSStocks:
    """Test US stock regime classification."""

    @pytest.fixture
    def detector(self):
        return RegimeDetector()

    def test_expansion_when_favorable(self, detector):
        indicators = {
            "yield_curve_2s10s": 0.5,
            "credit_spread": 1.0,
            "vix": 15.0,
            "macro_risk_score": 30.0,
        }
        state = detector.classify_pool("us_stocks", indicators)
        assert state.regime == "expansion"

    def test_contraction_when_stressed(self, detector):
        indicators = {
            "yield_curve_2s10s": -0.8,
            "credit_spread": 3.0,
            "vix": 35.0,
            "macro_risk_score": 75.0,
        }
        state = detector.classify_pool("us_stocks", indicators)
        assert state.regime == "contraction"


class TestRegimeDetectorGold:
    """Test gold regime classification."""

    @pytest.fixture
    def detector(self):
        return RegimeDetector()

    def test_bullish_when_favorable(self, detector):
        indicators = {
            "real_rate_10y": 0.5,
            "dxy_trend": -2.0,
            "gold_silver_ratio": 90.0,
        }
        state = detector.classify_pool("gold", indicators)
        assert state.regime == "bullish"

    def test_bearish_when_unfavorable(self, detector):
        indicators = {
            "real_rate_10y": 3.0,
            "dxy_trend": 3.0,
            "gold_silver_ratio": 60.0,
        }
        state = detector.classify_pool("gold", indicators)
        assert state.regime == "bearish"


class TestRegimeDetectorCommodities:
    """Test commodities regime classification."""

    @pytest.fixture
    def detector(self):
        return RegimeDetector()

    def test_reflation_when_strong(self, detector):
        indicators = {
            "copper_gold_ratio": 2.0,
            "crude_oil_trend": 8.0,
            "dxy_trend": -2.0,
        }
        state = detector.classify_pool("commodities", indicators)
        assert state.regime == "reflation"

    def test_deflation_when_weak(self, detector):
        indicators = {
            "copper_gold_ratio": -8.0,
            "crude_oil_trend": -15.0,
            "dxy_trend": 3.0,
        }
        state = detector.classify_pool("commodities", indicators)
        assert state.regime == "deflation"


class TestRegimeDetectorAllPools:
    """Test classify_all which runs all four pools."""

    @pytest.fixture
    def detector(self):
        return RegimeDetector()

    def test_classify_all_returns_four_states(self, detector):
        all_indicators = {
            "a_shares": {
                "margin_debt_trend": 3.0,
                "northbound_flow": 100.0,
                "market_breadth": 70.0,
                "china_risk_score": 30.0,
            },
            "us_stocks": {
                "yield_curve_2s10s": 0.5,
                "credit_spread": 1.0,
                "vix": 15.0,
                "macro_risk_score": 30.0,
            },
            "gold": {
                "real_rate_10y": 0.5,
                "dxy_trend": -2.0,
                "gold_silver_ratio": 90.0,
            },
            "commodities": {
                "copper_gold_ratio": 2.0,
                "crude_oil_trend": 8.0,
                "dxy_trend": -2.0,
            },
        }
        states = detector.classify_all(all_indicators)
        assert len(states) == 4
        assert all(isinstance(s, RegimeState) for s in states.values())
        assert set(states.keys()) == {"a_shares", "us_stocks", "gold", "commodities"}

    def test_unknown_pool_raises(self, detector):
        with pytest.raises(ValueError, match="Unknown pool"):
            detector.classify_pool("crypto", {})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_regime_detector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quant.analysis.regime'`

- [ ] **Step 3: Implement RegimeDetector**

```python
# quant/analysis/regime/__init__.py
from .regime_detector import RegimeDetector, RegimeState

__all__ = ["RegimeDetector", "RegimeState"]
```

```python
# quant/analysis/regime/regime_detector.py
"""
Regime Detector — classifies market state per asset pool.

Each pool (a_shares, us_stocks, gold, commodities) is classified into
a regime based on threshold rules applied to macro indicators.
Thresholds are loaded from config/regime_thresholds.yaml.
"""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml


POOLS = ("a_shares", "us_stocks", "gold", "commodities")

_REGIME_MAP = {
    "a_shares": {"positive": "risk-on", "negative": "risk-off", "neutral": "transition"},
    "us_stocks": {"positive": "expansion", "negative": "contraction", "neutral": "transition"},
    "gold": {"positive": "bullish", "negative": "bearish", "neutral": "neutral"},
    "commodities": {"positive": "reflation", "negative": "deflation", "neutral": "neutral"},
}

# Which direction each indicator signals "positive" regime.
# True means higher value = positive; False means lower value = positive.
_INDICATOR_POLARITY = {
    # A-shares
    "margin_debt_trend": True,      # higher margin = risk-on
    "northbound_flow": True,        # higher inflow = risk-on
    "market_breadth": True,         # more stocks above MA = risk-on
    "china_risk_score": False,      # lower risk score = risk-on
    # US stocks
    "yield_curve_2s10s": True,      # positive curve = expansion
    "credit_spread": False,         # tighter spread = expansion
    "vix": False,                   # lower VIX = expansion
    "macro_risk_score": False,      # lower risk = expansion
    # Gold
    "real_rate_10y": False,         # lower real rates = gold bullish
    "dxy_trend": False,             # weaker dollar = gold bullish
    "gold_silver_ratio": True,      # higher ratio = flight to safety = gold bullish
    # Commodities
    "copper_gold_ratio": True,      # higher = reflation
    "crude_oil_trend": True,        # higher = reflation
    # dxy_trend reused for commodities (same polarity: lower = reflation)
}


@dataclass
class RegimeState:
    pool: str
    regime: str
    confidence: float
    days_since_change: int
    drivers: List[str]
    updated_at: str


class RegimeDetector:
    """Classifies market regime for each asset pool using config-driven thresholds."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = str(Path(__file__).parents[3] / "config" / "regime_thresholds.yaml")
        with open(config_path) as f:
            self._config = yaml.safe_load(f)
        self._previous_regimes: Dict[str, List[str]] = {p: [] for p in POOLS}

    def classify_pool(self, pool: str, indicators: Dict[str, float]) -> RegimeState:
        """Classify a single pool given its indicator values."""
        if pool not in POOLS:
            raise ValueError(f"Unknown pool: {pool}. Valid pools: {POOLS}")

        pool_config = self._config[pool]
        indicator_configs = pool_config["indicators"]

        positive_votes = 0
        negative_votes = 0
        total_votes = 0
        drivers: List[str] = []

        for ind_name, thresholds in indicator_configs.items():
            value = indicators.get(ind_name)
            if value is None:
                continue

            total_votes += 1
            vote = self._vote_indicator(pool, ind_name, value, thresholds)

            if vote > 0:
                positive_votes += 1
                drivers.append(f"{ind_name}: {value:.1f} (bullish)")
            elif vote < 0:
                negative_votes += 1
                drivers.append(f"{ind_name}: {value:.1f} (bearish)")

        if total_votes == 0:
            regime_key = "neutral"
            confidence = 0.0
        else:
            pos_ratio = positive_votes / total_votes
            neg_ratio = negative_votes / total_votes

            if pos_ratio >= 0.6:
                regime_key = "positive"
                confidence = pos_ratio
            elif neg_ratio >= 0.6:
                regime_key = "negative"
                confidence = neg_ratio
            else:
                regime_key = "neutral"
                confidence = 1.0 - abs(pos_ratio - neg_ratio)

        regime_label = _REGIME_MAP[pool][regime_key]

        # Track regime history for days_since_change
        history = self._previous_regimes[pool]
        if history and history[-1] == regime_label:
            days_since_change = len(history)
        else:
            days_since_change = 0
        history.append(regime_label)
        # Keep last 30 entries
        if len(history) > 30:
            self._previous_regimes[pool] = history[-30:]

        return RegimeState(
            pool=pool,
            regime=regime_label,
            confidence=round(confidence, 2),
            days_since_change=days_since_change,
            drivers=drivers,
            updated_at=datetime.now().isoformat(timespec="seconds"),
        )

    def classify_all(self, all_indicators: Dict[str, Dict[str, float]]) -> Dict[str, RegimeState]:
        """Classify all four pools at once."""
        return {pool: self.classify_pool(pool, all_indicators.get(pool, {})) for pool in POOLS}

    def _vote_indicator(self, pool: str, ind_name: str, value: float, thresholds: dict) -> int:
        """Return +1 (positive), -1 (negative), or 0 (neutral) for one indicator."""
        # Find the positive and negative threshold keys
        pos_key = None
        neg_key = None
        for key in thresholds:
            if key == ind_name:
                continue
            # Positive thresholds contain keywords like "risk_on", "expansion", "bullish", "reflation"
            if any(word in key for word in ("risk_on", "expansion", "bullish", "reflation")):
                pos_key = key
            # Negative thresholds
            if any(word in key for word in ("risk_off", "contraction", "bearish", "deflation")):
                neg_key = key

        if pos_key is None or neg_key is None:
            return 0

        pos_threshold = thresholds[pos_key]
        neg_threshold = thresholds[neg_key]

        is_higher_positive = _INDICATOR_POLARITY.get(ind_name, True)

        if is_higher_positive:
            if value >= pos_threshold:
                return 1
            elif value <= neg_threshold:
                return -1
        else:
            if value <= pos_threshold:
                return 1
            elif value >= neg_threshold:
                return -1

        return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_regime_detector.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/regime/ tests/unit/test_regime_detector.py
git commit -m "feat(regime): add RegimeDetector with config-driven thresholds"
```

---

### Task 3: Signal Registry

**Files:**
- Create: `quant/analysis/signals/__init__.py`
- Create: `quant/analysis/signals/signal_registry.py`
- Create: `tests/unit/test_signal_registry.py`

- [ ] **Step 1: Write tests for Signal Registry**

```python
# tests/unit/test_signal_registry.py
"""Tests for SignalRegistry — signal definition, validation, and filtering."""
import pytest
from quant.analysis.signals.signal_registry import (
    SignalDefinition,
    SignalValidation,
    ActiveSignal,
    SignalRegistry,
)


class TestSignalDefinition:
    def test_creation(self):
        sig = SignalDefinition(
            name="rsi_oversold_bounce",
            asset_pools=["a_shares"],
            signal_type="mean_reversion",
            source_analyzer="TechnicalAnalyzer",
            lookback_days=60,
            condition="RSI < 30",
            condition_description="RSI drops below 30",
            regime_filter={"a_shares": ["risk-on", "transition"]},
            forward_days=5,
        )
        assert sig.name == "rsi_oversold_bounce"
        assert "a_shares" in sig.asset_pools


class TestSignalValidation:
    def test_is_valid_above_threshold(self):
        val = SignalValidation(
            hit_rate=0.67,
            avg_return=0.021,
            sample_size=42,
            validated_date="2026-04-01",
            regime_hit_rates={"risk-on": 0.72, "risk-off": 0.38},
        )
        assert val.is_valid(min_hit_rate=0.55)
        assert not val.is_valid(min_hit_rate=0.70)

    def test_hit_rate_for_regime(self):
        val = SignalValidation(
            hit_rate=0.67,
            avg_return=0.021,
            sample_size=42,
            validated_date="2026-04-01",
            regime_hit_rates={"risk-on": 0.72, "risk-off": 0.38},
        )
        assert val.hit_rate_for_regime("risk-on") == 0.72
        assert val.hit_rate_for_regime("unknown") == val.hit_rate  # fallback


class TestSignalRegistry:
    @pytest.fixture
    def registry(self):
        return SignalRegistry()

    def test_loads_signals_from_config(self, registry):
        """Registry loads signals from config/signals.yaml on init."""
        assert len(registry.definitions) > 0
        names = [d.name for d in registry.definitions]
        assert "rsi_oversold_bounce" in names

    def test_get_signals_for_pool(self, registry):
        """Filter signals by asset pool."""
        a_share_sigs = registry.get_signals_for_pool("a_shares")
        assert all("a_shares" in s.asset_pools for s in a_share_sigs)
        assert len(a_share_sigs) > 0

    def test_get_signals_for_pool_and_regime(self, registry):
        """Filter signals by pool AND regime."""
        sigs = registry.get_signals_for_pool_and_regime("a_shares", "risk-off")
        # RSI overbought should be active in risk-off, but RSI oversold should not
        names = [s.name for s in sigs]
        assert "rsi_overbought_warning" in names
        assert "rsi_oversold_bounce" not in names

    def test_get_signal_by_name(self, registry):
        sig = registry.get_signal_by_name("vix_spike")
        assert sig is not None
        assert sig.signal_type == "macro"

    def test_get_signal_by_name_not_found(self, registry):
        assert registry.get_signal_by_name("nonexistent") is None

    def test_set_and_get_validation(self, registry):
        val = SignalValidation(
            hit_rate=0.67,
            avg_return=0.021,
            sample_size=42,
            validated_date="2026-04-01",
            regime_hit_rates={},
        )
        registry.set_validation("rsi_oversold_bounce", val)
        retrieved = registry.get_validation("rsi_oversold_bounce")
        assert retrieved is not None
        assert retrieved.hit_rate == 0.67

    def test_min_hit_rate_from_config(self, registry):
        assert registry.min_hit_rate == 0.55
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_signal_registry.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement SignalRegistry**

```python
# quant/analysis/signals/__init__.py
from .signal_registry import (
    SignalDefinition,
    SignalValidation,
    ActiveSignal,
    SignalRegistry,
)

__all__ = ["SignalDefinition", "SignalValidation", "ActiveSignal", "SignalRegistry"]
```

```python
# quant/analysis/signals/signal_registry.py
"""
Signal Registry — manages signal definitions, validations, and filtering.

Signals are loaded from config/signals.yaml. Each signal has a definition
(what it detects), an optional validation (backtested hit-rate), and can
produce ActiveSignal instances when conditions are met.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class SignalDefinition:
    name: str
    asset_pools: List[str]
    signal_type: str
    source_analyzer: str
    lookback_days: int
    condition: str
    condition_description: str
    regime_filter: Dict[str, List[str]]
    forward_days: int = 5


@dataclass
class SignalValidation:
    hit_rate: float
    avg_return: float
    sample_size: int
    validated_date: str
    regime_hit_rates: Dict[str, float]

    def is_valid(self, min_hit_rate: float = 0.55) -> bool:
        return self.hit_rate >= min_hit_rate

    def hit_rate_for_regime(self, regime: str) -> float:
        return self.regime_hit_rates.get(regime, self.hit_rate)


@dataclass
class ActiveSignal:
    definition: SignalDefinition
    validation: Optional[SignalValidation]
    fired_at: str
    symbol: Optional[str]
    action: str
    reasoning: str


class SignalRegistry:
    """Loads signal definitions from YAML config and manages validations."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = str(Path(__file__).parents[3] / "config" / "signals.yaml")
        with open(config_path) as f:
            raw = yaml.safe_load(f)

        self.min_hit_rate: float = raw.get("min_hit_rate", 0.55)
        self.definitions: List[SignalDefinition] = []
        self._validations: Dict[str, SignalValidation] = {}

        for entry in raw.get("signals", []):
            self.definitions.append(SignalDefinition(
                name=entry["name"],
                asset_pools=entry["asset_pools"],
                signal_type=entry["signal_type"],
                source_analyzer=entry["source_analyzer"],
                lookback_days=entry["lookback_days"],
                condition=entry["condition"],
                condition_description=entry["condition_description"],
                regime_filter=entry.get("regime_filter", {}),
                forward_days=entry.get("forward_days", 5),
            ))

    def get_signals_for_pool(self, pool: str) -> List[SignalDefinition]:
        return [d for d in self.definitions if pool in d.asset_pools]

    def get_signals_for_pool_and_regime(
        self, pool: str, regime: str
    ) -> List[SignalDefinition]:
        result = []
        for d in self.definitions:
            if pool not in d.asset_pools:
                continue
            # If no regime_filter for this pool, signal is always active
            pool_regimes = d.regime_filter.get(pool)
            if pool_regimes is None or len(d.regime_filter) == 0:
                result.append(d)
            elif regime in pool_regimes:
                result.append(d)
        return result

    def get_signal_by_name(self, name: str) -> Optional[SignalDefinition]:
        for d in self.definitions:
            if d.name == name:
                return d
        return None

    def set_validation(self, signal_name: str, validation: SignalValidation) -> None:
        self._validations[signal_name] = validation

    def get_validation(self, signal_name: str) -> Optional[SignalValidation]:
        return self._validations.get(signal_name)

    def load_validations_from_dir(self, dir_path: str) -> int:
        """Load cached validation results from JSON files. Returns count loaded."""
        import json
        loaded = 0
        path = Path(dir_path)
        if not path.exists():
            return 0
        for f in path.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                val = SignalValidation(
                    hit_rate=data["hit_rate"],
                    avg_return=data["avg_return"],
                    sample_size=data["sample_size"],
                    validated_date=data["validated_date"],
                    regime_hit_rates=data.get("regime_hit_rates", {}),
                )
                self._validations[f.stem] = val
                loaded += 1
            except (json.JSONDecodeError, KeyError):
                continue
        return loaded
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_signal_registry.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/signals/ tests/unit/test_signal_registry.py
git commit -m "feat(signals): add SignalRegistry with YAML-driven definitions"
```

---

### Task 4: Signal Validator

**Files:**
- Create: `quant/analysis/signals/signal_validator.py`
- Create: `tests/unit/test_signal_validator.py`

- [ ] **Step 1: Write tests for SignalValidator**

```python
# tests/unit/test_signal_validator.py
"""Tests for SignalValidator — walk-forward hit-rate validation."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from quant.analysis.signals.signal_validator import SignalValidator
from quant.analysis.signals.signal_registry import SignalDefinition, SignalValidation


def _make_price_series(n_days: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq="B")
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, n_days)))
    return pd.DataFrame({
        "open": close * (1 + rng.normal(0, 0.005, n_days)),
        "high": close * (1 + abs(rng.normal(0, 0.01, n_days))),
        "low": close * (1 - abs(rng.normal(0, 0.01, n_days))),
        "close": close,
        "volume": rng.randint(1_000_000, 10_000_000, n_days).astype(float),
    }, index=dates)


class TestSignalValidator:
    @pytest.fixture
    def validator(self):
        return SignalValidator()

    @pytest.fixture
    def price_data(self):
        return _make_price_series()

    def test_validate_rsi_signal(self, validator, price_data):
        """Validate RSI oversold signal against price data."""
        sig_def = SignalDefinition(
            name="rsi_oversold_bounce",
            asset_pools=["a_shares"],
            signal_type="mean_reversion",
            source_analyzer="TechnicalAnalyzer",
            lookback_days=60,
            condition="RSI < 30",
            condition_description="RSI below 30",
            regime_filter={},
            forward_days=5,
        )
        result = validator.validate_signal(sig_def, price_data)
        assert isinstance(result, SignalValidation)
        assert 0.0 <= result.hit_rate <= 1.0
        assert result.sample_size >= 0
        assert isinstance(result.avg_return, float)
        assert result.validated_date is not None

    def test_validate_ma_cross_signal(self, validator, price_data):
        """Validate MA golden cross signal."""
        sig_def = SignalDefinition(
            name="ma_golden_cross",
            asset_pools=["a_shares"],
            signal_type="trend",
            source_analyzer="TechnicalAnalyzer",
            lookback_days=120,
            condition="MA20 crosses above MA60",
            condition_description="20-day MA crosses above 60-day MA",
            regime_filter={},
            forward_days=20,
        )
        result = validator.validate_signal(sig_def, price_data)
        assert isinstance(result, SignalValidation)
        assert result.sample_size >= 0

    def test_no_signals_returns_zero_hit_rate(self, validator):
        """If condition never fires, hit_rate = 0, sample_size = 0."""
        # Very short flat data — RSI won't drop below 30
        flat_data = pd.DataFrame({
            "open": [100.0] * 100,
            "high": [101.0] * 100,
            "low": [99.0] * 100,
            "close": [100.0] * 100,
            "volume": [1_000_000.0] * 100,
        }, index=pd.date_range(end=datetime.now(), periods=100, freq="B"))

        sig_def = SignalDefinition(
            name="test_never_fires",
            asset_pools=["a_shares"],
            signal_type="mean_reversion",
            source_analyzer="TechnicalAnalyzer",
            lookback_days=60,
            condition="RSI < 10",
            condition_description="RSI below 10 (extreme)",
            regime_filter={},
            forward_days=5,
        )
        result = validator.validate_signal(sig_def, flat_data)
        assert result.sample_size == 0
        assert result.hit_rate == 0.0

    def test_save_and_load_validation(self, validator, price_data, tmp_path):
        """Validation results can be saved to and loaded from disk."""
        sig_def = SignalDefinition(
            name="test_save",
            asset_pools=["a_shares"],
            signal_type="mean_reversion",
            source_analyzer="TechnicalAnalyzer",
            lookback_days=60,
            condition="RSI < 30",
            condition_description="RSI below 30",
            regime_filter={},
            forward_days=5,
        )
        result = validator.validate_signal(sig_def, price_data)
        validator.save_validation(sig_def.name, result, str(tmp_path))

        # Load it back
        from quant.analysis.signals.signal_registry import SignalRegistry
        registry = SignalRegistry()
        count = registry.load_validations_from_dir(str(tmp_path))
        assert count == 1
        loaded = registry.get_validation("test_save")
        assert loaded is not None
        assert abs(loaded.hit_rate - result.hit_rate) < 0.001
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_signal_validator.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement SignalValidator**

```python
# quant/analysis/signals/signal_validator.py
"""
Signal Validator — walk-forward hit-rate calculation for registered signals.

For each signal definition, replays the condition over historical price data,
records forward returns, and calculates hit-rate.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from quant.analysis.signals.signal_registry import SignalDefinition, SignalValidation
from quant.core.indicators import add_technical_indicators


class SignalValidator:
    """Validates signals by replaying conditions on historical data."""

    # Map of condition strings to evaluation functions.
    # Each function takes a DataFrame with indicators and returns a boolean Series
    # marking rows where the signal fires.
    _CONDITION_EVALUATORS = {
        "RSI < 30": lambda df: df["RSI"] < 30,
        "RSI < 10": lambda df: df["RSI"] < 10,
        "RSI > 70": lambda df: df["RSI"] > 70,
        "MA20 crosses above MA60": lambda df: (df["MA20"] > df["MA60"]) & (df["MA20"].shift(1) <= df["MA60"].shift(1)),
        "MA20 crosses below MA60": lambda df: (df["MA20"] < df["MA60"]) & (df["MA20"].shift(1) >= df["MA60"].shift(1)),
        "breakout_type == 'up' AND volume_confirmed": lambda df: (
            (df["close"] > df["Donchian_High"].shift(1)) & (df["Volume_Ratio"] > 1.5)
        ),
        "comprehensive_score > 70": None,  # requires CapitalFlowAnalyzer, not replayable from price alone
        "comprehensive_score < 30": None,
        "composite_score > 75": None,       # requires ValueInvestingAnalyzer
        "margin_5d_change_pct > 3.0": None,  # requires margin data
        "credit_spread_change_20d > 0.3": None,  # requires FRED data
        "vix > 25 AND vix_5d_change > 5": None,  # requires VIX data
        "dxy_20d_roc < -2.0": None,         # requires DXY data
    }

    def validate_signal(
        self,
        signal_def: SignalDefinition,
        price_data: pd.DataFrame,
        regime_series: Optional[pd.Series] = None,
    ) -> SignalValidation:
        """
        Validate a signal against historical price data.

        Args:
            signal_def: The signal to validate.
            price_data: OHLCV DataFrame with DatetimeIndex.
            regime_series: Optional Series of regime labels indexed by date,
                          for regime-conditional hit-rate calculation.

        Returns:
            SignalValidation with hit-rate and statistics.
        """
        evaluator = self._CONDITION_EVALUATORS.get(signal_def.condition)
        if evaluator is None:
            # Signal condition not replayable from price data alone
            return SignalValidation(
                hit_rate=0.0,
                avg_return=0.0,
                sample_size=0,
                validated_date=datetime.now().strftime("%Y-%m-%d"),
                regime_hit_rates={},
            )

        # Add technical indicators
        df = add_technical_indicators(price_data.copy())
        df = df.dropna(subset=["RSI", "MA20", "MA60"])

        if len(df) < signal_def.lookback_days:
            return SignalValidation(
                hit_rate=0.0, avg_return=0.0, sample_size=0,
                validated_date=datetime.now().strftime("%Y-%m-%d"),
                regime_hit_rates={},
            )

        # Find signal firing points
        try:
            fires = evaluator(df)
        except (KeyError, TypeError):
            return SignalValidation(
                hit_rate=0.0, avg_return=0.0, sample_size=0,
                validated_date=datetime.now().strftime("%Y-%m-%d"),
                regime_hit_rates={},
            )

        fires = fires.fillna(False)
        fire_dates = df.index[fires]

        if len(fire_dates) == 0:
            return SignalValidation(
                hit_rate=0.0, avg_return=0.0, sample_size=0,
                validated_date=datetime.now().strftime("%Y-%m-%d"),
                regime_hit_rates={},
            )

        # Calculate forward returns at each firing point
        forward_days = signal_def.forward_days
        close = df["close"]
        hits = 0
        returns = []
        regime_hits: dict = {}
        regime_totals: dict = {}

        is_bearish = signal_def.signal_type in ("mean_reversion",) and "overbought" in signal_def.name
        is_bearish = is_bearish or "death_cross" in signal_def.name or "distribution" in signal_def.name
        is_bearish = is_bearish or "widening" in signal_def.name or "spike" in signal_def.name

        for fire_date in fire_dates:
            fire_idx = df.index.get_loc(fire_date)
            target_idx = fire_idx + forward_days
            if target_idx >= len(df):
                continue

            entry_price = close.iloc[fire_idx]
            exit_price = close.iloc[target_idx]
            ret = (exit_price - entry_price) / entry_price

            returns.append(ret)

            if is_bearish:
                if ret < 0:
                    hits += 1
            else:
                if ret > 0:
                    hits += 1

            # Regime-conditional tracking
            if regime_series is not None and fire_date in regime_series.index:
                regime = regime_series.loc[fire_date]
                regime_totals[regime] = regime_totals.get(regime, 0) + 1
                if (is_bearish and ret < 0) or (not is_bearish and ret > 0):
                    regime_hits[regime] = regime_hits.get(regime, 0) + 1

        sample_size = len(returns)
        hit_rate = hits / sample_size if sample_size > 0 else 0.0
        avg_return = float(np.mean(returns)) if returns else 0.0

        regime_hit_rates = {}
        for regime, total in regime_totals.items():
            regime_hit_rates[regime] = regime_hits.get(regime, 0) / total if total > 0 else 0.0

        return SignalValidation(
            hit_rate=round(hit_rate, 4),
            avg_return=round(avg_return, 6),
            sample_size=sample_size,
            validated_date=datetime.now().strftime("%Y-%m-%d"),
            regime_hit_rates=regime_hit_rates,
        )

    def save_validation(self, signal_name: str, validation: SignalValidation, dir_path: str) -> None:
        """Save validation result to a JSON file."""
        path = Path(dir_path)
        path.mkdir(parents=True, exist_ok=True)
        data = {
            "hit_rate": validation.hit_rate,
            "avg_return": validation.avg_return,
            "sample_size": validation.sample_size,
            "validated_date": validation.validated_date,
            "regime_hit_rates": validation.regime_hit_rates,
        }
        (path / f"{signal_name}.json").write_text(json.dumps(data, indent=2))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_signal_validator.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/signals/signal_validator.py tests/unit/test_signal_validator.py
git commit -m "feat(signals): add SignalValidator with walk-forward hit-rate calculation"
```

---

### Task 5: Commodity Analyzer

**Files:**
- Create: `quant/analysis/indicators/commodity_analyzer.py`
- Create: `tests/unit/test_commodity_analyzer.py`

- [ ] **Step 1: Write tests for CommodityAnalyzer**

```python
# tests/unit/test_commodity_analyzer.py
"""Tests for CommodityAnalyzer — gold & commodity indicators."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from quant.analysis.indicators.commodity_analyzer import CommodityAnalyzer


def _make_commodity_data(n_days=200, seed=42):
    """Generate synthetic commodity price data."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq="B")
    gold = 2000 * np.exp(np.cumsum(rng.normal(0.0001, 0.008, n_days)))
    silver = gold / (75 + rng.normal(0, 3, n_days))
    copper = 4.0 * np.exp(np.cumsum(rng.normal(0.0001, 0.012, n_days)))
    crude = 75 * np.exp(np.cumsum(rng.normal(0, 0.015, n_days)))
    dxy = 105 * np.exp(np.cumsum(rng.normal(-0.0001, 0.005, n_days)))
    return {
        "gold": pd.Series(gold, index=dates, name="gold"),
        "silver": pd.Series(silver, index=dates, name="silver"),
        "copper": pd.Series(copper, index=dates, name="copper"),
        "crude_oil": pd.Series(crude, index=dates, name="crude_oil"),
        "dxy": pd.Series(dxy, index=dates, name="dxy"),
    }


class TestCommodityAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return CommodityAnalyzer()

    @pytest.fixture
    def commodity_data(self):
        return _make_commodity_data()

    def test_analyze_returns_all_indicators(self, analyzer, commodity_data):
        """analyze() returns gold_silver_ratio, copper_gold_ratio, etc."""
        result = analyzer.analyze(commodity_data)
        assert "gold_silver_ratio" in result
        assert "copper_gold_ratio" in result
        assert "gold_roc_20d" in result
        assert "crude_oil_roc_20d" in result
        assert "dxy_roc_20d" in result
        assert "analyzed_at" in result

    def test_gold_silver_ratio_reasonable(self, analyzer, commodity_data):
        result = analyzer.analyze(commodity_data)
        ratio = result["gold_silver_ratio"]
        assert 50 < ratio < 120  # reasonable range

    def test_roc_is_percentage(self, analyzer, commodity_data):
        result = analyzer.analyze(commodity_data)
        # ROC should be in percentage terms
        assert -50 < result["gold_roc_20d"] < 50
        assert -50 < result["crude_oil_roc_20d"] < 50

    def test_regime_indicators_for_gold(self, analyzer, commodity_data):
        """get_regime_indicators('gold') returns indicators the RegimeDetector needs."""
        result = analyzer.get_regime_indicators("gold", commodity_data)
        assert "gold_silver_ratio" in result
        assert "dxy_trend" in result

    def test_regime_indicators_for_commodities(self, analyzer, commodity_data):
        result = analyzer.get_regime_indicators("commodities", commodity_data)
        assert "copper_gold_ratio" in result
        assert "crude_oil_trend" in result
        assert "dxy_trend" in result

    def test_empty_data_handles_gracefully(self, analyzer):
        result = analyzer.analyze({})
        assert result.get("error") is not None or result.get("gold_silver_ratio") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_commodity_analyzer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement CommodityAnalyzer**

```python
# quant/analysis/indicators/commodity_analyzer.py
"""
Commodity Analyzer — gold, silver, copper, crude oil indicators.

Computes ratios and rate-of-change metrics used by:
- RegimeDetector (gold and commodities regime classification)
- TransmissionGraph (commodity edge monitoring)
- Dashboard (commodity pool cards)
"""
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


class CommodityAnalyzer:
    """Analyzes gold, silver, copper, crude oil, and DXY relationships."""

    def analyze(self, data: Dict[str, pd.Series]) -> Dict[str, Any]:
        """
        Compute all commodity indicators from price series.

        Args:
            data: Dict with keys 'gold', 'silver', 'copper', 'crude_oil', 'dxy'.
                  Each value is a pd.Series with DatetimeIndex.

        Returns:
            Dict with indicator values and metadata.
        """
        if not data:
            return {"error": "No data provided", "analyzed_at": datetime.now().isoformat(timespec="seconds")}

        result: Dict[str, Any] = {}

        gold = data.get("gold")
        silver = data.get("silver")
        copper = data.get("copper")
        crude = data.get("crude_oil")
        dxy = data.get("dxy")

        # Gold/Silver ratio
        if gold is not None and silver is not None and len(gold) > 0 and len(silver) > 0:
            # Align indices
            aligned = pd.DataFrame({"gold": gold, "silver": silver}).dropna()
            if len(aligned) > 0:
                result["gold_silver_ratio"] = round(float(aligned["gold"].iloc[-1] / aligned["silver"].iloc[-1]), 2)
                result["gold_silver_ratio_ma20"] = round(float((aligned["gold"] / aligned["silver"]).rolling(20).mean().iloc[-1]), 2) if len(aligned) >= 20 else None
            else:
                result["gold_silver_ratio"] = None
        else:
            result["gold_silver_ratio"] = None

        # Copper/Gold ratio (normalized to percentage change from mean)
        if copper is not None and gold is not None and len(copper) > 0 and len(gold) > 0:
            aligned = pd.DataFrame({"copper": copper, "gold": gold}).dropna()
            if len(aligned) > 20:
                ratio = aligned["copper"] / aligned["gold"]
                ratio_mean = ratio.rolling(60, min_periods=20).mean()
                result["copper_gold_ratio"] = round(float((ratio.iloc[-1] / ratio_mean.iloc[-1] - 1) * 100), 2)
            else:
                result["copper_gold_ratio"] = None
        else:
            result["copper_gold_ratio"] = None

        # Rate-of-change calculations (20-day, in %)
        for name, series in [("gold", gold), ("crude_oil", crude), ("dxy", dxy), ("copper", copper)]:
            if series is not None and len(series) >= 21:
                roc = (series.iloc[-1] / series.iloc[-21] - 1) * 100
                result[f"{name}_roc_20d"] = round(float(roc), 2)
            else:
                result[f"{name}_roc_20d"] = None

        result["analyzed_at"] = datetime.now().isoformat(timespec="seconds")
        return result

    def get_regime_indicators(self, pool: str, data: Dict[str, pd.Series]) -> Dict[str, float]:
        """
        Extract the specific indicators needed by RegimeDetector for a given pool.

        Args:
            pool: 'gold' or 'commodities'
            data: Same as analyze() input.

        Returns:
            Dict matching the keys expected by RegimeDetector config.
        """
        analysis = self.analyze(data)
        dxy_roc = analysis.get("dxy_roc_20d", 0.0) or 0.0

        if pool == "gold":
            return {
                "gold_silver_ratio": analysis.get("gold_silver_ratio", 75.0) or 75.0,
                "dxy_trend": dxy_roc,
                # real_rate_10y must be provided separately (from FRED)
            }
        elif pool == "commodities":
            return {
                "copper_gold_ratio": analysis.get("copper_gold_ratio", 0.0) or 0.0,
                "crude_oil_trend": analysis.get("crude_oil_roc_20d", 0.0) or 0.0,
                "dxy_trend": dxy_roc,
            }
        else:
            return {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_commodity_analyzer.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/indicators/commodity_analyzer.py tests/unit/test_commodity_analyzer.py
git commit -m "feat(commodity): add CommodityAnalyzer for gold and commodity indicators"
```

---

### Task 6: Transmission Graph

**Files:**
- Create: `quant/analysis/transmission/__init__.py`
- Create: `quant/analysis/transmission/transmission_graph.py`
- Create: `tests/unit/test_transmission_graph.py`

- [ ] **Step 1: Write tests for TransmissionGraph**

```python
# tests/unit/test_transmission_graph.py
"""Tests for TransmissionGraph — cross-asset causal edge monitoring."""
import pytest
from datetime import datetime
from quant.analysis.transmission.transmission_graph import (
    TransmissionEdge,
    ActiveTransmission,
    TransmissionGraph,
)


class TestTransmissionEdge:
    def test_creation(self):
        edge = TransmissionEdge(
            source="DXY",
            target="gold",
            direction="inverse",
            lag_min_days=0,
            lag_max_days=1,
            threshold=0.8,
            strength=0.72,
            source_ticker="DX-Y.NYB",
            target_ticker="GC=F",
        )
        assert edge.source == "DXY"
        assert edge.direction == "inverse"


class TestTransmissionGraph:
    @pytest.fixture
    def graph(self):
        return TransmissionGraph()

    def test_loads_edges_from_config(self, graph):
        assert len(graph.edges) > 0
        sources = [e.source for e in graph.edges]
        assert "DXY" in sources

    def test_check_triggers_with_significant_move(self, graph):
        """When source moves beyond threshold, edge triggers."""
        # Simulate DXY moving +1.5% (threshold is 0.8%)
        current_values = {"DXY": 106.5}
        previous_values = {"DXY": 105.0}  # +1.43%
        active = graph.check_triggers(current_values, previous_values)
        # Should trigger DXY -> gold and DXY -> copper edges
        triggered_targets = [a.edge.target for a in active]
        assert "gold" in triggered_targets

    def test_no_trigger_below_threshold(self, graph):
        """Small moves don't trigger."""
        current_values = {"DXY": 105.2}
        previous_values = {"DXY": 105.0}  # +0.19%
        active = graph.check_triggers(current_values, previous_values)
        dxy_triggers = [a for a in active if a.edge.source == "DXY"]
        assert len(dxy_triggers) == 0

    def test_active_transmission_has_countdown(self, graph):
        current_values = {"DXY": 107.0}
        previous_values = {"DXY": 105.0}  # +1.9%
        active = graph.check_triggers(current_values, previous_values)
        for a in active:
            if a.edge.source == "DXY":
                assert a.days_remaining >= 0
                assert a.status == "triggered"
                assert a.source_move != 0.0

    def test_update_transmission_status(self, graph):
        """After lag period, check if target moved as expected."""
        # Create an active transmission manually
        edge = graph.edges[0]  # DXY -> gold
        at = ActiveTransmission(
            edge=edge,
            triggered_at="2026-04-10T09:00:00",
            source_move=1.5,
            expected_target="gold down 0.5-1.5%",
            days_remaining=0,
            status="triggered",
        )
        # Target moved in expected direction
        target_move = -1.2  # gold down 1.2% (correct for inverse)
        updated = graph.update_status(at, target_move)
        assert updated.status == "confirmed"

    def test_update_transmission_failed(self, graph):
        edge = graph.edges[0]
        at = ActiveTransmission(
            edge=edge,
            triggered_at="2026-04-10T09:00:00",
            source_move=1.5,
            expected_target="gold down",
            days_remaining=0,
            status="triggered",
        )
        # Target moved in wrong direction
        target_move = 0.8  # gold up (wrong for inverse edge)
        updated = graph.update_status(at, target_move)
        assert updated.status == "failed"

    def test_get_edges_by_source(self, graph):
        dxy_edges = graph.get_edges_by_source("DXY")
        assert len(dxy_edges) >= 2  # DXY -> gold, DXY -> copper, DXY -> northbound

    def test_get_edges_by_target(self, graph):
        gold_edges = graph.get_edges_by_target("gold")
        assert len(gold_edges) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_transmission_graph.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TransmissionGraph**

```python
# quant/analysis/transmission/__init__.py
from .transmission_graph import TransmissionEdge, ActiveTransmission, TransmissionGraph

__all__ = ["TransmissionEdge", "ActiveTransmission", "TransmissionGraph"]
```

```python
# quant/analysis/transmission/transmission_graph.py
"""
Transmission Graph — cross-asset causal edge monitoring.

Defines directed edges between asset classes and monitors when
upstream nodes move significantly, triggering countdown alerts
for expected downstream impacts.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class TransmissionEdge:
    source: str
    target: str
    direction: str       # "inverse" | "direct"
    lag_min_days: int
    lag_max_days: int
    threshold: float     # minimum move to trigger (%)
    strength: float      # backtested correlation (0-1)
    source_ticker: Optional[str] = None
    target_ticker: Optional[str] = None


@dataclass
class ActiveTransmission:
    edge: TransmissionEdge
    triggered_at: str
    source_move: float
    expected_target: str
    days_remaining: int
    status: str          # "triggered" | "propagating" | "confirmed" | "failed"


class TransmissionGraph:
    """Manages cross-asset causal edges and monitors trigger conditions."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = str(Path(__file__).parents[3] / "config" / "transmission_edges.yaml")
        with open(config_path) as f:
            raw = yaml.safe_load(f)

        self.edges: List[TransmissionEdge] = []
        for entry in raw.get("edges", []):
            # Handle different threshold key names
            threshold = (
                entry.get("threshold_pct")
                or entry.get("threshold_pp")
                or entry.get("threshold_points")
                or 1.0
            )
            self.edges.append(TransmissionEdge(
                source=entry["source"],
                target=entry["target"],
                direction=entry["direction"],
                lag_min_days=entry["lag_min_days"],
                lag_max_days=entry["lag_max_days"],
                threshold=threshold,
                strength=entry.get("initial_strength", 0.5),
                source_ticker=entry.get("source_ticker"),
                target_ticker=entry.get("target_ticker"),
            ))

        self._active: List[ActiveTransmission] = []

    def check_triggers(
        self,
        current_values: Dict[str, float],
        previous_values: Dict[str, float],
    ) -> List[ActiveTransmission]:
        """
        Check if any source node has moved beyond its threshold.

        Args:
            current_values: {source_name: current_price_or_level}
            previous_values: {source_name: previous_price_or_level}

        Returns:
            List of newly triggered ActiveTransmission objects.
        """
        newly_triggered: List[ActiveTransmission] = []

        for edge in self.edges:
            current = current_values.get(edge.source)
            previous = previous_values.get(edge.source)
            if current is None or previous is None or previous == 0:
                continue

            pct_move = ((current - previous) / abs(previous)) * 100

            if abs(pct_move) >= edge.threshold:
                # Determine expected target direction
                if edge.direction == "inverse":
                    expected_dir = "down" if pct_move > 0 else "up"
                else:
                    expected_dir = "up" if pct_move > 0 else "down"

                at = ActiveTransmission(
                    edge=edge,
                    triggered_at=datetime.now().isoformat(timespec="seconds"),
                    source_move=round(pct_move, 2),
                    expected_target=f"{edge.target} {expected_dir}",
                    days_remaining=edge.lag_max_days,
                    status="triggered",
                )
                newly_triggered.append(at)

        self._active.extend(newly_triggered)
        return newly_triggered

    def update_status(self, transmission: ActiveTransmission, target_move: float) -> ActiveTransmission:
        """
        Update transmission status based on observed target move.

        Args:
            transmission: The active transmission to update.
            target_move: Observed target move (%).

        Returns:
            Updated ActiveTransmission with new status.
        """
        edge = transmission.edge
        if edge.direction == "inverse":
            expected_sign = -1 if transmission.source_move > 0 else 1
        else:
            expected_sign = 1 if transmission.source_move > 0 else -1

        if (target_move > 0 and expected_sign > 0) or (target_move < 0 and expected_sign < 0):
            transmission.status = "confirmed"
        else:
            transmission.status = "failed"

        return transmission

    def get_active_transmissions(self) -> List[ActiveTransmission]:
        return [a for a in self._active if a.status in ("triggered", "propagating")]

    def get_edges_by_source(self, source: str) -> List[TransmissionEdge]:
        return [e for e in self.edges if e.source == source]

    def get_edges_by_target(self, target: str) -> List[TransmissionEdge]:
        return [e for e in self.edges if e.target == target]

    def tick_day(self) -> List[ActiveTransmission]:
        """Advance all active transmissions by one day. Returns those that expired."""
        expired = []
        for at in self._active:
            if at.status in ("triggered", "propagating"):
                at.days_remaining -= 1
                if at.days_remaining <= 0:
                    at.status = "propagating"
                    expired.append(at)
        return expired
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_transmission_graph.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/transmission/ tests/unit/test_transmission_graph.py
git commit -m "feat(transmission): add TransmissionGraph with cross-asset causal edges"
```

---

### Task 7: Verdict Engine

**Files:**
- Create: `quant/analysis/verdict/__init__.py`
- Create: `quant/analysis/verdict/verdict_engine.py`
- Create: `tests/unit/test_verdict_engine.py`

- [ ] **Step 1: Write tests for VerdictEngine**

```python
# tests/unit/test_verdict_engine.py
"""Tests for VerdictEngine — synthesizes regime + signals + transmissions into verdicts."""
import pytest
from quant.analysis.verdict.verdict_engine import (
    VerdictEngine,
    PoolVerdict,
    PositionAlert,
    DashboardVerdict,
)
from quant.analysis.regime.regime_detector import RegimeState
from quant.analysis.signals.signal_registry import (
    SignalDefinition,
    SignalValidation,
    ActiveSignal,
)
from quant.analysis.transmission.transmission_graph import (
    TransmissionEdge,
    ActiveTransmission,
)


def _make_regime(pool, regime):
    return RegimeState(
        pool=pool, regime=regime, confidence=0.8,
        days_since_change=5, drivers=["test"], updated_at="2026-04-12T09:00:00",
    )


def _make_signal(name, signal_type, is_bearish=False):
    defn = SignalDefinition(
        name=name, asset_pools=["a_shares"], signal_type=signal_type,
        source_analyzer="Test", lookback_days=60,
        condition="test", condition_description="test",
        regime_filter={}, forward_days=5,
    )
    val = SignalValidation(
        hit_rate=0.68, avg_return=0.02 if not is_bearish else -0.02,
        sample_size=40, validated_date="2026-04-01", regime_hit_rates={},
    )
    return ActiveSignal(
        definition=defn, validation=val,
        fired_at="2026-04-12T09:00:00", symbol="000001.SZ",
        action="reduce" if is_bearish else "add",
        reasoning="test signal",
    )


class TestPoolVerdict:
    def test_creation(self):
        v = PoolVerdict(
            pool="a_shares", action="reduce", confidence="high",
            reasoning=["margin declining"], active_signals=[], active_transmissions=[],
            regime=_make_regime("a_shares", "risk-off"),
        )
        assert v.action == "reduce"
        assert v.pool == "a_shares"


class TestVerdictEngine:
    @pytest.fixture
    def engine(self):
        return VerdictEngine()

    def test_pool_verdict_reduce_in_risk_off_with_bearish_signals(self, engine):
        regime = _make_regime("a_shares", "risk-off")
        signals = [
            _make_signal("dist", "momentum", is_bearish=True),
            _make_signal("rsi_high", "mean_reversion", is_bearish=True),
        ]
        verdict = engine.compute_pool_verdict("a_shares", regime, signals, [])
        assert verdict.action == "reduce"

    def test_pool_verdict_add_in_risk_on_with_bullish_signals(self, engine):
        regime = _make_regime("a_shares", "risk-on")
        signals = [
            _make_signal("accum", "momentum", is_bearish=False),
            _make_signal("rsi_low", "mean_reversion", is_bearish=False),
        ]
        verdict = engine.compute_pool_verdict("a_shares", regime, signals, [])
        assert verdict.action == "add"

    def test_pool_verdict_hold_when_conflicting(self, engine):
        regime = _make_regime("a_shares", "transition")
        signals = [
            _make_signal("bull", "momentum", is_bearish=False),
            _make_signal("bear", "momentum", is_bearish=True),
        ]
        verdict = engine.compute_pool_verdict("a_shares", regime, signals, [])
        assert verdict.action == "hold"

    def test_pool_verdict_hold_when_no_signals(self, engine):
        regime = _make_regime("a_shares", "risk-on")
        verdict = engine.compute_pool_verdict("a_shares", regime, [], [])
        assert verdict.action == "hold"

    def test_dashboard_verdict_defensive_when_multiple_reduce(self, engine):
        regimes = {
            "a_shares": _make_regime("a_shares", "risk-off"),
            "us_stocks": _make_regime("us_stocks", "contraction"),
            "gold": _make_regime("gold", "bearish"),
            "commodities": _make_regime("commodities", "deflation"),
        }
        signals = {
            "a_shares": [_make_signal("bear1", "momentum", True)],
            "us_stocks": [_make_signal("bear2", "momentum", True)],
            "gold": [_make_signal("bear3", "momentum", True)],
            "commodities": [_make_signal("bear4", "momentum", True)],
        }
        result = engine.compute_dashboard_verdict(regimes, signals, {}, [])
        assert isinstance(result, DashboardVerdict)
        assert result.overall_stance in ("defensive", "cautious")

    def test_dashboard_verdict_aggressive_when_multiple_add(self, engine):
        regimes = {
            "a_shares": _make_regime("a_shares", "risk-on"),
            "us_stocks": _make_regime("us_stocks", "expansion"),
            "gold": _make_regime("gold", "bullish"),
            "commodities": _make_regime("commodities", "reflation"),
        }
        signals = {
            "a_shares": [_make_signal("bull1", "momentum", False)],
            "us_stocks": [_make_signal("bull2", "momentum", False)],
            "gold": [_make_signal("bull3", "momentum", False)],
            "commodities": [_make_signal("bull4", "momentum", False)],
        }
        result = engine.compute_dashboard_verdict(regimes, signals, {}, [])
        assert result.overall_stance in ("aggressive", "neutral")

    def test_position_alerts_sorted_by_urgency(self, engine):
        regime = _make_regime("a_shares", "risk-off")
        sell_signal = _make_signal("sell", "momentum", is_bearish=True)
        buy_signal = _make_signal("buy", "momentum", is_bearish=False)
        buy_signal.symbol = "600519.SH"

        positions = [
            {"symbol": "000001.SZ", "name": "Ping An", "pool": "a_shares"},
            {"symbol": "600519.SH", "name": "Moutai", "pool": "a_shares"},
        ]
        alerts = engine.compute_position_alerts(
            positions, {"a_shares": regime}, {"a_shares": [sell_signal, buy_signal]},
        )
        assert len(alerts) > 0
        # Sell alerts should come before buy
        actions = [a.action for a in alerts]
        if "consider selling" in actions and "add on dip" in actions:
            assert actions.index("consider selling") < actions.index("add on dip")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_verdict_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Implement VerdictEngine**

```python
# quant/analysis/verdict/__init__.py
from .verdict_engine import VerdictEngine, PoolVerdict, PositionAlert, DashboardVerdict

__all__ = ["VerdictEngine", "PoolVerdict", "PositionAlert", "DashboardVerdict"]
```

```python
# quant/analysis/verdict/verdict_engine.py
"""
Verdict Engine — synthesizes regime, signals, and transmissions into actionable verdicts.

This replaces StockRanker as the top-level decision layer. It does not compute scores;
it aggregates conclusions from Regime Detector, Signal Registry, and Transmission Graph.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from quant.analysis.regime.regime_detector import RegimeState
from quant.analysis.signals.signal_registry import ActiveSignal
from quant.analysis.transmission.transmission_graph import ActiveTransmission


# Regime labels that indicate negative environments
_NEGATIVE_REGIMES = {"risk-off", "contraction", "bearish", "deflation"}
_POSITIVE_REGIMES = {"risk-on", "expansion", "bullish", "reflation"}


@dataclass
class PoolVerdict:
    pool: str
    action: str              # "add" | "hold" | "reduce" | "avoid"
    confidence: str          # "high" | "medium" | "low"
    reasoning: List[str]
    active_signals: List[ActiveSignal]
    active_transmissions: List[ActiveTransmission]
    regime: RegimeState


@dataclass
class PositionAlert:
    symbol: str
    name: str
    pool: str
    action: str
    signals: List[ActiveSignal]
    reasoning: str


@dataclass
class DashboardVerdict:
    overall_stance: str      # "aggressive" | "neutral" | "cautious" | "defensive"
    pool_verdicts: List[PoolVerdict]
    position_alerts: List[PositionAlert]
    transmission_alerts: List[ActiveTransmission]
    updated_at: str


class VerdictEngine:
    """Aggregates regime, signals, and transmissions into per-pool action verdicts."""

    def compute_pool_verdict(
        self,
        pool: str,
        regime: RegimeState,
        signals: List[ActiveSignal],
        transmissions: List[ActiveTransmission],
    ) -> PoolVerdict:
        """Compute action verdict for one asset pool."""
        reasoning: List[str] = []

        # Count bullish vs bearish signals, weighted by hit-rate
        bullish_weight = 0.0
        bearish_weight = 0.0

        for sig in signals:
            hr = sig.validation.hit_rate if sig.validation else 0.5
            if sig.action in ("add", "watch"):
                bullish_weight += hr
            elif sig.action in ("reduce", "avoid"):
                bearish_weight += hr

        # Regime influence
        if regime.regime in _NEGATIVE_REGIMES:
            bearish_weight += 0.3 * regime.confidence
            reasoning.append(f"regime: {regime.regime} (confidence {regime.confidence:.0%})")
        elif regime.regime in _POSITIVE_REGIMES:
            bullish_weight += 0.3 * regime.confidence
            reasoning.append(f"regime: {regime.regime} (confidence {regime.confidence:.0%})")
        else:
            reasoning.append(f"regime: {regime.regime} (transition)")

        # Add signal reasoning
        for sig in signals:
            hr_str = f"{sig.validation.hit_rate:.0%}" if sig.validation else "?"
            reasoning.append(f"{sig.definition.name}: {sig.reasoning} (hit-rate {hr_str})")

        # Decision logic
        if len(signals) == 0:
            action = "hold"
            confidence = "low"
            reasoning.append("no validated signals — hold by default")
        elif bullish_weight > bearish_weight * 1.3:
            action = "add"
            confidence = "high" if bullish_weight > bearish_weight * 2 else "medium"
        elif bearish_weight > bullish_weight * 1.3:
            action = "reduce"
            confidence = "high" if bearish_weight > bullish_weight * 2 else "medium"
        else:
            action = "hold"
            confidence = "low"
            reasoning.append("conflicting signals — hold")

        return PoolVerdict(
            pool=pool,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            active_signals=signals,
            active_transmissions=transmissions,
            regime=regime,
        )

    def compute_dashboard_verdict(
        self,
        regimes: Dict[str, RegimeState],
        signals_by_pool: Dict[str, List[ActiveSignal]],
        transmissions_by_pool: Dict[str, List[ActiveTransmission]],
        all_transmissions: List[ActiveTransmission],
    ) -> DashboardVerdict:
        """Compute the full dashboard verdict across all pools."""
        pool_verdicts = []
        for pool in ("a_shares", "us_stocks", "gold", "commodities"):
            regime = regimes.get(pool)
            if regime is None:
                regime = RegimeState(
                    pool=pool, regime="unknown", confidence=0.0,
                    days_since_change=0, drivers=[], updated_at=datetime.now().isoformat(),
                )
            pool_signals = signals_by_pool.get(pool, [])
            pool_trans = transmissions_by_pool.get(pool, [])
            verdict = self.compute_pool_verdict(pool, regime, pool_signals, pool_trans)
            pool_verdicts.append(verdict)

        # Overall stance
        actions = [v.action for v in pool_verdicts]
        reduce_count = actions.count("reduce") + actions.count("avoid")
        add_count = actions.count("add")

        if reduce_count >= 3:
            overall = "defensive"
        elif reduce_count >= 2:
            overall = "cautious"
        elif add_count >= 3:
            overall = "aggressive"
        else:
            overall = "neutral"

        return DashboardVerdict(
            overall_stance=overall,
            pool_verdicts=pool_verdicts,
            position_alerts=[],  # populated by compute_position_alerts
            transmission_alerts=all_transmissions,
            updated_at=datetime.now().isoformat(timespec="seconds"),
        )

    def compute_position_alerts(
        self,
        positions: List[Dict[str, Any]],
        regimes: Dict[str, RegimeState],
        signals_by_pool: Dict[str, List[ActiveSignal]],
    ) -> List[PositionAlert]:
        """Generate per-position action alerts sorted by urgency."""
        alerts: List[PositionAlert] = []

        for pos in positions:
            symbol = pos["symbol"]
            name = pos.get("name", symbol)
            pool = pos.get("pool", "a_shares")

            # Find signals that match this symbol
            matching_signals = []
            for sig in signals_by_pool.get(pool, []):
                if sig.symbol == symbol or sig.symbol is None:
                    matching_signals.append(sig)

            if not matching_signals:
                continue

            # Determine action based on signal consensus
            bearish_count = sum(1 for s in matching_signals if s.action in ("reduce", "avoid"))
            bullish_count = sum(1 for s in matching_signals if s.action in ("add", "watch"))

            regime = regimes.get(pool)
            regime_negative = regime and regime.regime in _NEGATIVE_REGIMES

            if bearish_count > bullish_count or (bearish_count > 0 and regime_negative):
                action = "consider selling"
                reasoning_parts = [s.reasoning for s in matching_signals if s.action in ("reduce", "avoid")]
            elif bullish_count > bearish_count and not regime_negative:
                action = "add on dip"
                reasoning_parts = [s.reasoning for s in matching_signals if s.action in ("add", "watch")]
            else:
                action = "watch"
                reasoning_parts = [s.reasoning for s in matching_signals]

            reasoning = "; ".join(reasoning_parts[:3])

            alerts.append(PositionAlert(
                symbol=symbol,
                name=name,
                pool=pool,
                action=action,
                signals=matching_signals,
                reasoning=reasoning,
            ))

        # Sort: sell first, then buy, then watch
        action_priority = {"consider selling": 0, "add on dip": 1, "watch": 2, "hold": 3}
        alerts.sort(key=lambda a: action_priority.get(a.action, 9))

        return alerts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_verdict_engine.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/verdict/ tests/unit/test_verdict_engine.py
git commit -m "feat(verdict): add VerdictEngine — synthesizes regime + signals into conclusions"
```

---

### Task 8: Run full test suite and verify integration

- [ ] **Step 1: Run all new tests together**

Run: `pytest tests/unit/test_regime_detector.py tests/unit/test_signal_registry.py tests/unit/test_signal_validator.py tests/unit/test_commodity_analyzer.py tests/unit/test_transmission_graph.py tests/unit/test_verdict_engine.py -v`
Expected: All tests PASS

- [ ] **Step 2: Run full project test suite to check for regressions**

Run: `pytest tests/ -v --tb=short`
Expected: No regressions in existing tests

- [ ] **Step 3: Verify import chain works end-to-end**

Run:
```bash
python -c "
from quant.analysis.regime import RegimeDetector, RegimeState
from quant.analysis.signals import SignalRegistry, SignalValidator, SignalValidation, ActiveSignal
from quant.analysis.transmission import TransmissionGraph, ActiveTransmission
from quant.analysis.verdict import VerdictEngine, DashboardVerdict, PoolVerdict
from quant.analysis.indicators.commodity_analyzer import CommodityAnalyzer
print('All imports OK')
print(f'Registry has {len(SignalRegistry().definitions)} signals')
print(f'Graph has {len(TransmissionGraph().edges)} edges')
print(f'Detector pools: {RegimeDetector().classify_all({\"a_shares\": {}, \"us_stocks\": {}, \"gold\": {}, \"commodities\": {}}).keys()}')
"
```
Expected: Prints OK with signal/edge counts

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test: verify signal foundation modules integrate correctly"
```
