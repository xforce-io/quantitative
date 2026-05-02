"""Tests for rotation universe loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from quant.analysis.rotation.universe import EtfEntry, load_universe


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "universe.yaml"
    p.write_text(content, encoding="utf-8")
    return p


def test_load_universe_returns_entries(tmp_path: Path) -> None:
    yaml = _write_yaml(
        tmp_path,
        """
        schema_version: 1
        updated_at: "2026-05-02"
        industry_etfs:
          - { symbol: "510050.SH", name: "上证50ETF", category: "大盘" }
          - { symbol: "512000.SH", name: "券商ETF",   category: "金融" }
        style_etfs:
          - { symbol: "510880.SH", name: "红利ETF",   category: "风格-红利" }
        """,
    )
    entries = load_universe(yaml)
    assert len(entries) == 3
    assert entries[0] == EtfEntry(symbol="510050.SH", name="上证50ETF", category="大盘")
    assert {e.symbol for e in entries} == {"510050.SH", "512000.SH", "510880.SH"}


def test_load_universe_rejects_duplicate_symbol(tmp_path: Path) -> None:
    yaml = _write_yaml(
        tmp_path,
        """
        schema_version: 1
        industry_etfs:
          - { symbol: "510050.SH", name: "上证50ETF", category: "大盘" }
          - { symbol: "510050.SH", name: "上证50ETF重复", category: "大盘" }
        """,
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_universe(yaml)


def test_load_universe_rejects_missing_field(tmp_path: Path) -> None:
    yaml = _write_yaml(
        tmp_path,
        """
        schema_version: 1
        industry_etfs:
          - { symbol: "510050.SH", category: "大盘" }
        """,
    )
    with pytest.raises(ValueError, match="missing field"):
        load_universe(yaml)


def test_load_universe_rejects_unknown_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_universe(tmp_path / "does_not_exist.yaml")


def test_load_universe_default_path_loads() -> None:
    """Repo's default config/rotation_universe.yaml must be valid and non-empty."""
    entries = load_universe(None)
    assert len(entries) >= 10
    for e in entries:
        assert "." in e.symbol
        code, suffix = e.symbol.split(".")
        assert code.isdigit() and len(code) == 6
        assert suffix in {"SH", "SZ"}
