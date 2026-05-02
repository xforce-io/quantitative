# Decision Cockpit: Web + Analysis Layer Redesign

## Context

The quantitative trading system serves a single user managing four asset pools (A-shares weekly, US stocks monthly, gold event-driven, commodities event-driven) with a mixed-frequency investment style. The system has rich indicator computation but four critical pain points:

1. **Information scattered** — data spread across pages with no unified view
2. **No conclusions** — indicators displayed but no actionable verdict
3. **Signals not trustworthy** — scores lack backtested validation
4. **Insufficient lead time** — no cross-asset transmission model, no regime-conditional leading signals

## Approach: Parallel Track

Two workstreams run concurrently:

- **Track 1 (UI):** Restructure the three-page system around asset pools and add a verdict layer
- **Track 2 (Analysis):** Build a signal validation framework, regime detector, and cross-asset transmission graph

Integration phase connects Track 2 outputs into Track 1's UI.

---

## Part 1: Analysis Layer Redesign

### 1.1 Regime Detector

New module: `quant/analysis/regime/regime_detector.py`

Classifies the current market environment for each of four asset pools:

| Asset Pool | Regimes | Primary Inputs |
|-----------|---------|----------------|
| A-shares | risk-on / risk-off / transition | margin debt trend, northbound flow, A-share breadth, China PMI |
| US stocks | expansion / contraction / transition | yield curve (2s10s), credit spreads, VIX level + term structure, ISM PMI |
| Gold | bullish / bearish / neutral | real rates (TIPS yield), DXY trend, gold/silver ratio |
| Commodities | reflation / deflation / neutral | copper/gold ratio, crude oil trend, DXY, global PMI |

Output per pool:
```python
@dataclass
class RegimeState:
    pool: str              # "a_shares" | "us_stocks" | "gold" | "commodities"
    regime: str            # e.g. "risk-off"
    confidence: float      # 0-1
    days_since_change: int # days since last regime transition
    drivers: list[str]     # human-readable reasons
    updated_at: str        # ISO timestamp
```

Implementation approach:
- Each pool has a `classify()` method that takes relevant macro data and returns a regime label
- Classification uses threshold-based rules on the primary inputs (not ML — interpretability matters)
- Thresholds are calibrated from historical data but defined in config (`config/regime_thresholds.yaml`), not hardcoded
- Regime transitions require confirmation (2+ consecutive days) to avoid whipsaw

Existing modules reused:
- `MacroLiquidityAnalyzer` provides the 12-dimension scores → feed into US stocks and commodities regime classification
- `GlobalUsdLiquidity` → feeds gold and commodities regime
- `ChinaMarketSignalAnalyzer` → feeds A-shares regime
- `LeadingIndicatorsAnalyzer` (VIX, credit spread, margin, yield curve) → feeds US stocks and A-shares regime

### 1.2 Signal Registry

New module: `quant/analysis/signals/signal_registry.py`

Every signal in the system must be registered with metadata and validation results.

```python
@dataclass
class SignalDefinition:
    name: str                    # "RSI oversold bounce"
    asset_pools: list[str]       # ["a_shares"]
    signal_type: str             # "mean_reversion" | "momentum" | "breakout" | "macro"
    source_analyzer: str         # "TechnicalAnalyzer"
    lookback_days: int           # 14
    condition: str               # machine-readable condition (e.g., "RSI < 30") — evaluated by SignalValidator against historical data
    condition_description: str   # human-readable explanation for UI display
    regime_filter: dict          # {"a_shares": ["risk-on", "transition"]} — regimes where signal is active
    
@dataclass  
class SignalValidation:
    hit_rate: float              # 0-1, from walk-forward test
    avg_return: float            # average N-day return after signal fires
    sample_size: int             # number of historical occurrences
    validated_date: str          # last validation date
    regime_hit_rates: dict       # {"risk-on": 0.72, "risk-off": 0.38}
    
@dataclass
class ActiveSignal:
    definition: SignalDefinition
    validation: SignalValidation
    fired_at: str                # when the signal triggered
    symbol: str | None           # specific stock, or None for macro signals
    action: str                  # "add" | "reduce" | "watch" | "avoid"
    reasoning: str               # human-readable explanation
```

Signal registration: signals are defined in `config/signals.yaml` with their conditions and regime filters. The registry loads these at startup and matches them against incoming data.

