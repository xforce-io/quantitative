#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
股票排名引擎 (Stock Ranker)

基于多因子加权评分的股票排名系统
支持多种投资风格的权重配置
"""

import pandas as pd
import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from functools import lru_cache
import hashlib

from quant.core.logging_config import get_logger
from quant.data_providers.data_provider_factory import DataProviderFactory
from quant.analysis.indicators.capital_flow_analyzer import CapitalFlowAnalyzer
from quant.analysis.indicators.technical_analyzer import TechnicalAnalyzer
from quant.analysis.valuation.price_valuation import ETFValuationAnalyzer
from quant.analysis.indicators.momentum_analyzer import ShortTermMomentumAnalyzer

logger = get_logger(__name__)

# 持久化缓存目录
_CACHE_DIR = Path(__file__).parent.parent.parent.parent / 'cache' / 'ranking'
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_cache_file() -> Path:
    """获取当日缓存文件路径"""
    today = datetime.now().strftime('%Y%m%d')
    return _CACHE_DIR / f'scores_{today}.json'


def _load_cache() -> Dict[str, Dict[str, float]]:
    """从文件加载当日缓存"""
    cache_file = _get_cache_file()
    if cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"已加载排名缓存: {len(data)} 条记录")
                return data
        except Exception as e:
            logger.warning(f"加载缓存文件失败: {e}")
    return {}


def _save_cache(cache: Dict[str, Dict[str, float]]):
    """保存缓存到文件"""
    cache_file = _get_cache_file()
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"保存缓存文件失败: {e}")


def _cleanup_old_cache(keep_days: int = 3):
    """清理旧的缓存文件，保留最近 N 天"""
    try:
        for cache_file in _CACHE_DIR.glob('scores_*.json'):
            # 提取日期
            date_str = cache_file.stem.replace('scores_', '')
            try:
                file_date = datetime.strptime(date_str, '%Y%m%d')
                if (datetime.now() - file_date).days > keep_days:
                    cache_file.unlink()
                    logger.debug(f"删除旧缓存: {cache_file.name}")
            except ValueError:
                continue
    except Exception as e:
        logger.debug(f"清理缓存失败: {e}")


# 启动时清理旧缓存
_cleanup_old_cache()

# 内存缓存 (从文件加载)
_score_cache: Dict[str, Dict[str, float]] = _load_cache()


class StockRanker:
    """股票排名引擎"""

    # 默认权重配置 (4因子: money_flow, technical, valuation, trend)
    DEFAULT_PROFILES = {
        'short_term': {'money_flow': 0.35, 'technical': 0.30, 'valuation': 0.05, 'trend': 0.30},
        'balanced': {'money_flow': 0.25, 'technical': 0.25, 'valuation': 0.25, 'trend': 0.25},
        'value': {'money_flow': 0.15, 'technical': 0.15, 'valuation': 0.55, 'trend': 0.15},
        'trend': {'money_flow': 0.20, 'technical': 0.20, 'valuation': 0.10, 'trend': 0.50},
        'momentum': {'money_flow': 0.40, 'technical': 0.15, 'valuation': 0.05, 'trend': 0.40},
    }

    def __init__(self, data_provider_name: str = 'tushare', use_cache: bool = True):
        """
        初始化排名引擎

        Args:
            data_provider_name: 数据提供商名称
            use_cache: 是否使用缓存
        """
        self.data_provider = DataProviderFactory.create(data_provider_name, enableCache=use_cache)
        self.capital_flow_analyzer = CapitalFlowAnalyzer(data_provider_name, use_cache)
        self.technical_analyzer = TechnicalAnalyzer()
        self.valuation_analyzer = ETFValuationAnalyzer()
        self.momentum_analyzer = ShortTermMomentumAnalyzer(data_provider_name, mode='advanced')

        # 加载权重配置
        self.profiles = self._load_profiles()

    def _load_profiles(self) -> Dict[str, Dict]:
        """加载权重配置文件"""
        config_path = Path(__file__).parent.parent.parent.parent / 'config' / 'ranking_profiles.yaml'

        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    profiles = {}
                    for name, profile in config.get('profiles', {}).items():
                        profiles[name] = profile.get('weights', {})
                    if profiles:
                        logger.debug(f"已加载 {len(profiles)} 个排名配置")
                        return profiles
            except Exception as e:
                logger.warning(f"加载配置文件失败: {e}, 使用默认配置")

        return self.DEFAULT_PROFILES

    def get_available_profiles(self) -> List[str]:
        """获取可用的配置名称列表"""
        return list(self.profiles.keys())

    def clear_cache(self):
        """清除分数缓存（内存和文件）"""
        global _score_cache
        count = len(_score_cache)
        _score_cache.clear()

        # 删除当日缓存文件
        cache_file = _get_cache_file()
        if cache_file.exists():
            cache_file.unlink()

        logger.info(f"已清除 {count} 条缓存记录")

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        global _score_cache
        cache_file = _get_cache_file()
        return {
            'cache_size': len(_score_cache),
            'cached_symbols': list(_score_cache.keys()),
            'cache_file': str(cache_file),
            'cache_file_exists': cache_file.exists()
        }

    def rank(
        self,
        symbols: List[str],
        profile: str = 'balanced',
        days: int = 60,
        top_n: Optional[int] = None
    ) -> pd.DataFrame:
        """
        对股票列表进行排名

        Args:
            symbols: 股票代码列表
            profile: 权重配置名称
            days: 分析数据的天数
            top_n: 返回前N名，None表示返回全部

        Returns:
            包含排名结果的DataFrame
        """
        if profile not in self.profiles:
            logger.warning(f"未知配置 '{profile}', 使用 'balanced'")
            profile = 'balanced'

        weights = self.profiles[profile]
        logger.info(f"开始排名: {len(symbols)} 只标的, 配置: {profile}")
        logger.debug(f"权重: {weights}")

        results = []
        for i, symbol in enumerate(symbols):
            logger.debug(f"分析 [{i+1}/{len(symbols)}]: {symbol}")
            try:
                scores = self._calculate_scores(symbol, days)
                composite_score = self._calculate_composite_score(scores, weights)

                results.append({
                    'symbol': symbol,
                    'composite_score': composite_score,
                    'money_flow_score': scores.get('money_flow', 0),
                    'technical_score': scores.get('technical', 0),
                    'valuation_score': scores.get('valuation', 0),
                    'trend_score': scores.get('trend', 0),
                    'status': 'success'
                })
            except Exception as e:
                logger.warning(f"分析 {symbol} 失败: {e}")
                results.append({
                    'symbol': symbol,
                    'composite_score': 0,
                    'money_flow_score': 0,
                    'technical_score': 0,
                    'valuation_score': 0,
                    'trend_score': 0,
                    'status': f'error: {str(e)}'
                })

        # 创建DataFrame并排序
        df = pd.DataFrame(results)
        df = df.sort_values('composite_score', ascending=False).reset_index(drop=True)
        df['rank'] = range(1, len(df) + 1)

        # 调整列顺序
        columns = ['rank', 'symbol', 'composite_score', 'money_flow_score',
                   'technical_score', 'valuation_score', 'trend_score', 'status']
        df = df[columns]

        if top_n is not None and top_n > 0:
            df = df.head(top_n)

        # 批量保存缓存，避免频繁IO
        global _score_cache
        _save_cache(_score_cache)
        logger.info(f"排名完成: 缓存已更新，共 {len(_score_cache)} 条记录")

        logger.info(f"排名完成: 成功 {len(df[df['status'] == 'success'])} 只")
        return df

    def _calculate_scores(self, symbol: str, days: int) -> Dict[str, float]:
        """
        计算单只股票的各因子分数（带持久化缓存）

        Args:
            symbol: 股票代码
            days: 分析天数

        Returns:
            各因子分数字典
        """
        global _score_cache

        # 缓存键
        cache_key = f"{symbol}_{days}"

        # 检查缓存（当日缓存文件已在模块加载时读取）
        if cache_key in _score_cache:
            logger.debug(f"{symbol} 使用缓存分数")
            return _score_cache[cache_key]

        scores = {}

        # 1. 资金流向分数
        try:
            scores['money_flow'] = self.capital_flow_analyzer.score(symbol, days)
        except Exception as e:
            logger.debug(f"{symbol} 资金流向分析失败: {e}")
            scores['money_flow'] = 50.0

        # 2. 获取价格数据用于技术和估值分析
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days + 252)).strftime('%Y%m%d')
            price_data = self.data_provider.getStockData(symbol, start_date, end_date, 'D')
        except Exception as e:
            logger.debug(f"{symbol} 获取价格数据失败: {e}")
            price_data = pd.DataFrame()

        # 3. 技术形态分数
        try:
            scores['technical'] = self.technical_analyzer.score(symbol, price_data)
        except Exception as e:
            logger.debug(f"{symbol} 技术分析失败: {e}")
            scores['technical'] = 50.0

        # 4. 估值分数
        try:
            scores['valuation'] = self.valuation_analyzer.score(symbol, price_data)
        except Exception as e:
            logger.debug(f"{symbol} 估值分析失败: {e}")
            scores['valuation'] = 50.0

        # 5. 趋势分数 (使用 ShortTermMomentumAnalyzer 的高级模式)
        try:
            momentum_result = self.momentum_analyzer.analyze_symbol(symbol, days=days)
            if 'error' not in momentum_result:
                # momentum_score 范围是 0-100，直接使用
                scores['trend'] = float(momentum_result.get('momentum_score', 50))
            else:
                scores['trend'] = 50.0
        except Exception as e:
            logger.debug(f"{symbol} 趋势分析失败: {e}")
            scores['trend'] = 50.0

        # 存入内存缓存
        _score_cache[cache_key] = scores
        # _save_cache(_score_cache)  # 移除：改为在 rank 方法结束时统一保存，避免频繁IO
        logger.debug(f"{symbol} 分数已计算并存入内存缓存")

        return scores

    def _calculate_composite_score(self, scores: Dict[str, float], weights: Dict[str, float]) -> float:
        """
        计算加权综合分数

        Args:
            scores: 各因子分数 (每个因子分数范围 0-100)
            weights: 权重配置 (权重之和应为 1.0)

        Returns:
            综合分数 (0-100)
        """
        composite = 0.0
        total_weight = 0.0

        for factor, weight in weights.items():
            if factor in scores:
                composite += scores[factor] * weight
                total_weight += weight

        # 归一化：如果部分因子缺失，按实际权重比例计算
        # 例如：如果只有 money_flow(0.33) 和 technical(0.33) 有值，
        # 则 total_weight=0.66，需要将结果放大到完整范围
        if total_weight > 0:
            composite = composite / total_weight

        return round(composite, 2)

    def rank_from_config(
        self,
        screen_name: str,
        profile: str = 'balanced',
        days: int = 60,
        top_n: Optional[int] = None,
        config_path: str = 'config/screens.yaml'
    ) -> pd.DataFrame:
        """
        从配置文件加载股票池并排名

        Args:
            screen_name: 配置中的股票池名称
            profile: 权重配置名称
            days: 分析天数
            top_n: 返回前N名
            config_path: 配置文件路径

        Returns:
            排名结果DataFrame
        """
        symbols = self._load_symbols_from_config(screen_name, config_path)

        if not symbols:
            logger.error(f"未找到股票池: {screen_name}")
            return pd.DataFrame()

        logger.info(f"从 {screen_name} 加载了 {len(symbols)} 只标的")
        return self.rank(symbols, profile, days, top_n)

    def _load_symbols_from_config(self, screen_name: str, config_path: str) -> List[str]:
        """从配置文件加载股票代码列表"""
        config_file = Path(config_path)
        if not config_file.is_absolute():
            config_file = Path(__file__).parent.parent.parent.parent / config_path

        if not config_file.exists():
            logger.error(f"配置文件不存在: {config_file}")
            return []

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            screens = config.get('screens', {})
            if screen_name not in screens:
                return []

            screen_data = screens[screen_name]
            # 提取股票代码
            symbols = []
            for key, value in screen_data.items():
                if isinstance(value, dict) and 'symbol' in value:
                    symbols.append(value['symbol'])
                elif isinstance(value, str):
                    symbols.append(value)

            return symbols

        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return []

    def format_ranking_report(self, df: pd.DataFrame, profile: str) -> str:
        """
        格式化排名结果为可读报告

        Args:
            df: 排名结果DataFrame
            profile: 使用的配置名称

        Returns:
            格式化的文本报告
        """
        if df.empty:
            return "无排名数据"

        weights = self.profiles.get(profile, self.profiles['balanced'])

        lines = [
            "=" * 80,
            f"📊 股票排名报告",
            f"📅 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"⚙️  排名配置: {profile}",
            f"📈 权重设置: 资金流向={weights.get('money_flow', 0):.0%}, "
            f"技术形态={weights.get('technical', 0):.0%}, "
            f"估值={weights.get('valuation', 0):.0%}, "
            f"趋势={weights.get('trend', 0):.0%}",
            "=" * 80,
            "",
            f"{'排名':<6}{'代码':<12}{'综合分':<10}{'资金分':<10}{'技术分':<10}{'估值分':<10}{'趋势分':<10}{'状态':<10}",
            "-" * 90
        ]

        for _, row in df.iterrows():
            status = '✓' if row['status'] == 'success' else '✗'
            lines.append(
                f"{row['rank']:<6}{row['symbol']:<12}"
                f"{row['composite_score']:<10.1f}"
                f"{row['money_flow_score']:<10.1f}"
                f"{row['technical_score']:<10.1f}"
                f"{row['valuation_score']:<10.1f}"
                f"{row['trend_score']:<10.1f}"
                f"{status:<10}"
            )

        lines.extend([
            "",
            "=" * 80,
            f"共 {len(df)} 只标的, 成功分析 {len(df[df['status'] == 'success'])} 只",
            "⚠️  提示: 排名仅供参考，不构成投资建议",
            "=" * 80
        ])

        return "\n".join(lines)


def test_ranker():
    """测试排名引擎"""
    logger.info("测试股票排名引擎...")

    ranker = StockRanker()

    # 测试股票列表
    test_symbols = ['000001.SZ', '002594.SZ', '600036.SH']

    print("\n可用配置:", ranker.get_available_profiles())

    # 测试不同配置
    for profile in ['short_term', 'balanced', 'value']:
        print(f"\n--- 测试配置: {profile} ---")
        result = ranker.rank(test_symbols, profile=profile, days=30)
        print(ranker.format_ranking_report(result, profile))


if __name__ == '__main__':
    test_ranker()
