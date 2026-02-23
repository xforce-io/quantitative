"""
AI Right Panel Component - 右侧 AI 分析师面板

实现设计文档中的 UI 层架构（v7.2 修复版）：
- 🎨 现代化玻璃拟态视觉风格
- ⚡ CSS-based 折叠，避免全页重绘
- 💬 多轮对话支持
- 🌊 流式输出渲染
- 🚀 极速交互体验 (st.fragment)
- ⚡ Agent 预热机制提升首次响应速度
"""

import streamlit as st
import threading

# 尝试导入 fragment，如果为了兼容旧版本则回退到普通函数
try:
    from streamlit import fragment
except ImportError:
    def fragment(func):
        return func

def _inject_panel_css():
    """注入 AI 面板专属 CSS（稳健版：不使用 fixed/:has，避免影响全局布局）"""
    st.markdown(
        """
        <style>
        :root {
            --ai-primary: #6366f1;
            --ai-primary-2: #a855f7;
            --ai-text: #0f172a;
            --ai-muted: #64748b;
            --ai-border: rgba(148, 163, 184, 0.35);
            --ai-surface: rgba(248, 250, 252, 0.9);
            --ai-surface-2: rgba(255, 255, 255, 0.95);
        }

        /* -------- Crisp-ish panel primitives (scoped by st-key- prefixes) -------- */
        /* AI 面板列固定定位：滚动时保持在视口内 */
        [data-testid="stVerticalBlock"]:has(div[class*="st-key-aiToggle_"]) {
            position: sticky;
            top: 1rem;
            align-self: flex-start;
            max-height: calc(100vh - 2rem);
            overflow-y: auto;
        }

        /* 让面板列里的元素更紧凑一点（不改全局 block-container） */
        div[class*="st-key-aiToggle_"],
        div[class*="st-key-aiClear_"],
        div[class*="st-key-aiQa"] {
            margin-top: 0 !important;
            margin-bottom: 0.25rem !important;
        }

        /* AI 面板列需要足够的底部空间 */
        [data-testid="stVerticalBlock"]:has(div[class*="st-key-aiToggle_"]) {
            padding-bottom: 24px !important;
        }

        .ai-panel-header {
            padding: 10px 12px;
            border: 1px solid var(--ai-border);
            border-radius: 12px;
            background: linear-gradient(135deg, var(--ai-surface) 0%, var(--ai-surface-2) 100%);
            margin-bottom: 10px;
        }

        .ai-panel-title {
            font-weight: 800;
            color: var(--ai-text);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .ai-panel-subtitle {
            font-size: 0.8rem;
            color: var(--ai-muted);
            margin-top: 2px;
        }

        .ai-status-badge {
            font-size: 0.65rem;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 6px;
            background: rgba(16, 185, 129, 0.15);
            color: #065f46;
        }

        .ai-panel-collapsed-hint {
            font-size: 0.85rem;
            color: var(--ai-muted);
            padding: 10px 12px;
            border: 1px dashed rgba(148, 163, 184, 0.6);
            border-radius: 12px;
            background: rgba(248, 250, 252, 0.6);
        }

        /* -------- Buttons: make them feel like Crisp (pill / hover / focus) -------- */
        div[class*="st-key-aiToggle_"] button {
            border-radius: 12px !important;
            border: 1px solid rgba(99, 102, 241, 0.25) !important;
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(168, 85, 247, 0.10)) !important;
            color: var(--ai-text) !important;
            font-weight: 700 !important;
            height: 40px !important;
            transition: transform 0.12s ease, box-shadow 0.12s ease, border-color 0.12s ease !important;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06) !important;
        }

        div[class*="st-key-aiToggle_"] button:hover {
            transform: translateY(-1px) !important;
            border-color: rgba(99, 102, 241, 0.45) !important;
            box-shadow: 0 10px 22px rgba(15, 23, 42, 0.10) !important;
        }

        div[class*="st-key-aiClear_"] button {
            border-radius: 12px !important;
            border: 1px solid rgba(148, 163, 184, 0.45) !important;
            background: rgba(255, 255, 255, 0.85) !important;
            color: var(--ai-muted) !important;
            font-weight: 700 !important;
            height: 40px !important;
        }

        div[class*="st-key-aiClear_"] button:disabled {
            opacity: 0.55 !important;
        }

        div[class*="st-key-aiQa"] button {
            border-radius: 14px !important;
            border: 1px solid rgba(99, 102, 241, 0.20) !important;
            background: rgba(255, 255, 255, 0.90) !important;
            height: 44px !important;
            font-weight: 800 !important;
            transition: transform 0.12s ease, box-shadow 0.12s ease !important;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06) !important;
        }

        div[class*="st-key-aiQa"] button:hover {
            transform: translateY(-1px) !important;
            box-shadow: 0 12px 24px rgba(15, 23, 42, 0.10) !important;
        }

        /* -------- Chat bubbles: crisp + readable -------- */
        [data-testid="stChatMessage"] {
            border-radius: 14px !important;
            border: 1px solid rgba(148, 163, 184, 0.25) !important;
            background: rgba(255, 255, 255, 0.85) !important;
            padding: 10px 12px !important;
            margin-bottom: 10px !important;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05) !important;
        }

        /* Streamlit 有些版本会用 .stChatMessage 作为 class，做兼容 */
        .stChatMessage {
            border-radius: 14px !important;
            border: 1px solid rgba(148, 163, 184, 0.25) !important;
            background: rgba(255, 255, 255, 0.85) !important;
            padding: 10px 12px !important;
            margin-bottom: 10px !important;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05) !important;
        }

        /* -------- Chat input: Premium glassmorphism style -------- */
        [data-testid="stChatInput"] {
            padding: 8px 0 20px 0 !important;  /* 底部留足空间 */
        }

        [data-testid="stChatInput"] > div {
            background: linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(248,250,252,0.98) 100%) !important;
            border-radius: 20px !important;
            border: 1.5px solid transparent !important;
            background-clip: padding-box !important;
            box-shadow: 
                0 4px 20px rgba(99, 102, 241, 0.08),
                0 8px 32px rgba(15, 23, 42, 0.06),
                inset 0 1px 0 rgba(255, 255, 255, 0.9) !important;
            position: relative !important;
            overflow: hidden !important;
        }

        /* 渐变边框效果（伪元素实现） */
        [data-testid="stChatInput"] > div::before {
            content: '';
            position: absolute;
            inset: 0;
            border-radius: 20px;
            padding: 1.5px;
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.35), rgba(168, 85, 247, 0.25), rgba(99, 102, 241, 0.15));
            -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
            mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
            -webkit-mask-composite: xor;
            mask-composite: exclude;
            pointer-events: none;
        }
        
        [data-testid="stChatInput"] textarea {
            border-radius: 16px !important;
            border: none !important;
            background: transparent !important;
            font-size: 0.95rem !important;
            padding: 14px 16px !important;
            color: var(--ai-text) !important;
            resize: none !important;
        }

        [data-testid="stChatInput"] textarea::placeholder {
            color: rgba(100, 116, 139, 0.7) !important;
            font-weight: 500 !important;
        }

        [data-testid="stChatInput"] textarea:focus {
            outline: none !important;
            box-shadow: none !important;
        }

        /* Focus 状态 - 整体容器发光 */
        [data-testid="stChatInput"] > div:focus-within {
            box-shadow: 
                0 0 0 3px rgba(99, 102, 241, 0.15),
                0 8px 28px rgba(99, 102, 241, 0.12),
                0 12px 40px rgba(15, 23, 42, 0.08),
                inset 0 1px 0 rgba(255, 255, 255, 0.9) !important;
        }

        [data-testid="stChatInput"] > div:focus-within::before {
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.6), rgba(168, 85, 247, 0.45), rgba(99, 102, 241, 0.3));
        }

        /* 发送按钮美化 */
        [data-testid="stChatInput"] button {
            background: linear-gradient(135deg, var(--ai-primary), var(--ai-primary-2)) !important;
            border: none !important;
            border-radius: 12px !important;
            color: white !important;
            width: 40px !important;
            height: 40px !important;
            margin: 6px !important;
            transition: transform 0.15s ease, box-shadow 0.15s ease !important;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.35) !important;
        }

        [data-testid="stChatInput"] button:hover {
            transform: scale(1.08) !important;
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.45) !important;
        }

        [data-testid="stChatInput"] button:active {
            transform: scale(0.96) !important;
        }

        [data-testid="stChatInput"] button svg {
            fill: white !important;
            stroke: white !important;
        }

        /* -------- 面板整体底部间距 -------- */
        div[class*="st-key-aiInput_"] {
            margin-bottom: 16px !important;
            padding-bottom: 8px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def _warmup_agent_manager():
    """后台预热 AgentManager"""
    try:
        from web.agent_manager import get_agent_manager
        get_agent_manager()
    except Exception:
        pass  # 预热失败不影响主流程

_agent_warmup_started = False

def _ensure_agent_warmup():
    """确保 Agent 预热已启动"""
    global _agent_warmup_started
    if not _agent_warmup_started:
        _agent_warmup_started = True
        threading.Thread(target=_warmup_agent_manager, daemon=True).start()

def _get_ai_panel_state(session_id: str) -> dict:
    """获取/初始化面板状态（按 session_id 隔离）"""
    if "aiPanelStates" not in st.session_state:
        st.session_state.aiPanelStates = {}
    if session_id not in st.session_state.aiPanelStates:
        st.session_state.aiPanelStates[session_id] = {
            "collapsed": False,
            "messages": [],
            "pendingPrompt": "",
        }
    return st.session_state.aiPanelStates[session_id]

@fragment
def render_ai_right_panel(session_id: str = "default"):
    """渲染右侧 AI 分析师面板（稳健版：右侧分栏内渲染，可折叠，不遮挡主内容）"""
    _inject_panel_css()
    _ensure_agent_warmup()

    panel_state = _get_ai_panel_state(session_id)

    # 顶部工具条：折叠/展开 + 清空
    t1, t2 = st.columns([0.7, 0.3])
    with t1:
        toggle_label = "✦ 展开" if panel_state["collapsed"] else "✕ 收起"
        if st.button(toggle_label, key=f"aiToggle_{session_id}", use_container_width=True):
            panel_state["collapsed"] = not panel_state["collapsed"]
            st.rerun(scope="fragment")
    with t2:
        if st.button("🗑 清空", key=f"aiClear_{session_id}", use_container_width=True, disabled=panel_state["collapsed"]):
            panel_state["messages"] = []
            panel_state["pendingPrompt"] = ""
            st.rerun(scope="fragment")

    if panel_state["collapsed"]:
        st.markdown('<div class="ai-panel-collapsed-hint">AI 已收起。点击「✦ 展开」开始对话。</div>', unsafe_allow_html=True)
        return

    # 头部（紧凑、稳健）
    st.markdown(
        """
        <div class="ai-panel-header">
          <div class="ai-panel-title">✦ AI 分析师 <span class="ai-status-badge">ONLINE</span></div>
          <div class="ai-panel-subtitle">量化投研助理（不遮挡图表，分栏显示）</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 聊天消息容器（固定高度，自动滚动）
    with st.container(height=350):
        # 欢迎区 + 快捷提问（无历史时显示）
        if not panel_state["messages"]:
            st.info("👋 我可以分析当前页面数据。你想先看『行情解读』还是『主力动向』？")
            q1, q2 = st.columns(2)
            with q1:
                if st.button("📈 行情解读", key=f"aiQa1_{session_id}", use_container_width=True):
                    panel_state["pendingPrompt"] = "请根据当前页面展示的数据，做一份简洁的行情解读（要点+结论+风险）。"
                    st.rerun(scope="fragment")
            with q2:
                if st.button("💰 主力动向", key=f"aiQa2_{session_id}", use_container_width=True):
                    panel_state["pendingPrompt"] = "请结合当前页面展示的数据，分析主力资金动向（流入/流出/持续性/关注点）。"
                    st.rerun(scope="fragment")
        else:
            # 历史消息
            for msg in panel_state["messages"]:
                with st.chat_message(msg["role"], avatar="🧑‍💻" if msg["role"] == "user" else "🤖"):
                    st.markdown(msg["content"])

        # 处理 pendingPrompt（fail fast：处理完一次就清空，避免重复）
        if panel_state.get("pendingPrompt"):
            user_input = panel_state["pendingPrompt"]
            panel_state["pendingPrompt"] = ""
            panel_state["messages"].append({"role": "user", "content": user_input})

            with st.chat_message("user", avatar="🧑‍💻"):
                st.markdown(user_input)

            with st.chat_message("assistant", avatar="🤖"):
                msg_placeholder = st.empty()
                status_box = st.status("🧠 Thinking...", expanded=False)

                full_text = ""
                try:
                    from web.agent_manager import run_agent_stream_sync
                    for event in run_agent_stream_sync(user_input, session_id):
                        if event.get("type") == "delta":
                            full_text += event.get("content", "")
                            msg_placeholder.markdown(full_text + "▌")
                        elif event.get("type") == "progress":
                            status_box.update(label=f"🔄 {event.get('content', '')}", state="running")

                    status_box.update(label="✅ Done", state="complete")
                    msg_placeholder.markdown(full_text)
                    panel_state["messages"].append({"role": "assistant", "content": full_text})
                except Exception as e:
                    error_msg = f"Error: {e}"
                    status_box.update(label="❌ Error", state="error")
                    msg_placeholder.markdown(error_msg)
                    panel_state["messages"].append({"role": "assistant", "content": error_msg})

            st.rerun(scope="fragment")

    # 底部输入框
    if prompt := st.chat_input("输入问题…", key=f"aiInput_{session_id}"):
        panel_state["pendingPrompt"] = prompt
        st.rerun(scope="fragment")

def get_ai_panel_layout(main_ratio: int = 7, panel_ratio: int = 3):
    """
    创建布局容器。
    
    稳健版：恢复标准左右分栏布局，右侧面板不会遮挡主内容。
    
    Args:
        main_ratio: 主内容区比例
        panel_ratio: AI 面板区比例
    
    Returns:
        包含两个 column 的元组
    """
    if main_ratio <= 0 or panel_ratio <= 0:
        raise ValueError("main_ratio and panel_ratio must be positive")
    return st.columns([main_ratio, panel_ratio])

def init_ai_panel_for_page(page_name: str, page_path: str = ""):
    """页面初始化"""
    if "current_page_name" not in st.session_state or st.session_state.current_page_name != page_name:
        from web.page_registry import init_page_registry
        init_page_registry(page_name, page_path)
        st.session_state.current_page_name = page_name
