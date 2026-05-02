#!/usr/bin/env python3
"""FeaturePipeline — normalize raw indicators into [-1, +1] features."""

from __future__ import annotations

import math
import os
from typing import Dict, Optional

import numpy as np
import pandas as pd
import yaml


def _tanh(x: float) -> float:
    return math.tanh(x)


class FeaturePipeline:
    """
    Transforms raw time-series indicators into normalized features in [-1, +1].

    Parameters
    ----------
    pool : str
        Asset pool name (e.g. "us_stocks").
    config_path : str, optional
        Path to regime_features.yaml.
    """

    def __init__(self, pool: str = "us_stocks", config_path: Optional[str] = None) -> None:
        if config_path is None:
            here = os.path.dirname(os.path.abspath(__file__))
            repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
            config_path = os.path.join(repo_root, "config", "regime_features.yaml")

        with open(config_path, "r", encoding="utf-8") as fh:
            full_cfg = yaml.safe_load(fh)

        self._cfg = full_cfg[pool]
        self._pool = pool
        self._zscore_window: int = self._cfg["zscore_window"]
        self._momentum_window: int = self._cfg["momentum_window"]
        self._features_cfg: Dict = self._cfg["features"]

    @property
    def feature_names(self) -> list[str]:
        return list(self._features_cfg.keys())

    def compute(
        self,
        series: Dict[str, pd.Series],
        eval_idx: int = -1,
    ) -> Dict[str, float]:
        """
        Compute all features from raw time-series data.

        Parameters
        ----------
        series : dict
            Mapping of source name -> pd.Series with DatetimeIndex.
            Expected keys: "vix", "credit_spread", "yield_curve", "benchmark".
        eval_idx : int
            Index position to evaluate at. Use -1 for latest, or a specific
            integer index for walk-forward backtesting.

        Returns
        -------
        dict
            Feature name -> value in [-1, +1]. Empty dict if insufficient data.
        """
        # Check minimum data requirement
        min_required = max(self._zscore_window, self._momentum_window, 200)
        for s in series.values():
            if len(s) < min_required:
                return {}

        # Slice all series up to eval_idx (inclusive)
        sliced = {}
        for name, s in series.items():
            if eval_idx == -1:
                sliced[name] = s
            else:
                sliced[name] = s.iloc[: eval_idx + 1]

        # Check again after slicing (re-compute min_required in case eval_idx reduced length)
        for s in sliced.values():
            if len(s) < min_required:
                return {}

        features: Dict[str, float] = {}

        for feat_name, feat_cfg in self._features_cfg.items():
            source = sliced[feat_cfg["source"]]
            method = feat_cfg["method"]
            polarity = feat_cfg["polarity"]

            if method == "zscore":
                val = self._zscore_feature(source, self._zscore_window)
            elif method == "momentum_zscore":
                val = self._momentum_zscore_feature(
                    source, self._momentum_window, self._zscore_window,
                )
            elif method == "ratio":
                val = self._price_vs_ma200(source)
            elif method == "ma_ratio":
                val = self._ma50_vs_ma200(source)
            elif method == "rsi":
                val = self._rsi_feature(source)
            else:
                continue

            features[feat_name] = round(val * polarity, 6)

        return features

    # --- Normalization methods ---

    @staticmethod
    def _zscore_feature(series: pd.Series, window: int) -> float:
        """Z-score of latest value over rolling window, compressed by tanh."""
        recent = series.iloc[-window:]
        mean = float(recent.mean())
        std = float(recent.std())
        if std < 1e-10:
            return 0.0
        z = (float(series.iloc[-1]) - mean) / std
        return _tanh(z)

    @staticmethod
    def _momentum_zscore_feature(
        series: pd.Series, momentum_window: int, zscore_window: int,
    ) -> float:
        """Z-score of N-day change, compressed by tanh."""
        if len(series) < momentum_window + zscore_window:
            return 0.0
        changes = series.diff(momentum_window).dropna()
        recent_changes = changes.iloc[-zscore_window:]
        mean = float(recent_changes.mean())
        std = float(recent_changes.std())
        if std < 1e-10:
            return 0.0
        latest_change = float(changes.iloc[-1])
        z = (latest_change - mean) / std
        return _tanh(z)

    @staticmethod
    def _price_vs_ma200(prices: pd.Series) -> float:
        """(price - MA200) / MA200, compressed by tanh."""
        ma200 = float(prices.iloc[-200:].mean())
        if ma200 < 1e-10:
            return 0.0
        ratio = (float(prices.iloc[-1]) - ma200) / ma200
        # Scale up slightly so 5% deviation -> ~tanh(1) ~ 0.76
        return _tanh(ratio * 20)

    @staticmethod
    def _ma50_vs_ma200(prices: pd.Series) -> float:
        """(MA50 - MA200) / MA200, compressed by tanh."""
        ma50 = float(prices.iloc[-50:].mean())
        ma200 = float(prices.iloc[-200:].mean())
        if ma200 < 1e-10:
            return 0.0
        ratio = (ma50 - ma200) / ma200
        return _tanh(ratio * 20)

    @staticmethod
    def _rsi_feature(prices: pd.Series, period: int = 14) -> float:
        """RSI normalized to [-1, +1]: (RSI - 50) / 50."""
        deltas = prices.diff().iloc[-(period + 1):]
        gains = deltas.clip(lower=0)
        losses = -deltas.clip(upper=0)
        avg_gain = float(gains.mean())
        avg_loss = float(losses.mean())
        if avg_gain < 1e-10 and avg_loss < 1e-10:
            # Flat prices — no movement in either direction; RSI is neutral
            rsi = 50.0
        elif avg_loss < 1e-10:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        return (rsi - 50) / 50
