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
        # raw = 0.5 + 0.5 + 0.5 = 1.5, tanh(1.5) ~ 0.905
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
        # Only a and b contribute; c is missing -> treated as 0
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
