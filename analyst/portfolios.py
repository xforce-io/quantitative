#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
投资组合配置文件 (Portfolio Configurations)

支持多个预定义投资组合的配置管理，包括股票信息、风险特征、流动性评估等。
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any, Union
import json
from pathlib import Path
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class SymbolInfo:
    """标的信息数据类"""
    symbol: str
    name: str
    market: str = 'unknown'  # A股、港股、美股、指数
    sector: str = 'unknown'  # 行业分类
    volatility: str = 'medium'  # low, medium, high
    liquidity: str = 'good'  # poor, fair, good, excellent
    
    def to_dict(self):
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'name': self.name,
            'market': self.market,
            'sector': self.sector,
            'volatility': self.volatility,
            'liquidity': self.liquidity
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建实例"""
        return cls(
            symbol=data['symbol'],
            name=data['name'],
            market=data.get('market', 'unknown'),
            sector=data.get('sector', 'unknown'),
            volatility=data.get('volatility', 'medium'),
            liquidity=data.get('liquidity', 'good')
        )


@dataclass
class Sleeve:
    """投资袖套（Sleeve）数据类 - 组合内的子分组"""
    name: str  # sleeve名称
    target_return: float  # 目标年化收益率（如 0.01 = 1%）
    risk_level: str  # 风险级别: conservative, income, growth, aggressive
    allocation_ratio: float  # 在整个组合中的配置比例
    symbols: Dict[str, float]  # 该sleeve内的标的及权重
    description: str = ''  # 描述

    def to_dict(self):
        """转换为字典"""
        return {
            'name': self.name,
            'target_return': self.target_return,
            'risk_level': self.risk_level,
            'allocation_ratio': self.allocation_ratio,
            'symbols': self.symbols,
            'description': self.description
        }

    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建实例"""
        return cls(
            name=data['name'],
            target_return=data['target_return'],
            risk_level=data['risk_level'],
            allocation_ratio=data['allocation_ratio'],
            symbols=data['symbols'],
            description=data.get('description', '')
        )


# 指数到可交易ETF的代理映射（分析-交易解耦）
INDEX_TO_ETF_PROXY: Dict[str, str] = {
    'IXIC': '513100.SH',     # 纳指 -> 纳指100ETF
    'NDX': '513100.SH',
    'SPX': '513500.SH',      # 标普 -> 标普500ETF
    'SP500': '513500.SH',
    'DJI': '513030.SH',      # 道琼斯 -> 道琼斯ETF（若无则留空或自定义）
    'HSI': '159920.SZ',      # 恒生 -> 恒生ETF
    'HKTECH': '513330.SH',   # 恒生科技 -> 恒生科技ETF
}


# 组合配置（外部配置为唯一事实源；此处初始化为空，由 _try_load_from_config 填充）
PORTFOLIOS: Dict[str, Dict[str, SymbolInfo]] = {}

# 投资组合元数据（外部配置为唯一事实源；此处初始化为空）
PORTFOLIO_META: Dict[str, Dict[str, Any]] = {}

# 投资组合的Sleeve配置
PORTFOLIO_SLEEVES: Dict[str, List[Sleeve]] = {}


