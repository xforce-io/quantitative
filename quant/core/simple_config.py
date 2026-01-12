#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
简化的配置管理器
Simplified Configuration Manager
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from functools import lru_cache

class SimpleConfig:
    """简化的配置管理器，使用单一 config.yaml 文件"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理器

        Args:
            config_path: 配置文件路径，默认为 config.yaml
        """
        if config_path is None:
            # 自动查找配置文件
            self.config_path = self._find_config_file()
        else:
            self.config_path = Path(config_path)

        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        self._config = self._load_config()

    def _find_config_file(self) -> Path:
        """自动查找配置文件"""
        # 从当前脚本位置向上查找
        current = Path(__file__).parent
        while current != current.parent:
            config_file = current / "config.yaml"
            if config_file.exists():
                return config_file
            current = current.parent

        # 如果没找到，默认使用根目录
        return Path("config.yaml")

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # 环境变量替换
            config = self._substitute_env_vars(config)

            return config
        except Exception as e:
            raise RuntimeError(f"Failed to load config: {e}")

    def _substitute_env_vars(self, obj):
        """递归替换环境变量"""
        if isinstance(obj, dict):
            return {k: self._substitute_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._substitute_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith('${') and obj.endswith('}'):
            # 提取环境变量名
            env_var = obj[2:-1]
            return os.getenv(env_var, obj)
        else:
            return obj

    def get(self, key: str, default=None) -> Any:
        """
        获取配置值，支持点号分隔的嵌套键

        Args:
            key: 配置键，支持 'providers.tushare.enabled' 格式
            default: 默认值

        Returns:
            配置值
        """
        keys = key.split('.')
        value = self._config

        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        获取配置段

        Args:
            section: 段名称

        Returns:
            配置段字典
        """
        return self.get(section, {})

    # 便捷方法
    def get_system_config(self) -> Dict[str, Any]:
        """获取系统配置"""
        return self.get_section('system')

    def get_providers_config(self) -> Dict[str, Any]:
        """获取数据提供者配置"""
        return self.get_section('providers')

    def get_strategies_config(self) -> Dict[str, Any]:
        """获取策略配置"""
        return self.get_section('strategies')

    def get_cache_config(self) -> Dict[str, Any]:
        """获取缓存配置"""
        return self.get_section('cache')

    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return self.get_section('logging')

    def get_backtesting_config(self) -> Dict[str, Any]:
        """获取回测配置"""
        return self.get_section('backtesting')

    def get_agent_experiments_config(self) -> Dict[str, Any]:
        """获取Agent实验配置"""
        return self.get_section('agent_experiments')

    def get_risk_profiles_config(self) -> Dict[str, Any]:
        """获取风险配置文件"""
        return self.get_section('risk_profiles')

    @property
    def data_dir(self) -> str:
        """数据目录"""
        return self.get('system.data_dir', 'data')

    @property
    def cache_dir(self) -> str:
        """缓存目录"""
        return self.get('system.cache_dir', 'cache')

    @property
    def logs_dir(self) -> str:
        """日志目录"""
        return self.get('system.logs_dir', 'logs')

    @property
    def reports_dir(self) -> str:
        """报告目录"""
        return self.get('system.reports_dir', 'reports')

    @property
    def default_provider(self) -> str:
        """默认数据提供者"""
        return self.get('providers.default', 'tushare')

    def is_cache_enabled(self) -> bool:
        """是否启用缓存"""
        return self.get('cache.enabled', True)

    def get_cache_ttl(self, data_type: str) -> int:
        """获取缓存TTL"""
        return self.get(f'cache.strategies.{data_type}_ttl_hours', 24)

    def get_strategy_config(self, strategy_name: str) -> Dict[str, Any]:
        """获取特定策略配置"""
        return self.get(f'strategies.{strategy_name}', {})

    def dump(self) -> Dict[str, Any]:
        """返回完整配置字典"""
        return self._config.copy()


# 全局配置实例
@lru_cache(maxsize=1)
def get_config() -> SimpleConfig:
    """获取全局配置实例（单例模式）"""
    return SimpleConfig()


# 便捷函数
def get_config_value(key: str, default=None):
    """便捷函数：获取配置值"""
    return get_config().get(key, default)


def get_provider_config(provider_name: str = None) -> Dict[str, Any]:
    """便捷函数：获取数据提供者配置"""
    config = get_config()
    if provider_name:
        return config.get(f'providers.{provider_name}', {})
    else:
        return config.get_providers_config()


def get_strategy_config(strategy_name: str) -> Dict[str, Any]:
    """便捷函数：获取策略配置"""
    return get_config().get_strategy_config(strategy_name)