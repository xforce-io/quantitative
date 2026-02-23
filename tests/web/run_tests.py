#!/usr/bin/env python3
"""
AI 分析师 E2E 测试运行脚本

使用方法:
    # 无头模式运行所有测试
    python tests/web/run_tests.py

    # 有头模式（可视化）运行
    python tests/web/run_tests.py --headed

    # 只运行 UI 测试
    python tests/web/run_tests.py --ui-only

    # 运行多轮对话测试（较慢）
    python tests/web/run_tests.py --multi-turn

    # 生成测试报告
    python tests/web/run_tests.py --report
"""

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def check_dependencies():
    """检查测试依赖是否安装"""
    try:
        import playwright
    except ImportError:
        print("❌ Playwright 未安装，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright", "pytest-playwright"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("✅ Playwright 安装完成")
    
    try:
        import pytest
    except ImportError:
        print("❌ pytest 未安装，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pytest"], check=True)
        print("✅ pytest 安装完成")


def run_tests(args):
    """运行测试"""
    check_dependencies()
    
    cmd = [
        sys.executable, "-m", "pytest",
        str(PROJECT_ROOT / "tests" / "web"),
        "-v",
    ]
    
    # 有头模式
    if args.headed:
        cmd.append("--headed")
    
    # 慢速网络模拟
    if args.slow_mo:
        cmd.extend(["--slowmo", str(args.slow_mo)])
    
    # 测试过滤
    if args.ui_only:
        cmd.extend(["-k", "TestAIPanelUI or TestAIPanelInteraction"])
    elif args.multi_turn:
        cmd.extend(["-k", "TestAIPanelMultiTurn"])
    elif args.tool_viz:
        cmd.extend(["-k", "TestAIPanelToolVisualization"])
    elif args.pattern:
        cmd.extend(["-k", args.pattern])
    
    # 生成 HTML 报告
    if args.report:
        cmd.extend(["--html=tests/web/report.html", "--self-contained-html"])
    
    # 失败时截图
    cmd.append("--screenshot=only-on-failure")
    
    # 视频录制（失败时）
    if args.video:
        cmd.append("--video=retain-on-failure")
    
    # 浏览器选择
    cmd.extend(["--browser", args.browser])
    
    # 并行执行
    if args.parallel:
        cmd.extend(["-n", str(args.parallel)])
    
    # 失败后停止
    if args.failfast:
        cmd.append("-x")
    
    print(f"🧪 运行命令: {' '.join(cmd)}")
    print("-" * 60)
    
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="AI 分析师 E2E 测试运行器")
    
    # 显示模式
    parser.add_argument("--headed", action="store_true", help="有头模式运行（显示浏览器）")
    parser.add_argument("--slow-mo", type=int, default=0, help="慢速执行（毫秒）")
    
    # 测试选择
    parser.add_argument("--ui-only", action="store_true", help="只运行 UI 测试")
    parser.add_argument("--multi-turn", action="store_true", help="运行多轮对话测试")
    parser.add_argument("--tool-viz", action="store_true", help="运行工具可视化测试")
    parser.add_argument("-k", "--pattern", type=str, help="自定义测试过滤模式")
    
    # 报告和录制
    parser.add_argument("--report", action="store_true", help="生成 HTML 测试报告")
    parser.add_argument("--video", action="store_true", help="录制失败测试的视频")
    
    # 浏览器选择
    parser.add_argument("--browser", default="chromium", choices=["chromium", "firefox", "webkit"], help="浏览器类型")
    
    # 执行控制
    parser.add_argument("-n", "--parallel", type=int, help="并行执行数量")
    parser.add_argument("-x", "--failfast", action="store_true", help="失败后立即停止")
    
    args = parser.parse_args()
    sys.exit(run_tests(args))


if __name__ == "__main__":
    main()
