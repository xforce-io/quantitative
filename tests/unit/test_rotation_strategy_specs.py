"""Tests for published rotation strategy specifications."""
from __future__ import annotations

import json
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_SOTA_PATH = _ROOT / "config" / "strategies" / "rotation" / "sota.json"


def test_sota_points_to_existing_strategy_spec() -> None:
    """SOTA metadata must point to a readable strategy spec."""
    sota = json.loads(_SOTA_PATH.read_text(encoding="utf-8"))
    spec_path = _ROOT / sota["strategy_path"]

    assert spec_path.exists()

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["strategy_id"] == sota["current_sota_strategy"]
    assert spec["status"] == "production_baseline"


def test_run_007_spec_uses_only_live_ready_risk_on_factors() -> None:
    """Production baseline must not depend on delayed fund_share factors."""
    sota = json.loads(_SOTA_PATH.read_text(encoding="utf-8"))
    spec = json.loads((_ROOT / sota["strategy_path"]).read_text(encoding="utf-8"))

    factors = spec["risk_on_allocation"]["multi_factor_config"]["factors"]
    factor_names = {factor["name"] for factor in factors}

    assert factor_names == {"momentum", "low_volatility", "relative_strength"}
    assert "shares_momentum" not in factor_names
    assert spec["validation"]["decision"] == "KEEP"
