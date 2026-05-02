# Continuous Regime Scorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `ContinuousRegimeScorer` that replaces discrete voting with weighted continuous scoring for regime classification, outputting a compatible `RegimeState` and integrated into the existing walk-forward validation framework.

**Architecture:** Three new modules (`feature_pipeline.py`, `scoring_backend.py`, `continuous_scorer.py`) sit alongside the existing `RegimeDetector` without modifying it. A `FeaturePipeline` normalizes raw indicators into [-1, +1] features, a `WeightedLinearBackend` computes a weighted sum, and `ContinuousRegimeScorer` maps the result to a `RegimeState`. Grid search optimization finds optimal weights from historical data.

**Tech Stack:** Python, numpy, pandas (already in project). No new dependencies.

---

## File Structure

```
quant/analysis/regime/
├── regime_detector.py          # UNCHANGED
├── regime_validator.py         # MODIFY: add validate_us_stocks_continuous(), extend compare_all
├── feature_pipeline.py         # CREATE: FeaturePipeline class
├── scoring_backend.py          # CREATE: ScoringBackend ABC + WeightedLinearBackend
├── continuous_scorer.py        # CREATE: ContinuousRegimeScorer
└── __init__.py                 # MODIFY: export new classes

config/
├── regime_thresholds.yaml      # UNCHANGED
├── regime_features.yaml        # CREATE: feature definitions
└── regime_weights.json         # CREATE: default + optimized weights

tests/unit/
├── test_regime_detector.py     # UNCHANGED
├── test_feature_pipeline.py    # CREATE
├── test_scoring_backend.py     # CREATE
└── test_continuous_scorer.py   # CREATE
```

---

### Task 1: Feature configuration file

**Files:**
- Create: `config/regime_features.yaml`

- [ ] **Step 1: Create the feature configuration**

```yaml
# config/regime_features.yaml
# Feature definitions for ContinuousRegimeScorer (us_stocks pool).

us_stocks:
  # Normalization defaults
  zscore_window: 60        # rolling window for z-score (trading days)
  momentum_window: 20      # window for rate-of-change features

  # Score-to-regime mapping thresholds
  expansion_threshold: 0.2
  contraction_threshold: -0.2

  features:
    # --- Macro level (z-score of absolute value) ---
    vix_level:
      source: vix
      method: zscore       # z-score over rolling window, then tanh
      polarity: -1         # higher VIX = bearish → negative contribution

    cs_level:
      source: credit_spread
      method: zscore
      polarity: -1         # higher spread = bearish

    yc_level:
      source: yield_curve
      method: zscore
      polarity: 1          # higher 2s10s = bullish

    # --- Macro momentum (z-score of N-day change) ---
    vix_roc:
      source: vix
      method: momentum_zscore   # ROC over momentum_window, z-score, tanh
      polarity: -1              # rising VIX = bearish

    cs_change:
      source: credit_spread
      method: momentum_zscore
      polarity: -1              # widening spread = bearish

    yc_change:
      source: yield_curve
      method: momentum_zscore
      polarity: 1               # steepening = bullish

    # --- Price technicals (natural-range normalization) ---
    price_vs_ma200:
      source: benchmark
      method: ratio              # (price - MA200) / MA200, then tanh
      polarity: 1                # above MA200 = bullish

    ma50_vs_ma200:
      source: benchmark
      method: ma_ratio           # (MA50 - MA200) / MA200, then tanh
      polarity: 1                # golden cross zone = bullish

    rsi_norm:
      source: benchmark
      method: rsi                # (RSI14 - 50) / 50 → [-1, +1]
      polarity: 1                # RSI > 50 = bullish
```

- [ ] **Step 2: Commit**

```bash
git add config/regime_features.yaml
git commit -m "config: add regime feature definitions for continuous scorer"
```

---

### Task 2: FeaturePipeline — tests

**Files:**
- Create: `tests/unit/test_feature_pipeline.py`

- [ ] **Step 1: Write failing tests for FeaturePipeline**

