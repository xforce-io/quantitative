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
    
    def is_ai_panel_visible(self) -> bool:
        """检查 AI 面板是否可见"""
        return self.page.get_by_text("AI 分析师").count() > 0

    def expand_ai_panel(self):
        """展开 AI 面板"""
        # 实际按钮文本: "✦ 展开"
        expand_btns = self.page.locator('button:has-text("展开")').all()
        for btn in expand_btns:
            if btn.is_visible():
                btn.click()
                self.page.wait_for_timeout(500)
                return

    def collapse_ai_panel(self):
        """折叠 AI 面板"""
        # 实际按钮文本: "✕ 收起"
        collapse_btns = self.page.locator('button:has-text("收起")').all()
        for btn in collapse_btns:
            if btn.is_visible():
                btn.click()
                self.page.wait_for_timeout(500)
                return
    
    def send_ai_message(self, message: str):
        """向 AI 发送消息"""
        # 在 AI 面板内找 chat input（使用更通用的选择器）
        chat_input = self.page.locator('[data-testid="stChatInput"] textarea').last
        chat_input.fill(message)
        chat_input.press("Enter")
    
    def wait_for_ai_response(self, timeout: int = 60000):
        """等待 AI 响应完成"""
        # 等待 "正在思考..." 状态出现
        self.page.wait_for_selector('text="正在思考..."', timeout=5000)
        # 等待状态变为 "回答完成" 或超时
        self.page.wait_for_function(
            """() => {
                const status = document.querySelector('[data-testid="stStatus"]');
                if (!status) return true;
                return status.textContent.includes('回答完成') || 
                       status.textContent.includes('系统异常') ||
                       status.textContent.includes('发生错误');
            }""",
            timeout=timeout
        )
    
    def get_ai_messages(self) -> list:
        """获取所有 AI 对话消息"""
        messages = []
        for msg in self.page.locator('[data-testid="stChatMessage"]').all():
            role = msg.get_attribute('data-message-author')
            content = msg.locator('[data-testid="stChatMessageContent"]').text_content()
            messages.append({"role": role, "content": content})
        return messages
    
    def clear_ai_history(self):
        """清空 AI 对话历史"""
        # 实际按钮文本: "🗑 清空"
        clear_btns = self.page.locator('button:has-text("清空")').all()
        for btn in clear_btns:
            if btn.is_visible():
                btn.click()
                self.page.wait_for_timeout(500)
                return

    def click_quick_action_button(self):
        """点击快捷操作按钮（行情解读或主力动向）"""
        # 实际按钮: "📈 行情解读" 或 "💰 主力动向"
        btn = self.page.locator('button:has-text("行情解读")')
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click()
            return
        btn = self.page.locator('button:has-text("主力动向")')
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click()


@pytest.fixture
def streamlit_helper(page) -> StreamlitHelper:
    """Streamlit 辅助实例"""
    return StreamlitHelper(page)
