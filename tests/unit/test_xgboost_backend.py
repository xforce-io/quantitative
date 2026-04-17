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
