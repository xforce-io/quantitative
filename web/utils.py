"""
Web Utilities
配置管理和辅助函数。
"""

import json
from pathlib import Path
from typing import Dict, List, Any

# 配置文件路径
CONFIG_DIR = Path(__file__).parent.parent / "config"
WATCHLIST_FILE = CONFIG_DIR / "watchlist.json"


def load_watchlist() -> Dict[str, List[str]]:
    """加载自选列表"""
    if not WATCHLIST_FILE.exists():
        default_config = {
            "stocks": ["000001.SZ 平安银行", "600519.SH 贵州茅台"],
            "industries": ["半导体", "商业航天"]
        }
        save_watchlist(default_config)
        return default_config
    
    try:
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"stocks": [], "industries": []}


def save_watchlist(data: Dict[str, List[str]]) -> None:
    """保存自选列表"""
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
