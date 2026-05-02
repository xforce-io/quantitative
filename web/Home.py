import streamlit as st
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
# 这样我们就可以直接导入 quant 和 web 模块
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置页面配置
st.set_page_config(
    page_title="Quantitative Trading Platform",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 导入统一的样式和配置
from web.ui_theme import setup_matplotlib_style, apply_plotly_theme, apply_custom_css

# 初始化样式
setup_matplotlib_style()
apply_plotly_theme()
apply_custom_css()

from quant.core.logging_config import get_logger

st.title("📈 量化交易分析平台")

st.markdown("""
### 欢迎使用

集成化的量化分析工作台，覆盖宏观环境监控、持仓跟踪、机会扫描。
""")

st.divider()

# ==================== 应用卡片导航 ====================

st.markdown("### 🚀 快速入口")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; margin-bottom: 10px;">
        <span style="font-size: 48px;">📊</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("#### Dashboard")
    st.caption("Overall verdict, cross-asset alerts, pool status — one page to know what to do")
    st.page_link("pages/1_📊_Dashboard.py", label="进入 →", icon="📊")

with col2:
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; margin-bottom: 10px;">
        <span style="font-size: 48px;">👀</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("#### Watchlist")
    st.caption("Positions organized by asset pool with regime context and action suggestions")
    st.page_link("pages/2_👀_Watchlist.py", label="进入 →", icon="👀")

with col3:
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); border-radius: 15px; margin-bottom: 10px;">
        <span style="font-size: 48px;">🔍</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("#### Scanner")
    st.caption("Find opportunities in A-shares, US value stocks, gold and commodities")
    st.page_link("pages/3_🔍_Scanner.py", label="进入 →", icon="🔍")

st.divider()

# ==================== 功能详情 ====================

with st.expander("📖 功能详情", expanded=False):
    st.markdown("""
    #### 1. 📊 Dashboard
    Overall verdict, cross-asset alerts, pool status — one page to know what to do:
    - **Verdict bar with overall stance and per-pool actions**
    - **Asset pool cards showing regime status**
    - **Position alerts with action suggestions**

    #### 2. 👀 Watchlist
    Positions organized by asset pool with regime context and action suggestions:
    - **Tabs by asset pool** (A-shares, US stocks, gold, commodities)
    - **Per-position regime context and signals**
    - **In-page add/remove management**

    #### 3. 🔍 Scanner
    Find opportunities in A-shares, US value stocks, gold and commodities:
    - **A-share scan** (box breakout + market signals)
    - **US value scan** (five-factor screening)
    - **Gold & commodity scan**
    """)

# 系统状态检查
st.sidebar.markdown("---")
st.sidebar.info(f"Project Root: `{project_root}`")

try:
    from quant.data.implementations.tushare_provider import TushareProvider
    st.sidebar.success("✅ Core System Loaded")
except ImportError as e:
    st.sidebar.error(f"❌ System Import Failed: {e}")

st.sidebar.markdown("---")
st.sidebar.caption("© 2026 Quantitative Trading System")
