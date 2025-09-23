#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF资金流向分析器 (ETF Capital Flow Analyzer)

基于分钟级成交量数据分析ETF的资金流向特征
由于ETF没有传统的主力/大单资金流数据，本分析器通过成交量和价格关系来推断资金流向

主要功能:
1. 基于成交量-价格关系的资金流向分析
2. 成交量活跃度分析
3. 资金流入流出趋势判断
4. 与日线数据的成交量对比分析
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


class ETFCapitalFlowAnalyzer:
    """ETF资金流向分析器"""

    def __init__(self, data_provider_name: str = 'tushare', use_cache: bool = True):
        """
        初始化ETF资金流向分析器

        Args:
            data_provider_name: 数据提供商名称
            use_cache: 是否使用缓存
        """
        self.data_provider = DataProviderFactory.create(data_provider_name, enableCache=use_cache)
        self.use_cache = use_cache

        # 缓存数据避免重复请求
        self._minute_cache = {}
        self._daily_cache = {}

    def analyze_etf_capital_flow(self, symbol: str, days: int = 5) -> Dict[str, Any]:
        """
        分析ETF资金流向（基于分钟级成交量数据）

        Args:
            symbol: ETF代码
            days: 分析天数

        Returns:
            Dict包含成交量活跃度、资金流向趋势、价量关系等指标
        """
        try:
            # 获取分钟级数据
            minute_data = self._get_minute_data(symbol, days)
            if minute_data.empty:
                return self._get_empty_result("无分钟级数据")

            # 获取日线数据作为对比
            daily_data = self._get_daily_data(symbol, days)

            # 1. 成交量活跃度分析
            volume_activity = self._analyze_volume_activity(minute_data, daily_data)

            # 2. 价量关系分析
            price_volume_relation = self._analyze_price_volume_relation(minute_data)

            # 3. 资金流向趋势分析
            flow_trend = self._analyze_flow_trend(minute_data)

            # 4. 成交额分析
            amount_analysis = self._analyze_trading_amount(minute_data)

            # 5. 综合评分计算
            comprehensive_score = self._calculate_etf_flow_score(
                volume_activity, price_volume_relation, flow_trend, amount_analysis
            )

            return {
                'symbol': symbol,
                'analysis_period': f'{days}天',
                'data_quality': {
                    'minute_records': len(minute_data),
                    'daily_records': len(daily_data),
                    'latest_date': minute_data.index[-1].strftime('%Y-%m-%d %H:%M') if len(minute_data) > 0 else None
                },
                'volume_activity': volume_activity,
                'price_volume_relation': price_volume_relation,
                'flow_trend': flow_trend,
                'amount_analysis': amount_analysis,
                'comprehensive_score': comprehensive_score,
                'flow_signals': self._identify_flow_signals(minute_data),
                'investment_suggestion': self._generate_etf_suggestion(comprehensive_score, flow_trend)
            }

        except Exception as e:
            print(f"ETF资金流分析失败 {symbol}: {str(e)}")
            return self._get_empty_result(f"分析失败: {str(e)}")

    def _get_minute_data(self, symbol: str, days: int) -> pd.DataFrame:
        """获取分钟级数据"""
        cache_key = f"{symbol}_{days}d_5min"

        if cache_key in self._minute_cache:
            return self._minute_cache[cache_key]

        try:
            # 计算时间范围 - 确保获取工作日
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days * 3)  # 多获取一些数据确保有足够的交易日

            print(f"正在获取{symbol}的分钟级数据，时间范围：{start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")

            # 使用stk_mins接口获取5分钟数据
            import tushare as ts
            import os
            
            # 尝试多种方式获取token
            ts_token = None
            if hasattr(self.data_provider, 'config') and self.data_provider.config:
                ts_token = self.data_provider.config.get('token')
            
            if not ts_token:
                ts_token = os.getenv('TUSHARE_TOKEN')
            
            if not ts_token:
                print("缺少Tushare token配置，请设置TUSHARE_TOKEN环境变量")
                return pd.DataFrame()
                
            ts.set_token(ts_token)
            pro = ts.pro_api()

            # 分批获取数据（按天获取避免接口限制）
            all_data = []
            current_date = start_date
            
            while current_date <= end_date:
                if current_date.weekday() < 5:  # 只获取工作日
                    try:
                        df_day = pro.stk_mins(
                            ts_code=symbol,
                            freq='5min',
                            start_date=current_date.strftime('%Y-%m-%d 09:30:00'),
                            end_date=current_date.strftime('%Y-%m-%d 15:00:00')
                        )
                        
                        if not df_day.empty:
                            all_data.append(df_day)
                            print(f"  获取{current_date.strftime('%Y-%m-%d')}数据：{len(df_day)}条记录")
                        
                        # 避免频率限制
                        import time
                        time.sleep(0.2)
                        
                    except Exception as day_e:
                        print(f"  获取{current_date.strftime('%Y-%m-%d')}数据失败: {str(day_e)}")
                
                current_date += timedelta(days=1)
            
            if all_data:
                df = pd.concat(all_data, ignore_index=True)
                
                # 处理数据
                df['trade_time'] = pd.to_datetime(df['trade_time'])
                df = df.set_index('trade_time').sort_index()
                
                # 去除重复数据
                df = df[~df.index.duplicated(keep='first')]
                
                # 计算价格变化
                df['price_change'] = df['close'] - df['open']
                df['price_change_pct'] = df['price_change'] / df['open']
                
                # 只保留最近days天的数据
                if len(df) > 0:
                    recent_date = df.index[-1].date()
                    start_filter = recent_date - timedelta(days=days)
                    df = df[df.index.date > start_filter]
                    
                    print(f"成功获取{symbol}分钟数据：{len(df)}条记录，时间范围：{df.index[0]} 到 {df.index[-1]}")
                    
                    self._minute_cache[cache_key] = df
                    return df
                else:
                    print(f"获取到的{symbol}数据为空")
            else:
                print(f"未能获取到{symbol}的任何分钟数据")

        except Exception as e:
            print(f"获取{symbol}分钟级数据失败: {str(e)}")
            import traceback
            traceback.print_exc()

        return pd.DataFrame()

    def _get_daily_data(self, symbol: str, days: int) -> pd.DataFrame:
        """获取日线数据作为对比"""
        cache_key = f"{symbol}_{days}d_daily"

        if cache_key in self._daily_cache:
            return self._daily_cache[cache_key]

        try:
            end = datetime.now()
            start = end - timedelta(days=days*2)
            start_str = start.strftime('%Y%m%d')
            end_str = end.strftime('%Y%m%d')

            # 获取ETF日线数据
            df = self.data_provider.getFundData(symbol, start_str, end_str, 'D')
            if not df.empty:
                df = df.tail(days)  # 只要最近days天
                self._daily_cache[cache_key] = df
                return df

        except Exception as e:
            print(f"获取{symbol}日线数据失败: {str(e)}")

        return pd.DataFrame()

    def _analyze_volume_activity(self, minute_data: pd.DataFrame, daily_data: pd.DataFrame) -> Dict[str, Any]:
        """分析成交量活跃度"""
        if minute_data.empty:
            return {'activity_level': 'unknown', 'relative_activity': 0}

        # 计算活跃度指标
        avg_vol = minute_data['vol'].mean()
        vol_std = minute_data['vol'].std()
        vol_cv = vol_std / avg_vol if avg_vol > 0 else 0

        # 高成交量时段占比
        high_vol_threshold = minute_data['vol'].quantile(0.8)
        high_vol_periods = len(minute_data[minute_data['vol'] >= high_vol_threshold])
        high_vol_ratio = high_vol_periods / len(minute_data)

        # 与日均成交量对比
        relative_activity = 1.0
        if not daily_data.empty and 'volume' in daily_data.columns:
            daily_avg_vol = daily_data['volume'].mean()
            minute_total_vol = minute_data['vol'].sum()
            # 假设一天有48个5分钟周期（4小时交易）
            estimated_daily_vol = minute_total_vol / len(minute_data) * 48
            if daily_avg_vol > 0:
                relative_activity = estimated_daily_vol / daily_avg_vol

        # 活跃度等级判断
        if high_vol_ratio > 0.3 and vol_cv > 2.0:
            activity_level = 'very_high'
        elif high_vol_ratio > 0.25 and vol_cv > 1.5:
            activity_level = 'high'
        elif high_vol_ratio > 0.2 and vol_cv > 1.0:
            activity_level = 'medium'
        elif high_vol_ratio > 0.15:
            activity_level = 'low'
        else:
            activity_level = 'very_low'

        return {
            'activity_level': activity_level,
            'avg_volume': float(avg_vol),
            'volume_volatility': float(vol_cv),
            'high_vol_ratio': float(high_vol_ratio),
            'relative_activity': float(relative_activity)
        }

    def _analyze_price_volume_relation(self, minute_data: pd.DataFrame) -> Dict[str, Any]:
        """分析价量关系"""
        if minute_data.empty:
            return {'correlation': 0, 'pattern': 'unknown'}

        # 分别计算上涨和下跌时的平均成交量
        price_up = minute_data[minute_data['price_change'] > 0]
        price_down = minute_data[minute_data['price_change'] < 0]
        price_flat = minute_data[minute_data['price_change'] == 0]

        avg_vol_up = price_up['vol'].mean() if len(price_up) > 0 else 0
        avg_vol_down = price_down['vol'].mean() if len(price_down) > 0 else 0
        avg_vol_flat = price_flat['vol'].mean() if len(price_flat) > 0 else 0

        # 计算价量相关性
        correlation = minute_data['price_change'].corr(minute_data['vol'])

        # 判断资金流向模式
        up_down_ratio = avg_vol_up / avg_vol_down if avg_vol_down > 0 else 1.0

        if up_down_ratio > 1.2:
            pattern = 'bullish'  # 上涨时放量
            pattern_desc = '上涨放量'
        elif up_down_ratio < 0.8:
            pattern = 'bearish'  # 下跌时放量
            pattern_desc = '下跌放量'
        else:
            pattern = 'neutral'  # 无明显差异
            pattern_desc = '价量平衡'

        return {
            'correlation': float(correlation) if not pd.isna(correlation) else 0,
            'pattern': pattern,
            'pattern_desc': pattern_desc,
            'avg_vol_up': float(avg_vol_up),
            'avg_vol_down': float(avg_vol_down),
            'up_down_ratio': float(up_down_ratio),
            'up_periods': len(price_up),
            'down_periods': len(price_down)
        }

    def _analyze_flow_trend(self, minute_data: pd.DataFrame) -> Dict[str, Any]:
        """分析资金流向趋势"""
        if minute_data.empty or len(minute_data) < 20:
            return {'trend': 'unknown', 'strength': 0}

        # 计算移动平均成交量
        minute_data['vol_ma5'] = minute_data['vol'].rolling(window=5).mean()
        minute_data['vol_ma20'] = minute_data['vol'].rolling(window=20).mean()

        # 最近vs历史成交量对比
        recent_vol = minute_data['vol'].tail(10).mean()  # 最近10个周期
        historical_vol = minute_data['vol'].head(len(minute_data)-10).mean()  # 历史平均

        trend_strength = (recent_vol - historical_vol) / historical_vol if historical_vol > 0 else 0

        # 趋势判断
        if trend_strength > 0.2:
            trend = 'increasing'
            trend_desc = '成交量递增'
        elif trend_strength < -0.2:
            trend = 'decreasing'
            trend_desc = '成交量递减'
        else:
            trend = 'stable'
            trend_desc = '成交量平稳'

        # 计算成交量趋势的持续性
        vol_diff = minute_data['vol_ma5'] - minute_data['vol_ma20']
        consistency = len(vol_diff[vol_diff > 0]) / len(vol_diff.dropna()) if len(vol_diff.dropna()) > 0 else 0

        return {
            'trend': trend,
            'trend_desc': trend_desc,
            'strength': float(trend_strength),
            'consistency': float(consistency),
            'recent_vol': float(recent_vol),
            'historical_vol': float(historical_vol)
        }

    def _analyze_trading_amount(self, minute_data: pd.DataFrame) -> Dict[str, Any]:
        """分析成交额"""
        if minute_data.empty:
            return {'avg_amount': 0, 'amount_intensity': 'low'}

        total_amount = minute_data['amount'].sum()
        avg_amount = minute_data['amount'].mean()
        amount_std = minute_data['amount'].std()

        # 大额交易时段识别（成交额前20%）
        high_amount_threshold = minute_data['amount'].quantile(0.8)
        large_trades = minute_data[minute_data['amount'] >= high_amount_threshold]
        large_trade_ratio = len(large_trades) / len(minute_data)

        # 成交额强度判断
        if large_trade_ratio > 0.25:
            intensity = 'high'
        elif large_trade_ratio > 0.2:
            intensity = 'medium'
        else:
            intensity = 'low'

        return {
            'total_amount': float(total_amount),
            'avg_amount': float(avg_amount),
            'amount_volatility': float(amount_std / avg_amount if avg_amount > 0 else 0),
            'large_trade_ratio': float(large_trade_ratio),
            'amount_intensity': intensity
        }

    def _calculate_etf_flow_score(self, volume_activity, price_volume_relation, flow_trend, amount_analysis) -> float:
        """计算ETF资金流综合评分"""
        score = 0

        # 成交量活跃度评分 (30%)
        activity_scores = {
            'very_high': 30, 'high': 25, 'medium': 20, 'low': 15, 'very_low': 10
        }
        score += activity_scores.get(volume_activity['activity_level'], 15)

        # 价量关系评分 (30%)
        if price_volume_relation['pattern'] == 'bullish':
            score += 30
        elif price_volume_relation['pattern'] == 'neutral':
            score += 20
        else:  # bearish
            score += 10

        # 资金流趋势评分 (25%)
        if flow_trend['trend'] == 'increasing':
            score += 25
        elif flow_trend['trend'] == 'stable':
            score += 15
        else:  # decreasing
            score += 5

        # 成交额强度评分 (15%)
        amount_scores = {'high': 15, 'medium': 10, 'low': 5}
        score += amount_scores.get(amount_analysis['amount_intensity'], 5)

        return min(100, max(0, score))

    def _identify_flow_signals(self, minute_data: pd.DataFrame) -> List[str]:
        """识别资金流向信号"""
        signals = []

        if minute_data.empty:
            return signals

        # 成交量异常放大信号
        recent_vol = minute_data['vol'].tail(5).mean()
        historical_vol = minute_data['vol'].mean()
        if recent_vol > historical_vol * 1.5:
            signals.append("成交量异常放大")

        # 价量背离信号
        price_up_periods = minute_data[minute_data['price_change'] > 0]
        if len(price_up_periods) > 0:
            if price_up_periods['vol'].mean() < minute_data['vol'].mean() * 0.8:
                signals.append("上涨缩量（可能为技术性反弹）")

        # 大额成交信号
        high_amount = minute_data['amount'].quantile(0.9)
        recent_high_amount = minute_data.tail(10)
        if (recent_high_amount['amount'] >= high_amount).sum() >= 3:
            signals.append("连续大额成交")

        return signals

    def _generate_etf_suggestion(self, score: float, flow_trend: Dict) -> str:
        """生成ETF投资建议"""
        if score >= 75:
            suggestion = "资金流入强劲，适合积极配置"
        elif score >= 60:
            suggestion = "资金流入较好，可适度增持"
        elif score >= 45:
            suggestion = "资金流向中性，建议持有观望"
        elif score >= 30:
            suggestion = "资金流向偏弱，建议控制仓位"
        else:
            suggestion = "资金流向疲弱，建议谨慎操作"

        # 结合趋势调整建议
        if flow_trend['trend'] == 'decreasing' and score < 50:
            suggestion += "，注意规避风险"
        elif flow_trend['trend'] == 'increasing' and score > 60:
            suggestion += "，可考虑加仓"

        return suggestion

    def _get_empty_result(self, reason: str) -> Dict[str, Any]:
        """返回空的分析结果"""
        return {
            'volume_activity': {'activity_level': 'unknown', 'relative_activity': 0},
            'price_volume_relation': {'correlation': 0, 'pattern': 'unknown'},
            'flow_trend': {'trend': 'unknown', 'strength': 0},
            'amount_analysis': {'amount_intensity': 'unknown'},
            'comprehensive_score': 0,
            'flow_signals': [],
            'investment_suggestion': '数据不足，无法分析',
            'error': reason
        }


