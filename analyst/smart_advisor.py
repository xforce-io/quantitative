#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能投资顾问（Smart Investment Advisor）- 推荐使用

核心理念：从"单一指标驱动"升级为"多维度平衡决策"

与其他工具的区别：
• 相比 investment_advisor.py：避免过度依赖RSI等单一指标，加入历史位置分析
• 相比 prob_analysis.py：不仅提供概率统计，还给出综合投资建议
• 相比 enhanced_advisor.py：功能更全面，集成概率统计和风险评估

核心功能：
1. 历史位置分析 - 距离历史高点/低点的位置评估，避免盲目追高杀跌
2. 多维度风险评估 - RSI(20%) + 位置(30%) + 波动率(15%) + 趋势(20%) + 成交量(15%)
3. 概率统计分析 - 基于历史相似状态的未来走势概率统计
4. 综合投资建议 - 整合所有分析结果的平衡决策

适用场景：日常投资决策的主要工具

使用方法：
  python analyst/smart_advisor.py --symbol 000300.SH
  python analyst/smart_advisor.py --symbol IXIC --days-back 3000
"""

import sys
import pandas as pd
import numpy as np
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple, Optional, List
import argparse

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from quant.data_providers.data_provider_factory import DataProviderFactory
from analyst.capital_flow_analyzer import CapitalFlowAnalyzer


# 历史极值配置（可根据实际情况更新）
HISTORICAL_EXTREMES = {
    '000300.SH': {'high': 5380.0, 'low': 1600.0, 'name': '沪深300'},
    '000001.SH': {'high': 6124.0, 'low': 998.0, 'name': '上证指数'},
    '399001.SZ': {'high': 19600.0, 'low': 2500.0, 'name': '深证成指'},
    '588000.SH': {'high': 1.6, 'low': 0.69, 'name': '科创50ETF'},
    'IXIC': {'high': 16212.0, 'low': 1100.0, 'name': '纳斯达克'},
}


class IntegratedAdvisor:
    def __init__(self, symbol: str, days_back: int = 2500, enable_fundamental: bool = True, enable_capital_flow: bool = True):
        self.symbol = symbol
        self.days_back = days_back
        self.enable_fundamental = enable_fundamental
        self.enable_capital_flow = enable_capital_flow
        self.data = None
        self.indicators = {}
        self.position_analysis = {}
        self.risk_score = 0
        self.risk_level = ""
        self.risk_details = {}
        self.probability_analysis = {}
        self.recommendation = ""
        self.action_details = {'action': '无法分析', 'percentage': 'N/A', 'reason': ['数据不足']}
        self.comprehensive_analysis = {}
        self.fundamental_analysis = {}
        self.capital_flow_analysis = {}

        # 初始化资金流分析器
        if self.enable_capital_flow and self._is_a_share_stock():
            try:
                self.capital_flow_analyzer = CapitalFlowAnalyzer()
            except Exception as e:
                print(f"⚠️ 资金流分析器初始化失败: {e}")
                self.enable_capital_flow = False
                self.capital_flow_analyzer = None
        else:
            self.capital_flow_analyzer = None

    def _is_a_share_stock(self) -> bool:
        """检查是否为A股股票（支持资金流分析）"""
        return self.symbol.endswith('.SZ') or self.symbol.endswith('.SH')

    def is_global_index(self, symbol: str) -> bool:
        """检查是否为全球指数"""
        symbol = symbol.upper()
        return (symbol.startswith('^') or 
                symbol in {'IXIC','NDX','NASDAQ','SPX','DJI','HSI','HKTECH','HSCEI'})
    
    def _is_etf_or_index(self, symbol: str) -> bool:
        """检测是否为ETF或指数（更宽容的评分标准）"""
        symbol = symbol.upper()
        
        # 全球指数
        if self.is_global_index(symbol):
            return True
            
        # A股指数（000、399开头）
        if symbol.startswith('000') or symbol.startswith('399'):
            return True
            
        # ETF基金（5、15开头或包含ETF）
        if (symbol.startswith('5') or symbol.startswith('15') or 
            'ETF' in symbol or 'LOF' in symbol):
            return True
            
        return False
        
    def fetch_data(self):
        """获取历史数据"""
        provider = DataProviderFactory.create('tushare', enableCache=True)
        end = datetime.now()
        start = end - timedelta(days=self.days_back)
        start_str = start.strftime('%Y%m%d')
        end_str = end.strftime('%Y%m%d')
        
        # 智能选择数据接口
        symbol_upper = self.symbol.upper()
        df = None
        
        try:
            if self.is_global_index(symbol_upper):
                df = provider.getGlobalIndexData(self.symbol, start_str, end_str, 'D')
            elif self.symbol.endswith('.SH') or self.symbol.endswith('.SZ'):
                if self.symbol.startswith('000') or self.symbol.startswith('399'):
                    df = provider.getIndexData(self.symbol, start_str, end_str, 'D')
                elif self.symbol.startswith('5') or self.symbol.startswith('15'):
                    df = provider.getFundData(self.symbol, start_str, end_str, 'D')
                else:
                    df = provider.getStockData(self.symbol, start_str, end_str, 'D')
        except Exception as e:
            print(f"获取数据失败: {e}")
            return None
            
        self.data = df
        return df
    
    def calculate_indicators(self):
        """计算技术指标"""
        if self.data is None or len(self.data) < 200:
            return
            
        df = self.data
        
        # 均线
        df['MA20'] = df['close'].rolling(20).mean()
        df['MA50'] = df['close'].rolling(50).mean()
        df['MA200'] = df['close'].rolling(200).mean()
        df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # MACD
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_Histogram'] = df['MACD'] - df['MACD_Signal']
        
        # 唐奇安通道
        df['Donchian_High'] = df['high'].rolling(20).max()
        df['Donchian_Low'] = df['low'].rolling(20).min()
        
        # 布林带
        df['BB_Middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)
        
        # 成交量指标
        df['Volume_MA'] = df['volume'].rolling(20).mean()
        df['Volume_Ratio'] = df['volume'] / df['Volume_MA']
        
        # ATR（真实波幅）
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['ATR'] = true_range.rolling(14).mean()
        df['ATR_Ratio'] = df['ATR'] / df['close']
        
        self.data = df
        
    def analyze_historical_position(self):
        """分析历史位置"""
        if self.data is None or len(self.data) == 0:
            return
            
        current_price = float(self.data['close'].iloc[-1])
        
        # 获取数据期间的最高最低
        data_high = float(self.data['high'].max())
        data_low = float(self.data['low'].min())
        
        # 获取历史极值（如果有配置）
        hist_high = data_high
        hist_low = data_low
        
        if self.symbol in HISTORICAL_EXTREMES:
            config = HISTORICAL_EXTREMES[self.symbol]
            hist_high = max(config['high'], data_high)
            hist_low = min(config['low'], data_low)
        
        # 计算位置百分比
        position_pct = (current_price - hist_low) / (hist_high - hist_low) * 100
        distance_to_high = (hist_high - current_price) / current_price * 100
        distance_to_low = (current_price - hist_low) / current_price * 100
        
        # 计算近期位置（52周）
        recent_52w = self.data.tail(252) if len(self.data) > 252 else self.data
        high_52w = float(recent_52w['high'].max())
        low_52w = float(recent_52w['low'].min())
        position_52w = (current_price - low_52w) / (high_52w - low_52w) * 100
        
        self.position_analysis = {
            'current_price': current_price,
            'historical_high': hist_high,
            'historical_low': hist_low,
            'position_pct': position_pct,
            'distance_to_high_pct': distance_to_high,
            'distance_to_low_pct': distance_to_low,
            'high_52w': high_52w,
            'low_52w': low_52w,
            'position_52w': position_52w,
            'is_near_historical_high': position_pct > 85,
            'is_near_historical_low': position_pct < 15,
            'is_near_52w_high': position_52w > 85,
            'is_near_52w_low': position_52w < 15,
        }
    
    def calculate_probability_analysis(self, horizons=(5, 20, 60, 120)):
        """计算历史概率统计"""
        if self.data is None or len(self.data) < 200:
            return
            
        df = self.data.copy()
        
        # 计算前瞻收益率
        for h in horizons:
            df[f'fwd_{h}d'] = df['close'].shift(-h) / df['close'] - 1.0
        
        # 获取当前状态
        latest = df.iloc[-1]
        price = latest['close']
        
        # 定义条件
        cond_bull = (
            (df['close'] > df['MA20']) &
            (df['close'] > df['EMA50']) &
            (df['close'] > df['EMA200']) &
            (df['MACD'] > df['MACD_Signal'])
        )
        
        cond_strong = cond_bull & (df['RSI'] >= 70) & (df['high'] >= df['Donchian_High'])
        
        # 当前状态
        current_state = {
            'ma_above': int((price > latest['MA20']) + (price > latest['EMA50']) + (price > latest['EMA200'])),
            'rsi': float(latest['RSI']) if np.isfinite(latest['RSI']) else None,
            'macd_positive': bool(latest['MACD'] > latest['MACD_Signal']),
            'up_breakout': bool(latest['high'] >= latest['Donchian_High'])
        }
        
        # 计算概率
        results = {}
        for label, mask in [('strong_bullish', cond_strong), ('bullish', cond_bull)]:
            subset = df[mask].copy()
            results[label] = {
                'sample_size': len(subset),
                'probabilities': {}
            }
            
            for h in horizons:
                if len(subset) > h:
                    subset_valid = subset.iloc[:-h]
                    fr = subset_valid[f'fwd_{h}d'].dropna()
                    
                    if len(fr) > 0:
                        prob_up = float((fr > 0).sum()) / len(fr)
                        prob_up_2pct = float((fr > 0.02).sum()) / len(fr)
                        prob_up_5pct = float((fr > 0.05).sum()) / len(fr)
                        prob_down = float((fr < 0).sum()) / len(fr)
                        
                        results[label]['probabilities'][h] = {
                            'n': len(fr),
                            'prob_up': prob_up,
                            'prob_up_2pct': prob_up_2pct,
                            'prob_up_5pct': prob_up_5pct,
                            'prob_down': prob_down,
                            'avg_return': float(fr.mean()),
                            'median_return': float(fr.median())
                        }
        
        self.probability_analysis = {
            'current_state': current_state,
            'results': results
        }
    
    def calculate_multi_dimensional_risk(self):
        """多维度风险评估 - 优化版本，增强趋势分析权重，特别优化ETF评分"""
        if self.data is None or len(self.data) < 200:
            return
            
        latest = self.data.iloc[-1]
        risk_factors = []
        risk_weights = []
        risk_details = {}
        
        # 检测是否为ETF或指数
        is_etf_or_index = self._is_etf_or_index(self.symbol)
        
        # 1. RSI风险（权重降至10%，减少单一指标影响，ETF更加宽容）
        rsi = float(latest.get('RSI', 50))
        
        # 获取趋势强度用于RSI评判调整
        price = float(latest['close'])
        ma20 = float(latest.get('MA20', price))
        ma50 = float(latest.get('MA50', price))
        ma200 = float(latest.get('MA200', price))
        macd = float(latest.get('MACD', 0))
        macd_signal = float(latest.get('MACD_Signal', 0))
        
        trend_score = sum([
            price > ma20, price > ma50, price > ma200,
            ma20 > ma50, ma50 > ma200, macd > macd_signal
        ])
        
        # RSI风险评估（趋势强劲时更宽容，ETF更宽容）
        if rsi > 85:
            if trend_score >= 5 and is_etf_or_index:
                risk_factors.append(60)  # ETF强势趋势中超买风险降低
                risk_details['rsi'] = f"RSI极度超买({rsi:.1f})但趋势强劲(ETF)"
            elif trend_score >= 5:
                risk_factors.append(70)  # 个股趋势强时也降低风险
                risk_details['rsi'] = f"RSI极度超买({rsi:.1f})但趋势强劲"
            else:
                risk_factors.append(85)
                risk_details['rsi'] = f"RSI极度超买({rsi:.1f})"
        elif rsi > 75:
            if trend_score >= 4 and is_etf_or_index:
                risk_factors.append(50)  # ETF趋势好时显著降低风险
                risk_details['rsi'] = f"RSI超买({rsi:.1f})但趋势良好(ETF)"
            elif trend_score >= 4:
                risk_factors.append(60)
                risk_details['rsi'] = f"RSI超买({rsi:.1f})但趋势良好"
            else:
                risk_factors.append(70)
                risk_details['rsi'] = f"RSI超买({rsi:.1f})"
        elif rsi > 65:
            risk_factors.append(45 if not is_etf_or_index else 35)
            risk_details['rsi'] = f"RSI偏高({rsi:.1f})"
        elif rsi < 20:
            # 极度超卖时仍有反弹风险，不要过于乐观
            risk_factors.append(55)
            risk_details['rsi'] = f"RSI极度超卖({rsi:.1f})"
        elif rsi < 30:
            risk_factors.append(35)
            risk_details['rsi'] = f"RSI超卖({rsi:.1f})"
        else:
            risk_factors.append(30)
            risk_details['rsi'] = f"RSI正常({rsi:.1f})"
        risk_weights.append(0.08)  # 从0.1降至0.08，为资金流让出权重

        # 2. 历史位置风险（权重调整为22%）
        pos_pct = self.position_analysis.get('position_pct', 50)
        if pos_pct > 90:
            if trend_score >= 5 and is_etf_or_index:
                risk_factors.append(65)  # ETF强势突破高位风险降低
                risk_details['position'] = f"创新高位({pos_pct:.1f}%)但趋势强劲(ETF)"
            elif trend_score >= 4:
                risk_factors.append(75)  # 强趋势时高位风险降低
                risk_details['position'] = f"接近历史高位({pos_pct:.1f}%)但趋势强劲"
            else:
                risk_factors.append(85)
                risk_details['position'] = f"接近历史高位({pos_pct:.1f}%)"
        elif pos_pct > 75:
            if is_etf_or_index and trend_score >= 4:
                risk_factors.append(50)  # ETF趋势好时高位风险大幅降低
                risk_details['position'] = f"位置较高({pos_pct:.1f}%)但趋势强劲(ETF)"
            else:
                risk_factors.append(65)
                risk_details['position'] = f"位置偏高({pos_pct:.1f}%)"
        elif pos_pct < 25:
            risk_factors.append(25)
            risk_details['position'] = f"位置偏低({pos_pct:.1f}%)"
        else:
            risk_factors.append(40)
            risk_details['position'] = f"位置适中({pos_pct:.1f}%)"
        risk_weights.append(0.22)  # 从0.25调整为0.22
        
        # 3. 波动率风险（权重保持15%）
        atr_ratio = float(latest.get('ATR_Ratio', 0.02))
        if atr_ratio > 0.05:
            risk_factors.append(75)
            risk_details['volatility'] = f"波动率很高({atr_ratio*100:.1f}%)"
        elif atr_ratio > 0.03:
            risk_factors.append(55)
            risk_details['volatility'] = f"波动率偏高({atr_ratio*100:.1f}%)"
        else:
            risk_factors.append(30)
            risk_details['volatility'] = f"波动率正常({atr_ratio*100:.1f}%)"
        risk_weights.append(0.13)  # 从0.15调整为0.13

        # 4. 趋势风险（权重调整为30%）
        price = float(latest['close'])
        ma20 = float(latest.get('MA20', price))
        ma50 = float(latest.get('MA50', price))
        ma200 = float(latest.get('MA200', price))
        macd = float(latest.get('MACD', 0))
        macd_signal = float(latest.get('MACD_Signal', 0))
        
        # 趋势评分系统（更详细）
        trend_score = 0
        trend_details = []
        
        if price > ma20:
            trend_score += 1
            trend_details.append("价格>MA20")
        if price > ma50:
            trend_score += 1  
            trend_details.append("价格>MA50")
        if price > ma200:
            trend_score += 1
            trend_details.append("价格>MA200")
        if ma20 > ma50:
            trend_score += 1
            trend_details.append("MA20>MA50")
        if ma50 > ma200:
            trend_score += 1
            trend_details.append("MA50>MA200")
        if macd > macd_signal:
            trend_score += 1
            trend_details.append("MACD金叉")
            
        # 趋势风险评级（更精细化）
        if trend_score >= 5:
            risk_factors.append(45)  # 完美多头，但可能过热
            risk_details['trend'] = "完美多头排列(可能过热)"
        elif trend_score == 4:
            risk_factors.append(35)
            risk_details['trend'] = "强势上升趋势"
        elif trend_score == 3:
            risk_factors.append(40)
            risk_details['trend'] = "趋势向上"
        elif trend_score == 2:
            risk_factors.append(55)
            risk_details['trend'] = "趋势不明"
        elif trend_score == 1:
            risk_factors.append(70)  # 明显偏空，风险较高
            risk_details['trend'] = "趋势偏弱"
        else:  # trend_score == 0
            risk_factors.append(80)  # 全面空头排列，风险很高
            risk_details['trend'] = "空头排列(风险高)"
            
        risk_weights.append(0.3)  # 从0.35调整为0.3

        # 5. 成交量风险（权重调整为12%）
        vol_ratio = float(latest.get('Volume_Ratio', 1.0))
        if vol_ratio > 2.5:
            risk_factors.append(75)
            risk_details['volume'] = f"成交量异常放大({vol_ratio:.1f}倍)"
        elif vol_ratio > 1.5:
            risk_factors.append(45)
            risk_details['volume'] = f"成交量放大({vol_ratio:.1f}倍)"
        elif vol_ratio < 0.5:
            risk_factors.append(65)  # 量能不足也是风险
            risk_details['volume'] = f"成交量萎缩({vol_ratio:.1f}倍)"
        else:
            risk_factors.append(35)
            risk_details['volume'] = f"成交量正常({vol_ratio:.1f}倍)"
        risk_weights.append(0.12)  # 从0.15调整为0.12

        # 6. 资金流向风险（新增，权重15%）
        if self.enable_capital_flow and self.capital_flow_analyzer and self._is_a_share_stock():
            try:
                # 获取资金流向分析结果
                flow_result = self.capital_flow_analyzer.analyze_stock_money_flow(self.symbol, days=20)
                self.capital_flow_analysis = flow_result

                main_inflow_ratio = flow_result.get('main_inflow_ratio', 0)
                institutional_interest = flow_result.get('institutional_interest', 'unknown')
                flow_consistency = flow_result.get('flow_consistency', 0)

                # 基于主力资金流向评估风险
                if main_inflow_ratio is None:
                    risk_factors.append(50)  # 无数据时中性风险
                    risk_details['capital_flow'] = "资金流向数据缺失"
                elif main_inflow_ratio > 0.05:  # 5%以上净流入
                    risk_factors.append(25)  # 大幅降低风险
                    risk_details['capital_flow'] = f"主力大幅流入({main_inflow_ratio:.1%})"
                elif main_inflow_ratio > 0.02:  # 2%以上净流入
                    risk_factors.append(35)  # 适度降低风险
                    risk_details['capital_flow'] = f"主力适度流入({main_inflow_ratio:.1%})"
                elif main_inflow_ratio > -0.02:  # 小幅波动
                    risk_factors.append(45)  # 轻微风险
                    risk_details['capital_flow'] = f"资金流向平衡({main_inflow_ratio:.1%})"
                elif main_inflow_ratio > -0.05:  # 2-5%流出
                    risk_factors.append(65)  # 适度提高风险
                    risk_details['capital_flow'] = f"主力适度流出({abs(main_inflow_ratio):.1%})"
                else:  # 5%以上流出
                    risk_factors.append(80)  # 大幅提高风险
                    risk_details['capital_flow'] = f"主力大幅流出({abs(main_inflow_ratio):.1%})"

                # 机构关注度调整
                if institutional_interest == 'high':
                    risk_factors[-1] -= 5  # 高关注度降低风险
                elif institutional_interest == 'low':
                    risk_factors[-1] += 5  # 低关注度提高风险

                # 确保风险分数在合理范围内
                risk_factors[-1] = max(15, min(85, risk_factors[-1]))

            except Exception as e:
                print(f"⚠️ 资金流向风险评估失败: {e}")
                risk_factors.append(50)  # 分析失败时使用中性风险
                risk_details['capital_flow'] = "资金流向分析失败"
                self.capital_flow_analysis = {'error': str(e)}

        else:
            # 非A股或未启用资金流分析时跳过
            risk_factors.append(50)  # 中性风险
            risk_details['capital_flow'] = "不支持资金流分析"

        risk_weights.append(0.15)  # 资金流风险权重15%

        # 计算加权风险分数
        self.risk_score = sum(r * w for r, w in zip(risk_factors, risk_weights))
        self.risk_details = risk_details
        
        # 风险分级
        if self.risk_score >= 70:
            self.risk_level = "高风险"
        elif self.risk_score >= 50:
            self.risk_level = "中高风险"
        elif self.risk_score >= 40:
            self.risk_level = "中等风险"
        elif self.risk_score >= 25:
            self.risk_level = "中低风险"
        else:
            self.risk_level = "低风险"
    
    def analyze_fundamental_data(self):
        """分析基本面数据"""
        if not self.enable_fundamental or self.is_global_index(self.symbol):
            self.fundamental_analysis = {'message': '跳过基本面分析（指数或已禁用）'}
            return
        
        try:
            provider = DataProviderFactory.create('tushare', enableCache=True)
            financial_data = provider.getFinancialData(self.symbol)
            
            if not financial_data or not financial_data.get('eps_data'):
                self.fundamental_analysis = {'message': '无基本面数据'}
                return
            
            # 估值分析
            valuation_analysis = self._analyze_valuation(financial_data)
            
            # 盈利质量分析  
            profitability_analysis = self._analyze_profitability(financial_data)
            
            # 成长性分析
            growth_analysis = self._analyze_growth(financial_data)
            
            # 综合基本面评分
            fundamental_score = self._calculate_fundamental_score(
                valuation_analysis, profitability_analysis, growth_analysis
            )
            
            self.fundamental_analysis = {
                'valuation': valuation_analysis,
                'profitability': profitability_analysis, 
                'growth': growth_analysis,
                'fundamental_score': fundamental_score,
                'has_data': True
            }
            
        except Exception as e:
            print(f"⚠️ 基本面分析失败: {e}")
            self.fundamental_analysis = {'message': f'分析失败: {str(e)}'}
    
    def _analyze_valuation(self, financial_data):
        """估值分析"""
        try:
            latest_pe = financial_data.get('latest_pe')
            latest_pb = financial_data.get('latest_pb')
            
            analysis = {'pe': None, 'pb': None, 'valuation_level': '未知'}
            score = 0
            
            # PE分析
            if latest_pe and latest_pe > 0:
                analysis['pe'] = latest_pe
                # 数据验证
                if latest_pe > 1000:
                    pe_level = '异常高(数据需核实)'
                    score -= 20
                    analysis['warning'] = f'PE值异常高({latest_pe:.1f})，可能数据有误或公司刚扭亏'
                elif latest_pe < 15:
                    pe_level = '低估'
                    score += 25
                elif latest_pe < 25:
                    pe_level = '合理'
                    score += 15
                elif latest_pe < 50:
                    pe_level = '偏高'
                    score += 5
                else:
                    pe_level = '高估'
                    score -= 10
                analysis['pe_level'] = pe_level
            
            # PB分析
            if latest_pb and latest_pb > 0:
                analysis['pb'] = latest_pb
                # 数据验证
                if latest_pb > 50:
                    pb_level = '异常高(需核实)'
                    score -= 15
                    if not analysis.get('warning'):
                        analysis['warning'] = f'PB值异常高({latest_pb:.1f})，需要核实数据'
                elif latest_pb < 1.5:
                    pb_level = '低估'
                    score += 15
                elif latest_pb < 3:
                    pb_level = '合理'
                    score += 10
                elif latest_pb < 5:
                    pb_level = '偏高'
                    score += 0
                else:
                    pb_level = '高估'
                    score -= 10
                analysis['pb_level'] = pb_level
            
            # 综合估值水平
            if score >= 30:
                analysis['valuation_level'] = '明显低估'
            elif score >= 20:
                analysis['valuation_level'] = '相对低估' 
            elif score >= 10:
                analysis['valuation_level'] = '估值合理'
            elif score >= 0:
                analysis['valuation_level'] = '估值偏高'
            else:
                analysis['valuation_level'] = '估值过高'
            
            analysis['valuation_score'] = score
            return analysis
            
        except Exception as e:
            return {'error': str(e), 'valuation_score': 0}
    
    def _analyze_profitability(self, financial_data):
        """盈利质量分析"""
        try:
            eps_data = financial_data.get('eps_data', [])
            if not eps_data or len(eps_data) < 4:
                return {'message': 'EPS数据不足', 'profitability_score': 0}
            
            # 获取最近4个季度EPS
            recent_eps = [item['eps'] for item in eps_data[:4]]
            
            # 计算ROE代理指标（基于EPS稳定性）
            eps_std = np.std(recent_eps) if len(recent_eps) > 1 else 0
            eps_mean = np.mean(recent_eps)
            
            analysis = {}
            score = 0
            
            # EPS稳定性分析
            if eps_mean > 0:
                cv = eps_std / eps_mean if eps_mean != 0 else float('inf')
                if cv < 0.2:
                    stability = '非常稳定'
                    score += 20
                elif cv < 0.4:
                    stability = '较为稳定'
                    score += 15
                elif cv < 0.6:
                    stability = '一般稳定'
                    score += 10
                else:
                    stability = '波动较大'
                    score += 0
            else:
                stability = '盈利为负'
                score -= 20
            
            analysis['eps_stability'] = stability
            analysis['recent_eps_mean'] = eps_mean
            analysis['profitability_score'] = score
            
            return analysis
            
        except Exception as e:
            return {'error': str(e), 'profitability_score': 0}
    
    def _analyze_growth(self, financial_data):
        """成长性分析"""
        try:
            eps_data = financial_data.get('eps_data', [])
            if not eps_data or len(eps_data) < 8:
                return {'message': 'EPS数据不足', 'growth_score': 0}
            
            # 获取最近8个季度EPS用于同比分析
            recent_eps = [item['eps'] for item in eps_data[:8]]
            
            analysis = {}
            score = 0
            
            # 计算同比增长率（最近4个季度vs前4个季度）
            current_q = recent_eps[:4]
            year_ago_q = recent_eps[4:8]
            
            growth_rates = []
            for i in range(4):
                if year_ago_q[i] > 0:
                    growth_rate = (current_q[i] - year_ago_q[i]) / year_ago_q[i]
                    growth_rates.append(growth_rate)
            
            if growth_rates:
                avg_growth = np.mean(growth_rates)
                
                if avg_growth >= 0.3:  # 30%+增长
                    growth_level = '高速增长'
                    score += 30
                elif avg_growth >= 0.15:  # 15%+增长
                    growth_level = '快速增长'
                    score += 20
                elif avg_growth >= 0.05:  # 5%+增长
                    growth_level = '稳定增长'
                    score += 10
                elif avg_growth >= 0:
                    growth_level = '缓慢增长'
                    score += 5
                else:
                    growth_level = '负增长'
                    score -= 15
                
                analysis['avg_yoy_growth'] = avg_growth
                analysis['growth_level'] = growth_level
            else:
                analysis['growth_level'] = '无法计算'
                score = 0
            
            analysis['growth_score'] = score
            return analysis
            
        except Exception as e:
            return {'error': str(e), 'growth_score': 0}
    
    def _calculate_fundamental_score(self, valuation, profitability, growth):
        """计算综合基本面评分"""
        try:
            val_score = valuation.get('valuation_score', 0)
            prof_score = profitability.get('profitability_score', 0)
            growth_score = growth.get('growth_score', 0)
            
            # 加权计算: 估值30% + 盈利质量35% + 成长性35%
            total_score = val_score * 0.3 + prof_score * 0.35 + growth_score * 0.35
            
            # 评级
            if total_score >= 25:
                rating = '优秀'
            elif total_score >= 15:
                rating = '良好'
            elif total_score >= 5:
                rating = '一般'
            elif total_score >= -5:
                rating = '较弱'
            else:
                rating = '差'
            
            return {
                'total_score': round(total_score, 1),
                'rating': rating,
                'components': {
                    'valuation': val_score,
                    'profitability': prof_score,
                    'growth': growth_score
                }
            }
        except:
            return {'total_score': 0, 'rating': '未知'}

    def generate_comprehensive_recommendation(self):
        """生成综合投资建议 - 优化版本，增加趋势否决权"""
        latest = self.data.iloc[-1]
        
        # 收集关键信息
        rsi = float(latest.get('RSI', 50))
        pos_pct = self.position_analysis.get('position_pct', 50)
        distance_to_high = self.position_analysis.get('distance_to_high_pct', 20)
        
        # 详细趋势判断
        price = float(latest['close'])
        ma20 = float(latest.get('MA20', price))
        ma50 = float(latest.get('MA50', price))
        ma200 = float(latest.get('MA200', price))
        macd = float(latest.get('MACD', 0))
        macd_signal = float(latest.get('MACD_Signal', 0))
        
        # 计算趋势强度
        trend_score = 0
        if price > ma20:
            trend_score += 1
        if price > ma50:
            trend_score += 1
        if price > ma200:
            trend_score += 1
        if ma20 > ma50:
            trend_score += 1
        if ma50 > ma200:
            trend_score += 1
        if macd > macd_signal:
            trend_score += 1
            
        # 趋势分类
        if trend_score >= 5:
            trend_status = "强劲多头"
            trend_bullish = True
        elif trend_score >= 3:
            trend_status = "偏多头"
            trend_bullish = True
        elif trend_score == 2:
            trend_status = "趋势不明"
            trend_bullish = False
        elif trend_score == 1:
            trend_status = "偏空头"
            trend_bearish = True
        else:
            trend_status = "明显空头"
            trend_bearish = True
        
        # 概率支撑
        prob_support = False
        if 'bullish' in self.probability_analysis.get('results', {}):
            bullish_probs = self.probability_analysis['results']['bullish'].get('probabilities', {})
            if 20 in bullish_probs and bullish_probs[20].get('prob_up', 0) > 0.6:
                prob_support = True
        
        # 基本面支撑
        fundamental_support = False
        fundamental_score = 0
        if self.fundamental_analysis.get('has_data'):
            fundamental_score = self.fundamental_analysis['fundamental_score'].get('total_score', 0)
            if fundamental_score >= 15:  # 基本面良好
                fundamental_support = True
        
        # 综合决策逻辑
        decision_factors = []
        
        # ======== 新增：趋势否决权检查 ========
        # 如果趋势明显空头，不论其他条件如何都不建议加仓
        if trend_score <= 1:  # 明显空头或偏空头
            if trend_score == 0:
                self.recommendation = "谨慎观望 → 等待趋势改善"
                decision_factors.append(f"全面空头排列({trend_status})")
                decision_factors.append("趋势否决权：不宜加仓")
            else:  # trend_score == 1
                self.recommendation = "观望为主 → 等待确认"
                decision_factors.append(f"趋势偏弱({trend_status})")
                decision_factors.append("趋势风险较高")
                
            # 即使RSI超卖也要保守
            if rsi < 30:
                decision_factors.append(f"RSI超卖({rsi:.1f})但趋势未改")
            
            self.action_details = {
                'action': '持有观望',
                'percentage': '维持现状或小幅减仓',
                'reason': decision_factors
            }
            return
        
        # ======== 原有逻辑：趋势正常时的决策 ========
        
        # 基于风险等级的基础建议
        if self.risk_score >= 70:
            base_action = "减仓/观望"
            decision_factors.append(f"风险较高({self.risk_score:.0f}/100)")
        elif self.risk_score >= 50:
            base_action = "谨慎持有"
            decision_factors.append(f"风险适中({self.risk_score:.0f}/100)")
        else:
            base_action = "适度加仓"
            decision_factors.append(f"风险较低({self.risk_score:.0f}/100)")
        
        # 趋势因素调整（现在权重更高）
        decision_factors.append(f"趋势状态: {trend_status}")
        
        # 基本面因素调整
        if fundamental_support:
            decision_factors.append(f"基本面支撑({fundamental_score:.1f}分)")
        elif fundamental_score < 0:
            decision_factors.append(f"基本面较弱({fundamental_score:.1f}分)")
            
        # 精细化调整因素
        if distance_to_high < 10 and rsi > 80:
            self.recommendation = f"{base_action} → 减仓优先"
            decision_factors.append("接近历史高位且超买")
        elif distance_to_high > 20 and trend_bullish and (prob_support or fundamental_support):
            self.recommendation = f"{base_action} → 持有/加仓"
            decision_factors.append("仍有上涨空间且趋势/基本面良好")
        elif pos_pct < 30 and rsi < 30 and trend_bullish and fundamental_support:
            # 只有趋势向好时才积极加仓
            self.recommendation = "适度加仓"
            decision_factors.append("位置较低、超卖且趋势+基本面支撑")
        elif pos_pct < 30 and rsi < 30 and trend_score >= 2:
            # 至少趋势不明朗才考虑小幅加仓
            self.recommendation = "小幅加仓"
            decision_factors.append("位置较低且超卖，但需关注趋势")
        else:
            self.recommendation = base_action
        
        # 具体操作建议
        if "减仓" in self.recommendation:
            self.action_details = {
                'action': '减仓',
                'percentage': '30-50%',
                'reason': decision_factors
            }
        elif "加仓" in self.recommendation:
            # 根据趋势强度和基本面调整加仓幅度
            if trend_score >= 4 and fundamental_support:
                percentage = '20-40%'
            elif trend_score >= 3:
                percentage = '15-25%'  
            else:
                percentage = '10-20%'  # 趋势不强时保守
                
            self.action_details = {
                'action': '加仓',
                'percentage': percentage,
                'reason': decision_factors
            }
        else:
            self.action_details = {
                'action': '持有观望',
                'percentage': '维持现状',
                'reason': decision_factors
            }
    
    def analyze(self):
        """执行完整分析"""
        print(f"\n{'='*80}")
        print(f"综合投资分析报告 - {self.symbol}")
        print(f"{'='*80}")
        
        # 获取数据
        if self.fetch_data() is None:
            print("❌ 无法获取数据")
            return
            
        # 执行各项分析
        self.calculate_indicators()
        self.analyze_historical_position()
        self.calculate_probability_analysis()
        
        # 基本面分析（股票特有）
        if self.enable_fundamental:
            self.analyze_fundamental_data()
        
        self.calculate_multi_dimensional_risk()
        self.generate_comprehensive_recommendation()
        
        # 输出结果
        self._print_results()
        
    def _print_results(self):
        """打印分析结果"""
        latest = self.data.iloc[-1]
        
        # 0. 数据时间戳
        data_date = self.data.index[-1]
        if hasattr(data_date, 'strftime'):
            date_str = data_date.strftime('%Y-%m-%d')
        else:
            date_str = str(data_date)[:10]
        
        print(f"\n📅 数据日期: {date_str}")
        
        # 1. 基本信息
        print(f"\n📊 基本信息")
        print(f"  当前价格: {self.position_analysis['current_price']:.2f}")
        print(f"  历史最高: {self.position_analysis['historical_high']:.2f}")
        print(f"  历史最低: {self.position_analysis['historical_low']:.2f}")
        
        # 2. 位置分析
        print(f"\n📈 位置分析")
        print(f"  历史位置: {self.position_analysis['position_pct']:.1f}%")
        print(f"  距离历史高点: {self.position_analysis['distance_to_high_pct']:.1f}%")
        print(f"  52周位置: {self.position_analysis['position_52w']:.1f}%")
        
        # 3. 技术指标
        print(f"\n📊 技术指标")
        print(f"  RSI: {float(latest.get('RSI', 0)):.1f}")
        print(f"  MACD: {'多头' if float(latest.get('MACD', 0)) > float(latest.get('MACD_Signal', 0)) else '空头'}")
        print(f"  均线: {'多头排列' if float(latest['close']) > float(latest.get('MA20', 0)) > float(latest.get('MA50', 0)) else '未完全多头'}")
        
        # 4. 基本面分析
        if self.fundamental_analysis.get('has_data'):
            print(f"\n💰 基本面分析")
            
            fund_score = self.fundamental_analysis['fundamental_score']
            print(f"  综合评分: {fund_score['total_score']:.1f}分 ({fund_score['rating']})")
            
            # 估值分析
            valuation = self.fundamental_analysis['valuation']
            if valuation.get('pe'):
                print(f"  市盈率(PE): {valuation['pe']:.1f} ({valuation.get('pe_level', '未知')})")
            if valuation.get('pb'):
                print(f"  市净率(PB): {valuation['pb']:.2f} ({valuation.get('pb_level', '未知')})")
            print(f"  估值水平: {valuation.get('valuation_level', '未知')}")
            
            # 数据警告
            if valuation.get('warning'):
                print(f"  ⚠️ 数据警告: {valuation['warning']}")
            
            # 盈利质量
            profitability = self.fundamental_analysis['profitability']
            if 'eps_stability' in profitability:
                print(f"  盈利稳定性: {profitability['eps_stability']}")
                if 'recent_eps_mean' in profitability:
                    print(f"  近期平均EPS: {profitability['recent_eps_mean']:.3f}")
            
            # 成长性
            growth = self.fundamental_analysis['growth']
            if 'growth_level' in growth:
                print(f"  成长性: {growth['growth_level']}")
                if 'avg_yoy_growth' in growth:
                    print(f"  平均同比增长: {growth['avg_yoy_growth']*100:.1f}%")
        else:
            fund_msg = self.fundamental_analysis.get('message', '无基本面数据')
            print(f"\n💰 基本面分析: {fund_msg}")
        
        # 5. 概率统计
        print(f"\n📈 历史概率分析")
        prob_results = self.probability_analysis.get('results', {})
        
        for condition in ['bullish', 'strong_bullish']:
            if condition in prob_results:
                cond_data = prob_results[condition]
                print(f"\n  {condition}条件 (样本数: {cond_data['sample_size']})")
                
                for horizon in [5, 20, 60]:
                    if horizon in cond_data['probabilities']:
                        probs = cond_data['probabilities'][horizon]
                        print(f"    {horizon}日: 上涨概率{probs['prob_up']*100:.1f}%, "
                              f"下跌概率{probs['prob_down']*100:.1f}%, "
                              f"平均收益{probs['avg_return']*100:.1f}%")
        
        # 5. 风险评估
        print(f"\n⚠️  风险评估")
        print(f"  综合风险分数: {self.risk_score:.1f}/100")
        print(f"  风险等级: {self.risk_level}")
        print(f"  风险详情:")
        for key, desc in self.risk_details.items():
            print(f"    - {desc}")
        
        # 6. 资金流向分析（如果可用）
        if self.capital_flow_analysis and 'error' not in self.capital_flow_analysis:
            print(f"\n💰 资金流向分析")
            flow = self.capital_flow_analysis
            print(f"  主力净流入比例: {flow.get('main_inflow_ratio', 'N/A'):.1%}" if flow.get('main_inflow_ratio') is not None else "  主力净流入比例: 无数据")
            print(f"  大单趋势: {flow.get('large_order_trend', 'N/A')}")
            print(f"  机构关注度: {flow.get('institutional_interest', 'N/A')}")
            print(f"  综合评分: {flow.get('comprehensive_score', 'N/A'):.0f}/100" if flow.get('comprehensive_score') is not None else "  综合评分: 无数据")

            # 显示风险和机会信号
            risk_signals = flow.get('risk_signals', [])
            opportunity_signals = flow.get('opportunity_signals', [])

            if risk_signals:
                print(f"  ⚠️ 风险信号: {'; '.join(risk_signals)}")
            if opportunity_signals:
                print(f"  ✨ 机会信号: {'; '.join(opportunity_signals)}")

        # 7. 投资建议
        print(f"\n🎯 投资建议")
        print(f"  建议: {self.recommendation}")
        print(f"  操作: {self.action_details['action']} ({self.action_details['percentage']})")
        print(f"  理由:")
        for reason in self.action_details['reason']:
            print(f"    - {reason}")
        
        # 7. 关键提示
        print(f"\n💡 关键提示")
        if self.position_analysis['is_near_historical_high']:
            print(f"  ⚠️  接近历史高位，注意风险")
        if self.position_analysis['is_near_52w_high']:
            print(f"  📈 接近52周高点")
        if float(latest.get('RSI', 50)) > 80:
            print(f"  🔥 RSI超买，可能有短期回调")
        if self.position_analysis['distance_to_high_pct'] > 20:
            print(f"  ✅ 距离历史高点仍有{self.position_analysis['distance_to_high_pct']:.0f}%空间")
        
        # 概率警示
        if 'bullish' in prob_results:
            bullish_20d = prob_results['bullish'].get('probabilities', {}).get(20, {})
            if bullish_20d.get('prob_down', 0) > 0.6:
                print(f"  ⚠️  历史统计显示20日内下跌概率偏高")


def main():
    parser = argparse.ArgumentParser(
        description='综合投资分析工具 - 整合位置分析、风险评估和概率统计',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python analyst/integrated_advisor.py --symbol 000300.SH
  python analyst/integrated_advisor.py --symbol IXIC --days-back 3000
  python analyst/integrated_advisor.py --symbol 588000.SH
        """
    )
    
    parser.add_argument('--symbol', default='000300.SH', help='标的代码')
    parser.add_argument('--days-back', type=int, default=2500, help='历史数据天数')
    
    args = parser.parse_args()
    
    advisor = IntegratedAdvisor(args.symbol, args.days_back)
    advisor.analyze()
    

if __name__ == '__main__':
    main()
