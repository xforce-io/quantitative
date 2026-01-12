#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ETF估值分析器 (ETF Valuation Analyzer)

提供ETF估值水平分析，包括：
1. 价格历史分位数分析（判断高估/低估）
2. 溢价率/折价率分析
3. 均值回归信号
4. 估值区间判断
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

from quant.core.indicators import TechnicalIndicators
from quant.core.logging_config import get_logger

logger = get_logger(__name__)


class ETFValuationAnalyzer:
    """ETF估值分析器"""

    def score(self, symbol: str, data: pd.DataFrame = None) -> float:
        """
        计算估值评分 (0-100)

        Args:
            symbol: 股票/ETF代码
            data: 价格数据 (如果为None则需要外部提供)

        Returns:
            0-100 的标准化分数，低估=高分，高估=低分
        """
        if data is None or data.empty:
            return 50.0  # 无数据时返回中性分数

        report = self.generate_comprehensive_valuation_report(data, symbol=symbol)

        if 'error' in report:
            return 50.0

        # 获取估值得分 (-3 到 +3)
        valuation_score = report.get('comprehensive_assessment', {}).get('valuation_score', 0)

        # 转换到 0-100: -3 -> 100 (极度低估=高分), +3 -> 0 (极度高估=低分)
        # 公式: score = (3 - valuation_score) / 6 * 100
        normalized_score = (3 - valuation_score) / 6 * 100
        return max(0, min(100, normalized_score))

    def __init__(self):
        """初始化估值分析器"""
        self.indicators = TechnicalIndicators()
    
    def calculate_price_percentile(self, data: pd.DataFrame, 
                                   lookback_periods: List[int] = [252, 504, 756]) -> Dict:
        """
        计算价格历史分位数
        
        Args:
            data: 价格数据，包含close列
            lookback_periods: 回看周期列表（交易日）[1年, 2年, 3年]
            
        Returns:
            价格分位数分析结果
        """
        # 数据验证
        if not self._validate_price_data(data):
            logger.warning("价格数据验证失败")
            return {'error': '数据为空或缺少必要列'}
        
        current_price = float(data['close'].iloc[-1])
        results = {
            'current_price': current_price,
            'analysis_date': data.index[-1].strftime('%Y-%m-%d') if hasattr(data.index[-1], 'strftime') else str(data.index[-1]),
            'percentiles': {}
        }
        
        # 计算不同周期的分位数
        for period in lookback_periods:
            if len(data) >= period:
                period_data = data.tail(period)
                period_name = f"{period//252}年" if period >= 252 else f"{period}天"
                
                # 计算当前价格的分位数
                percentile = (period_data['close'] <= current_price).sum() / len(period_data) * 100
                
                # 计算统计量
                period_mean = period_data['close'].mean()
                period_std = period_data['close'].std()
                period_median = period_data['close'].median()
                period_min = period_data['close'].min()
                period_max = period_data['close'].max()
                
                # 计算Z-score（标准化距离）
                z_score = (current_price - period_mean) / period_std if period_std > 0 else 0
                
                # 估值判断
                valuation_level = self._judge_valuation_by_percentile(percentile)
                
                results['percentiles'][period_name] = {
                    'percentile': percentile,
                    'z_score': z_score,
                    'mean': period_mean,
                    'median': period_median,
                    'std': period_std,
                    'min': period_min,
                    'max': period_max,
                    'distance_from_mean_pct': (current_price - period_mean) / period_mean * 100,
                    'distance_from_median_pct': (current_price - period_median) / period_median * 100,
                    'valuation_level': valuation_level
                }
        
        # 综合估值判断
        if results['percentiles']:
            avg_percentile = np.mean([v['percentile'] for v in results['percentiles'].values()])
            results['overall_percentile'] = avg_percentile
            results['overall_valuation'] = self._judge_valuation_by_percentile(avg_percentile)
        
        return results
    
    def _judge_valuation_by_percentile(self, percentile: float) -> str:
        """根据分位数判断估值水平"""
        if percentile >= 90:
            return "极度高估"
        elif percentile >= 75:
            return "高估"
        elif percentile >= 60:
            return "偏高"
        elif percentile >= 40:
            return "合理"
        elif percentile >= 25:
            return "偏低"
        elif percentile >= 10:
            return "低估"
        else:
            return "极度低估"
    
    def calculate_premium_discount(self, etf_price: float, nav: float = None, 
                                   index_price: float = None) -> Dict:
        """
        计算ETF溢价率/折价率
        
        Args:
            etf_price: ETF市场价格
            nav: ETF净值（如果可获取）
            index_price: 标的指数价格（归一化后）
            
        Returns:
            溢价/折价分析结果
        """
        results = {
            'etf_price': etf_price,
            'premium_discount_pct': None,
            'status': None
        }
        
        # 相对于净值的溢价率
        if nav is not None and nav > 0:
            premium_pct = (etf_price - nav) / nav * 100
            results['nav'] = nav
            results['premium_discount_pct'] = premium_pct
            
            if premium_pct > 2:
                results['status'] = "显著溢价"
            elif premium_pct > 0.5:
                results['status'] = "小幅溢价"
            elif premium_pct > -0.5:
                results['status'] = "平价交易"
            elif premium_pct > -2:
                results['status'] = "小幅折价"
            else:
                results['status'] = "显著折价"
        
        # 相对于指数的偏离度
        if index_price is not None and index_price > 0:
            deviation_pct = (etf_price - index_price) / index_price * 100
            results['index_price'] = index_price
            results['index_deviation_pct'] = deviation_pct
        
        return results
    
    def calculate_mean_reversion_signals(self, data: pd.DataFrame, 
                                         ma_period: int = 20,
                                         std_multiplier: float = 2.0) -> Dict:
        """
        计算均值回归信号
        
        Args:
            data: 价格数据
            ma_period: 均线周期
            std_multiplier: 标准差倍数
            
        Returns:
            均值回归信号
        """
        # 数据验证
        if not self._validate_price_data(data, min_rows=ma_period):
            logger.warning(f"数据不足以计算均值回归信号: {len(data)} < {ma_period}")
            return {'error': f'数据不足{ma_period}天'}
        
        # 计算移动平均和标准差
        data = data.copy()
        data[f'MA{ma_period}'] = data['close'].rolling(window=ma_period).mean()
        data['STD'] = data['close'].rolling(window=ma_period).std()
        
        # 计算布林带
        data['Upper_Band'] = data[f'MA{ma_period}'] + (std_multiplier * data['STD'])
        data['Lower_Band'] = data[f'MA{ma_period}'] - (std_multiplier * data['STD'])
        
        # 当前值
        latest = data.iloc[-1]
        current_price = float(latest['close'])
        ma_value = float(latest[f'MA{ma_period}'])
        upper_band = float(latest['Upper_Band'])
        lower_band = float(latest['Lower_Band'])
        
        # 计算偏离度
        deviation_from_ma = (current_price - ma_value) / ma_value * 100
        
        # 布林带位置（0-100%）
        if upper_band != lower_band:
            bb_position = (current_price - lower_band) / (upper_band - lower_band) * 100
        else:
            bb_position = 50.0
        
        # 均值回归信号
        if current_price > upper_band:
            signal = "卖出信号"
            signal_strength = "强"
            reason = f"价格突破上轨{std_multiplier}倍标准差，可能回归"
        elif current_price < lower_band:
            signal = "买入信号"
            signal_strength = "强"
            reason = f"价格跌破下轨{std_multiplier}倍标准差，可能反弹"
        elif bb_position > 75:
            signal = "观望/减仓"
            signal_strength = "中"
            reason = "价格偏高，接近上轨"
        elif bb_position < 25:
            signal = "观望/加仓"
            signal_strength = "中"
            reason = "价格偏低，接近下轨"
        else:
            signal = "持有"
            signal_strength = "弱"
            reason = "价格在合理区间"
        
        return {
            'current_price': current_price,
            'ma_value': ma_value,
            'upper_band': upper_band,
            'lower_band': lower_band,
            'deviation_from_ma_pct': deviation_from_ma,
            'bollinger_position': bb_position,
            'signal': signal,
            'signal_strength': signal_strength,
            'reason': reason,
            'ma_period': ma_period,
            'std_multiplier': std_multiplier
        }
    
    def _validate_price_data(self, data: pd.DataFrame, min_rows: int = 1) -> bool:
        """
        验证价格数据质量
        
        Args:
            data: 价格数据
            min_rows: 最小行数
        
        Returns:
            是否通过验证
        """
        if data is None or data.empty:
            return False
        
        if 'close' not in data.columns:
            return False
        
        if len(data) < min_rows:
            return False
        
        # 检查close列是否有有效值
        if data['close'].isna().all():
            return False
        
        # 检查是否全为0
        if (data['close'] == 0).all():
            return False
        
        return True
    
    def calculate_valuation_zone(self, data: pd.DataFrame,
                                 periods: List[int] = [20, 60, 120, 252]) -> Dict:
        """
        计算估值区间（基于多周期均线）
        
        Args:
            data: 价格数据
            periods: 均线周期列表
            
        Returns:
            估值区间分析
        """
        if data.empty or 'close' not in data.columns:
            return {'error': '数据为空或缺少必要列'}
        
        current_price = float(data['close'].iloc[-1])
        
        # 计算各周期均线
        ma_values = {}
        for period in periods:
            if len(data) >= period:
                ma = data['close'].rolling(window=period).mean().iloc[-1]
                ma_values[f'MA{period}'] = float(ma)
        
        if not ma_values:
            return {'error': '数据不足以计算均线'}
        
        # 判断多头/空头排列
        sorted_mas = sorted(ma_values.items(), key=lambda x: int(x[0][2:]))
        ma_trend = "多头排列" if all(
            sorted_mas[i][1] > sorted_mas[i+1][1] 
            for i in range(len(sorted_mas)-1)
        ) else "空头排列" if all(
            sorted_mas[i][1] < sorted_mas[i+1][1] 
            for i in range(len(sorted_mas)-1)
        ) else "混乱"
        
        # 价格相对于各均线的位置
        price_vs_ma = {}
        above_count = 0
        for ma_name, ma_value in ma_values.items():
            deviation = (current_price - ma_value) / ma_value * 100
            price_vs_ma[ma_name] = {
                'value': ma_value,
                'deviation_pct': deviation,
                'above': current_price > ma_value
            }
            if current_price > ma_value:
                above_count += 1
        
        # 估值区间判断
        above_ratio = above_count / len(ma_values)
        if above_ratio >= 0.75:
            zone = "高估区"
        elif above_ratio >= 0.5:
            zone = "合理偏高区"
        elif above_ratio >= 0.25:
            zone = "合理偏低区"
        else:
            zone = "低估区"
        
        return {
            'current_price': current_price,
            'ma_values': ma_values,
            'price_vs_ma': price_vs_ma,
            'ma_trend': ma_trend,
            'above_ma_count': above_count,
            'total_ma_count': len(ma_values),
            'above_ratio': above_ratio,
            'valuation_zone': zone
        }
    
    def generate_comprehensive_valuation_report(self, data: pd.DataFrame, 
                                                nav: float = None,
                                                symbol: str = "") -> Dict:
        """
        生成综合估值报告
        
        Args:
            data: 价格数据
            nav: ETF净值（可选）
            symbol: 标的代码
            
        Returns:
            综合估值分析报告
        """
        if data.empty:
            return {'error': '数据为空'}
        
        current_price = float(data['close'].iloc[-1])
        
        # 1. 价格分位数分析
        percentile_analysis = self.calculate_price_percentile(data)
        
        # 2. 溢价率分析
        premium_analysis = self.calculate_premium_discount(current_price, nav)
        
        # 3. 均值回归信号
        mean_reversion = self.calculate_mean_reversion_signals(data)
        
        # 4. 估值区间
        valuation_zone = self.calculate_valuation_zone(data)
        
        # 综合评估
        comprehensive_assessment = self._generate_comprehensive_assessment(
            percentile_analysis, premium_analysis, mean_reversion, valuation_zone
        )
        
        return {
            'symbol': symbol,
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'current_price': current_price,
            'percentile_analysis': percentile_analysis,
            'premium_analysis': premium_analysis,
            'mean_reversion_signals': mean_reversion,
            'valuation_zone': valuation_zone,
            'comprehensive_assessment': comprehensive_assessment
        }
    
    def _generate_comprehensive_assessment(self, percentile_analysis: Dict,
                                          premium_analysis: Dict,
                                          mean_reversion: Dict,
                                          valuation_zone: Dict) -> Dict:
        """生成综合评估"""
        signals = []
        score = 0  # -3到+3的评分，负数=低估，正数=高估
        
        # 分位数评估
        if 'overall_valuation' in percentile_analysis:
            valuation = percentile_analysis['overall_valuation']
            if '极度高估' in valuation:
                score += 3
                signals.append("📈 价格分位数显示极度高估")
            elif '高估' in valuation:
                score += 2
                signals.append("📈 价格分位数显示高估")
            elif '偏高' in valuation:
                score += 1
                signals.append("📊 价格分位数偏高")
            elif '偏低' in valuation:
                score -= 1
                signals.append("📊 价格分位数偏低")
            elif '低估' in valuation:
                score -= 2
                signals.append("📉 价格分位数显示低估")
            elif '极度低估' in valuation:
                score -= 3
                signals.append("📉 价格分位数显示极度低估")
        
        # 溢价率评估
        if premium_analysis.get('status'):
            status = premium_analysis['status']
            if '显著溢价' in status:
                score += 1
                signals.append(f"💰 {status}，谨慎买入")
            elif '显著折价' in status:
                score -= 1
                signals.append(f"💰 {status}，可能存在机会")
        
        # 均值回归信号
        if 'signal' in mean_reversion and 'error' not in mean_reversion:
            mr_signal = mean_reversion['signal']
            if '卖出' in mr_signal:
                score += 1
                signals.append(f"🔄 均值回归提示: {mr_signal}")
            elif '买入' in mr_signal:
                score -= 1
                signals.append(f"🔄 均值回归提示: {mr_signal}")
        
        # 估值区间
        if 'valuation_zone' in valuation_zone and 'error' not in valuation_zone:
            zone = valuation_zone['valuation_zone']
            if '高估区' in zone:
                score += 1
                signals.append(f"📍 当前处于{zone}")
            elif '低估区' in zone:
                score -= 1
                signals.append(f"📍 当前处于{zone}")
        
        # 综合建议
        if score >= 3:
            recommendation = "强烈建议观望或减仓"
            risk_level = "高"
        elif score >= 1:
            recommendation = "建议谨慎，可考虑减仓"
            risk_level = "中高"
        elif score <= -3:
            recommendation = "可积极关注，考虑建仓"
            risk_level = "低"
        elif score <= -1:
            recommendation = "可适当关注，逢低布局"
            risk_level = "中低"
        else:
            recommendation = "估值相对合理，保持观察"
            risk_level = "中"
        
        return {
            'valuation_score': score,
            'signals': signals,
            'recommendation': recommendation,
            'risk_level': risk_level
        }
    
    def format_valuation_report(self, report: Dict) -> str:
        """
        格式化估值报告为可读文本
        
        Args:
            report: 综合估值报告
            
        Returns:
            格式化的文本报告
        """
        if 'error' in report:
            return f"❌ 错误: {report['error']}"
        
        lines = [
            f"📊 ETF估值分析报告 - {report.get('symbol', '未知')}",
            "=" * 70,
            f"📅 分析时间: {report.get('analysis_date', 'N/A')}",
            f"💰 当前价格: {report.get('current_price', 0):.3f}",
            ""
        ]
        
        # 价格分位数分析
        if 'percentile_analysis' in report and 'percentiles' in report['percentile_analysis']:
            lines.append("📈 历史价格分位数分析:")
            for period, data in report['percentile_analysis']['percentiles'].items():
                lines.append(
                    f"  {period}: {data['percentile']:.1f}% 分位 | "
                    f"距均值: {data['distance_from_mean_pct']:+.2f}% | "
                    f"估值: {data['valuation_level']}"
                )
            if 'overall_valuation' in report['percentile_analysis']:
                lines.append(f"  ⭐ 综合估值: {report['percentile_analysis']['overall_valuation']}")
            lines.append("")
        
        # 溢价率分析
        if 'premium_analysis' in report and report['premium_analysis'].get('status'):
            lines.append("💎 溢价/折价分析:")
            pa = report['premium_analysis']
            if pa.get('premium_discount_pct') is not None:
                lines.append(f"  溢价率: {pa['premium_discount_pct']:+.2f}%")
                lines.append(f"  状态: {pa['status']}")
            lines.append("")
        
        # 均值回归信号
        if 'mean_reversion_signals' in report and 'error' not in report['mean_reversion_signals']:
            lines.append("🔄 均值回归信号:")
            mrs = report['mean_reversion_signals']
            lines.append(f"  信号: {mrs['signal']} (强度: {mrs['signal_strength']})")
            lines.append(f"  原因: {mrs['reason']}")
            lines.append(f"  偏离均线: {mrs['deviation_from_ma_pct']:+.2f}%")
            lines.append(f"  布林带位置: {mrs['bollinger_position']:.1f}%")
            lines.append("")
        
        # 估值区间
        if 'valuation_zone' in report and 'error' not in report['valuation_zone']:
            lines.append("📍 估值区间分析:")
            vz = report['valuation_zone']
            lines.append(f"  均线排列: {vz['ma_trend']}")
            lines.append(f"  价格高于均线比例: {vz['above_ratio']:.1%}")
            lines.append(f"  估值区间: {vz['valuation_zone']}")
            lines.append("")
        
        # 综合评估
        if 'comprehensive_assessment' in report:
            lines.append("🎯 综合评估:")
            ca = report['comprehensive_assessment']
            lines.append(f"  估值得分: {ca['valuation_score']:+d} (-3低估 ~ +3高估)")
            lines.append(f"  风险水平: {ca['risk_level']}")
            lines.append(f"  投资建议: {ca['recommendation']}")
            lines.append("")
            lines.append("  主要信号:")
            for signal in ca['signals']:
                lines.append(f"    • {signal}")
        
        lines.extend([
            "",
            "=" * 70,
            "⚠️ 风险提示: 以上分析仅供参考，不构成投资建议"
        ])
        
        return "\n".join(lines)


# Backward compatibility alias
PriceValuationAnalyzer = ETFValuationAnalyzer
