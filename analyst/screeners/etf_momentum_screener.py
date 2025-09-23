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

Created by: Quantitative Trading System
Date: 2024
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import logging
from typing import Dict, List, Optional, Tuple
import os
import json

# 调整sys.path以便从项目根目录导入quant包
import sys
from pathlib import Path
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# 使用统一数据提供器工厂和技术指标模块
from quant.data_providers.data_provider_factory import DataProviderFactory
from quant.core.indicators import TechnicalIndicators

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
            raise ValueError("请设置TUSHARE_TOKEN环境变量或提供token参数")
        
        # 筛选条件配置
        self.screening_config = {
            'momentum': {
                '1month_return_min': 3.0,      # 1个月最小收益率 %
                '3month_return_min': 8.0,      # 3个月最小收益率 %
                '6month_return_min': 15.0,     # 6个月最小收益率 %
                '12month_return_min': 20.0,    # 12个月最小收益率 %
                'rsi_min': 40.0,               # RSI最小值
                'rsi_max': 80.0,               # RSI最大值
                'macd_signal': 'positive'      # MACD信号要求
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
        
        # ETF分类配置
        self.etf_categories = {
            'broad_market': ['510300.SH', '159919.SZ', '510500.SH'],  # 大盘指数
            'sector': ['159995.SZ', '512480.SH', '512660.SH'],        # 行业ETF
            'thematic': ['515050.SH', '516950.SH', '588000.SH'],      # 主题ETF
            'bonds': ['511010.SH', '511880.SH'],                      # 债券ETF
            'commodities': ['159930.SZ', '518880.SH'],                # 商品ETF
            'international': ['513100.SH', '513050.SH']               # 海外ETF
        }
        
        # 使用数据提供者工厂创建带缓存的数据提供者
        try:
            config = {'token': token}
            self.data_provider = DataProviderFactory.create('tushare', config, enableCache=True)
            logger.info("✅ 成功初始化缓存数据提供者 (Tushare)")
        except Exception as e:
            logger.error(f"初始化数据提供者失败: {e}")
            raise
        
        # 缓存目录
        self.cache_dir = os.path.join(PROJECT_ROOT, "cache", "etf_screener")
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def get_etf_list(self, include_types: List[str] = None) -> pd.DataFrame:
        """
        获取ETF列表
        
        Args:
            include_types: 包含的ETF类型列表，如['broad_market', 'sector']
            
        Returns:
            ETF基本信息DataFrame
        """
        logger.info("获取ETF列表...")
        
        try:
            # 使用数据提供者获取基金列表
            etf_data = self.data_provider.getFundBasic(
                market='E',  # ETF
                status='L'   # 存续
            )
            
            if etf_data.empty:
                logger.warning("未获取到ETF数据")
                return pd.DataFrame()
            
            # 过滤掉场外基金，只保留场内ETF
            etf_data = etf_data[
                (etf_data['ts_code'].str.endswith('.SH')) | 
                (etf_data['ts_code'].str.endswith('.SZ'))
            ].copy()
            
            # 如果指定了类型，进行过滤
            if include_types:
                selected_codes = []
                for category in include_types:
                    if category in self.etf_categories:
                        selected_codes.extend(self.etf_categories[category])
                
                if selected_codes:
                    etf_data = etf_data[etf_data['ts_code'].isin(selected_codes)].copy()
            
            logger.info(f"获取到 {len(etf_data)} 只ETF")
            return etf_data
            
        except Exception as e:
            logger.error(f"获取ETF列表失败: {e}")
            # 如果API失败，使用预定义的主要ETF列表
            return self.get_fallback_etf_list(include_types)
    
    def get_fallback_etf_list(self, include_types: List[str] = None) -> pd.DataFrame:
        """获取备用ETF列表"""
        logger.info("使用预定义ETF列表...")
        
        fallback_etfs = {
            # 宽基指数ETF
            '510300.SH': {'name': '沪深300ETF', 'category': 'broad_market', 'benchmark': '沪深300'},
            '159919.SZ': {'name': '沪深300ETF', 'category': 'broad_market', 'benchmark': '沪深300'},
            '510500.SH': {'name': '中证500ETF', 'category': 'broad_market', 'benchmark': '中证500'},
            '159915.SZ': {'name': '创业板ETF', 'category': 'broad_market', 'benchmark': '创业板指'},
            
            # 行业ETF
            '512480.SH': {'name': '半导体ETF', 'category': 'sector', 'benchmark': '中华半导体芯片指数'},
            '512660.SH': {'name': '军工ETF', 'category': 'sector', 'benchmark': '中证军工指数'},
            '512200.SH': {'name': '房地产ETF', 'category': 'sector', 'benchmark': '中证房地产指数'},
            '515220.SH': {'name': '煤炭ETF', 'category': 'sector', 'benchmark': '中证煤炭指数'},
            
            # 主题ETF
            '515050.SH': {'name': '5G ETF', 'category': 'thematic', 'benchmark': '中证5G通信主题指数'},
            '516950.SH': {'name': '新能源ETF', 'category': 'thematic', 'benchmark': '中证新能源指数'},
            '588000.SH': {'name': '科创50ETF', 'category': 'thematic', 'benchmark': '科创50指数'},
            
            # 海外ETF
            '513100.SH': {'name': '纳指ETF', 'category': 'international', 'benchmark': '纳斯达克100'},
            '513050.SH': {'name': '中概互联ETF', 'category': 'international', 'benchmark': '中概互联指数'},
        }
        
        # 构建DataFrame
        etf_list = []
        for ts_code, info in fallback_etfs.items():
            if not include_types or info['category'] in include_types:
                etf_list.append({
                    'ts_code': ts_code,
                    'name': info['name'],
                    'category': info['category'],
                    'benchmark': info['benchmark']
                })
        
        return pd.DataFrame(etf_list)
    
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
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=months_back * 30)).strftime('%Y%m%d')
            
            # 获取价格数据 - 使用正确的方法签名
            price_data = self.data_provider.getFundData(
                symbol=ts_code, 
                startDate=start_date, 
                endDate=end_date, 
                freq='D'
            )
            
            if price_data is None or price_data.empty:
                logger.warning(f"未获取到 {ts_code} 的价格数据")
                return pd.DataFrame()
            
            # 确保数据按日期升序排列
            price_data = price_data.sort_index()
            
            # 确保包含必要的列
            required_cols = ['open', 'high', 'low', 'close']
            missing_cols = [col for col in required_cols if col not in price_data.columns]
            if missing_cols:
                logger.warning(f"{ts_code} 缺少必要列: {missing_cols}")
                return pd.DataFrame()
            
            # 添加成交量列（如果没有的话）
            if 'volume' not in price_data.columns:
                if 'vol' in price_data.columns:
                    price_data['volume'] = price_data['vol']
                else:
                    price_data['volume'] = 1000000  # 默认成交量
            
            return price_data
            
        except Exception as e:
            logger.error(f"获取 {ts_code} 价格数据失败: {e}")
            return pd.DataFrame()
    
    def calculate_momentum_indicators(self, price_data: pd.DataFrame) -> Dict:
        """
        计算动量指标
        
        Args:
            price_data: 价格数据
            
        Returns:
            动量指标字典
        """
        if price_data.empty or len(price_data) < 252:  # 至少需要1年数据
            return {}
        
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
            
            # 计算RSI
            rsi = TechnicalIndicators.calculate_rsi(price_data)
            current_rsi = rsi.iloc[-1] if not rsi.empty else 50.0
            
            # 计算MACD
            macd_dict = TechnicalIndicators.calculate_macd(price_data)
            current_macd = macd_dict['MACD'].iloc[-1] if not macd_dict['MACD'].empty else 0.0
            current_macd_signal = macd_dict['MACD_Signal'].iloc[-1] if not macd_dict['MACD_Signal'].empty else 0.0
            macd_histogram = macd_dict['MACD_Histogram'].iloc[-1] if not macd_dict['MACD_Histogram'].empty else 0.0
            
            # 计算动量强度（基于价格变化率和成交量）
            price_change_20d = (current_price - price_data['close'].iloc[-21]) / price_data['close'].iloc[-21] * 100 if len(price_data) > 21 else 0
            momentum_strength = min(abs(price_change_20d) / 10.0, 1.0)  # 归一化到0-1
            
            momentum_indicators = {
                **returns,
                'rsi': current_rsi,
                'macd': current_macd,
                'macd_signal': current_macd_signal,
                'macd_histogram': macd_histogram,
                'momentum_strength': momentum_strength,
                'price_change_20d': price_change_20d
            }
            
            return momentum_indicators
            
        except Exception as e:
            logger.error(f"计算动量指标失败: {e}")
            return {}
    
    def calculate_trend_indicators(self, price_data: pd.DataFrame) -> Dict:
        """
        计算趋势指标
        
        Args:
            price_data: 价格数据
            
        Returns:
            趋势指标字典
        """
        if price_data.empty or len(price_data) < 60:
            return {}
        
        try:
            # 添加移动平均线
            price_data_with_ma = TechnicalIndicators.calculate_moving_averages(price_data)
            
            current_price = price_data_with_ma['close'].iloc[-1]
            
            # 移动平均线
            ma5 = price_data_with_ma['MA5'].iloc[-1] if 'MA5' in price_data_with_ma.columns else current_price
            ma20 = price_data_with_ma['MA20'].iloc[-1] if 'MA20' in price_data_with_ma.columns else current_price
            ma60 = price_data_with_ma['MA60'].iloc[-1] if 'MA60' in price_data_with_ma.columns else current_price
            
            # 趋势判断
            ma5_above_ma20 = ma5 > ma20
            ma20_above_ma60 = ma20 > ma60
            price_above_ma20 = current_price > ma20
            
            # 计算趋势强度（基于均线排列）
            trend_alignment_score = 0
            if ma5 > ma20:
                trend_alignment_score += 0.33
            if ma20 > ma60:
                trend_alignment_score += 0.33
            if current_price > ma20:
                trend_alignment_score += 0.34
            
            # 计算唐奇安通道
            donchian_dict = TechnicalIndicators.calculate_donchian_channels(price_data, 20)
            if not donchian_dict['Donchian_High'].empty:
                donchian_high = donchian_dict['Donchian_High'].iloc[-1]
                donchian_low = donchian_dict['Donchian_Low'].iloc[-1]
                donchian_position = (current_price - donchian_low) / (donchian_high - donchian_low) if donchian_high > donchian_low else 0.5
            else:
                donchian_position = 0.5
            
            # 计算价格趋势（线性回归斜率）
            if len(price_data) >= 20:
                recent_prices = price_data['close'].tail(20).values
                x = np.arange(len(recent_prices))
                slope, _ = np.polyfit(x, recent_prices, 1)
                trend_slope = slope / recent_prices[-1] * 100  # 转换为百分比
            else:
                trend_slope = 0
            
            trend_indicators = {
                'ma5': ma5,
                'ma20': ma20,
                'ma60': ma60,
                'ma5_above_ma20': ma5_above_ma20,
                'ma20_above_ma60': ma20_above_ma60,
                'price_above_ma20': price_above_ma20,
                'trend_strength': trend_alignment_score,
                'donchian_position': donchian_position,
                'trend_slope': trend_slope
            }
            
            return trend_indicators
            
        except Exception as e:
            logger.error(f"计算趋势指标失败: {e}")
            return {}
    
    def calculate_volume_indicators(self, price_data: pd.DataFrame) -> Dict:
        """
        计算成交量指标
        
        Args:
            price_data: 价格数据
            
        Returns:
            成交量指标字典
        """
        if price_data.empty or 'volume' not in price_data.columns or len(price_data) < 20:
            return {'volume_ratio': 1.0, 'avg_volume': 0, 'volume_trend': 'unknown'}
        
        try:
            # 计算成交量指标
            volume_indicators_dict = TechnicalIndicators.calculate_volume_indicators(price_data, 'volume')
            
            current_volume = price_data['volume'].iloc[-1]
            avg_volume_20d = volume_indicators_dict['Volume_MA'].iloc[-1] if not volume_indicators_dict['Volume_MA'].empty else current_volume
            volume_ratio = volume_indicators_dict['Volume_Ratio'].iloc[-1] if not volume_indicators_dict['Volume_Ratio'].empty else 1.0
            
            # 判断成交量趋势
            if len(price_data) >= 10:
                recent_volume = price_data['volume'].tail(5).mean()
                earlier_volume = price_data['volume'].tail(10).head(5).mean()
                volume_trend = 'increasing' if recent_volume > earlier_volume else 'decreasing'
            else:
                volume_trend = 'stable'
            
            return {
                'current_volume': current_volume,
                'avg_volume': avg_volume_20d,
                'volume_ratio': volume_ratio,
                'volume_trend': volume_trend
            }
            
        except Exception as e:
            logger.error(f"计算成交量指标失败: {e}")
            return {'volume_ratio': 1.0, 'avg_volume': 0, 'volume_trend': 'unknown'}
    
    def calculate_quality_indicators(self, price_data: pd.DataFrame) -> Dict:
        """
        计算质量指标（风险和收益质量）
        
        Args:
            price_data: 价格数据
            
        Returns:
            质量指标字典
        """
        if price_data.empty or len(price_data) < 60:
            return {}
        
        try:
            # 计算收益率序列
            returns_dict = TechnicalIndicators.calculate_returns(price_data)
            daily_returns = returns_dict['daily_return'].dropna()
            
            # 计算回撤
            drawdown_dict = TechnicalIndicators.calculate_drawdown(price_data)
            max_drawdown = abs(drawdown_dict['drawdown'].min()) if not drawdown_dict['drawdown'].empty else 0
            
            # 计算波动率（年化）
            if len(daily_returns) > 20:
                volatility = daily_returns.std() * np.sqrt(252)
            else:
                volatility = 0
            
            # 计算夏普比率（假设无风险利率为3%）
            risk_free_rate = 0.03
            if len(daily_returns) > 20 and volatility > 0:
                mean_return = daily_returns.mean() * 252
                sharpe_ratio = (mean_return - risk_free_rate) / volatility
            else:
                sharpe_ratio = 0
            
            # 计算收益质量指标
            positive_days = (daily_returns > 0).sum()
            total_days = len(daily_returns)
            win_rate = positive_days / total_days if total_days > 0 else 0
            
            # 计算价格稳定性（变异系数）
            if len(price_data) > 20:
                price_cv = price_data['close'].std() / price_data['close'].mean()
            else:
                price_cv = 0
            
            return {
                'max_drawdown': max_drawdown,
                'volatility': volatility,
                'sharpe_ratio': sharpe_ratio,
                'win_rate': win_rate,
                'price_cv': price_cv,
                'tracking_error': 0.02  # ETF通常跟踪误差较小，设置默认值
            }
            
        except Exception as e:
            logger.error(f"计算质量指标失败: {e}")
            return {}
    
    def analyze_etf(self, ts_code: str) -> Dict:
        """
        分析单只ETF
        
        Args:
            ts_code: ETF代码
            
        Returns:
            分析结果字典
        """
        logger.info(f"分析ETF: {ts_code}")
        
        try:
            # 获取价格数据
            price_data = self.get_etf_price_data(ts_code)
            if price_data.empty:
                return {'success': False, 'error': f'未获取到{ts_code}的价格数据'}
            
            # 计算各种指标
            momentum_indicators = self.calculate_momentum_indicators(price_data)
            trend_indicators = self.calculate_trend_indicators(price_data)
            volume_indicators = self.calculate_volume_indicators(price_data)
            quality_indicators = self.calculate_quality_indicators(price_data)
            
            # 评估筛选条件
            screening_result = self.evaluate_screening_criteria(
                momentum_indicators, trend_indicators, volume_indicators, quality_indicators
            )
            
            return {
                'success': True,
                'ts_code': ts_code,
                'data_points': len(price_data),
                'analysis_date': datetime.now().isoformat(),
                'momentum': momentum_indicators,
                'trend': trend_indicators,
                'volume': volume_indicators,
                'quality': quality_indicators,
                'screening_result': screening_result
            }
            
        except Exception as e:
            logger.error(f"分析ETF {ts_code} 失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def evaluate_screening_criteria(self, momentum: Dict, trend: Dict, volume: Dict, quality: Dict) -> Dict:
        """
        评估筛选条件
        
        Args:
            momentum: 动量指标
            trend: 趋势指标
            volume: 成交量指标
            quality: 质量指标
            
        Returns:
            筛选结果字典
        """
        config = self.screening_config
        results = {}
        
        # 动量条件评估
        momentum_score = 0
        momentum_checks = []
        
        for period in ['1month', '3month', '6month', '12month']:
            return_key = f'{period}_return'
            min_return_key = f'{period}_return_min'
            
            if return_key in momentum and min_return_key in config['momentum']:
                actual_return = momentum[return_key]
                required_return = config['momentum'][min_return_key]
                passes = actual_return >= required_return
                
                momentum_checks.append({
                    'criterion': f'{period}_return',
                    'actual': actual_return,
                    'required': required_return,
                    'passes': passes
                })
                
                if passes:
                    momentum_score += 0.25
        
        # RSI检查
        if 'rsi' in momentum:
            rsi_passes = (config['momentum']['rsi_min'] <= momentum['rsi'] <= config['momentum']['rsi_max'])
            momentum_checks.append({
                'criterion': 'rsi',
                'actual': momentum['rsi'],
                'required': f"{config['momentum']['rsi_min']}-{config['momentum']['rsi_max']}",
                'passes': rsi_passes
            })
            if rsi_passes:
                momentum_score += 0.1
        
        # MACD检查
        if 'macd_histogram' in momentum:
            macd_passes = momentum['macd_histogram'] > 0
            momentum_checks.append({
                'criterion': 'macd_signal',
                'actual': 'positive' if macd_passes else 'negative',
                'required': 'positive',
                'passes': macd_passes
            })
            if macd_passes:
                momentum_score += 0.1
        
        results['momentum'] = {
            'score': momentum_score,
            'max_score': 1.0,
            'passes': momentum_score >= 0.6,  # 至少60%条件通过
            'details': momentum_checks
        }
        
        # 趋势条件评估
        trend_score = 0
        trend_checks = []
        
        if trend:
            # 均线排列检查
            ma_checks = [
                ('ma5_above_ma20', trend.get('ma5_above_ma20', False)),
                ('ma20_above_ma60', trend.get('ma20_above_ma60', False)),
                ('price_above_ma20', trend.get('price_above_ma20', False))
            ]
            
            for criterion, passes in ma_checks:
                trend_checks.append({
                    'criterion': criterion,
                    'actual': passes,
                    'required': True,
                    'passes': passes
                })
                if passes:
                    trend_score += 0.25
            
            # 趋势强度检查
            trend_strength_passes = trend.get('trend_strength', 0) >= config['trend']['trend_strength_min']
            trend_checks.append({
                'criterion': 'trend_strength',
                'actual': trend.get('trend_strength', 0),
                'required': config['trend']['trend_strength_min'],
                'passes': trend_strength_passes
            })
            if trend_strength_passes:
                trend_score += 0.15
            
            # 唐奇安位置检查
            donchian_passes = trend.get('donchian_position', 0) >= config['trend']['donchian_position_min']
            trend_checks.append({
                'criterion': 'donchian_position',
                'actual': trend.get('donchian_position', 0),
                'required': config['trend']['donchian_position_min'],
                'passes': donchian_passes
            })
            if donchian_passes:
                trend_score += 0.10
        
        results['trend'] = {
            'score': trend_score,
            'max_score': 1.0,
            'passes': trend_score >= 0.5,  # 至少50%条件通过
            'details': trend_checks
        }
        
        # 成交量条件评估
        volume_score = 0
        volume_checks = []
        
        if volume:
            # 成交量比率检查
            volume_ratio_passes = volume.get('volume_ratio', 0) >= config['volume']['volume_ratio_min']
            volume_checks.append({
                'criterion': 'volume_ratio',
                'actual': volume.get('volume_ratio', 0),
                'required': config['volume']['volume_ratio_min'],
                'passes': volume_ratio_passes
            })
            if volume_ratio_passes:
                volume_score += 0.4
            
            # 平均成交量检查
            avg_volume_passes = volume.get('avg_volume', 0) >= config['volume']['avg_volume_min']
            volume_checks.append({
                'criterion': 'avg_volume',
                'actual': volume.get('avg_volume', 0),
                'required': config['volume']['avg_volume_min'],
                'passes': avg_volume_passes
            })
            if avg_volume_passes:
                volume_score += 0.4
            
            # 成交量趋势检查
            volume_trend_passes = volume.get('volume_trend') == config['volume']['volume_trend']
            volume_checks.append({
                'criterion': 'volume_trend',
                'actual': volume.get('volume_trend', 'unknown'),
                'required': config['volume']['volume_trend'],
                'passes': volume_trend_passes
            })
            if volume_trend_passes:
                volume_score += 0.2
        
        results['volume'] = {
            'score': volume_score,
            'max_score': 1.0,
            'passes': volume_score >= 0.4,  # 至少40%条件通过
            'details': volume_checks
        }
        
        # 质量条件评估
        quality_score = 0
        quality_checks = []
        
        if quality:
            # 最大回撤检查
            drawdown_passes = quality.get('max_drawdown', 1) <= config['quality']['max_drawdown_max']
            quality_checks.append({
                'criterion': 'max_drawdown',
                'actual': quality.get('max_drawdown', 1),
                'required': f"<= {config['quality']['max_drawdown_max']}",
                'passes': drawdown_passes
            })
            if drawdown_passes:
                quality_score += 0.3
            
            # 波动率检查
            volatility_passes = quality.get('volatility', 1) <= config['quality']['volatility_max']
            quality_checks.append({
                'criterion': 'volatility',
                'actual': quality.get('volatility', 1),
                'required': f"<= {config['quality']['volatility_max']}",
                'passes': volatility_passes
            })
            if volatility_passes:
                quality_score += 0.3
            
            # 夏普比率检查
            sharpe_passes = quality.get('sharpe_ratio', 0) >= config['quality']['sharpe_ratio_min']
            quality_checks.append({
                'criterion': 'sharpe_ratio',
                'actual': quality.get('sharpe_ratio', 0),
                'required': f">= {config['quality']['sharpe_ratio_min']}",
                'passes': sharpe_passes
            })
            if sharpe_passes:
                quality_score += 0.4
        
        results['quality'] = {
            'score': quality_score,
            'max_score': 1.0,
            'passes': quality_score >= 0.4,  # 至少40%条件通过
            'details': quality_checks
        }
        
        # 综合评估
        overall_score = (
            results['momentum']['score'] * 0.35 +  # 动量权重35%
            results['trend']['score'] * 0.35 +     # 趋势权重35%
            results['volume']['score'] * 0.15 +    # 成交量权重15%
            results['quality']['score'] * 0.15     # 质量权重15%
        )
        
        # 综合判断：需要动量和趋势都通过，且综合得分>=0.6
        overall_passes = (
            results['momentum']['passes'] and 
            results['trend']['passes'] and 
            overall_score >= 0.6
        )
        
        results['overall'] = {
            'score': overall_score,
            'passes': overall_passes,
            'grade': self.get_grade(overall_score)
        }
        
        return results
    
    def get_grade(self, score: float) -> str:
        """根据得分获取评级"""
        if score >= 0.9:
            return 'A+'
        elif score >= 0.8:
            return 'A'
        elif score >= 0.7:
            return 'B+'
        elif score >= 0.6:
            return 'B'
        elif score >= 0.5:
            return 'C'
        else:
            return 'D'
    
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
                # 提取关键信息
                momentum = analysis_result['momentum']
                trend = analysis_result['trend']
                volume = analysis_result['volume']
                quality = analysis_result['quality']
                screening = analysis_result['screening_result']
                
                result_record = {
                    'ts_code': ts_code,
                    'name': etf_info.get('name', ''),
                    'category': etf_info.get('category', ''),
                    
                    # 动量指标
                    '1m_return': momentum.get('1month_return', 0),
                    '3m_return': momentum.get('3month_return', 0),
                    '6m_return': momentum.get('6month_return', 0),
                    '12m_return': momentum.get('12month_return', 0),
                    'rsi': momentum.get('rsi', 50),
                    'momentum_score': screening['momentum']['score'],
                    
                    # 趋势指标
                    'trend_strength': trend.get('trend_strength', 0),
                    'donchian_position': trend.get('donchian_position', 0),
                    'trend_slope': trend.get('trend_slope', 0),
                    'trend_score': screening['trend']['score'],
                    
                    # 成交量指标
                    'volume_ratio': volume.get('volume_ratio', 0),
                    'avg_volume': volume.get('avg_volume', 0),
                    'volume_score': screening['volume']['score'],
                    
                    # 质量指标
                    'max_drawdown': quality.get('max_drawdown', 0),
                    'volatility': quality.get('volatility', 0),
                    'sharpe_ratio': quality.get('sharpe_ratio', 0),
                    'quality_score': screening['quality']['score'],
                    
                    # 综合评估
                    'overall_score': screening['overall']['score'],
                    'grade': screening['overall']['grade'],
                    'passes_screening': screening['overall']['passes']
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
    
    def print_screening_results(self, results_df: pd.DataFrame):
        """
        打印筛选结果
        
        Args:
            results_df: 筛选结果DataFrame
        """
        if results_df.empty:
            print("\n❌ 未找到符合条件的ETF")
            return
        
        # 筛选通过的ETF
        passed_etfs = results_df[results_df['passes_screening'] == True]
        
        print(f"\n🎯 ETF动量筛选结果")
        print("=" * 120)
        print(f"总共分析: {len(results_df)} 只ETF")
        print(f"通过筛选: {len(passed_etfs)} 只ETF")
        
        if not passed_etfs.empty:
            print(f"\n✅ 通过筛选的ETF (按综合得分排序):")
            print("-" * 120)
            print(f"{'排名':<4} {'代码':<12} {'名称':<20} {'类型':<12} {'综合得分':<8} {'等级':<6} "
                  f"{'1月%':<8} {'3月%':<8} {'6月%':<8} {'12月%':<8} {'RSI':<6} {'夏普':<6}")
            print("-" * 120)
            
            for idx, (_, row) in enumerate(passed_etfs.iterrows(), 1):
                print(f"{idx:<4} {row['ts_code']:<12} {row['name']:<20} {row['category']:<12} "
                      f"{row['overall_score']:<8.3f} {row['grade']:<6} "
                      f"{row['1m_return']:<8.1f} {row['3m_return']:<8.1f} "
                      f"{row['6m_return']:<8.1f} {row['12m_return']:<8.1f} "
                      f"{row['rsi']:<6.1f} {row['sharpe_ratio']:<6.2f}")
        
        # 显示前10名ETF（包括未通过筛选的）
        print(f"\n📊 综合得分前10名ETF:")
        print("-" * 120)
        top_10 = results_df.head(10)
        
        for idx, (_, row) in enumerate(top_10.iterrows(), 1):
            status = "✅" if row['passes_screening'] else "❌"
            print(f"{status} {idx:<3} {row['ts_code']:<12} {row['name']:<20} "
                  f"得分: {row['overall_score']:.3f} | "
                  f"动量: {row['momentum_score']:.2f} | "
                  f"趋势: {row['trend_score']:.2f} | "
                  f"成交量: {row['volume_score']:.2f} | "
                  f"质量: {row['quality_score']:.2f}")
        
        # 统计信息
        if not passed_etfs.empty:
            print(f"\n📈 通过筛选ETF的统计信息:")
            print(f"平均1月收益率: {passed_etfs['1m_return'].mean():.2f}%")
            print(f"平均3月收益率: {passed_etfs['3m_return'].mean():.2f}%")
            print(f"平均6月收益率: {passed_etfs['6m_return'].mean():.2f}%")
            print(f"平均12月收益率: {passed_etfs['12m_return'].mean():.2f}%")
            print(f"平均夏普比率: {passed_etfs['sharpe_ratio'].mean():.3f}")
            print(f"平均最大回撤: {passed_etfs['max_drawdown'].mean():.2%}")
            
            # 类型分布
            category_dist = passed_etfs['category'].value_counts()
            print(f"\n📋 类型分布:")
            for category, count in category_dist.items():
                print(f"  {category}: {count}只")
    
    def save_results(self, results_df: pd.DataFrame, filename: str = None):
        """
        保存筛选结果
        
        Args:
            results_df: 筛选结果DataFrame
            filename: 文件名，如果为None则自动生成
        """
        if results_df.empty:
            return
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"etf_momentum_screening_{timestamp}.csv"
        
        filepath = os.path.join(self.cache_dir, filename)
        results_df.to_csv(filepath, index=False, encoding='utf-8-sig')
        logger.info(f"筛选结果已保存到: {filepath}")


def main():
    """主函数"""
    try:
        # 创建ETF筛选器
        screener = ETFMomentumScreener()
        
        print("🎯 ETF动量筛选系统")
        print("=" * 50)
        
        # 执行筛选
        print("🚀 开始筛选动量和趋势俱佳的ETF...")
        
        # 可以指定ETF类型，例如：
        # etf_types = ['broad_market', 'sector']  # 只筛选宽基和行业ETF
        # 或者设置为None来筛选所有类型
        
        results = screener.screen_etfs(
            etf_types=['broad_market', 'sector', 'thematic'],  # 筛选主要类型
            max_etfs=20  # 限制分析数量以节省时间
        )
        
        # 显示结果
        screener.print_screening_results(results)
        
        # 保存结果
        if not results.empty:
            screener.save_results(results)
            
            # 显示使用建议
            passed_count = (results['passes_screening'] == True).sum()
            if passed_count > 0:
                print(f"\n💡 投资建议:")
                print(f"   - 优先关注综合得分前3名的ETF")
                print(f"   - 建议分散投资，不要集中在单一类型")
                print(f"   - 定期复查动量指标，及时调整持仓")
                print(f"   - 关注成交量变化，确保流动性充足")
        
    except Exception as e:
        logger.error(f"ETF筛选过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()