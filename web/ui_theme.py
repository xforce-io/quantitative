"""
UI Theme & Configuration
集中管理颜色、样式和可视化配置，确保全站风格统一。
"""

import streamlit as st
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.io as pio

# ==================== 颜色定义 ====================

class Colors:
    # 涨跌色 (中国市场习惯：红涨绿跌)
    RISE = '#e74c3c'  # 红色
    FALL = '#2ecc71'  # 绿色
    NEUTRAL = '#95a5a6' # 灰色
    
    # 辅助色
    PRIMARY = '#3498db' # 蓝色
    WARNING = '#FFD700' # 金黄色 (用于价格曲线)
    INFO = '#8e44ad'    # 紫色
    
    # 图表色
    INSTITUTIONAL = '#e74c3c' # 机构
    RETAIL = '#2ecc71'        # 散户
    NORTH = '#3498db'         # 北向
    
    # 文字色
    TEXT_PRIMARY = '#2c3e50'
    TEXT_SECONDARY = '#7f8c8d'

# ==================== 样式配置 ====================

def setup_matplotlib_style():
    """统一配置 Matplotlib 样式 (支持中文)"""
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams['figure.dpi'] = 100
    plt.rcParams['axes.grid'] = True
    plt.rcParams['grid.alpha'] = 0.3
    plt.rcParams['grid.linestyle'] = '--'

def get_trend_color(value: float, inverse: bool = False) -> str:
    """
    获取涨跌颜色
    Args:
        value: 数值
        inverse: 是否反转 (如分位数越低越好时)
    """
    if inverse:
        if value > 0: return Colors.FALL
        if value < 0: return Colors.RISE
    else:
        if value > 0: return Colors.RISE
        if value < 0: return Colors.FALL
    return Colors.NEUTRAL

# ==================== Plotly 配置 ====================

def apply_plotly_theme():
    """配置 Plotly 默认模板"""
    pio.templates.default = "plotly_white"

def format_large_number(num: float) -> str:
    """格式化大数字 (亿/万)"""
    if abs(num) >= 1e8:
        return f"{num/1e8:.2f}亿"
    elif abs(num) >= 1e4:
        return f"{num/1e4:.2f}万"
    else:
        return f"{num:.2f}"


# ==================== Streamlit 自定义样式 ====================

def apply_custom_css():
    """
    应用自定义 CSS 样式
    - 加宽页面内容区域
    - 调整技术信号区域的字体大小
    """
    st.markdown("""
    <style>
    /* 加宽主内容区域并减少顶部留白 */
    .block-container {
        max-width: 1400px !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        padding-top: 2rem !important;
    }

    /* 隐藏顶部的装饰条和默认 Header 以节省空间 */
    header[data-testid="stHeader"] {
        display: none;
    }
    .stApp > header {
        display: none;
    }

    /* 技术信号区域的 metric 组件样式调整 */
    [data-testid="stMetric"] {
        background-color: #f8f9fa;
        padding: 10px 12px;
        border-radius: 8px;
    }

    /* 缩小 metric 标签字体 */
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
    }

    /* 缩小 metric 值字体，防止截断 */
    [data-testid="stMetricValue"] {
        font-size: 1.1rem !important;
        white-space: nowrap;
        overflow: visible !important;
    }

    /* metric delta 字体 */
    [data-testid="stMetricDelta"] {
        font-size: 0.75rem !important;
    }
    </style>
    """, unsafe_allow_html=True)