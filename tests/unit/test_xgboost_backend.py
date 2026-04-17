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