Minimum threshold: signals with `hit_rate < 0.55` are suppressed (not shown to user). This threshold is configurable.

Initial signal catalog (migrated from existing analyzers):

| Signal | Source | Asset Pool | Type |
|--------|--------|-----------|------|
| RSI oversold bounce | TechnicalAnalyzer | A-shares | mean_reversion |
| RSI overbought warning | TechnicalAnalyzer | A-shares | mean_reversion |
| Box breakout | BoxBreakoutAnalyzer | A-shares | breakout |
| Institutional accumulation | CapitalFlowAnalyzer | A-shares | momentum |
| Institutional distribution | CapitalFlowAnalyzer | A-shares | momentum |
| Volume-price divergence | TechnicalAnalyzer | A-shares | reversal |
| MA golden/death cross | TechnicalAnalyzer | A-shares, US stocks | trend |
| Value convergence | ValueInvestingAnalyzer | US stocks | value |
| Margin debt acceleration | LeadingIndicatorsAnalyzer | A-shares | macro |
| Credit spread widening | LeadingIndicatorsAnalyzer | US stocks | macro |
| VIX spike | LeadingIndicatorsAnalyzer | US stocks, gold | macro |
| DXY trend reversal | GlobalUsdLiquidity | gold, commodities | macro |

### 1.3 Signal Validator

New module: `quant/analysis/signals/signal_validator.py`

Walk-forward validation for each registered signal:

1. Load historical price data for the signal's asset pool (3-5 years)
2. Replay the signal condition over the historical period
3. For each signal firing, record the forward return at +1d, +5d, +20d
4. Calculate hit-rate = % of firings where forward return has correct sign
5. Calculate regime-conditional hit-rates by joining with historical regime classification
6. Store results in `data/signal_validations/` as JSON files (one per signal)

Validation runs:
- Full validation on first run (slow, ~minutes per signal depending on data availability)
- Incremental validation weekly (append new data points)
- Results cached to disk, loaded at startup

Data requirements:
- A-share signals: Tushare daily data (already available)
- US stock signals: Yahoo Finance daily data (already available)
- Gold/commodity signals: Yahoo Finance (GLD, GC=F, CL=F, HG=F)
- Macro signals: FRED data (already available via `fred_client.py`)

### 1.4 Transmission Graph

New module: `quant/analysis/transmission/transmission_graph.py`

A directed graph of cross-asset causal relationships. Edges are defined in config, monitored in real-time.

```python
@dataclass
class TransmissionEdge:
    source: str           # "DXY"
    target: str           # "gold"
    direction: str        # "inverse" | "direct"
    lag_range: tuple      # (0, 2) — days
    strength: float       # correlation strength from backtest (0-1)
    threshold: float      # minimum source move to trigger (e.g., 1.0%)
    
@dataclass
class ActiveTransmission:
    edge: TransmissionEdge
    triggered_at: str     # when source moved beyond threshold
    source_move: float    # actual source movement (e.g., +1.2%)
    expected_target: str  # "gold down 0.5-1.5%"
    days_remaining: int   # countdown within lag range
    status: str           # "triggered" | "propagating" | "confirmed" | "failed"
```

Initial edge definitions (`config/transmission_edges.yaml`):

| Source | Target | Direction | Lag (days) | Threshold |
|--------|--------|-----------|-----------|-----------|
| DXY | Gold | inverse | 0-1 | 0.8% |
| DXY | Copper | inverse | 1-3 | 1.0% |
| DXY | A-share northbound flow | inverse | 1-3 | 1.0% |
| Gold | A-share gold sector | direct | 0-2 | 1.5% |
| Credit spread | US risk assets | inverse | 3-7 | 0.15pp |
| VIX | All risk assets | inverse | 0-1 | 3 points |
| Yield curve (2s10s) | Recession probability | inverse | 30-90 | 0.25pp |
| Fed balance sheet | USD liquidity | direct | 5-15 | 1.0% |
| Margin debt (A-share) | A-share sentiment | direct | 1-3 | 3.0% |
| Copper/gold ratio | Commodities regime | direct | 0-5 | 2.0% |
| Crude oil | Inflation expectations | direct | 5-10 | 5.0% |

Edge strength is backtested: measure lag correlation over 3-5 years of historical data, store in validation files alongside signal validations.

