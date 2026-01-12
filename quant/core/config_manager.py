"""统一配置管理器 / Unified Configuration Manager

这个模块提供统一的配置管理功能，支持：
- 多配置文件加载
- 环境变量替换
- 配置验证
- 配置合并
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import re

logger = logging.getLogger(__name__)


class ConfigManager:
    """统一配置管理器"""
    
    def __init__(self, config_dir: str = "config"):
        """Initialize config manager
        
        Args:
            config_dir: Configuration directory path
        """
        self.config_dir = Path(config_dir)
        self._configs = {}
        self._env_pattern = re.compile(r'\$\{([^}]+)\}')
        
    def load_config(self, config_name: str) -> Dict[str, Any]:
        """Load configuration from file
        
        Args:
            config_name: Configuration name (without .yaml extension)
            
        Returns:
            Configuration dictionary
        """
        if config_name in self._configs:
            return self._configs[config_name]
            
        config_file = self.config_dir / f"{config_name}.yaml"
        if not config_file.exists():
            logger.warning(f"Configuration file not found: {config_file}")
            return {}
            
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            # Replace environment variables
            config = self._replace_env_vars(config)
            
            # Cache the config
            self._configs[config_name] = config
            
            logger.info(f"Loaded configuration: {config_name}")
            return config
            
        except Exception as e:
            logger.error(f"Failed to load config {config_name}: {e}")
            return {}
    
    def get_system_config(self) -> Dict[str, Any]:
        """Get system configuration"""
        return self.load_config("system_config")
    
    def get_data_sources_config(self) -> Dict[str, Any]:
        """Get data sources configuration"""
        return self.load_config("data_sources")
    
    def get_trading_config(self) -> Dict[str, Any]:
        """Get trading configuration"""
        return self.load_config("trading")
    
    def get_news_analysis_config(self) -> Dict[str, Any]:
        """Get news analysis configuration"""
        return self.load_config("news_analysis_config")

    def get_dolphin_config(self) -> Dict[str, Any]:
        """Get AI Agent (dolphin) configuration"""
        return self.load_config("dolphin")

    def get_llm_settings(self, model_key: str = None) -> Dict[str, str]:
        """Get LLM settings from dolphin config

        Args:
            model_key: Specific model key, or use default if None

        Returns:
            {"api_base": "...", "api_key": "...", "model": "..."}
        """
        config = self.get_dolphin_config()
        if not config:
            return {}

        model_key = model_key or config.get("default", "qwen-plus")
        llms = config.get("llms", {})
        clouds = config.get("clouds", {})

        model_config = llms.get(model_key, {})
        cloud_name = model_config.get("cloud", "aliyun")
        cloud_config = clouds.get(cloud_name, {})

        return {
            "api_base": cloud_config.get("api", ""),
            "api_key": cloud_config.get("api_key", ""),
            "model": model_config.get("model_name", model_key)
        }
    
    def get_investment_targets(self) -> List[Dict[str, Any]]:
        """Get investment targets configuration"""
        config = self.load_config("investment_targets")
        return config.get("targets", [])
    
    def get_llm_config(self, model_type: str = "premium") -> Dict[str, Any]:
        """Get LLM configuration
        
        Args:
            model_type: Type of model ('premium', 'cheap')
            
        Returns:
            LLM configuration
        """
        news_config = self.get_news_analysis_config()
        llm_configs = news_config.get("llm_configs", {})
        
        if model_type == "cheap":
            return llm_configs.get("cheap_model", {})
        else:
            return llm_configs.get("premium_model", {})
    
    def validate_config(self, config_name: str) -> bool:
        """Validate configuration
        
        Args:
            config_name: Configuration name to validate
            
        Returns:
            True if configuration is valid
        """
        config = self.load_config(config_name)
        if not config:
            return False
        
        # Add specific validation logic for each config type
        if config_name == "news_analysis":
            return self._validate_news_analysis_config(config)
        elif config_name == "trading":
            return self._validate_trading_config(config)
        elif config_name == "data_sources":
            return self._validate_data_sources_config(config)
        
        return True
    
    def merge_configs(self, *config_names: str) -> Dict[str, Any]:
        """Merge multiple configurations
        
        Args:
            config_names: Names of configurations to merge
            
        Returns:
            Merged configuration dictionary
        """
        merged = {}
        for config_name in config_names:
            config = self.load_config(config_name)
            merged.update(config)
        
        return merged
    
    def get_env_var(self, var_name: str, default: str = "") -> str:
        """Get environment variable with default value
        
        Args:
            var_name: Environment variable name
            default: Default value if variable is not set
            
        Returns:
            Environment variable value or default
        """
        return os.getenv(var_name, default)
    
    def _replace_env_vars(self, obj: Any) -> Any:
        """Replace environment variables in configuration
        
        Args:
            obj: Configuration object (dict, list, or string)
            
        Returns:
            Object with environment variables replaced
        """
        if isinstance(obj, dict):
            return {key: self._replace_env_vars(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            return self._env_pattern.sub(
                lambda m: os.getenv(m.group(1), m.group(0)), obj
            )
        else:
            return obj
    
    def _validate_news_analysis_config(self, config: Dict[str, Any]) -> bool:
        """Validate news analysis configuration"""
        required_sections = ["llm_configs", "analysis_stages", "cache_config"]
        for section in required_sections:
            if section not in config:
                logger.error(f"Missing required section in news_analysis config: {section}")
                return False
        
        # Validate LLM configs
        llm_configs = config.get("llm_configs", {})
        for model_type in ["cheap_model", "premium_model"]:
            if model_type in llm_configs:
                model_config = llm_configs[model_type]
                required_fields = ["provider", "api_key", "model"]
                for field in required_fields:
                    if field not in model_config:
                        logger.error(f"Missing required field {field} in {model_type}")
                        return False
        
        return True
    
    def _validate_trading_config(self, config: Dict[str, Any]) -> bool:
        """Validate trading configuration"""
        required_sections = ["data_sources", "strategies", "risk_management"]
        for section in required_sections:
            if section not in config:
                logger.error(f"Missing required section in trading config: {section}")
                return False
        
        return True
    
    def _validate_data_sources_config(self, config: Dict[str, Any]) -> bool:
        """Validate data sources configuration"""
        if "providers" not in config:
            logger.error("Missing providers section in data_sources config")
            return False
        
        return True
    
    def list_available_configs(self) -> List[str]:
        """List all available configuration files
        
        Returns:
            List of configuration names (without .yaml extension)
        """
        config_files = []
        for file_path in self.config_dir.glob("*.yaml"):
            config_files.append(file_path.stem)
        
        return sorted(config_files)
    
    def reload_config(self, config_name: str) -> Dict[str, Any]:
        """Reload configuration from file
        
        Args:
            config_name: Configuration name to reload
            
        Returns:
            Reloaded configuration
        """
        if config_name in self._configs:
            del self._configs[config_name]
        
        return self.load_config(config_name)
    
    def clear_cache(self):
        """Clear all cached configurations"""
        self._configs.clear()
        logger.info("Configuration cache cleared") 