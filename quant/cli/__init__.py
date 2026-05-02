"""
CLI命令模块

统一的命令行接口命令集合
"""

from .etf import register_etf_commands
from .data import register_data_commands
from .portfolio import register_portfolio_commands
from .advisor import register_advisor_commands
from .lowfreq import register_lowfreq_commands
from .rotation import register_rotation_commands
from .strategy import register_strategy_commands
from .system import register_system_commands
from .screener import register_screener_commands

__all__ = [
    'register_etf_commands',
    'register_data_commands',
    'register_portfolio_commands',
    'register_advisor_commands',
    'register_lowfreq_commands',
    'register_rotation_commands',
    'register_strategy_commands',
    'register_system_commands',
    'register_screener_commands',
]
