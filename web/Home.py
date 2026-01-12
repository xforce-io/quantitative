
import streamlit as st
import sys
from pathlib import Path

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

# 添加项目根目录到 Python 路径
# 这样我们就可以直接导入 quant 模块
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

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
        <span style="font-size: 48px;">💸</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("#### 资金流向分析")
    st.caption("监控机构/散户资金博弈，追踪北向资金，发现主力动向")
    st.page_link("pages/1_💸_Money_Flow.py", label="进入应用 →", icon="💸")

with col2:
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; margin-bottom: 10px;">
        <span style="font-size: 48px;">👀</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("#### 自选股监控")
    st.caption("管理自选列表，跟踪技术指标，监控估值分位")
    st.page_link("pages/2_👀_Watchlist.py", label="进入应用 →", icon="👀")

with col3:
    st.markdown("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); border-radius: 15px; margin-bottom: 10px;">
        <span style="font-size: 48px;">🏆</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("#### 风向排行榜")
    st.caption("多因子智能排名，多种策略配置，发现投资机会")
    st.page_link("pages/3_🏆_Ranking.py", label="进入应用 →", icon="🏆")

st.divider()

# ==================== 功能详情 ====================

with st.expander("📖 功能详情", expanded=False):
    st.markdown("""
    #### 1. 💸 资金流向分析 (Money Flow)
    提供全方位的市场资金流向监控：
    - **市场概览**：机构 vs 散户博弈、北向资金动向
    - **行业分析**：捕捉主力资金流入流出的热门板块
    - **个股追踪**：深度剖析个股的资金趋势

    #### 2. 👀 自选股监控 (Watchlist)
    管理和监控您的自选股列表：
    - **资金监控**：跟踪自选股资金流向
    - **技术指标**：均线、MACD、RSI 等指标分析
    - **估值监控**：PE/PB 历史分位追踪

    #### 3. 🏆 风向排行榜 (Ranking)
    对候选池标的进行多维度分析和排序：
    - **智能排名**：资金流向 + 技术形态 + 估值的多因子加权评分
    - **多种策略**：短线交易、均衡配置、价值投资、趋势跟踪、资金驱动
    - **赛道排行**：行业板块资金流向对比
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
