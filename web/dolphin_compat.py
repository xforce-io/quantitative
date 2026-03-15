"""
Dolphin compatibility helpers for web runtimes.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_dolphin_web_compat() -> None:
    """Apply minimal Dolphin runtime compatibility for web usage."""
    try:
        from dolphin.core import flags

        flags.set_flag(flags.EXPLORE_BLOCK_V2, False)
    except ImportError:
        logger.debug("Dolphin SDK is not available while applying compat settings")
    except Exception as exc:
        logger.warning("Failed to apply Dolphin web compatibility: %s", exc)
