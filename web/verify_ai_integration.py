#!/usr/bin/env python3
"""
AI 助手全页面集成验证脚本

用途：快速验证所有页面的 AI 助手是否正确集成

运行方式：
    python web/verify_ai_integration.py
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Tuple

# ANSI 颜色代码
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def check_file_has_pattern(file_path: str, patterns: List[str]) -> Tuple[bool, List[str]]:
    """检查文件是否包含所有指定的模式"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        missing_patterns = []
        for pattern in patterns:
            if pattern not in content:
                missing_patterns.append(pattern)
        
        return len(missing_patterns) == 0, missing_patterns
    except Exception as e:
        return False, [f"Error reading file: {e}"]

def verify_page_integration(page_path: str, page_name: str) -> Dict[str, any]:
    """验证单个页面的 AI 集成"""
    
    # 必须包含的模式
    required_patterns = [
        "from web.components_ai_panel import render_ai_right_panel, init_ai_panel_for_page, get_ai_panel_layout",
        "from web.page_registry import get_page_registry",
        f'init_ai_panel_for_page("{page_name}"',
        "get_ai_panel_layout(",
        "render_ai_right_panel(session_id=",
    ]
    
    success, missing = check_file_has_pattern(page_path, required_patterns)
    
    return {
        "page": page_name,
        "path": page_path,
        "success": success,
        "missing_patterns": missing
    }

def main():
    print(f"{BOLD}{BLUE}========================================{RESET}")
    print(f"{BOLD}{BLUE}  AI 助手全页面集成验证{RESET}")
    print(f"{BOLD}{BLUE}========================================{RESET}\n")
    
    # 定义要检查的页面
    pages_to_check = [
        ("web/pages/1_💸_Money_Flow.py", "Money Flow"),
        ("web/pages/2_👀_Watchlist.py", "Watchlist"),
        ("web/pages/3_🏆_Ranking.py", "Ranking"),
    ]
    
    results = []
    
    # 验证每个页面
    for page_path, page_name in pages_to_check:
        full_path = os.path.join(os.path.dirname(__file__), "..", page_path)
        
        if not os.path.exists(full_path):
            print(f"{RED}✗{RESET} {page_name}: 文件不存在 ({page_path})")
            results.append({
                "page": page_name,
                "path": page_path,
                "success": False,
                "missing_patterns": ["File not found"]
            })
            continue
        
        result = verify_page_integration(full_path, page_name)
        results.append(result)
        
        if result["success"]:
            print(f"{GREEN}✓{RESET} {BOLD}{page_name}{RESET}: AI 助手集成正确")
        else:
            print(f"{RED}✗{RESET} {BOLD}{page_name}{RESET}: AI 助手集成缺失")
            for pattern in result["missing_patterns"]:
                print(f"  {YELLOW}→{RESET} 缺失: {pattern[:80]}...")
    
    # 汇总结果
    print(f"\n{BOLD}{BLUE}========================================{RESET}")
    total = len(results)
    success_count = sum(1 for r in results if r["success"])
    
    if success_count == total:
        print(f"{GREEN}{BOLD}✓ 所有 {total} 个页面都正确集成了 AI 助手{RESET}")
        print(f"{GREEN}  集成覆盖率: 100%{RESET}")
        return 0
    else:
        print(f"{RED}{BOLD}✗ {total - success_count}/{total} 个页面的 AI 集成有问题{RESET}")
        print(f"{YELLOW}  集成覆盖率: {success_count/total*100:.1f}%{RESET}")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
