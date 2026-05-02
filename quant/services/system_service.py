"""System status service shared by command-line and web entrypoints."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

from quant import __version__


@dataclass(frozen=True)
class SystemStatus:
    """Structured system status result."""

    version: str
    environment: Dict[str, bool]
    directories: Dict[str, bool]
    config_files: Dict[str, bool]


class SystemService:
    """Provide system health and environment checks."""

    DEFAULT_DIRECTORIES = ("data", "cache", "logs", "reports", "config")
    DEFAULT_CONFIG_FILES = (
        "config/config.yaml",
        "config/portfolios.yaml",
        "config/screens.yaml",
    )

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[2]

    def get_status(
        self,
        directories: Iterable[str] | None = None,
        config_files: Iterable[str] | None = None,
    ) -> SystemStatus:
        """Return structured status for the project runtime."""
        directory_names = tuple(directories or self.DEFAULT_DIRECTORIES)
        config_names = tuple(config_files or self.DEFAULT_CONFIG_FILES)

        return SystemStatus(
            version=__version__,
            environment={
                "TUSHARE_TOKEN": bool(os.getenv("TUSHARE_TOKEN")),
            },
            directories={
                name: (self.project_root / name).exists()
                for name in directory_names
            },
            config_files={
                name: (self.project_root / name).exists()
                for name in config_names
            },
        )
