# XGBoost MLBackend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `XGBoostBackend` to `scoring_backend.py` that trains an XGBoost regressor via walk-forward CV and exposes the same `ScoringBackend` interface as `WeightedLinearBackend`.

**Architecture:** `XGBoostBackend` implements `ScoringBackend` ABC. `fit()` runs expanding-window walk-forward CV to report honest generalization metrics, then retrains on the full dataset for production use. `score()` calls `tanh(pred * 20)` to compress the predicted return to `[-1, +1]`.

**Tech Stack:** Python 3.12, xgboost>=1.7.0, numpy, existing `ScoringBackend` ABC

**Spec:** `docs/superpowers/specs/2026-04-18-xgboost-mlbackend-design.md`

---

## File Map

| File | Change |
|------|--------|
| `pyproject.toml` | Add `xgboost>=1.7.0` to core dependencies |
| `quant/analysis/regime/scoring_backend.py` | Add `XGBoostBackend` class (append after `WeightedLinearBackend`) |
| `tests/unit/test_xgboost_backend.py` | Create new test file |

---

### Task 1: Add xgboost dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add xgboost to core dependencies**

In `pyproject.toml`, add `"xgboost>=1.7.0",` to the `dependencies` list, after the `scipy` line:

```toml
    # Scientific computing (for regression analysis)
    "scipy>=1.9.0",

    # ML backend for regime scoring
    "xgboost>=1.7.0",
```

- [ ] **Step 2: Sync dependencies**

```bash
uv sync
```

Expected: installs xgboost (already present in environment, so fast).

- [ ] **Step 3: Verify import**

```bash
python -c "import xgboost; print(xgboost.__version__)"
```

Expected: prints a version string like `2.x.x`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add xgboost dependency for MLBackend"
```

---

### Task 2: XGBoostBackend skeleton — score-before-fit raises RuntimeError

**Files:**
- Modify: `quant/analysis/regime/scoring_backend.py`
- Create: `tests/unit/test_xgboost_backend.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_xgboost_backend.py`:

```python
#!/usr/bin/env python3
"""Tests for XGBoostBackend."""

import numpy as np
import pytest

from quant.analysis.regime.scoring_backend import ScoringBackend, XGBoostBackend


def _make_data(n=60, n_features=6, seed=42):
    """Synthetic feature matrix and forward returns for testing."""
    rng = np.random.RandomState(seed)
    feature_matrix = rng.randn(n, n_features)
    forward_returns = feature_matrix[:, 0] * 0.01 + rng.randn(n) * 0.005
    feature_names = [f"feat_{i}" for i in range(n_features)]
    return feature_names, feature_matrix, forward_returns


class TestXGBoostBackendInit:
    def test_score_before_fit_raises(self):
        backend = XGBoostBackend()
        with pytest.raises(RuntimeError, match="before fit"):
            backend.score({"feat_0": 0.5})

    def test_is_scoring_backend(self):
        assert isinstance(XGBoostBackend(), ScoringBackend)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/test_xgboost_backend.py -v
```

Expected: `ImportError: cannot import name 'XGBoostBackend'`

- [ ] **Step 3: Add XGBoostBackend skeleton to scoring_backend.py**

At the top of `scoring_backend.py`, add `XGBRegressor` to imports (after existing imports):

```python
from xgboost import XGBRegressor
```

Append the following class after `WeightedLinearBackend`:

```python
class XGBoostBackend(ScoringBackend):
    """
    XGBoost regression backend for regime scoring.

    fit() uses expanding walk-forward CV to evaluate generalization,
    then retrains on the full dataset for production use.
    score() returns tanh(predicted_return * 20) in [-1, +1].
    """

    _SCALE: float = 20.0
    _HIT_THRESHOLD: float = 0.2
    _MIN_TRAIN: int = 24
    _STEP: int = 6

    def __init__(self) -> None:
        self._model: Optional[XGBRegressor] = None
        self._feature_names: Optional[List[str]] = None

    def score(self, features: Dict[str, float]) -> float:
        if self._model is None:
            raise RuntimeError(
                "XGBoostBackend.score() called before fit(). Call fit() first."
            )
        x = np.array(
            [features.get(n, 0.0) for n in self._feature_names], dtype=float
        ).reshape(1, -1)
        pred = float(self._model.predict(x)[0])
        return math.tanh(pred * self._SCALE)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/test_xgboost_backend.py::TestXGBoostBackendInit -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/regime/scoring_backend.py tests/unit/test_xgboost_backend.py
