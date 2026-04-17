#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RegimeValidator — walk-forward accuracy measurement for RegimeDetector.

For each evaluation date, reconstructs the indicator snapshot from historical
time-series data, classifies the regime via RegimeDetector, then measures
the forward return of a benchmark asset to determine whether the regime
call was directionally correct.

Output structure mirrors SignalValidation so results can be consumed by
VerdictEngine to weight regime confidence by empirical accuracy.

Currently supports: us_stocks pool (VIX, credit spread, yield curve from
FRED + Yahoo).  Other pools can be added by implementing their
``_fetch_*_history`` methods.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from quant.analysis.regime.regime_detector import RegimeDetector, RegimeState
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RegimeCall:
    """A single regime classification at a point in time."""

    date: str                   # ISO date
    regime: str                 # e.g. "expansion", "contraction", "transition"
    confidence: float           # 0-1
    indicators: Dict[str, float]
    drivers: List[str]


@dataclass
class RegimeValidation:
    """Accuracy statistics for a pool's regime classifications."""

    pool: str
    benchmark: str              # e.g. "SPY"
    forward_days: int
    total_calls: int
    hit_rate: float             # fraction of directionally correct calls
    avg_return_positive: float  # avg forward return when regime is positive
    avg_return_negative: float  # avg forward return when regime is negative
    avg_return_neutral: float   # avg forward return when regime is neutral
    regime_counts: Dict[str, int]         # {"expansion": 40, ...}
    regime_hit_rates: Dict[str, float]    # {"expansion": 0.72, ...}
    regime_avg_returns: Dict[str, float]  # {"expansion": 0.015, ...}
    validated_date: str
    calls: List[RegimeCall] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Historical data fetchers
# ---------------------------------------------------------------------------


