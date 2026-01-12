#!/bin/bash
# 股票筛选快捷命令
# Quick command for stock screening

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/bin/screen_stocks.py"

# 直接调用Python脚本，传递所有参数
python3 "$PYTHON_SCRIPT" "$@"