git commit -m "feat: add XGBoostBackend skeleton with score-before-fit guard"
```

---

### Task 3: fit() — walk-forward CV + return structure

**Files:**
- Modify: `quant/analysis/regime/scoring_backend.py`
- Modify: `tests/unit/test_xgboost_backend.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_xgboost_backend.py`:

```python
class TestXGBoostBackendFit:
    def test_fit_returns_expected_keys(self):
        feature_names, X, y = _make_data()
        backend = XGBoostBackend()
        result = backend.fit(feature_names, X, y)
        assert set(result.keys()) == {"train_hit_rate", "test_hit_rate", "n_folds", "fold_details"}

    def test_hit_rates_in_valid_range(self):
        feature_names, X, y = _make_data()
        backend = XGBoostBackend()
        result = backend.fit(feature_names, X, y)
        assert 0.0 <= result["train_hit_rate"] <= 1.0
        assert 0.0 <= result["test_hit_rate"] <= 1.0

    def test_walk_forward_fold_count(self):
        # n=60, min_train=24, step=6 → folds starting at 24,30,36,42,48,54 → 6 folds
        feature_names, X, y = _make_data(n=60)
        backend = XGBoostBackend()
        result = backend.fit(feature_names, X, y)
        assert result["n_folds"] == 6

    def test_fold_details_structure(self):
        feature_names, X, y = _make_data()
        backend = XGBoostBackend()
        result = backend.fit(feature_names, X, y)
        for fold in result["fold_details"]:
            assert set(fold.keys()) == {"fold", "train_n", "test_n", "hit_rate"}
            assert 0.0 <= fold["hit_rate"] <= 1.0

    def test_fewer_samples_fewer_folds(self):
        # n=30, min_train=24, step=6 → only fold (24,30) → 1 fold
        feature_names, X, y = _make_data(n=30)
        backend = XGBoostBackend()
        result = backend.fit(feature_names, X, y)
        assert result["n_folds"] == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/test_xgboost_backend.py::TestXGBoostBackendFit -v