class PortfolioManager:
    """投资组合管理器

    - 管理组合与分类（portfolio vs screen）
    - 支持推荐权重与自定义权重
    - 支持指数到ETF的代理映射
    - 提供基础校验与权重生成器
    """
    
    def __init__(self):
        self.portfolios: Dict[str, Dict[str, SymbolInfo]] = PORTFOLIOS
        self.portfolio_meta: Dict[str, Dict[str, Any]] = PORTFOLIO_META
        self.portfolio_sleeves: Dict[str, List[Sleeve]] = PORTFOLIO_SLEEVES
        # 可选：用户自定义权重（优先级高于推荐权重）
        self.custom_weights: Dict[str, Dict[str, float]] = {}
        # 启动时尝试从 config/ 加载外部配置
        try:
            self._try_load_from_config()
        except Exception as e:
            logger.debug(f"加载配置失败（忽略，使用内置默认）: {e}")
        # 严格模式校验
        self._validate_or_fail()
    
    def get_portfolio(self, name: str) -> Dict[str, SymbolInfo]:
        """获取投资组合"""
        if name not in self.portfolios:
            raise ValueError(f"投资组合 '{name}' 不存在。可用组合: {list(self.portfolios.keys())}")
        return self.portfolios[name]
    
    def get_portfolio_meta(self, name: str) -> Dict[str, str]:
        """获取投资组合元数据"""
        return self.portfolio_meta.get(name, {})
    
    def get_type(self, name: str) -> str:
        meta = self.get_portfolio_meta(name)
        return meta.get('type', 'portfolio')
    
    def get_recommended_weights(self, name: str) -> Optional[Dict[str, float]]:
        meta = self.get_portfolio_meta(name)
        return meta.get('recommended_weights')
    
    def get_weights(self, name: str, use_recommended: bool = True, use_sleeves: bool = False) -> Optional[Dict[str, float]]:
        """获取组合权重

        Args:
            name: 组合名称
            use_recommended: 是否使用推荐权重
            use_sleeves: 是否使用sleeve配置生成权重
        """
        if name in self.custom_weights:
            return self.custom_weights[name]

        # 如果使用sleeve配置
        if use_sleeves and name in self.portfolio_sleeves:
            return self._calculate_sleeve_weights(name)

        if use_recommended:
            return self.get_recommended_weights(name)
        return None
    
    def set_weights(self, name: str, weights: Dict[str, float]) -> None:
        """设置自定义权重（将覆盖推荐权重用于聚合展示/回测）"""
        # 规范化
        total = sum(max(0.0, float(w)) for w in weights.values())
        if total <= 0:
            raise ValueError('权重和必须大于0')
        self.custom_weights[name] = {k: float(v) / total for k, v in weights.items() if k in self.portfolios.get(name, {})}
    
    def clear_weights(self, name: Optional[str] = None) -> None:
        if name is None:
            self.custom_weights.clear()
        else:
            self.custom_weights.pop(name, None)
    
    def list_portfolios(self) -> List[str]:
        """列出所有可用投资组合"""
        return list(self.portfolios.keys())
    
    def get_symbols_by_sector(self, portfolio_name: str, sector: str) -> List[str]:
        """按行业筛选标的"""
        portfolio = self.get_portfolio(portfolio_name)
        return [symbol for symbol, info in portfolio.items() if info.sector == sector]
    
    def get_symbols_by_risk(self, portfolio_name: str, risk_level: str) -> List[str]:
        """按风险等级筛选标的"""
        portfolio = self.get_portfolio(portfolio_name)
        return [symbol for symbol, info in portfolio.items() if info.volatility == risk_level]
    
    def create_custom_portfolio(self, name: str, symbols: List[str], 
                              symbol_names: List[str] = None, 
                              sectors: List[str] = None) -> Dict[str, SymbolInfo]:
        """创建自定义投资组合"""
        if not symbol_names:
            symbol_names = [f'标的{i+1}' for i in range(len(symbols))]
        if not sectors:
            sectors = ['unknown'] * len(symbols)
        
        if len(symbols) != len(symbol_names) or len(symbols) != len(sectors):
            raise ValueError("symbols, symbol_names, sectors 长度必须一致")
        
        custom_portfolio = {}
        for i, symbol in enumerate(symbols):
            custom_portfolio[symbol] = SymbolInfo(
                symbol=symbol,
                name=symbol_names[i],
                market='A股',
                sector=sectors[i]
            )
        
        self.portfolios[name] = custom_portfolio
        # 缺省标注为 portfolio（用户自建组合）
        self.portfolio_meta[name] = {
            'description': f'自定义组合 {name}',
            'type': 'portfolio',
            'risk_level': 'medium',
            'investment_style': 'custom',
            'suitable_for': '高级用户',
            'rebalance_frequency': 'monthly'
        }
        return custom_portfolio
    
    # ========= 代理与符号工具 =========
    def apply_index_proxy(self, symbol: str) -> str:
        """将指数符号映射为可交易ETF（若存在）"""
        return INDEX_TO_ETF_PROXY.get(symbol.upper(), symbol)
    
    def get_trade_symbols(self, name: str, use_proxy: bool = True) -> List[str]:
        portfolio = self.get_portfolio(name)
        symbols = list(portfolio.keys())
        if not use_proxy:
            return symbols
        return [self.apply_index_proxy(s) for s in symbols]

    # ========= Sleeve管理 =========
    def get_sleeves(self, portfolio_name: str) -> List[Sleeve]:
        """获取组合的sleeve配置"""
        return self.portfolio_sleeves.get(portfolio_name, [])

    def set_sleeves(self, portfolio_name: str, sleeves: List[Sleeve]):
        """设置组合的sleeve配置"""
        # 验证总配置比例为1
        total_allocation = sum(s.allocation_ratio for s in sleeves)
        if abs(total_allocation - 1.0) > 1e-6:
            raise ValueError(f"Sleeve配置比例总和必须为1，当前为{total_allocation:.4f}")

        # 验证每个sleeve内部权重和为1
        for sleeve in sleeves:
            if sleeve.symbols:
                symbol_total = sum(sleeve.symbols.values())
                if abs(symbol_total - 1.0) > 1e-6:
                    raise ValueError(f"Sleeve '{sleeve.name}' 内部权重和必须为1，当前为{symbol_total:.4f}")

        self.portfolio_sleeves[portfolio_name] = sleeves

    def add_sleeve(self, portfolio_name: str, sleeve: Sleeve):
        """向组合添加一个sleeve"""
        if portfolio_name not in self.portfolio_sleeves:
            self.portfolio_sleeves[portfolio_name] = []
        self.portfolio_sleeves[portfolio_name].append(sleeve)
        # 重新验证总配置比例
        total_allocation = sum(s.allocation_ratio for s in self.portfolio_sleeves[portfolio_name])
        if abs(total_allocation - 1.0) > 1e-6:
            logger.warning(f"警告：组合 '{portfolio_name}' 的sleeve配置比例总和为{total_allocation:.4f}，需要调整")

    def _calculate_sleeve_weights(self, portfolio_name: str) -> Dict[str, float]:
        """基于sleeve配置计算组合的最终权重"""
        sleeves = self.get_sleeves(portfolio_name)
        if not sleeves:
            return None

        final_weights = {}
        for sleeve in sleeves:
            # 该sleeve在整个组合中的配置比例
            sleeve_allocation = sleeve.allocation_ratio

            # 计算该sleeve内每个标的在整个组合中的权重
            for symbol, symbol_weight in sleeve.symbols.items():
                final_weight = sleeve_allocation * symbol_weight
                if symbol in final_weights:
                    final_weights[symbol] += final_weight
                else:
                    final_weights[symbol] = final_weight

        # 归一化（确保总和为1）
        total = sum(final_weights.values())
        if total > 0:
            final_weights = {k: v/total for k, v in final_weights.items()}

        return final_weights

    def create_default_sleeves(self, portfolio_name: str):
        """为组合创建默认的sleeve配置"""
        portfolio = self.get_portfolio(portfolio_name)
        symbols = list(portfolio.keys())

        if not symbols:
            return

        # 创建4个默认sleeve
        sleeves = []

        # Conservative Bucket (1% target) - 10% allocation
        conservative_symbols = [s for s in symbols if portfolio[s].volatility == 'low']
        if not conservative_symbols:
            conservative_symbols = symbols[:max(1, len(symbols)//4)]
        sleeves.append(Sleeve(
            name='Conservative',
            target_return=0.01,
            risk_level='conservative',
            allocation_ratio=0.10,
            symbols={s: 1.0/len(conservative_symbols) for s in conservative_symbols},
            description='现金管理/货币基金等低风险资产'
        ))

        # Income Bucket (4% target) - 30% allocation
        income_symbols = [s for s in symbols if portfolio[s].sector in ['金融', '银行', '保险']]
        if not income_symbols:
            income_symbols = symbols[len(symbols)//4:len(symbols)//2]
        sleeves.append(Sleeve(
            name='Income',
            target_return=0.04,
            risk_level='income',
            allocation_ratio=0.30,
            symbols={s: 1.0/len(income_symbols) for s in income_symbols},
            description='债券/分红股等收益型资产'
        ))

        # Growth Bucket (12% target) - 40% allocation
        growth_symbols = [s for s in symbols if portfolio[s].volatility == 'medium']
        if not growth_symbols:
            growth_symbols = symbols[len(symbols)//2:3*len(symbols)//4]
        sleeves.append(Sleeve(
            name='Growth',
            target_return=0.12,
            risk_level='growth',
            allocation_ratio=0.40,
            symbols={s: 1.0/len(growth_symbols) for s in growth_symbols},
            description='蓝筹成长股等平衡型资产'
        ))

        # Aggressive Bucket (30% target) - 20% allocation
        aggressive_symbols = [s for s in symbols if portfolio[s].volatility == 'high']
        if not aggressive_symbols:
            aggressive_symbols = symbols[3*len(symbols)//4:]
        sleeves.append(Sleeve(
            name='Aggressive',
            target_return=0.30,
            risk_level='aggressive',
            allocation_ratio=0.20,
            symbols={s: 1.0/len(aggressive_symbols) for s in aggressive_symbols},
            description='小盘股/新兴行业等高风险高收益资产'
        ))

        self.set_sleeves(portfolio_name, sleeves)
    
    # ========= 权重生成器 =========
    def build_weights(self, name_or_symbols: Union[str, List[str]], method: str = 'equal', lookback_days: int = 252,
                      single_stock_max: float = 0.10, etf_max: float = 0.20) -> Dict[str, float]:
        """为给定集合生成权重

        method:
          - equal: 等权
          - inv_vol: 波动率逆权（需本地CSV，缺失则回退等权）
        """
        # 支持传入组合名或符号列表
        if isinstance(name_or_symbols, str):
            symbols = list(self.get_portfolio(name_or_symbols).keys())
        else:
            symbols = list(name_or_symbols)
        if not symbols:
            return {}
        if method == 'equal':
            w = 1.0 / len(symbols)
            return {s: w for s in symbols}
        if method == 'inv_vol':
            vols: Dict[str, float] = {}
            for s in symbols:
                try:
                    df = self._load_local_prices(s, lookback_days)
                    if df is None or df.shape[0] < max(60, int(lookback_days*0.4)):
                        continue
                    returns = df['close'].pct_change().dropna()
                    vol = float(returns.std())
                    if vol and vol > 0:
                        vols[s] = vol
                except Exception as e:
                    logger.debug(f'计算波动率失败 {s}: {e}')
            if not vols:
                logger.warning('未能计算到有效波动率，回退等权')
                return {s: 1.0/len(symbols) for s in symbols}
            inv = {s: 1.0/v for s, v in vols.items()}
            total = sum(inv.values())
            weights = {s: inv.get(s, 0.0)/total for s in symbols}
            # 施加上限并归一
            def _is_etf(sym: str) -> bool:
                up = sym.upper()
                return (up.startswith('5') and (up.endswith('.SH') or up.endswith('.SZ')))
            capped = {}
            residual = 1.0
            adjustable: List[str] = []
            for s, w in weights.items():
                cap = etf_max if _is_etf(s) else single_stock_max
                w_c = min(max(w, 0.0), cap)
                capped[s] = w_c
                residual -= w_c
                if w > w_c:
                    # 被截断的，不再参与增配
                    pass
                else:
                    adjustable.append(s)
            if residual > 1e-8 and adjustable:
                add = residual / len(adjustable)
                for s in adjustable:
                    capped[s] += add
                residual = 0.0
            # 归一
            norm = sum(capped.values())
            if norm <= 0:
                return {s: 1.0/len(symbols) for s in symbols}
            return {s: v/norm for s, v in capped.items()}
        # 默认等权
        return {s: 1.0/len(symbols) for s in symbols}
    
    def _load_local_prices(self, symbol: str, lookback_days: int = 252):
        """尝试从 data/ 中加载本地CSV，返回最近 lookback_days 行，包含 close 列。
        支持命名模式：
          - {SYMBOL}_*_D.csv
          - index_{SYMBOL}_*_D.csv
          - fund_{SYMBOL}_*_D.csv
          - global_{SYMBOL}_*_D.csv
        """
        try:
            import pandas as pd
        except Exception:
            return None
        root = Path(__file__).parent.parent / 'data'
        if not root.exists():
            return None
        up = symbol.upper()
        patterns = [
            f"{up}_*_D.csv",
            f"index_{up}_*_D.csv",
            f"fund_{up}_*_D.csv",
            f"global_{up}_*_D.csv",
        ]
        files: List[Path] = []
        for pat in patterns:
            files.extend(root.glob(pat))
        if not files:
            return None
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for fp in files:
            try:
                df = pd.read_csv(fp)
                # 兼容不同列名
                cols = {c.lower(): c for c in df.columns}
                if 'close' not in cols:
                    # 常见收盘列名
                    for cand in ['CLOSE', 'close_price', 'Close', 'C']:
                        if cand in df.columns:
                            df['close'] = df[cand]
                            break
                if 'close' not in df.columns:
                    continue
                # 截取最近 lookback_days 行
                if df.shape[0] > lookback_days:
                    df = df.tail(lookback_days)
                return df
            except Exception:
                continue
        return None
    
    def save_to_json(self, filepath: str):
        """保存投资组合到JSON文件"""
        data = {
            'portfolios': {},
            'portfolio_meta': self.portfolio_meta,
            'portfolio_sleeves': {},
            'custom_weights': self.custom_weights,
            'index_proxy_map': INDEX_TO_ETF_PROXY,
        }

        for name, portfolio in self.portfolios.items():
            data['portfolios'][name] = {
                symbol: info.to_dict() for symbol, info in portfolio.items()
            }

        # 保存sleeve配置
        for name, sleeves in self.portfolio_sleeves.items():
            data['portfolio_sleeves'][name] = [sleeve.to_dict() for sleeve in sleeves]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_from_json(self, filepath: str):
        """从JSON文件加载投资组合"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.portfolio_meta = data.get('portfolio_meta', {})
        # 自定义权重与代理
        self.custom_weights = data.get('custom_weights', {})
        proxy_map = data.get('index_proxy_map')
        if isinstance(proxy_map, dict):
            INDEX_TO_ETF_PROXY.update({k.upper(): v for k, v in proxy_map.items()})
        self.portfolios = {}

        for name, portfolio_data in data.get('portfolios', {}).items():
            self.portfolios[name] = {
                symbol: SymbolInfo.from_dict(info_dict)
                for symbol, info_dict in portfolio_data.items()
            }

        # 加载sleeve配置
        self.portfolio_sleeves = {}
        for name, sleeves_data in data.get('portfolio_sleeves', {}).items():
            self.portfolio_sleeves[name] = [Sleeve.from_dict(sleeve_dict) for sleeve_dict in sleeves_data]

    # ========= 配置加载 =========
    def _expand_env(self, obj: Any) -> Any:
        """递归展开 ${ENV} 变量"""
        if isinstance(obj, dict):
            return {k: self._expand_env(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._expand_env(x) for x in obj]
        if isinstance(obj, str):
            return os.path.expandvars(obj)
        return obj

    def _load_yaml_or_json(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            if path.suffix.lower() in {'.yml', '.yaml'}:
                try:
                    import yaml  # type: ignore
                except Exception as e:
                    logger.warning(f"找不到yaml解析器(pyyaml)，跳过 {path.name}")
                    return None
                with open(path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            return self._expand_env(data)
        except Exception as e:
            logger.warning(f"读取配置失败 {path}: {e}")
            return None

    def _try_load_from_config(self) -> None:
        cfg_dir = PROJECT_ROOT / 'config'
        if not cfg_dir.exists():
            return
        # index proxies
        for fname in ['index_proxies.yaml', 'index_proxies.yml', 'index_proxies.json']:
            data = self._load_yaml_or_json(cfg_dir / fname)
            if isinstance(data, dict):
                mapping = data.get('index_proxy_map') if 'index_proxy_map' in data else data
                if isinstance(mapping, dict):
                    INDEX_TO_ETF_PROXY.update({str(k).upper(): str(v) for k, v in mapping.items()})
                break

        # portfolios
        for fname in ['portfolios.yaml', 'portfolios.yml', 'portfolios.json']:
            data = self._load_yaml_or_json(cfg_dir / fname)
            if not isinstance(data, dict):
                continue
            # 支持两种结构：
            # 1) 与 save_to_json 相同: { portfolios: {name: {symbol: info}}, portfolio_meta: {...}, custom_weights: {...} }
            # 2) 简化: { DEFAULT: { symbols: {...}, recommended_weights: {...} }, meta: {...} }
            if 'portfolios' in data:
                # 结构1
                raw_port = data.get('portfolios', {})
                new_portfolios: Dict[str, Dict[str, SymbolInfo]] = {}
                for name, p in raw_port.items():
                    if isinstance(p, dict):
                        new_portfolios[name] = {s: SymbolInfo.from_dict(v) if isinstance(v, dict) else SymbolInfo(s, str(v)) for s, v in p.items()}
                if new_portfolios:
                    self.portfolios = new_portfolios
                # meta / 权重 / sleeves
                if isinstance(data.get('portfolio_meta'), dict):
                    self.portfolio_meta = data['portfolio_meta']
                if isinstance(data.get('custom_weights'), dict):
                    # 直接采用（不做归一，使用时会归一）
                    self.custom_weights = {k: {ks: float(vs) for ks, vs in v.items()} for k, v in data['custom_weights'].items()}
                if isinstance(data.get('portfolio_sleeves'), dict):
                    self.portfolio_sleeves = {}
                    for name, sleeves_data in data['portfolio_sleeves'].items():
                        if isinstance(sleeves_data, list):
                            self.portfolio_sleeves[name] = [Sleeve.from_dict(s) for s in sleeves_data]
                break
            else:
                # 结构2（仅覆盖 DEFAULT）
                if 'DEFAULT' in data and isinstance(data['DEFAULT'], dict):
                    block = data['DEFAULT']
                    symbols = block.get('symbols') or block
                    if isinstance(symbols, dict):
                        self.portfolios['DEFAULT'] = {s: SymbolInfo.from_dict(v) if isinstance(v, dict) else SymbolInfo(s, str(v)) for s, v in symbols.items()}
                    # 推荐权重/meta
                    pm = self.portfolio_meta.get('DEFAULT', {}).copy()
                    if isinstance(block.get('recommended_weights'), dict):
                        pm['recommended_weights'] = {k: float(v) for k, v in block['recommended_weights'].items()}
                    self.portfolio_meta['DEFAULT'] = pm
                break

    # ========= 校验 =========
    def _validate_or_fail(self) -> None:
        strict = os.getenv('STRICT_CONFIG', 'true').lower() in ('1', 'true', 'yes')
        errors: List[str] = []
        # 组合存在性
        if not self.portfolios:
            errors.append('未加载到任何投资组合（请在 config/portfolios.yaml 定义 portfolios）')
        # 元数据匹配
        for name in self.portfolios.keys():
            meta = self.portfolio_meta.get(name, {})
            if not meta:
                errors.append(f"组合 {name} 缺少元数据（portfolio_meta.{name}）")
            if meta and meta.get('type', 'portfolio') != 'portfolio':
                errors.append(f"组合 {name} 的 type 应为 'portfolio'，但得到 '{meta.get('type')}'")
            # 推荐权重（若存在）校验和为1
            rw = meta.get('recommended_weights') if meta else None
            if isinstance(rw, dict) and rw:
                s = sum(float(v) for v in rw.values())
                if abs(s - 1.0) > 1e-6:
                    errors.append(f"组合 {name} 的 recommended_weights 权重和不为1（当前 {s:.6f}）")
                # 符号一致性
                for sym in rw.keys():
                    if sym not in self.portfolios[name]:
                        errors.append(f"组合 {name} 的权重中包含未在symbols中出现的标的: {sym}")

        if errors:
            msg = '\n'.join(errors)
            if strict:
                raise ValueError(f"配置校验失败（严格模式）:\n{msg}")
            else:
                logger.warning(f"配置存在问题（宽松模式）：\n{msg}")


# 创建全局实例
portfolio_manager = PortfolioManager()