```python
#!/usr/bin/env python3
"""Tests for FeaturePipeline — regime feature normalization."""

import numpy as np
import pandas as pd
import pytest

from quant.analysis.regime.feature_pipeline import FeaturePipeline


@pytest.fixture
def pipeline():
    return FeaturePipeline(pool="us_stocks")


@pytest.fixture
def sample_series():
    """200 trading days of synthetic data for each indicator."""
    dates = pd.bdate_range("2025-01-01", periods=200)
    rng = np.random.RandomState(42)
    return {
        "vix": pd.Series(20 + rng.randn(200) * 5, index=dates),
        "credit_spread": pd.Series(1.8 + rng.randn(200) * 0.3, index=dates),
        "yield_curve": pd.Series(0.2 + rng.randn(200) * 0.4, index=dates),
        "benchmark": pd.Series(
            450 * np.cumprod(1 + rng.randn(200) * 0.01), index=dates
        ),
    }


class TestFeaturePipelineOutput:
    def test_returns_all_nine_features(self, pipeline, sample_series):
        features = pipeline.compute(sample_series, eval_idx=-1)
        expected_keys = {
            "vix_level", "vix_roc", "cs_level", "cs_change",
            "yc_level", "yc_change", "price_vs_ma200",
            "ma50_vs_ma200", "rsi_norm",
        }
        assert set(features.keys()) == expected_keys

    def test_all_features_in_range(self, pipeline, sample_series):
        features = pipeline.compute(sample_series, eval_idx=-1)
        for name, val in features.items():
            assert -1.0 <= val <= 1.0, f"{name}={val} out of [-1, 1]"

    def test_extreme_vix_saturates(self, pipeline, sample_series):
        """A VIX spike to 80 should produce a feature near -1 (bearish)."""
        series = sample_series.copy()
        series["vix"] = series["vix"].copy()
        series["vix"].iloc[-1] = 80.0
        features = pipeline.compute(series, eval_idx=-1)
        assert features["vix_level"] < -0.5

    def test_rsi_midpoint_near_zero(self, pipeline):
        """Perfectly flat prices → RSI ~50 → rsi_norm ~0."""
        dates = pd.bdate_range("2025-01-01", periods=200)
        flat = pd.Series(100.0, index=dates)
        series = {
            "vix": pd.Series(20.0, index=dates),
            "credit_spread": pd.Series(1.8, index=dates),
            "yield_curve": pd.Series(0.2, index=dates),
            "benchmark": flat,
        }
        features = pipeline.compute(series, eval_idx=-1)
        assert abs(features["rsi_norm"]) < 0.15

    def test_eval_idx_slices_correctly(self, pipeline, sample_series):
        """Features at idx=100 should not see data after idx=100."""
        f1 = pipeline.compute(sample_series, eval_idx=100)
        f2 = pipeline.compute(sample_series, eval_idx=-1)
        # Different eval points → different features (almost certainly)
        assert f1 != f2

    def test_insufficient_data_returns_empty(self, pipeline):
        """If not enough history, return empty dict."""
        dates = pd.bdate_range("2025-01-01", periods=10)
        short = {
            "vix": pd.Series(20.0, index=dates),
            "credit_spread": pd.Series(1.8, index=dates),
            "yield_curve": pd.Series(0.2, index=dates),
            "benchmark": pd.Series(100.0, index=dates),
        }
        features = pipeline.compute(short, eval_idx=-1)
        assert features == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_feature_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quant.analysis.regime.feature_pipeline'`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_feature_pipeline.py
