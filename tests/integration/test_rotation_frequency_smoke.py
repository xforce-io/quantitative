"""Smoke tests: engine runs at biweekly and weekly without exceptions.

These tests do NOT compare against a fixture — we don't yet know the "right"
weekly numbers. They only assert: (1) the engine runs end-to-end, (2) results
are finite, (3) numbers fall within loose sanity bands.

Note: the run-007 spec has ``risk_on_allocation.rebalance_frequency = "monthly"``
which the CLI overrides when ``--frequency`` is provided. For biweekly/weekly
runs we write a patched copy of the spec into tmp_path with the target
frequency substituted, so the engine actually exercises the non-monthly path.
"""
from __future__ import annotations

import copy
import json
import math
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SPEC = _ROOT / "config" / "strategies" / "rotation" / "run_007_production.json"


@pytest.mark.slow
@pytest.mark.parametrize("frequency", ["biweekly", "weekly"])
def test_engine_runs_at_higher_frequency(frequency: str, tmp_path: Path) -> None:
    # Build a patched spec that sets the target frequency so the engine
    # exercises the non-monthly rebalance path (the spec value takes priority
    # over the CLI --frequency flag for multi_sleeve_rotation strategies).
    with _SPEC.open() as f:
        spec = json.load(f)

    patched_spec = copy.deepcopy(spec)
    patched_spec["risk_on_allocation"]["rebalance_frequency"] = frequency

    patched_spec_path = tmp_path / f"run_007_{frequency}.json"
    patched_spec_path.write_text(json.dumps(patched_spec, indent=2, ensure_ascii=False))

    output_path = tmp_path / f"smoke_{frequency}.json"
    cmd = [
        ".venv/bin/python",
        "scripts/long_rotation_discovery.py",
        "--mode", "candidate",
        "--params-file", str(patched_spec_path),
        "--frequency", frequency,
        "--output", str(output_path),
    ]
    result = subprocess.run(
        cmd, cwd=str(_ROOT), capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"{frequency} run failed (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout[-2000:]}\n"
        f"stderr:\n{result.stderr[-2000:]}"
    )

    with output_path.open() as f:
        data = json.load(f)

    for universe in ("index_proxy", "real_etf_full", "real_etf_subset"):
        univ = data.get("results", {}).get(universe)
        assert univ is not None, f"Missing universe {universe} in {frequency} output"

        ar = univ.get("candidate_oos_annual_return")
        mdd = univ.get("candidate_oos_max_drawdown")
        assert ar is not None, f"{frequency}/{universe}: missing annual_return"
        assert mdd is not None, f"{frequency}/{universe}: missing max_drawdown"
        assert math.isfinite(ar), f"{frequency}/{universe}: annual_return not finite ({ar})"
        assert math.isfinite(mdd), f"{frequency}/{universe}: max_drawdown not finite ({mdd})"

        # Sanity bands.
        assert -0.50 < ar < 1.00, (
            f"{frequency}/{universe}: annual_return={ar} outside sanity band [-0.50, 1.00]"
        )
        assert -0.60 < mdd <= 0.0, (
            f"{frequency}/{universe}: max_drawdown={mdd} outside sanity band (-0.60, 0.0]"
        )