```

Expected: all 5 FAIL — `fit()` currently inherits the no-op from `ScoringBackend`

- [ ] **Step 3: Implement fit() and helpers in XGBoostBackend**

Replace the `XGBoostBackend` class body in `scoring_backend.py` with the full implementation. The complete class (replacing the skeleton from Task 2) should read:

```python
class XGBoostBackend(ScoringBackend):
    """
    XGBoost regression backend for regime scoring.

    fit() uses expanding walk-forward CV to evaluate generalization,
    then retrains on the full dataset for production use.
    score() returns tanh(predicted_return * 20) in [-1, +1].
    """

    _SCALE: float = 20.0
    _HIT_THRESHOLD: float = 0.2
    _MIN_TRAIN: int = 24
    _STEP: int = 6

    def __init__(self) -> None:
        self._model: Optional[XGBRegressor] = None
        self._feature_names: Optional[List[str]] = None

    def score(self, features: Dict[str, float]) -> float:
        if self._model is None:
            raise RuntimeError(
                "XGBoostBackend.score() called before fit(). Call fit() first."
            )
        x = np.array(
            [features.get(n, 0.0) for n in self._feature_names], dtype=float
        ).reshape(1, -1)
        pred = float(self._model.predict(x)[0])
        return math.tanh(pred * self._SCALE)

    def fit(
        self,
        feature_names: List[str],
        feature_matrix: np.ndarray,
        forward_returns: np.ndarray,
        **kwargs,
    ) -> Dict:
        self._feature_names = list(feature_names)
        n = len(forward_returns)

        # Phase 1: walk-forward CV for evaluation
        folds = self._walk_forward_folds(n)
        fold_details = []
        for i, (train_end, test_end) in enumerate(folds):
            X_tr = feature_matrix[:train_end]
            y_tr = forward_returns[:train_end]
            X_te = feature_matrix[train_end:test_end]
            y_te = forward_returns[train_end:test_end]

            fold_model = self._make_model()
            fold_model.fit(X_tr, y_tr)
            preds = fold_model.predict(X_te)
            scores = np.tanh(preds * self._SCALE)
            hr = self._hit_rate(scores, y_te)
            fold_details.append({
                "fold": i + 1,
                "train_n": train_end,
                "test_n": test_end - train_end,
                "hit_rate": round(hr, 4),
            })

        # Phase 2: final model on full dataset (for production score())
        self._model = self._make_model()
        self._model.fit(feature_matrix, forward_returns)

        train_preds = self._model.predict(feature_matrix)
        train_scores = np.tanh(train_preds * self._SCALE)
        train_hr = self._hit_rate(train_scores, forward_returns)

        test_hr = float(np.mean([f["hit_rate"] for f in fold_details])) if fold_details else 0.0

        if test_hr < 0.50:
            logger.warning(
                f"XGBoostBackend CV test hit rate {test_hr:.3f} is below 0.50 (random baseline)"
            )

        return {
            "train_hit_rate": round(train_hr, 4),
            "test_hit_rate": round(test_hr, 4),
            "n_folds": len(fold_details),
            "fold_details": fold_details,
        }

    @classmethod
    def _walk_forward_folds(cls, n: int) -> List[Tuple[int, int]]:
        folds = []
        train_end = cls._MIN_TRAIN
        while train_end + cls._STEP <= n:
            folds.append((train_end, train_end + cls._STEP))
            train_end += cls._STEP
        return folds

    @classmethod
    def _hit_rate(cls, scores: np.ndarray, returns: np.ndarray) -> float:
        hits = total = 0
        for s, r in zip(scores, returns):
            if s > cls._HIT_THRESHOLD:
                total += 1
                if r > 0:
                    hits += 1
            elif s < -cls._HIT_THRESHOLD:
                total += 1
                if r < 0:
                    hits += 1
        return hits / total if total > 0 else 0.0

    @staticmethod
    def _make_model() -> XGBRegressor:
        return XGBRegressor(
            max_depth=3,
            n_estimators=100,
            learning_rate=0.1,
            reg_lambda=1.5,
            subsample=0.8,
            random_state=42,
            n_jobs=1,
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/test_xgboost_backend.py::TestXGBoostBackendFit -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add quant/analysis/regime/scoring_backend.py tests/unit/test_xgboost_backend.py
git commit -m "feat: implement XGBoostBackend.fit() with walk-forward CV"
```

---

### Task 4: score() after fit — value range and signal direction tests

**Files:**
- Modify: `tests/unit/test_xgboost_backend.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_xgboost_backend.py`:

```python
class TestXGBoostBackendScore:
    def test_score_in_range_after_fit(self):
        feature_names, X, y = _make_data()
        backend = XGBoostBackend()
        backend.fit(feature_names, X, y)
        score = backend.score({n: 0.3 for n in feature_names})
        assert -1.0 <= score <= 1.0

    def test_score_missing_feature_defaults_to_zero(self):
        feature_names, X, y = _make_data()
        backend = XGBoostBackend()
        backend.fit(feature_names, X, y)
        # Only supply one feature; the rest default to 0.0
        score = backend.score({feature_names[0]: 0.5})
        assert -1.0 <= score <= 1.0

    def test_bullish_features_give_positive_score(self):
        # Feature 0 is strongly positively correlated with returns — no noise
        rng = np.random.RandomState(0)
        n = 60
        feature_names = ["bull", "noise"]
        X = rng.randn(n, 2)
        y = X[:, 0] * 0.5   # strong, clean signal
        backend = XGBoostBackend()
        backend.fit(feature_names, X, y)
        score = backend.score({"bull": 1.0, "noise": 0.0})
        assert score > 0, f"Expected positive score for bullish features, got {score}"

    def test_bearish_features_give_negative_score(self):
        rng = np.random.RandomState(1)
        n = 60
        feature_names = ["bear", "noise"]
        X = rng.randn(n, 2)
        y = -X[:, 0] * 0.5  # strong, clean negative signal
        backend = XGBoostBackend()
        backend.fit(feature_names, X, y)
        score = backend.score({"bear": 1.0, "noise": 0.0})
        assert score < 0, f"Expected negative score for bearish features, got {score}"
```

- [ ] **Step 2: Run tests to confirm they pass**

```bash
pytest tests/unit/test_xgboost_backend.py::TestXGBoostBackendScore -v
```

Expected: 4 passed (score() was already implemented in Task 3)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_xgboost_backend.py
git commit -m "test: add score() value-range and signal-direction tests for XGBoostBackend"
```

---

### Task 5: Integration test with ContinuousRegimeScorer

**Files:**
- Modify: `tests/unit/test_xgboost_backend.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_xgboost_backend.py`:

```python
class TestXGBoostBackendIntegration:
    def test_scorer_returns_valid_regime_state(self):
        """XGBoostBackend plugs into ContinuousRegimeScorer without errors."""
        from quant.analysis.regime.continuous_scorer import ContinuousRegimeScorer

        feature_names = [
            "vix_level", "vix_roc", "cs_level", "cs_change",
            "yc_level", "yc_change", "price_vs_ma200", "ma50_vs_ma200", "rsi",
        ]
        rng = np.random.RandomState(0)
        n = 60
        X = rng.uniform(-1, 1, (n, len(feature_names)))
        y = rng.randn(n) * 0.01

        backend = XGBoostBackend()
        backend.fit(feature_names, X, y)

        # Mock pipeline so we can test scorer without real market data
        class _MockPipeline:
            @property
            def feature_names(self):
                return feature_names

            def compute(self, series, eval_idx=-1):
                return {name: 0.3 for name in feature_names}

        scorer = ContinuousRegimeScorer(
            pool="us_stocks",
            backend=backend,
            pipeline=_MockPipeline(),
        )
        state = scorer.classify({})

        assert state.pool == "us_stocks"
        assert state.regime in ("expansion", "contraction", "transition")
        assert 0.0 <= state.confidence <= 1.0
        assert len(state.drivers) > 0
```

- [ ] **Step 2: Run test to confirm it passes**

```bash
pytest tests/unit/test_xgboost_backend.py::TestXGBoostBackendIntegration -v
```

Expected: 1 passed

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
pytest tests/unit/test_xgboost_backend.py tests/unit/test_scoring_backend.py -v
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_xgboost_backend.py
git commit -m "test: add integration test for XGBoostBackend with ContinuousRegimeScorer"
```
