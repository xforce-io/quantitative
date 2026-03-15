"""
Centralized Skillkit registration helpers.
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def build_skillkits(global_config) -> List[object]:
    """Build all web skillkits for the current runtime."""
    from web.skillkits.page_data_skillkit import PageDataSkillkit

    skillkits = [
        PageDataSkillkit(),
    ]

    for skillkit in skillkits:
        if hasattr(skillkit, "setGlobalConfig"):
            skillkit.setGlobalConfig(global_config)

    return skillkits


def register_all_skillkits(global_skills, global_config, log: Optional[logging.Logger] = None) -> List[object]:
    """Register all configured skillkits into Dolphin GlobalSkills."""
    active_logger = log or logger
    skillkits = build_skillkits(global_config)

    installed = getattr(global_skills, "installedSkillset", None)
    if installed is None:
        raise RuntimeError("GlobalSkills.installedSkillset is not available")

    for skillkit in skillkits:
        installed.addSkillkit(skillkit)
        active_logger.info("Registered %s", skillkit.__class__.__name__)

    if hasattr(global_skills, "_syncAllSkills"):
        global_skills._syncAllSkills()

    return skillkits