Monitoring loop:
1. Each morning (or on page load), fetch latest values for all source nodes
2. Compare against previous day: if move exceeds threshold, mark edge as "triggered"
3. Start countdown timer based on lag range
4. When countdown reaches 0, check if target moved as expected → "confirmed" or "failed"
5. Track confirmation rate over time to update edge strength

### 1.5 Verdict Engine

New module: `quant/analysis/verdict/verdict_engine.py`

Replaces `StockRanker` as the top-level decision layer. Does not compute scores — it synthesizes conclusions from the three layers below it.

```python
@dataclass
class PoolVerdict:
    pool: str              # "a_shares"
    action: str            # "add" | "hold" | "reduce" | "avoid"
    confidence: str        # "high" | "medium" | "low"
    reasoning: list[str]   # human-readable bullet points
    active_signals: list[ActiveSignal]
    active_transmissions: list[ActiveTransmission]
    regime: RegimeState

@dataclass
class PositionAlert:
    symbol: str
    name: str
    pool: str
    action: str            # "consider selling" | "add on dip" | "watch" | "hold"
    signals: list[ActiveSignal]
    reasoning: str

@dataclass
class DashboardVerdict:
    overall_stance: str    # "aggressive" | "neutral" | "cautious" | "defensive"
    pool_verdicts: list[PoolVerdict]
    position_alerts: list[PositionAlert]
    transmission_alerts: list[ActiveTransmission]
    updated_at: str
```

Decision rules (initial heuristic, upgradeable):

1. **Per-pool action:**
   - Count bullish vs bearish active signals (weighted by hit-rate)
   - If regime = risk-off AND net bearish → "reduce"
   - If regime = risk-on AND net bullish → "add"
   - If signals conflict OR regime = transition → "hold"
   - If no validated signals fire → "hold" (no action without evidence)

2. **Overall stance:**
   - Count pool actions: if 3+ pools say "reduce" → "defensive"
   - If 3+ pools say "add" → "aggressive"
   - Otherwise → "neutral" or "cautious" based on mix

3. **Position alerts:**
   - For each watchlist position, check active signals that apply to its symbol
   - Combine with pool regime to generate action suggestion
   - Sort by urgency (sell signals first, then buy, then hold)

### 1.6 Gold & Commodity Coverage

New module: `quant/analysis/indicators/commodity_analyzer.py`

Extends the system to cover gold and commodities asset pools.

Data sources (via Yahoo Finance, already available):
- Gold: GLD (ETF), GC=F (futures)
- Silver: SLV, SI=F
- Copper: HG=F
- Crude oil: CL=F, USO
- Commodity index: DJP, GSG

Indicators:
- Gold/silver ratio (risk appetite proxy)
- Copper/gold ratio (already in MacroLiquidityAnalyzer, reuse)
- Real rates (TIPS yield from FRED, inverse gold driver)
- DXY correlation (already tracked)
- Gold ETF flows (if available from data provider)

This analyzer feeds into the Regime Detector (gold/commodities regime classification) and provides signals for the Signal Registry.

### 1.7 What Happens to StockRanker

`StockRanker` is not deleted. It is **demoted** from decision layer to signal source:

- Its composite score becomes one signal in the Signal Registry: "Ranker high score" (composite > 75)
- Its per-factor scores feed into individual signals (e.g., "institutional accumulation" from money_flow_score > 70)
- The hardcoded weight profiles are no longer used for final decisions — the Verdict Engine handles that
- `StockRanker` remains useful for Scanner's batch screening (score 1000 stocks quickly)

### 1.8 Data Provider Consolidation

Both data layers (`quant/data_providers/` old and `quant/data/` new) continue to exist, but:
- New modules (Regime Detector, Transmission Graph, Commodity Analyzer) use the new `quant/data/` layer only
- No migration of existing analyzers needed (they work fine with old layer)
- Over time, as analyzers are touched for other reasons, migrate them to new layer

---

## Part 2: Web Layer Redesign

### 2.1 Organizing Principle: Asset Pools

All three pages use the same four asset pools as their primary organizing dimension:

