#!/usr/bin/env python3
"""
ETF动量筛选器 - ETF Momentum Screener
专门筛选动量和趋势都很好的ETF产品

筛选条件：
1. 短期动量指标（1-3个月）
2. 中期趋势指标（3-6个月）
3. 长期趋势指标（6-12个月）
4. 成交量确认
5. 相对强度表现
6. 回撤控制
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import logging
from typing import Dict, List, Optional, Tuple
import os
import json
import yaml
from pathlib import Path

# 使用新架构的统一数据提供器
from quant.data import create_data_provider
from quant.core.indicators import TechnicalIndicators
from quant.analysis.etf_valuation_analyzer import ETFValuationAnalyzer
from quant.analysis.screener.industry_classifier import SubIndustryClassifier
from quant.analysis.screener.relative_strength_analyzer import RelativeStrengthAnalyzer
from quant.analysis.screener.peg_valuation_analyzer import PEGValuationAnalyzer
from quant.analysis.screener.industry_fundamentals_analyzer import IndustryFundamentalsAnalyzer

# 设置日志
logger = logging.getLogger(__name__)


class ETFMomentumScreener:
    """ETF动量筛选器"""
    
    def __init__(self, token: str = None):
        """
        初始化ETF筛选器
        
        Args:
            token: Tushare token，如果为None则从环境变量获取
        """
        if token is None:
            token = os.getenv('TUSHARE_TOKEN')
        
        if not token:
            logger.warning("未设置TUSHARE_TOKEN，将使用Yahoo Finance作为数据源")
        
        # 筛选条件配置
        self.screening_config = {
            'momentum': {
                '1month_return_min': 3.0,      # 1个月最小收益率 %
                '3month_return_min': 8.0,      # 3个月最小收益率 %
                '6month_return_min': 15.0,     # 6个月最小收益率 %
                '12month_return_min': 20.0,    # 12个月最小收益率 %
                'rsi_min': 40.0,               # RSI最小值
                'rsi_max': 90.0,               # RSI最大值（放宽至90，避免错过强势标的）
                'macd_signal': 'positive',     # MACD信号要求
                'momentum_decay_threshold': 0.5,  # 动能衰竭阈值（1月/6月收益率比）
                'peak_drawdown_warning': 0.90     # 峰值警告阈值（距12月高点90%以上即警告）
            },
            'trend': {
                'ma5_above_ma20': True,        # 5日均线在20日均线之上
                'ma20_above_ma60': True,       # 20日均线在60日均线之上
                'price_above_ma20': True,      # 价格在20日均线之上
                'trend_strength_min': 0.6,    # 趋势强度最小值 (0-1)
                'donchian_position_min': 0.7  # 价格在唐奇安通道的位置 (0-1)
            },
            'volume': {
                'volume_ratio_min': 1.0,       # 成交量比率最小值
                'volume_trend': 'increasing',  # 成交量趋势要求
                'avg_volume_min': 1000000      # 日均成交量最小值
            },
            'quality': {
                'max_drawdown_max': 0.25,      # 最大回撤上限 25%
                'volatility_max': 0.40,        # 波动率上限 40%
                'sharpe_ratio_min': 0.5,       # 夏普比率最小值
                'tracking_error_max': 0.05     # 跟踪误差上限 5%
            }
        }
        
        # 加载ETF分类配置
        try:
            self.etf_categories = self._load_etf_categories()
        except Exception as e:
            logger.warning(f"加载ETF分类配置失败: {e}")
            self.etf_categories = {}
        
        # 使用新架构的数据提供器
        try:
            config = {'token': token} if token else {}
            provider_type = 'tushare' if token else 'yahoo'
            self.data_provider = create_data_provider(provider_type, config)
            logger.info(f"✅ 成功初始化数据提供者 ({provider_type})")
        except Exception as e:
            logger.error(f"初始化数据提供者失败: {e}")
            # 尝试Yahoo Finance作为备用
            try:
                self.data_provider = create_data_provider('yahoo', {})
                logger.info("✅ 使用Yahoo Finance作为备用数据源")
            except Exception as e2:
                logger.error(f"备用数据源也失败: {e2}")
                raise
        
        # 报告输出目录（按日期组织）
        today = datetime.now().strftime("%Y%m%d")
        self.report_dir = Path("reports") / "etf_screening" / today
        self.report_dir.mkdir(parents=True, exist_ok=True)

        # 估值分析器
        self.valuation_analyzer = ETFValuationAnalyzer()

        # 🆕 子行业分类器
        try:
            self.industry_classifier = SubIndustryClassifier()
            logger.info("✅ 子行业分类器初始化完成")
        except Exception as e:
            logger.warning(f"子行业分类器初始化失败: {e}")
            self.industry_classifier = None

        # 🆕 相对强弱分析器
        try:
            self.rs_analyzer = RelativeStrengthAnalyzer(default_benchmark='000300.SH')
            logger.info("✅ 相对强弱分析器初始化完成")
        except Exception as e:
            logger.warning(f"相对强弱分析器初始化失败: {e}")
            self.rs_analyzer = None

        # 🆕 PEG估值分析器 (阶段2)
        try:
            self.peg_analyzer = PEGValuationAnalyzer(data_provider=self.data_provider)
            logger.info("✅ PEG估值分析器初始化完成")
        except Exception as e:
            logger.warning(f"PEG估值分析器初始化失败: {e}")
            self.peg_analyzer = None

        # 🆕 行业基本面分析器 (阶段2)
        try:
            self.fundamentals_analyzer = IndustryFundamentalsAnalyzer()
            logger.info("✅ 行业基本面分析器初始化完成")
        except Exception as e:
            logger.warning(f"行业基本面分析器初始化失败: {e}")
            self.fundamentals_analyzer = None

    def _load_etf_categories(self) -> dict:
        """从配置文件加载ETF分类"""
        config_file = Path(__file__).parent.parent.parent.parent / 'config' / 'etf_categories.yaml'
        if not config_file.exists():
            logger.warning(f"ETF分类配置文件不存在: {config_file}")
            return {}

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config.get('etf_categories', {})
        except Exception as e:
            logger.error(f"加载ETF分类配置失败: {e}")
            return {}

    def get_fallback_etf_list(self, include_types: List[str] = None) -> pd.DataFrame:
        """从配置文件获取ETF列表"""
        logger.info("从配置加载ETF列表...")
        
        if not self.etf_categories:
            logger.warning("ETF分类配置为空，返回空列表")
            return pd.DataFrame()
        
        # 构建DataFrame
        etf_list = []
        for category_key, category_data in self.etf_categories.items():
            # 如果指定了类型过滤
            if include_types and category_key not in include_types:
                continue
            
            etfs = category_data.get('etfs', [])
            for etf_info in etfs:
                etf_list.append({
                    'ts_code': etf_info.get('code', ''),
                    'name': etf_info.get('name', ''),
                    'category': category_key,
                    'benchmark': etf_info.get('benchmark', '')
                })
        
        df = pd.DataFrame(etf_list)
        logger.info(f"加载了 {len(df)} 只ETF")
        return df
    
    def get_etf_list(self, include_types: List[str] = None) -> pd.DataFrame:
        """
        获取ETF列表
        
        Args:
            include_types: 包含的ETF类型列表，如['broad_market', 'sector']
            
        Returns:
            ETF基本信息DataFrame
        """
        # 直接使用预定义的ETF列表
        return self.get_fallback_etf_list(include_types)
    
    def get_etf_price_data(self, ts_code: str, months_back: int = 15) -> pd.DataFrame:
        """
        获取ETF价格数据
        
        Args:
            ts_code: ETF代码
            months_back: 向前获取几个月的数据
            
        Returns:
            价格数据DataFrame
        """
        try:
            # 计算日期范围
            end_date = datetime.now()
            start_date = end_date - timedelta(days=months_back * 30)
            
            # 获取价格数据 - 使用正确的接口
            price_data = self.data_provider.get_stock_data(
                ts_code,
                start_date.strftime('%Y%m%d'),
                end_date.strftime('%Y%m%d'),
                'D'
            )
            
            if price_data is None or price_data.empty:
                logger.warning(f"未获取到 {ts_code} 的价格数据")
                return pd.DataFrame()
            
            # 确保数据按日期升序排列
            if 'date' in price_data.columns:
                price_data = price_data.set_index('date')
            price_data = price_data.sort_index()
            
            return price_data
            
        except Exception as e:
            logger.error(f"获取 {ts_code} 价格数据失败: {e}")
            return pd.DataFrame()
    
    def calculate_momentum_indicators(self, price_data: pd.DataFrame) -> Dict:
        """
        计算动量指标（增强版）
        
        Args:
            price_data: 价格数据
            
        Returns:
            动量指标字典（失败时返回带默认值的字典）
        """
        # 数据验证
        if price_data.empty or len(price_data) < 252:  # 至少需要1年数据
            logger.warning(f"数据不足以计算动量指标: {len(price_data)} < 252")
            return self._get_default_momentum_indicators()
        
        try:
            # 计算不同期间的收益率
            current_price = price_data['close'].iloc[-1]
            
            # 计算回溯收益率
            returns = {}
            periods = {
                '1month': 21,    # 约1个月
                '3month': 63,    # 约3个月
                '6month': 126,   # 约6个月
                '12month': 252   # 约12个月
            }
            
            for period_name, days in periods.items():
                if len(price_data) > days:
                    past_price = price_data['close'].iloc[-(days+1)]
                    returns[f'{period_name}_return'] = (current_price - past_price) / past_price * 100
                else:
                    returns[f'{period_name}_return'] = 0.0
            
            # 🆕 计算12个月内的最高价和回撤
            if len(price_data) >= 252:
                recent_12m_data = price_data.tail(252)
                peak_price_12m = recent_12m_data['close'].max()
                drawdown_from_peak = (current_price - peak_price_12m) / peak_price_12m * 100
                distance_to_peak_pct = current_price / peak_price_12m  # 距离峰值的百分比
            else:
                peak_price_12m = current_price
                drawdown_from_peak = 0.0
                distance_to_peak_pct = 1.0
            
            # 🆕 动能衰竭检测：1月收益 vs 6月收益
            momentum_decay_ratio = 0.0
            momentum_status = "正常"
            if returns.get('6month_return', 0) > 0:
                momentum_decay_ratio = returns.get('1month_return', 0) / returns.get('6month_return', 1)
                if momentum_decay_ratio < 0.3 and returns.get('1month_return', 0) < 5:
                    momentum_status = "动能衰竭"
                elif momentum_decay_ratio < 0:
                    momentum_status = "动能转负"
            
            # 🆕 动量趋势分析：前6月 vs 后6月
            momentum_trend = "稳定"
            if len(price_data) >= 252:
                # 前6个月收益率（6-12个月前）
                price_12m_ago = price_data['close'].iloc[-(252+1)]
                price_6m_ago = price_data['close'].iloc[-(126+1)]
                first_6m_return = (price_6m_ago - price_12m_ago) / price_12m_ago * 100
                
                # 后6个月收益率（近6个月）
                recent_6m_return = returns.get('6month_return', 0)
                
                if recent_6m_return > first_6m_return * 1.5:
                    momentum_trend = "加速上涨"
                elif recent_6m_return < first_6m_return * 0.5:
                    momentum_trend = "减速滞涨"
            
            # 计算RSI
            rsi = TechnicalIndicators.calculate_rsi(price_data)
            current_rsi = rsi.iloc[-1] if not rsi.empty else 50.0
            
            # 计算MACD
            macd_dict = TechnicalIndicators.calculate_macd(price_data)
            current_macd = macd_dict['MACD'].iloc[-1] if not macd_dict['MACD'].empty else 0.0
            current_macd_signal = macd_dict['MACD_Signal'].iloc[-1] if not macd_dict['MACD_Signal'].empty else 0.0
            macd_histogram = macd_dict['MACD_Histogram'].iloc[-1] if not macd_dict['MACD_Histogram'].empty else 0.0
            
            momentum_indicators = {
                **returns,
                'rsi': current_rsi,
                'macd': current_macd,
                'macd_signal': current_macd_signal,
                'macd_histogram': macd_histogram,
                # 新增指标
                'peak_price_12m': peak_price_12m,
                'drawdown_from_peak_pct': drawdown_from_peak,
                'distance_to_peak_pct': distance_to_peak_pct,
                'momentum_decay_ratio': momentum_decay_ratio,
                'momentum_status': momentum_status,
                'momentum_trend': momentum_trend
            }
            
            return momentum_indicators
            
        except Exception as e:
            logger.error(f"计算动量指标失败: {e}")
            return self._get_default_momentum_indicators()
    
    def _get_default_momentum_indicators(self) -> Dict:
        """返回默认动量指标（避免KeyError）"""
        return {
            '1month_return': 0.0,
            '3month_return': 0.0,
            '6month_return': 0.0,
            '12month_return': 0.0,
            'rsi': 50.0,
            'macd': 0.0,
            'macd_signal': 0.0,
            'macd_histogram': 0.0,
            'peak_price_12m': 0.0,
            'drawdown_from_peak_pct': 0.0,
            'distance_to_peak_pct': 1.0,
            'momentum_decay_ratio': 0.0,
            'momentum_status': '数据不足',
            'momentum_trend': '未知'
        }
    
    def analyze_etf(self, ts_code: str, include_valuation: bool = True, include_rs: bool = True) -> Dict:
        """
        分析单只ETF（增强版v3，包含估值、子行业、相对强弱分析）

        Args:
            ts_code: ETF代码
            include_valuation: 是否包含估值分析
            include_rs: 是否包含相对强弱分析

        Returns:
            分析结果字典
        """
        logger.info(f"开始分析ETF: {ts_code}")

        # 获取价格数据
        price_data = self.get_etf_price_data(ts_code)
        if price_data.empty:
            return {
                'success': False,
                'error': '无法获取价格数据',
                'ts_code': ts_code
            }

        # 计算动量指标
        momentum = self.calculate_momentum_indicators(price_data)

        # 🆕 子行业分类分析
        industry_meta = {}
        if self.industry_classifier:
            try:
                industry_meta = self.industry_classifier.get_industry_meta(ts_code) or {}
            except Exception as e:
                logger.warning(f"子行业分类失败 ({ts_code}): {e}")

        # 🆕 相对强弱分析
        rs_analysis = {}
        if include_rs and self.rs_analyzer:
            try:
                # 获取基准数据（指数使用get_index_data接口）
                end_date = datetime.now()
                start_date = end_date - timedelta(days=400)
                benchmark_data = self._get_benchmark_data(
                    '000300.SH',
                    start_date.strftime('%Y%m%d'),
                    end_date.strftime('%Y%m%d')
                )

                if not benchmark_data.empty:
                    rs_analysis = self.rs_analyzer.calculate_rs_rating(
                        price_data,
                        benchmark_data,
                        '000300.SH'
                    )
                else:
                    logger.warning(f"基准数据为空，跳过RS分析 ({ts_code})")
            except Exception as e:
                logger.warning(f"相对强弱分析失败 ({ts_code}): {e}")

        # 🆕 PEG估值分析 (阶段2)
        peg_analysis = {}
        if self.peg_analyzer and industry_meta:
            try:
                industry = industry_meta.get('industry', '')
                peg_analysis = self.peg_analyzer.calculate_peg_valuation(price_data, industry)
            except Exception as e:
                logger.warning(f"PEG估值分析失败 ({ts_code}): {e}")

        # 🆕 行业基本面分析 (阶段2)
        fundamentals_analysis = {}
        if self.fundamentals_analyzer and industry_meta:
            try:
                industry = industry_meta.get('industry', '')
                fundamentals_analysis = self.fundamentals_analyzer.analyze_fundamentals(industry, price_data)
            except Exception as e:
                logger.warning(f"行业基本面分析失败 ({ts_code}): {e}")
        
        # 估值分析
        valuation = {}
        if include_valuation:
            try:
                # 价格分位数分析
                percentile_analysis = self.valuation_analyzer.calculate_price_percentile(price_data)
                
                # 均值回归信号
                mean_reversion = self.valuation_analyzer.calculate_mean_reversion_signals(price_data)
                
                # 估值区间
                valuation_zone = self.valuation_analyzer.calculate_valuation_zone(price_data)
                
                valuation = {
                    'percentile': percentile_analysis.get('overall_percentile', 50),
                    'valuation_level': percentile_analysis.get('overall_valuation', '合理'),
                    'mean_reversion_signal': mean_reversion.get('signal', '持有'),
                    'valuation_zone': valuation_zone.get('valuation_zone', '合理区'),
                    'bollinger_position': mean_reversion.get('bollinger_position', 50),
                    'detailed_analysis': {
                        'percentile_analysis': percentile_analysis,
                        'mean_reversion': mean_reversion,
                        'valuation_zone': valuation_zone
                    }
                }
            except Exception as e:
                logger.warning(f"估值分析失败 ({ts_code}): {e}")
                valuation = {
                    'percentile': 50,
                    'valuation_level': '数据不足',
                    'mean_reversion_signal': '无信号',
                    'valuation_zone': '未知'
                }
        
        # 简单的筛选逻辑，记录未通过原因
        config = self.screening_config['momentum']
        momentum_score = 0
        momentum_checks = 0
        failed_reasons = []  # 记录未通过的原因

        # 1月收益率检查
        if momentum.get('1month_return', 0) >= config['1month_return_min']:
            momentum_score += 1
        else:
            failed_reasons.append(f"1月收益{momentum.get('1month_return', 0):.1f}% < {config['1month_return_min']}%")
        momentum_checks += 1

        # 3月收益率检查
        if momentum.get('3month_return', 0) >= config['3month_return_min']:
            momentum_score += 1
        else:
            failed_reasons.append(f"3月收益{momentum.get('3month_return', 0):.1f}% < {config['3month_return_min']}%")
        momentum_checks += 1

        # 6月收益率检查
        if momentum.get('6month_return', 0) >= config['6month_return_min']:
            momentum_score += 1
        else:
            failed_reasons.append(f"6月收益{momentum.get('6month_return', 0):.1f}% < {config['6month_return_min']}%")
        momentum_checks += 1

        # RSI检查
        current_rsi = momentum.get('rsi', 50)
        if config['rsi_min'] <= current_rsi <= config['rsi_max']:
            momentum_score += 1
        else:
            if current_rsi < config['rsi_min']:
                failed_reasons.append(f"RSI {current_rsi:.1f} < {config['rsi_min']}（超卖）")
            else:
                failed_reasons.append(f"RSI {current_rsi:.1f} > {config['rsi_max']}（超买）")
        momentum_checks += 1
        
        # 计算评分（结合估值、风险、RS、行业特征）
        base_score = momentum_score / momentum_checks if momentum_checks > 0 else 0

        # 🎯 "让利润奔跑"改进：估值调整 - 只在趋势反转时才惩罚
        valuation_adjustment = 0
        risk_adjustment = 0
        risk_warnings = []

        # 获取估值和趋势状态
        val_level = valuation.get('valuation_level', '合理') if (include_valuation and valuation) else '合理'
        macd = momentum.get('macd', 0)
        macd_signal = momentum.get('macd_signal', 0)
        momentum_status = momentum.get('momentum_status', '')
        momentum_trend = momentum.get('momentum_trend', '')

        # 估值策略：趋势优先
        if '极度高估' in val_level or '高估' in val_level:
            # 检查趋势反转信号
            is_macd_dead_cross = macd < macd_signal  # MACD死叉
            is_momentum_weak = momentum_status in ["动能衰竭", "动能转负"]
            is_trend_slow = momentum_trend == "减速滞涨"

            if is_macd_dead_cross and '极度高估' in val_level:
                # MACD死叉 + 极度高估 → 强烈卖出信号
                valuation_adjustment = -0.30
                risk_warnings.append("🔴 MACD死叉 + 极度高估，建议减仓")
            elif momentum_status == "动能转负" and '极度高估' in val_level:
                # 动能转负 + 极度高估 → 卖出信号
                valuation_adjustment = -0.25
                risk_warnings.append("⚠️ 动能转负 + 极度高估，谨慎持有")
            elif is_momentum_weak and '高估' in val_level:
                # 动能衰竭 + 高估 → 减分提示
                valuation_adjustment = -0.15
                risk_warnings.append("⚠️ 动能衰竭 + 高估，关注退出时机")
            elif is_trend_slow:
                # 减速滞涨 → 轻微减分
                valuation_adjustment = -0.10
                risk_warnings.append("📊 减速滞涨，注意趋势变化")
            else:
                # ✅ 强趋势中，估值仅作风险提示，不影响评分
                valuation_adjustment = 0
                if '极度高估' in val_level:
                    risk_warnings.append("💎 极度高估但趋势强劲，持续跟踪")
                else:
                    risk_warnings.append("📊 高估，关注趋势")

        elif '极度低估' in val_level:
            valuation_adjustment = 0.15
            risk_warnings.append("💰 极度低估，潜在机会")
        elif '低估' in val_level:
            valuation_adjustment = 0.10
            risk_warnings.append("📈 低估，可关注")

        # 峰值警告（仅提示，不扣分）
        if momentum.get('distance_to_peak_pct', 0) >= 0.89:
            if momentum_status not in ["动能衰竭", "动能转负"]:
                # 接近峰值但趋势仍强，仅提示
                risk_warnings.append("📍 接近12月峰值，设置止盈")

        # 动量趋势加分
        if momentum_trend == "加速上涨":
            risk_adjustment += 0.05
            if '极度高估' not in val_level:  # 非极度高估才提示加速
                risk_warnings.append("🚀 加速上涨")

        # 🆕 行业风险调整（基于产业链位置和竞争格局）
        industry_adjustment = 0
        if self.industry_classifier and industry_meta:
            try:
                industry_adjustment = self.industry_classifier.calculate_industry_risk_adjustment(
                    ts_code,
                    context={'profit_margin': 0.08}  # 可以从财务数据获取
                )
            except Exception as e:
                logger.warning(f"行业风险调整计算失败: {e}")

        # 🆕 相对强弱调整
        rs_adjustment = 0
        if include_rs and rs_analysis:
            rs_adjustment = rs_analysis.get('score_adjustment', 0)
            rs_status = rs_analysis.get('status', '同步')
            if rs_status in ['明显跑输', '弱势']:
                risk_warnings.append(f"📉 相对强弱: {rs_status}")

        # 🆕 PEG估值调整 (阶段2)
        peg_adjustment = 0
        if peg_analysis.get('available', False):
            peg_adjustment = peg_analysis.get('score_adjustment', 0)
            if peg_analysis.get('peg', 0) > 2.0:
                risk_warnings.append(f"⚠️ PEG偏高: {peg_analysis['peg']:.2f}")

        # 🆕 基本面调整 (阶段2)
        fundamentals_adjustment = 0
        if fundamentals_analysis.get('available', False):
            fundamentals_adjustment = fundamentals_analysis.get('risk_adjustment', 0)
            # 添加基本面警告
            for warning in fundamentals_analysis.get('warnings', []):
                if warning not in risk_warnings:
                    risk_warnings.append(warning)

        # 多因子综合评分 (v4.0)
        overall_score = max(0, min(1,
            base_score +           # 动量基础分 (0-1)
            valuation_adjustment + # 估值调整 (-0.1~+0.15)
            risk_adjustment +      # 风险调整 (-0.3~+0.05)
            industry_adjustment +  # 行业调整 (-0.3~+0.1)
            rs_adjustment +        # RS调整 (-0.15~+0.1)
            peg_adjustment +       # PEG调整 (-0.10~+0.15)
            fundamentals_adjustment # 基本面调整 (-0.20~+0.10)
        ))
        passes = overall_score >= 0.6  # 60%以上的条件通过即算通过
        
        return {
            'success': True,
            'ts_code': ts_code,
            'data_points': len(price_data),
            'analysis_date': datetime.now().strftime('%Y-%m-%d'),
            'momentum': momentum,
            'valuation': valuation,
            'industry_meta': industry_meta,          # 🆕 子行业分类信息
            'rs_analysis': rs_analysis,              # 🆕 相对强弱分析
            'peg_analysis': peg_analysis,            # 🆕 PEG估值分析 (阶段2)
            'fundamentals_analysis': fundamentals_analysis,  # 🆕 基本面分析 (阶段2)
            'screening_result': {
                'momentum': {
                    'score': base_score,
                    'passes': base_score >= 0.6
                },
                'overall': {
                    'score': overall_score,
                    'passes': passes,
                    'grade': 'A' if overall_score >= 0.8 else 'B' if overall_score >= 0.6 else 'C',
                    'valuation_adjustment': valuation_adjustment,
                    'risk_adjustment': risk_adjustment,
                    'industry_adjustment': industry_adjustment,       # 🆕 行业调整
                    'rs_adjustment': rs_adjustment,                   # 🆕 RS调整
                    'peg_adjustment': peg_adjustment,                 # 🆕 PEG调整 (阶段2)
                    'fundamentals_adjustment': fundamentals_adjustment, # 🆕 基本面调整 (阶段2)
                    'risk_warnings': risk_warnings,
                    'failed_reasons': failed_reasons if not passes else []  # 🆕 未通过原因
                }
            }
        }
    
    def _get_benchmark_data(self, benchmark_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取基准指数数据（统一接口）"""
        try:
            # 优先使用指数接口
            if hasattr(self.data_provider, 'get_index_data'):
                data = self.data_provider.get_index_data(benchmark_code, start_date, end_date, 'D')
                if not data.empty:
                    return data
            
            # 降级使用股票接口（某些provider不区分）
            logger.debug(f"降级使用 get_stock_data 获取指数 {benchmark_code}")
            return self.data_provider.get_stock_data(benchmark_code, start_date, end_date, 'D')
        
        except Exception as e:
            logger.error(f"获取基准数据失败 ({benchmark_code}): {e}")
            return pd.DataFrame()
    
    def screen_etfs(self, etf_types: List[str] = None, max_etfs: int = None) -> pd.DataFrame:
        """
        筛选ETF
        
        Args:
            etf_types: ETF类型列表，如['broad_market', 'sector']
            max_etfs: 最大分析ETF数量
            
        Returns:
            筛选结果DataFrame
        """
        logger.info("🚀 开始ETF动量筛选...")
        
        # 获取ETF列表
        etf_list = self.get_etf_list(etf_types)
        if etf_list.empty:
            logger.error("未获取到ETF列表")
            return pd.DataFrame()
        
        # 限制分析数量
        if max_etfs:
            etf_list = etf_list.head(max_etfs)
        
        logger.info(f"准备分析 {len(etf_list)} 只ETF")
        
        # 分析每只ETF
        results = []
        for idx, (_, etf_info) in enumerate(etf_list.iterrows()):
            ts_code = etf_info['ts_code']
            logger.info(f"分析进度: {idx + 1}/{len(etf_list)} - {ts_code}")
            
            # 分析ETF
            analysis_result = self.analyze_etf(ts_code)
            
            if analysis_result['success']:
                momentum = analysis_result['momentum']
                screening = analysis_result['screening_result']
                valuation = analysis_result.get('valuation', {})
                industry_meta = analysis_result.get('industry_meta', {})
                rs_analysis = analysis_result.get('rs_analysis', {})
                peg_analysis = analysis_result.get('peg_analysis', {})
                fundamentals_analysis = analysis_result.get('fundamentals_analysis', {})

                result_record = {
                    'ts_code': ts_code,
                    'name': etf_info.get('name', ''),
                    'category': etf_info.get('category', ''),
                    # 🆕 子行业分类
                    'sub_category': industry_meta.get('sub_category', ''),
                    'industry': industry_meta.get('industry', ''),
                    'supply_chain_position': industry_meta.get('supply_chain_position', ''),
                    'risk_multiplier': industry_meta.get('risk_multiplier', 1.0),
                    # 动量指标
                    '1m_return': momentum.get('1month_return', 0),
                    '3m_return': momentum.get('3month_return', 0),
                    '6m_return': momentum.get('6month_return', 0),
                    '12m_return': momentum.get('12month_return', 0),
                    'rsi': momentum.get('rsi', 50),
                    # 🆕 相对强弱
                    'rs_rating': rs_analysis.get('rs_rating', 50.0),
                    'rs_status': rs_analysis.get('status', '同步'),
                    'excess_return_1m': rs_analysis.get('excess_returns', {}).get('1M', 0),
                    'excess_return_3m': rs_analysis.get('excess_returns', {}).get('3M', 0),
                    # 🆕 PEG估值 (阶段2)
                    'peg': peg_analysis.get('peg', 0) if peg_analysis.get('available') else None,
                    'peg_level': peg_analysis.get('valuation_level', '数据不足'),
                    'growth_rate_pct': peg_analysis.get('growth_rate_pct', 0),
                    # 🆕 基本面 (阶段2)
                    'fundamentals_score': fundamentals_analysis.get('fundamentals_score', 0.5),
                    'health_rating': fundamentals_analysis.get('health_rating', '未知'),
                    # 评分
                    'momentum_score': screening['momentum']['score'],
                    'overall_score': screening['overall']['score'],
                    'grade': screening['overall']['grade'],
                    'passes_screening': screening['overall']['passes'],
                    # 估值信息
                    'valuation_percentile': valuation.get('percentile', 50),
                    'valuation_level': valuation.get('valuation_level', '合理'),
                    'valuation_zone': valuation.get('valuation_zone', '合理区'),
                    'mean_reversion_signal': valuation.get('mean_reversion_signal', '持有'),
                    # 风险指标
                    'drawdown_from_peak_pct': momentum.get('drawdown_from_peak_pct', 0),
                    'distance_to_peak_pct': momentum.get('distance_to_peak_pct', 1.0),
                    'momentum_status': momentum.get('momentum_status', '正常'),
                    'momentum_trend': momentum.get('momentum_trend', '稳定'),
                    'risk_warnings': '|'.join(screening['overall'].get('risk_warnings', [])),
                    'failed_reasons': screening['overall'].get('failed_reasons', [])  # 🆕 未通过原因
                }

                results.append(result_record)
            
            # API限制
            time.sleep(0.1)
        
        if not results:
            logger.warning("未获取到有效的ETF分析结果")
            return pd.DataFrame()
        
        # 转换为DataFrame并排序
        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values('overall_score', ascending=False)
        
        logger.info(f"完成ETF筛选，共分析 {len(results_df)} 只ETF")
        
        return results_df

    def screen_symbols(
        self,
        symbols: List[str],
        info_map: Optional[Dict[str, Dict[str, str]]] = None,
        max_etfs: Optional[int] = None,
        default_category: str = 'config_screen'
    ) -> pd.DataFrame:
        """按给定的代码列表进行ETF筛选。

        Args:
            symbols: 需要分析的ETF代码列表（如 '512480.SH'）。
            info_map: 可选的代码信息映射，用于提供名称/类别等显示信息，
                形如 { ts_code: { 'name': '...', 'category': '...' } }。
            max_etfs: 限制最大分析数量。
            default_category: 当未提供类别时使用的默认类别标签。

        Returns:
            筛选结果DataFrame。
        """
        logger.info("🚀 开始对自定义列表进行ETF动量筛选...")

        if not symbols:
            logger.error("未提供任何ETF代码")
            return pd.DataFrame()

        # 限制数量
        symbols_to_analyze = symbols[:max_etfs] if max_etfs else symbols

        # 构造与内部流程一致的基本信息DataFrame
        records: List[Dict[str, str]] = []
        for code in symbols_to_analyze:
            meta = (info_map or {}).get(code, {})
            records.append({
                'ts_code': code,
                'name': str(meta.get('name', '')),
                'category': str(meta.get('category', meta.get('sector', default_category)))
            })
        etf_list = pd.DataFrame.from_records(records)

        logger.info(f"准备分析 {len(etf_list)} 只ETF（自定义列表）")

        results: List[Dict] = []
        for idx, (_, etf_info) in enumerate(etf_list.iterrows()):
            ts_code = etf_info['ts_code']
            logger.info(f"分析进度: {idx + 1}/{len(etf_list)} - {ts_code}")

            analysis_result = self.analyze_etf(ts_code)
            if analysis_result.get('success'):
                momentum = analysis_result['momentum']
                screening = analysis_result['screening_result']
                valuation = analysis_result.get('valuation', {})
                industry_meta = analysis_result.get('industry_meta', {})
                rs_analysis = analysis_result.get('rs_analysis', {})
                peg_analysis = analysis_result.get('peg_analysis', {})
                fundamentals_analysis = analysis_result.get('fundamentals_analysis', {})

                results.append({
                    'ts_code': ts_code,
                    'name': etf_info.get('name', ''),
                    'category': etf_info.get('category', default_category),
                    # 🆕 子行业分类
                    'sub_category': industry_meta.get('sub_category', ''),
                    'industry': industry_meta.get('industry', ''),
                    'supply_chain_position': industry_meta.get('supply_chain_position', ''),
                    'risk_multiplier': industry_meta.get('risk_multiplier', 1.0),
                    # 动量指标
                    '1m_return': momentum.get('1month_return', 0),
                    '3m_return': momentum.get('3month_return', 0),
                    '6m_return': momentum.get('6month_return', 0),
                    '12m_return': momentum.get('12month_return', 0),
                    'rsi': momentum.get('rsi', 50),
                    # 🆕 相对强弱
                    'rs_rating': rs_analysis.get('rs_rating', 50.0),
                    'rs_status': rs_analysis.get('status', '同步'),
                    'excess_return_1m': rs_analysis.get('excess_returns', {}).get('1M', 0),
                    'excess_return_3m': rs_analysis.get('excess_returns', {}).get('3M', 0),
                    # 🆕 PEG估值 (阶段2)
                    'peg': peg_analysis.get('peg', 0) if peg_analysis.get('available') else None,
                    'peg_level': peg_analysis.get('valuation_level', '数据不足'),
                    'growth_rate_pct': peg_analysis.get('growth_rate_pct', 0),
                    # 🆕 基本面 (阶段2)
                    'fundamentals_score': fundamentals_analysis.get('fundamentals_score', 0.5),
                    'health_rating': fundamentals_analysis.get('health_rating', '未知'),
                    # 评分
                    'momentum_score': screening['momentum']['score'],
                    'overall_score': screening['overall']['score'],
                    'grade': screening['overall']['grade'],
                    'passes_screening': screening['overall']['passes'],
                    # 估值信息
                    'valuation_percentile': valuation.get('percentile', 50),
                    'valuation_level': valuation.get('valuation_level', '合理'),
                    'valuation_zone': valuation.get('valuation_zone', '合理区'),
                    'mean_reversion_signal': valuation.get('mean_reversion_signal', '持有'),
                    # 风险指标
                    'drawdown_from_peak_pct': momentum.get('drawdown_from_peak_pct', 0),
                    'distance_to_peak_pct': momentum.get('distance_to_peak_pct', 1.0),
                    'momentum_status': momentum.get('momentum_status', '正常'),
                    'momentum_trend': momentum.get('momentum_trend', '稳定'),
                    'risk_warnings': '|'.join(screening['overall'].get('risk_warnings', [])),
                    'failed_reasons': screening['overall'].get('failed_reasons', [])  # 🆕 未通过原因
                })

            # 轻量限速，避免频繁请求
            time.sleep(0.1)

        if not results:
            logger.warning("未获取到有效的ETF分析结果（自定义列表）")
            return pd.DataFrame()

        results_df = pd.DataFrame(results).sort_values('overall_score', ascending=False)
        logger.info(f"完成ETF筛选（自定义列表），共分析 {len(results_df)} 只ETF")
        return results_df
    
    def print_screening_results(self, results_df: pd.DataFrame):
        """
        打印筛选结果
        
        Args:
            results_df: 筛选结果DataFrame
        """
        if results_df.empty:
            logger.info("\n❌ 未找到符合条件的ETF")
            return
        
        # 筛选通过的ETF
        passed_etfs = results_df[results_df['passes_screening'] == True]
        
        logger.info("\n🎯 ETF动量筛选结果")
        print("=" * 120)
        logger.info("总共分析: {len(results_df)} 只ETF")
        logger.info("通过筛选: {len(passed_etfs)} 只ETF")
        
        if not passed_etfs.empty:
            logger.info("\n✅ 通过筛选的ETF (按综合得分排序):")
            print("-" * 180)
            print(f"{'排名':<4} {'代码':<12} {'名称':<20} {'类型':<12} {'综合得分':<8} {'等级':<6} "
                  f"{'1月%':<8} {'3月%':<8} {'6月%':<8} {'12月%':<8} {'RSI':<6} {'估值':<12} {'风险警告':<30}")
            print("-" * 180)
            
            for idx, (_, row) in enumerate(passed_etfs.iterrows(), 1):
                val_level = row.get('valuation_level', '合理')
                warnings = row.get('risk_warnings', '')
                print(f"{idx:<4} {row['ts_code']:<12} {row['name']:<20} {row['category']:<12} "
                      f"{row['overall_score']:<8.3f} {row['grade']:<6} "
                      f"{row['1m_return']:<8.1f} {row['3m_return']:<8.1f} "
                      f"{row['6m_return']:<8.1f} {row['12m_return']:<8.1f} "
                      f"{row['rsi']:<6.1f} {val_level:<12} {warnings:<30}")
        
        # 显示前10名ETF（包括未通过筛选的）
        logger.info("\n📊 综合得分前10名ETF:")
        print("-" * 120)
        top_10 = results_df.head(10)
        
        for idx, (_, row) in enumerate(top_10.iterrows(), 1):
            status = "✅" if row['passes_screening'] else "❌"
            print(f"{status} {idx:<3} {row['ts_code']:<12} {row['name']:<20} "
                  f"得分: {row['overall_score']:.3f} | "
                  f"1月: {row['1m_return']:.1f}% | "
                  f"3月: {row['3m_return']:.1f}% | "
                  f"6月: {row['6m_return']:.1f}%")
        
        # 🆕 未通过筛选的ETF（显示前10名）
        failed_etfs = results_df[results_df['passes_screening'] == False]
        if not failed_etfs.empty:
            logger.info("\n❌ 未通过筛选的ETF (按综合得分排序，显示前10名):")
            print("-" * 150)
            logger.info("{'排名':<4} {'代码':<12} {'名称':<20} {'类型':<12} {'综合得分':<8} {'等级':<6} {'未通过原因':<60}")
            print("-" * 150)

            # 按综合得分倒序，显示接近通过的ETF
            failed_sorted = failed_etfs.sort_values('overall_score', ascending=False).head(10)

            for idx, (_, row) in enumerate(failed_sorted.iterrows(), 1):
                failed_reasons = row.get('failed_reasons', [])
                if isinstance(failed_reasons, list):
                    reasons_str = ', '.join(failed_reasons[:2]) if failed_reasons else '综合得分不足'  # 最多显示2个原因
                else:
                    reasons_str = str(failed_reasons) if failed_reasons else '综合得分不足'

                # 限制原因字符串长度
                if len(reasons_str) > 58:
                    reasons_str = reasons_str[:55] + '...'

                print(f"{idx:<4} {row['ts_code']:<12} {row['name']:<20} {row['category']:<12} "
                      f"{row['overall_score']:<8.3f} {row['grade']:<6} {reasons_str:<60}")

        # 统计信息
        if not passed_etfs.empty:
            logger.info("\n📈 通过筛选ETF的统计信息:")
            logger.info("平均1月收益率: {passed_etfs['1m_return'].mean():.2f}%")
            logger.info("平均3月收益率: {passed_etfs['3m_return'].mean():.2f}%")
            logger.info("平均6月收益率: {passed_etfs['6m_return'].mean():.2f}%")
            logger.info("平均12月收益率: {passed_etfs['12m_return'].mean():.2f}%")


def main():
    """主函数 - 用于测试"""
    import logging
    
    # 设置日志
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    try:
        # 创建ETF筛选器
        screener = ETFMomentumScreener()
        
        logger.info("🎯 ETF动量筛选系统")
        print("=" * 50)
        
        # 执行筛选
        logger.info("🚀 开始筛选动量和趋势俱佳的ETF...")
        
        results = screener.screen_etfs(
            etf_types=['broad_market', 'sector'],  # 筛选宽基和行业ETF
            max_etfs=10  # 限制分析数量以节省时间
        )
        
        # 显示结果
        screener.print_screening_results(results)
        
        if not results.empty:
            # 保存结果
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = screener.report_dir / f"etf_screening_{timestamp}.csv"
            results.to_csv(output_file, index=False, encoding='utf-8-sig')
            logger.info("\n💾 结果已保存到: {output_file}")
        
    except Exception as e:
        logger.error(f"ETF筛选过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
