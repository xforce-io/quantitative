"""
E2E 测试配置 - Playwright 与 Streamlit 集成

配置 pytest-playwright 的 fixture 和通用工具函数
"""

import pytest
import subprocess
import time
import socket
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def is_port_open(host: str, port: int) -> bool:
    """检查端口是否开放"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        return result == 0


def wait_for_streamlit(host: str = "localhost", port: int = 8501, timeout: int = 30) -> bool:
    """等待 Streamlit 服务启动"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_open(host, port):
            # 额外等待一下让 Streamlit 完全初始化
            time.sleep(2)
            return True
        time.sleep(0.5)
    return False


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """配置浏览器上下文参数"""
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
    }


@pytest.fixture(scope="session")
def streamlit_server():
    """
    Streamlit 服务器 fixture
    
    检查服务是否已运行，如果未运行则启动它
    """
    host = "localhost"
    port = 8501
    base_url = f"http://{host}:{port}"
    
    # 检查是否已经有服务在运行
    if is_port_open(host, port):
        print(f"\n✅ Streamlit server already running at {base_url}")
        yield base_url
        return
    
    # 如果没有，则启动服务
    print(f"\n🚀 Starting Streamlit server...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    
    process = subprocess.Popen(
        ["streamlit", "run", str(PROJECT_ROOT / "web" / "Home.py"), "--server.headless=true"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # 等待服务启动
    if not wait_for_streamlit(host, port, timeout=30):
        process.terminate()
        raise RuntimeError("Failed to start Streamlit server")
    
    print(f"✅ Streamlit server started at {base_url}")
    yield base_url
    
    # 测试结束后停止服务（如果是我们启动的）
    print("\n🛑 Stopping Streamlit server...")
    process.terminate()
    process.wait(timeout=10)


@pytest.fixture
def app_url(streamlit_server):
    """获取应用 URL"""
    return streamlit_server


# Playwright 页面辅助方法
class StreamlitHelper:
    """Streamlit 页面操作辅助类"""
    
    def __init__(self, page):
        self.page = page
    
    def wait_for_app_loaded(self, timeout: int = 30000):
        """等待 Streamlit 应用加载完成"""
        # 等待主容器出现
        self.page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=timeout)
        
        # 等待加载动画消失（如果存在）
        try:
            self.page.wait_for_function(
                "() => !document.querySelector('[data-testid=\"stStatusWidget\"]') || "
                "document.querySelector('[data-testid=\"stStatusWidget\"]').offsetParent === null",
                timeout=10000
            )
        except Exception:
            pass  # 如果没有加载动画，继续
        
        # 等待页面内容稳定（无新元素渲染）
        self.page.wait_for_load_state("networkidle")
        
        # 额外等待确保 Streamlit 完成渲染
        self.page.wait_for_timeout(2000)
    
    def navigate_to_page(self, page_name: str):
        """通过侧边栏导航到指定页面"""
        # 展开侧边栏
        sidebar_button = self.page.locator('[data-testid="stSidebarNav"]')
        if sidebar_button.is_visible():
            # 点击页面链接
            self.page.click(f'text="{page_name}"')
            self.wait_for_app_loaded()
    

@pytest.fixture
def streamlit_helper(page) -> StreamlitHelper:
    """Streamlit 辅助实例"""
    return StreamlitHelper(page)