| Pool | Color | Emoji | Frequency |
|------|-------|-------|-----------|
| A-shares | red (#e74c3c) | CN flag | weekly |
| US stocks | blue (#4facfe) | US flag | monthly |
| Gold | yellow (#f1c40f) | gold medal | event-driven |
| Commodities | orange (#e67e22) | oil drum | event-driven |

This replaces the current organizing dimensions (stock/industry tabs, scan mode dropdown).

### 2.2 Dashboard Redesign

The Dashboard becomes the "open and know what to do" page. Four sections top to bottom:

**Section 1: Verdict Bar**
- Overall stance badge (aggressive/neutral/cautious/defensive) with color
- One line per asset pool: action + short reasoning
- Data freshness timestamp + confidence note ("based on N validated signals, avg hit-rate X%")

**Section 2: Transmission Chain Alerts**
- Active cross-asset transmission chains only (hide dormant ones)
- Each chain shows: source move → expected target impact → countdown → hit-rate
- Sorted by urgency (shortest remaining lag first)

**Section 3: Asset Pool Cards**
- 2x2 grid, one card per pool
- Each card shows: regime badge, top leading signals (with direction arrows), watchlist alert count
- Click to expand: shows all active signals for that pool with details

**Section 4: Position Alerts**
- Sorted by urgency (sell first, then buy opportunities, then holds)
- Each alert: symbol, action suggestion, reasoning, signal hit-rate
- Click to expand: detailed chart and signal evidence

**Removed from Dashboard:**
- Raw leading indicator numbers (VIX: 18.2) — replaced by interpreted signals ("VIX normal, no stress")
- Traffic light display — replaced by regime badges with actual meaning
- Separate macro bar — folded into Verdict Bar and Pool Cards

### 2.3 Watchlist Redesign

**Tabs by asset pool** (replacing stock/industry tabs):
- Each tab shows positions in that pool
- Tab header includes regime badge: "A-Shares (risk-off)"

**Per-position display:**
- Alert emoji + name + symbol + action suggestion
- One-line signal summary with hit-rate
- Expandable detail: charts (Plotly only), full signal list, historical performance

**Watchlist management (in-page):**
- "Add" button opens a search/select dialog (no JSON editing)
- "Remove" button on each position
- Positions auto-classified into asset pool by symbol format (`.SZ/.SH` → A-shares, etc.)
- `config/watchlist.yaml` format extended to support pool grouping:

```yaml
a_shares:
  - symbol: "000001.SZ"
    name: "Ping An Bank"
  - symbol: "600519.SH"
    name: "Kweichow Moutai"
us_stocks:
  - symbol: "AAPL"
    name: "Apple"
gold:
  - symbol: "GLD"
    name: "SPDR Gold Trust"
commodities:
  - symbol: "USO"
    name: "US Oil Fund"
```

**Industry monitoring** is kept as a sub-section within the A-shares tab (it's only relevant for A-shares).

### 2.4 Scanner Redesign

**Tabs by asset pool** (replacing sidebar dropdown):
- A-Share Scan: box breakout + momentum + capital flow signals
- US Value Scan: five-factor screening
- Gold/Commodity Scan: new, based on commodity analyzer signals

**Regime-aware scanning:**
- Each tab shows current regime badge at the top
- In risk-off regime, A-share scan biases toward defensive names
- Scanner only shows results with signal hit-rate > 55%

**Closed loop:**
- Each result row has a "+ Add to Watchlist" button
- Clicking adds to the appropriate pool in watchlist config
- Confirmation toast: "Added Stock X to A-shares watchlist"

**Remove "Macro Liquidity" scan mode** — this information now lives in Dashboard's Verdict Bar and Pool Cards. No need for a separate scan mode.

**File splitting:**
- Current 1332-line `Scanner.py` split into per-tab modules:
  - `web/scanner/ashare_scan.py`
  - `web/scanner/us_value_scan.py`
  - `web/scanner/commodity_scan.py`
- `Scanner.py` becomes a thin shell that imports and renders tabs

### 2.5 Cross-Cutting UI Changes

**Charts: Plotly only**
- Remove all matplotlib chart functions from `components.py`
- Migrate `plot_trend_chart()` and `plot_technical_chart()` to Plotly equivalents
- Consistent dark theme via `apply_plotly_theme()`

**Data freshness:**
- Every data-fetching section shows "Updated: HH:MM" timestamp
- Manual refresh button per section (clears `st.cache_data` for that function)
- Stale data warning if cache is > 2x TTL (e.g., API was unreachable)

**Component cleanup:**
- Remove duplicate chart functions (matplotlib + Plotly versions)
- Remove `components_ic_report.py` (already deleted but verify)
- Extract `_alert_level()` to shared utility (used by Dashboard + Watchlist)

---

## Part 3: Implementation Sequencing (Parallel Tracks)

### Track 1: Immediate UI Wins (Week 1-2)

Focus: make the system usable as a decision tool NOW, using heuristic rules before backtest framework is ready.

1. Extend watchlist config to support asset pool grouping + gold/commodities
2. Add Verdict Bar to Dashboard (heuristic rules initially)
3. Add gold/commodities to Dashboard macro section
4. Restructure Watchlist tabs by asset pool
5. Add "+ Add to Watchlist" to Scanner results
6. Add data freshness timestamps
7. Kill matplotlib, unify to Plotly
8. Split Scanner.py into per-tab modules

### Track 2: Signal Foundation (Week 1-3)

Focus: build the analytical backbone that makes verdicts trustworthy.

1. Build Regime Detector with config-driven thresholds
2. Build Signal Registry + signal definitions in YAML
3. Build Signal Validator (walk-forward hit-rate)
4. Build Transmission Graph with edge definitions
5. Build Commodity Analyzer (gold + commodities coverage)
6. Run initial validation on all signals, store results

### Integration (Week 3-4)

1. Build Verdict Engine (connects Regime + Signals + Transmission)
2. Replace Dashboard heuristic verdict with Verdict Engine output
3. Add hit-rate badges to all signal displays
4. Add transmission chain visualization to Dashboard
5. Make Scanner regime-aware (filter signals by regime)

### What's NOT in Scope

- Mobile responsive design (personal tool, desktop only)
- Multi-user support / authentication
- Real-time streaming (daily/weekly frequency is sufficient)
- ML-based regime detection (rule-based is more interpretable)
- Automated trading / order execution
- Migration of old data provider layer (works fine, migrate opportunistically)
- AI Panel changes (keep as-is, may benefit from Verdict Engine context later)

---

## File Structure Summary

### New Files

```
quant/analysis/regime/
  __init__.py
  regime_detector.py           # RegimeDetector class
  
quant/analysis/signals/
  __init__.py
  signal_registry.py           # SignalRegistry, SignalDefinition, ActiveSignal
  signal_validator.py          # Walk-forward validation engine

quant/analysis/transmission/
  __init__.py
  transmission_graph.py        # TransmissionGraph, TransmissionEdge, ActiveTransmission

quant/analysis/verdict/
  __init__.py
  verdict_engine.py            # VerdictEngine, PoolVerdict, DashboardVerdict

quant/analysis/indicators/
  commodity_analyzer.py        # Gold & commodity analysis (NEW)

config/
  regime_thresholds.yaml       # Regime classification thresholds
  signals.yaml                 # Signal definitions catalog
  transmission_edges.yaml      # Cross-asset causal edges
  watchlist.yaml               # Extended watchlist (replaces watchlist.json)

data/signal_validations/       # Cached validation results (gitignored)

web/scanner/
  __init__.py
  ashare_scan.py               # A-share scanning tab
  us_value_scan.py             # US value scanning tab  
  commodity_scan.py            # Gold & commodity scanning tab
```

### Modified Files

```
web/pages/1_📊_Dashboard.py    # Major rewrite: verdict bar + transmission + pool cards
web/pages/2_👀_Watchlist.py    # Restructure tabs by pool, add in-page management
web/pages/3_🔍_Scanner.py     # Thin shell importing per-tab modules
web/components.py              # Remove matplotlib functions, add shared utilities
web/data_service.py            # Add verdict/regime/transmission data fetchers
web/utils.py                   # Extended for new watchlist.yaml format
web/Home.py                    # Update descriptions to match new system
```

### Unchanged (reused as-is)

```
quant/analysis/indicators/technical_analyzer.py
quant/analysis/indicators/capital_flow_analyzer.py
quant/analysis/indicators/short_term_momentum.py
quant/analysis/indicators/box_breakout_analyzer.py
quant/analysis/indicators/macro_liquidity_analyzer.py
quant/analysis/indicators/global_usd_liquidity.py
quant/analysis/indicators/leading_indicators.py
quant/analysis/indicators/china_market_signal_analyzer.py
quant/analysis/valuation/price_valuation.py
quant/analysis/screener/ranker.py  (demoted from decision layer to signal source)
quant/data/ (new data layer)
quant/data_providers/ (old data layer, no migration needed)
```
