#!/usr/bin/env python3
"""Backfill experiments/history.json from existing .petri/runs/run-XXX verdicts.

Scans `.petri/runs/run-*/artifacts/*/reviewer/verdict.json`, picks the latest
verdict per run (highest attempt index), and writes a chronologically sorted
history file consumed by the reviewer playbook for the
`regression_vs_last_keep_pp` check.

Idempotent: rewrites history.json from scratch each invocation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = REPO_ROOT / ".petri" / "runs"
HISTORY_PATH = REPO_ROOT / "experiments" / "history.json"


def _latest_verdict(run_dir: Path) -> Path | None:
    artifacts = run_dir / "artifacts"
    if not artifacts.is_dir():
        return None
    candidates = sorted(
        artifacts.glob("*/reviewer/verdict.json"),
        key=lambda p: p.parent.parent.name,
    )
    return candidates[-1] if candidates else None


def _started_at(run_dir: Path) -> str | None:
    run_json = run_dir / "run.json"
    if not run_json.is_file():
        return None
    try:
        return json.loads(run_json.read_text()).get("startedAt")
    except json.JSONDecodeError:
        return None


def _hypothesis(verdict: dict) -> str:
    return (verdict.get("strategy_summary") or {}).get("hypothesis", "")[:200]


def _mode(verdict: dict, key: str, field: str):
    mode = (
        (verdict.get("results") or {})
        .get("per_mode_comparison", {})
        .get(key, {})
    )
    if mode.get("status") and mode["status"] != "success":
        return None
    return mode.get(field)


def build_history() -> dict:
    entries = []
    for run_dir in sorted(RUNS_DIR.glob("run-*")):
        verdict_path = _latest_verdict(run_dir)
        if not verdict_path:
            continue
        try:
            verdict = json.loads(verdict_path.read_text())
        except json.JSONDecodeError:
            continue
        entries.append({
            "run_id": run_dir.name,
            "started_at": _started_at(run_dir),
            "decision": verdict.get("decision"),
            "hypothesis": _hypothesis(verdict),
            "index_proxy_annual_return": _mode(verdict, "index_proxy", "candidate_annual_return"),
            "index_proxy_mdd": _mode(verdict, "index_proxy", "candidate_mdd"),
            "real_etf_full_annual_return": _mode(verdict, "real_etf_full", "candidate_annual_return"),
            "real_etf_full_mdd": _mode(verdict, "real_etf_full", "candidate_mdd"),
            "real_etf_subset_annual_return": _mode(verdict, "real_etf_subset", "candidate_annual_return"),
            "real_etf_subset_mdd": _mode(verdict, "real_etf_subset", "candidate_mdd"),
            "long_proxy_coverage_years": (verdict.get("results") or {}).get("long_proxy_coverage_years"),
        })
    def _sort_key(e: dict) -> tuple:
        m = re.search(r"(\d+)$", e["run_id"])
        return (int(m.group(1)) if m else 1_000_000, e["run_id"])

    entries.sort(key=_sort_key)
    return {"experiments": entries, "total_experiments": len(entries)}


def main() -> None:
    history = build_history()
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n")
    keep_count = sum(1 for e in history["experiments"] if e["decision"] == "KEEP")
    print(f"wrote {HISTORY_PATH} | total={history['total_experiments']} keep={keep_count}")


if __name__ == "__main__":
    main()