def test_etf_capital_flow_analyzer():
    """测试ETF资金流向分析器"""
    print("🔄 测试ETF资金流向分析器...")

    analyzer = ETFCapitalFlowAnalyzer()

    # 测试科创50ETF
    test_symbol = "588000.SH"
    print(f"\n📊 测试ETF资金流向分析: {test_symbol}")

    flow_result = analyzer.analyze_etf_capital_flow(test_symbol, days=3)
    
    if 'error' not in flow_result:
        print("ETF资金流向分析结果:")
        print(f"  成交量活跃度: {flow_result['volume_activity']['activity_level']}")
        print(f"  价量关系: {flow_result['price_volume_relation']['pattern_desc']}")
        print(f"  资金流趋势: {flow_result['flow_trend']['trend_desc']}")
        print(f"  成交额强度: {flow_result['amount_analysis']['amount_intensity']}")
        print(f"  综合评分: {flow_result['comprehensive_score']:.0f}/100")
        print(f"  投资建议: {flow_result['investment_suggestion']}")
        
        if flow_result['flow_signals']:
            print(f"  市场信号: {'; '.join(flow_result['flow_signals'])}")
    else:
        print(f"分析失败: {flow_result['error']}")

    print("\n✅ ETF资金流向分析器测试完成")


if __name__ == '__main__':
    test_etf_capital_flow_analyzer()