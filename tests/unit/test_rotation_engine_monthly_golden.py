"""Golden test: run-007 production spec at frequency=monthly must reproduce
the published SOTA metrics within 0.01pp.

This is the one-vote-veto for the frequency-parameterized engine refactor.
If this test fails, the refactor has changed monthly-path behavior and is
considered broken.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = _ROOT / "tests" / "fixtures" / "run_007_monthly_baseline.json"
_SPEC = _ROOT / "config" / "strategies" / "rotation" / "run_007_production.json"

# Mapping from fixture's metric short-keys to backtest output keys.
_METRIC_KEY_MAP = {
    "annual_return": "candidate_oos_annual_return",
    "mdd": "candidate_oos_max_drawdown",
}


@pytest.mark.slow
def test_run_007_monthly_reproduces_baseline(tmp_path: Path) -> None:
    output_path = tmp_path / "run_007_golden.json"

    cmd = [
        ".venv/bin/python",
        "scripts/long_rotation_discovery.py",
        "--mode", "candidate",
        "--params-file", str(_SPEC),
        "--frequency", "monthly",
        "--output", str(output_path),
    ]
    result = subprocess.run(
        cmd, cwd=str(_ROOT), capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"Backtest failed (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout[-2000:]}\n"
        f"stderr:\n{result.stderr[-2000:]}"
    )

    with output_path.open() as f:
        actual = json.load(f)
    with _FIXTURE.open() as f:
        baseline = json.load(f)

    tolerance = baseline["tolerance_pp"] / 100.0
    failures: list[str] = []
    universes = baseline["expected_metrics"]
    for universe, expected_metrics in universes.items():
        actual_universe = actual.get("results", {}).get(universe)
        assert actual_universe is not None, (
            f"Missing universe in output: results.{universe}"
        )
        for short_key, expected_value in expected_metrics.items():
            output_key = _METRIC_KEY_MAP[short_key]
            actual_value = actual_universe.get(output_key)
            if actual_value is None:
                failures.append(
                    f"{universe}.{output_key}: missing in output"
                )
                continue
            delta = abs(actual_value - expected_value)
            if delta > tolerance:
                failures.append(
                    f"{universe}.{output_key}: expected {expected_value}, "
                    f"got {actual_value} (delta {actual_value - expected_value:+.4f}, "
                    f"tolerance {tolerance})"
                )

    assert not failures, "Golden test failed — refactor changed monthly behavior:\n" + "\n".join(failures)