def _fetch_vix_history(start: datetime, end: datetime) -> pd.Series:
    """Fetch VIX daily close as a time series."""
    df = yf.download("^VIX", start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"), progress=False)
    if df.empty:
        raise ValueError("VIX data is empty")
    close = df["Close"].squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.dropna()


def _fetch_credit_spread_history(start: datetime, end: datetime) -> pd.Series:
    """Fetch HY-BBB credit spread from FRED."""
    from fredapi import Fred
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise ValueError("FRED_API_KEY required")
    fred = Fred(api_key=api_key)
    hy = fred.get_series("BAMLH0A0HYM2", observation_start=start,
                         observation_end=end)
    bbb = fred.get_series("BAMLC0A4CBBB", observation_start=start,
                          observation_end=end)
    spread = (hy - bbb).dropna()
    if spread.empty:
        raise ValueError("Credit spread data is empty")
    return spread


def _fetch_yield_curve_history(start: datetime, end: datetime) -> pd.Series:
    """Fetch 2s10s yield curve spread from FRED (T10Y2Y series)."""
    from fredapi import Fred
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise ValueError("FRED_API_KEY required")
    fred = Fred(api_key=api_key)
    series = fred.get_series("T10Y2Y", observation_start=start,
                             observation_end=end)
    if series is None or series.empty:
        raise ValueError("Yield curve data is empty")
    return series.dropna()


def _fetch_benchmark_history(ticker: str, start: datetime,
                             end: datetime) -> pd.Series:
    """Fetch benchmark daily close prices."""
    df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"), progress=False)
    if df.empty:
        raise ValueError(f"{ticker} data is empty")
    close = df["Close"].squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.dropna()


# ---------------------------------------------------------------------------
# RegimeValidator
# ---------------------------------------------------------------------------


class RegimeValidator:
    """Walk-forward validator for RegimeDetector classifications."""

    def __init__(self, detector: Optional[RegimeDetector] = None) -> None:
        self._detector = detector or RegimeDetector()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_us_stocks(
        self,
        lookback_years: int = 2,
        forward_days: int = 10,
        eval_frequency: str = "weekly",
        benchmark: str = "SPY",
    ) -> RegimeValidation:
        """
        Walk-forward validation of us_stocks regime classifications.

        Parameters
        ----------
        lookback_years : int
            How many years of history to evaluate.
        forward_days : int
            Trading days to measure forward return after each regime call.
        eval_frequency : str
            "weekly" or "monthly" — how often to sample regime calls.
        benchmark : str
            Ticker to measure forward returns against (default SPY).

        Returns
        -------
        RegimeValidation with accuracy statistics.
        """
        end = datetime.now()
        # Extra buffer for forward return measurement
        start = end - timedelta(days=lookback_years * 365 + 60)

        logger.info(
            f"Fetching historical data for us_stocks validation "
            f"({lookback_years} years, {eval_frequency} frequency, "
            f"{forward_days}-day forward)..."
        )

        # Fetch all time series once
        vix = _fetch_vix_history(start, end)
        credit_spread = _fetch_credit_spread_history(start, end)
        yield_curve = _fetch_yield_curve_history(start, end)
        benchmark_prices = _fetch_benchmark_history(benchmark, start, end)

        logger.info(
            f"Data fetched — VIX: {len(vix)} pts, credit_spread: "
            f"{len(credit_spread)} pts, yield_curve: {len(yield_curve)} pts, "
            f"{benchmark}: {len(benchmark_prices)} pts"
        )

        # Build evaluation dates
        eval_start = end - timedelta(days=lookback_years * 365)
        eval_dates = self._build_eval_dates(
            benchmark_prices.index, eval_start, end, eval_frequency,
        )

        logger.info(f"Evaluating {len(eval_dates)} regime calls...")

        # Classify regime at each evaluation date
        calls: List[RegimeCall] = []
        forward_returns: List[Optional[float]] = []

        for eval_date in eval_dates:
            # Snapshot indicators as of eval_date
            indicators = self._snapshot_indicators(
                eval_date, vix, credit_spread, yield_curve,
            )

            if not indicators:
                continue

            # Classify
            state = self._detector.classify_pool("us_stocks", indicators)

            calls.append(RegimeCall(
                date=pd.Timestamp(eval_date).strftime("%Y-%m-%d"),
                regime=state.regime,
                confidence=state.confidence,
                indicators=indicators,
                drivers=state.drivers,
            ))

            # Measure forward return
            fwd_ret = self._forward_return(
                benchmark_prices, eval_date, forward_days,
            )
            forward_returns.append(fwd_ret)

        # Compute statistics
        return self._compute_statistics(
            pool="us_stocks",
            benchmark=benchmark,
            forward_days=forward_days,
            calls=calls,
            forward_returns=forward_returns,
        )

    def validate_us_stocks_momentum(
        self,
        lookback_years: int = 2,
        forward_days: int = 10,
        eval_frequency: str = "weekly",
        benchmark: str = "SPY",
        momentum_window: int = 20,
    ) -> RegimeValidation:
        """
        Walk-forward validation using momentum-based regime classification.

        Instead of absolute indicator levels (VIX > 30 → contraction), uses
        rate-of-change:
          - VIX rising rapidly + credit spread widening → contraction
          - VIX falling + credit spread narrowing → expansion
          - Mixed signals → transition

        This tests the hypothesis that *direction of change* in risk indicators
        is more predictive than their absolute level.
        """
        end = datetime.now()
        start = end - timedelta(days=lookback_years * 365 + 60 + momentum_window * 2)

        logger.info(
            f"Fetching data for momentum-based validation "
            f"({lookback_years}y, {eval_frequency}, {forward_days}d fwd, "
            f"{momentum_window}d momentum)..."
        )

        vix = _fetch_vix_history(start, end)
        credit_spread = _fetch_credit_spread_history(start, end)
        yield_curve = _fetch_yield_curve_history(start, end)
        benchmark_prices = _fetch_benchmark_history(benchmark, start, end)

        eval_start = end - timedelta(days=lookback_years * 365)
        eval_dates = self._build_eval_dates(
            benchmark_prices.index, eval_start, end, eval_frequency,
        )

        logger.info(f"Evaluating {len(eval_dates)} momentum regime calls...")

        calls: List[RegimeCall] = []
        forward_returns: List[Optional[float]] = []

        for eval_date in eval_dates:
            regime, confidence, indicators, drivers = self._momentum_classify(
                eval_date, vix, credit_spread, yield_curve, momentum_window,
            )

            if regime is None:
                continue

            calls.append(RegimeCall(
                date=pd.Timestamp(eval_date).strftime("%Y-%m-%d"),
                regime=regime,
                confidence=confidence,
                indicators=indicators,
                drivers=drivers,
            ))

            fwd_ret = self._forward_return(
                benchmark_prices, eval_date, forward_days,
            )
            forward_returns.append(fwd_ret)

        return self._compute_statistics(
            pool="us_stocks",
            benchmark=benchmark,
            forward_days=forward_days,
            calls=calls,
            forward_returns=forward_returns,
        )

    def validate_us_stocks_combined(
        self,
        lookback_years: int = 2,
        forward_days: int = 10,
        eval_frequency: str = "weekly",
        benchmark: str = "SPY",
        momentum_window: int = 20,
    ) -> RegimeValidation:
        """
        Walk-forward validation using combined macro momentum + price technicals.

        Adds benchmark's own technical signals to the momentum-based macro
        indicators:
          - Price vs 200-day MA (trend)
          - 50/200 MA relationship (golden/death cross)
          - RSI momentum zone

        Technical signals get higher weight (2x) because they directly reflect
        price action rather than indirect macro proxies.

        Optimal parameters (from grid search over 5yr data):
          tech_weight=2, momentum_window=20, vix_roc_th=15%,
          cs_change_th=0.10, yc_change_th=0.10, rsi_mean_reversion=off
        """
        end = datetime.now()
        start = end - timedelta(days=lookback_years * 365 + 300)

        logger.info(
            f"Fetching data for combined validation "
            f"({lookback_years}y, {eval_frequency}, {forward_days}d fwd)..."
        )

        vix = _fetch_vix_history(start, end)
        credit_spread = _fetch_credit_spread_history(start, end)
        yield_curve = _fetch_yield_curve_history(start, end)
        benchmark_prices = _fetch_benchmark_history(benchmark, start, end)

        eval_start = end - timedelta(days=lookback_years * 365)
        eval_dates = self._build_eval_dates(
            benchmark_prices.index, eval_start, end, eval_frequency,
        )

        logger.info(f"Evaluating {len(eval_dates)} combined regime calls...")

        calls: List[RegimeCall] = []
        forward_returns: List[Optional[float]] = []

        for eval_date in eval_dates:
            regime, confidence, indicators, drivers = self._combined_classify(
                eval_date, vix, credit_spread, yield_curve,
                benchmark_prices, momentum_window,
            )

            if regime is None:
                continue

            calls.append(RegimeCall(
                date=pd.Timestamp(eval_date).strftime("%Y-%m-%d"),
                regime=regime,
                confidence=confidence,
                indicators=indicators,
                drivers=drivers,
            ))

            fwd_ret = self._forward_return(
                benchmark_prices, eval_date, forward_days,
            )
            forward_returns.append(fwd_ret)

        return self._compute_statistics(
            pool="us_stocks",
            benchmark=benchmark,
            forward_days=forward_days,
            calls=calls,
            forward_returns=forward_returns,
        )

    def validate_us_stocks_continuous(
        self,
        lookback_years: int = 2,
        forward_days: int = 10,
        eval_frequency: str = "weekly",
        benchmark: str = "SPY",
        optimize_weights: bool = False,
        weights_path: Optional[str] = None,
    ) -> RegimeValidation:
        """
        Walk-forward validation using ContinuousRegimeScorer.

        Parameters
        ----------
        lookback_years : int
            How many years of history to evaluate.
        forward_days : int
            Trading days to measure forward return.
        eval_frequency : str
            "weekly" or "monthly".
        benchmark : str
            Ticker for forward returns (default SPY).
        optimize_weights : bool
            If True, run grid search to find optimal weights before validation.
        weights_path : str, optional
            Path to save/load optimized weights.
        """
        from quant.analysis.regime.continuous_scorer import ContinuousRegimeScorer
        from quant.analysis.regime.feature_pipeline import FeaturePipeline
        from quant.analysis.regime.scoring_backend import WeightedLinearBackend

        end = datetime.now()
        start = end - timedelta(days=lookback_years * 365 + 300)

        logger.info(
            f"Fetching data for continuous validation "
            f"({lookback_years}y, {eval_frequency}, {forward_days}d fwd)..."
        )

        vix = _fetch_vix_history(start, end)
        credit_spread = _fetch_credit_spread_history(start, end)
        yield_curve = _fetch_yield_curve_history(start, end)
        benchmark_prices = _fetch_benchmark_history(benchmark, start, end)

        all_series = {
            "vix": vix,
            "credit_spread": credit_spread,
            "yield_curve": yield_curve,
            "benchmark": benchmark_prices,
        }

        eval_start = end - timedelta(days=lookback_years * 365)
        eval_dates = self._build_eval_dates(
            benchmark_prices.index, eval_start, end, eval_frequency,
        )

        pipeline = FeaturePipeline(pool="us_stocks")

        if optimize_weights:
            logger.info("Running grid search for optimal weights...")
            feature_rows = []
            fwd_rets_for_fit = []

            for ed in eval_dates:
                idx = benchmark_prices.index.get_indexer([ed], method="ffill")[0]
                if idx < 0:
                    continue
                features = pipeline.compute(all_series, eval_idx=idx)
                if not features:
                    continue
                fwd_ret = self._forward_return(benchmark_prices, ed, forward_days)
                if fwd_ret is None:
                    continue
                feature_rows.append([features[n] for n in pipeline.feature_names])
                fwd_rets_for_fit.append(fwd_ret)

            feature_matrix = np.array(feature_rows)
            fwd_array = np.array(fwd_rets_for_fit)

            backend = WeightedLinearBackend(
                dict.fromkeys(pipeline.feature_names, 1.0)
            )
            backend.fit(
                feature_names=pipeline.feature_names,
                feature_matrix=feature_matrix,
                forward_returns=fwd_array,
                save_path=weights_path,
            )
            scorer = ContinuousRegimeScorer(
                pool="us_stocks", backend=backend, pipeline=pipeline,
            )
        else:
            scorer = ContinuousRegimeScorer(pool="us_stocks", pipeline=pipeline)

        logger.info(f"Evaluating {len(eval_dates)} continuous regime calls...")

        calls: List[RegimeCall] = []
        forward_returns: List[Optional[float]] = []

        for ed in eval_dates:
            idx = benchmark_prices.index.get_indexer([ed], method="ffill")[0]
            if idx < 0:
                continue
            state = scorer.classify(all_series, eval_idx=idx)
            if state.regime == "transition" and state.confidence == 0.0:
                continue

            calls.append(RegimeCall(
                date=pd.Timestamp(ed).strftime("%Y-%m-%d"),
                regime=state.regime,
                confidence=state.confidence,
                indicators={},
                drivers=state.drivers,
            ))
            forward_returns.append(
                self._forward_return(benchmark_prices, ed, forward_days)
            )

        return self._compute_statistics(
            pool="us_stocks",
            benchmark=benchmark,
            forward_days=forward_days,
            calls=calls,
            forward_returns=forward_returns,
        )

    @staticmethod
    def _momentum_classify(
        eval_date: pd.Timestamp,
        vix: pd.Series,
        credit_spread: pd.Series,
        yield_curve: pd.Series,
        window: int,
    ) -> Tuple[Optional[str], float, Dict[str, float], List[str]]:
        """
        Classify regime based on indicator momentum (rate of change).

        Voting logic:
          - VIX ROC > +15%   → bearish vote (fear rising)
          - VIX ROC < -15%   → bullish vote (fear subsiding)
          - CS change > +0.15 → bearish vote (credit tightening)
          - CS change < -0.15 → bullish vote (credit easing)
          - YC change > +0.10 → bullish vote (curve steepening = growth)
          - YC change < -0.10 → bearish vote (curve flattening = recession risk)

        Returns (regime, confidence, indicators_dict, drivers_list) or
        (None, ...) if insufficient data.
        """
        ed = pd.Timestamp(eval_date)
        indicators: Dict[str, float] = {}
        drivers: List[str] = []

        # VIX rate of change
        vix_avail = vix[vix.index <= ed]
        if len(vix_avail) < window + 1:
            return None, 0.0, {}, []
        vix_now = float(vix_avail.iloc[-1])
        vix_then = float(vix_avail.iloc[-window - 1])
        vix_roc = (vix_now / vix_then - 1) * 100 if vix_then != 0 else 0
        indicators["vix"] = vix_now
        indicators["vix_roc"] = round(vix_roc, 1)

        # Credit spread change
        cs_avail = credit_spread[credit_spread.index <= ed]
        if len(cs_avail) < window + 1:
            return None, 0.0, {}, []
        cs_now = float(cs_avail.iloc[-1])
        cs_then = float(cs_avail.iloc[-window - 1])
        cs_chg = cs_now - cs_then
        indicators["credit_spread"] = cs_now
        indicators["cs_change"] = round(cs_chg, 3)

        # Yield curve change
        yc_avail = yield_curve[yield_curve.index <= ed]
        if len(yc_avail) < window + 1:
            return None, 0.0, {}, []
        yc_now = float(yc_avail.iloc[-1])
        yc_then = float(yc_avail.iloc[-window - 1])
        yc_chg = yc_now - yc_then
        indicators["yield_curve"] = yc_now
        indicators["yc_change"] = round(yc_chg, 3)

        # Voting
        bullish = 0
        bearish = 0

        if vix_roc > 15:
            bearish += 1
            drivers.append(f"VIX surging +{vix_roc:.0f}% over {window}d")
        elif vix_roc < -15:
            bullish += 1
            drivers.append(f"VIX falling {vix_roc:.0f}% over {window}d")

        if cs_chg > 0.15:
            bearish += 1
            drivers.append(f"Credit spread widening +{cs_chg:.2f} over {window}d")
        elif cs_chg < -0.15:
            bullish += 1
            drivers.append(f"Credit spread narrowing {cs_chg:.2f} over {window}d")

        if yc_chg > 0.10:
            bullish += 1
            drivers.append(f"Yield curve steepening +{yc_chg:.2f} over {window}d")
        elif yc_chg < -0.10:
            bearish += 1
            drivers.append(f"Yield curve flattening {yc_chg:.2f} over {window}d")

        total = bullish + bearish
        if total == 0:
            return "transition", 0.0, indicators, ["No strong momentum signals"]

        if bullish > bearish:
            confidence = bullish / (bullish + bearish)
            return "expansion", round(confidence, 2), indicators, drivers
        elif bearish > bullish:
            confidence = bearish / (bullish + bearish)
            return "contraction", round(confidence, 2), indicators, drivers
        else:
            return "transition", 0.5, indicators, drivers

    def compare_all_us_stocks(
        self,
        lookback_years: int = 5,
        forward_days: int = 10,
        eval_frequency: str = "weekly",
        benchmark: str = "SPY",
        momentum_window: int = 20,
    ) -> Dict[str, RegimeValidation]:
        """
        Run all three classifiers (level, momentum, combined) on the same
        data fetch. Avoids redundant FRED/Yahoo API calls.
        """
        end = datetime.now()
        start = end - timedelta(days=lookback_years * 365 + 300)

        logger.info(f"Fetching data once for 4-way comparison ({lookback_years}y)...")

        vix = _fetch_vix_history(start, end)
        credit_spread = _fetch_credit_spread_history(start, end)
        yield_curve = _fetch_yield_curve_history(start, end)
        benchmark_prices = _fetch_benchmark_history(benchmark, start, end)

        logger.info(
            f"Data fetched — VIX: {len(vix)}, CS: {len(credit_spread)}, "
            f"YC: {len(yield_curve)}, {benchmark}: {len(benchmark_prices)}"
        )

        eval_start = end - timedelta(days=lookback_years * 365)
        eval_dates = self._build_eval_dates(
            benchmark_prices.index, eval_start, end, eval_frequency,
        )

        # --- Level-based ---
        level_calls: List[RegimeCall] = []
        level_fwd: List[Optional[float]] = []
        for ed in eval_dates:
            indicators = self._snapshot_indicators(ed, vix, credit_spread, yield_curve)
            if not indicators:
                continue
            state = self._detector.classify_pool("us_stocks", indicators)
            level_calls.append(RegimeCall(
                date=pd.Timestamp(ed).strftime("%Y-%m-%d"),
                regime=state.regime, confidence=state.confidence,
                indicators=indicators, drivers=state.drivers,
            ))
            level_fwd.append(self._forward_return(benchmark_prices, ed, forward_days))

        # --- Momentum-based ---
        mom_calls: List[RegimeCall] = []
        mom_fwd: List[Optional[float]] = []
        for ed in eval_dates:
            regime, conf, ind, drv = self._momentum_classify(
                ed, vix, credit_spread, yield_curve, momentum_window)
            if regime is None:
                continue
            mom_calls.append(RegimeCall(
                date=pd.Timestamp(ed).strftime("%Y-%m-%d"),
                regime=regime, confidence=conf, indicators=ind, drivers=drv,
            ))
            mom_fwd.append(self._forward_return(benchmark_prices, ed, forward_days))

        # --- Combined ---
        comb_calls: List[RegimeCall] = []
        comb_fwd: List[Optional[float]] = []
        for ed in eval_dates:
            regime, conf, ind, drv = self._combined_classify(
                ed, vix, credit_spread, yield_curve, benchmark_prices, momentum_window)
            if regime is None:
                continue
            comb_calls.append(RegimeCall(
                date=pd.Timestamp(ed).strftime("%Y-%m-%d"),
                regime=regime, confidence=conf, indicators=ind, drivers=drv,
            ))
            comb_fwd.append(self._forward_return(benchmark_prices, ed, forward_days))

        # --- Continuous ---
        from quant.analysis.regime.continuous_scorer import ContinuousRegimeScorer

        all_series = {
            "vix": vix,
            "credit_spread": credit_spread,
            "yield_curve": yield_curve,
            "benchmark": benchmark_prices,
        }

        scorer = ContinuousRegimeScorer(pool="us_stocks")
        cont_calls: List[RegimeCall] = []
        cont_fwd: List[Optional[float]] = []
        for ed in eval_dates:
            idx = benchmark_prices.index.get_indexer([ed], method="ffill")[0]
            if idx < 0:
                continue
            state = scorer.classify(all_series, eval_idx=idx)
            if state.regime == "transition" and state.confidence == 0.0:
                continue
            cont_calls.append(RegimeCall(
                date=pd.Timestamp(ed).strftime("%Y-%m-%d"),
                regime=state.regime, confidence=state.confidence,
                indicators={}, drivers=state.drivers,
            ))
            cont_fwd.append(self._forward_return(benchmark_prices, ed, forward_days))

        return {
            "level": self._compute_statistics("us_stocks", benchmark, forward_days, level_calls, level_fwd),
            "momentum": self._compute_statistics("us_stocks", benchmark, forward_days, mom_calls, mom_fwd),
            "combined": self._compute_statistics("us_stocks", benchmark, forward_days, comb_calls, comb_fwd),
            "continuous": self._compute_statistics("us_stocks", benchmark, forward_days, cont_calls, cont_fwd),
        }

    @staticmethod
    def _combined_classify(
        eval_date: pd.Timestamp,
        vix: pd.Series,
        credit_spread: pd.Series,
        yield_curve: pd.Series,
        benchmark_prices: pd.Series,
        momentum_window: int,
    ) -> Tuple[Optional[str], float, Dict[str, float], List[str]]:
        """
        Classify regime using macro momentum + benchmark technicals.

        Macro votes (weight 1 each):
          - VIX ROC > +15%   → bearish    | < -15% → bullish
          - CS change > +0.10 → bearish   | < -0.10 → bullish
          - YC change > +0.10 → bullish   | < -0.10 → bearish

        Technical votes (weight 2 each — higher because directly price-based):
          - Price > MA200    → bullish    | Price < MA200 → bearish
          - MA50 > MA200     → bullish    | MA50 < MA200 → bearish
          - RSI > 50         → bullish    | RSI < 50 → bearish
        """
        ed = pd.Timestamp(eval_date)
        indicators: Dict[str, float] = {}
        drivers: List[str] = []

        # Need at least 200 trading days of benchmark data
        prices_avail = benchmark_prices[benchmark_prices.index <= ed]
        if len(prices_avail) < 200:
            return None, 0.0, {}, []

        price = float(prices_avail.iloc[-1])

        # --- Technical signals (weight 2 each) ---
        bullish_w = 0.0
        bearish_w = 0.0

        # MA200
        ma200 = float(prices_avail.iloc[-200:].mean())
        indicators["price"] = round(price, 2)
        indicators["ma200"] = round(ma200, 2)
        if price > ma200:
            bullish_w += 2
            drivers.append(f"Price above MA200 ({price:.0f} > {ma200:.0f})")
        else:
            bearish_w += 2
            drivers.append(f"Price below MA200 ({price:.0f} < {ma200:.0f})")

        # MA50 vs MA200
        ma50 = float(prices_avail.iloc[-50:].mean())
        indicators["ma50"] = round(ma50, 2)
        if ma50 > ma200:
            bullish_w += 2
            drivers.append(f"MA50 > MA200 (golden cross zone)")
        else:
            bearish_w += 2
            drivers.append(f"MA50 < MA200 (death cross zone)")

        # RSI (14-day)
        if len(prices_avail) >= 15:
            deltas = prices_avail.diff().iloc[-15:]
            gains = deltas.clip(lower=0)
            losses = (-deltas.clip(upper=0))
            avg_gain = float(gains.mean())
            avg_loss = float(losses.mean())
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            indicators["rsi"] = round(rsi, 1)

            if rsi > 50:
                bullish_w += 2
                drivers.append(f"RSI {rsi:.0f} > 50 (bullish momentum)")
            else:
                bearish_w += 2
                drivers.append(f"RSI {rsi:.0f} < 50 (bearish momentum)")

        # --- Macro momentum signals (weight 1 each) ---
        vix_avail = vix[vix.index <= ed]
        if len(vix_avail) >= momentum_window + 1:
            vix_now = float(vix_avail.iloc[-1])
            vix_then = float(vix_avail.iloc[-momentum_window - 1])
            vix_roc = (vix_now / vix_then - 1) * 100 if vix_then != 0 else 0
            indicators["vix"] = round(vix_now, 1)
            indicators["vix_roc"] = round(vix_roc, 1)
            if vix_roc > 15:
                bearish_w += 1
                drivers.append(f"VIX surging +{vix_roc:.0f}%")
            elif vix_roc < -15:
                bullish_w += 1
                drivers.append(f"VIX falling {vix_roc:.0f}%")

        cs_avail = credit_spread[credit_spread.index <= ed]
        if len(cs_avail) >= momentum_window + 1:
            cs_chg = float(cs_avail.iloc[-1]) - float(cs_avail.iloc[-momentum_window - 1])
            indicators["cs_change"] = round(cs_chg, 3)
            if cs_chg > 0.10:
                bearish_w += 1
                drivers.append(f"Credit spread widening +{cs_chg:.2f}")
            elif cs_chg < -0.10:
                bullish_w += 1
                drivers.append(f"Credit spread narrowing {cs_chg:.2f}")

        yc_avail = yield_curve[yield_curve.index <= ed]
        if len(yc_avail) >= momentum_window + 1:
            yc_chg = float(yc_avail.iloc[-1]) - float(yc_avail.iloc[-momentum_window - 1])
            indicators["yc_change"] = round(yc_chg, 3)
            if yc_chg > 0.10:
                bullish_w += 1
                drivers.append(f"Yield curve steepening +{yc_chg:.2f}")
            elif yc_chg < -0.10:
                bearish_w += 1
                drivers.append(f"Yield curve flattening {yc_chg:.2f}")

        # --- Determine regime ---
        total = bullish_w + bearish_w
        if total == 0:
            return "transition", 0.0, indicators, ["No signals"]

        if bullish_w > bearish_w:
            confidence = round(bullish_w / total, 2)
            return "expansion", confidence, indicators, drivers
        elif bearish_w > bullish_w:
            confidence = round(bearish_w / total, 2)
            return "contraction", confidence, indicators, drivers
        else:
            return "transition", 0.5, indicators, drivers

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_eval_dates(
        trading_index: pd.DatetimeIndex,
        start: datetime,
        end: datetime,
        frequency: str,
    ) -> List[pd.Timestamp]:
        """Select evaluation dates from the trading calendar."""
        mask = (trading_index >= pd.Timestamp(start)) & (
            trading_index <= pd.Timestamp(end)
        )
        trading_days = trading_index[mask]

        if frequency == "monthly":
            # Last trading day of each month
            monthly = trading_days.to_series().groupby(
                trading_days.to_period("M")
            ).last()
            return list(monthly.values)
        else:
            # Weekly: every Friday (or last trading day of the week)
            weekly = trading_days.to_series().groupby(
                trading_days.to_period("W")
            ).last()
            return list(weekly.values)

    @staticmethod
    def _snapshot_indicators(
        eval_date: pd.Timestamp,
        vix: pd.Series,
        credit_spread: pd.Series,
        yield_curve: pd.Series,
    ) -> Dict[str, float]:
        """
        Get indicator values as of eval_date.

        Uses the most recent available value on or before eval_date
        (forward-fill logic to handle weekends/holidays in FRED data).
        """
        indicators: Dict[str, float] = {}

        for name, series in [
            ("vix", vix),
            ("credit_spread", credit_spread),
            ("yield_curve_2s10s", yield_curve),
        ]:
            # Find the most recent value on or before eval_date
            available = series[series.index <= eval_date]
            if not available.empty:
                indicators[name] = float(available.iloc[-1])

        return indicators

    @staticmethod
    def _forward_return(
        prices: pd.Series,
        eval_date: pd.Timestamp,
        forward_days: int,
    ) -> Optional[float]:
        """Compute forward return from eval_date over forward_days trading days."""
        future = prices[prices.index > eval_date]
        if len(future) < forward_days:
            return None

        entry_candidates = prices[prices.index <= eval_date]
        if entry_candidates.empty:
            return None

        entry_price = float(entry_candidates.iloc[-1])
        exit_price = float(future.iloc[forward_days - 1])

        if entry_price == 0:
            return None

        return (exit_price - entry_price) / entry_price

    @staticmethod
    def _compute_statistics(
        pool: str,
        benchmark: str,
        forward_days: int,
        calls: List[RegimeCall],
        forward_returns: List[Optional[float]],
    ) -> RegimeValidation:
        """Aggregate per-regime accuracy statistics."""
        # Pair calls with returns, skip None returns
        paired = [
            (call, ret)
            for call, ret in zip(calls, forward_returns)
            if ret is not None
        ]

        if not paired:
            return RegimeValidation(
                pool=pool, benchmark=benchmark, forward_days=forward_days,
                total_calls=0, hit_rate=0.0,
                avg_return_positive=0.0, avg_return_negative=0.0,
                avg_return_neutral=0.0,
                regime_counts={}, regime_hit_rates={},
                regime_avg_returns={}, validated_date=date.today().isoformat(),
                calls=calls,
            )

        # Positive regimes expect positive returns; negative expect negative
        _POSITIVE = frozenset({"risk-on", "expansion", "bullish", "reflation"})
        _NEGATIVE = frozenset({"risk-off", "contraction", "bearish", "deflation"})

        # Group by regime
        regime_returns: Dict[str, List[float]] = {}
        hits = 0
        directional_total = 0

        for call, ret in paired:
            regime_returns.setdefault(call.regime, []).append(ret)

            if call.regime in _POSITIVE:
                directional_total += 1
                if ret > 0:
                    hits += 1
            elif call.regime in _NEGATIVE:
                directional_total += 1
                if ret < 0:
                    hits += 1
            # Neutral/transition calls don't count toward hit rate

        hit_rate = hits / directional_total if directional_total > 0 else 0.0

        # Per-regime stats
        regime_counts: Dict[str, int] = {}
        regime_hit_rates: Dict[str, float] = {}
        regime_avg_returns: Dict[str, float] = {}

        for regime, rets in regime_returns.items():
            regime_counts[regime] = len(rets)
            regime_avg_returns[regime] = float(np.mean(rets))

            if regime in _POSITIVE:
                regime_hit_rates[regime] = sum(1 for r in rets if r > 0) / len(rets)
            elif regime in _NEGATIVE:
                regime_hit_rates[regime] = sum(1 for r in rets if r < 0) / len(rets)
            else:
                regime_hit_rates[regime] = 0.0  # neutral has no directional expectation

        # Aggregate returns by regime category
        pos_rets = [r for c, r in paired if c.regime in _POSITIVE]
        neg_rets = [r for c, r in paired if c.regime in _NEGATIVE]
        neu_rets = [r for c, r in paired if c.regime not in _POSITIVE and c.regime not in _NEGATIVE]

        return RegimeValidation(
            pool=pool,
            benchmark=benchmark,
            forward_days=forward_days,
            total_calls=len(paired),
            hit_rate=round(hit_rate, 4),
            avg_return_positive=round(float(np.mean(pos_rets)), 6) if pos_rets else 0.0,
            avg_return_negative=round(float(np.mean(neg_rets)), 6) if neg_rets else 0.0,
            avg_return_neutral=round(float(np.mean(neu_rets)), 6) if neu_rets else 0.0,
            regime_counts=regime_counts,
            regime_hit_rates={k: round(v, 4) for k, v in regime_hit_rates.items()},
            regime_avg_returns={k: round(v, 6) for k, v in regime_avg_returns.items()},
            validated_date=date.today().isoformat(),
            calls=calls,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_validation(
        self,
        validation: RegimeValidation,
        dir_path: str,
    ) -> str:
        """
        Save validation result to JSON.

        Returns the file path written.
        """
        os.makedirs(dir_path, exist_ok=True)
        filename = f"regime_{validation.pool}_{validation.forward_days}d.json"
        file_path = os.path.join(dir_path, filename)

        payload = {
            "pool": validation.pool,
            "benchmark": validation.benchmark,
            "forward_days": validation.forward_days,
            "total_calls": validation.total_calls,
            "hit_rate": validation.hit_rate,
            "avg_return_positive": validation.avg_return_positive,
            "avg_return_negative": validation.avg_return_negative,
            "avg_return_neutral": validation.avg_return_neutral,
            "regime_counts": validation.regime_counts,
            "regime_hit_rates": validation.regime_hit_rates,
            "regime_avg_returns": validation.regime_avg_returns,
            "validated_date": validation.validated_date,
            # Omit individual calls from JSON to keep file size reasonable
        }
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

        logger.info(f"Saved regime validation to {file_path}")
        return file_path


# ---------------------------------------------------------------------------
# CLI entry point for quick testing
# ---------------------------------------------------------------------------

def _print_report(v: RegimeValidation) -> None:
    """Print a human-readable report to stdout."""
    print(f"\n{'='*60}")
    print(f"Regime Validation: {v.pool} (benchmark: {v.benchmark})")
    print(f"{'='*60}")
    print(f"Forward window:  {v.forward_days} trading days")
    print(f"Total calls:     {v.total_calls}")
    print(f"Overall hit rate: {v.hit_rate:.1%}")
    print(f"\nAvg return when regime is positive: {v.avg_return_positive:+.2%}")
    print(f"Avg return when regime is negative: {v.avg_return_negative:+.2%}")
    print(f"Avg return when regime is neutral:  {v.avg_return_neutral:+.2%}")

    print(f"\nPer-regime breakdown:")
    print(f"{'Regime':<15} {'Count':>6} {'Hit Rate':>10} {'Avg Return':>12}")
    print(f"{'-'*45}")
    for regime in sorted(v.regime_counts.keys()):
        count = v.regime_counts[regime]
        hr = v.regime_hit_rates.get(regime, 0.0)
        ar = v.regime_avg_returns.get(regime, 0.0)
        print(f"{regime:<15} {count:>6} {hr:>9.1%} {ar:>+11.2%}")

    print(f"\nValidated: {v.validated_date}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate RegimeDetector accuracy")
    parser.add_argument("--years", type=int, default=2, help="Lookback years")
    parser.add_argument("--forward-days", type=int, default=10, help="Forward return window")
    parser.add_argument("--frequency", choices=["weekly", "monthly"], default="weekly")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--save-dir", default=None, help="Directory to save results")
    parser.add_argument("--mode", choices=["level", "momentum", "combined", "continuous", "compare"],
                        default="compare", help="Which classifier to validate")
    parser.add_argument("--optimize", action="store_true",
                        help="Run grid search to optimize continuous scorer weights")
    parser.add_argument("--weights-path", default=None,
                        help="Path to save/load optimized weights")
    args = parser.parse_args()

    validator = RegimeValidator()
    results = {}

    if args.mode == "compare":
        # Fetch data once, run all three classifiers
        results = validator.compare_all_us_stocks(
            lookback_years=args.years,
            forward_days=args.forward_days,
            eval_frequency=args.frequency,
            benchmark=args.benchmark,
        )
        for name, r in results.items():
            _print_report(r)
    else:
        if args.mode == "level":
            results["level"] = validator.validate_us_stocks(
                lookback_years=args.years, forward_days=args.forward_days,
                eval_frequency=args.frequency, benchmark=args.benchmark,
            )
        elif args.mode == "momentum":
            results["momentum"] = validator.validate_us_stocks_momentum(
                lookback_years=args.years, forward_days=args.forward_days,
                eval_frequency=args.frequency, benchmark=args.benchmark,
            )
        elif args.mode == "combined":
            results["combined"] = validator.validate_us_stocks_combined(
                lookback_years=args.years, forward_days=args.forward_days,
                eval_frequency=args.frequency, benchmark=args.benchmark,
            )
        elif args.mode == "continuous":
            results["continuous"] = validator.validate_us_stocks_continuous(
                lookback_years=args.years, forward_days=args.forward_days,
                eval_frequency=args.frequency, benchmark=args.benchmark,
                optimize_weights=args.optimize, weights_path=args.weights_path,
            )
        for r in results.values():
            _print_report(r)

    if len(results) >= 2:
        print("=" * 60)
        print("COMPARISON SUMMARY")
        print("=" * 60)
        header = f"{'':20s}"
        for name in results:
            header += f" {name:>12s}"
        print(header)
        print(f"{'-'*(20 + 13 * len(results))}")
        for label, attr in [
            ("Hit rate", "hit_rate"),
            ("Total calls", "total_calls"),
            ("Expansion hit", None),
            ("Contraction hit", None),
            ("Avg ret (positive)", "avg_return_positive"),
            ("Avg ret (negative)", "avg_return_negative"),
        ]:
            line = f"{label:20s}"
            for name, r in results.items():
                if attr == "hit_rate":
                    line += f" {r.hit_rate:>11.1%}"
                elif attr == "total_calls":
                    line += f" {r.total_calls:>12d}"
                elif attr == "avg_return_positive":
                    line += f" {r.avg_return_positive:>+11.2%}"
                elif attr == "avg_return_negative":
                    line += f" {r.avg_return_negative:>+11.2%}"
                elif label == "Expansion hit":
                    hr = r.regime_hit_rates.get("expansion", 0)
                    line += f" {hr:>11.1%}"
                elif label == "Contraction hit":
                    hr = r.regime_hit_rates.get("contraction", 0)
                    line += f" {hr:>11.1%}"
            print(line)
        print()

    if args.save_dir:
        for r in results.values():
            validator.save_validation(r, args.save_dir)
