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

st.title("📈 Quantitative Trading Platform")

st.markdown("""
### 欢迎使用量化交易分析平台

这是一个集成化的量化分析工作台，集成了数据获取、策略回测、市场分析等功能。
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
    st.caption("Macro environment, watchlist alerts, top signals — one page to know what to do")
    st.page_link("pages/1_📊_Dashboard.py", label="Open →", icon="📊")

with col2:
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; margin-bottom: 10px;">
        <span style="font-size: 48px;">👀</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("#### Watchlist")
    st.caption("Position tracking, technical indicators, capital flow monitoring")
    st.page_link("pages/2_👀_Watchlist.py", label="Open →", icon="👀")

with col3:
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); border-radius: 15px; margin-bottom: 10px;">
        <span style="font-size: 48px;">🔍</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("#### Scanner")
    st.caption("Macro liquidity, A-share/HK signals, value investing, box breakout scans")
    st.page_link("pages/3_🔍_Scanner.py", label="Open →", icon="🔍")

st.divider()

# ==================== 功能详情 ====================

with st.expander("📖 功能详情", expanded=False):
    st.markdown("""
    #### 1. 📊 Dashboard
    One-page overview of everything you need to know:
    - **Macro Status Bar**: USD liquidity, macro risk, A-share sentiment
    - **Watchlist Alerts**: Positions with triggered signals, sorted by alert level
    - **Signal Levels**: Watch → Warning → Signal → Strong Signal

    #### 2. 👀 Watchlist
    Monitor your positions and sectors:
    - **Capital Flow**: Institutional vs retail flows for each position
    - **Technical Indicators**: MA, MACD, RSI analysis
    - **Sector Tracking**: Industry fund flows and technical charts

    #### 3. 🔍 Scanner
    Find opportunities across markets:
    - **Macro Liquidity** (US): FRED-based risk monitoring
    - **A-Share/HK Signals**: China market sentiment and capital flows
    - **Value Investing** (US): Five-factor fundamental screening
    - **Box Breakout** (A-Share): Donchian Channel breakout detection
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
