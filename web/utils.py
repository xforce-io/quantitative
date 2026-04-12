"""Watchlist config management — load/save watchlist.yaml with pool grouping."""
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

WATCHLIST_FILE = Path(__file__).parent.parent / "config" / "watchlist.yaml"
LEGACY_WATCHLIST_FILE = Path(__file__).parent.parent / "config" / "watchlist.json"
POOLS = ("a_shares", "us_stocks", "gold", "commodities")


def _classify_symbol(symbol: str) -> str:
    """Auto-detect asset pool from symbol format."""
    s = symbol.upper()
    if s.endswith(".SZ") or s.endswith(".SH") or s.endswith(".HK"):
        return "a_shares"
    gold_tickers = {"GLD", "IAU", "GC=F", "SI=F", "SLV"}
    commodity_tickers = {"USO", "CL=F", "HG=F", "DJP", "GSG", "COPX"}
    ticker = s.split(".")[0].split(" ")[0]
    if ticker in gold_tickers:
        return "gold"
    if ticker in commodity_tickers:
        return "commodities"
    return "us_stocks"


def load_watchlist() -> Dict[str, Any]:
    """Load watchlist from YAML. Falls back to legacy JSON if YAML doesn't exist.

    Returns a dict with pool keys (a_shares, us_stocks, gold, commodities,
    industries) plus a backward-compatible 'stocks' key containing the
    legacy "SYMBOL Name" string format used by existing pages.
    """
    if WATCHLIST_FILE.exists():
        with open(WATCHLIST_FILE) as f:
            data = yaml.safe_load(f) or {}
        for pool in POOLS:
            if pool not in data:
                data[pool] = []
        if "industries" not in data:
            data["industries"] = []
        # Backward-compatible 'stocks' list: "SYMBOL Name" strings across all pools
        data["stocks"] = [
            f"{entry['symbol']} {entry['name']}"
            for pool in POOLS
            for entry in data.get(pool, [])
        ]
        return data

    # Legacy fallback: read JSON and migrate to YAML
    if LEGACY_WATCHLIST_FILE.exists():
        import json
        with open(LEGACY_WATCHLIST_FILE) as f:
            old = json.load(f)
        data: Dict[str, Any] = {pool: [] for pool in POOLS}
        data["industries"] = old.get("industries", [])
        for stock_str in old.get("stocks", []):
            parts = stock_str.split(" ", 1)
            symbol = parts[0]
            name = parts[1] if len(parts) > 1 else symbol
            pool = _classify_symbol(symbol)
            data[pool].append({"symbol": symbol, "name": name})
        save_watchlist(data)
        # Reload from YAML now that it's saved (adds 'stocks' key)
        return load_watchlist()

    result: Dict[str, Any] = {pool: [] for pool in POOLS}
    result["industries"] = []
    result["stocks"] = []
    return result


def save_watchlist(data: Dict[str, Any]) -> None:
    """Save watchlist to YAML.

    Accepts both new pool-based dicts and legacy dicts that contain a 'stocks'
    key with "SYMBOL Name" strings — legacy entries are migrated to pools
    before saving so the YAML always uses the canonical pool format.
    """
    WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)

    # If caller passed legacy 'stocks' strings, migrate them into pools first
    if "stocks" in data and isinstance(data.get("stocks"), list):
        migrated: Dict[str, Any] = {pool: list(data.get(pool, [])) for pool in POOLS}
        migrated["industries"] = data.get("industries", [])
        for stock_str in data["stocks"]:
            if isinstance(stock_str, str):
                parts = stock_str.split(" ", 1)
                symbol = parts[0]
                name = parts[1] if len(parts) > 1 else symbol
                pool = _classify_symbol(symbol)
                # Only add if not already present in pool list
                existing = [e["symbol"] for e in migrated.get(pool, [])]
                if symbol not in existing:
                    migrated[pool].append({"symbol": symbol, "name": name})
        yaml_data = migrated
    else:
        # Strip the synthetic 'stocks' key before writing (it's derived, not stored)
        yaml_data = {k: v for k, v in data.items() if k != "stocks"}

    with open(WATCHLIST_FILE, "w") as f:
        yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def add_to_watchlist(symbol: str, name: str, pool: Optional[str] = None) -> str:
    """Add a symbol to watchlist. Auto-detects pool if not specified. Returns pool name."""
    if pool is None:
        pool = _classify_symbol(symbol)
    data = load_watchlist()
    existing = [s["symbol"] for s in data.get(pool, [])]
    if symbol not in existing:
        data[pool].append({"symbol": symbol, "name": name})
        save_watchlist(data)
    return pool


def remove_from_watchlist(symbol: str) -> bool:
    """Remove a symbol from watchlist. Returns True if found and removed."""
    data = load_watchlist()
    for pool in POOLS:
        entries = data.get(pool, [])
        for i, entry in enumerate(entries):
            if entry["symbol"] == symbol:
                entries.pop(i)
                save_watchlist(data)
                return True
    return False


def get_all_symbols() -> List[Dict[str, str]]:
    """Get all watchlist symbols across all pools, each with pool tag."""
    data = load_watchlist()
    result = []
    for pool in POOLS:
        for entry in data.get(pool, []):
            result.append({**entry, "pool": pool})
    return result
