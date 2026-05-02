# XGBoost MLBackend Design

**Date:** 2026-04-18
**Status:** Approved

## Background

The existing `WeightedLinearBackend` uses a fixed-weight linear model optimized via grid search. Testing on 5-year data revealed severe overfitting (train/test gap 25.1%, test hit rate 40.8%) because a single global weight vector cannot adapt to market regime changes across cycles. This design introduces `XGBoostBackend` to capture non-linear feature interactions while using walk-forward CV to produce honest generalization estimates.

## Architecture

`XGBoostBackend` is added to `quant/analysis/regime/scoring_backend.py` alongside `WeightedLinearBackend`, implementing the same `ScoringBackend` ABC:

```
ScoringBackend (ABC)
├── WeightedLinearBackend   ← existing
└── XGBoostBackend          ← new
```

`ContinuousRegimeScorer` accepts any `ScoringBackend` instance — no changes needed to swap in `XGBoostBackend`.

## Training Objective

**Regression mode**: XGBoost predicts forward return directly. Output is compressed to `[-1, +1]` via `tanh(pred * scale_factor)`, where `scale_factor=20` matches the existing scaling convention. This preserves return magnitude in the signal, unlike a binary classifier which discards it.

## `score(features: Dict[str, float]) -> float`

- Convert feature dict to numpy vector (ordered by `feature_names` from `fit()`)
- Call `xgb.predict([x])[0]` to get predicted forward return
- Return `tanh(pred * 20)`
- Raises `RuntimeError` if called before `fit()`

## `fit(feature_names, feature_matrix, forward_returns, **kwargs) -> Dict`

Two-phase process:

### Phase 1 — Walk-forward CV (evaluation)

Expanding-window cross-validation with:
- Minimum training samples: 24
- Step size: 6 (monthly data → 6-month test windows)
- Folds: generated until data is exhausted (~4–6 folds on 60 samples)

```
Fold 1: train [0:24],  test [24:30]
Fold 2: train [0:30],  test [30:36]
Fold 3: train [0:36],  test [36:42]
...
```

Each fold trains a fresh XGBoost model, predicts on the test window, computes hit rate using the same threshold logic as `WeightedLinearBackend._compute_hit_rate()` (|score| > 0.2 counts, transition zone excluded).

Reports: per-fold hit rates, mean CV hit rate (`test_hit_rate`).

### Phase 2 — Final model (production)

After CV, retrain on **full dataset** `[0:n]` to produce the model used by `score()`. `feature_names` is stored as instance state so `score()` can reconstruct the input vector in the correct order.

Return dict:
```python
{
    "train_hit_rate": float,   # hit rate on full training set
    "test_hit_rate": float,    # mean CV test hit rate across folds
    "n_folds": int,
    "fold_details": [{"fold": int, "train_n": int, "test_n": int, "hit_rate": float}, ...]
}
```

Logs a warning if `test_hit_rate < 0.50` (below random).

## Hyperparameters (fixed)

```python
XGBRegressor(
    max_depth=3,
    n_estimators=100,
    learning_rate=0.1,
    reg_lambda=1.5,
    subsample=0.8,
    random_state=42,
    n_jobs=1,
)
```

Shallow trees (`max_depth=3`) and L2 regularization (`reg_lambda=1.5`) are the primary overfitting controls given ~60 monthly samples.

## Testing

File: `tests/unit/test_xgboost_backend.py`

| Test | Description |
|------|-------------|
| `test_score_before_fit_raises` | `score()` raises `RuntimeError` before `fit()` |
| `test_fit_returns_expected_keys` | result has `train_hit_rate`, `test_hit_rate`, `n_folds`, `fold_details` |
| `test_score_in_range` | after `fit()`, `score()` returns value in `[-1, +1]` |
| `test_walk_forward_fold_count` | n=60, step=6, min_train=24 → expect 4–6 folds |
| `test_integration_with_continuous_scorer` | `ContinuousRegimeScorer(backend=XGBoostBackend())` returns valid `RegimeState` after fit |

All tests use synthetic numpy arrays; no real data dependency.

## Constraints

- No model persistence (no save/load); retrain on each run
- Feature importance-based drivers deferred to a future task
- Only `us_stocks` pool tested initially (same as existing `ContinuousRegimeScorer`)
