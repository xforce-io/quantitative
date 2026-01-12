#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资金流向分析器 (Capital Flow Analyzer)

提供个股资金流向、北向资金、主力资金等多维度分析功能
用于增强advisor工具的投资决策能力

主要功能:
1. 个股资金流向分析 - 主力/大单/中单/小单资金流向
2. 北向资金关注度分析 - 港资偏好和关注度变化
3. 板块资金流向分析 - 行业轮动和热点追踪
4. 资金流向趋势分析 - 短期和中期资金流向趋势
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import warnings
warnings.filterwarnings('ignore')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from quant.data_providers.data_provider_factory import DataProviderFactory
import yaml

from quant.core.logging_config import get_logger
logger = get_logger(__name__)



class CapitalFlowAnalyzer:
    """资金流向分析器"""

    def score(self, symbol: str, days: int = 30) -> float:
        """
        计算资金流向评分 (0-100)

        Args:
            symbol: 股票代码
            days: 分析天数

        Returns:
            0-100 的标准化分数，资金流入越强分数越高
        """
        result = self.analyze_stock_money_flow(symbol, days)
        return result.get('comprehensive_score', 0.0)

    def __init__(self, data_provider_name: str = 'tushare', use_cache: bool = True):
        """
        初始化资金流向分析器

        Args:
            data_provider_name: 数据提供商名称
            use_cache: 是否使用缓存
        """
        self.data_provider = DataProviderFactory.create(data_provider_name, enableCache=use_cache)
        self.use_cache = use_cache

        # 缓存数据避免重复请求
        self._flow_cache = {}
        self._hsgt_cache = {}

    def analyze_stock_money_flow(self, symbol: str, days: int = 30) -> Dict[str, Any]:
        """
        分析个股资金流向

        Args:
            symbol: 股票代码
            days: 分析天数

        Returns:
            Dict包含主力净流入比例、大单趋势、资金流向一致性、机构关注度等指标
        """
        try:
            # 计算日期范围
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days+20)).strftime('%Y%m%d')

            # 获取资金流向数据
            flow_data = self._get_money_flow_data(symbol, start_date, end_date)

            if flow_data.empty:
                return self._get_empty_flow_result("无资金流向数据")

            # 取最近的days天数据
            recent_data = flow_data.tail(days)

            if len(recent_data) < 5:  # 至少需要5天数据
                return self._get_empty_flow_result("数据量不足")

            # 1. 主力净流入比例分析
            main_inflow_analysis = self._analyze_main_inflow(recent_data)

            # 2. 大单趋势分析
            large_order_analysis = self._analyze_large_order_trend(recent_data)

            # 3. 资金流向一致性分析
            consistency_analysis = self._analyze_flow_consistency(recent_data)

            # 4. 机构关注度分析 (基于大单和特大单活跃度)
            institutional_analysis = self._analyze_institutional_interest(recent_data)

            # 5. 综合评分计算
            comprehensive_score = self._calculate_flow_score(
                main_inflow_analysis, large_order_analysis,
                consistency_analysis, institutional_analysis
            )

            return {
                'symbol': symbol,
                'analysis_period': f'{days}天',
                'data_quality': {
                    'total_days': len(recent_data),
                    'valid_data_ratio': len(recent_data.dropna()) / len(recent_data),
                    'latest_date': recent_data.index[-1].strftime('%Y-%m-%d') if len(recent_data) > 0 else None
                },
                'main_inflow_ratio': main_inflow_analysis['avg_ratio'],
                'main_inflow_trend': main_inflow_analysis['trend'],
                'main_inflow_stability': main_inflow_analysis['stability'],
                'large_order_trend': large_order_analysis['trend_direction'],
                'large_order_strength': large_order_analysis['trend_strength'],
                'flow_consistency': consistency_analysis['consistency_score'],
                'flow_direction_agreement': consistency_analysis['direction_agreement'],
                'institutional_interest': institutional_analysis['interest_level'],
                'institutional_activity': institutional_analysis['activity_score'],
                'comprehensive_score': comprehensive_score,
                'risk_signals': self._identify_risk_signals(recent_data),
                'opportunity_signals': self._identify_opportunity_signals(recent_data),
                'detailed_metrics': {
                    'recent_5d_main_inflow': recent_data['main_inflow_ratio'].tail(5).mean() if 'main_inflow_ratio' in recent_data.columns else 0,
                    'recent_5d_large_net': recent_data['large_net_amount'].tail(5).sum() if 'large_net_amount' in recent_data.columns else 0,
                    'max_single_day_inflow': recent_data['net_main_amount'].max() if 'net_main_amount' in recent_data.columns else 0,
                    'max_single_day_outflow': recent_data['net_main_amount'].min() if 'net_main_amount' in recent_data.columns else 0
                }
            }

        except Exception as e:
            logger.info("分析个股资金流向失败 {symbol}: {str(e)}")
            return self._get_empty_flow_result(f"分析失败: {str(e)}")

    def analyze_northbound_flow(self, symbol: str, days: int = 60) -> Dict[str, Any]:
        """
        分析北向资金关注度

        Args:
            symbol: 股票代码
            days: 分析天数

        Returns:
            Dict包含北向资金关注度、持续性、变化趋势等指标
        """
        try:
            # 计算日期范围
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days+20)).strftime('%Y%m%d')

            # 获取沪深港通数据
            hsgt_data = self._get_hsgt_data(start_date, end_date)

            if hsgt_data.empty:
                return self._get_empty_northbound_result("无北向资金数据")

            # 获取该股票在HSGT Top10中的出现情况
            top10_analysis = self._analyze_hsgt_top10_appearance(symbol, days)

            # 分析北向资金整体流向趋势
            overall_trend = self._analyze_hsgt_overall_trend(hsgt_data.tail(days))

            # 计算股票的北向资金关注度
            attention_score = self._calculate_northbound_attention(top10_analysis, overall_trend)

            return {
                'symbol': symbol,
                'analysis_period': f'{days}天',
                'northbound_attention': attention_score,
                'top10_appearances': top10_analysis['appearance_count'],
                'avg_rank_in_top10': top10_analysis['avg_rank'],
                'recent_trend': top10_analysis['recent_trend'],
                'overall_northbound_trend': overall_trend['trend_direction'],
                'market_sentiment': overall_trend['market_sentiment'],
                'relative_preference': self._calculate_relative_preference(top10_analysis, overall_trend)
            }

        except Exception as e:
            logger.info("分析北向资金关注度失败 {symbol}: {str(e)}")
            return self._get_empty_northbound_result(f"分析失败: {str(e)}")

    def analyze_sector_flow(self, symbols: List[str], days: int = 20) -> Dict[str, Any]:
        """
        分析板块资金流向

        Args:
            symbols: 股票代码列表
            days: 分析天数

        Returns:
            Dict包含板块整体资金流向、个股贡献度、热点强度等
        """
        try:
            sector_flows = {}
            total_flow = 0
            valid_stocks = 0

            # 分析每只股票的资金流向
            for symbol in symbols:
                flow_result = self.analyze_stock_money_flow(symbol, days)
                if flow_result.get('main_inflow_ratio') is not None:
                    sector_flows[symbol] = flow_result
                    total_flow += flow_result.get('detailed_metrics', {}).get('recent_5d_main_inflow', 0)
                    valid_stocks += 1

            if valid_stocks == 0:
                return {'error': '板块内无有效资金流向数据', 'valid_stocks': 0}

            # 计算板块指标
            avg_inflow_ratio = total_flow / valid_stocks

            # 找出资金流入最强的个股
            top_inflow_stocks = sorted(
                [(symbol, data['main_inflow_ratio']) for symbol, data in sector_flows.items()],
                key=lambda x: x[1], reverse=True
            )[:3]

            # 计算板块资金流向一致性
            flow_directions = [1 if data['main_inflow_ratio'] > 0 else -1 for data in sector_flows.values()]
            consistency = abs(sum(flow_directions)) / len(flow_directions)

            # 板块热度评估
            heat_score = self._calculate_sector_heat(sector_flows, avg_inflow_ratio, consistency)

            return {
                'sector_symbol_count': len(symbols),
                'valid_stocks': valid_stocks,
                'avg_main_inflow_ratio': avg_inflow_ratio,
                'sector_consistency': consistency,
                'sector_heat_score': heat_score,
                'top_inflow_stocks': top_inflow_stocks,
                'sector_trend': 'inflow' if avg_inflow_ratio > 0.02 else 'outflow' if avg_inflow_ratio < -0.02 else 'neutral',
                'individual_analysis': sector_flows
            }

        except Exception as e:
            logger.info("分析板块资金流向失败: {str(e)}")
            return {'error': f'分析失败: {str(e)}'}

    def _get_money_flow_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取资金流向数据（带缓存）"""
        cache_key = f"{symbol}_{start_date}_{end_date}"

        if cache_key in self._flow_cache:
            return self._flow_cache[cache_key]

        try:
            data = self.data_provider.getMoneyFlow(symbol, start_date, end_date)
            self._flow_cache[cache_key] = data
            return data
        except Exception as e:
            logger.info("获取资金流向数据失败 {symbol}: {str(e)}")
            return pd.DataFrame()

    def _get_hsgt_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """获取沪深港通数据（带缓存）"""
        cache_key = f"hsgt_{start_date}_{end_date}"

        if cache_key in self._hsgt_cache:
            return self._hsgt_cache[cache_key]

        try:
            data = self.data_provider.getHSGTFlow(start_date, end_date)
            self._hsgt_cache[cache_key] = data
            return data
        except Exception as e:
            logger.info("获取HSGT数据失败: {str(e)}")
            return pd.DataFrame()

    def _analyze_main_inflow(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析主力净流入"""
        if 'main_inflow_ratio' not in data.columns:
            return {'avg_ratio': 0, 'trend': 'unknown', 'stability': 0}

        ratios = data['main_inflow_ratio'].dropna()

        if len(ratios) == 0:
            return {'avg_ratio': 0, 'trend': 'unknown', 'stability': 0}

        avg_ratio = ratios.mean()

        # 趋势分析：最近5天 vs 前期
        if len(ratios) >= 10:
            recent = ratios.tail(5).mean()
            earlier = ratios.head(len(ratios)-5).mean()
            if recent > earlier + 0.01:
                trend = 'improving'
            elif recent < earlier - 0.01:
                trend = 'deteriorating'
            else:
                trend = 'stable'
        else:
            trend = 'insufficient_data'

        # 稳定性分析
        stability = 1 - (ratios.std() / (abs(ratios.mean()) + 0.01))
        stability = max(0, min(1, stability))

        return {
            'avg_ratio': float(avg_ratio),
            'trend': trend,
            'stability': float(stability)
        }

    def _analyze_large_order_trend(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析大单趋势"""
        if 'large_net_amount' not in data.columns:
            return {'trend_direction': 'unknown', 'trend_strength': 0}

        large_flows = data['large_net_amount'].dropna()

        if len(large_flows) < 5:
            return {'trend_direction': 'unknown', 'trend_strength': 0}

        # 计算趋势方向
        positive_days = (large_flows > 0).sum()
        total_days = len(large_flows)

        if positive_days / total_days > 0.6:
            direction = 'bullish'
        elif positive_days / total_days < 0.4:
            direction = 'bearish'
        else:
            direction = 'neutral'

        # 计算趋势强度
        strength = abs(large_flows.mean()) / (large_flows.std() + 1e-6)
        strength = min(1, strength / 1000000)  # 标准化

        return {
            'trend_direction': direction,
            'trend_strength': float(strength)
        }

    def _analyze_flow_consistency(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析资金流向一致性"""
        flow_columns = ['small_net_amount', 'mid_net_amount', 'large_net_amount', 'xlarge_net_amount']
        available_columns = [col for col in flow_columns if col in data.columns]

        if len(available_columns) < 2:
            return {'consistency_score': 0, 'direction_agreement': 0}

        # 计算各类资金的方向一致性
        direction_agreement = 0
        consistency_scores = []

        for idx, row in data.iterrows():
            directions = [1 if row[col] > 0 else -1 if row[col] < 0 else 0 for col in available_columns if pd.notna(row[col])]
            if len(directions) > 1:
                agreement = abs(sum(directions)) / len(directions)
                consistency_scores.append(agreement)

        if consistency_scores:
            avg_consistency = np.mean(consistency_scores)
            direction_agreement = len([s for s in consistency_scores if s > 0.5]) / len(consistency_scores)
        else:
            avg_consistency = 0
            direction_agreement = 0

        return {
            'consistency_score': float(avg_consistency),
            'direction_agreement': float(direction_agreement)
        }

    def _analyze_institutional_interest(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析机构关注度"""
        # 基于大单和特大单的活跃度
        large_cols = ['large_buy_amount', 'large_sell_amount', 'xlarge_buy_amount', 'xlarge_sell_amount']
        available_cols = [col for col in large_cols if col in data.columns]

        if not available_cols:
            return {'interest_level': 'low', 'activity_score': 0}

        # 计算大单活跃度
        total_activity = 0
        for col in available_cols:
            total_activity += data[col].sum()

        # 转换为标准化分数
        activity_score = min(1, total_activity / 1e8)  # 以1亿为基准标准化

        if activity_score > 0.7:
            interest_level = 'high'
        elif activity_score > 0.3:
            interest_level = 'medium'
        else:
            interest_level = 'low'

        return {
            'interest_level': interest_level,
            'activity_score': float(activity_score)
        }

    def _calculate_flow_score(self, main_analysis, large_analysis, consistency_analysis, institutional_analysis) -> float:
        """计算综合资金流评分"""
        score = 0

        # 主力资金流入权重 40%
        main_ratio = main_analysis['avg_ratio']
        if main_ratio > 0.05:
            score += 40
        elif main_ratio > 0.02:
            score += 30
        elif main_ratio > 0:
            score += 20
        elif main_ratio > -0.02:
            score += 10
        else:
            score += 0

        # 大单趋势权重 25%
        if large_analysis['trend_direction'] == 'bullish':
            score += 25 * large_analysis['trend_strength']
        elif large_analysis['trend_direction'] == 'bearish':
            score -= 25 * large_analysis['trend_strength']

        # 一致性权重 20%
        score += 20 * consistency_analysis['consistency_score']

        # 机构关注度权重 15%
        activity_bonus = {'high': 15, 'medium': 10, 'low': 5}
        score += activity_bonus.get(institutional_analysis['interest_level'], 5)

        return max(0, min(100, score))

    def _analyze_hsgt_top10_appearance(self, symbol: str, days: int) -> Dict[str, Any]:
        """分析股票在HSGT Top10中的出现情况"""
        # 这里简化处理，实际需要循环查询每日的top10数据
        # 由于API限制，这里返回模拟结果
        return {
            'appearance_count': 0,
            'avg_rank': 0,
            'recent_trend': 'stable'
        }

    def _analyze_hsgt_overall_trend(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析HSGT整体趋势"""
        if data.empty:
            return {'trend_direction': 'unknown', 'market_sentiment': 'neutral'}

        # 分析北向资金整体流向
        if 'hk2sh_net' in data.columns and 'hk2sz_net' in data.columns:
            total_net = data['hk2sh_net'] + data['hk2sz_net']
            avg_net = total_net.mean()

            if avg_net > 1e8:  # 1亿以上
                trend = 'strong_inflow'
                sentiment = 'bullish'
            elif avg_net > 0:
                trend = 'inflow'
                sentiment = 'positive'
            elif avg_net < -1e8:
                trend = 'strong_outflow'
                sentiment = 'bearish'
            else:
                trend = 'outflow'
                sentiment = 'negative'
        else:
            trend = 'unknown'
            sentiment = 'neutral'

        return {
            'trend_direction': trend,
            'market_sentiment': sentiment
        }

    def _calculate_northbound_attention(self, top10_analysis: Dict, overall_trend: Dict) -> float:
        """计算北向资金关注度评分"""
        base_score = top10_analysis['appearance_count'] * 10
        rank_bonus = max(0, 11 - top10_analysis['avg_rank']) if top10_analysis['avg_rank'] > 0 else 0

        return min(100, base_score + rank_bonus)

    def _calculate_relative_preference(self, top10_analysis: Dict, overall_trend: Dict) -> str:
        """计算相对偏好"""
        if top10_analysis['appearance_count'] > 5:
            return 'high_preference'
        elif top10_analysis['appearance_count'] > 2:
            return 'medium_preference'
        else:
            return 'low_preference'

    def _calculate_sector_heat(self, sector_flows: Dict, avg_inflow: float, consistency: float) -> float:
        """计算板块热度评分"""
        # 基于平均流入、一致性和个股强度
        base_score = max(0, min(50, avg_inflow * 1000 + 25))  # 基础分数
        consistency_score = consistency * 30  # 一致性分数

        # 强势个股加分
        strong_stocks = len([data for data in sector_flows.values()
                           if data.get('main_inflow_ratio', 0) > 0.05])
        strength_bonus = min(20, strong_stocks * 5)

        return base_score + consistency_score + strength_bonus

    def _identify_risk_signals(self, data: pd.DataFrame) -> List[str]:
        """识别风险信号"""
        signals = []

        if 'net_main_amount' in data.columns:
            recent_outflow = data['net_main_amount'].tail(3)
            if (recent_outflow < 0).all():
                signals.append("连续3日主力资金净流出")

        if 'main_inflow_ratio' in data.columns:
            avg_ratio = data['main_inflow_ratio'].tail(5).mean()
            if avg_ratio < -0.05:
                signals.append("近5日主力净流出比例超过5%")

        return signals

    def _identify_opportunity_signals(self, data: pd.DataFrame) -> List[str]:
        """识别机会信号"""
        signals = []

        if 'net_main_amount' in data.columns:
            recent_inflow = data['net_main_amount'].tail(3)
            if (recent_inflow > 0).all():
                signals.append("连续3日主力资金净流入")

        if 'main_inflow_ratio' in data.columns:
            avg_ratio = data['main_inflow_ratio'].tail(5).mean()
            if avg_ratio > 0.05:
                signals.append("近5日主力净流入比例超过5%")

        return signals

    def _get_empty_flow_result(self, reason: str) -> Dict[str, Any]:
        """返回空的资金流向分析结果"""
        return {
            'main_inflow_ratio': None,
            'large_order_trend': 'unknown',
            'flow_consistency': 0,
            'institutional_interest': 'unknown',
            'comprehensive_score': 0,
            'error': reason
        }

    def _get_empty_northbound_result(self, reason: str) -> Dict[str, Any]:
        """返回空的北向资金分析结果"""
        return {
            'northbound_attention': 0,
            'top10_appearances': 0,
            'avg_rank_in_top10': 0,
            'recent_trend': 'unknown',
            'overall_northbound_trend': 'unknown',
            'market_sentiment': 'neutral',
            'error': reason
        }

    def analyze_industry_flow(
        self,
        industry_symbols: Dict[str, List[str]],
        days: int = 30
    ) -> Dict[str, Dict[str, Any]]:
        """
        分析多个行业的资金流向

        Args:
            industry_symbols: 行业代码映射 {industry_name: [symbol1, symbol2, ...]}
            days: 分析天数

        Returns:
            Dict包含各行业的资金流向分析结果
        """
        industry_results = {}

        for industry_name, symbols in industry_symbols.items():
            logger.info("正在分析行业: {industry_name} (包含 {len(symbols)} 只股票)...")

            # 分析该行业的板块资金流向
            sector_result = self.analyze_sector_flow(symbols, days)

            if 'error' not in sector_result:
                # 增强行业数据
                individual_analysis = sector_result.get('individual_analysis', {})

                # 计算额外的行业指标
                avg_institutional = sum(
                    data.get('institutional_activity', 0)
                    for data in individual_analysis.values()
                ) / len(individual_analysis) if individual_analysis else 0

                # 找出强势股票
                top_stocks = sorted(
                    [(symbol, data.get('comprehensive_score', 0))
                     for symbol, data in individual_analysis.items()],
                    key=lambda x: x[1],
                    reverse=True
                )[:5]

                industry_results[industry_name] = {
                    'avg_inflow_ratio': sector_result['avg_main_inflow_ratio'],
                    'sector_heat_score': sector_result['sector_heat_score'],
                    'sector_consistency': sector_result['sector_consistency'],
                    'valid_stocks': sector_result['valid_stocks'],
                    'sector_trend': sector_result['sector_trend'],
                    'top_stocks': top_stocks,
                    'avg_institutional_activity': avg_institutional,
                    'individual_analysis': individual_analysis
                }
            else:
                logger.info("  ⚠️ 行业 {industry_name} 分析失败: {sector_result.get('error')}")
                industry_results[industry_name] = {
                    'avg_inflow_ratio': 0,
                    'sector_heat_score': 0,
                    'sector_consistency': 0,
                    'valid_stocks': 0,
                    'sector_trend': 'unknown',
                    'error': sector_result.get('error')
                }

        return industry_results

    def load_industry_symbols_from_config(
        self,
        config_path: str = 'config/screens.yaml',
        selected_industries: Optional[List[str]] = None
    ) -> Dict[str, List[str]]:
        """
        从配置文件加载行业股票列表

        Args:
            config_path: 配置文件路径
            selected_industries: 选择的行业列表，None表示加载所有

        Returns:
            行业股票映射字典
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            screens = config.get('screens', {})
            industry_symbols = {}

            # 行业映射（从screen名称到友好的行业名称）
            industry_name_mapping = {
                'BANK': '银行',
                'SEMICONDUCTOR': '半导体',
                'NEW_ENERGY': '新能源',
                'HEALTHCARE': '医药生物',
                'TECH_GROWTH': '科技成长',
                'HKTECH': '港股科技'
            }

            for screen_name, stocks in screens.items():
                # 跳过非行业类别（如GLOBAL、INDUSTRY_ETF等）
                if screen_name in ['GLOBAL', 'INDUSTRY_ETF']:
                    continue

                # 如果指定了行业列表，则过滤
                if selected_industries and screen_name not in selected_industries:
                    continue

                # 获取友好的行业名称
                friendly_name = industry_name_mapping.get(screen_name, screen_name)

                # 提取股票代码（排除ETF）
                stock_symbols = [
                    info['symbol']
                    for symbol, info in stocks.items()
                    if info.get('market') == 'A股'  # 只取A股，排除ETF
                ]

                if stock_symbols:
                    industry_symbols[friendly_name] = stock_symbols

            return industry_symbols

        except Exception as e:
            logger.info("加载行业配置失败: {str(e)}")
            return {}


def test_capital_flow_analyzer():
    """测试资金流向分析器"""
    logger.info("🔄 测试资金流向分析器...")

    analyzer = CapitalFlowAnalyzer()

    # 测试个股资金流向分析
    test_symbol = "002594.SZ"
    logger.info("\n📊 测试个股资金流向分析: {test_symbol}")

    flow_result = analyzer.analyze_stock_money_flow(test_symbol, days=20)
    logger.info("资金流向分析结果:")
    logger.info("主力净流入比例: {flow_result.get('main_inflow_ratio', 'N/A')}")
    logger.info("大单趋势: {flow_result.get('large_order_trend', 'N/A')}")
    logger.info("资金流向一致性: {flow_result.get('flow_consistency', 'N/A')}")
    logger.info("机构关注度: {flow_result.get('institutional_interest', 'N/A')}")
    logger.info("综合评分: {flow_result.get('comprehensive_score', 'N/A')}")

    # 测试北向资金分析
    logger.info("\n🌏 测试北向资金分析: {test_symbol}")
    northbound_result = analyzer.analyze_northbound_flow(test_symbol, days=30)
    logger.info("北向资金分析结果:")
    logger.info("关注度评分: {northbound_result.get('northbound_attention', 'N/A')}")
    logger.info("整体趋势: {northbound_result.get('overall_northbound_trend', 'N/A')}")
    logger.info("市场情绪: {northbound_result.get('market_sentiment', 'N/A')}")

    logger.info("\n✅ 资金流向分析器测试完成")


if __name__ == '__main__':
    test_capital_flow_analyzer()