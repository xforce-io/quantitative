#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
选股篮子（Screens）定义与管理

将非-DEFAULT 的集合迁移为 Screen（选股篮子），用于从候选集合构建投资组合。
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import logging

from analyst.portfolios import SymbolInfo, portfolio_manager
from pathlib import Path
import json
import os
import time

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

# 延迟导入筛选器以避免循环依赖
logger = logging.getLogger(__name__)


# 选股篮子定义：唯一事实源为 config/screens.yaml（或 JSON）。此处初始化为空，由 _try_load_from_config 填充。
SCREENS: Dict[str, Dict[str, SymbolInfo]] = {}


SCREENS_META: Dict[str, Dict[str, Any]] = {}


class ScreenManager:
    """选股篮子管理器 - 支持静态和动态筛选"""

    def __init__(self):
        self.static_screens: Dict[str, Dict[str, SymbolInfo]] = SCREENS
        self.meta: Dict[str, Dict[str, Any]] = SCREENS_META
        
        # 动态筛选相关
        self.dynamic_screens: Dict[str, Dict[str, SymbolInfo]] = {}
        self.dynamic_meta: Dict[str, Dict[str, Any]] = {}
        self.last_refresh: Dict[str, datetime] = {}
        self.screeners: Dict[str, Any] = {}  # 延迟初始化
        
        # 启动尝试从 config/ 加载屏幕配置（YAML/JSON）
        try:
            self._try_load_from_config()
        except Exception:
            pass
        self._validate_or_fail()
        
        # 初始化动态筛选器
        self._init_screeners()

    def list_screens(self, include_dynamic: bool = True) -> List[str]:
        """列出所有可用的选股篮子
        
        Args:
            include_dynamic: 是否包含动态筛选篮子
            
        Returns:
            选股篮子名称列表
        """
        static_screens = list(self.static_screens.keys())
        if include_dynamic:
            dynamic_screens = list(self.dynamic_screens.keys())
            return sorted(list(set(static_screens + dynamic_screens)))
        return static_screens

    @property
    def screens(self) -> Dict[str, Dict[str, SymbolInfo]]:
        """兼容性属性：合并静态和动态篮子"""
        combined = self.static_screens.copy()
        combined.update(self.dynamic_screens)
        return combined
    
    def get_screen(self, name: str, use_dynamic: bool = False, auto_refresh: bool = False) -> Dict[str, SymbolInfo]:
        """获取选股篮子
        
        Args:
            name: 篮子名称
            use_dynamic: 是否优先使用动态篮子
            auto_refresh: 是否自动刷新过期的动态篮子
            
        Returns:
            标的信息字典
        """
        # 如果指定使用动态篮子，先检查是否需要刷新
        if use_dynamic and auto_refresh:
            if self._should_refresh_dynamic_screen(name):
                try:
                    self.refresh_dynamic_screen(name)
                except Exception as e:
                    logger.warning(f"动态刷新篮子 {name} 失败: {e}")
        
        # 优先返回动态篮子（如果存在且要求使用）
        if use_dynamic and name in self.dynamic_screens:
            return self.dynamic_screens[name]
        
        # 返回静态篮子
        if name in self.static_screens:
            return self.static_screens[name]
        
        # 都没有则报错
        available = self.list_screens(include_dynamic=True)
        raise ValueError(f"选股篮子 '{name}' 不存在。可用: {available}")

    def get_screen_meta(self, name: str) -> Dict[str, Any]:
        return self.meta.get(name, {})

    def get_symbols(self, name: str, use_dynamic: bool = False) -> List[str]:
        """获取选股篮子中的所有标的代码"""
        return list(self.get_screen(name, use_dynamic=use_dynamic).keys())

    def build_weights(self, name: str, method: str = 'equal', use_dynamic: bool = False) -> Dict[str, float]:
        """为选股篮子生成权重
        
        Args:
            name: 篮子名称
            method: 权重方法 ('equal', 'inv_vol')
            use_dynamic: 是否使用动态篮子
        """
        symbols = self.get_symbols(name, use_dynamic=use_dynamic)
        # 复用 PortfolioManager 的权重生成逻辑
        return portfolio_manager.build_weights(symbols, method=method)

    def get_trade_symbols(self, name: str, use_proxy: bool = True, use_dynamic: bool = False) -> List[str]:
        """获取可交易的标的代码列表"""
        symbols = self.get_symbols(name, use_dynamic=use_dynamic)
        if not use_proxy:
            return symbols
        return [portfolio_manager.apply_index_proxy(s) for s in symbols]

    def _validate_or_fail(self) -> None:
        import os
        strict = os.getenv('STRICT_CONFIG', 'false').lower() in ('1', 'true', 'yes')  # 默认宽松模式
        errors = []
        if not self.static_screens:
            errors.append('未加载到任何选股篮子（请在 config/screens.yaml 定义 screens）')
        for name in self.static_screens.keys():
            meta = self.meta.get(name, {})
            if not meta:
                # 不作为严重错误，只警告
                logger.debug(f"选股篮子 {name} 缺少元数据")
            elif meta.get('type', 'screen') != 'screen':
                errors.append(f"选股篮子 {name} 的 type 应为 'screen'，但得到 '{meta.get('type')}'")
        if errors:
            msg = '\n'.join(errors)
            if strict:
                raise ValueError(f"配置校验失败（严格模式）:\n{msg}")
            else:
                logger.warning(f"配置存在问题（宽松模式）:\n{msg}")

    # ===== 配置加载 =====
    def _expand_env(self, obj):
        if isinstance(obj, dict):
            return {k: self._expand_env(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._expand_env(x) for x in obj]
        if isinstance(obj, str):
            return os.path.expandvars(obj)
        return obj

    def _read_yaml_or_json(self, path: Path):
        if not path.exists():
            return None
        try:
            if path.suffix.lower() in {'.yaml', '.yml'}:
                if yaml is None:
                    return None
                with open(path, 'r', encoding='utf-8') as f:
                    return self._expand_env(yaml.safe_load(f))
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    return self._expand_env(json.load(f))
        except Exception:
            return None

    def _try_load_from_config(self):
        cfg_dir = Path(__file__).parent.parent / 'config'
        if not cfg_dir.exists():
            return
        for fname in ['screens.yaml', 'screens.yml', 'screens.json']:
            data = self._read_yaml_or_json(cfg_dir / fname)
            if not isinstance(data, dict):
                continue
            # 支持两种形态：
            # 1) { screens: {NAME: {SYMBOL: info_dict}}, screens_meta: {...}}
            # 2) 直接 { NAME: {SYMBOL: ...}, meta: {...}}
            if 'screens' in data:
                raw = data.get('screens', {})
                parsed: Dict[str, Dict[str, SymbolInfo]] = {}
                for name, m in raw.items():
                    if isinstance(m, dict):
                        parsed[name] = {s: (SymbolInfo.from_dict(v) if isinstance(v, dict) else SymbolInfo(s, str(v))) for s, v in m.items()}
                if parsed:
                    self.static_screens = parsed
                if isinstance(data.get('screens_meta'), dict):
                    self.meta = data['screens_meta']
                break
            else:
                # 形态2
                parsed: Dict[str, Dict[str, SymbolInfo]] = {}
                for name, m in data.items():
                    if name == 'meta':
                        continue
                    if isinstance(m, dict):
                        parsed[name] = {s: (SymbolInfo.from_dict(v) if isinstance(v, dict) else SymbolInfo(s, str(v))) for s, v in m.items()}
                if parsed:
                    self.static_screens = parsed
                if isinstance(data.get('meta'), dict):
                    self.meta = data['meta']
                break
    
    # ========= 动态筛选功能 =========
    def _init_screeners(self) -> None:
        """延迟初始化筛选器以避免循环依赖"""
        try:
            # 延迟导入以避免循环依赖
            from analyst.screeners.etf_momentum_screener import ETFMomentumScreener
            from analyst.screeners.company_screener import CompanyScreener
            
            # 初始化筛选器（如果TOKEN可用）
            token = os.getenv('TUSHARE_TOKEN')
            if token:
                try:
                    self.screeners['etf_momentum'] = ETFMomentumScreener(token)
                    self.screeners['company_canslim'] = CompanyScreener(token)
                    logger.info("动态筛选器初始化成功")
                except Exception as e:
                    logger.warning(f"筛选器初始化失败: {e}")
            else:
                logger.info("未设置TUSHARE_TOKEN，跳过动态筛选器初始化")
        except ImportError as e:
            logger.warning(f"筛选器模块导入失败: {e}")
    
    def refresh_dynamic_screen(self, name: str, force: bool = False) -> bool:
        """刷新指定的动态选股篮子
        
        Args:
            name: 篮子名称
            force: 是否强制刷新（忽略时间限制）
            
        Returns:
            是否成功刷新
        """
        if not self.screeners:
            logger.warning("筛选器未初始化，无法进行动态刷新")
            return False
        
        # 检查是否需要刷新
        if not force and not self._should_refresh_dynamic_screen(name):
            logger.debug(f"篮子 {name} 无需刷新")
            return True
        
        try:
            logger.info(f"开始刷新动态篮子: {name}")
            
            # 根据篮子名称选择适当的筛选器和策略
            if name.upper() in ['ETF_MOMENTUM', 'INDUSTRY_ETF', 'ETF_HIGH_MOMENTUM']:
                return self._refresh_etf_screen(name)
            elif name.upper() in ['SEMICONDUCTOR_DYNAMIC', 'BANK_DYNAMIC', 'NEW_ENERGY_DYNAMIC', 'HEALTHCARE_DYNAMIC', 'TECH_GROWTH_DYNAMIC']:
                return self._refresh_stock_screen(name)
            else:
                logger.warning(f"未知的动态篮子类型: {name}")
                return False
                
        except Exception as e:
            logger.error(f"刷新动态篮子 {name} 失败: {e}")
            return False
    
    def _refresh_etf_screen(self, name: str) -> bool:
        """刷新ETF类型的动态篮子"""
        if 'etf_momentum' not in self.screeners:
            logger.warning("ETF动量筛选器未初始化")
            return False
            
        screener = self.screeners['etf_momentum']
        
        # 根据篮子名称设置筛选参数
        if name.upper() == 'ETF_HIGH_MOMENTUM':
            # 高动量ETF筛选
            etf_types = ['broad_market', 'sector', 'thematic']
            max_count = 15
        else:
            # 默认行业ETF筛选
            etf_types = ['sector', 'thematic']
            max_count = 20
        
        try:
            # 执行筛选
            results = screener.screen_etfs(
                etf_types=etf_types,
                max_etfs=max_count
            )
            
            if not results.empty:
                # 转换为SymbolInfo格式
                dynamic_symbols = {}
                for _, row in results.iterrows():
                    etf_code = row.get('ts_code', row.name)
                    etf_data = row.to_dict()
                    dynamic_symbols[etf_code] = SymbolInfo(
                        symbol=etf_code,
                        name=etf_data.get('name', etf_code),
                        market='ETF',
                        sector=etf_data.get('category', 'ETF'),
                        volatility='high',
                        liquidity='excellent'
                    )
                
                # 保存到动态篮子
                self.dynamic_screens[name] = dynamic_symbols
                self.dynamic_meta[name] = {
                    'description': f'动态ETF动量篮子 - {len(dynamic_symbols)}只ETF',
                    'type': 'dynamic_screen',
                    'screener_type': 'etf_momentum',
                    'last_refresh': datetime.now().isoformat(),
                    'refresh_frequency': 'weekly'
                }
                self.last_refresh[name] = datetime.now()
                
                logger.info(f"成功刷新ETF篮子 {name}，共 {len(dynamic_symbols)} 只标的")
                return True
            else:
                logger.warning(f"ETF筛选无结果: {name}")
                return False
                
        except Exception as e:
            logger.error(f"ETF筛选失败: {e}")
            return False
    
    def _refresh_stock_screen(self, name: str) -> bool:
        """刷新股票类型的动态篮子"""
        if 'company_canslim' not in self.screeners:
            logger.warning("公司CANSLIM筛选器未初始化")
            return False
        
        screener = self.screeners['company_canslim']
        
        # 根据篮子名称设置筛选参数
        sector_mapping = {
            'SEMICONDUCTOR_DYNAMIC': '半导体',
            'BANK_DYNAMIC': '银行', 
            'NEW_ENERGY_DYNAMIC': '新能源',
            'HEALTHCARE_DYNAMIC': '医药生物',
            'TECH_GROWTH_DYNAMIC': '科技'
        }
        
        target_sector = sector_mapping.get(name.upper(), None)
        
        try:
            # 执行筛选
            results = screener.screen_stocks(
                max_stocks=30,
                save_results=False
            )
            
            if not results.empty:
                # 转换为SymbolInfo格式
                dynamic_symbols = {}
                for _, row in results.iterrows():
                    stock_code = row.get('ts_code', row.name)
                    stock_data = row.to_dict()
                    dynamic_symbols[stock_code] = SymbolInfo(
                        symbol=stock_code,
                        name=stock_data.get('name', stock_code),
                        market='A股',
                        sector=target_sector or stock_data.get('sector', 'unknown'),
                        volatility='high',
                        liquidity='good'
                    )
                
                # 保存到动态篮子
                self.dynamic_screens[name] = dynamic_symbols
                self.dynamic_meta[name] = {
                    'description': f'动态{target_sector}篮子 - {len(dynamic_symbols)}只股票',
                    'type': 'dynamic_screen', 
                    'screener_type': 'company_canslim',
                    'last_refresh': datetime.now().isoformat(),
                    'refresh_frequency': 'daily'
                }
                self.last_refresh[name] = datetime.now()
                
                logger.info(f"成功刷新股票篮子 {name}，共 {len(dynamic_symbols)} 只标的")
                return True
            else:
                logger.warning(f"股票筛选无结果: {name}")
                return False
                
        except Exception as e:
            logger.error(f"股票筛选失败: {e}")
            return False
    
    def _should_refresh_dynamic_screen(self, name: str) -> bool:
        """判断是否需要刷新动态篮子"""
        if name not in self.last_refresh:
            return True
        
        last_time = self.last_refresh[name]
        now = datetime.now()
        
        # 根据篮子类型设置不同的刷新间隔
        meta = self.dynamic_meta.get(name, {})
        refresh_freq = meta.get('refresh_frequency', 'daily')
        
        if refresh_freq == 'daily':
            threshold = timedelta(hours=24)
        elif refresh_freq == 'weekly':
            threshold = timedelta(days=7)
        elif refresh_freq == 'monthly':
            threshold = timedelta(days=30)
        else:
            threshold = timedelta(hours=24)  # 默认每日
        
        return (now - last_time) > threshold
    
    def refresh_all_dynamic_screens(self, force: bool = False) -> Dict[str, bool]:
        """刷新所有动态篮子
        
        Args:
            force: 是否强制刷新所有篮子
            
        Returns:
            每个篮子的刷新结果
        """
        results = {}
        
        # 预定义的动态篮子列表
        dynamic_baskets = [
            'ETF_HIGH_MOMENTUM',
            'SEMICONDUCTOR_DYNAMIC', 
            'BANK_DYNAMIC',
            'NEW_ENERGY_DYNAMIC',
            'HEALTHCARE_DYNAMIC',
            'TECH_GROWTH_DYNAMIC'
        ]
        
        for basket_name in dynamic_baskets:
            try:
                results[basket_name] = self.refresh_dynamic_screen(basket_name, force=force)
            except Exception as e:
                logger.error(f"刷新篮子 {basket_name} 时出错: {e}")
                results[basket_name] = False
        
        success_count = sum(1 for success in results.values() if success)
        logger.info(f"动态篮子刷新完成: {success_count}/{len(results)} 成功")
        
        return results
    
    def get_screen_meta(self, name: str, use_dynamic: bool = False) -> Dict[str, Any]:
        """获取篮子元数据，支持动态篮子"""
        if use_dynamic and name in self.dynamic_meta:
            return self.dynamic_meta[name]
        return self.meta.get(name, {})
    
    def is_dynamic_screen(self, name: str) -> bool:
        """检查是否为动态篮子"""
        return name in self.dynamic_screens
    
    def get_dynamic_screen_status(self, name: str) -> Dict[str, Any]:
        """获取动态篮子状态信息"""
        if name not in self.dynamic_screens:
            return {'exists': False}
        
        meta = self.dynamic_meta.get(name, {})
        last_refresh = self.last_refresh.get(name)
        
        return {
            'exists': True,
            'symbol_count': len(self.dynamic_screens[name]),
            'last_refresh': last_refresh.isoformat() if last_refresh else None,
            'screener_type': meta.get('screener_type'),
            'refresh_frequency': meta.get('refresh_frequency'),
            'needs_refresh': self._should_refresh_dynamic_screen(name)
        }


# 全局实例
screen_manager = ScreenManager()
