"""Combine A-layer multiplier with B-layer weights into final positions."""
from __future__ import annotations


class PortfolioCombiner:
    """Compose ``multiplier × weights`` into a final position dict."""

    def combine(
        self,
        weights: dict[str, float],
        multiplier: float,
    ) -> dict[str, float]:
        """Return ``{symbol: final_position}``.

        Empty ``weights`` always maps to an empty result regardless of multiplier
        (B has decided no opportunities).  ``multiplier`` must lie in ``[0, 1]``.
        """
        if not 0.0 <= multiplier <= 1.0:
            raise ValueError(f"multiplier must be in [0, 1], got {multiplier}")
        if not weights:
            return {}
        return {symbol: weight * multiplier for symbol, weight in weights.items()}
