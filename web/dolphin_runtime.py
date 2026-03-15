"""
Thin Dolphin runtime bootstrap for web entrypoints.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any, Dict

from web.dolphin_compat import apply_dolphin_web_compat
from web.skillkits.registry import register_all_skillkits

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DOLPHIN_CONFIG_PATH = PROJECT_ROOT / "config" / "dolphin.yaml"

_runtime: Dict[str, Any] | None = None
_runtime_lock = threading.Lock()


def get_dolphin_runtime() -> Dict[str, Any]:
    """Initialize and return the shared Dolphin runtime."""
    global _runtime

    if _runtime is not None:
        return _runtime

    with _runtime_lock:
        if _runtime is not None:
            return _runtime

        try:
            from dolphin.core.config.global_config import GlobalConfig
            from dolphin.sdk.skill.global_skills import GlobalSkills
        except ImportError as exc:
            raise RuntimeError(f"Dolphin SDK not available: {exc}") from exc

        apply_dolphin_web_compat()

        if DOLPHIN_CONFIG_PATH.exists():
            global_config = GlobalConfig.from_yaml(str(DOLPHIN_CONFIG_PATH))
            logger.info("Loaded Dolphin config from %s", DOLPHIN_CONFIG_PATH)
        else:
            global_config = GlobalConfig.from_dict({})
            logger.warning("Dolphin config not found, using empty config")

        global_skills = GlobalSkills(global_config)
        register_all_skillkits(global_skills, global_config, logger)

        _runtime = {
            "global_config": global_config,
            "global_skills": global_skills,
        }
        return _runtime


async def get_dolphin_runtime_async() -> Dict[str, Any]:
    """Async wrapper for web handlers that already run in an event loop."""
    return await asyncio.to_thread(get_dolphin_runtime)
