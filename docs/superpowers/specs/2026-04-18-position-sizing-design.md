# A-Share Position Sizing Tool Design

**Date:** 2026-04-18
**Status:** Approved

## Goal

A weekly-updated tool that tells the user how much of their A-share portfolio to invest, based on current market volatility. Output is a single number (0–100%) with supporting context. Includes a backtest to validate the strategy against buy-and-hold.

## Background

The existing regime scorer (ContinuousRegimeScorer) is not actionable for position sizing because it persistently outputs "expansion" in bull markets. This tool takes a different approach: instead of predicting direction, it manages risk exposure by targeting a fixed volatility level. When the market is calm, be fully invested. When the market is volatile, scale back proportionally. No ML, no training objective, no overfitting risk.

## Approach

**Volatility targeting** (rule-based):

```
position = min(100%, target_vol / realized_vol_20d)
```

- `realized_vol_20d`: annualized standard deviation of CSI 300 daily returns over the past 20 trading days = σ_daily × √252
- `target_vol`: 20% (user-defined, represents aggressive risk tolerance)
- Examples: vol=15% → 100%; vol=20% → 100%; vol=30% → 67%; vol=40% → 50%; vol=60% → 33%

## Architecture

New module: `quant/analysis/position_sizing/`

### File Map

| File | Responsibility |
|------|----------------|
| `quant/analysis/position_sizing/__init__.py` | Package export |
| `quant/analysis/position_sizing/volatility.py` | `VolatilityCalculator` — fetches CSI 300 data via tushare, computes rolling annualized vol |
| `quant/analysis/position_sizing/sizer.py` | `PositionSizer` — applies vol targeting formula, returns position size + context |
| `quant/analysis/position_sizing/backtest.py` | `PositionSizingBacktest` — weekly-rebalanced backtest vs buy-and-hold |
| `tests/fixtures/csi300_daily.csv` | Real CSI 300 daily data (one-time download, committed to repo) |
| `tests/unit/test_position_sizing.py` | Tests using real fixture data |

### Data Source

Tushare (`TUSHARE_TOKEN` from environment variable), index code `000300.SH`, via `pro.index_daily()`. Returns daily OHLCV for CSI 300.

## Component Specifications

### VolatilityCalculator

```python
class VolatilityCalculator:
    def __init__(self, window: int = 20) -> None: ...

    def fetch(self, start_date: str, end_date: str) -> pd.Series:
        """Fetch CSI 300 daily close prices from tushare. Returns DatetimeIndex series."""

    def realized_vol(self, prices: pd.Series) -> float:
        """Compute annualized vol from price series: std(daily_returns) * sqrt(252)."""

    def rolling_vol(self, prices: pd.Series) -> pd.Series:
        """Rolling 20-day annualized vol series (for backtest)."""
```

### PositionSizer

```python
@dataclass
class PositionSizing:
    position_pct: float       # 0.0 – 1.0
    realized_vol: float       # annualized, e.g. 0.274
    target_vol: float         # e.g. 0.20
    updated_date: str         # ISO date

class PositionSizer:
    def __init__(self, target_vol: float = 0.20) -> None: ...

    def size(self, prices: pd.Series) -> PositionSizing:
        """Compute current position size from price series."""
```

### PositionSizingBacktest

```python
@dataclass
class BacktestResult:
    annual_return_strategy: float
    annual_return_benchmark: float
    annual_vol_strategy: float
    annual_vol_benchmark: float
    max_drawdown_strategy: float
    max_drawdown_benchmark: float
    sharpe_strategy: float        # risk-free rate = 3%
    sharpe_benchmark: float

class PositionSizingBacktest:
    def __init__(self, target_vol: float = 0.20, risk_free: float = 0.03) -> None: ...

    def run(self, prices: pd.Series) -> BacktestResult:
        """
        Weekly rebalancing simulation.
        - Every Friday: recompute position from trailing 20-day vol
        - Strategy weekly return = position * index weekly return
        - Benchmark: 100% invested throughout
        """
```

## Data Flow

```
tushare pro.index_daily("000300.SH")
        ↓ daily close prices
VolatilityCalculator.rolling_vol()
        ↓ rolling 20-day annualized vol series
PositionSizer.size()    ← for current week
PositionSizingBacktest.run()  ← for historical validation
```

## Output Example

```
当前建议仓位: 73%
当前20日年化波动率: 27.4%  (目标: 20%)
上次更新: 2026-04-18

── 回测 2022-01 ~ 2026-04 ──────────────
              满仓        动态仓位
年化收益     +3.2%        +2.1%
年化波动率   28.6%        20.3%
最大回撤     -33.2%       -21.8%
夏普比率      0.01         0.05
```

## Testing

**Fixture:** `tests/fixtures/csi300_daily.csv` — real CSI 300 daily close from 2021-01-01 to 2026-04-01, downloaded once via tushare and committed to repo. A one-time download script `scripts/download_csi300_fixture.py` generates this file using `TUSHARE_TOKEN` from environment.

**Tests using fixture data:**

| Test | Description |
|------|-------------|
| `test_vol_high_during_2022_bear` | 2022 bear market vol ≥ 30% |
| `test_vol_low_during_2024_bull` | 2024 Q1-Q2 vol ≤ 22% (A-share had Sep rally, not uniformly calm) |
| `test_position_capped_at_100` | Vol < target → position = 100%, never > 100% |
| `test_position_below_70_in_2022` | High-vol 2022 → position < 70% |
| `test_backtest_drawdown_improvement` | Strategy max drawdown < benchmark max drawdown |
| `test_backtest_vol_near_target` | Strategy realized vol within 5pp of 20% target |
| `test_backtest_output_keys` | BacktestResult has all required fields |

## Constraints

- No ML, no training. Pure rule-based formula.
- `target_vol` is the only user-configurable parameter.
- Weekly rebalancing in backtest (Friday close).
- Risk-free rate fixed at 3% for Sharpe calculation.
- Does not cover US stocks, gold, or commodities — A-shares only in this version.
