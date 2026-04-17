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

    def test_shape_mismatch_raises_value_error(self):
        feature_names, X, y = _make_data(n_features=6)
        backend = XGBoostBackend()
        wrong_names = feature_names[:4]  # 4 names, 6 columns
        with pytest.raises(ValueError, match="feature_matrix has 6 columns"):
            backend.fit(wrong_names, X, y)

    def test_score_raises_after_failed_fit(self):
        feature_names, X, y = _make_data(n_features=6)
        backend = XGBoostBackend()
        with pytest.raises(ValueError):
            backend.fit(feature_names[:4], X, y)  # fail due to shape mismatch
        with pytest.raises(RuntimeError, match="before fit"):
            backend.score({n: 0.1 for n in feature_names})

    def test_no_warning_when_no_folds(self, caplog):
        # n=20 < min_train=24 → no folds → test_hr=0.0, but no warning should fire
        import logging
        feature_names, X, y = _make_data(n=20)
        backend = XGBoostBackend()
        with caplog.at_level(logging.WARNING):
            result = backend.fit(feature_names, X, y)
        assert result["n_folds"] == 0
        assert result["test_hit_rate"] == 0.0
        assert "below 0.50" not in caplog.text


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
        score = backend.score({feature_names[0]: 0.5})
        assert -1.0 <= score <= 1.0

    def test_bullish_features_give_positive_score(self):
        rng = np.random.RandomState(0)
        n = 60
        feature_names = ["bull", "noise"]
        X = rng.randn(n, 2)
        y = X[:, 0] * 0.5
        backend = XGBoostBackend()
        backend.fit(feature_names, X, y)
        score = backend.score({"bull": 1.0, "noise": 0.0})
        assert score > 0, f"Expected positive score for bullish features, got {score}"

    def test_bearish_features_give_negative_score(self):
        rng = np.random.RandomState(1)
        n = 60
        feature_names = ["bear", "noise"]
        X = rng.randn(n, 2)
        y = -X[:, 0] * 0.5
        backend = XGBoostBackend()
        backend.fit(feature_names, X, y)
        score = backend.score({"bear": 1.0, "noise": 0.0})
        assert score < 0, f"Expected negative score for bearish features, got {score}"