git commit -m "test: add failing tests for FeaturePipeline"
```

---

### Task 3: FeaturePipeline — implementation

**Files:**
- Create: `quant/analysis/regime/feature_pipeline.py`

- [ ] **Step 1: Implement FeaturePipeline**

```python
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
            Mapping of source name → pd.Series with DatetimeIndex.
            Expected keys: "vix", "credit_spread", "yield_curve", "benchmark".
        eval_idx : int
            Index position to evaluate at. Use -1 for latest, or a specific
            integer index for walk-forward backtesting.

        Returns
        -------
        dict
            Feature name → value in [-1, +1]. Empty dict if insufficient data.
        """
        # Check minimum data requirement
        min_required = max(self._zscore_window, self._momentum_window, 200) + 1
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

        # Check again after slicing
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
        # Scale up slightly so 5% deviation → ~tanh(1) ≈ 0.76
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
        if avg_loss < 1e-10:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        return (rsi - 50) / 50
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_feature_pipeline.py -v`
Expected: all 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add quant/analysis/regime/feature_pipeline.py
git commit -m "feat: implement FeaturePipeline for continuous regime scoring"
```

---

### Task 4: ScoringBackend — tests

**Files:**
- Create: `tests/unit/test_scoring_backend.py`

- [ ] **Step 1: Write failing tests for ScoringBackend**

```python
#!/usr/bin/env python3
"""Tests for ScoringBackend — weighted linear scoring."""

import json
import math
import os
import tempfile

import numpy as np
import pytest

from quant.analysis.regime.scoring_backend import (
    ScoringBackend,
    WeightedLinearBackend,
)


class TestWeightedLinearBackend:
    def test_score_with_equal_weights(self):
        weights = {"a": 1.0, "b": 1.0, "c": 1.0}
        backend = WeightedLinearBackend(weights)
        features = {"a": 0.5, "b": 0.5, "c": 0.5}
        score = backend.score(features)
        # raw = 0.5 + 0.5 + 0.5 = 1.5, tanh(1.5) ≈ 0.905
        assert abs(score - math.tanh(1.5)) < 0.001

    def test_opposing_features_cancel(self):
        weights = {"a": 1.0, "b": 1.0}
        backend = WeightedLinearBackend(weights)
        features = {"a": 0.8, "b": -0.8}
        score = backend.score(features)
        # raw = 0.0, tanh(0) = 0
        assert abs(score) < 0.001

    def test_negative_weights(self):
        weights = {"a": -2.0, "b": 1.0}
        backend = WeightedLinearBackend(weights)
        features = {"a": 0.5, "b": 0.5}
        # raw = -2*0.5 + 1*0.5 = -0.5
        score = backend.score(features)
        assert score < 0

    def test_missing_feature_ignored(self):
        weights = {"a": 1.0, "b": 1.0, "c": 1.0}
        backend = WeightedLinearBackend(weights)
        features = {"a": 0.5, "b": 0.5}
        # Only a and b contribute; c is missing → treated as 0
        score = backend.score(features)
        expected = math.tanh(1.0)
        assert abs(score - expected) < 0.001

    def test_score_bounded(self):
        weights = {"a": 10.0, "b": 10.0, "c": 10.0}
        backend = WeightedLinearBackend(weights)
        features = {"a": 1.0, "b": 1.0, "c": 1.0}
        score = backend.score(features)
        assert -1.0 <= score <= 1.0

    def test_load_from_json(self, tmp_path):
        weights_data = {
            "weights": {"a": 1.5, "b": -0.5},
            "metadata": {"hit_rate": 0.65},
        }
        path = tmp_path / "weights.json"
        path.write_text(json.dumps(weights_data))
        backend = WeightedLinearBackend.from_json(str(path))
        assert backend._weights == {"a": 1.5, "b": -0.5}

    def test_is_scoring_backend(self):
        backend = WeightedLinearBackend({"a": 1.0})
        assert isinstance(backend, ScoringBackend)


class TestGridSearch:
    def test_fit_improves_or_matches_default(self):
        """Grid search should find weights at least as good as all-ones."""
        rng = np.random.RandomState(42)
        n = 100
        feature_names = ["a", "b", "c"]
        # Feature a is predictive, b and c are noise
        feature_matrix = rng.randn(n, 3)
        forward_returns = feature_matrix[:, 0] * 0.01 + rng.randn(n) * 0.002

        backend = WeightedLinearBackend(dict.fromkeys(feature_names, 1.0))
        result = backend.fit(
            feature_names=feature_names,
            feature_matrix=feature_matrix,
            forward_returns=forward_returns,
            search_values=[-1, 0, 1],
        )
        assert "train_hit_rate" in result
        assert "test_hit_rate" in result
        assert result["train_hit_rate"] >= 0.5

    def test_fit_saves_to_json(self, tmp_path):
        rng = np.random.RandomState(42)
        n = 100
        feature_names = ["a", "b"]
        feature_matrix = rng.randn(n, 2)
        forward_returns = feature_matrix[:, 0] * 0.01

        backend = WeightedLinearBackend(dict.fromkeys(feature_names, 1.0))
        save_path = str(tmp_path / "optimized.json")
        backend.fit(
            feature_names=feature_names,
            feature_matrix=feature_matrix,
            forward_returns=forward_returns,
            search_values=[-1, 0, 1],
            save_path=save_path,
        )
        assert os.path.exists(save_path)
        with open(save_path) as f:
            data = json.load(f)
        assert "weights" in data
        assert "metadata" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_scoring_backend.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_scoring_backend.py
git commit -m "test: add failing tests for ScoringBackend and grid search"
```

---

### Task 5: ScoringBackend — implementation

**Files:**
- Create: `quant/analysis/regime/scoring_backend.py`
- Create: `config/regime_weights.json`

- [ ] **Step 1: Implement ScoringBackend and WeightedLinearBackend**

```python
#!/usr/bin/env python3
"""ScoringBackend — abstract scoring interface + weighted linear implementation."""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from itertools import product
from typing import Dict, List, Optional, Tuple

import numpy as np

from quant.core.logging_config import get_logger

logger = get_logger(__name__)


class ScoringBackend(ABC):
    """Abstract interface for regime scoring backends."""

    @abstractmethod
    def score(self, features: Dict[str, float]) -> float:
        """Compute regime score from normalized features. Returns [-1, +1]."""
        ...

    def fit(
        self,
        feature_names: List[str],
        feature_matrix: np.ndarray,
        forward_returns: np.ndarray,
        **kwargs,
    ) -> Dict:
        """Optimize parameters from historical data. Default: no-op."""
        return {}


class WeightedLinearBackend(ScoringBackend):
    """
    Weighted linear combination of features, compressed by tanh.

    score = tanh(Σ weight_i × feature_i)
    """

    def __init__(self, weights: Dict[str, float]) -> None:
        self._weights = weights

    @classmethod
    def from_json(cls, path: str) -> WeightedLinearBackend:
        """Load weights from a JSON file."""
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(data["weights"])

    def score(self, features: Dict[str, float]) -> float:
        raw = sum(
            self._weights[k] * features.get(k, 0.0)
            for k in self._weights
        )
        return math.tanh(raw)

    def fit(
        self,
        feature_names: List[str],
        feature_matrix: np.ndarray,
        forward_returns: np.ndarray,
        search_values: Optional[List[float]] = None,
        save_path: Optional[str] = None,
    ) -> Dict:
        """
        Grid search over weight combinations to maximize hit rate.

        Uses grouped search: macro-level, macro-momentum, technicals
        searched sequentially to keep search space manageable.

        Parameters
        ----------
        feature_names : list
            Names corresponding to columns of feature_matrix.
        feature_matrix : ndarray, shape (n_samples, n_features)
            Normalized features for each evaluation date.
        forward_returns : ndarray, shape (n_samples,)
            Forward returns for each evaluation date.
        search_values : list of float, optional
            Weight values to search over. Default: [-2, -1, 0, 1, 2].
        save_path : str, optional
            If provided, save optimized weights to this JSON file.

        Returns
        -------
        dict with keys: weights, train_hit_rate, test_hit_rate, split_idx
        """
        if search_values is None:
            search_values = [-2.0, -1.0, 0.0, 1.0, 2.0]

        n = len(forward_returns)
        split_idx = int(n * 0.7)

        train_features = feature_matrix[:split_idx]
        train_returns = forward_returns[:split_idx]
        test_features = feature_matrix[split_idx:]
        test_returns = forward_returns[split_idx:]

        # Group features for staged search
        groups = self._build_groups(feature_names)

        best_weights = {name: 1.0 for name in feature_names}

        for group_name, group_indices in groups:
            group_names = [feature_names[i] for i in group_indices]
            best_group_hr = -1.0

            for combo in product(search_values, repeat=len(group_indices)):
                candidate = best_weights.copy()
                for i, idx in enumerate(group_indices):
                    candidate[feature_names[idx]] = combo[i]

                hr = self._compute_hit_rate(
                    candidate, feature_names, train_features, train_returns,
                )
                if hr > best_group_hr:
                    best_group_hr = hr
                    for i, idx in enumerate(group_indices):
                        best_weights[feature_names[idx]] = combo[i]

            logger.info(
                f"Grid search group '{group_name}': "
                f"best train hit_rate={best_group_hr:.3f}"
            )

        self._weights = best_weights

        train_hr = self._compute_hit_rate(
            best_weights, feature_names, train_features, train_returns,
        )
        test_hr = self._compute_hit_rate(
            best_weights, feature_names, test_features, test_returns,
        )

        logger.info(
            f"Grid search complete: train={train_hr:.3f}, test={test_hr:.3f}, "
            f"gap={abs(train_hr - test_hr):.3f}"
        )
        if abs(train_hr - test_hr) > 0.15:
            logger.warning(
                f"Possible overfitting: train/test gap = {abs(train_hr - test_hr):.3f}"
            )

        result = {
            "weights": best_weights,
            "train_hit_rate": round(train_hr, 4),
            "test_hit_rate": round(test_hr, 4),
            "split_idx": split_idx,
        }

        if save_path is not None:
            payload = {
                "weights": best_weights,
                "metadata": {
                    "train_hit_rate": round(train_hr, 4),
                    "test_hit_rate": round(test_hr, 4),
                    "n_train": split_idx,
                    "n_test": n - split_idx,
                    "search_values": search_values,
                },
            }
            with open(save_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            logger.info(f"Saved optimized weights to {save_path}")

        return result

    @staticmethod
    def _build_groups(feature_names: List[str]) -> List[Tuple[str, List[int]]]:
        """Split features into search groups by category."""
        macro_level = []
        macro_momentum = []
        technicals = []

        for i, name in enumerate(feature_names):
            if name in ("vix_level", "cs_level", "yc_level"):
                macro_level.append(i)
            elif name in ("vix_roc", "cs_change", "yc_change"):
                macro_momentum.append(i)
            else:
                technicals.append(i)

        groups = []
        if macro_level:
            groups.append(("macro_level", macro_level))
        if macro_momentum:
            groups.append(("macro_momentum", macro_momentum))
        if technicals:
            groups.append(("technicals", technicals))
        return groups

    @staticmethod
    def _compute_hit_rate(
        weights: Dict[str, float],
        feature_names: List[str],
        feature_matrix: np.ndarray,
        forward_returns: np.ndarray,
    ) -> float:
        """Compute directional hit rate for given weights."""
        weight_vec = np.array([weights.get(n, 0.0) for n in feature_names])
        raw_scores = feature_matrix @ weight_vec
        scores = np.tanh(raw_scores)

        hits = 0
        total = 0
        for score, ret in zip(scores, forward_returns):
            if score > 0.2:
                total += 1
                if ret > 0:
                    hits += 1
            elif score < -0.2:
                total += 1
                if ret < 0:
                    hits += 1
            # Transition zone: no directional expectation

        return hits / total if total > 0 else 0.0
```

- [ ] **Step 2: Create default weights file**

```json
{
  "weights": {
    "vix_level": 1.0,
    "vix_roc": 1.0,
    "cs_level": 1.0,
    "cs_change": 1.0,
    "yc_level": 1.0,
    "yc_change": 1.0,
    "price_vs_ma200": 1.0,
    "ma50_vs_ma200": 1.0,
    "rsi_norm": 1.0
  },
  "metadata": {
    "note": "Default equal weights — run grid search to optimize"
  }
}
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_scoring_backend.py -v`
Expected: all 9 tests PASS

- [ ] **Step 4: Commit**

```bash
git add quant/analysis/regime/scoring_backend.py config/regime_weights.json
git commit -m "feat: implement ScoringBackend with weighted linear scoring and grid search"
```

---

### Task 6: ContinuousRegimeScorer — tests

**Files:**
- Create: `tests/unit/test_continuous_scorer.py`

- [ ] **Step 1: Write failing tests for ContinuousRegimeScorer**

```python
#!/usr/bin/env python3
"""Tests for ContinuousRegimeScorer — end-to-end scoring → RegimeState."""

import numpy as np
import pandas as pd
import pytest

from quant.analysis.regime.continuous_scorer import ContinuousRegimeScorer
from quant.analysis.regime.regime_detector import RegimeState


@pytest.fixture
def scorer():
    return ContinuousRegimeScorer(pool="us_stocks")


@pytest.fixture
def bullish_series():
    """Strongly bullish market: low VIX, tight spreads, steep curve, uptrend."""
    dates = pd.bdate_range("2024-01-01", periods=300)
    return {
        "vix": pd.Series(
            np.concatenate([np.full(280, 25.0), np.full(20, 12.0)]),
            index=dates,
        ),
        "credit_spread": pd.Series(
            np.concatenate([np.full(280, 2.0), np.full(20, 1.0)]),
            index=dates,
        ),
        "yield_curve": pd.Series(
            np.concatenate([np.full(280, 0.0), np.full(20, 0.8)]),
            index=dates,
        ),
        "benchmark": pd.Series(
            400 * np.cumprod(np.concatenate([
                np.full(280, 1.001),
                np.full(20, 1.005),
            ])),
            index=dates,
        ),
    }


@pytest.fixture
def bearish_series():
    """Strongly bearish market: high VIX, wide spreads, inverted curve, downtrend."""
    dates = pd.bdate_range("2024-01-01", periods=300)
    return {
        "vix": pd.Series(
            np.concatenate([np.full(280, 15.0), np.full(20, 40.0)]),
            index=dates,
        ),
        "credit_spread": pd.Series(
            np.concatenate([np.full(280, 1.5), np.full(20, 3.5)]),
            index=dates,
        ),
        "yield_curve": pd.Series(
            np.concatenate([np.full(280, 0.5), np.full(20, -0.5)]),
            index=dates,
        ),
        "benchmark": pd.Series(
            500 * np.cumprod(np.concatenate([
                np.full(280, 1.001),
                np.full(20, 0.995),
            ])),
            index=dates,
        ),
    }


class TestContinuousRegimeScorerOutput:
    def test_returns_regime_state(self, scorer, bullish_series):
        state = scorer.classify(bullish_series)
        assert isinstance(state, RegimeState)
        assert state.pool == "us_stocks"

    def test_bullish_market_is_expansion(self, scorer, bullish_series):
        state = scorer.classify(bullish_series)
        assert state.regime == "expansion"
        assert state.confidence > 0.3

    def test_bearish_market_is_contraction(self, scorer, bearish_series):
        state = scorer.classify(bearish_series)
        assert state.regime == "contraction"
        assert state.confidence > 0.3

    def test_confidence_between_zero_and_one(self, scorer, bullish_series):
        state = scorer.classify(bullish_series)
        assert 0.0 <= state.confidence <= 1.0

    def test_drivers_populated(self, scorer, bullish_series):
        state = scorer.classify(bullish_series)
        assert len(state.drivers) > 0

    def test_raw_score_available(self, scorer, bullish_series):
        score = scorer.score(bullish_series)
        assert isinstance(score, float)
        assert -1.0 <= score <= 1.0

    def test_score_positive_for_bullish(self, scorer, bullish_series):
        score = scorer.score(bullish_series)
        assert score > 0

    def test_score_negative_for_bearish(self, scorer, bearish_series):
        score = scorer.score(bearish_series)
        assert score < 0

    def test_classify_at_index(self, scorer, bullish_series):
        """Can classify at a specific historical index for backtesting."""
        state = scorer.classify(bullish_series, eval_idx=250)
        assert isinstance(state, RegimeState)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_continuous_scorer.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_continuous_scorer.py
git commit -m "test: add failing tests for ContinuousRegimeScorer"
```

---

### Task 7: ContinuousRegimeScorer — implementation

**Files:**
- Create: `quant/analysis/regime/continuous_scorer.py`
- Modify: `quant/analysis/regime/__init__.py`

- [ ] **Step 1: Implement ContinuousRegimeScorer**

```python
#!/usr/bin/env python3
"""ContinuousRegimeScorer — weighted continuous scoring for regime classification."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd

from quant.analysis.regime.feature_pipeline import FeaturePipeline
from quant.analysis.regime.regime_detector import RegimeState
from quant.analysis.regime.scoring_backend import ScoringBackend, WeightedLinearBackend


# Default score-to-regime thresholds (can be overridden via config)
_DEFAULT_EXPANSION_THRESHOLD = 0.2
_DEFAULT_CONTRACTION_THRESHOLD = -0.2

# Pool label mapping (same as RegimeDetector)
_POOL_LABELS = {
    "us_stocks": ("expansion", "contraction", "transition"),
}


class ContinuousRegimeScorer:
    """
    Continuous-score-based regime classifier.

    Replaces discrete voting with weighted continuous scoring.
    Outputs a standard RegimeState compatible with VerdictEngine and Dashboard.

    Parameters
    ----------
    pool : str
        Asset pool (currently only "us_stocks").
    backend : ScoringBackend, optional
        Scoring backend. Defaults to WeightedLinearBackend loaded from
        config/regime_weights.json.
    pipeline : FeaturePipeline, optional
        Feature pipeline. Defaults to FeaturePipeline(pool).
    expansion_threshold : float, optional
        Score above this → positive regime. Default 0.2.
    contraction_threshold : float, optional
        Score below this → negative regime. Default -0.2.
    """

    def __init__(
        self,
        pool: str = "us_stocks",
        backend: Optional[ScoringBackend] = None,
        pipeline: Optional[FeaturePipeline] = None,
        expansion_threshold: Optional[float] = None,
        contraction_threshold: Optional[float] = None,
    ) -> None:
        self._pool = pool
        self._pipeline = pipeline or FeaturePipeline(pool=pool)

        if backend is None:
            here = os.path.dirname(os.path.abspath(__file__))
            repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
            weights_path = os.path.join(repo_root, "config", "regime_weights.json")
            backend = WeightedLinearBackend.from_json(weights_path)
        self._backend = backend

        pos_label, neg_label, neutral_label = _POOL_LABELS[pool]
        self._pos_label = pos_label
        self._neg_label = neg_label
        self._neutral_label = neutral_label

        self._expansion_th = expansion_threshold or _DEFAULT_EXPANSION_THRESHOLD
        self._contraction_th = contraction_threshold or _DEFAULT_CONTRACTION_THRESHOLD

    def score(
        self,
        series: Dict[str, pd.Series],
        eval_idx: int = -1,
    ) -> float:
        """
        Compute raw continuous score in [-1, +1].

        Positive = bullish, negative = bearish, near zero = transition.
        """
        features = self._pipeline.compute(series, eval_idx=eval_idx)
        if not features:
            return 0.0
        return self._backend.score(features)

    def classify(
        self,
        series: Dict[str, pd.Series],
        eval_idx: int = -1,
    ) -> RegimeState:
        """
        Classify regime from time-series data.

        Returns a RegimeState compatible with existing RegimeDetector output.
        """
        features = self._pipeline.compute(series, eval_idx=eval_idx)
        if not features:
            return RegimeState(
                pool=self._pool,
                regime=self._neutral_label,
                confidence=0.0,
                days_since_change=0,
                drivers=["Insufficient data for continuous scoring"],
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

        raw_score = self._backend.score(features)

        regime, confidence = self._map_score(raw_score)

        drivers = self._build_drivers(features, raw_score)

        return RegimeState(
            pool=self._pool,
            regime=regime,
            confidence=round(confidence, 4),
            days_since_change=0,
            drivers=drivers,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _map_score(self, score: float) -> tuple[str, float]:
        """Map continuous score to (regime_label, confidence)."""
        if score > self._expansion_th:
            return self._pos_label, score
        elif score < self._contraction_th:
            return self._neg_label, abs(score)
        else:
            # Transition: confidence = how far from the edges
            confidence = 1.0 - abs(score) / self._expansion_th
            return self._neutral_label, max(0.0, confidence)

    @staticmethod
    def _build_drivers(features: Dict[str, float], score: float) -> List[str]:
        """Build human-readable driver list from feature contributions."""
        drivers: List[str] = []

        # Sort features by absolute contribution (descending)
        sorted_features = sorted(
            features.items(), key=lambda x: abs(x[1]), reverse=True,
        )

        for name, val in sorted_features[:5]:
            direction = "bullish" if val > 0 else "bearish"
            drivers.append(f"{name}: {val:+.3f} ({direction})")

        drivers.append(f"composite score: {score:+.3f}")
        return drivers
```

- [ ] **Step 2: Update `__init__.py` to export new classes**

Add to `quant/analysis/regime/__init__.py`:

```python
"""
Regime Detection Module

Classifies market regime (risk-on/off, expansion/contraction, etc.)
per asset pool based on configurable indicator thresholds.
"""

from .regime_detector import RegimeDetector, RegimeState
from .continuous_scorer import ContinuousRegimeScorer
from .feature_pipeline import FeaturePipeline
from .scoring_backend import ScoringBackend, WeightedLinearBackend

__all__ = [
    "RegimeDetector",
    "RegimeState",
    "ContinuousRegimeScorer",
    "FeaturePipeline",
    "ScoringBackend",
    "WeightedLinearBackend",
]
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_continuous_scorer.py tests/unit/test_feature_pipeline.py tests/unit/test_scoring_backend.py -v`
Expected: all tests PASS

- [ ] **Step 4: Run existing regime detector tests to confirm no regressions**

Run: `python -m pytest tests/unit/test_regime_detector.py -v`
Expected: all existing tests still PASS

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/regime/continuous_scorer.py quant/analysis/regime/__init__.py
git commit -m "feat: implement ContinuousRegimeScorer with score-to-regime mapping"
```

---

### Task 8: RegimeValidator integration

**Files:**
- Modify: `quant/analysis/regime/regime_validator.py:491-570` (extend `compare_all_us_stocks`)
- Modify: `quant/analysis/regime/regime_validator.py:939-1023` (extend CLI)

- [ ] **Step 1: Add `validate_us_stocks_continuous` method**

Add this method to the `RegimeValidator` class, after the existing `validate_us_stocks_combined` method (after line 395):

```python
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

            import numpy as np
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
```

- [ ] **Step 2: Add import for Optional at top of file (if not already present)**

Check line 7 of `regime_validator.py` — `Optional` is already imported. No change needed.

- [ ] **Step 3: Extend `compare_all_us_stocks` to include continuous**

In `compare_all_us_stocks`, after the combined classifier block (around line 564), add:

```python
        # --- Continuous ---
        from quant.analysis.regime.continuous_scorer import ContinuousRegimeScorer
        from quant.analysis.regime.feature_pipeline import FeaturePipeline

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
```

And update the return statement to include `"continuous"`:

```python
        return {
            "level": self._compute_statistics("us_stocks", benchmark, forward_days, level_calls, level_fwd),
            "momentum": self._compute_statistics("us_stocks", benchmark, forward_days, mom_calls, mom_fwd),
            "combined": self._compute_statistics("us_stocks", benchmark, forward_days, comb_calls, comb_fwd),
            "continuous": self._compute_statistics("us_stocks", benchmark, forward_days, cont_calls, cont_fwd),
        }
```

- [ ] **Step 4: Extend CLI to support continuous mode**

In the CLI section (around line 948), update the `--mode` choices:

```python
    parser.add_argument("--mode", choices=["level", "momentum", "combined", "continuous", "compare"],
                        default="compare", help="Which classifier to validate")
    parser.add_argument("--optimize", action="store_true",
                        help="Run grid search to optimize continuous scorer weights")
    parser.add_argument("--weights-path", default=None,
                        help="Path to save/load optimized weights")
```

Add the continuous mode handler in the `else` block (around line 977):

```python
        elif args.mode == "continuous":
            results["continuous"] = validator.validate_us_stocks_continuous(
                lookback_years=args.years, forward_days=args.forward_days,
                eval_frequency=args.frequency, benchmark=args.benchmark,
                optimize_weights=args.optimize, weights_path=args.weights_path,
            )
```

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/unit/test_regime_detector.py tests/unit/test_feature_pipeline.py tests/unit/test_scoring_backend.py tests/unit/test_continuous_scorer.py -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add quant/analysis/regime/regime_validator.py
git commit -m "feat: integrate ContinuousRegimeScorer into RegimeValidator with 4-way comparison"
```
