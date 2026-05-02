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

    score = tanh(sum(weight_i * feature_i))
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
        self._model = None
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
        self._model = None
        self._feature_names = None
        n = len(forward_returns)

        if feature_matrix.shape[1] != len(feature_names):
            raise ValueError(
                f"feature_matrix has {feature_matrix.shape[1]} columns "
                f"but {len(feature_names)} feature names were provided"
            )

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

        if fold_details and test_hr < 0.50:
            logger.warning(
                f"XGBoostBackend CV test hit rate {test_hr:.3f} is below 0.50 (random baseline)"
            )

        self._feature_names = list(feature_names)
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
    def _make_model():
        from xgboost import XGBRegressor  # deferred — xgboost is optional dependency
        return XGBRegressor(
            max_depth=3,
            n_estimators=100,
            learning_rate=0.1,
            reg_lambda=1.5,
            subsample=0.8,
            random_state=42,
            n_jobs=1,
        )
